#!/usr/bin/env bash
# watch_build.sh — Monitor the subtensor pow-faucet build
BINARY="/home/arhant/Development/Bittensor/subtensor/target/release/node-subtensor"
LOG="/tmp/build.log"

while true; do
    clear
    echo "════════════════════════════════════════"
    echo "  Subtensor pow-faucet Build Monitor"
    echo "════════════════════════════════════════"
    echo ""
    
    if [[ -f "$BINARY" ]]; then
        SIZE=$(du -h "$BINARY" | cut -f1)
        echo "  ✅  BUILD COMPLETE! Binary: $BINARY ($SIZE)"
        echo ""
        echo "  Next step: ./start_local.sh"
        break
    fi
    
    DONE=$(grep "Compiling" "$LOG" 2>/dev/null | wc -l)
    RUNNING=$(ps aux | grep "cargo build" | grep -v grep | wc -l)
    
    echo "  Status: $([[ $RUNNING -gt 0 ]] && echo 'Compiling...' || echo 'Not running!')"
    echo "  Crates compiled: $DONE / ~600"
    echo "  Progress: $(echo "scale=0; $DONE * 100 / 600" | bc)%"
    echo ""
    echo "  Memory:"
    free -h | grep Mem
    echo ""
    echo "  Last 5 crates:"
    grep "Compiling" "$LOG" 2>/dev/null | tail -5 | sed 's/   Compiling/    •/'
    echo ""
    echo "  (refreshes every 10s — Ctrl+C to exit)"
    
    sleep 10
done
