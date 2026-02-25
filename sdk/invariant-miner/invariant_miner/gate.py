"""
invariant_miner/gate.py
======================
GateResult constants — the possible outcomes of receipt verification.

Every call to Verifier.verify() returns one of these values in the
``result`` field of the VerifyResult.

Usage:
    from invariant_miner import GateResult, Verifier

    result = verifier.verify(receipt)
    if result.result == GateResult.PASS:
        # receipt is valid — score on output quality
        ...
    elif result.result == GateResult.GATE3:
        # replay detected — log the violation
        ...
"""

from __future__ import annotations


class GateResult:
    """String constants for gate verification outcomes.

    These match the values returned by both the Rust extension
    (invariant_gates_rs) and the pure Python fallback so callers
    never need to branch on backend.

    Attributes
    ----------
    PASS : str
        All four gates passed. Receipt is valid.
    GATE1 : str
        Gate 1 failed — agent_id is not in the authorized registry.
        Attack blocked: Sybil identity, cross-miner output copying.
    GATE2 : str
        Gate 2 failed — model_hash is not in the approved model list.
        Attack blocked: Model impersonation (claiming GPT-4, running llama-3.2-1b).
    GATE3 : str
        Gate 3 failed — counter is not strictly greater than the last
        confirmed counter for this agent. Attack blocked: exact replay,
        counter rollback.
    GATE4 : str
        Gate 4 failed — SHA-256(agent_id || model_hash || execution_hash
        || counter) does not match the receipt's digest field.
        Attack blocked: any field tampering, output forgery,
        cross-tempo output caching (tempo_id is inside execution_hash).
    PARSE_ERROR : str
        The receipt JSON could not be parsed or decoded.
    """

    PASS: str = "PASS"
    GATE1: str = "GATE1_AGENT_NOT_AUTHORIZED"
    GATE2: str = "GATE2_MODEL_NOT_APPROVED"
    GATE3: str = "GATE3_REPLAY_DETECTED"
    GATE4: str = "GATE4_DIGEST_MISMATCH"
    PARSE_ERROR: str = "PARSE_ERROR"

    # Human-readable labels for logging / reporting
    _LABELS: dict[str, str] = {
        "PASS": "Pass",
        "GATE1_AGENT_NOT_AUTHORIZED": "Gate 1 — Agent not authorized",
        "GATE2_MODEL_NOT_APPROVED": "Gate 2 — Model not approved",
        "GATE3_REPLAY_DETECTED": "Gate 3 — Replay detected",
        "GATE4_DIGEST_MISMATCH": "Gate 4 — Digest mismatch",
        "PARSE_ERROR": "Parse error",
    }

    @classmethod
    def is_pass(cls, result: str) -> bool:
        """Return True if *result* is a passing gate result.

        Args:
            result: A gate result string (e.g. from VerifyResult.result).

        Returns:
            True if result == GateResult.PASS, False otherwise.

        Example:
            >>> GateResult.is_pass(GateResult.PASS)
            True
            >>> GateResult.is_pass(GateResult.GATE3)
            False
        """
        return result == cls.PASS

    @classmethod
    def label(cls, result: str) -> str:
        """Return a human-readable label for a gate result code.

        Args:
            result: A gate result string constant.

        Returns:
            A short English description of the result.

        Example:
            >>> GateResult.label(GateResult.GATE3)
            'Gate 3 — Replay detected'
        """
        return cls._LABELS.get(result, f"Unknown ({result})")

    @classmethod
    def gate_number(cls, result: str) -> int:
        """Return the gate number that failed (0 = pass, 1–4 = gate).

        Args:
            result: A gate result string constant.

        Returns:
            0 for PASS, 1–4 for the failed gate, -1 for PARSE_ERROR.

        Example:
            >>> GateResult.gate_number(GateResult.GATE4)
            4
            >>> GateResult.gate_number(GateResult.PASS)
            0
        """
        mapping = {
            cls.PASS: 0,
            cls.GATE1: 1,
            cls.GATE2: 2,
            cls.GATE3: 3,
            cls.GATE4: 4,
            cls.PARSE_ERROR: -1,
        }
        return mapping.get(result, -1)

    @classmethod
    def all_codes(cls) -> list[str]:
        """Return all defined gate result codes in order."""
        return [
            cls.PASS,
            cls.GATE1,
            cls.GATE2,
            cls.GATE3,
            cls.GATE4,
            cls.PARSE_ERROR,
        ]
