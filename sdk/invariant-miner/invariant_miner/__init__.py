"""
invariant-miner — INVARIANT Miner SDK
=====================================
Cryptographic execution receipt generation and verification
for Bittensor subnet miners.

by Orthonode Infrastructure Labs · orthonode.xyz

Quick start
-----------
    from invariant_miner import build_receipt, derive_agent_id, hash_model

    # Derive your agent identity once at startup
    agent_id = derive_agent_id(
        hotkey_ss58="5YourHotkeyHere...",
        model_identifier="my-model-v1",
        registration_block=12345,
    )

    # After executing a task, build a receipt
    receipt = build_receipt(
        agent_id=agent_id,
        model_identifier="my-model-v1",
        task_input="What is 2+2?",
        output="4",
        counter=1,          # strictly monotonic — increment each tempo
        tempo_id=100,
        timestamp=time.time(),
    )

    # receipt.to_dict() → send this to the validator alongside your output

Gate results
------------
    GateResult.PASS   — all four gates passed
    GateResult.GATE1  — agent not in registry
    GateResult.GATE2  — model not approved
    GateResult.GATE3  — replay / counter rollback detected
    GateResult.GATE4  — digest mismatch / tampered receipt

Backend
-------
    invariant_miner tries to import the compiled Rust extension
    (invariant_gates_rs) for production speed (~50–100× faster).
    Falls back to pure Python automatically — no code changes needed.

    Check which backend is active:
        from invariant_miner import using_rust
        print(using_rust())   # True = Rust, False = Python fallback
"""

from __future__ import annotations

__version__ = "1.0.0"
__author__ = "Orthonode Infrastructure Labs"
__email__ = "contact@orthonode.xyz"
__license__ = "MIT"
__all__ = [
    # Identity
    "derive_agent_id",
    "derive_agent_id_from_model_hash",
    "derive_hardware_agent_id",
    "hash_model",
    # Receipt
    "build_receipt",
    "build_receipt_from_model_hash",
    "Receipt",
    # Registry
    "Registry",
    # Verifier
    "Verifier",
    "VerifyResult",
    # Gate constants
    "GateResult",
    # Backend query
    "using_rust",
    # Exceptions
    "InvariantError",
    "CounterRollbackError",
    "ReceiptBuildError",
    "RegistryError",
    "VerifierError",
    "BackendError",
]

# ---------------------------------------------------------------------------
# Internal: load the backend (Rust or Python) once at import time
# ---------------------------------------------------------------------------
from invariant_miner._backend import (
    _build_receipt,
    _derive_hardware_agent_id,
    _derive_software_agent_id,
    _hash_model,
    _using_rust,
)
from invariant_miner.builder import build_receipt, build_receipt_from_model_hash
from invariant_miner.errors import (
    BackendError,
    CounterRollbackError,
    InvariantError,
    ReceiptBuildError,
    RegistryError,
    VerifierError,
)
from invariant_miner.gate import GateResult
from invariant_miner.identity import (
    derive_agent_id,
    derive_agent_id_from_model_hash,
    derive_hardware_agent_id,
    hash_model,
)
from invariant_miner.receipt import Receipt
from invariant_miner.registry import Registry
from invariant_miner.verifier import Verifier, VerifyResult


def using_rust() -> bool:
    """Return True if the compiled Rust extension is active.

    When True, gate operations run at ~50–100× Python speed.
    When False, the pure Python fallback is in use — functionally identical.
    """
    return _using_rust()
