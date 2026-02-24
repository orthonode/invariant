"""
INVARIANT - Deterministic Trust Infrastructure for Bittensor
===========================================================
Core package providing cryptographic verification and trust scoring.

This package contains:
- Four-gate cryptographic receipt verification (Rust/Python bridge)
- OAP (On-chain Agent Performance) trust engine
- Bittensor miner and validator implementations
- Protocol synapse definitions

Import examples:
    from invariant import Verifier, Registry, GateResult
    from invariant import OAPEngine, ViolationType
    from invariant import InvariantTask, InvariantRegistration
"""

__version__ = "1.0.0"
__author__ = "INVARIANT Team"

from .phase1_core.invariant_gates_bridge import (
    GateResult,
    Registry,
    Verifier,
    build_receipt,
    derive_hardware_agent_id,
    derive_software_agent_id,
    hash_model,
    using_rust,
)
from .phase1_core.invariant_oap import (
    OAPEngine,
    ViolationType,
)
from .protocol import (
    InvariantHeartbeat,
    InvariantRegistration,
    InvariantTask,
    # InvariantReceipt is a bt.Synapse in protocol.py (for Axon transport).
    # The cryptographic receipt dataclass lives in invariant_gates.py.
    # Import it by its full path if needed:
    #   from invariant.phase1_core.invariant_gates import InvariantReceipt
)

__all__ = [
    # Core verification (bridge — Rust when compiled, Python fallback)
    "Verifier",
    "Registry",
    "GateResult",
    "derive_software_agent_id",
    "derive_hardware_agent_id",
    "hash_model",
    "build_receipt",
    "using_rust",
    # Trust engine
    "OAPEngine",
    "ViolationType",
    # Protocol synapses
    "InvariantTask",
    "InvariantRegistration",
    "InvariantHeartbeat",
]
