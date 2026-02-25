# INVARIANT Subnet — Full Test Sequence

## Prerequisites

- Local `subtensor` binary built with `--features pow-faucet` (see build step below)
- Python venv at `./venv/` with `pip install -r requirements.txt` done
- Wallets: `miner1`, `validator1`, `owner` (all present in `~/.bittensor/wallets/`)

---

## Quick: Core System (no node required)

These run anywhere, any time:

```bash
source venv/bin/activate

# 1. Full pytest suite (21 tests — must all pass)
pytest invariant/invariant/tests/ -v

# 2. Local harness (5 scenario tests, no node required)
python scripts/test_locally.py

# 3. Bridge self-test (confirms Rust backend active)
python invariant/invariant/phase1_core/invariant_gates_bridge.py
```

Expected: all green, backend = Rust.

---

## Full Local Dev Setup (requires pow-faucet binary)

### Build the binary (one-time, ~30–60 min)

```bash
cd /home/arhant/Development/Bittensor/subtensor
cargo build -p node-subtensor --features pow-faucet --profile release -j4 \
    > /tmp/build.log 2>&1 &

# Monitor progress
./watch_build.sh
# Binary ready at: subtensor/target/release/node-subtensor
```

### Step 1 — Start the chain

```bash
cd /home/arhant/Development/Bittensor
./start_local.sh
```

This script starts subtensor with `--dev --one --validator` (single AURA node, produces blocks every ~8s).

Wait for: `Imported #1` in the node log.

```bash
tail -f /tmp/subtensor_node.log | grep "Imported"
```

### Step 2 — Register neurons (first-time only)

```bash
source venv/bin/activate
python instant_register.py
```

This creates subnet 1, funds wallets, and registers miner + validator.
Confirm with: `btcli subnet list --subtensor.network local`

### Step 3 — Set serving rate limit (if miner IP update fails)

If `serve_axon` keeps returning "Custom error: 11" (InvalidIpAddress when using 127.0.0.1),
or "Custom error: 12" (ServingRateLimitExceeded), run once:

```bash
source venv/bin/activate
python3 -c "
from substrateinterface import Keypair
import bittensor as bt
sub = bt.Subtensor(network='local')
alice = Keypair.create_from_uri('//Alice')
call = sub.substrate.compose_call('AdminUtils', 'sudo_set_serving_rate_limit', {'netuid': 1, 'serving_rate_limit': 0})
sudo_call = sub.substrate.compose_call('Sudo', 'sudo', {'call': call})
ext = sub.substrate.create_signed_extrinsic(call=sudo_call, keypair=alice)
r = sub.substrate.submit_extrinsic(ext, wait_for_inclusion=True, wait_for_finalization=False)
print('Rate limit set to 0:', r.is_success)
"
```

### Step 4 — Start Miner (Terminal 1)

The miner auto-detects the machine's LAN IP before axon registration (chain rejects 127.0.0.1).
Override with `--axon.external_ip X.X.X.X` only if auto-detection picks the wrong interface.

```bash
source venv/bin/activate
python miner.py \
    --wallet.name miner1 --wallet.hotkey default \
    --netuid 1 \
    --subtensor.network local \
    --axon.port 8091
```

Expected startup:
```
SUCCESS | INVARIANT Miner ready | backend=Rust | agent=... | NTS=50.0 | counter=N
SUCCESS | Axon started on port 8091
SUCCESS | ✅ Axon announced to chain
```

### Step 5 — Start Validator (Terminal 2)

```bash
source venv/bin/activate
python validator.py \
    --wallet.name validator1 --wallet.hotkey default \
    --netuid 1 \
    --subtensor.network local
```

Expected first-tempo output:
```
SUCCESS | INVARIANT Validator ready | backend=Rust | tempo=N
INFO    | === Tempo N | 1 active miners ===
DEBUG   | UID 1 dendrite result type=InvariantTask status=200
INFO    | Auto-registered agent <hex>... for UID 1 (hotkey ...)    ← first run only
INFO    | UID 1 | quality=1.00 × NTS=50.0/100 × fresh=1.0 = weight=0.5000
SUCCESS | Weights set | tempo=N | active_miners=1
```

On second and subsequent tempos: no auto-registration line (agent is cached).

---

## What Each Line Proves

| Log line | Gate/system verified |
|---|---|
| `backend=Rust` | PyO3 extension compiled and loaded |
| `status=200` | Dendrite reached miner axon, miner processed the task |
| `Auto-registered agent...` | Gate 1 first-time registration (auto-discovers from receipt) |
| `quality=1.00` | Miner computed correct SHA-256 / math output |
| `NTS=50.0/100` | OAP engine loaded, starting score for new agent |
| `weight=0.5000` | Full emission formula: quality × NTS × freshness |
| `Weights set` | On-chain weight submission successful |

---

## Notes

- **Chain rejects 127.0.0.1** for axon registration (loopback = invalid IP per subtensor pallet).
  Use the machine's LAN IP (`192.168.x.x`) or another reachable non-loopback address.
- **Custom error 11** = `InvalidIpAddress` (trying to register 127.0.0.1)
- **Custom error 12** = `ServingRateLimitExceeded` (update axon IP too frequently; run the rate-limit-reset script above)
- **validator_permit is always False** on local dev chains (no staking → no validator permit).
  The miner's blacklist only rejects hotkeys not in the metagraph.
- Node log: `tail -f /tmp/subtensor_node.log`
- Stop node: `pkill -f node-subtensor`
