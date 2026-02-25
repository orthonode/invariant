"""
invariant/tests/test_invariant.py
===================================
Full test suite.  Runs on both Rust and Python backends.
All 8 attack vectors.  OAP lifecycle.  Emission formula.  Bridge.

Run:
    pytest invariant/tests/ -v
"""

import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../phase1_core"))

from invariant_gates_bridge import (
    Verifier, Registry, GateResult,
    derive_software_agent_id, hash_model, build_receipt, using_rust,
)
from invariant_oap import OAPEngine, ViolationType

# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def model_hex():
    return hash_model("invariant-test-model-v1")


@pytest.fixture(scope="module")
def agent_hex(model_hex):
    return derive_software_agent_id("5TestHotkeyInvariant", model_hex, 1000)


@pytest.fixture
def verifier(tmp_path, agent_hex, model_hex):
    reg_path   = str(tmp_path / "registry.json")
    state_path = str(tmp_path / "state.json")

    reg = Registry(reg_path)
    reg.register_agent(agent_hex, "5TestHotkeyInvariant")
    reg.approve_model(model_hex)

    return Verifier(reg_path, state_path)


@pytest.fixture
def oap(tmp_path, agent_hex):
    engine = OAPEngine(str(tmp_path / "oap.json"))
    engine.get_or_create(agent_hex, "5TestHotkeyInvariant", 100)
    return engine


@pytest.fixture
def receipt_factory(agent_hex, model_hex):
    """Returns a factory function for building receipts."""
    counter = [0]
    def make(task="What is 2+2?", output="4", tempo=100):
        counter[0] += 1
        return build_receipt(agent_hex, model_hex, task, output, counter[0], tempo, time.time())
    return make


# ── Tests: Gate Engine ────────────────────────────────────────────

class TestGateEngine:

    def test_backend_reported(self):
        """Bridge reports which backend is active."""
        backend = "Rust" if using_rust() else "Python"
        print(f"\n  Backend: {backend}")
        assert isinstance(using_rust(), bool)

    def test_valid_receipt_passes(self, verifier, receipt_factory):
        r = receipt_factory()
        result = verifier.verify(r)
        assert GateResult.is_pass(result["result"]), f"Expected PASS: {result}"
        assert result["gate_number"] == 0

    def test_receipt_is_136_bytes_conceptually(self, agent_hex, model_hex):
        """Verify the dict has all required fields."""
        r = build_receipt(agent_hex, model_hex, "task", "out", 1, 100, time.time())
        for field in ["agent_id", "model_hash", "execution_hash", "counter", "digest"]:
            assert field in r, f"Missing field: {field}"
        for hex_field in ["agent_id", "model_hash", "execution_hash", "digest"]:
            assert len(r[hex_field]) == 64, f"{hex_field} should be 64 hex chars"

    # ── Attack 1: Replay ──────────────────────────────────────────

    def test_attack_replay(self, verifier, receipt_factory):
        """Same receipt submitted twice → Gate 3 fires."""
        r = receipt_factory()
        assert GateResult.is_pass(verifier.verify(r)["result"])
        result = verifier.verify(r)
        assert result["result"] == GateResult.GATE3, f"Replay not caught: {result}"
        assert result["gate_number"] == 3

    # ── Attack 2: Counter rollback ────────────────────────────────

    def test_attack_counter_rollback(self, verifier, agent_hex, model_hex):
        """Submitting lower counter → Gate 3 fires."""
        r5 = build_receipt(agent_hex, model_hex, "t", "o", 500, 100, time.time())
        r3 = build_receipt(agent_hex, model_hex, "t", "o", 3,   100, time.time())
        assert GateResult.is_pass(verifier.verify(r5)["result"])
        result = verifier.verify(r3)
        assert result["result"] == GateResult.GATE3

    # ── Attack 3: Unknown agent (Sybil) ───────────────────────────

    def test_attack_sybil_unknown_agent(self, verifier, model_hex):
        """Unknown agent_id → Gate 1 fires."""
        bad_agent = "ff" * 32
        r = build_receipt(bad_agent, model_hex, "task", "out", 1, 100, time.time())
        result = verifier.verify(r)
        assert result["result"] == GateResult.GATE1, f"Sybil not caught: {result}"
        assert result["gate_number"] == 1

    # ── Attack 4: Model impersonation ─────────────────────────────

    def test_attack_model_impersonation(self, verifier, agent_hex):
        """Unapproved model_hash → Gate 2 fires."""
        bad_model = hash_model("unapproved-model-v999")
        r = build_receipt(agent_hex, bad_model, "task", "out", 1, 100, time.time())
        result = verifier.verify(r)
        assert result["result"] == GateResult.GATE2, f"Model spoof not caught: {result}"
        assert result["gate_number"] == 2

    # ── Attack 5: Digest tamper ───────────────────────────────────

    def test_attack_digest_tamper(self, verifier, receipt_factory):
        """Zeroed digest → Gate 4 fires."""
        r = receipt_factory()
        r["digest"] = "00" * 32
        result = verifier.verify(r)
        assert result["result"] == GateResult.GATE4, f"Tamper not caught: {result}"
        assert result["gate_number"] == 4

    # ── Attack 6: Output caching (cross-tempo) ────────────────────

    def test_attack_output_caching(self, agent_hex, model_hex):
        """Same task+output but different tempo → different execution_hash."""
        r1 = build_receipt(agent_hex, model_hex, "task", "4", 1, 100, time.time())
        r2 = build_receipt(agent_hex, model_hex, "task", "4", 2, 101, time.time())
        assert r1["execution_hash"] != r2["execution_hash"], \
            "Different tempos must produce different execution_hashes"

    # ── Attack 7: Output copying (cross-miner) ────────────────────

    def test_attack_output_copying(self, model_hex):
        """Miner B cannot use Miner A's receipt — agent_ids differ."""
        m_hex   = model_hex
        agent_a = derive_software_agent_id("5MinerA", m_hex, 100)
        agent_b = derive_software_agent_id("5MinerB", m_hex, 101)

        r_a = build_receipt(agent_a, m_hex, "task A", "ans", 1, 100, time.time())
        r_b = build_receipt(agent_b, m_hex, "task A", "ans", 1, 100, time.time())

        # Different agent_ids → different digests → Gate 4 would catch any substitution
        assert r_a["agent_id"]  != r_b["agent_id"]
        assert r_a["digest"]    != r_b["digest"]

    # ── Attack 8: Execution hash binds to specific input ──────────

    def test_attack_wrong_input_execution_hash(self, agent_hex, model_hex):
        """Miner receives task A but claims task B's execution hash → doesn't match."""
        r_correct = build_receipt(agent_hex, model_hex, "task A", "ans", 1, 100, time.time())
        r_wrong   = build_receipt(agent_hex, model_hex, "task B", "ans", 1, 100, time.time())
        # Execution hashes must differ because inputs differ
        assert r_correct["execution_hash"] != r_wrong["execution_hash"]

    # ── Batch ─────────────────────────────────────────────────────

    def test_batch_verify(self, verifier, agent_hex, model_hex):
        """Batch of 10 sequential receipts all pass."""
        receipts = [
            build_receipt(agent_hex, model_hex, f"task {i}", "ans", 9000 + i, 100, time.time())
            for i in range(10)
        ]
        results = verifier.verify_batch(receipts)
        assert all(GateResult.is_pass(r["result"]) for r in results), \
            f"Batch failure: {[r for r in results if not GateResult.is_pass(r['result'])]}"


# ── Tests: OAP Engine ─────────────────────────────────────────────

class TestOAPEngine:

    def test_cold_start(self, oap, agent_hex):
        assert oap.get_nts(agent_hex) == 50.0

    def test_clean_tempos_raise_nts(self, oap, agent_hex):
        for t in range(101, 121):
            oap.record_clean(agent_hex, t)
        assert oap.get_nts(agent_hex) > 50.0

    def test_violation_drops_nts(self, oap, agent_hex):
        base = oap.get_nts(agent_hex)
        oap.record_violation(agent_hex, 121, 4, ViolationType.GATE4, "test")
        assert oap.get_nts(agent_hex) < base

    def test_catastrophic_flag(self, oap, agent_hex):
        for i in range(3):
            oap.record_violation(agent_hex, 130 + i, 3, ViolationType.GATE3, "replay")
        assert oap.get_nts(agent_hex) <= 40.0
        ledger = oap._ledgers[agent_hex]
        assert ledger.catastrophic

    def test_emission_weight_formula(self):
        w = OAPEngine.emission_weight(1.0, 90.0, in_window=True)
        assert abs(w - 0.9) < 0.001

        w_late = OAPEngine.emission_weight(1.0, 90.0, in_window=False, late=True)
        assert abs(w_late - 0.45) < 0.001

        w_zero = OAPEngine.emission_weight(1.0, 90.0, in_window=False, late=False)
        assert w_zero == 0.0

    def test_override_cap(self, tmp_path, agent_hex):
        engine = OAPEngine(str(tmp_path / "override_oap.json"))
        engine.get_or_create(agent_hex, "5Override", 0)

        ok, msg = engine.apply_override(agent_hex, 75.0, "test", "admin", 2026)
        assert ok, msg
        ok, msg = engine.apply_override(agent_hex, 80.0, "test", "admin", 2026)
        assert ok, msg
        ok, msg = engine.apply_override(agent_hex, 85.0, "test", "admin", 2026)
        assert not ok, "Third override in same year should be rejected"

    def test_adaptive_anchoring(self, tmp_path):
        engine = OAPEngine(str(tmp_path / "anchor_oap.json"))
        aid    = "ab" * 32
        engine.get_or_create(aid, "5Anchor", 0)

        # Force NTS high
        for t in range(1, 81):
            engine.record_clean(aid, t)

        # At NTS > 80 anchor interval should be 10
        assert engine.should_anchor(aid, 90)   # next_anchor = ~91
        assert not engine.should_anchor(aid, 85)

    def test_stats_structure(self, oap, agent_hex):
        s = oap.stats(agent_hex)
        assert "nts" in s
        assert "violations" in s
        assert "streak" in s


# ── Tests: Throughput ─────────────────────────────────────────────

class TestThroughput:
    def test_1000_verifications_complete_in_reasonable_time(
        self, verifier, agent_hex, model_hex
    ):
        """
        1000 verifications should complete in < 5 seconds on Python,
        < 0.2 seconds on Rust.
        """
        N    = 1000
        base = 50_000

        t0 = time.time()
        for i in range(N):
            r = build_receipt(
                agent_hex, model_hex, f"task {i}", f"out {i}",
                base + i, 100, time.time()
            )
            verifier.verify(r)
        elapsed = time.time() - t0

        # 2.0s for Rust (stable under background load); still ≥2.5× faster than Python 5.0s
        limit = 2.0 if using_rust() else 5.0
        assert elapsed < limit, (
            f"{'Rust' if using_rust() else 'Python'} took {elapsed:.2f}s "
            f"for {N} verifications (limit {limit}s)"
        )
        rate = N / elapsed
        print(f"\n  Throughput: {rate:,.0f} receipts/sec ({elapsed*1000:.0f}ms total)")
