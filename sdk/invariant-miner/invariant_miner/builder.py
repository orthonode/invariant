"""
invariant_miner/builder.py
=========================
build_receipt() — the main entry point for miners.

This is the function you call after executing a task.
It computes the execution_hash and digest, assembles the receipt,
and returns a Receipt instance ready to send to the validator.

Usage
-----
    import time
    from invariant_miner import build_receipt, derive_agent_id, hash_model

    # ── At miner startup (once) ──────────────────────────────────────
    model_identifier = "llama-3.2-1b-instruct-v1"
    model_hash       = hash_model(model_identifier)

    agent_id = derive_agent_id(
        hotkey_ss58        = wallet.hotkey.ss58_address,
        model_identifier   = model_identifier,
        registration_block = reg_block,
    )

    counter = load_counter_from_disk()   # monotonically increasing int

    # ── After executing each task (every tempo) ──────────────────────
    output  = run_my_model(task_input)
    counter += 1

    receipt = build_receipt(
        agent_id         = agent_id,
        model_identifier = model_identifier,
        task_input       = task_input,
        output           = output,
        counter          = counter,
        tempo_id         = current_tempo,
        timestamp        = time.time(),
    )

    save_counter_to_disk(counter)

    # Send to validator alongside the output
    synapse.receipt_json = receipt.to_json()
"""

from __future__ import annotations

import json
import time as _time
from typing import Optional

from invariant_miner._backend import _build_receipt, _hash_model
from invariant_miner.errors import ReceiptBuildError
from invariant_miner.receipt import Receipt


def build_receipt(
    agent_id: str,
    model_identifier: str,
    task_input: str,
    output: str,
    counter: int,
    tempo_id: int,
    timestamp: Optional[float] = None,
    *,
    model_hash: Optional[str] = None,
) -> Receipt:
    """Build a complete, cryptographically valid INVARIANT execution receipt.

    This is the primary miner-side API call.  After executing a task,
    call this function with the input, output, and current counter to
    produce a receipt that the validator can verify against all four gates.

    The receipt binds:
    - **WHO** ran the task (``agent_id`` — hotkey-bound, unforgeable)
    - **WHAT** they ran (``model_hash`` — must be in approved registry)
    - **WHAT THEY PRODUCED** (``execution_hash`` — includes task_input + output)
    - **THAT IT IS FRESH** (``counter`` — strictly monotonic, blocks replay)
    - **THAT NOTHING WAS TAMPERED** (``digest`` — SHA-256 of all four fields)

    Args:
        agent_id:         64-char hex agent_id from :func:`~invariant_miner.derive_agent_id`.
                          Derive once at startup and reuse every tempo.
        model_identifier: Human-readable model identifier string — e.g.
                          ``"llama-3.2-1b-instruct-v1"``.  Must match
                          the identifier registered with the validator.
                          Used to compute ``model_hash`` if not supplied.
        task_input:       The exact task input string sent by the validator.
                          Must match verbatim — any difference changes
                          execution_hash and Gate 4 will fail.
        output:           The model's output string for this task.
                          Must match verbatim — any difference changes
                          execution_hash and Gate 4 will fail.
        counter:          Monotonic uint64.  Must be strictly greater than
                          the last counter the validator confirmed for this
                          agent.  Increment by at least 1 per tempo.
                          Persist across restarts — counter regression
                          triggers Gate 3.
        tempo_id:         The Bittensor tempo identifier for this task.
                          Included in execution_hash so a receipt from
                          tempo N cannot be replayed at tempo N+1.
        timestamp:        Unix timestamp (float seconds).  Defaults to
                          ``time.time()`` if not provided.  Informational
                          only — not included in the digest.
        model_hash:       Optional pre-computed 64-char hex model_hash.
                          If supplied, ``model_identifier`` is ignored for
                          hash computation (but still stored for reference).
                          Use this when you cache the model_hash at startup.

    Returns:
        A fully constructed and signed :class:`~invariant_miner.receipt.Receipt`.

    Raises:
        ReceiptBuildError: If any input is invalid or receipt construction fails.
        ValueError:       If ``agent_id`` is not a valid 64-char hex string,
                          ``counter`` is negative, or ``tempo_id`` is negative.

    Example:
        >>> receipt = build_receipt(
        ...     agent_id         = "b7c4e9" + "0" * 58,    # your real agent_id
        ...     model_identifier = "llama-3.2-1b-instruct-v1",
        ...     task_input       = "What is 2+2?",
        ...     output           = "4",
        ...     counter          = 42,
        ...     tempo_id         = 100,
        ... )
        >>> print(receipt.to_json())
        {"version":1,"agent_id":"b7c4e9...","counter":42,...}
    """
    # ── Input validation ─────────────────────────────────────────────────────
    if not agent_id or len(agent_id) != 64:
        raise ValueError(
            f"agent_id must be a 64-character hex string, got length {len(agent_id) if agent_id else 0}"
        )
    try:
        bytes.fromhex(agent_id)
    except ValueError as e:
        raise ValueError(f"agent_id is not valid hex: {e}") from e

    if counter < 0:
        raise ValueError(f"counter must be >= 0, got {counter}")
    if counter > 0xFFFF_FFFF_FFFF_FFFF:
        raise ValueError(f"counter exceeds uint64 max ({counter})")
    if tempo_id < 0:
        raise ValueError(f"tempo_id must be >= 0, got {tempo_id}")
    if not task_input and task_input != "":
        raise ValueError("task_input must be a string (may be empty)")
    if not output and output != "":
        raise ValueError("output must be a string (may be empty)")

    if timestamp is None:
        timestamp = _time.time()

    # ── Resolve model_hash ───────────────────────────────────────────────────
    if model_hash is not None:
        if len(model_hash) != 64:
            raise ValueError(
                f"model_hash must be a 64-character hex string, got length {len(model_hash)}"
            )
        try:
            bytes.fromhex(model_hash)
        except ValueError as e:
            raise ValueError(f"model_hash is not valid hex: {e}") from e
        resolved_model_hash = model_hash
    else:
        if not model_identifier or not model_identifier.strip():
            raise ValueError(
                "model_identifier must be a non-empty string "
                "(or supply model_hash= directly)"
            )
        resolved_model_hash = _hash_model(model_identifier)

    # ── Build the receipt via backend (Rust or Python) ───────────────────────
    try:
        receipt_json_str = _build_receipt(
            agent_id_hex=agent_id,
            model_hash_hex=resolved_model_hash,
            task_input=task_input,
            output=output,
            counter=counter,
            tempo_id=tempo_id,
            timestamp=timestamp,
        )
    except Exception as exc:
        raise ReceiptBuildError(
            f"Receipt construction failed: {exc}\n"
            f"  agent_id={agent_id[:12]}…  counter={counter}  tempo_id={tempo_id}"
        ) from exc

    # ── Parse back into a Receipt dataclass ──────────────────────────────────
    try:
        raw = json.loads(receipt_json_str)
        receipt = Receipt(
            agent_id=raw["agent_id"],
            model_hash=raw["model_hash"],
            execution_hash=raw["execution_hash"],
            counter=int(raw["counter"]),
            digest=raw["digest"],
            version=int(raw.get("version", 1)),
            timestamp=float(raw.get("timestamp", timestamp)),
            tempo_id=int(raw.get("tempo_id", tempo_id)),
        )
    except Exception as exc:
        raise ReceiptBuildError(
            f"Failed to parse receipt returned by backend: {exc}"
        ) from exc

    return receipt


def build_receipt_from_model_hash(
    agent_id: str,
    model_hash: str,
    task_input: str,
    output: str,
    counter: int,
    tempo_id: int,
    timestamp: Optional[float] = None,
) -> Receipt:
    """Build a receipt when you have the model_hash directly (not the identifier).

    Convenience wrapper around :func:`build_receipt` for the common case
    where you pre-compute and cache the model_hash at miner startup.

    Args:
        agent_id:    64-char hex agent_id.
        model_hash:  64-char hex model_hash from :func:`~invariant_miner.hash_model`.
        task_input:  The task input string.
        output:      The model output string.
        counter:     Monotonic uint64 counter.
        tempo_id:    Bittensor tempo identifier.
        timestamp:   Unix timestamp. Defaults to ``time.time()``.

    Returns:
        A fully constructed and signed :class:`~invariant_miner.receipt.Receipt`.

    Raises:
        ReceiptBuildError: If construction fails.
        ValueError:        If inputs are invalid.

    Example:
        >>> # At startup — compute once
        >>> mh = hash_model("llama-3.2-1b-instruct-v1")
        >>>
        >>> # Each tempo — fast, no re-hashing of model identifier
        >>> receipt = build_receipt_from_model_hash(
        ...     agent_id   = my_agent_id,
        ...     model_hash = mh,
        ...     task_input = "What is 2+2?",
        ...     output     = "4",
        ...     counter    = 42,
        ...     tempo_id   = 100,
        ... )
    """
    return build_receipt(
        agent_id=agent_id,
        model_identifier="",  # ignored when model_hash is supplied
        task_input=task_input,
        output=output,
        counter=counter,
        tempo_id=tempo_id,
        timestamp=timestamp,
        model_hash=model_hash,
    )
