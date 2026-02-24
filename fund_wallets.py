#!/usr/bin/env python3
"""
Fund INVARIANT wallets from Alice sudo account on local --dev node.
Alice's URI on every Substrate dev node: //Alice
"""
import bittensor as bt

# Your three coldkeys from the screenshot
WALLETS = {
    "owner":      "5DaFrQjhPKy4LQQ4WXhWspzZhjViMQgPNE3kuTzoHgtWMPgb",
    "miner1":     "5CJyjX24nbwKyQSLCMJrYkNJdyo3qp3ebekhvVQPdDXfGnuS",
    "validator1": "5G6JzqK9Si47gLQxWrT2RitAUYz7hw7RzcHX6ZMSTwWphE6f",
}

AMOUNT    = 10_000  # TAO per wallet
ENDPOINT  = "ws://127.0.0.1:9944"

print("Connecting to local subtensor...")
config = bt.Config()
config.subtensor.chain_endpoint = ENDPOINT
config.subtensor.network = "local"
sub = bt.Subtensor(config=config)

# Alice keypair — built into every Substrate --dev node
# URI is //Alice, NOT a 12-word mnemonic
from bittensor.utils.balance import Balance
import bittensor.core.subtensor as bts

# Use substrate interface directly — the correct way
substrate = sub.substrate

print("Creating Alice keypair...")
from substrateinterface import Keypair
alice = Keypair.create_from_uri("//Alice")
print(f"Alice address: {alice.ss58_address}")

# Check Alice balance first
alice_balance = sub.get_balance(alice.ss58_address)
print(f"Alice balance: {alice_balance}")

print(f"\nFunding {len(WALLETS)} wallets with {AMOUNT:,} TAO each...\n")

for name, addr in WALLETS.items():
    try:
        # Check before
        before = sub.get_balance(addr)
        
        # Build transfer call
        call = substrate.compose_call(
            call_module   = "Balances",
            call_function = "transfer_keep_alive",
            call_params   = {
                "dest":  addr,
                "value": AMOUNT * 10**9,   # Convert TAO → rao (1 TAO = 1e9 rao)
            }
        )
        
        # Sign and submit with Alice
        extrinsic = substrate.create_signed_extrinsic(call=call, keypair=alice)
        receipt   = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
        
        # Check after
        after = sub.get_balance(addr)
        print(f"  ✓ {name}: {before} → {after}")
        
    except Exception as e:
        print(f"  ✗ {name}: FAILED — {e}")

print("\nDone. Verify with:")
for name, addr in WALLETS.items():
    print(f"  btcli wallet balance --subtensor.chain_endpoint ws://127.0.0.1:9944")
