# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**INVARIANT** is a Bittensor subnet that produces a cryptographically-verified trust score (NTS, 0–100) per miner. It proves *how* miners produce outputs, not just what they output, via a three-layer trust stack (SHA identity → execution receipt → OAP lifecycle engine).

## Commands

### Testing

```bash
# Full pytest suite (21 tests) — must all pass before any PR
pytest invariant/invariant/tests/ -v

# Run a single test
pytest invariant/invariant/tests/test_invariant.py::TestGateEngine::test_attack_replay -v

# Local harness (no Bittensor node required)
python scripts/test_locally.py

# Bridge self-test (confirms which backend is active)
python invariant/invariant/phase1_core/invariant_gates_bridge.py
```

### Rust Extension

```bash
# Build Rust extension (production speed, ~50–100× faster than Python)
cd invariant/invariant-gates
maturin develop --features python-ext --release
cd ../..

# Verify Rust backend active
python -c "
import sys; sys.path.insert(0,'invariant/invariant/phase1_core')
from invariant_gates_bridge import using_rust
print('Rust:', using_rust())
"

# Rust checks (required before committing Rust changes)
cd invariant/invariant-gates
cargo fmt
cargo clippy -- -D warnings
cargo test

# Rust benchmarks
cargo bench
```

### Install

```bash
pip install -r requirements.txt
# For Rust extension: pip install maturin
```

### Running Nodes (requires local subtensor)

```bash
python invariant/invariant/phase1_bittensor/miner.py \
    --wallet.name miner1 --wallet.hotkey default \
    --netuid $NETUID --subtensor.network local \
    --axon.port 8091

python invariant/invariant/phase1_bittensor/validator.py \
    --wallet.name validator1 --wallet.hotkey default \
    --netuid $NETUID --subtensor.network local
```

## Architecture

### Three-Layer Trust Stack

```
Layer 1 (Identity/SHA): agent_id = SHA-256(hotkey ‖ model_hash ‖ reg_block)
Layer 2 (Execution Receipt): 136-byte receipt with four-gate cryptographic verification
Layer 3 (OAP Engine): Lifecycle trust score (NTS), append-only behavioral history
```

Emission weight formula: `quality × (NTS/100) × freshness`

### Repository Layout

```
invariant/
├── invariant-gates/          ← Rust crate (PyO3 extension, builds invariant_gates_rs.so)
│   └── src/
│       ├── lib.rs            ← PyO3 module root
│       ├── crypto.rs         ← SHA-256, Keccak-256 primitives
│       ├── receipt.rs        ← 136-byte receipt struct
│       ├── registry.rs       ← thread-safe identity + model registry
│       └── verifier.rs       ← stateful four-gate verifier
│
└── invariant/
    ├── phase1_core/
    │   ├── invariant_gates_bridge.py  ← THE BRIDGE (always import from here)
    │   ├── invariant_gates.py         ← Pure Python fallback (byte-for-byte identical to Rust)
    │   └── invariant_oap.py           ← OAP trust engine
    ├── phase1_bittensor/
    │   ├── miner.py                   ← Bittensor Axon miner
    │   └── validator.py               ← Three-tier scoring validator
    └── tests/
        └── test_invariant.py          ← Full test suite (21 tests)

scripts/                               ← Standalone scripts (excluded from pytest)
protocol.py                            ← InvariantTask synapse definition
```

### The Bridge Pattern

**Always import exclusively through the bridge.** Never import `invariant_gates.py` directly.

```python
# CORRECT
from invariant_gates_bridge import (
    Verifier, Registry, GateResult,
    build_receipt, derive_software_agent_id, hash_model,
)

# NEVER do this
from invariant_gates import InvariantVerifier  # wrong
```

The bridge tries `import invariant_gates_rs` first; falls back to pure Python if the `.so` is absent. The API is identical either way.

### Four Gates (all must pass, first failure → score 0.0)

1. **Gate 1 — Identity Authorization**: `agent_id` in authorized registry? (blocks Sybil, cross-miner copying)
2. **Gate 2 — Model Approval**: `model_hash` in approved list? (blocks model impersonation)
3. **Gate 3 — Replay Protection**: `counter > last_confirmed`? (blocks replays, rollback attacks)
4. **Gate 4 — Digest Verification**: `SHA-256(agent_id ‖ model_hash ‖ execution_hash ‖ counter) == digest`? (blocks any tampering, output forgery, cross-tempo caching)

### Critical Invariants

- **Gate logic must be byte-for-byte identical** between `invariant_gates.py` and the Rust crate. Any change to gate logic must update both.
- **The bridge never contains gate logic** — it is a routing layer only.
- **OAP ledger is append-only** — no silent NTS resets ever; NTS is clamped to `[0.0, 100.0]`.
- **Catastrophic flag is permanent** (3× Gate 3 violations → NTS cap at 40.0, only overridable max 2×/year).
- **Bittensor integration**: Use v10+ PascalCase API; maintain graceful fallback for `serve_axon` Custom Error 10; task dispatch is per-miner (not broadcast).

## Code Standards

### Python
- PEP 8, 100-character line limit
- Type hints required on all public function signatures
- Docstrings required on all public classes and functions
- Conventional Commits: `type(scope): description` — scopes: `gates`, `oap`, `bridge`, `miner`, `validator`, `rust`, `tests`, `scripts`, `docs`

### Rust
- `cargo fmt` before every commit
- `cargo clippy -- -D warnings` must pass
- No `unwrap()` in library code; no `unsafe` without explicit justification

### Test Standards

Each test must assert:
- *Which gate fired* (`result["result"] == GateResult.GATE3`)
- *Which gate number* (`result["gate_number"] == 3`)
- Include a docstring explaining the attack scenario being tested

New tests belong in `TestGateEngine` (gate behavior), `TestOAPEngine` (OAP scoring), or `TestThroughput` (performance-sensitive changes).
