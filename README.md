<div align="center">

```
 _____ _   _ _   _  ___  ______ _____  ___   _   _ _____
|_   _| \ | | | | |/ _ \ | ___ \_   _|/ _ \ | \ | |_   _|
  | | |  \| | | | / /_\ \| |_/ / | | / /_\ \|  \| | | |
  | | | . ` | | | |  _  ||    /  | | |  _  || . ` | | |
 _| |_| |\  \ \_/ / | | || |\ \ _| |_| | | || |\  | | |
 \___/\_| \_/\___/\_| |_/\_| \_|\___/\_| |_/\_| \_/ \_/
```

**Deterministic Trust Infrastructure for Bittensor**

*by [Orthonode Infrastructure Labs](https://orthonode.xyz)*

[![CI](https://github.com/orthonode/invariant/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/orthonode/invariant/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-orange.svg)](LICENSE)
[![Bittensor](https://img.shields.io/badge/Bittensor-Subnet-7B2D8B)](https://bittensor.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![Rust](https://img.shields.io/badge/Rust-1.75%2B-orange)](https://rustup.rs)
[![Tests](https://img.shields.io/badge/Tests-21%20passing-brightgreen)](#testing)
[![SHA Live](https://img.shields.io/badge/SHA-Arbitrum%20Sepolia%20LIVE-brightgreen)](https://sepolia.arbiscan.io/address/0xD661a1aB8CEFaaCd78F4B968670C3bC438415615)
[![TON-SHA Live](https://img.shields.io/badge/TON--SHA-Testnet%20LIVE-brightgreen)](https://testnet.tonscan.org/address/kQBVqAhPv_ANWm0hfjJdLnQmvvC8_rQ_NEryVX3uFOUF05OP)

---

> *"Don't trust the output. Verify the execution."*

> *"We didn't build INVARIANT for this ideathon. We built it because Bittensor's own whitepaper admits the ledger cannot audit the parameters of each model. INVARIANT is the answer to their own stated limitation."*

</div>

---

## What is INVARIANT?

INVARIANT is a Bittensor subnet that produces a cryptographically-verified **INVARIANT Trust Score (NTS)** per miner — derived from three independently unfakeable layers stacked into a complete trust stack that Bittensor has never had.

Every Bittensor subnet today trusts miner *outputs*. INVARIANT makes them *provable*.

| Layer | Technology | What it proves | Status |
|-------|-----------|----------------|--------|
| **Layer 1 — SHA** | Hardware-bound identity (Keccak-256) | *Who* this miner is | [Live on Arbitrum Sepolia](https://sepolia.arbiscan.io/address/0xD661a1aB8CEFaaCd78F4B968670C3bC438415615) · 89+ txns |
| **Layer 2 — TON-SHA** | Execution receipt (SHA-256 four-gate) | *How* they produced the output | [Live on TON Testnet](https://testnet.tonscan.org/address/kQBVqAhPv_ANWm0hfjJdLnQmvvC8_rQ_NEryVX3uFOUF05OP) · 17+ txns |
| **Layer 3 — OAP** | Lifecycle trust governance | *Who they have been* across every tempo | Architecture published at [orthonode.xyz](https://orthonode.xyz) |

**Emission formula:**

```
weight = output_quality × (NTS / 100) × freshness_factor
```

A miner with NTS 90 and perfect output scores 0.90. A miner with NTS 40 (prior violations, gaming history) and perfect output scores 0.40. **Past behavior permanently affects future earnings.**

---

## The Problem

Academic analysis of two years of Bittensor on-chain data found that **rewards are driven by stake, not quality**. The root cause: Bittensor's Yuma Consensus scores miners on *outputs*, but outputs are trivial to fake:

| Attack | Current Defense | INVARIANT Defense |
|--------|----------------|-------------------|
| Return a cached response | None | `execution_hash` includes `tempo_id` → Gate 4 fails |
| Copy another miner's output | None | `agent_id` is hotkey-bound → Gate 1 fails |
| Run cheap model, claim expensive | None | `model_hash` must match approved registry → Gate 2 fails |
| Submit same receipt twice | None | Monotonic counter → Gate 3 fails |
| Sybil with new identities | None | NTS starts at 50, gaming costs real tempo time |
| Validator cartel collusion | Yuma (probabilistic) | Gates are deterministic — two honest validators always agree |
| Digest forgery | None | Can't produce valid SHA-256 without running the computation |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    LAYER 3 — OAP ENGINE                         │
│              Lifecycle Trust Governance (Python)                │
│                                                                 │
│  Trust score 0–100 · Append-only behavioral history             │
│  Catastrophic flag (permanent cap at 40) · Scar accumulation    │
│  Adaptive anchoring · Override governance (2/yr cap)            │
│                                                                 │
│  OUTPUT: Signed integrity state per miner per tempo             │
└──────────────────────────┬──────────────────────────────────────┘
                           │ feeds into
┌──────────────────────────▼──────────────────────────────────────┐
│                    LAYER 2 — EXECUTION RECEIPT                  │
│            Four-Gate Verification (Rust + Python bridge)        │
│                                                                 │
│  Gate 1: agent_id in authorized registry?                       │
│  Gate 2: model_hash in approved list?                           │
│  Gate 3: counter > last confirmed counter?                      │
│  Gate 4: SHA-256(agent_id‖model_hash‖execution_hash‖counter)    │
│          == digest?                                             │
│                                                                 │
│  OUTPUT: Per-execution tamper-evident, replay-safe receipt      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ anchored by
┌──────────────────────────▼──────────────────────────────────────┐
│                    LAYER 1 — IDENTITY                           │
│            Hardware-Bound / Software-Bound Agent ID             │
│                                                                 │
│  Software: SHA-256(hotkey_ss58 ‖ model_hash ‖ reg_block)        │
│  Hardware: Keccak-256(eFuse MAC ‖ chip_model) — DePIN nodes     │
│  Monotonic counter rollback protection                          │
│  Clone containment · Key rotation governance                    │
│                                                                 │
│  OUTPUT: 32-byte tamper-proof agent_id                          │
└─────────────────────────────────────────────────────────────────┘
```

### Repository Structure

```
INVARIANT/
├── invariant/
│   ├── invariant-gates/               ← Rust crate (PyO3 extension)
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs                 ← crate root + PyO3 bindings
│   │       ├── crypto.rs              ← SHA-256, Keccak-256 primitives
│   │       ├── receipt.rs             ← 136-byte receipt struct
│   │       ├── registry.rs            ← thread-safe identity + model registry
│   │       └── verifier.rs            ← stateful four-gate verifier
│   │
│   └── invariant/
│       ├── phase1_core/
│       │   ├── invariant_gates_bridge.py    ← THE BRIDGE (always import this)
│       │   ├── invariant_gates.py           ← Pure Python fallback
│       │   └── invariant_oap.py             ← OAP trust engine
│       ├── phase1_bittensor/
│       │   ├── miner.py                     ← Bittensor Axon miner
│       │   └── validator.py                 ← Three-tier scoring validator
│       └── tests/
│           └── test_invariant.py            ← Full test suite (21 tests)
│
├── scripts/
│   ├── test_locally.py           ← Local test harness (no node required)
│   ├── deploy_testnet.py         ← Testnet deployment automation
│   ├── setup_wallets.py          ← Wallet creation helper
│   ├── register_subnet.py        ← Subnet registration helper
│   └── launch_nodes.py           ← Launch miner + validator helper
│
├── docs/
│   ├── WHITEPAPER.md             ← Technical whitepaper
│   ├── INCENTIVE_MECHANISM.md    ← Incentive mechanism deep dive
│   ├── PITCH.md                  ← Hackquest ideathon pitch document
│   ├── DEPLOYMENT_GUIDE.md       ← Full deployment guide
│   └── LOCAL_TESTING.md          ← Local test suite guide
│
├── README.md
├── ROADMAP.md
├── THREAT_MODEL.md               ← Complete threat model
├── ARCHITECTURE.md               ← Full architecture + Mermaid diagrams
├── CHANGELOG.md
├── CONTRIBUTING.md
├── SECURITY.md
└── LICENSE
```

---

## Quickstart

### Prerequisites

- Python 3.10+
- `pip install bittensor`

### Option A — Python only (no Rust required, zero friction)

```bash
git clone https://github.com/orthonode/invariant.git
cd invariant

pip install -r requirements.txt

# Run the full local test suite — no node required
python scripts/test_locally.py

# Run pytest (21 tests)
pytest invariant/invariant/tests/ -v
```

Everything works immediately. The bridge automatically detects that the Rust `.so` is absent and falls back to pure Python — **zero code changes anywhere**.

### Option B — Rust + Python (production speed, ~50–100× faster)

```bash
# 1. Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh && source "$HOME/.cargo/env"

# 2. Install maturin
pip install maturin

# 3. Build the Rust extension
cd invariant/invariant-gates
maturin develop --features python-ext --release
cd ../..

# 4. Verify Rust backend is active
python -c "
import sys; sys.path.insert(0,'invariant/invariant/phase1_core')
from invariant_gates_bridge import using_rust
print('Rust backend:', using_rust())
"
# → Rust backend: True

# 5. Run tests (same tests, Rust speed)
python scripts/test_locally.py
pytest invariant/invariant/tests/ -v
```

---

## The Bridge Pattern

All Python code imports **exclusively** through the bridge. Never import `invariant_gates.py` directly.

```python
# CORRECT — always through the bridge
from invariant_gates_bridge import (
    Verifier, Registry, GateResult,
    build_receipt, derive_software_agent_id, hash_model,
)

# NEVER do this
from invariant_gates import InvariantVerifier  # ← wrong
```

The bridge tries `import invariant_gates_rs` first. Rust runs if the `.so` exists. Python runs if not. **The API is byte-for-byte identical either way.**

---

## The Four Gates

Every receipt passes all four gates in sequence. First failure short-circuits — **zero score, no partial credit**.

```
GATE 1 — Identity Authorization
   Is agent_id in the authorized registry?
   → Blocks: Sybil attacks, unknown agents, cross-miner output copying

GATE 2 — Model Approval
   Is model_hash in the validator-approved list?
   → Blocks: Model impersonation (claiming GPT-4 while running llama-3.2-1b)

GATE 3 — Replay Protection
   Is counter strictly greater than last confirmed counter?
   → Blocks: Exact replay attacks, counter rollback attacks

GATE 4 — Digest Verification
   SHA-256(agent_id ‖ model_hash ‖ execution_hash ‖ counter) == digest?
   → Blocks: Any tampering with receipt fields, output forgery
   → Note: execution_hash = SHA-256(task_input ‖ output ‖ tempo_id)
            Cannot be produced without running the actual computation.
```

Two honest validators on the same receipt **always produce identical gate results**. This is the structural anti-collusion guarantee. Disagreement between validators is on-chain evidence of compromise.

---

## The Receipt Format

```
INVARIANT RECEIPT (136 bytes conceptually)
─────────────────────────────────────────────
Field            Size     Content
─────────────────────────────────────────────
agent_id         32 bytes SHA-256(hotkey ‖ model_hash ‖ reg_block)
model_hash       32 bytes SHA-256(model_identifier_string)
execution_hash   32 bytes SHA-256(task_input ‖ output ‖ tempo_id)
counter          8 bytes  Monotonic uint64, strictly increasing
digest           32 bytes SHA-256(all four fields above, packed)
─────────────────────────────────────────────
Total:           136 bytes
```

---

## Performance

| Backend | Per receipt | 1,000-receipt batch | 192-miner tempo sweep |
|---------|------------|--------------------|-----------------------|
| **Python** (fallback) | ~2 ms | ~2,000 ms | ~384,000 ms |
| **Rust** (production) | <50 µs | <50 ms | <10 ms |

Measured on standard developer hardware. Run benchmarks:

```bash
# Python benchmark (included in test suite)
python scripts/test_locally.py

# Rust microbenchmarks
cd invariant/invariant-gates
cargo bench
# → target/criterion/
```

---

## Bittensor Local Subnet Setup

Complete guide for running INVARIANT on a local subtensor dev node.

### 1. Build and start local subtensor

```bash
git clone https://github.com/opentensor/subtensor.git
cd subtensor
cargo build --release --features pow-faucet
./target/release/node-subtensor --dev --tmp &
cd ..
```

### 2. Create wallets

```bash
btcli wallet new_coldkey --wallet.name owner
btcli wallet new_hotkey  --wallet.name owner     --wallet.hotkey default
btcli wallet new_coldkey --wallet.name miner1
btcli wallet new_hotkey  --wallet.name miner1    --wallet.hotkey default
btcli wallet new_coldkey --wallet.name miner2
btcli wallet new_hotkey  --wallet.name miner2    --wallet.hotkey default
btcli wallet new_coldkey --wallet.name validator1
btcli wallet new_hotkey  --wallet.name validator1 --wallet.hotkey default
```

### 3. Fund wallets

```bash
btcli wallet faucet --wallet.name owner      --subtensor.network local
btcli wallet faucet --wallet.name validator1 --subtensor.network local
btcli wallet faucet --wallet.name miner1     --subtensor.network local
btcli wallet faucet --wallet.name miner2     --subtensor.network local
```

### 4. Create the INVARIANT subnet

```bash
btcli subnet create --wallet.name owner --subtensor.network local
# ─── Note the NETUID printed ───
export NETUID=1   # replace with your actual netuid
```

### 5. Register miners and validator

```bash
btcli subnet register --netuid $NETUID --wallet.name miner1     --subtensor.network local
btcli subnet register --netuid $NETUID --wallet.name miner2     --subtensor.network local
btcli subnet register --netuid $NETUID --wallet.name validator1 --subtensor.network local
```

### 6. Stake the validator

```bash
btcli stake add --wallet.name validator1 --amount 1000 --subtensor.network local
```

### 7. Launch

```bash
# Miner 1
python invariant/invariant/phase1_bittensor/miner.py \
    --wallet.name miner1 --wallet.hotkey default \
    --netuid $NETUID --subtensor.network local \
    --axon.port 8091 &

# Miner 2
python invariant/invariant/phase1_bittensor/miner.py \
    --wallet.name miner2 --wallet.hotkey default \
    --netuid $NETUID --subtensor.network local \
    --axon.port 8092 &

# Validator
python invariant/invariant/phase1_bittensor/validator.py \
    --wallet.name validator1 --wallet.hotkey default \
    --netuid $NETUID --subtensor.network local
```

---

## Testing

### Full local test suite (no node required)

```bash
python scripts/test_locally.py
```

Expected output includes:
- ✅ Receipt generation + OAP basics
- ✅ All 8 attack scenarios blocked
- ✅ OAP trust lifecycle (cold-start, escalation, catastrophic flag, override cap)
- ✅ Throughput benchmark

### Pytest (21 tests)

```bash
pytest invariant/invariant/tests/ -v
```

### Bridge self-test

```bash
python invariant/invariant/phase1_core/invariant_gates_bridge.py
```

---

## Attack Vectors

| # | Attack | Gate | Mechanism |
|---|--------|------|-----------|
| 1 | Replay (same receipt twice) | 3 | Monotonic counter — mathematically airtight |
| 2 | Counter rollback | 3 | Counter must be strictly greater |
| 3 | Sybil (unknown agent) | 1 | `agent_id` must be in authorized registry |
| 4 | Model impersonation | 2 | `model_hash` must match approved list |
| 5 | Digest tamper | 4 | SHA-256 of all four fields — physically unforgeable |
| 6 | Output caching (cross-tempo) | 4 | `execution_hash` includes `tempo_id` — different tempo = different hash |
| 7 | Output copying (cross-miner) | 1 | `agent_id` is hotkey-bound — can't forge another miner's ID |
| 8 | Wrong input in execution_hash | 4 | `execution_hash` binds to specific task input |
| 9 | Validator collusion | Yuma | Gates are deterministic — disagreement is provable on-chain |
| 10 | NTS tank-and-recover gaming | OAP | Catastrophic flag is permanent · Recovery bounded at 0.3/tempo |

---

## NTS Scoring

NTS (INVARIANT Trust Score) is a continuous float on `[0.0, 100.0]`.

| Event | Effect |
|-------|--------|
| Cold start | NTS = 50.0 |
| Clean tempo | NTS rises (log-scaled consistency bonus) |
| Gate 1 violation | −25.0 scar |
| Gate 2 violation | −15.0 scar |
| Gate 3 violation | −20.0 scar |
| Gate 4 violation | −25.0 scar |
| 3× Gate 3 violations | Catastrophic flag: permanent cap at 40.0 |
| Override | Max 2 per year, signed + logged |

---

## Credentials

INVARIANT is not a whitepaper. The underlying technology is live on two chains:

| Contract | Chain | Address | Status |
|----------|-------|---------|--------|
| SHA | Arbitrum Sepolia | [`0xD661a1aB8CEFaaCd78F4B968670C3bC438415615`](https://sepolia.arbiscan.io/address/0xD661a1aB8CEFaaCd78F4B968670C3bC438415615) | **89+ transactions** |
| TON-SHA | TON Testnet | [`kQBVqAhPv_ANWm0hfjJdLnQmvvC8_rQ_NEryVX3uFOUF05OP`](https://testnet.tonscan.org/address/kQBVqAhPv_ANWm0hfjJdLnQmvvC8_rQ_NEryVX3uFOUF05OP) | **17+ transactions** |
| OAP | — | Architecture at [orthonode.xyz/oap.html](https://orthonode.xyz/oap.html) | In development |

Cross-layer Keccak-256 and SHA-256 parity validated across **10,000+ test vectors**.

---

## Why Bittensor Specifically

Bittensor is the only network with economic incentives (TAO emissions) to make it rational for miners worldwide to maintain a permanent behavioral record. Without Bittensor's emission model, a miner has no reason to honestly maintain their OAP record. With emissions tied to NTS, **honest behavior is the profit-maximizing strategy**.

The miner/validator architecture maps perfectly to the executor/verifier separation that INVARIANT requires. No other chain has this structure.

---

## License

MIT License — see [LICENSE](LICENSE).

---

## About Orthonode

[Orthonode Infrastructure Labs](https://orthonode.xyz) builds deterministic physical verification infrastructure for autonomous systems, DePIN networks, and mobility platforms.

- **Location:** Bhopal, Madhya Pradesh, India
- **Research:** [orthonode.xyz](https://orthonode.xyz)
- **X / Twitter:** [@orthonode](https://x.com/orthonode)

---

<div align="center">

*"Physics is invariant. Verification is deterministic. Trust is earned, not assumed."*

**— Orthonode Infrastructure Labs**

</div>