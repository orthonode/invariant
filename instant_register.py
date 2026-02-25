#!/usr/bin/env python3
"""
INVARIANT — Instant Local Registration
=======================================
One-shot setup: creates wallets, funds them, creates subnet, registers
neurons, and sets serving_rate_limit=0 so the miner can announce its axon.

No POW. No waiting. Uses Alice (dev sudo). Done in ~30 seconds.

Usage:
    python instant_register.py

Run ONCE after starting the local node with ./start_local.sh --node-only
"""

import sys
import time
from pathlib import Path

print("Loading dependencies...")
import bittensor as bt
from substrateinterface import Keypair, SubstrateInterface

ENDPOINT = "ws://127.0.0.1:9944"
NETUID   = 1

# Alice's known dev coldkeys (pre-funded in --dev genesis)
COLDKEYS = {
    "owner":      "5DaFrQjhPKy4LQQ4WXhWspzZhjViMQgPNE3kuTzoHgtWMPgb",
    "miner1":     "5CJyjX24nbwKyQSLCMJrYkNJdyo3qp3ebekhvVQPdDXfGnuS",
    "validator1": "5G6JzqK9Si47gLQxWrT2RitAUYz7hw7RzcHX6ZMSTwWphE6f",
}

OR = "\033[38;5;208m"; GR = "\033[32m"; RE = "\033[31m"
YE = "\033[33m";       DI = "\033[2m";  RS = "\033[0m"; BO = "\033[1m"

def ok(msg):   print(f"   {GR}✓{RS} {msg}")
def warn(msg): print(f"   {YE}⚠ {RS} {msg}")
def err(msg):  print(f"   {RE}✗{RS} {msg}")


# ── Substrate helpers ────────────────────────────────────────────────────────

def submit(substrate, keypair, call, label=""):
    try:
        ext = substrate.create_signed_extrinsic(call=call, keypair=keypair)
        r   = substrate.submit_extrinsic(ext, wait_for_inclusion=True)
        if r.is_success:
            ok(label)
            return True
        err(f"{label}: {r.error_message}")
        return False
    except Exception as e:
        err(f"{label}: {e}")
        return False


def sudo(substrate, alice, module, fn, params, label=""):
    inner = substrate.compose_call(module, fn, params)
    outer = substrate.compose_call("Sudo", "sudo", {"call": inner})
    return submit(substrate, alice, outer, label)


def fund(substrate, alice, bt_sub, dest_addr, name, amount=10_000):
    try:
        bal = float(str(bt_sub.get_balance(dest_addr)).replace("τ", "").strip())
        if bal >= 1_000:
            ok(f"{name}: already funded ({bal:.0f} τ) — skip")
            return True
    except Exception:
        pass
    call = substrate.compose_call(
        "Balances", "transfer_keep_alive",
        {"dest": dest_addr, "value": int(amount * 1e9)},
    )
    return submit(substrate, alice, call, f"Funded {name} ({amount:,} τ)")


# ── Wallet creation ──────────────────────────────────────────────────────────

def ensure_wallet(name: str, hotkey: str = "default") -> bt.Wallet:
    """Create wallet files if they don't exist. Never overwrites existing keys."""
    w = bt.Wallet(name=name, hotkey=hotkey)
    created_cold = False
    created_hot  = False

    if not Path(w.coldkey_file.path).exists():
        w.create_new_coldkey(n_words=12, use_password=False, overwrite=False)
        created_cold = True

    if not Path(w.hotkey_file.path).exists():
        w.create_new_hotkey(n_words=12, use_password=False, overwrite=False)
        created_hot = True

    if created_cold or created_hot:
        ok(f"Wallet '{name}': created {'coldkey ' if created_cold else ''}"
           f"{'hotkey' if created_hot else ''}".strip())
    else:
        ok(f"Wallet '{name}': already exists")

    return w


# ── Main ─────────────────────────────────────────────────────────────────────

print()
print(OR + BO + "═" * 56 + RS)
print(OR + BO + "  INVARIANT — Instant Local Setup (No POW)" + RS)
print(OR + BO + "═" * 56 + RS)

# ── Step 1: Connect ──────────────────────────────────────────────────────────
print(f"\n{BO}[1/6] Connecting to {ENDPOINT}...{RS}")
try:
    substrate = SubstrateInterface(
        url=ENDPOINT,
        type_registry_preset="substrate-node-template",
    )
    config = bt.Config()
    config.subtensor.chain_endpoint = ENDPOINT
    config.subtensor.network = "local"
    bt_sub = bt.Subtensor(config=config)
    ok(f"Connected — block #{substrate.get_block_number(None)}")
except Exception as e:
    err(str(e))
    print(f"\n  {YE}Is the local node running?{RS}")
    print(f"  {DI}  ./start_local.sh --node-only{RS}")
    sys.exit(1)

alice = Keypair.create_from_uri("//Alice")
ok(f"Alice (sudo): {alice.ss58_address}")

# ── Step 2: Create wallets ───────────────────────────────────────────────────
print(f"\n{BO}[2/6] Creating wallets (skip if already exist)...{RS}")
wallets = {}
for name in ["owner", "miner1", "validator1"]:
    wallets[name] = ensure_wallet(name)

# ── Step 3: Fund coldkeys ────────────────────────────────────────────────────
print(f"\n{BO}[3/6] Funding coldkeys (10,000 τ each)...{RS}")
for name, addr in COLDKEYS.items():
    fund(substrate, alice, bt_sub, addr, name)

# ── Step 4: Create subnet ────────────────────────────────────────────────────
print(f"\n{BO}[4/6] Ensuring subnet {NETUID} exists...{RS}")
try:
    if bt_sub.subnet_exists(netuid=NETUID):
        ok(f"Subnet {NETUID} already exists")
    else:
        owner_wallet = wallets["owner"]
        result = bt_sub.register_subnet(
            wallet=owner_wallet,
            prompt=False,
        )
        if result:
            ok(f"Subnet {NETUID} created")
        else:
            warn("Subnet creation returned False — may already exist")
except Exception as e:
    warn(f"Subnet check/create: {e}")

# ── Step 5: Register neurons ─────────────────────────────────────────────────
print(f"\n{BO}[5/6] Registering neurons on subnet {NETUID}...{RS}")
for wallet_name in ["miner1", "validator1"]:
    w  = wallets[wallet_name]
    hk = w.hotkey.ss58_address
    try:
        if bt_sub.is_hotkey_registered_on_subnet(hotkey_ss58=hk, netuid=NETUID):
            ok(f"{wallet_name}: already registered on subnet {NETUID}")
            continue
    except Exception:
        pass

    try:
        registered = bt_sub.burned_register(wallet=w, netuid=NETUID)
        if registered:
            ok(f"{wallet_name}: registered via burned_register")
        else:
            err(f"{wallet_name}: burned_register returned False")
    except Exception as e:
        err(f"{wallet_name}: {e}")

# ── Step 6: Set serving_rate_limit = 0 ──────────────────────────────────────
print(f"\n{BO}[6/6] Setting serving_rate_limit = 0 (axon IP updates unrestricted)...{RS}")
sudo(
    substrate, alice,
    "AdminUtils", "sudo_set_serving_rate_limit",
    {"netuid": NETUID, "serving_rate_limit": 0},
    f"serving_rate_limit → 0 on subnet {NETUID}",
)

# ── Status summary ───────────────────────────────────────────────────────────
print()
print(OR + BO + "═" * 56 + RS)
print(OR + BO + "  STATUS" + RS)
print(OR + BO + "═" * 56 + RS)

for name, addr in COLDKEYS.items():
    try:
        bal = bt_sub.get_balance(addr)
        print(f"  {name:<12} {bal}")
    except Exception:
        print(f"  {name:<12} (balance unavailable)")

print()
try:
    mg = bt_sub.metagraph(NETUID)
    print(f"  Subnet {NETUID}: {mg.n.item()} neurons")
    for i, hk in enumerate(mg.hotkeys):
        print(f"    [{i}] {hk[:28]}...")
except Exception as e:
    print(f"  Metagraph: {e}")

print()
print(OR + BO + "═" * 56 + RS)
print(GR + BO + "  ✅  Setup complete — start miner and validator:" + RS)
print(OR + BO + "═" * 56 + RS)
print(f"""
  {BO}Terminal 1 — Miner:{RS}
  {DI}source venv/bin/activate{RS}
  python miner.py \\
      --wallet.name miner1 --wallet.hotkey default \\
      --netuid {NETUID} --subtensor.network local \\
      --axon.port 8091
  {DI}(LAN IP auto-detected — no --axon.external_ip needed){RS}

  {BO}Terminal 2 — Validator:{RS}
  {DI}source venv/bin/activate{RS}
  python validator.py \\
      --wallet.name validator1 --wallet.hotkey default \\
      --netuid {NETUID} --subtensor.network local

  {BO}Or run the full test suite:{RS}
  python run_tests.py --all
""")
