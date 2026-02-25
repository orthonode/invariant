"""
INVARIANT Protocol - Shared Synapse Definitions
==============================================
Shared synapse definitions used by both miners and validators.
All network communication uses these standardized message formats.

Usage:
    from invariant.protocol import InvariantTask
"""

import bittensor as bt
from typing import Optional


class InvariantTask(bt.Synapse):
    """
    Task synapse sent from validator to miner and returned with results.

    Validator sets task_input, tempo_id, task_type before sending.
    Miner fills output, receipt_json, checkpoint_json in the response.
    """

    # Validator → Miner
    task_input: str = ""
    tempo_id: int = 0
    task_type: str = "hash"  # hash, math, logic, code

    # Miner → Validator (filled in handle_task)
    output: str = ""
    receipt_json: str = ""       # JSON-serialised receipt dict from build_receipt()
    checkpoint_json: str = ""    # JSON-serialised OAP checkpoint dict (may be empty)

    def deserialize(self) -> "InvariantTask":
        """Return self so bittensor passes the full synapse to the caller."""
        return self


class InvariantRegistration(bt.Synapse):
    """
    Registration synapse for miner to register agent_id with validator.
    Validator verifies the agent_id derivation before adding to registry.
    """
    agent_id_hex: str = ""   # 64-char hex
    model_hash_hex: str = "" # 64-char hex
    hotkey: str = ""
    reg_block: int = 0

    # Validator response
    registered: bool = False
    reason: str = ""


class InvariantHeartbeat(bt.Synapse):
    """
    Heartbeat synapse for miner to report status.
    Used for health monitoring and tempo synchronization.
    """
    agent_id_hex: str = ""
    current_counter: int = 0
    last_tempo: int = 0
    tasks_completed: int = 0

    # Validator response
    tempo_id: int = 0
    network_time: int = 0
