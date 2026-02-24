#!/usr/bin/env python3
"""
INVARIANT — Local Node Fast Registration (NO POW)
==================================================
For local --dev nodes ONLY.

On a local Substrate --dev node:
  - Alice account has unlimited TAO
  - Sudo can bypass POW entirely using force_register
  - Blocks are 2-3 seconds — POW almost always goes stale anyway

This script bypasses POW entirely and gets you registered in seconds.

Run: python fast_register_local.py
"""

import time
import sys
from substrateinterface import Keypair, SubstrateInterface
import bittensor as bt

ENDPOINT = "ws://127.0.0.1:9944"

WALLETS = {
    "owner":      "5DaFrQjhPKy4LQQ4WXhWspzZhjViMQgPNE3kuTzoHgtWMPgb",
    "miner1":     "5CJyjX24nbwKyQSLCMJrYkNJdyo3qp3ebekhvVQPdDXfGnuS",
    "validator1": "5G6JzqK9Si47gLQxWrT2RitAUYz7hw7RzcHX6ZMSTwWphE6f",
}

FUND_RAO = 10_000 * 10**9   # 10,000 TAO in rao


def connect():
    print(f"🔗 Connecting to {ENDPOINT}...")
    try:
        substrate = SubstrateInterface(url=ENDPOINT)
        config = bt.Config()
        config.subtensor.chain_endpoint = ENDPOINT
        config.subtensor.network = "local"
        bt_sub    = bt.Subtensor(config=config)
        print(f"   ✓ Block #{substrate.get_block_number(None)}")
        return substrate, bt_sub
    except Exception as e:
        print(f"   ✗ {e}")
        print("   Start your local node:")
        print("   docker run -d --name bt-local -p 9944:9944 \\")
        print("     opentensor/subtensor:latest --dev --rpc-external --ws-external")
        sys.exit(1)


def sudo_transfer(substrate: SubstrateInterface, alice: Keypair, dest: str, amount_rao: int):
    """Transfer TAO from Alice to dest on local dev node."""
    try:
        call = substrate.compose_call(
            call_module   = "Balances",
            call_function = "transfer_keep_alive",
            call_params   = {"dest": dest, "value": amount_rao}
        )
        extrinsic = substrate.create_signed_extrinsic(call=call, keypair=alice)
        receipt   = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
        return receipt.is_success
    except Exception as e:
        # Try with MultiAddress format
        try:
            call = substrate.compose_call(
                call_module   = "Balances",
                call_function = "transfer_keep_alive",
                call_params   = {"dest": {"Id": dest}, "value": amount_rao}
            )
            extrinsic = substrate.create_signed_extrinsic(call=call, keypair=alice)
            receipt   = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
            return receipt.is_success
        except Exception as e2:
            print(f"      Transfer error: {e2}")
            return False


def force_register_hotkey(substrate: SubstrateInterface, alice: Keypair,
                           netuid: int, hotkey_ss58: str, coldkey_ss58: str):
    """
    Use sudo to register a hotkey without POW.
    This uses the SubtensorModule::sudo_register extrinsic.
    Only works on --dev nodes where Alice is sudo.
    """
    try:
        # Method 1: sudo_register (if available in this subtensor version)
        inner_call = substrate.compose_call(
            call_module   = "SubtensorModule",
            call_function = "sudo_register",
            call_params   = {
                "netuid":         netuid,
                "hotkey":         hotkey_ss58,
                "coldkey":        coldkey_ss58,
                "balance_to_add": 1 * 10**9,   # 1 TAO stake
            }
        )
        sudo_call = substrate.compose_call(
            call_module   = "Sudo",
            call_function = "sudo",
            call_params   = {"call": inner_call}
        )
        extrinsic = substrate.create_signed_extrinsic(call=sudo_call, keypair=alice)
        receipt   = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
        if receipt.is_success:
            return True

    except Exception as e:
        pass  # Try method 2

    try:
        # Method 2: forced_register (newer subtensor versions)
        inner_call = substrate.compose_call(
            call_module   = "SubtensorModule",
            call_function = "forced_register",
            call_params   = {
                "netuid":  netuid,
                "hotkey":  hotkey_ss58,
                "coldkey": coldkey_ss58,
            }
        )
        sudo_call = substrate.compose_call(
            call_module   = "Sudo",
            call_function = "sudo",
            call_params   = {"call": inner_call}
        )
        extrinsic = substrate.create_signed_extrinsic(call=sudo_call, keypair=alice)
        receipt   = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
        return receipt.is_success

    except Exception as e:
        return False


def main():
    substrate, bt_sub = connect()

    # Alice — the local dev sudo account
    alice = Keypair.create_from_uri("//Alice")
    print(f"\n👑 Alice: {alice.ss58_address}")

    # ── STEP 1: Fund all wallets ──────────────────────────────────────────────
    print("\n💰 STEP 1: Funding wallets...")
    for name, addr in WALLETS.items():
        before = bt_sub.get_balance(addr)
        # Handle Balance object - it might already be a float or have __float__ method
        try:
            before_balance = float(before)
        except (ValueError, TypeError):
            # If it's a string with τ prefix, clean it
            before_str = str(before).replace(" τ", "").replace(",", "")
            before_balance = float(before_str)
        
        if before_balance >= 1000:
            print(f"   ✓ {name}: already has {before} (skipping)")
            continue

        ok = sudo_transfer(substrate, alice, addr, FUND_RAO)
        after = bt_sub.get_balance(addr)
        status = "✓" if ok else "~"
        print(f"   {status} {name}: → {after}")

    # ── STEP 2: Create subnet ─────────────────────────────────────────────────
    print("\n🌐 STEP 2: Creating INVARIANT subnet...")

    # Load owner wallet (needs to be on disk)
    try:
        owner_wallet = bt.Wallet(name="owner", hotkey="default")
        # Check if key exists
        _ = owner_wallet.coldkeypub.ss58_address
    except Exception:
        print("   ⚠  Owner wallet not found on disk.")
        print("   Create it: btcli wallet new_coldkey --wallet.name owner")
        print("   Then import the coldkey for address:", WALLETS["owner"])
        owner_wallet = None

    netuid = -1

    if owner_wallet:
        total_subnets = bt_sub.get_total_subnets()
        print(f"   Total subnets: {total_subnets}")

        if total_subnets > 1:  # subnet 0 is root
            netuid = 1  # Use netuid 1 for our subnet
            print(f"   ℹ  Using netuid={netuid}")
        else:
            cost = bt_sub.get_subnet_burn_cost()
            print(f"   Subnet cost: {cost} TAO")
            result = bt_sub.register_subnet(wallet=owner_wallet)
            if result:
                time.sleep(3)  # Wait for block
                netuid = bt_sub.get_total_subnets() - 1
                print(f"   ✓ Subnet created! netuid={netuid}")
            else:
                print("   ✗ Subnet creation failed")
                netuid = 1  # Use default

    if netuid == -1:
        netuid = 1
        print(f"   Using netuid={netuid}")

    # ── STEP 3: Register miners/validators (no POW) ───────────────────────────
    print(f"\n⛏  STEP 3: Registering neurons on subnet {netuid} (NO POW)...")

    # Try sudo registration first (fastest, no POW)
    neurons = {
        "miner1":     (WALLETS["miner1"],     WALLETS["owner"]),
        "validator1": (WALLETS["validator1"], WALLETS["owner"]),
    }

    for name, (hotkey, coldkey) in neurons.items():
        # Check if already registered
        if bt_sub.is_hotkey_registered(netuid=netuid, hotkey_ss58=hotkey):
            print(f"   ✓ {name}: already registered")
            continue

        print(f"   Registering {name}...")

        # Try sudo force register (no POW)
        ok = force_register_hotkey(substrate, alice, netuid, hotkey, coldkey)

        if ok:
            print(f"   ✓ {name}: registered via sudo (no POW!)")
        else:
            print(f"   ✗ {name}: sudo failed — falling back to POW registration")
            print(f"      Run: btcli subnet register --wallet.name {name} --wallet.hotkey default --netuid {netuid} --subtensor.chain_endpoint {ENDPOINT} --processors {__import__('multiprocessing').cpu_count()}")

    # ── STEP 4: Verify ───────────────────────────────────────────────────────
    print(f"\n📊 STEP 4: Verification...")
    time.sleep(3)

    try:
        metagraph = bt_sub.metagraph(netuid)
        print(f"   Subnet {netuid} — {metagraph.n.item()} neurons registered")
        for i, hk in enumerate(metagraph.hotkeys):
            stake = metagraph.S[i].item()
            print(f"   [{i}] {hk[:20]}... stake={stake:.2f}")
    except Exception as e:
        print(f"   Metagraph error: {e}")

    for name, addr in WALLETS.items():
        bal = bt_sub.get_balance(addr)
        print(f"   {name}: {bal}")

    print(f"""
╔══════════════════════════════════════════════════════╗
║  ✅ INVARIANT Local Setup Complete                   ║
╠══════════════════════════════════════════════════════╣
║  netuid:   {netuid}                                      ║
║  endpoint: {ENDPOINT}               ║
╠══════════════════════════════════════════════════════╣
║  START MINER:                                        ║
║  python neurons/miner.py \\                           ║
║    --wallet.name miner1 \\                            ║
║    --wallet.hotkey default \\                         ║
║    --netuid {netuid} \\                                   ║
║    --subtensor.network local \\                       ║
║    --subtensor.chain_endpoint {ENDPOINT}  ║
║                                                      ║
║  START VALIDATOR:                                    ║
║  python neurons/validator.py \\                       ║
║    --wallet.name validator1 \\                        ║
║    --wallet.hotkey default \\                         ║
║    --netuid {netuid} \\                                   ║
║    --subtensor.network local \\                       ║
║    --subtensor.chain_endpoint {ENDPOINT}  ║
╚══════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
