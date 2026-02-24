"""
INVARIANT Phase 1 Core
======================
Core cryptographic verification and trust scoring components.

This module provides:
- Four-gate receipt verification (Rust/Python bridge)
- OAP trust engine for lifecycle scoring
- Cryptographic primitives for identity and receipts
"""

from .invariant_gates_bridge import (
    Verifier,
    Registry,
    GateResult,
    derive_software_agent_id,
    derive_hardware_agent_id,
    hash_model,
    build_receipt,
    using_rust,
)

from .invariant_oap import (
    OAPEngine,
    ViolationType,
)

__all__ = [
    "Verifier",
    "Registry",
    "GateResult", 
    "derive_software_agent_id",
    "derive_hardware_agent_id",
    "hash_model",
    "build_receipt",
    "using_rust",
    "OAPEngine",
    "ViolationType",
]
