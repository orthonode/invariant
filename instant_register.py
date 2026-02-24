#!/usr/bin/env python3
"""
INVARIANT — Instant Local Registration
No POW. No waiting. Uses Alice sudo. Done in 10 seconds.
"""

import time
import sys

print("Loading dependencies...")
from substrateinterface import Keypair, SubstrateInterface
import bittensor as bt

ENDPOINT  = "ws://127.0.0.1:9944"
NETUID    = 1

COLDKEYS = {
    "owner":      "5DaFrQjhPKy4LQQ4WXhWspzZhjViMQgPNE3kuTzoHgtWMPgb",
    "miner1":     "5CJyjX24nbwKyQSLCMJrYkNJdyo3qp3ebekhvVQPdDXfGnuS",
    "validator1": "5G6JzqK9Si47gLQxWrT2RitAUYz7hw7RzcHX6ZMSTwWphE6f",
}

# Hotkeys — these must be the actual hotkey addresses from your wallet files
# Run: btcli wallet overview --wallet.name miner1
# and paste the hotkey ss58 address here
HOTKEYS = {
    "miner1":     None,   # fill in after running btcli wallet overview
    "validator1": None,
}

# ─────────────────────────────────────────────────────────────────────────────

def submit(substrate, alice, call, label=""):
    """Sign with Alice and submit, wait for inclusion."""
    try:
        ext = substrate.create_signed_extrinsic(call=call, keypair=alice)
        r   = substrate.submit_extrinsic(ext, wait_for_inclusion=True)
        if r.is_success:
            print(f"   ✓ {label}")
            return True
        else:
            print(f"   ✗ {label}: {r.error_message}")
            return False
    except Exception as e:
        print(f"   ✗ {label}: {e}")
        return False


def fund(substrate, alice, dest, amount_tao, name):
    """Send TAO from Alice to dest."""
    call = substrate.compose_call(
        call_module   = "Balances",
        call_function = "transfer_keep_alive",
        call_params   = {"dest": dest, "value": int(amount_tao * 1e9)},
    )
    return submit(substrate, alice, call, f"Funded {name} ({amount_tao} TAO)")


def sudo_call(substrate, alice, module, function, params, label=""):
    """Wrap a call in sudo and submit with Alice."""
    inner = substrate.compose_call(
        call_module   = module,
        call_function = function,
        call_params   = params,
    )
    outer = substrate.compose_call(
        call_module   = "Sudo",
        call_function = "sudo",
        call_params   = {"call": inner},
    )
    return submit(substrate, alice, outer, label)


def get_hotkey(wallet_name):
    """Load hotkey ss58 from wallet file on disk."""
    try:
        w = bt.Wallet(name=wallet_name, hotkey="default")
        return w.hotkey.ss58_address
    except Exception as e:
        print(f"   ✗ Could not load {wallet_name} hotkey: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "═"*55)
print("  INVARIANT — Instant Local Registration (No POW)")
print("═"*55)

# ── 1. Connect ────────────────────────────────────────────────────────────────
print(f"\n[1/5] Connecting to {ENDPOINT}...")
try:
    substrate = SubstrateInterface(url=ENDPOINT, type_registry_preset="substrate-node-template")
    config = bt.Config()
    config.subtensor.chain_endpoint = ENDPOINT
    config.subtensor.network = "local"
    bt_sub    = bt.Subtensor(config=config)
    print(f"      Block #{substrate.get_block_number(None)} ✓")
except Exception as e:
    print(f"      ✗ {e}")
    print("\n      Is your local node running? Check with:")
    print("      docker ps | grep subtensor")
    print("      OR look at the terminal running the node — it should show blocks scrolling")
    sys.exit(1)

# ── 2. Alice ─────────────────────────────────────────────────────────────────
print("\n[2/5] Loading Alice (dev sudo account)...")
alice = Keypair.create_from_uri("//Alice")
print(f"      Alice: {alice.ss58_address}")
try:
    alice_bal = bt_sub.get_balance(alice.ss58_address)
    print(f"      Balance: {alice_bal}")
except:
    print("      (balance check skipped)")

# ── 3. Fund all wallets ───────────────────────────────────────────────────────
print("\n[3/5] Funding wallets (10,000 TAO each from Alice)...")
for name, addr in COLDKEYS.items():
    try:
        bal_before = bt_sub.get_balance(addr)
        bal_float  = float(str(bal_before).replace("τ","").strip())
        if bal_float >= 1000:
            print(f"   ✓ {name}: already has {bal_before} (skip)")
            continue
    except:
        pass
    fund(substrate, alice, addr, 10_000, name)

# ── 4. Load hotkeys from wallet files ─────────────────────────────────────────
print("\n[4/5] Loading hotkeys from wallet files...")
for wname in ["miner1", "validator1"]:
    hk = get_hotkey(wname)
    if hk:
        HOTKEYS[wname] = hk
        print(f"   ✓ {wname}: {hk[:20]}...")
    else:
        # Fallback: use coldkey as hotkey (works for local testing)
        HOTKEYS[wname] = COLDKEYS[wname]
        print(f"   ⚠  {wname}: using coldkey as hotkey (create proper hotkey later)")

# ── 5. Register neurons via sudo (NO POW) ─────────────────────────────────────
print(f"\n[5/5] Registering on subnet {NETUID} via sudo (no POW)...")

for role, wallet_name in [("miner1", "miner1"), ("validator1", "validator1")]:
    hotkey  = HOTKEYS[wallet_name]
    coldkey = COLDKEYS[wallet_name]

    if not hotkey:
        print(f"   ✗ {wallet_name}: no hotkey — skip")
        continue

    # Check if already registered
    try:
        if bt_sub.is_hotkey_registered(netuid=NETUID, hotkey_ss58=hotkey):
            print(f"   ✓ {wallet_name}: already registered on subnet {NETUID}")
            continue
    except:
        pass

    # Try burned_register directly (uses TAO instead of POW - instant)
    print(f"   Trying burned_register for {wallet_name}...")
    try:
        w   = bt.Wallet(name=wallet_name, hotkey="default")
        ok  = bt_sub.burned_register(wallet=w, netuid=NETUID)
        if ok:
            print(f"   ✓ {wallet_name}: registered via burned_register")
            registered = True
        else:
            print(f"   ✗ {wallet_name}: burned_register failed")
            registered = False
    except Exception as e:
        print(f"   burned_register error: {e}")
        registered = False

    if not registered:
        print(f"""
   ══ MANUAL FALLBACK for {wallet_name} ══
   The sudo path isn't available in this subtensor version.
   Run this in a new terminal:

   btcli subnet register \\
     --wallet.name {wallet_name} \\
     --wallet.hotkey default \\
     --netuid {NETUID} \\
     --subtensor.chain_endpoint ws://127.0.0.1:9944 \\
     --no_prompt

   Note: If POW still stales, your local node is too fast.
   Solution: use 'burned_register' (costs TAO but no POW):
   The fast_register_local.py script handles this automatically.
""")

# ── Final check ───────────────────────────────────────────────────────────────
print("\n" + "═"*55)
print("  STATUS CHECK")
print("═"*55)

for name, addr in COLDKEYS.items():
    try:
        bal = bt_sub.get_balance(addr)
        print(f"  {name}: {bal}")
    except:
        print(f"  {name}: (balance check failed)")

print()
try:
    mg = bt_sub.metagraph(NETUID)
    print(f"  Subnet {NETUID}: {mg.n.item()} neurons")
    for i, hk in enumerate(mg.hotkeys):
        print(f"    [{i}] {hk[:24]}... S={mg.S[i].item():.2f}")
except Exception as e:
    print(f"  Metagraph: {e}")

print("""
  ════════════════════════════════════════════
  NEXT: Start miner and validator

  python neurons/miner.py \\
    --wallet.name miner1 \\
    --wallet.hotkey default \\
    --netuid 1 \\
    --subtensor.chain_endpoint ws://127.0.0.1:9944

  python neurons/validator.py \\
    --wallet.name validator1 \\
    --wallet.hotkey default \\
    --netuid 1 \\
    --subtensor.chain_endpoint ws://127.0.0.1:9944
  ════════════════════════════════════════════
""")
