"""
invariant/phase1_core/invariant_gates_bridge.py
================================================
THE BRIDGE — this is the file all other Python code imports.

It attempts to load the compiled Rust extension (invariant_gates_rs)
built by `maturin develop --features python-ext`.

If the Rust extension is not available (not yet compiled, CI environment,
fresh clone before first build), it falls back transparently to the pure
Python implementation with zero API changes.

CALLERS:
    from invariant_gates_bridge import (
        derive_software_agent_id,
        derive_hardware_agent_id,
        hash_model,
        build_receipt,
        Verifier,
        Registry,
        GateResult,
    )

That's it.  The caller never needs to know whether Rust or Python is running.
In production after `maturin develop`, Rust is ~50-100x faster.
On a fresh clone before building, Python keeps everything working.
"""

import importlib
import json
import logging
import os
import sys
import time

log = logging.getLogger("invariant.bridge")

# ─────────────────────────────────────────────────────────────────
# Attempt Rust import
# ─────────────────────────────────────────────────────────────────

_USING_RUST = False
_rs = None

try:
    import invariant_gates_rs as _rs

    _USING_RUST = True
    log.info(f"[INVARIANT] Rust gate engine loaded (v{_rs.__version__}) — full speed")
except ImportError:
    log.warning(
        "[INVARIANT] Rust extension not found. "
        "Run `maturin develop --features python-ext` in invariant-gates/ "
        "for ~50-100x faster gate verification. "
        "Using pure Python fallback — functionally identical."
    )

# ─────────────────────────────────────────────────────────────────
# Pure Python fallback (imported only if Rust not available)
# ─────────────────────────────────────────────────────────────────

if not _USING_RUST:
    # Import pure Python implementations from invariant_gates.py
    # (same directory)
    _here = os.path.dirname(os.path.abspath(__file__))
    if _here not in sys.path:
        sys.path.insert(0, _here)

    from invariant_gates import (
        GateResult as _PyGateResult,
    )
    from invariant_gates import (
        InvariantReceipt as _PyReceipt,
    )
    from invariant_gates import (
        InvariantRegistry as _PyRegistry,
    )
    from invariant_gates import (
        InvariantVerifier as _PyVerifier,
    )
    from invariant_gates import (
        derive_hardware_agent_id as _py_derive_hardware,
    )
    from invariant_gates import (
        derive_software_agent_id as _py_derive_software,
    )
    from invariant_gates import (
        generate_receipt as _py_generate_receipt,
    )
    from invariant_gates import (
        hash_model as _py_hash_model,
    )


# ─────────────────────────────────────────────────────────────────
# Unified public API
# All code imports from HERE — not from invariant_gates.py directly
# ─────────────────────────────────────────────────────────────────


class GateResult:
    """Mirrors the Rust GateResult enum codes."""

    PASS = "PASS"
    GATE1 = "GATE1_AGENT_NOT_AUTHORIZED"
    GATE2 = "GATE2_MODEL_NOT_APPROVED"
    GATE3 = "GATE3_REPLAY_DETECTED"
    GATE4 = "GATE4_DIGEST_MISMATCH"
    PARSE_ERROR = "PARSE_ERROR"

    @staticmethod
    def is_pass(code: str) -> bool:
        return code == GateResult.PASS


def using_rust() -> bool:
    """Returns True if the Rust extension is loaded."""
    return _USING_RUST


# ── Identity derivation ───────────────────────────────────────────


def derive_software_agent_id(
    hotkey_ss58: str,
    model_hash_hex: str,
    registration_block: int,
) -> str:
    """
    Returns 64-char hex agent_id.

    Rust path:   calls py_derive_software_agent_id in the .so
    Python path: calls invariant_gates.derive_software_agent_id
    """
    if _USING_RUST:
        return _rs.py_derive_software_agent_id(
            hotkey_ss58, model_hash_hex, registration_block
        )
    else:
        model_hash_bytes = bytes.fromhex(model_hash_hex)
        result = _py_derive_software(hotkey_ss58, model_hash_bytes, registration_block)
        return result.hex()


def derive_hardware_agent_id(efuse_mac_hex: str, chip_model_hex: str) -> str:
    """Returns 64-char hex agent_id (Keccak-256 for DePIN hardware)."""
    if _USING_RUST:
        return _rs.py_derive_hardware_agent_id(efuse_mac_hex, chip_model_hex)
    else:
        mac = bytes.fromhex(efuse_mac_hex)
        chip = bytes.fromhex(chip_model_hex)
        return _py_derive_hardware(mac, chip).hex()


def hash_model(identifier: str) -> str:
    """SHA-256 of model identifier string. Returns 64-char hex."""
    if _USING_RUST:
        return _rs.py_hash_model(identifier)
    else:
        return _py_hash_model(identifier).hex()


# ── Receipt generation (miner side) ──────────────────────────────


def build_receipt(
    agent_id_hex: str,
    model_hash_hex: str,
    task_input: str,
    output: str,
    counter: int,
    tempo_id: int,
    timestamp: float,
) -> dict:
    """
    Build a complete signed receipt.  Returns JSON-ready dict.

    This is called by the miner after task execution.
    The dict is JSON-serialised and transmitted via Axon synapse.
    """
    if _USING_RUST:
        json_str = _rs.py_build_receipt(
            agent_id_hex,
            model_hash_hex,
            task_input,
            output,
            counter,
            tempo_id,
            timestamp,
        )
        return json.loads(json_str)
    else:
        receipt = _py_generate_receipt(
            agent_id=bytes.fromhex(agent_id_hex),
            model_hash=bytes.fromhex(model_hash_hex),
            task_input=task_input,
            output=output,
            counter=counter,
            tempo_id=tempo_id,
        )
        return receipt.to_dict()


# ── Registry ──────────────────────────────────────────────────────


class Registry:
    """
    Thin wrapper. Delegates to Rust or Python registry transparently.

    Rust path: loads via RsVerifier (Rust owns the registry internally).
    Python path: wraps InvariantRegistry from invariant_gates.py.

    In Phase 2 this will sync from subtensor extrinsics.
    """

    def __init__(self, registry_path: str = "./invariant_registry.json"):
        self.registry_path = registry_path
        if not _USING_RUST:
            self._py = _PyRegistry(registry_path)

    def is_authorized(self, agent_id_hex: str) -> bool:
        if not _USING_RUST:
            return self._py.is_authorized(bytes.fromhex(agent_id_hex))
        # With Rust: authorization checked inside RsVerifier — not needed standalone
        # but kept for Python compatibility
        return True  # Verifier handles this

    def is_approved_model(self, model_hash_hex: str) -> bool:
        if not _USING_RUST:
            return self._py.is_approved_model(bytes.fromhex(model_hash_hex))
        return True

    def register_agent(self, agent_id_hex: str, hotkey: str, metadata: dict = None):
        if not _USING_RUST:
            self._py.register_agent(bytes.fromhex(agent_id_hex), hotkey, metadata or {})
        else:
            # With Rust: write to registry JSON file; RsVerifier reloads on next instantiation
            import json

            try:
                with open(self.registry_path, "r") as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                data = {"version": 1, "agents": {}, "models": []}

            data["agents"][agent_id_hex] = {
                "hotkey": hotkey,
                "registered": time.time(),
                "metadata": metadata or {},
            }

            with open(self.registry_path, "w") as f:
                json.dump(data, f, indent=2)

    def approve_model(self, model_hash_hex: str):
        if not _USING_RUST:
            self._py.approve_model(bytes.fromhex(model_hash_hex))
        else:
            # With Rust: write to registry JSON file; RsVerifier reloads on next instantiation
            import json

            try:
                with open(self.registry_path, "r") as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                data = {"version": 1, "agents": {}, "models": []}

            if model_hash_hex not in data["models"]:
                data["models"].append(model_hash_hex)

            with open(self.registry_path, "w") as f:
                json.dump(data, f, indent=2)

    def get_agents(self) -> dict:
        """
        Returns {agent_id_hex: {"hotkey": ..., ...}} dict.
        Used by the validator to map UIDs to agent IDs.
        """
        if not _USING_RUST:
            return self._py._data.get("agents", {})
        else:
            import json

            try:
                with open(self.registry_path, "r") as f:
                    data = json.load(f)
                return data.get("agents", {})
            except (FileNotFoundError, json.JSONDecodeError):
                return {}


# ── Verifier ──────────────────────────────────────────────────────


class Verifier:
    """
    Four-gate verifier.  Unified interface over Rust and Python backends.

    Usage:
        v = Verifier("./registry.json", "./state.json")
        result = v.verify(receipt_dict)
        if result["result"] != GateResult.PASS:
            score = 0.0
    """

    def __init__(
        self,
        registry_path: str = "./invariant_registry.json",
        state_path: str = "./invariant_state.json",
    ):
        self.registry_path = registry_path
        self.state_path = state_path

        if _USING_RUST:
            self._rs = _rs.RsVerifier(registry_path, state_path)
        else:
            registry = _PyRegistry(registry_path)
            self._py = _PyVerifier(registry, state_path)

    def verify(self, receipt_dict: dict) -> dict:
        """
        Verify one receipt.

        Args:
            receipt_dict: dict with keys agent_id, model_hash, execution_hash,
                          counter, digest (all hex strings), plus optional metadata.

        Returns:
            {"result": "PASS"|"GATE1_...", "gate_number": 0-4, "detail": "..."}
        """
        if _USING_RUST:
            json_str = self._rs.verify_json(json.dumps(receipt_dict))
            return json.loads(json_str)
        else:
            # Python path: convert dict to InvariantReceipt, run verify
            from invariant_gates import InvariantReceipt

            receipt = InvariantReceipt.from_dict(receipt_dict)
            py_result, detail = self._py.verify(receipt)
            gate_num = {
                "PASS": 0,
                "GATE1_AGENT_NOT_AUTHORIZED": 1,
                "GATE2_MODEL_NOT_APPROVED": 2,
                "GATE3_REPLAY_DETECTED": 3,
                "GATE4_DIGEST_MISMATCH": 4,
            }.get(py_result.value, 0)
            return {
                "result": py_result.value,
                "gate_number": gate_num,
                "detail": detail or "",
            }

    def verify_batch(self, receipt_dicts: list) -> list:
        """
        Verify a list of receipts.  Returns list of result dicts.
        Rust path uses a single FFI call for the whole batch.
        """
        if _USING_RUST:
            json_str = self._rs.verify_batch_json(json.dumps(receipt_dicts))
            return json.loads(json_str)
        else:
            return [self.verify(r) for r in receipt_dicts]

    def get_counter(self, agent_id_hex: str) -> int:
        if _USING_RUST:
            return self._rs.get_counter(agent_id_hex)
        else:
            return self._py.get_counter(agent_id_hex)


# ─────────────────────────────────────────────────────────────────
# Self-test — runs on both Rust and Python backends
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile
    import time

    backend = "Rust ✦" if _USING_RUST else "Python (fallback)"
    print(f"{'=' * 60}")
    print(f"INVARIANT Gate Bridge Self-Test  [{backend}]")
    print(f"{'=' * 60}")

    # Use a fresh temp dir each run so stale counter state never bleeds between runs.
    with tempfile.TemporaryDirectory() as _tmp:
        _reg_path = f"{_tmp}/registry.json"
        _state_path = f"{_tmp}/state.json"

        model_hex = hash_model("bridge-test-model-v1")
        agent_hex = derive_software_agent_id("5TestHotkeyBridge", model_hex, 5000)
        print(f"model_hash  = {model_hex[:16]}...")
        print(f"agent_id    = {agent_hex[:16]}...")

        # Populate registry BEFORE constructing Verifier (Rust reads JSON at init).
        reg = Registry(_reg_path)
        reg.register_agent(agent_hex, "5TestHotkeyBridge")
        reg.approve_model(model_hex)

        v = Verifier(_reg_path, _state_path)

        # Test 1 — valid receipt
        ts = time.time()
        receipt = build_receipt(agent_hex, model_hex, "What is 2+2?", "4", 1, 200, ts)
        result = v.verify(receipt)
        assert result["result"] == GateResult.PASS, f"Expected PASS: {result}"
        print(f"✅ Test 1 PASS: Valid receipt verified")

        # Test 2 — replay (same counter=1, already consumed)
        result = v.verify(receipt)
        assert result["result"] == GateResult.GATE3, f"Expected GATE3: {result}"
        print(f"✅ Test 2 PASS: Replay blocked (Gate 3)")

        # Test 3 — tampered digest
        # MUST use a fresh counter (counter=2) so Gate 3 doesn't fire first.
        fresh = build_receipt(agent_hex, model_hex, "What is 2+2?", "4", 2, 200, ts)
        bad = dict(fresh)
        bad["digest"] = "00" * 32  # zero out digest — Gate 4 must fire
        result = v.verify(bad)
        assert result["result"] == GateResult.GATE4, f"Expected GATE4: {result}"
        print(f"✅ Test 3 PASS: Tampered digest blocked (Gate 4)")

        # Test 4 — throughput (counters 1000-1999, well above what was consumed)
        N = 1000
        counter = 1000
        t0 = time.time()
        for _ in range(N):
            counter += 1
            r = build_receipt(agent_hex, model_hex, "task", "out", counter, 200, ts)
            v.verify(r)
        elapsed = time.time() - t0
        per_op = (elapsed / N) * 1_000  # ms
        per_op_us = per_op * 1000  # µs

        print(f"\n{'=' * 60}")
        print(f"Backend:       {backend}")
        print(f"Throughput:    {N} receipts in {elapsed * 1000:.1f}ms")
        print(f"Per receipt:   {per_op_us:.1f} µs")
        print(f"Rate:          {int(N / elapsed):,} receipts/second")
        if _USING_RUST:
            print(
                f"Target:        < 50 µs/receipt  →  "
                f"{'✅ MET' if per_op_us < 50 else '⚠️ CHECK'}"
            )
        else:
            print(f"Target (Rust): < 50 µs/receipt  →  build Rust for production speed")
        print(f"{'=' * 60}")
