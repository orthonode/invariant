"""
INVARIANT Protocol - Shared Synapse Definitions
==============================================
Shared synapse definitions used by both miners and validators.
All network communication uses these standardized message formats.

Usage:
    from invariant.protocol import InvariantTask, InvariantRegistration
"""

import bittensor as bt
from typing import Optional


class InvariantTask(bt.Synapse):
    """
    Task synapse sent from validator to miner.
    Contains the task input and metadata needed for receipt generation.
    """
    task_input: str = ""
    tempo_id: int = 0
    task_type: str = "hash"  # hash, math, logic, code
    
    # Miner fills these fields
    task_output: str = ""
    agent_id_hex: str = ""
    model_hash_hex: str = ""
    counter: int = 0
    digest: str = ""
    execution_time_ms: int = 0
    
    def deserialize_output(self) -> dict:
        """Parse miner's response into receipt format."""
        return {
            "task_input": self.task_input,
            "task_output": self.task_output,
            "tempo_id": self.tempo_id,
            "task_type": self.task_type,
            "agent_id_hex": self.agent_id_hex,
            "model_hash_hex": self.model_hash_hex,
            "counter": self.counter,
            "digest": self.digest,
            "execution_time_ms": self.execution_time_ms,
        }


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


class InvariantReceipt(bt.Synapse):
    """
    Direct receipt submission synapse.
    Alternative to embedding receipt in task response.
    """
    version: int = 1
    agent_id_hex: str = ""
    model_hash_hex: str = ""
    execution_hash: str = ""
    counter: int = 0
    digest: str = ""
    timestamp: float = 0.0
    tempo_id: int = 0
    
    # Validator response
    verified: bool = False
    gate_result: str = ""
    nts_score: float = 0.0
