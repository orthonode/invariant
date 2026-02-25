# INVARIANT — Changelog

All notable changes to INVARIANT are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### In Progress
- Bittensor testnet deployment (Phase 2)
- Open-source miner SDK (`veritas-miner` PyPI package)
- Cross-subnet NTS API (Phase 3)
- Adversarial reasoning task track

---

## [1.0.0] — 2026-02-28

### Added — Core Engine

- `invariant/phase1_core/invariant_gates.py` — Pure Python four-gate verifier
  - Gate 1: Agent identity authorization (SHA-256 registry lookup)
  - Gate 2: Model hash approval (approved model list)
  - Gate 3: Replay protection (monotonic counter enforcement)
  - Gate 4: Digest verification (SHA-256 cryptographic binding)
  - `InvariantReceipt` dataclass — 136-byte receipt format
  - `InvariantRegistry` — thread-safe agent + model registry (JSON-backed)
  - `InvariantVerifier` — stateful four-gate verifier with counter persistence
  - `derive_software_agent_id(hotkey, model_hash, reg_block)` — software agent identity
  - `derive_hardware_agent_id(efuse_mac, chip_model)` — hardware (DePIN) agent identity
  - `generate_receipt(...)` — miner-side receipt construction
  - `hash_model(identifier)` — canonical model hash derivation

- `invariant/phase1_core/invariant_gates_bridge.py` — Rust/Python unified bridge
  - Transparent backend selection: Rust extension if compiled, Python otherwise
  - `using_rust()` — runtime backend query
  - `derive_software_agent_id()` — bridge-unified identity derivation
  - `derive_hardware_agent_id()` — bridge-unified hardware identity
  - `hash_model()` — bridge-unified model hashing
  - `build_receipt()` — bridge-unified receipt construction
  - `Registry` — bridge-unified registry wrapper
  - `Verifier` — bridge-unified verifier with `verify()` and `verify_batch()`
  - `GateResult` — unified gate result constants
  - Self-test with throughput benchmark (runs on both backends)

- `invariant/phase1_core/invariant_oap.py` — OAP lifecycle trust engine
  - `MinerLedger` dataclass — per-agent behavioral state
  - `OAPEngine` — append-only behavioral ledger, JSON-persisted
  - `get_or_create(agent_id, hotkey, reg_tempo)` — cold-start at NTS=50
  - `record_clean(agent_id, tempo)` — log successful tempo, raise NTS
  - `record_violation(agent_id, tempo, gate, vtype, detail)` — log violation, apply scar
  - `record_timeout(agent_id, tempo)` — convenience wrapper for timeout violations
  - `should_anchor(agent_id, tempo)` — adaptive anchoring query
  - `checkpoint(agent_id, tempo)` — signed integrity state snapshot
  - `write_shared_checkpoint()` — atomic write for validator consensus
  - `load_shared_checkpoint()` — restore from shared checkpoint
  - `apply_override(agent_id, new_nts, reason, authorized_by, year)` — governance override
  - `emission_weight(quality, nts, in_window, late)` — canonical emission formula
  - `stats(agent_id)` — summary statistics for an agent
  - `ViolationType` enum: GATE1, GATE2, GATE3, GATE4, TIMEOUT, NO_RECEIPT
  - NTS scoring constants: start=50, max=100, min=0, catastrophic_cap=40
  - Scar system: Gate 1=25, Gate 2=15, Gate 3=20, Gate 4=25
  - Adaptive anchoring: HIGH (≥80 NTS) every 10 tempos, MED every 5, LOW every 1
  - Override governance: hard cap 2 per calendar year, append-only audit log
  - Catastrophic flag: triggered by 3× Gate 3 violations, permanent NTS cap at 40

- `invariant/invariant-gates/` — Rust crate with PyO3 bindings
  - `src/crypto.rs` — SHA-256 and Keccak-256 primitives (no_std compatible)
  - `src/receipt.rs` — 136-byte receipt struct, serialization/deserialization
  - `src/registry.rs` — thread-safe identity and model registry
  - `src/verifier.rs` — stateful four-gate verifier, counter persistence
  - `src/lib.rs` — PyO3 binding entry point
  - `benches/gate_bench.rs` — Criterion benchmarks
  - Throughput: ~9,000+ receipts/second on standard hardware
  - `maturin develop --features python-ext` build path

### Added — Bittensor Integration

- `invariant/phase1_bittensor/miner.py` — Bittensor v10 Axon miner
  - `InvariantTask` synapse: task_input, tempo_id, task_type, output, receipt_json, checkpoint_json
  - `execute_task(task_input, task_type)` — deterministic proof-of-computation tasks
  - `InvariantMiner` class with Bittensor v10 PascalCase API
  - Identity derivation and persistence across restarts (`identity.json`)
  - Monotonic counter persistence across restarts (`counter.json`)
  - OAP anchoring in task responses
  - Graceful `serve_axon` fallback for Custom Error 10 (local dev nodes)
  - Blacklist: rejects non-permitted validators
  - Priority: stake-weighted request prioritization

- `invariant/phase1_bittensor/validator.py` — Three-tier scoring pipeline
  - `generate_task(tempo, uid)` — deterministic per-(tempo, uid) task generation
  - `score_output(task_input, task_type, output)` — objective output quality scoring
  - `InvariantValidator` class with Bittensor v10 PascalCase API
  - Tier 1 — Four-gate receipt verification
  - Tier 2 — Output quality scoring (math: exact match; hash: SHA-256 verification)
  - Tier 3 — NTS multiplier from OAP engine
  - Per-miner unique task dispatch (not broadcast — prevents output copying)
  - `emission_weight = output_quality × (NTS/100) × freshness_factor`
  - Freshness windows: 120s full credit, 180s 50% credit, >180s zero
  - `set_weights` via Bittensor subtensor (normalised float32 array)

### Added — Testing

- `invariant/invariant/tests/test_invariant.py` — Full pytest suite (21 tests)
  - `TestGateEngine` (12 tests): backend reporting, valid receipt, field validation, all 8 attack vectors, batch verify
  - `TestOAPEngine` (8 tests): cold-start, clean tempos, violation, catastrophic flag, emission formula, override cap, adaptive anchoring, stats structure
  - `TestThroughput` (1 test): 1,000 verifications within time limit (0.5s Rust / 5s Python)
  - All tests isolated with `pytest.fixture(tmp_path)` — no cross-test state leakage

- `scripts/test_locally.py` — Local test harness (no Bittensor node required)
  - Pixel-art INVARIANT banner with ANSI color rendering
  - `test_receipt_generation()` — receipt build, verify, replay block, OAP basics
  - `test_attack_scenarios()` — all 8 attack vectors with explicit gate failure assertions
  - `test_oap_lifecycle()` — cold-start, escalation, catastrophic flag, emission formula, override cap
  - `test_performance()` — 1,000 verifications benchmark with µs/receipt and receipts/second
  - Colored pass/fail output with timing breakdown

### Added — Scripts

- `scripts/setup_wallets.py` — Automated wallet creation for local dev
- `scripts/register_subnet.py` — Subnet creation and registration helper
- `scripts/launch_nodes.py` — Parallel miner + validator launch helper
- `scripts/deploy_testnet.py` — Testnet deployment automation

### Added — Documentation

- `README.md` — Comprehensive project README with full architecture diagrams
- `ROADMAP.md` — 6-phase development roadmap (Phase 0 through Phase 6 + 2027 vision)
- `THREAT_MODEL.md` — Formal threat model (attacker taxonomy, gate forensics, threat matrix)
- `ARCHITECTURE.md` — Full architecture with Mermaid diagrams
- `WHITEPAPER.md` — Technical whitepaper for Hackquest Ideathon
- `CHANGELOG.md` — This file
- `CONTRIBUTING.md` — Contribution guidelines
- `SECURITY.md` — Security disclosure policy
- `LICENSE` — MIT License
- `docs/PITCH.md` — Hackquest ideathon pitch document
- `docs/INCENTIVE_MECHANISM.md` — Incentive mechanism deep dive
- `docs/DEPLOYMENT_GUIDE.md` — Full deployment guide
- `docs/LOCAL_TESTING.md` — Local test suite guide (no node required)

### Added — Configuration

- `pyproject.toml` — maturin build configuration
- `requirements.txt` — Python dependencies
- `.gitignore` — Comprehensive ignore rules (Python, Rust, Bittensor wallets, seed phrases)
- `SUBNET_PARAMS.json` — Subnet hyperparameter configuration

### Fixed — API Alignment (Bittensor v10)

- Replaced all lowercase `bt.wallet` → `bt.Wallet`
- Replaced all lowercase `bt.subtensor` → `bt.Subtensor`
- Replaced all lowercase `bt.metagraph` → `bt.Metagraph`
- Replaced all lowercase `bt.axon` → `bt.Axon`
- Replaced all lowercase `bt.dendrite` → `bt.Dendrite`
- Fixed `bt.logging.set_config(config=cfg)` call pattern
- Fixed `Dendrite` call: `await self.dendrite(axons=[axon], synapse=s, timeout=N)`
- Fixed `AxonInfo.is_serving` property usage (True when `ip != "0.0.0.0"`)
- Fixed `set_weights` signature for v10 (uids as int64, weights as float32)

### Fixed — OAP Engine

- Removed non-existent `last_seen` field from `MinerLedger` deserialization
- Fixed checkpoint data mapping to avoid `__init__` errors on load
- Added `_next_anchor_tempo()` helper for checkpoint restoration
- Fixed `should_anchor()` return value for unregistered agents

### Fixed — Bridge

- Fixed `GateResult.GATE3` constant value (`"GATE3_REPLAY_DETECTED"`)
- Fixed Rust/Python path for `verify_batch` to use single FFI call on Rust
- Fixed `Registry.get_agents()` JSON loading for Rust path
- Fixed `Verifier` construction to always happen after registry is written

### Fixed — Tests

- Added `pyproject.toml` `[tool.pytest.ini_options]` to scope discovery to `invariant/invariant/tests/`
- Fixed cross-test counter state leakage by using `tmp_path` fixtures
- Fixed tamper test to use `counter+1` (not same counter) before checking Gate 4
- Fixed OAP lifecycle test to use non-overlapping tempo numbers

---

## [0.3.0] — 2026-02-20

### Added
- TON-SHA contract deployed on TON Testnet
  - Contract: `kQBVqAhPv_ANWm0hfjJdLnQmvvC8_rQ_NEryVX3uFOUF05OP`
  - 17+ live transactions
  - Tact 1.6 implementation
  - SHA-256 native on TON (no external oracle)
  - 0.03 TON per operation
- TON Fast Grants application submitted
- Cross-layer SHA-256 parity validated (Rust ↔ Tact ↔ Python): 10,000+ test vectors

---

## [0.2.0] — 2026-02-10

### Added
- SHA contract deployed on Arbitrum Sepolia
  - Contract: `0xD661a1aB8CEFaaCd78F4B968670C3bC438415615`
  - 89+ live transactions
  - Rust Stylus implementation with Keccak-256
  - 12,564 gas per receipt at N=50 batched
- Stylus Sprint grant application submitted ($25K)
- IoTeX exploit forensic analysis published (Feb 22, 2026)
- SHA DePIN deep-dive article published

---

## [0.1.0] — 2026-01-15

### Added
- OAP (Orthonode Adaptive Protocol) architecture specification
  - Physics compliance validation model
  - Lifecycle trust scoring model design
  - Adaptive anchoring algorithm
  - Override governance design (2/yr cap)
  - Catastrophic flag mechanism
- Architecture published at orthonode.xyz/oap.html
- Nexus Protocol Phase 1.4.0: 1M transaction stress test (0% corruption, 50–60 TPS)

---

## [0.0.1] — 2026-01-01

### Added
- Orthonode Infrastructure Labs founded
- Core doctrine established:
  - Physics is invariant
  - Identity must be device-bound
  - Trust must be lifecycle-governed
  - Integrity must be append-only
  - Redemption must be bounded
  - Verification must be deterministic
- Initial research into DePIN hardware spoofing attack vectors

---

[Unreleased]: https://github.com/orthonode/invariant/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/orthonode/invariant/releases/tag/v1.0.0
[0.3.0]: https://github.com/orthonode/invariant/releases/tag/v0.3.0
[0.2.0]: https://github.com/orthonode/invariant/releases/tag/v0.2.0
[0.1.0]: https://github.com/orthonode/invariant/releases/tag/v0.1.0
[0.0.1]: https://github.com/orthonode/invariant/releases/tag/v0.0.1