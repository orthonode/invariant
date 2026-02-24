# INVARIANT — Deployment Guide

**Deterministic Trust Infrastructure for Bittensor**  
*by Orthonode Infrastructure Labs*

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Local Development (Localnet)](#local-development-localnet)
4. [Testnet Deployment](#testnet-deployment)
5. [Miner Configuration](#miner-configuration)
6. [Validator Configuration](#validator-configuration)
7. [Running the Test Suite](#running-the-test-suite)
8. [Rust Backend (Production Speed)](#rust-backend-production-speed)
9. [Troubleshooting](#troubleshooting)
10. [Security Checklist](#security-checklist)

---

## Overview

INVARIANT runs on the standard Bittensor miner/validator architecture. This guide covers:

- **Local development** — full subnet simulation on your machine, no tokens required
- **Testnet** — live Bittensor testnet deployment for demonstration
- **Production** — mainnet deployment (Phase 4, Q2 2026)

The Python fallback requires zero compilation. Rust extension adds ~50–100× speed.

---

## Prerequisites

### Required

| Dependency | Version | Install |
|-----------|---------|---------|
| Python | 3.10+ | `python --version` |
| pip | 23+ | `pip install --upgrade pip` |
| bittensor | 7.0+ | `pip install bittensor` |
| git | any | `git --version` |

### For local subtensor node

| Dependency | Version | Install |
|-----------|---------|---------|
| Rust toolchain | 1.75+ | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |
| gcc / build-essential | any | `sudo apt install build-essential` (Linux) |

### For Rust gate engine (optional, ~50–100× faster)

| Dependency | Version | Install |
|-----------|---------|---------|
| Rust toolchain | 1.75+ | (same as above) |
| maturin | 1.4+ | `pip install maturin` |

---

## Local Development (Localnet)

Local development runs a full Bittensor subnet on your machine. No real TAO required.

### Step 1 — Clone the repository

```bash
git clone https://github.com/orthonode/invariant.git
cd invariant
```

### Step 2 — Install Python dependencies

```bash
pip install -r requirements.txt
```

### Step 3 — Build and start local subtensor

```bash
# Clone subtensor (if not already done)
git clone https://github.com/opentensor/subtensor.git
cd subtensor

# Build with proof-of-work faucet enabled (required for local dev)
cargo build --release --features pow-faucet

# Start the local dev node (in a separate terminal or background)
./target/release/node-subtensor --dev --tmp &

# Verify it's running
sleep 3
curl -s http://127.0.0.1:9933 -H "Content-Type: application/json" \
  -d '{"id":1,"jsonrpc":"2.0","method":"system_health","params":[]}' \
  | python3 -m json.tool

cd ..
```

You should see `"isSyncing": false` and `"peers": 0` (local node has no peers — correct).

### Step 4 — Create wallets

```bash
# Owner wallet (creates and owns the subnet)
btcli wallet new_coldkey --wallet.name owner     --no-password
btcli wallet new_hotkey  --wallet.name owner     --wallet.hotkey default --no-password

# Miner wallets
btcli wallet new_coldkey --wallet.name miner1    --no-password
btcli wallet new_hotkey  --wallet.name miner1    --wallet.hotkey default --no-password
btcli wallet new_coldkey --wallet.name miner2    --no-password
btcli wallet new_hotkey  --wallet.name miner2    --wallet.hotkey default --no-password

# Validator wallet
btcli wallet new_coldkey --wallet.name validator1 --no-password
btcli wallet new_hotkey  --wallet.name validator1 --wallet.hotkey default --no-password
```

> **Security note:** `--no-password` is only for local development. Never use on testnet or mainnet.

### Step 5 — Fund wallets via faucet

```bash
# Fund owner (needs TAO to create subnet)
btcli wallet faucet --wallet.name owner      --subtensor.network local
btcli wallet faucet --wallet.name owner      --subtensor.network local  # run 2–3 times

# Fund validator (needs TAO to stake)
btcli wallet faucet --wallet.name validator1 --subtensor.network local
btcli wallet faucet --wallet.name validator1 --subtensor.network local

# Fund miners (optional — miners don't need TAO to operate)
btcli wallet faucet --wallet.name miner1     --subtensor.network local
btcli wallet faucet --wallet.name miner2     --subtensor.network local
```

Check balances:
```bash
btcli wallet overview --wallet.name owner     --subtensor.network local
btcli wallet overview --wallet.name validator1 --subtensor.network local
```

### Step 6 — Create the INVARIANT subnet

```bash
btcli subnet create \
    --wallet.name owner \
    --wallet.hotkey default \
    --subtensor.network local

# ─── IMPORTANT: note the NETUID printed ───
# It's usually 1 on a fresh local node.
export NETUID=1
```

Verify subnet was created:
```bash
btcli subnet list --subtensor.network local
```

### Step 7 — Register miners and validator

```bash
btcli subnet register \
    --netuid $NETUID \
    --wallet.name miner1 \
    --wallet.hotkey default \
    --subtensor.network local

btcli subnet register \
    --netuid $NETUID \
    --wallet.name miner2 \
    --wallet.hotkey default \
    --subtensor.network local

btcli subnet register \
    --netuid $NETUID \
    --wallet.name validator1 \
    --wallet.hotkey default \
    --subtensor.network local
```

### Step 8 — Stake the validator

```bash
btcli stake add \
    --wallet.name validator1 \
    --wallet.hotkey default \
    --amount 1000 \
    --subtensor.network local
```

Verify metagraph:
```bash
btcli subnet metagraph --netuid $NETUID --subtensor.network local
```

### Step 9 — Launch miner(s)

Open a new terminal for each miner:

**Terminal 2 — Miner 1:**
```bash
python invariant/invariant/phase1_bittensor/miner.py \
    --wallet.name miner1 \
    --wallet.hotkey default \
    --netuid $NETUID \
    --subtensor.network local \
    --axon.port 8091 \
    --model_identifier "invariant-v1" \
    --logging.debug
```

**Terminal 3 — Miner 2:**
```bash
python invariant/invariant/phase1_bittensor/miner.py \
    --wallet.name miner2 \
    --wallet.hotkey default \
    --netuid $NETUID \
    --subtensor.network local \
    --axon.port 8092 \
    --model_identifier "invariant-v1" \
    --logging.debug
```

### Step 10 — Launch validator

**Terminal 4 — Validator:**
```bash
python invariant/invariant/phase1_bittensor/validator.py \
    --wallet.name validator1 \
    --wallet.hotkey default \
    --netuid $NETUID \
    --subtensor.network local \
    --logging.debug
```

The validator will:
1. Sync metagraph
2. Generate unique tasks per miner
3. Query each miner via Dendrite
4. Run four-gate verification on each receipt
5. Score with OAP NTS multiplier
6. Call `set_weights` on chain

### Step 11 — Verify it's working

Watch the validator logs for lines like:
```
INVARIANT Validator ready | backend=Python | tempo=0
=== Tempo 0 | 2 active miners ===
UID 0 | quality=1.00 × NTS=50.0/100 × fresh=1.0 = weight=0.5000
UID 1 | quality=1.00 × NTS=50.0/100 × fresh=1.0 = weight=0.5000
Weights set | tempo=0 | active_miners=2
```

---

## Testnet Deployment

For Bittensor testnet (Finney test network), the process is similar but requires:

- Testnet TAO from the faucet at [Discord #testnet-faucet](https://discord.gg/bittensor)
- Public IP addresses for miners (or port forwarding)
- Real wallet security (use passwords)

### Key differences from localnet

```bash
# Replace --subtensor.network local with:
--subtensor.network test

# Replace --subtensor.chain_endpoint ws://127.0.0.1:9944 with:
# (not needed — 'test' uses the default testnet endpoint)

# Wallets should use passwords on testnet:
btcli wallet new_coldkey --wallet.name miner1   # will prompt for password
```

### Obtain testnet TAO

```bash
# Join Bittensor Discord and request testnet TAO in #testnet-faucet
# Then check balance:
btcli wallet overview --wallet.name owner --subtensor.network test
```

### Register on testnet

All btcli commands are identical except `--subtensor.network test` replaces `local`.

### Miner public accessibility

On testnet, your miner's axon must be reachable from validator IPs. Ensure:

```bash
# Open firewall port (example — adjust to your firewall)
sudo ufw allow 8091/tcp
sudo ufw allow 8092/tcp

# Verify external connectivity
curl http://YOUR_PUBLIC_IP:8091/  # should return something from the axon
```

---

## Miner Configuration

### Full argument reference

```bash
python invariant/invariant/phase1_bittensor/miner.py \
    --wallet.name miner1 \          # wallet cold key name
    --wallet.hotkey default \        # wallet hot key name
    --netuid 1 \                     # subnet netuid
    --subtensor.network local \      # network: local | test | finney
    --axon.port 8091 \               # port for this miner's axon
    --model_identifier "my-model-v1" \ # human-readable model name
    --logging.debug \                # verbose logging
    --logging.trace                  # even more verbose
```

### Data files

The miner creates the following files in `./miner_data/`:

| File | Contents | Notes |
|------|----------|-------|
| `identity.json` | agent_id, model_hash, hotkey | Created once at registration |
| `counter.json` | Current monotonic counter | Persisted across restarts |
| `registry.json` | Agent + model registry | Written at startup |
| `oap.json` | OAP ledger (NTS state) | Append-only, grows over time |

> **Important:** Never delete `counter.json` between restarts. If deleted, the counter resets to 0, which may cause Gate 3 failures until the counter naturally exceeds the validator's last-confirmed value.

### Model identifier

The `--model_identifier` argument determines the miner's `model_hash`:

```
model_hash = SHA-256("my-model-v1")
```

This hash must be in the validator's approved model list. The default `"invariant-v1"` is automatically approved by the validator template.

To add a custom model:
1. Run your miner with `--model_identifier "your-model-name"`
2. The miner will register this model hash automatically (Phase 1 behavior)
3. In Phase 2+, model approval will be governed by on-chain voting

---

## Validator Configuration

### Full argument reference

```bash
python invariant/invariant/phase1_bittensor/validator.py \
    --wallet.name validator1 \       # validator wallet
    --wallet.hotkey default \
    --netuid 1 \
    --subtensor.network local \
    --logging.debug
```

### Data files

The validator creates the following files in `./validator_data/`:

| File | Contents | Notes |
|------|----------|-------|
| `registry.json` | Approved agents + models | Built from miner registrations |
| `state.json` | Per-agent counter state | **Never delete** — enables Gate 3 |
| `oap.json` | All miner OAP ledgers | Append-only behavioral history |

> **Critical:** `state.json` tracks the last confirmed counter per agent. If this file is deleted, Gate 3 resets and all counters below the old confirmed values become valid again. Back this file up regularly.

### Scoring parameters

Edit these constants in `validator.py` to tune scoring:

```python
WINDOW_BLOCKS = 10   # blocks for full freshness credit (120s at 12s/block)
LATE_BLOCKS   = 15   # blocks for 50% freshness credit (180s at 12s/block)
MIN_QUALITY   = 0.3  # minimum quality score for any weight
```

### Weight setting

The validator normalizes weights before calling `set_weights`. If all miners score 0.0 in a tempo, `set_weights` is skipped (no on-chain transaction).

---

## Running the Test Suite

### Local harness (no node required — recommended first step)

```bash
python scripts/test_locally.py
```

This runs 5 test suites:
1. Receipt generation + OAP basics
2. All 8 attack scenarios
3. OAP trust lifecycle
4. Throughput benchmark
5. Bridge self-check

Options:
```bash
python scripts/test_locally.py --no-color   # disable ANSI colors (CI environments)
python scripts/test_locally.py --quick      # reduced iteration count (faster)
```

### Pytest (21 tests)

```bash
pytest invariant/invariant/tests/ -v
```

Run specific test classes:
```bash
pytest invariant/invariant/tests/ -v -k "TestGateEngine"
pytest invariant/invariant/tests/ -v -k "TestOAPEngine"
pytest invariant/invariant/tests/ -v -k "TestThroughput"
```

### Bridge self-test

```bash
python invariant/invariant/phase1_core/invariant_gates_bridge.py
```

Expected output includes:
```
✅ Test 1 PASS: Valid receipt verified
✅ Test 2 PASS: Replay blocked (Gate 3)
✅ Test 3 PASS: Tampered digest blocked (Gate 4)
Rate: 500+ receipts/second (Python) or 9,000+ receipts/second (Rust)
```

---

## Rust Backend (Production Speed)

The Rust gate engine is optional but provides ~50–100× faster verification.

### Build

```bash
# Ensure Rust is installed
rustup --version

# Install maturin
pip install maturin

# Build and install into current Python environment
cd invariant/invariant-gates
maturin develop --features python-ext --release
cd ../..
```

### Verify

```bash
python -c "
import sys
sys.path.insert(0, 'invariant/invariant/phase1_core')
from invariant_gates_bridge import using_rust
print('Rust backend active:', using_rust())
"
```

Expected: `Rust backend active: True`

### Run benchmarks

```bash
cd invariant/invariant-gates
cargo bench
# Results saved to target/criterion/
```

### Build a distributable wheel

```bash
cd invariant/invariant-gates
maturin build --features python-ext --release
# Wheel in: target/wheels/invariant_gates_rs-*.whl
```

Install the wheel:
```bash
pip install target/wheels/invariant_gates_rs-*.whl
```

---

## Troubleshooting

### Custom Error 10 on serve_axon

**Symptom:** `serve_axon failed: Custom Error 10`

**Cause:** The subnet state is still settling after creation, or the miner's registration is not yet finalized on-chain.

**Fix:** Wait 10–15 seconds and restart the miner. The miner handles this gracefully — it continues operating even if `serve_axon` fails, because the axon is still reachable by IP.

```bash
# If the miner exits with this error, just restart:
python invariant/invariant/phase1_bittensor/miner.py [same args] &
```

### No active miners found by validator

**Symptom:** `No active miners in metagraph (is_serving=False for all)`

**Cause:** Miners haven't started yet, or `serve_axon` failed for all miners.

**Fix:**
1. Ensure miners are running and their axon ports are open
2. Wait 1–2 tempo cycles for metagraph to sync
3. Check miner logs for `Axon started on port XXXX`

### Gate 3 failures after restart

**Symptom:** All receipts fail at Gate 3 after restarting a miner

**Cause:** The miner's `counter.json` was deleted or corrupted. The counter reset to 0, but the validator's `state.json` remembers a higher confirmed counter.

**Fix:**
```bash
# Option 1: Check the validator's state.json for your agent_id
cat validator_data/state.json

# Option 2: Reset the miner's counter to a value higher than the validator's last confirmed
# Edit miner_data/counter.json:
echo '{"counter": 100000}' > miner_data/counter.json

# Option 3: Re-register with a new hotkey (NTS resets to 50)
```

### OAP checkpoint errors

**Symptom:** `KeyError: 'last_seen'` or similar on OAP load

**Cause:** Stale OAP JSON from an older schema version.

**Fix:**
```bash
# Delete and let OAP rebuild from scratch
rm miner_data/oap.json validator_data/oap.json
```

NTS scores reset to 50 for all miners. This is acceptable in development but not on mainnet (OAP history is valuable).

### Validator not setting weights

**Symptom:** Validator runs but `set_weights` is never called

**Cause:** Either all miners scored 0.0 (all gate failures) or the validator doesn't have enough stake.

**Fix:**
```bash
# Check validator stake
btcli wallet overview --wallet.name validator1 --subtensor.network local

# Add more stake if needed
btcli stake add --wallet.name validator1 --amount 1000 --subtensor.network local
```

### ImportError for invariant_gates_bridge

**Symptom:** `ModuleNotFoundError: No module named 'invariant_gates_bridge'`

**Cause:** `sys.path` doesn't include the `phase1_core` directory.

**Fix:** Always run scripts from the repository root:
```bash
# From the repo root:
python scripts/test_locally.py          # ✅
python invariant/invariant/phase1_bittensor/miner.py ...  # ✅

# NOT from inside the scripts/ directory:
cd scripts && python test_locally.py    # ❌ path resolution will fail
```

### Python 3.10+ type hint errors

**Symptom:** `TypeError: 'type' object is not subscriptable` on `list[tuple[...]]`

**Cause:** Python < 3.10 doesn't support `list[...]` syntax in runtime code.

**Fix:** Upgrade to Python 3.10+ or add `from __future__ import annotations` at the top of affected files.

---

## Security Checklist

Before any testnet or mainnet deployment:

- [ ] All wallet coldkeys use strong passwords (`btcli wallet new_coldkey` without `--no-password`)
- [ ] Seed phrases stored offline, never in the repository
- [ ] `seed-phrase/` directory confirmed absent from git (`git status`)
- [ ] `.bittensor/` directory confirmed in `.gitignore`
- [ ] `wallets_*.json` files confirmed absent from git
- [ ] `miner_data/` and `validator_data/` in `.gitignore`
- [ ] `state.json` backed up (counter state is critical for Gate 3)
- [ ] Miner axon port (8091+) not exposed on mainnet validators
- [ ] Validator data directory not world-readable (`chmod 700 validator_data/`)
- [ ] Log files don't contain hotkey private keys (they shouldn't, but verify)
- [ ] `--no-password` flag never used outside local development

---

## Quick Reference

### Reset local development environment

```bash
# Stop all processes
kill $(pgrep -f "node-subtensor") 2>/dev/null
kill $(pgrep -f "miner.py") 2>/dev/null
kill $(pgrep -f "validator.py") 2>/dev/null

# Clean up data directories (local dev only — never on testnet)
rm -rf miner_data/ validator_data/

# Clean up Bittensor wallets (local dev only)
rm -rf ~/.bittensor/wallets/miner1 ~/.bittensor/wallets/miner2
rm -rf ~/.bittensor/wallets/validator1 ~/.bittensor/wallets/owner

# Start fresh
./subtensor/target/release/node-subtensor --dev --tmp &
```

### One-command local test (no node required)

```bash
python scripts/test_locally.py && pytest invariant/invariant/tests/ -v
```

---

*Deployment Guide v1.0.0 — February 2026*  
*Orthonode Infrastructure Labs — orthonode.xyz*