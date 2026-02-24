"""
invariant/phase1_core/invariant_gates.py
=========================================
Pure Python four-gate engine.  This is the fallback used when the
Rust extension (invariant_gates_rs) has not yet been compiled.

DO NOT import this file directly in production code.
ALWAYS import through invariant_gates_bridge.py — it handles
the Rust/Python selection automatically.
"""

import hashlib
import json
import struct
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


RECEIPT_VERSION    = 1
RECEIPT_SIZE_BYTES = 136  # 32+32+32+8+32


class GateResult(Enum):
    PASS               = "PASS"
    AGENT_NOT_AUTH     = "GATE1_AGENT_NOT_AUTHORIZED"
    MODEL_NOT_APPROVED = "GATE2_MODEL_NOT_APPROVED"
    REPLAY_DETECTED    = "GATE3_REPLAY_DETECTED"
    DIGEST_MISMATCH    = "GATE4_DIGEST_MISMATCH"


# ── Identity ─────────────────────────────────────────────────────

def derive_software_agent_id(hotkey_ss58: str, model_hash: bytes, registration_block: int) -> bytes:
    h = hashlib.sha256()
    h.update(hotkey_ss58.encode("utf-8"))
    h.update(model_hash)
    h.update(struct.pack(">Q", registration_block))
    return h.digest()


def derive_hardware_agent_id(efuse_mac: bytes, chip_model_byte: bytes) -> bytes:
    try:
        import sha3
        k = sha3.keccak_256()
        k.update(efuse_mac)
        k.update(chip_model_byte)
        return k.digest()
    except ImportError:
        h = hashlib.sha256()
        h.update(efuse_mac)
        h.update(chip_model_byte)
        return h.digest()


def hash_model(identifier: str) -> bytes:
    return hashlib.sha256(identifier.encode("utf-8")).digest()


# ── Receipt ───────────────────────────────────────────────────────

@dataclass
class InvariantReceipt:
    agent_id:       bytes
    model_hash:     bytes
    execution_hash: bytes
    counter:        int
    digest:         bytes
    version:        int   = RECEIPT_VERSION
    timestamp:      float = 0.0
    tempo_id:       int   = 0

    def to_bytes(self) -> bytes:
        return (self.agent_id + self.model_hash + self.execution_hash
                + struct.pack(">Q", self.counter) + self.digest)

    def to_dict(self) -> dict:
        return {
            "version":        self.version,
            "agent_id":       self.agent_id.hex(),
            "model_hash":     self.model_hash.hex(),
            "execution_hash": self.execution_hash.hex(),
            "counter":        self.counter,
            "digest":         self.digest.hex(),
            "timestamp":      self.timestamp,
            "tempo_id":       self.tempo_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "InvariantReceipt":
        return cls(
            version        = d.get("version", RECEIPT_VERSION),
            agent_id       = bytes.fromhex(d["agent_id"]),
            model_hash     = bytes.fromhex(d["model_hash"]),
            execution_hash = bytes.fromhex(d["execution_hash"]),
            counter        = d["counter"],
            digest         = bytes.fromhex(d["digest"]),
            timestamp      = d.get("timestamp", 0.0),
            tempo_id       = d.get("tempo_id", 0),
        )


def compute_execution_hash(task_input: str, output: str, tempo_id: int, timestamp: float) -> bytes:
    h = hashlib.sha256()
    h.update(task_input.encode("utf-8"))
    h.update(output.encode("utf-8"))
    h.update(struct.pack(">Q", tempo_id))
    h.update(struct.pack(">d", timestamp))
    return h.digest()


def compute_receipt_digest(agent_id: bytes, model_hash: bytes,
                           execution_hash: bytes, counter: int) -> bytes:
    h = hashlib.sha256()
    h.update(agent_id)
    h.update(model_hash)
    h.update(execution_hash)
    h.update(struct.pack(">Q", counter))
    return h.digest()


def generate_receipt(agent_id: bytes, model_hash: bytes, task_input: str,
                     output: str, counter: int, tempo_id: int) -> InvariantReceipt:
    ts             = time.time()
    execution_hash = compute_execution_hash(task_input, output, tempo_id, ts)
    digest         = compute_receipt_digest(agent_id, model_hash, execution_hash, counter)
    return InvariantReceipt(
        agent_id=agent_id, model_hash=model_hash,
        execution_hash=execution_hash, counter=counter, digest=digest,
        timestamp=ts, tempo_id=tempo_id,
    )


# ── Registry ──────────────────────────────────────────────────────

class InvariantRegistry:
    def __init__(self, registry_path: str = "./invariant_registry.json"):
        self.registry_path = registry_path
        self._data = self._load()

    def _load(self) -> dict:
        try:
            with open(self.registry_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"agents": {}, "models": [], "version": 1}

    def _save(self):
        with open(self.registry_path, "w") as f:
            json.dump(self._data, f, indent=2)

    def is_authorized(self, agent_id: bytes) -> bool:
        return agent_id.hex() in self._data.get("agents", {})

    def is_approved_model(self, model_hash: bytes) -> bool:
        return model_hash.hex() in self._data.get("models", [])

    def register_agent(self, agent_id: bytes, hotkey: str, metadata: dict = None):
        self._data.setdefault("agents", {})[agent_id.hex()] = {
            "hotkey": hotkey, "registered": time.time(), "metadata": metadata or {}
        }
        self._save()

    def approve_model(self, model_hash: bytes):
        models = self._data.setdefault("models", [])
        if model_hash.hex() not in models:
            models.append(model_hash.hex())
            self._save()

    def get_agent(self, agent_id: bytes) -> Optional[dict]:
        return self._data.get("agents", {}).get(agent_id.hex())


# ── Verifier ──────────────────────────────────────────────────────

class InvariantVerifier:
    def __init__(self, registry: InvariantRegistry, state_path: str = "./invariant_state.json"):
        self.registry   = registry
        self.state_path = state_path
        self._counters  = self._load_counters()

    def _load_counters(self) -> dict:
        try:
            with open(self.state_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_counters(self):
        with open(self.state_path, "w") as f:
            json.dump(self._counters, f)

    def get_counter(self, agent_id_hex: str) -> int:
        return self._counters.get(agent_id_hex, 0)

    def advance_counter(self, agent_id_hex: str, new_counter: int):
        self._counters[agent_id_hex] = new_counter
        self._save_counters()

    def verify(self, receipt: InvariantReceipt) -> Tuple[GateResult, Optional[str]]:
        agent_hex = receipt.agent_id.hex()

        if not self.registry.is_authorized(receipt.agent_id):
            return GateResult.AGENT_NOT_AUTH, f"agent_id={agent_hex[:16]}... not in registry"

        if not self.registry.is_approved_model(receipt.model_hash):
            return GateResult.MODEL_NOT_APPROVED, f"model_hash={receipt.model_hash.hex()[:16]}... not approved"

        last = self.get_counter(agent_hex)
        if receipt.counter <= last:
            return GateResult.REPLAY_DETECTED, f"counter={receipt.counter} not > last={last}"

        expected = compute_receipt_digest(
            receipt.agent_id, receipt.model_hash, receipt.execution_hash, receipt.counter
        )
        if expected != receipt.digest:
            return GateResult.DIGEST_MISMATCH, f"digest mismatch"

        self.advance_counter(agent_hex, receipt.counter)
        return GateResult.PASS, None
