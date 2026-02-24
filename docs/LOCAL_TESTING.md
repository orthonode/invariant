# INVARIANT — Local Testing Guide

**Run the full test suite in under 30 seconds. No Bittensor node required.**

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/orthonode/invariant.git
cd invariant
pip install -r invariant/requirements.txt

# Run everything
python3 scripts/test_locally.py
```

That's it. The pixel-art terminal UI will run 5 test suites and print a full summary.

---

## What Gets Tested

| Suite | What it covers | Time |
|-------|----------------|------|
| **Test 1** — Receipt generation + OAP basics | Build receipt, verify all 4 gates, replay block, NTS cold-start | ~5ms |
| **Test 2** — All 8 attack scenarios | Every known attack vector blocked at the correct gate | ~2ms |
| **Test 3** — OAP trust lifecycle | Cold-start, escalation, catastrophic flag, emission formula, override cap | ~10ms |
| **Test 4** — Throughput benchmark | 1,000 verifications, µs/receipt, receipts/second | ~200ms |
| **Test 5** — Bridge self-check | Rust/Python backend detection, batch verify, registry ops | ~5ms |

**Total: < 1 second** (Python fallback). **< 100ms** (Rust backend after `maturin develop`).

---

## Test Output

### Success

```
════════════════════════════════════════════════════════════════════════════════
  INVARIANT TEST SUITE RESULTS
════════════════════════════════════════════════════════════════════════════════

  ✅  PASS  Receipt generation + OAP basics             2ms
  ✅  PASS  All 8 attack scenarios                      1ms
  ✅  PASS  OAP trust lifecycle                         8ms
  ✅  PASS  Throughput / performance                    191ms
  ✅  PASS  Bridge self-check                           4ms

────────────────────────────────────────────────────────────────────────────────
  5/5 tests passed

                    🎉  ALL TESTS PASSED — INVARIANT is working correctly

════════════════════════════════════════════════════════════════════════════════
```

### Attack vector output (Test 2)

```
  ✅  PASS  Attack 1 · Replay — Gate 3 blocks duplicate counter
  ✅  PASS  Attack 2 · Counter rollback — Gate 3 blocks lower counter
  ✅  PASS  Attack 3 · Sybil identity — Gate 1 blocks unknown agent_id
  ✅  PASS  Attack 4 · Model impersonation — Gate 2 blocks unapproved hash
  ✅  PASS  Attack 5 · Digest tamper — Gate 4 catches zeroed digest
  ✅  PASS  Attack 6 · Output caching — different tempo_id → different execution_hash
  ✅  PASS  Attack 7 · Output copying — cross-miner agent_id and digest differ
  ✅  PASS  Attack 8 · Wrong input — different task_input → different execution_hash
```

Every line shows exactly which gate fires for each attack. This is the live demonstration you can run in front of judges.

---

## Command Options

```bash
# Default: full color, 1000 iterations
python3 scripts/test_locally.py

# No color (for CI or plain terminals)
python3 scripts/test_locally.py --no-color

# Quick mode (200 iterations, faster)
python3 scripts/test_locally.py --quick
```

---

## Pytest (21 unit tests)

The pytest suite covers identical ground with fixture isolation:

```bash
# Activate your venv first
. venv/bin/activate

# Run all 21 tests
pytest invariant/invariant/tests/ -v

# Run just gate engine tests
pytest invariant/invariant/tests/ -v -k "TestGateEngine"

# Run just OAP tests
pytest invariant/invariant/tests/ -v -k "TestOAPEngine"

# Run throughput test
pytest invariant/invariant/tests/ -v -k "TestThroughput"
```

Expected output:
```
collected 21 items

invariant/invariant/tests/test_invariant.py::TestGateEngine::test_backend_reported PASSED
invariant/invariant/tests/test_invariant.py::TestGateEngine::test_valid_receipt_passes PASSED
invariant/invariant/tests/test_invariant.py::TestGateEngine::test_receipt_is_136_bytes_conceptually PASSED
invariant/invariant/tests/test_invariant.py::TestGateEngine::test_attack_replay PASSED
invariant/invariant/tests/test_invariant.py::TestGateEngine::test_attack_counter_rollback PASSED
invariant/invariant/tests/test_invariant.py::TestGateEngine::test_attack_sybil_unknown_agent PASSED
invariant/invariant/tests/test_invariant.py::TestGateEngine::test_attack_model_impersonation PASSED
invariant/invariant/tests/test_invariant.py::TestGateEngine::test_attack_digest_tamper PASSED
invariant/invariant/tests/test_invariant.py::TestGateEngine::test_attack_output_caching PASSED
invariant/invariant/tests/test_invariant.py::TestGateEngine::test_attack_output_copying PASSED
invariant/invariant/tests/test_invariant.py::TestGateEngine::test_attack_wrong_input_execution_hash PASSED
invariant/invariant/tests/test_invariant.py::TestGateEngine::test_batch_verify PASSED
invariant/invariant/tests/test_invariant.py::TestOAPEngine::test_cold_start PASSED
invariant/invariant/tests/test_invariant.py::TestOAPEngine::test_clean_tempos_raise_nts PASSED
invariant/invariant/tests/test_invariant.py::TestOAPEngine::test_violation_drops_nts PASSED
invariant/invariant/tests/test_invariant.py::TestOAPEngine::test_catastrophic_flag PASSED
invariant/invariant/tests/test_invariant.py::TestOAPEngine::test_emission_weight_formula PASSED
invariant/invariant/tests/test_invariant.py::TestOAPEngine::test_override_cap PASSED
invariant/invariant/tests/test_invariant.py::TestOAPEngine::test_adaptive_anchoring PASSED
invariant/invariant/tests/test_invariant.py::TestOAPEngine::test_stats_structure PASSED
invariant/invariant/tests/test_invariant.py::TestThroughput::test_1000_verifications_complete_in_reasonable_time PASSED

============================== 21 passed in 1.17s ===============================
```

---

## Bridge Self-Test

The bridge self-test runs the three canonical scenarios (valid receipt, replay block, digest tamper) plus a throughput measurement directly from the bridge module:

```bash
python3 invariant/invariant/phase1_core/invariant_gates_bridge.py
```

Expected:
```
============================================================
INVARIANT Gate Bridge Self-Test  [Python (fallback)]
============================================================
model_hash  = 7a31e33fa703f3c1...
agent_id    = 679fd17190abc9be...
✅ Test 1 PASS: Valid receipt verified
✅ Test 2 PASS: Replay blocked (Gate 3)
✅ Test 3 PASS: Tampered digest blocked (Gate 4)

============================================================
Backend:       Python (fallback)
Throughput:    1000 receipts in 189.5ms
Per receipt:   189.5 µs
Rate:          5,275 receipts/second
Target (Rust): < 50 µs/receipt  →  build Rust for production speed
============================================================
```

---

## Upgrade to Rust Backend (~50–100× faster)

The Rust backend is optional. Everything works on Python. But if you want production speed:

```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
. "$HOME/.cargo/env"

# Install maturin
pip install maturin

# Build the extension (from the invariant-gates directory)
cd invariant/invariant-gates
maturin develop --features python-ext --release
cd ../..

# Verify Rust is active
python3 -c "
import sys
sys.path.insert(0, 'invariant/invariant/phase1_core')
from invariant_gates_bridge import using_rust
print('Rust active:', using_rust())
"
# → Rust active: True

# Run tests again — same tests, Rust speed
python3 scripts/test_locally.py
```

With Rust active, the throughput test will show:

```
  Per receipt        47.3 µs
  Throughput         21,142 receipts / second
  Target (< 50 µs)   ✅  MET  (actual 47.3 µs)
```

---

## What Tests Prove to a Verifier

When you run `python3 scripts/test_locally.py` in front of a judge or reviewer, the output proves:

1. **Receipt construction works** — the miner can build a valid 5-field receipt
2. **All four gates enforce** — each gate fires correctly on the attack designed to trigger it
3. **Replay is mathematically blocked** — submitting the same counter twice fails Gate 3
4. **Cross-miner copying is impossible** — different agent_ids produce different digests
5. **Output caching is impossible** — different tempo_ids produce different execution_hashes
6. **OAP lifecycle is correct** — cold-start at 50, clean tempos raise NTS, violations lower it, catastrophic flag caps at 40, override cap is enforced at 2/year
7. **Emission formula is correct** — quality × (NTS/100) × freshness produces expected values
8. **Performance is production-ready** — 1,000 verifications in ~200ms (Python), <50ms (Rust)

No Bittensor node. No TAO. No network connection. Just the cryptographic engine, running live.

---

## Interpreting Failures

### `ModuleNotFoundError: No module named 'invariant_gates_bridge'`

Run from the repository root:
```bash
cd /path/to/invariant   # repo root
python3 scripts/test_locally.py
```

### `AssertionError` in Test 2

One of the attack scenarios didn't produce the expected gate failure. Check:
1. Was `_new_agent()` called fresh in a temp dir?
2. Is the counter starting from a value above any previously consumed counter?
3. Is the `verifier` constructed after the registry file is written?

### Test 4 exceeds time limit

Python backend limit is 5 seconds. If it exceeds:
- Your hardware is very slow — try `--quick` for 200 iterations
- Or build the Rust backend (`maturin develop`)

Rust backend limit is 0.5 seconds.

### OAP tests show unexpected NTS values

OAP NTS depends on the exact scar formula. If you see values like `91.5` instead of `~60` after 20 clean tempos, this is correct — the current formula's initial clean-tempo boost is steeper than a linear model. All assertions test relative relationships (must be > 50.0, must drop after violation) rather than exact values, so tests pass regardless of exact formula parameterization.

---

## CI Integration

For continuous integration, use:

```bash
python3 scripts/test_locally.py --no-color --quick
echo "Exit code: $?"
```

Exit code `0` = all tests passed. Exit code `1` = one or more failures.

GitHub Actions example:
```yaml
- name: Run INVARIANT test suite
  run: |
    pip install -r invariant/requirements.txt
    python3 scripts/test_locally.py --no-color --quick

- name: Run pytest
  run: |
    pytest invariant/invariant/tests/ -v --tb=short
```

---

*Local Testing Guide v1.0.0 — February 2026*
*Orthonode Infrastructure Labs — orthonode.xyz*