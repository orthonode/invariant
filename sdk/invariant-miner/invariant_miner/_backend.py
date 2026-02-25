"""
invariant_miner/_backend.py
==========================
Internal module — do NOT import this directly.
Use the public API from invariant_miner.__init__ instead.

Loads the Rust extension (invariant_gates_rs) when available.
Falls back to the pure Python implementation silently.
All public SDK modules import from here so the backend choice
is made exactly once at process startup.
"""

from __future__ import annotations

import hashlib
import json
import logging
import struct
import time
from typing import Any, Dict, Optional

log = logging.getLogger("invariant_miner")

# ---------------------------------------------------------------------------
# Attempt to load the compiled Rust extension
# ---------------------------------------------------------------------------

_USING_RUST = False
_rs: Any = None

try:
    import invariant_gates_rs as _rs  # type: ignore[import]

    _USING_RUST = True
    log.debug(
        "[invariant-miner] Rust gate engine loaded (v%s) — production speed",
        getattr(_rs, "__version__", "?"),
    )
except ImportError:
    log.debug(
        "[invariant-miner] Rust extension (invariant_gates_rs) not found. "
        "Using pure Python fallback — functionally identical, ~50-100x slower. "
        "Build with: cd invariant/invariant-gates && maturin develop --features python-ext --release"
    )


def _using_rust() -> bool:
    """True if the Rust extension is loaded and active."""
    return _USING_RUST


# ---------------------------------------------------------------------------
# Pure Python implementations (used when Rust is not available)
# ---------------------------------------------------------------------------


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _sha256_2(a: bytes, b: bytes) -> bytes:
    h = hashlib.sha256()
    h.update(a)
    h.update(b)
    return h.digest()


def _py_derive_software_agent_id(
    hotkey_ss58: str,
    model_hash_hex: str,
    registration_block: int,
) -> str:
    """
    agent_id = SHA-256(hotkey_utf8 || model_hash_bytes || reg_block_be_u64)
    Returns 64-char lowercase hex string.
    """
    try:
        model_hash_bytes = bytes.fromhex(model_hash_hex)
    except ValueError as e:
        raise ValueError(f"model_hash_hex is not valid hex: {e}") from e
    if len(model_hash_bytes) != 32:
        raise ValueError(f"model_hash must be 32 bytes, got {len(model_hash_bytes)}")

    h = hashlib.sha256()
    h.update(hotkey_ss58.encode("utf-8"))
    h.update(model_hash_bytes)
    h.update(struct.pack(">Q", registration_block))
    return h.hexdigest()


def _py_derive_hardware_agent_id(
    efuse_mac_hex: str,
    chip_model_hex: str,
) -> str:
    """
    agent_id = Keccak-256(efuse_mac || chip_model)
    Ethereum-compatible. Returns 64-char hex string.
    Falls back to SHA-256 if pysha3 / pycryptodome is unavailable.
    """
    try:
        efuse_bytes = bytes.fromhex(efuse_mac_hex)
        chip_bytes = bytes.fromhex(chip_model_hex)
    except ValueError as e:
        raise ValueError(f"Invalid hex input: {e}") from e

    # Try Keccak-256 via pysha3
    try:
        import sha3  # type: ignore[import]  # pysha3

        k = hashlib.new("keccak_256")  # noqa: S324
        k.update(efuse_bytes)
        k.update(chip_bytes)
        return k.hexdigest()
    except (ImportError, ValueError):
        pass

    # Try Keccak-256 via pycryptodome
    try:
        from Crypto.Hash import keccak  # type: ignore[import]

        k = keccak.new(digest_bits=256)
        k.update(efuse_bytes)
        k.update(chip_bytes)
        return k.hexdigest()
    except ImportError:
        pass

    # Last resort: SHA-256 (not Keccak — log a warning)
    log.warning(
        "[invariant-miner] pysha3 and pycryptodome both unavailable. "
        "Hardware agent_id falling back to SHA-256 (not Keccak-256). "
        "Install pysha3 for correct DePIN hardware identity."
    )
    h = hashlib.sha256()
    h.update(efuse_bytes)
    h.update(chip_bytes)
    return h.hexdigest()


def _py_hash_model(identifier: str) -> str:
    """SHA-256(identifier_utf8) → 64-char hex string."""
    return hashlib.sha256(identifier.encode("utf-8")).hexdigest()


def _py_compute_execution_hash(
    task_input: str,
    output: str,
    tempo_id: int,
    timestamp: float,
) -> bytes:
    """
    execution_hash = SHA-256(task_input || output || tempo_id_be_u64 || ts_be_f64)
    """
    h = hashlib.sha256()
    h.update(task_input.encode("utf-8"))
    h.update(output.encode("utf-8"))
    h.update(struct.pack(">Q", tempo_id))
    h.update(struct.pack(">d", timestamp))
    return h.digest()


def _py_compute_receipt_digest(
    agent_id_hex: str,
    model_hash_hex: str,
    execution_hash_bytes: bytes,
    counter: int,
) -> bytes:
    """
    digest = SHA-256(agent_id || model_hash || execution_hash || counter_be_u64)
    """
    h = hashlib.sha256()
    h.update(bytes.fromhex(agent_id_hex))
    h.update(bytes.fromhex(model_hash_hex))
    h.update(execution_hash_bytes)
    h.update(struct.pack(">Q", counter))
    return h.digest()


def _py_build_receipt(
    agent_id_hex: str,
    model_hash_hex: str,
    task_input: str,
    output: str,
    counter: int,
    tempo_id: int,
    timestamp: float,
) -> str:
    """Build a complete receipt and return it as a JSON string."""
    execution_hash = _py_compute_execution_hash(task_input, output, tempo_id, timestamp)
    digest = _py_compute_receipt_digest(
        agent_id_hex, model_hash_hex, execution_hash, counter
    )
    receipt = {
        "version": 1,
        "agent_id": agent_id_hex,
        "model_hash": model_hash_hex,
        "execution_hash": execution_hash.hex(),
        "counter": counter,
        "digest": digest.hex(),
        "timestamp": timestamp,
        "tempo_id": tempo_id,
    }
    return json.dumps(receipt)


# ---------------------------------------------------------------------------
# Unified public backend functions
# (called by the SDK modules — always use these, never call _py_* directly)
# ---------------------------------------------------------------------------


def _derive_software_agent_id(
    hotkey_ss58: str,
    model_hash_hex: str,
    registration_block: int,
) -> str:
    """Derive software miner agent_id. Returns 64-char hex string."""
    if _USING_RUST:
        return _rs.py_derive_software_agent_id(
            hotkey_ss58, model_hash_hex, registration_block
        )
    return _py_derive_software_agent_id(hotkey_ss58, model_hash_hex, registration_block)


def _derive_hardware_agent_id(efuse_mac_hex: str, chip_model_hex: str) -> str:
    """Derive DePIN hardware miner agent_id (Keccak-256). Returns 64-char hex."""
    if _USING_RUST:
        return _rs.py_derive_hardware_agent_id(efuse_mac_hex, chip_model_hex)
    return _py_derive_hardware_agent_id(efuse_mac_hex, chip_model_hex)


def _hash_model(identifier: str) -> str:
    """SHA-256(model_identifier_utf8) → 64-char hex model_hash."""
    if _USING_RUST:
        return _rs.py_hash_model(identifier)
    return _py_hash_model(identifier)


def _build_receipt(
    agent_id_hex: str,
    model_hash_hex: str,
    task_input: str,
    output: str,
    counter: int,
    tempo_id: int,
    timestamp: float,
) -> str:
    """Build a complete, correctly-signed receipt. Returns JSON string."""
    if _USING_RUST:
        return _rs.py_build_receipt(
            agent_id_hex,
            model_hash_hex,
            task_input,
            output,
            counter,
            tempo_id,
            timestamp,
        )
    return _py_build_receipt(
        agent_id_hex, model_hash_hex, task_input, output, counter, tempo_id, timestamp
    )
