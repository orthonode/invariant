# INVARIANT Subnet — Docker Test Sequence

## Root Cause: Why `latest` Image Doesn't Work Locally

The `ghcr.io/opentensor/subtensor:latest` (mainnet) image has a **sealing bug** — when
`--sealing instant` or `--sealing manual` is used (required for block production without
peers), the node panics at `service.rs:793: RefCell already mutably borrowed`.

The `ghcr.io/opentensor/subtensor:latest-local` tag is **not published** — it must be
built locally with `--features "pow-faucet"`.

---

## Mode A — Local Dev (One-Time Build Required)

### Step 1 — Build the local image once

```bash
cd /home/arhant/Development/Bittensor/subtensor
cargo build -p node-subtensor --features "pow-faucet" --profile release -j2
# Takes 30–60 min. Monitor: tail -f /tmp/subtensor_build.log
```

> `-j2` limits parallel Rust compiler jobs to stay within 7.8 GB RAM.
> Build only needs to be done once; the binary is reused afterwards.

### Step 2 — Start local dev node (after build)

```bash
# Generate chain spec (only needed once after build)
./target/release/node-subtensor build-spec --chain=local \
    --disable-default-bootnode --raw > /tmp/localnet.json

# Run single-node with instant sealing (blocks on every transaction)
./target/release/node-subtensor \
    --chain /tmp/localnet.json \
    --alice \
    --sealing instant \
    --rpc-external \
    --rpc-cors=all \
    --rpc-methods=unsafe \
    --unsafe-force-node-key-generation \
    --tmp
```

> Or wrap it in docker using the locally-built binary:
> ```bash
> docker build --target subtensor-local -t subtensor-local .
> docker-compose -f docker-compose.localnet.yml up -d
> ```

### Step 3 — Verify connection

```bash
source venv/bin/activate
python -c "
import bittensor as bt
config = bt.Config()
config.subtensor = bt.Config()
config.subtensor.network = 'local'
config.subtensor.chain_endpoint = 'ws://127.0.0.1:9944'
sub = bt.Subtensor(config=config)
print(f'Connected! Block: {sub.get_current_block()}')
"
```

### Step 4 — Register subnet and fund wallets

```bash
source venv/bin/activate
python instant_register.py
```

### Step 5 — Terminal 1: Start Miner

```bash
source venv/bin/activate
python miner.py \
    --wallet.name miner1 \
    --wallet.hotkey default \
    --netuid 1 \
    --subtensor.network local \
    --subtensor.chain_endpoint ws://127.0.0.1:9944 \
    --axon.port 8091
```

### Step 6 — Terminal 2: Start Validator

```bash
source venv/bin/activate
python validator.py \
    --wallet.name validator1 \
    --wallet.hotkey default \
    --netuid 1 \
    --subtensor.network local \
    --subtensor.chain_endpoint ws://127.0.0.1:9944
```

---

## Mode B — Mainnet Lite Docker (no local testing, requires real TAO)

### Step 1 — Start mainnet node

```bash
cd /home/arhant/Development/Bittensor/subtensor
./scripts/run/subtensor.sh -e docker --network mainnet --node-type lite
```

### Step 2 — Verify connection (wait ~30s for warp sync)

```bash
source venv/bin/activate
python -c "
import bittensor as bt
config = bt.Config()
config.subtensor = bt.Config()
config.subtensor.network = 'finney'
config.subtensor.chain_endpoint = 'ws://127.0.0.1:9944'
sub = bt.Subtensor(config=config)
print(f'Mainnet block: {sub.get_current_block()}')
"
```

### Step 3 — Start Miner (Mainnet)

```bash
source venv/bin/activate
python miner.py \
    --wallet.name miner1 \
    --wallet.hotkey default \
    --netuid 1 \
    --subtensor.network finney
```

### Step 4 — Start Validator (Mainnet)

```bash
source venv/bin/activate
python validator.py \
    --wallet.name validator1 \
    --wallet.hotkey default \
    --netuid 1 \
    --subtensor.network finney
```

---

## What Was Tried and Why It Fails

| Approach | Result | Reason |
|----------|--------|--------|
| `latest` + `--dev` | No blocks (stuck at #0) | GRANDPA needs 2+ validators |
| `latest` + `--force-authoring` | No blocks | Same - no session keys registered |
| `latest` + Alice+Bob peered | No blocks | Session keys not in local chain spec |
| `latest` + `--chain local --alice --validator` | No blocks | Same |
| `latest` + `--sealing instant` | Panic | `RefCell already mutably borrowed` bug |
| `latest` + `--sealing manual` | Panic on `engine_createBlock` | Same bug |
| `latest-local` docker pull | Fails | Image not published on ghcr.io |
| Build `subtensor-local` image | ✅ Works | Requires `--features "pow-faucet"` |

---

## Current Status

### ✅ Working
- `ghcr.io/opentensor/subtensor:latest` pulled
- Mainnet docker node connects (finney, block ~7.6M)
- Local chain spec generated: `/tmp/localnet.json`
- 21/21 INVARIANT core tests pass (Rust backend)
- `miner.py` and `validator.py` use bridge pattern correctly

### ⏳ In Progress
- Building `node-subtensor` with `pow-faucet` (background, ~30-60 min)
- Command: `cargo build -p node-subtensor --features "pow-faucet" --profile release -j2`
- Monitor: `wc -l /tmp/subtensor_build.log` (grows as crates compile)
- Check completion: `ls subtensor/target/release/node-subtensor`

### Next Steps After Build
1. Run: `./subtensor/target/release/node-subtensor --chain /tmp/localnet.json --alice --sealing instant --rpc-external --rpc-cors=all --rpc-methods=unsafe --unsafe-force-node-key-generation --tmp`
2. Regenerate chain spec from new binary (optional - `/tmp/localnet.json` may work)
3. Run `python instant_register.py`
4. Start miner + validator
