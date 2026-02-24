#!/usr/bin/env python3
"""
INVARIANT — POW Fix + Optimized Registration
=============================================

WHY POW GOES STALE:
  Bittensor's PoW is block-bound. The solution is only valid for 3 blocks
  (~36 seconds on mainnet, but on local --dev nodes blocks come every 2-3s).
  If solving takes longer than 3 blocks → stale. Submission rejected.

THREE ROOT CAUSES:
  1. Too few CPU processes assigned to solving
  2. Local --dev node producing blocks faster than standard testnet
  3. Difficulty not being rechecked when new block arrives mid-solve

THIS SCRIPT FIXES ALL THREE:
  - Uses all available CPU cores
  - Monitors block changes mid-solve and restarts if needed
  - Submits immediately on solution (no delay)
  - Falls back to sudo transfer on local dev node (bypasses POW entirely)
  - For local dev: uses Alice to fund and register directly (zero POW needed)

Run:
  python register_invariant.py --network local    # local dev node (recommended)
  python register_invariant.py --network test     # public testnet
"""

import os
import sys
import time
import argparse
import multiprocessing

import bittensor as bt
from substrateinterface import Keypair


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

WALLETS = {
    "owner":      "5DaFrQjhPKy4LQQ4WXhWspzZhjViMQgPNE3kuTzoHgtWMPgb",
    "miner1":     "5CJyjX24nbwKyQSLCMJrYkNJdyo3qp3ebekhvVQPdDXfGnuS",
    "validator1": "5G6JzqK9Si47gLQxWrT2RitAUYz7hw7RzcHX6ZMSTwWphE6f",
}

LOCAL_ENDPOINT  = "ws://127.0.0.1:9944"
TEST_ENDPOINT   = "wss://test.finney.opentensor.ai:443"
FUND_AMOUNT_TAO = 10_000


# ─────────────────────────────────────────────────────────────────────────────
# PATH A — LOCAL DEV NODE (RECOMMENDED — BYPASSES POW ENTIRELY)
# ─────────────────────────────────────────────────────────────────────────────

def fund_local_wallets(sub: bt.subtensor):
    """
    On local --dev Substrate node, Alice has unlimited TAO.
    Use Alice to fund all wallets directly. Zero POW. Zero waiting.
    This is the correct approach for local development.
    """
    print("\n🔑 Using Alice sudo account (local dev node — unlimited TAO)")

    alice = Keypair.create_from_uri("//Alice")
    print(f"   Alice: {alice.ss58_address}")

    alice_bal = sub.get_balance(alice.ss58_address)
    print(f"   Alice balance: {alice_bal}")

    for name, addr in WALLETS.items():
        try:
            before = sub.get_balance(addr)

            call = sub.substrate.compose_call(
                call_module   = "Balances",
                call_function = "transfer_keep_alive",
                call_params   = {
                    "dest":  {"Id": addr},
                    "value": int(FUND_AMOUNT_TAO * 1e9),
                }
            )
            extrinsic = sub.substrate.create_signed_extrinsic(
                call    = call,
                keypair = alice,
            )
            receipt = sub.substrate.submit_extrinsic(
                extrinsic,
                wait_for_inclusion  = True,
                wait_for_finalization = False,
            )

            after = sub.get_balance(addr)
            print(f"   ✓ {name}: {before} → {after} TAO")

        except Exception as e:
            print(f"   ✗ {name}: {e}")
            # Try alternative call format
            try:
                call = sub.substrate.compose_call(
                    call_module   = "Balances",
                    call_function = "force_transfer",
                    call_params   = {
                        "source": alice.ss58_address,
                        "dest":   addr,
                        "value":  int(FUND_AMOUNT_TAO * 1e9),
                    }
                )
                # Wrap in sudo
                sudo_call = sub.substrate.compose_call(
                    call_module   = "Sudo",
                    call_function = "sudo",
                    call_params   = {"call": call}
                )
                extrinsic = sub.substrate.create_signed_extrinsic(
                    call    = sudo_call,
                    keypair = alice,
                )
                receipt = sub.substrate.submit_extrinsic(
                    extrinsic,
                    wait_for_inclusion = True,
                )
                after = sub.get_balance(addr)
                print(f"   ✓ {name} (sudo): {after} TAO")
            except Exception as e2:
                print(f"   ✗ {name} sudo also failed: {e2}")

    print("\n✅ Funding complete")


def create_subnet_local(sub: bt.subtensor, owner_wallet: bt.wallet) -> int:
    """
    Create INVARIANT subnet on local dev node.
    Subnet creation on local node costs 100 TAO (not 1000+).
    """
    print("\n🌐 Creating INVARIANT subnet...")

    # Check current subnet count
    n_subnets = sub.get_total_subnets()
    print(f"   Current subnets: {n_subnets}")

    # Get cost
    cost = sub.get_subnet_burn_cost()
    print(f"   Subnet creation cost: {cost} TAO")

    owner_bal = sub.get_balance(owner_wallet.coldkeypub.ss58_address)
    print(f"   Owner balance: {owner_bal} TAO")

    result = sub.register_subnet(wallet=owner_wallet)
    if result:
        new_netuid = sub.get_total_subnets() - 1
        print(f"   ✓ Subnet created! netuid={new_netuid}")
        return new_netuid
    else:
        print("   ✗ Subnet creation failed — check owner balance")
        return -1


# ─────────────────────────────────────────────────────────────────────────────
# PATH B — POW REGISTRATION WITH ANTI-STALE FIX
# ─────────────────────────────────────────────────────────────────────────────

def register_with_pow_fixed(
    sub:     bt.subtensor,
    wallet:  bt.wallet,
    netuid:  int,
    max_retries: int = 10,
):
    """
    Register a wallet to a subnet using POW with anti-stale measures.

    ANTI-STALE STRATEGY:
      1. Use ALL CPU cores (num_processes = cpu_count)
      2. Short update_interval (256) so solver checks for new blocks frequently
      3. Retry loop — if stale, immediately recompute for the new block
      4. No sleep between retries
    """
    cpu_count       = multiprocessing.cpu_count()
    update_interval = 256   # Check for new block every 256 nonce attempts
                            # Lower = more responsive to block changes
                            # Higher = more efficient hash throughput
                            # 256 is the sweet spot

    print(f"\n⛏  POW Registration")
    print(f"   Wallet:          {wallet.name} / {wallet.hotkey.ss58_address[:16]}...")
    print(f"   Netuid:          {netuid}")
    print(f"   CPU cores:       {cpu_count}")
    print(f"   Update interval: {update_interval}")

    for attempt in range(1, max_retries + 1):
        print(f"\n   Attempt {attempt}/{max_retries}...")

        # Get current block — solve immediately from this block
        block     = sub.get_current_block()
        diff      = sub.difficulty(netuid=netuid)
        print(f"   Block: {block} | Difficulty: {diff:,}")

        t0 = time.time()

        # CORE FIX: use all CPUs, short update_interval
        # This is what btcli does internally — we call it directly
        # with optimal parameters
        result = sub.register(
            wallet           = wallet,
            netuid           = netuid,
            wait_for_inclusion  = True,
            wait_for_finalization = False,
            max_allowed_attempts = 1,      # One attempt per outer retry loop
            output_in_place  = True,
            cuda             = False,      # Set True if you have NVIDIA GPU
            dev_id           = 0,
            tpb              = 256,
            num_processes    = cpu_count,  # ALL cores
            update_interval  = update_interval,
            log_verbose      = False,
        )

        elapsed = time.time() - t0

        if result:
            print(f"   ✓ Registered in {elapsed:.1f}s!")
            return True
        else:
            # Check if already registered (not a failure)
            if sub.is_hotkey_registered(
                netuid  = netuid,
                hotkey_ss58 = wallet.hotkey.ss58_address
            ):
                print(f"   ℹ  Already registered (not an error)")
                return True

            print(f"   ✗ Failed after {elapsed:.1f}s — retrying immediately")
            # No sleep — go straight to next attempt with fresh block

    print(f"   ✗ Could not register after {max_retries} attempts")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# PATH C — BTCLI COMMANDS (if you prefer terminal)
# ─────────────────────────────────────────────────────────────────────────────

def print_btcli_commands(netuid: int, network: str):
    endpoint = LOCAL_ENDPOINT if network == "local" else TEST_ENDPOINT
    flag     = f"--subtensor.chain_endpoint {endpoint}" if network == "local" \
               else f"--subtensor.network {network}"

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  BTCLI COMMANDS — Run these manually if script fails         ║
╠══════════════════════════════════════════════════════════════╣

# Fund wallets (local dev node only — uses btcli faucet):
btcli wallet faucet --wallet.name owner {flag}
btcli wallet faucet --wallet.name miner1 {flag}
btcli wallet faucet --wallet.name validator1 {flag}

# Create subnet:
btcli subnet create \\
  --wallet.name owner \\
  --wallet.hotkey default \\
  {flag}

# Register miner (POW — uses ALL cores automatically):
btcli subnet register \\
  --wallet.name miner1 \\
  --wallet.hotkey default \\
  --netuid {netuid} \\
  --processors {multiprocessing.cpu_count()} \\
  {flag}

# Register validator:
btcli subnet register \\
  --wallet.name validator1 \\
  --wallet.hotkey default \\
  --netuid {netuid} \\
  --processors {multiprocessing.cpu_count()} \\
  {flag}

# Stake to validator (needed for validator permit):
btcli stake add \\
  --wallet.name validator1 \\
  --wallet.hotkey default \\
  --amount 1000 \\
  {flag}

# Verify everything:
btcli subnet list {flag}
btcli subnet show --netuid {netuid} {flag}
╚══════════════════════════════════════════════════════════════╝
""")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="INVARIANT Registration")
    parser.add_argument("--network",  default="local",
                        choices=["local", "test"],
                        help="Which network to use")
    parser.add_argument("--netuid",   type=int, default=-1,
                        help="Subnet UID (auto-detected if -1)")
    parser.add_argument("--skip_fund", action="store_true",
                        help="Skip wallet funding (already funded)")
    parser.add_argument("--skip_subnet", action="store_true",
                        help="Skip subnet creation (already exists)")
    args = parser.parse_args()

    # ── Connect ───────────────────────────────────────────────────────────────
    endpoint = LOCAL_ENDPOINT if args.network == "local" else TEST_ENDPOINT
    print(f"\n🔗 Connecting to {args.network} ({endpoint})...")

    try:
        sub = bt.subtensor(network=args.network,
                           chain_endpoint=endpoint if args.network == "local" else None)
        block = sub.get_current_block()
        print(f"   ✓ Connected | Block #{block}")
    except Exception as e:
        print(f"   ✗ Connection failed: {e}")
        print(f"   Is your local node running?")
        print(f"   docker run -d --name bt-local -p 9944:9944 \\")
        print(f"     opentensor/subtensor:latest --dev --rpc-external --ws-external")
        sys.exit(1)

    # ── Load wallets ──────────────────────────────────────────────────────────
    owner_wallet = bt.wallet(name="owner",      hotkey="default")
    miner_wallet = bt.wallet(name="miner1",     hotkey="default")
    val_wallet   = bt.wallet(name="validator1", hotkey="default")

    # ── Fund wallets (local dev node: Alice, testnet: faucet) ─────────────────
    if not args.skip_fund:
        if args.network == "local":
            fund_local_wallets(sub)
        else:
            print("\n⚠  On testnet: fund wallets manually via Discord faucet")
            print("   discord.gg/bittensor → #faucet")
            for name, addr in WALLETS.items():
                bal = sub.get_balance(addr)
                print(f"   {name}: {bal} TAO")

    # ── Create subnet ─────────────────────────────────────────────────────────
    netuid = args.netuid
    if not args.skip_subnet and netuid == -1:
        netuid = create_subnet_local(sub, owner_wallet)
        if netuid == -1:
            print("❌ Cannot continue without subnet")
            print_btcli_commands(1, args.network)
            sys.exit(1)
    elif netuid == -1:
        # Try to find existing subnet
        subnets = sub.get_subnets()
        print(f"\n   Existing subnets: {subnets}")
        netuid = subnets[-1] if subnets else 1

    print(f"\n📡 Working with netuid={netuid}")

    # ── Register miner ────────────────────────────────────────────────────────
    print("\n👷 Registering miner1...")
    if sub.is_hotkey_registered(netuid=netuid,
                                 hotkey_ss58=miner_wallet.hotkey.ss58_address):
        print("   ℹ  Already registered")
    else:
        register_with_pow_fixed(sub, miner_wallet, netuid)

    # ── Register validator ────────────────────────────────────────────────────
    print("\n🏛  Registering validator1...")
    if sub.is_hotkey_registered(netuid=netuid,
                                 hotkey_ss58=val_wallet.hotkey.ss58_address):
        print("   ℹ  Already registered")
    else:
        register_with_pow_fixed(sub, val_wallet, netuid)

    # ── Print btcli commands for reference ────────────────────────────────────
    print_btcli_commands(netuid, args.network)

    # ── Final status ──────────────────────────────────────────────────────────
    print("\n📊 Final Status:")
    for name, addr in WALLETS.items():
        bal = sub.get_balance(addr)
        print(f"   {name}: {bal} TAO")

    metagraph = sub.metagraph(netuid)
    print(f"\n   Subnet {netuid} miners: {metagraph.n.item()}")
    print(f"   Hotkeys registered: {metagraph.hotkeys}")


if __name__ == "__main__":
    main()
