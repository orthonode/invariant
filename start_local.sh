#!/usr/bin/env bash
# start_local.sh — One-shot INVARIANT local dev environment
# Run from: /home/arhant/Development/Bittensor/
# Usage:    ./start_local.sh [--register-only | --node-only]

set -e
BINARY="/home/arhant/Development/Bittensor/subtensor/target/release/node-subtensor"
CHAINSPEC="/tmp/localnet.json"
ENDPOINT="ws://127.0.0.1:9944"
LOG_NODE="/tmp/subtensor_node.log"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
fail() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── 0. Check binary ─────────────────────────────────────────────────────────
[[ -f "$BINARY" ]] || fail "Binary not found: $BINARY\nRun: cd subtensor && cargo build -p node-subtensor --features pow-faucet --profile release -j4"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  INVARIANT Local Dev — start_local.sh"
echo "═══════════════════════════════════════════════════════"

if [[ "$1" != "--register-only" ]]; then
    # ── 1. Stop any existing node ──────────────────────────────────────────
    pkill -f "node-subtensor" 2>/dev/null && warn "Killed existing node" && sleep 2

    # ── 2. Start node in background ────────────────────────────────────────
    echo ""
    echo "[1/4] Starting subtensor node (--dev --one single-validator mode)..."
    nohup "$BINARY" \
        --dev \
        --one \
        --validator \
        --rpc-external \
        --rpc-cors=all \
        --rpc-methods=unsafe \
        > "$LOG_NODE" 2>&1 &
    NODE_PID=$!
    echo "      PID=$NODE_PID  Log=$LOG_NODE"

    # ── 4. Wait for RPC ────────────────────────────────────────────────────
    echo "      Waiting for RPC to come up..."
    for i in $(seq 1 20); do
        sleep 2
        if grep -q "Running JSON-RPC server" "$LOG_NODE" 2>/dev/null; then
            ok "Node RPC ready (${i}×2s)"
            break
        fi
        if [[ $i -eq 20 ]]; then
            fail "Node didn't start after 40s. Check log: $LOG_NODE"
        fi
    done
fi

if [[ "$1" != "--node-only" ]]; then
    # ── 5. Register ────────────────────────────────────────────────────────
    echo ""
    echo "[3/4] Running instant_register.py..."
    source /home/arhant/Development/Bittensor/venv/bin/activate
    cd /home/arhant/Development/Bittensor
    python instant_register.py

    # ── 6. Instructions ────────────────────────────────────────────────────
    echo ""
    echo "[4/4] Ready. Open two more terminals and run:"
    echo ""
    echo "  Terminal 1 (miner):"
    echo "  cd /home/arhant/Development/Bittensor && source venv/bin/activate"
    echo "  python miner.py \\"
    echo "      --wallet.name miner1 --wallet.hotkey default \\"
    echo "      --netuid 1 --subtensor.network local --axon.port 8091"
    echo "  # LAN IP is auto-detected — no --axon.external_ip needed"
    echo ""
    echo "  Terminal 2 (validator):"
    echo "  cd /home/arhant/Development/Bittensor && source venv/bin/activate"
    echo "  python validator.py \\"
    echo "      --wallet.name validator1 --wallet.hotkey default \\"
    echo "      --netuid 1 --subtensor.network local"
    echo ""
    echo "  Or run everything via master test suite:"
    echo "  python run_tests.py --all"
    echo ""
    echo "  Node log:  tail -f $LOG_NODE"
    echo "  Stop node: pkill -f node-subtensor"
    echo ""
    echo "═══════════════════════════════════════════════════════"
fi
