"""
INVARIANT Phase 1 Bittensor Integration
=======================================
Bittensor miner and validator implementations for INVARIANT subnet.

This module provides:
- Drop-in miner with receipt generation
- Three-tier validator with deterministic scoring
- Integration with Bittensor subnet protocol
"""

from .miner import InvariantMiner
from .validator import InvariantValidator

__all__ = [
    "InvariantMiner",
    "InvariantValidator",
]
