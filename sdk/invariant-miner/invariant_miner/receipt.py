"""
invariant_miner/receipt.py
=========================
Receipt dataclass — the 136-byte execution proof produced by every
INVARIANT miner after task execution.

The receipt is submitted alongside the task output to the validator.
The validator runs all four gates against it before scoring output quality.

Wire format (136 bytes, big-endian):
    agent_id        [0:32]   SHA-256(hotkey || model_hash || reg_block)
    model_hash      [32:64]  SHA-256(model_identifier_string)
    execution_hash  [64:96]  SHA-256(task_input || output || tempo_id || timestamp)
    counter         [96:104] uint64, strictly monotonic
    digest          [104:136] SHA-256(agent_id || model_hash || exec_hash || counter)

The JSON form (for Axon/Dendrite transport) uses hex strings for byte fields.

Usage
-----
    from invariant_miner import build_receipt

    receipt = build_receipt(
        agent_id="<64-char hex>",
        model_identifier="my-model-v1",
        task_input="What is 2+2?",
        output="4",
        counter=1,
        tempo_id=100,
        timestamp=time.time(),
    )

    # Send over the wire
    json_str = receipt.to_json()

    # Reconstruct on the validator side
    receipt2 = Receipt.from_json(json_str)
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from typing import Any, Dict

_WIRE_SIZE = 136  # bytes


@dataclass(frozen=True)
class Receipt:
    """An INVARIANT execution receipt.

    All byte fields are stored as lowercase hex strings for easy
    JSON serialisation and human inspection.

    Attributes
    ----------
    agent_id : str
        64-char hex.  SHA-256(hotkey || model_hash || registration_block).
        Identifies the miner uniquely; hotkey-bound so it cannot be forged.
    model_hash : str
        64-char hex.  SHA-256(model_identifier_string).
        Must appear in the validator's approved model registry (Gate 2).
    execution_hash : str
        64-char hex.  SHA-256(task_input || output || tempo_id || timestamp).
        Cryptographically binds the specific input/output pair and tempo.
        Cannot be produced without having computed the output.
    counter : int
        Monotonic uint64.  Must be strictly greater than the last confirmed
        counter for this agent (Gate 3 — replay protection).
        Increment by at least 1 each tempo.
    digest : str
        64-char hex.  SHA-256(agent_id || model_hash || execution_hash || counter).
        Integrity seal over all four core fields (Gate 4).
    version : int
        Receipt format version.  Current: 1.
    timestamp : float
        Unix timestamp (seconds) at receipt creation.  Informational only —
        not included in the digest.
    tempo_id : int
        Bittensor tempo identifier.  Included in execution_hash so receipts
        cannot be reused across tempos (cross-tempo caching attack).
    """

    agent_id: str  # 64-char hex
    model_hash: str  # 64-char hex
    execution_hash: str  # 64-char hex
    counter: int  # uint64, monotonic
    digest: str  # 64-char hex
    version: int = 1
    timestamp: float = 0.0
    tempo_id: int = 0

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        for name in ("agent_id", "model_hash", "execution_hash", "digest"):
            val = getattr(self, name)
            if len(val) != 64:
                raise ValueError(
                    f"Receipt.{name} must be 64 hex characters (32 bytes), "
                    f"got {len(val)}"
                )
            try:
                bytes.fromhex(val)
            except ValueError as e:
                raise ValueError(f"Receipt.{name} is not valid hex: {e}") from e
        if self.counter < 0:
            raise ValueError(f"Receipt.counter must be >= 0, got {self.counter}")
        if self.tempo_id < 0:
            raise ValueError(f"Receipt.tempo_id must be >= 0, got {self.tempo_id}")

    # ------------------------------------------------------------------
    # Serialisation — JSON (transport format)
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return the receipt as a plain dict (JSON-serialisable).

        This is the form transmitted over Axon/Dendrite.

        Returns:
            Dict with string hex fields for all byte arrays and
            int/float for scalar fields.
        """
        return {
            "version": self.version,
            "agent_id": self.agent_id,
            "model_hash": self.model_hash,
            "execution_hash": self.execution_hash,
            "counter": self.counter,
            "digest": self.digest,
            "timestamp": self.timestamp,
            "tempo_id": self.tempo_id,
        }

    def to_json(self) -> str:
        """Serialise the receipt to a compact JSON string.

        Returns:
            Compact JSON string — safe to embed in a Bittensor synapse field.
        """
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Receipt":
        """Reconstruct a Receipt from a plain dict.

        Args:
            d: A dict previously produced by :meth:`to_dict` or decoded
               from the JSON transport form.

        Returns:
            A validated Receipt instance.

        Raises:
            KeyError:   If a required field is missing.
            ValueError: If any field fails validation.
        """
        return cls(
            agent_id=d["agent_id"],
            model_hash=d["model_hash"],
            execution_hash=d["execution_hash"],
            counter=int(d["counter"]),
            digest=d["digest"],
            version=int(d.get("version", 1)),
            timestamp=float(d.get("timestamp", 0.0)),
            tempo_id=int(d.get("tempo_id", 0)),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "Receipt":
        """Deserialise a Receipt from a JSON string.

        Args:
            json_str: A JSON string previously produced by :meth:`to_json`.

        Returns:
            A validated Receipt instance.

        Raises:
            json.JSONDecodeError: If the string is not valid JSON.
            KeyError:   If a required field is missing.
            ValueError: If any field fails validation.
        """
        return cls.from_dict(json.loads(json_str))

    # ------------------------------------------------------------------
    # Serialisation — binary wire format (136 bytes)
    # ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        """Serialise to the canonical 136-byte binary wire format.

        Layout (big-endian):
            [0:32]   agent_id
            [32:64]  model_hash
            [64:96]  execution_hash
            [96:104] counter (uint64 BE)
            [104:136] digest

        Returns:
            Exactly 136 bytes.
        """
        buf = bytearray(_WIRE_SIZE)
        buf[0:32] = bytes.fromhex(self.agent_id)
        buf[32:64] = bytes.fromhex(self.model_hash)
        buf[64:96] = bytes.fromhex(self.execution_hash)
        buf[96:104] = struct.pack(">Q", self.counter)
        buf[104:136] = bytes.fromhex(self.digest)
        return bytes(buf)

    @classmethod
    def from_bytes(cls, data: bytes | bytearray) -> "Receipt":
        """Deserialise from the canonical 136-byte binary wire format.

        Args:
            data: Exactly 136 bytes in the canonical layout.

        Returns:
            A validated Receipt instance (version=1, timestamp=0.0, tempo_id=0).

        Raises:
            ValueError: If data is not exactly 136 bytes.
        """
        if len(data) != _WIRE_SIZE:
            raise ValueError(f"Expected exactly {_WIRE_SIZE} bytes, got {len(data)}")
        return cls(
            agent_id=data[0:32].hex(),
            model_hash=data[32:64].hex(),
            execution_hash=data[64:96].hex(),
            counter=struct.unpack(">Q", data[96:104])[0],
            digest=data[104:136].hex(),
            version=1,
            timestamp=0.0,
            tempo_id=0,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def short_id(self) -> str:
        """Return the first 12 characters of agent_id for log messages."""
        return self.agent_id[:12]

    def short_digest(self) -> str:
        """Return the first 12 characters of digest for log messages."""
        return self.digest[:12]

    def __repr__(self) -> str:
        return (
            f"Receipt(agent={self.short_id()}…, "
            f"counter={self.counter}, "
            f"tempo={self.tempo_id}, "
            f"digest={self.short_digest()}…)"
        )
