"""
invariant_miner/registry.py
==========================
Registry — manages the authorized agent list and approved model list.

The validator maintains the authoritative registry.  Miners use the
registry to pre-check that their agent_id and model_hash are registered
before submitting receipts — avoiding wasted tempo cycles from Gate 1/2
failures.

The registry is backed by a JSON file on disk.  The Rust extension
(invariant_gates_rs) provides a thread-safe RwLock<Inner> implementation.
The pure Python fallback is a dict-backed equivalent with threading.RLock.

Usage
-----
    from invariant_miner import Registry

    # Create / load a registry
    reg = Registry(path="./miner_data/registry.json")

    # Register your agent (done once after subnet registration)
    reg.register_agent(
        agent_id=my_agent_id,          # 64-char hex
        hotkey_ss58="5YourHotkey...",
    )

    # Register your model (must match what the validator approves)
    reg.approve_model(model_hash=my_model_hash)

    # Save to disk
    reg.save()

    # Pre-flight check before building a receipt
    if not reg.is_authorized(my_agent_id):
        raise RuntimeError("Agent not registered — run registration first")
    if not reg.is_approved(my_model_hash):
        raise RuntimeError("Model not approved — contact subnet validator")
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------


class _AgentMeta:
    """Metadata stored alongside each agent registration."""

    __slots__ = ("hotkey", "registered_at", "metadata")

    def __init__(
        self,
        hotkey: str,
        registered_at: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.hotkey = hotkey
        self.registered_at = registered_at
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hotkey": self.hotkey,
            "registered": self.registered_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "_AgentMeta":
        return cls(
            hotkey=d.get("hotkey", ""),
            registered_at=float(d.get("registered", 0.0)),
            metadata=d.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class Registry:
    """Thread-safe registry of authorized agents and approved models.

    The registry is the source of truth for Gate 1 (agent authorization)
    and Gate 2 (model approval).  Validators maintain the authoritative
    copy; miners use a local copy to pre-check before building receipts.

    The JSON schema on disk:
    ::

        {
            "version": 1,
            "agents": {
                "<agent_id_hex>": {
                    "hotkey": "<ss58>",
                    "registered": <unix_timestamp>,
                    "metadata": {}
                }
            },
            "models": ["<model_hash_hex>", ...]
        }

    Attributes
    ----------
    path : str | None
        Path to the backing JSON file, or None for an in-memory-only registry.

    Thread safety
    -------------
    All read and write operations are protected by a ``threading.RLock``.
    Multiple threads (e.g. async Axon handlers) can safely call
    :meth:`is_authorized` and :meth:`is_approved` concurrently.
    """

    def __init__(self, path: Optional[str] = None) -> None:
        """Create or load a Registry.

        If *path* points to an existing JSON file, its contents are loaded
        immediately.  If the file does not exist yet, an empty registry is
        created and will be written when :meth:`save` is called.

        Args:
            path: Optional path to the backing JSON file.
                  If None, the registry is in-memory only (not persisted).

        Example:
            >>> reg = Registry(path="./miner_data/registry.json")
        """
        self._path: Optional[str] = str(path) if path is not None else None
        self._lock = threading.RLock()
        self._agents: Dict[str, _AgentMeta] = {}  # agent_id_hex → meta
        self._models: set[str] = set()  # model_hash_hex

        if self._path and os.path.isfile(self._path):
            self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load registry state from the backing JSON file (internal)."""
        if not self._path:
            return
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return  # file absent or corrupt — start empty

        with self._lock:
            agents_raw: Dict[str, Any] = data.get("agents", {})
            for agent_id_hex, meta_raw in agents_raw.items():
                self._agents[agent_id_hex.lower()] = _AgentMeta.from_dict(meta_raw)

            models_raw: List[str] = data.get("models", [])
            for mh in models_raw:
                self._models.add(mh.lower())

    def save(self) -> None:
        """Persist the current registry state to disk.

        Does nothing if no path was provided at construction time.

        Raises:
            OSError: If the file cannot be written.

        Example:
            >>> reg.register_agent("aabbcc...", "5Hotkey...")
            >>> reg.save()   # write to disk
        """
        if not self._path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self._path)), exist_ok=True)
        with self._lock:
            data = {
                "version": 1,
                "agents": {aid: meta.to_dict() for aid, meta in self._agents.items()},
                "models": sorted(self._models),
            }
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, self._path)  # atomic on POSIX

    @classmethod
    def load(cls, path: str) -> "Registry":
        """Load a Registry from a JSON file.

        Convenience constructor equivalent to ``Registry(path=path)``.

        Args:
            path: Path to the registry JSON file.

        Returns:
            A Registry instance populated from the file.

        Example:
            >>> reg = Registry.load("./validator_data/registry.json")
        """
        return cls(path=path)

    # ------------------------------------------------------------------
    # Write operations (registration path)
    # ------------------------------------------------------------------

    def register_agent(
        self,
        agent_id: str,
        hotkey_ss58: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register an agent in the authorized list.

        Idempotent — registering the same agent_id again updates the
        metadata and hotkey but does not change the registered timestamp.

        Args:
            agent_id:    64-char hex agent_id (from :func:`~invariant_miner.derive_agent_id`).
            hotkey_ss58: The Bittensor hotkey SS58 address for this agent.
            metadata:    Optional dict of additional metadata (stored as-is).

        Raises:
            ValueError: If agent_id is not a valid 64-char hex string.

        Example:
            >>> reg.register_agent(
            ...     agent_id   = derive_agent_id(hotkey, "model-v1", 12345),
            ...     hotkey_ss58 = wallet.hotkey.ss58_address,
            ... )
        """
        agent_id = self._validate_hex32(agent_id, "agent_id")
        with self._lock:
            existing = self._agents.get(agent_id)
            reg_time = existing.registered_at if existing else time.time()
            self._agents[agent_id] = _AgentMeta(
                hotkey=hotkey_ss58,
                registered_at=reg_time,
                metadata=metadata or {},
            )

    def approve_model(self, model_hash: str) -> None:
        """Add a model hash to the approved model list.

        Idempotent — approving the same model_hash twice is a no-op.

        Args:
            model_hash: 64-char hex model_hash (from :func:`~invariant_miner.hash_model`).

        Raises:
            ValueError: If model_hash is not a valid 64-char hex string.

        Example:
            >>> reg.approve_model(hash_model("llama-3.2-1b-instruct-v1"))
        """
        model_hash = self._validate_hex32(model_hash, "model_hash")
        with self._lock:
            self._models.add(model_hash)

    def revoke_agent(self, agent_id: str) -> bool:
        """Remove an agent from the authorized list.

        Args:
            agent_id: 64-char hex agent_id to revoke.

        Returns:
            True if the agent was present and removed, False if not found.
        """
        agent_id = self._validate_hex32(agent_id, "agent_id")
        with self._lock:
            return self._agents.pop(agent_id, None) is not None

    def revoke_model(self, model_hash: str) -> bool:
        """Remove a model hash from the approved list.

        Args:
            model_hash: 64-char hex model_hash to revoke.

        Returns:
            True if the model was present and removed, False if not found.
        """
        model_hash = self._validate_hex32(model_hash, "model_hash")
        with self._lock:
            if model_hash in self._models:
                self._models.discard(model_hash)
                return True
            return False

    # ------------------------------------------------------------------
    # Read operations (Gate 1 / Gate 2 hot path)
    # ------------------------------------------------------------------

    def is_authorized(self, agent_id: str) -> bool:
        """Return True if *agent_id* is in the authorized registry (Gate 1).

        This is called on the hot path — must be O(1).

        Args:
            agent_id: 64-char hex agent_id to check.

        Returns:
            True if authorized, False otherwise.

        Example:
            >>> if not reg.is_authorized(my_agent_id):
            ...     raise RuntimeError("Not registered — re-run registration")
        """
        with self._lock:
            return agent_id.lower() in self._agents

    def is_approved(self, model_hash: str) -> bool:
        """Return True if *model_hash* is in the approved model list (Gate 2).

        This is called on the hot path — must be O(1).

        Args:
            model_hash: 64-char hex model_hash to check.

        Returns:
            True if approved, False otherwise.

        Example:
            >>> if not reg.is_approved(my_model_hash):
            ...     raise RuntimeError("Model not approved by validator")
        """
        with self._lock:
            return model_hash.lower() in self._models

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Return agent metadata for *agent_id*, or None if not found.

        Args:
            agent_id: 64-char hex agent_id.

        Returns:
            Dict with ``hotkey``, ``registered``, and ``metadata`` keys,
            or None if the agent is not registered.
        """
        with self._lock:
            meta = self._agents.get(agent_id.lower())
            return meta.to_dict() if meta is not None else None

    def list_agents(self) -> List[str]:
        """Return a sorted list of all registered agent_id hex strings.

        Returns:
            List of 64-char hex strings, sorted alphabetically.
        """
        with self._lock:
            return sorted(self._agents.keys())

    def list_models(self) -> List[str]:
        """Return a sorted list of all approved model_hash hex strings.

        Returns:
            List of 64-char hex strings, sorted alphabetically.
        """
        with self._lock:
            return sorted(self._models)

    def agent_count(self) -> int:
        """Return the number of registered agents."""
        with self._lock:
            return len(self._agents)

    def model_count(self) -> int:
        """Return the number of approved models."""
        with self._lock:
            return len(self._models)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_hex32(value: str, name: str) -> str:
        """Validate that *value* is a 64-character hex string and return lowercase."""
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string, got {type(value).__name__}")
        value = value.lower().strip()
        if len(value) != 64:
            raise ValueError(
                f"{name} must be exactly 64 hex characters (32 bytes), "
                f"got {len(value)} characters"
            )
        try:
            bytes.fromhex(value)
        except ValueError as e:
            raise ValueError(f"{name} is not valid hex: {e}") from e
        return value

    def __repr__(self) -> str:
        return (
            f"Registry(agents={self.agent_count()}, "
            f"models={self.model_count()}, "
            f"path={self._path!r})"
        )
