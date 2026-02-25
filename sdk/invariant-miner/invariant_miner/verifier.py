"""
invariant_miner/verifier.py
==========================
Verifier — stateful four-gate receipt verifier.

Validators use this to verify miner receipts each tempo.
Miners can use this locally to pre-validate receipts before submission.

The verifier maintains a monotonic counter state per agent (Gate 3).
Counter state is persisted to disk so restarts do not open a replay window.

Four gates execute in sequence; the first failure short-circuits.
Two honest validators on the same receipt always produce identical results.
Disagreement between validators is on-chain evidence of compromise.

Usage (validator side)
----------------------
    from invariant_miner import Registry, Verifier, GateResult

    reg = Registry(path="./validator_data/registry.json")
    reg.approve_model(hash_model("llama-3.2-1b-instruct-v1"))
    reg.save()

    verifier = Verifier(
        registry=reg,
        state_path="./validator_data/counter_state.json",
    )

    # Verify a single receipt
    result = verifier.verify(receipt)
    if GateResult.is_pass(result.result):
        score_on_quality(receipt)
    else:
        log_violation(result)

    # Verify a batch (one full tempo sweep)
    results = verifier.verify_batch(receipts)

Usage (miner pre-flight check)
-------------------------------
    # Build a local verifier to pre-check before submitting
    local_verifier = Verifier(
        registry=reg,
        state_path="./miner_data/counter_state.json",
    )
    result = local_verifier.verify(receipt)
    if not GateResult.is_pass(result.result):
        logger.error("Pre-flight check failed: %s — do not submit", result.detail)
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from invariant_miner._backend import _using_rust
from invariant_miner.errors import VerifierError
from invariant_miner.gate import GateResult
from invariant_miner.receipt import Receipt
from invariant_miner.registry import Registry

# ---------------------------------------------------------------------------
# VerifyResult
# ---------------------------------------------------------------------------


@dataclass
class VerifyResult:
    """Result of a single receipt verification pass through all four gates.

    Attributes
    ----------
    result : str
        One of the :class:`~invariant_miner.GateResult` constants.
        ``GateResult.PASS`` means all four gates passed.
    gate_number : int
        0 if all gates passed, 1–4 indicating which gate failed first,
        -1 for parse errors.
    detail : str
        Human-readable description of the failure (empty on PASS).
    agent_id : str
        The agent_id from the receipt that was verified (64-char hex).
    counter : int
        The counter from the receipt that was verified.
    verified_at : float
        Unix timestamp when verification completed.

    Example:
        >>> result = verifier.verify(receipt)
        >>> if result.is_pass():
        ...     apply_quality_score(receipt)
        ... else:
        ...     print(f"Gate {result.gate_number} failed: {result.detail}")
    """

    result: str
    gate_number: int
    detail: str
    agent_id: str = ""
    counter: int = 0
    verified_at: float = field(default_factory=time.time)

    def is_pass(self) -> bool:
        """Return True if all four gates passed."""
        return self.result == GateResult.PASS

    def to_dict(self) -> dict:
        """Return the result as a plain dict (JSON-serialisable)."""
        return {
            "result": self.result,
            "gate_number": self.gate_number,
            "detail": self.detail,
            "agent_id": self.agent_id,
            "counter": self.counter,
            "verified_at": self.verified_at,
        }

    @classmethod
    def pass_result(cls, agent_id: str, counter: int) -> "VerifyResult":
        """Construct a passing VerifyResult."""
        return cls(
            result=GateResult.PASS,
            gate_number=0,
            detail="",
            agent_id=agent_id,
            counter=counter,
        )

    @classmethod
    def fail_result(
        cls,
        gate: int,
        result: str,
        detail: str,
        agent_id: str = "",
        counter: int = 0,
    ) -> "VerifyResult":
        """Construct a failing VerifyResult."""
        return cls(
            result=result,
            gate_number=gate,
            detail=detail,
            agent_id=agent_id,
            counter=counter,
        )

    def __repr__(self) -> str:
        if self.is_pass():
            return f"VerifyResult(PASS, agent={self.agent_id[:12]}…, counter={self.counter})"
        return (
            f"VerifyResult(gate={self.gate_number}, "
            f"result={self.result}, "
            f"agent={self.agent_id[:12] if self.agent_id else '?'}…, "
            f"detail={self.detail!r})"
        )


# ---------------------------------------------------------------------------
# Counter state persistence
# ---------------------------------------------------------------------------


class _CounterState:
    """Persisted per-agent counter state.

    Maps agent_id_hex → last confirmed counter value.
    Atomic write pattern: write to .tmp then os.replace() for crash safety.
    """

    def __init__(self, path: Optional[str]) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._counters: Dict[str, int] = {}

        if path and os.path.isfile(path):
            self._load()

    def _load(self) -> None:
        if not self._path:
            return
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            with self._lock:
                self._counters = {
                    k.lower(): int(v) for k, v in data.get("counters", {}).items()
                }
        except (OSError, json.JSONDecodeError, ValueError):
            pass  # corrupt or absent — start clean

    def save(self) -> None:
        if not self._path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self._path)), exist_ok=True)
        with self._lock:
            data = {"counters": dict(self._counters)}
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, self._path)

    def get(self, agent_id: str) -> int:
        with self._lock:
            return self._counters.get(agent_id.lower(), 0)

    def advance(self, agent_id: str, new_counter: int) -> None:
        with self._lock:
            self._counters[agent_id.lower()] = new_counter
        self.save()


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------


class Verifier:
    """Stateful four-gate receipt verifier.

    Maintains counter state per agent across calls so replays are always
    detected, even across restarts (counter state is persisted to disk).

    The verifier is thread-safe — multiple Axon handler threads can call
    :meth:`verify` concurrently.

    Parameters
    ----------
    registry : Registry
        The authorized agent and approved model registry.
        Provides Gate 1 (agent authorization) and Gate 2 (model approval).
    state_path : str, optional
        Path to persist counter state (Gate 3).
        If None, counter state is in-memory only (lost on restart).
        **Production validators should always specify a state_path.**

    Example:
        >>> reg = Registry(path="./data/registry.json")
        >>> reg.approve_model(hash_model("my-model-v1"))
        >>> verifier = Verifier(registry=reg, state_path="./data/state.json")
        >>> result = verifier.verify(receipt)
    """

    def __init__(
        self,
        registry: Registry,
        state_path: Optional[str] = None,
    ) -> None:
        if not isinstance(registry, Registry):
            raise VerifierError(
                f"registry must be a invariant_miner.Registry instance, "
                f"got {type(registry).__name__}"
            )
        self._registry = registry
        self._state = _CounterState(state_path)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Single-receipt verification
    # ------------------------------------------------------------------

    def verify(self, receipt: Receipt) -> VerifyResult:
        """Verify a single receipt through all four gates.

        Gates execute in sequence; the first failure short-circuits and
        returns immediately with zero score.  On success, the counter is
        advanced so this receipt cannot be replayed.

        Gate 1 — Identity Authorization
            Is ``receipt.agent_id`` in the authorized registry?
            Blocks: Sybil attacks, unknown agents, output copying.

        Gate 2 — Model Approval
            Is ``receipt.model_hash`` in the approved model list?
            Blocks: Model impersonation (claiming GPT-4, running llama-1b).

        Gate 3 — Replay Protection
            Is ``receipt.counter`` strictly greater than the last confirmed
            counter for this agent?
            Blocks: Exact replay attacks, counter rollback attacks.

        Gate 4 — Digest Integrity
            Does SHA-256(agent_id || model_hash || execution_hash || counter)
            equal ``receipt.digest``?
            Blocks: Any field tampering, output forgery, cross-tempo caching.

        Args:
            receipt: A :class:`~invariant_miner.receipt.Receipt` to verify.

        Returns:
            A :class:`VerifyResult`.  Check ``result.is_pass()`` first.
            On failure, ``result.gate_number`` identifies the first gate
            that fired and ``result.detail`` describes the failure.

        Example:
            >>> result = verifier.verify(receipt)
            >>> if result.is_pass():
            ...     weight = quality_score * (nts / 100) * freshness
            ... else:
            ...     oap.record_violation(receipt.agent_id, result.gate_number)
        """
        if not isinstance(receipt, Receipt):
            return VerifyResult.fail_result(
                gate=-1,
                result=GateResult.PARSE_ERROR,
                detail=f"Expected Receipt instance, got {type(receipt).__name__}",
            )

        # ── Gate 1: Identity authorization ──────────────────────────────────
        if not self._registry.is_authorized(receipt.agent_id):
            return VerifyResult.fail_result(
                gate=1,
                result=GateResult.GATE1,
                detail=f"agent_id={receipt.agent_id[:12]}… not in authorized registry",
                agent_id=receipt.agent_id,
                counter=receipt.counter,
            )

        # ── Gate 2: Model approval ───────────────────────────────────────────
        if not self._registry.is_approved(receipt.model_hash):
            return VerifyResult.fail_result(
                gate=2,
                result=GateResult.GATE2,
                detail=f"model_hash={receipt.model_hash[:12]}… not in approved model list",
                agent_id=receipt.agent_id,
                counter=receipt.counter,
            )

        # ── Gate 3: Replay protection ────────────────────────────────────────
        with self._lock:
            last_counter = self._state.get(receipt.agent_id)
            if receipt.counter <= last_counter:
                return VerifyResult.fail_result(
                    gate=3,
                    result=GateResult.GATE3,
                    detail=(
                        f"counter={receipt.counter} not > "
                        f"last_confirmed={last_counter} "
                        f"(agent={receipt.agent_id[:12]}…)"
                    ),
                    agent_id=receipt.agent_id,
                    counter=receipt.counter,
                )

            # ── Gate 4: Digest integrity ─────────────────────────────────────
            expected_digest = self._compute_digest(receipt)
            if expected_digest != receipt.digest:
                return VerifyResult.fail_result(
                    gate=4,
                    result=GateResult.GATE4,
                    detail=(
                        f"digest mismatch: "
                        f"expected={expected_digest[:12]}… "
                        f"got={receipt.digest[:12]}…"
                    ),
                    agent_id=receipt.agent_id,
                    counter=receipt.counter,
                )

            # ── All gates passed — advance counter ───────────────────────────
            self._state.advance(receipt.agent_id, receipt.counter)

        return VerifyResult.pass_result(
            agent_id=receipt.agent_id,
            counter=receipt.counter,
        )

    # ------------------------------------------------------------------
    # Batch verification
    # ------------------------------------------------------------------

    def verify_batch(self, receipts: List[Receipt]) -> List[VerifyResult]:
        """Verify a batch of receipts, returning results in the same order.

        Validators call this once per tempo for all miners' receipts.
        Each receipt is verified independently; failures do not affect
        other receipts in the batch.

        Args:
            receipts: A list of :class:`~invariant_miner.receipt.Receipt` objects.

        Returns:
            A list of :class:`VerifyResult` objects in the same order as
            the input receipts.

        Example:
            >>> results = verifier.verify_batch(all_miner_receipts)
            >>> passing = [r for r in results if r.is_pass()]
            >>> print(f"{len(passing)}/{len(results)} receipts passed")
        """
        return [self.verify(r) for r in receipts]

    # ------------------------------------------------------------------
    # Counter queries
    # ------------------------------------------------------------------

    def get_counter(self, agent_id: str) -> int:
        """Return the last confirmed counter for *agent_id*.

        Miners can query this on startup to resync their counter after a
        crash or restart.

        Args:
            agent_id: 64-char hex agent_id.

        Returns:
            Last confirmed counter value (0 if never seen).

        Example:
            >>> last = verifier.get_counter(my_agent_id)
            >>> counter = last + 1   # safe starting point after a restart
        """
        return self._state.get(agent_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_digest(receipt: Receipt) -> str:
        """Recompute the expected digest for *receipt* and return as hex.

        digest = SHA-256(agent_id_bytes || model_hash_bytes ||
                         execution_hash_bytes || counter_be_u64)
        """
        import hashlib
        import struct

        h = hashlib.sha256()
        h.update(bytes.fromhex(receipt.agent_id))
        h.update(bytes.fromhex(receipt.model_hash))
        h.update(bytes.fromhex(receipt.execution_hash))
        h.update(struct.pack(">Q", receipt.counter))
        return h.hexdigest()

    def __repr__(self) -> str:
        return (
            f"Verifier("
            f"agents={self._registry.agent_count()}, "
            f"models={self._registry.model_count()}"
            f")"
        )
