#!/usr/bin/env python3
"""
INVARIANT Wallet Setup Script
=============================
Create and fund wallets for testnet deployment.

Usage:
    python scripts/setup_wallets.py --network test
"""

import argparse
import json
import sys
from pathlib import Path

import bittensor as bt


def setup_wallets(network: str = "test"):
    """Setup and fund INVARIANT wallets."""
    print(f"🔧 Setting up wallets for {network} network")
    
    subtensor = bt.Subtensor(network=network)
    wallets = {}
    
    # Create wallets
    wallet_configs = [
        ("owner", "Subnet owner and faucet"),
        ("miner1", "First test miner"),
        ("validator1", "First test validator"),
    ]
    
    for name, description in wallet_configs:
        print(f"\n📝 Creating {name}: {description}")
        
        try:
            wallet = bt.Wallet(name=name, hotkey="default")
            
            # Create coldkey if needed
            if not wallet.coldkeypub_file.exists_on_device():
                wallet.create_new_coldkey(use_password=False, overwrite=True)
                print(f"  ✅ Created coldkey")
            else:
                print(f"  ✅ Coldkey exists")
            
            # Create hotkey if needed
            if not wallet.hotkey_file.exists_on_device():
                wallet.create_new_hotkey(use_password=False, overwrite=True)
                print(f"  ✅ Created hotkey")
            else:
                print(f"  ✅ Hotkey exists")
            
            wallets[name] = wallet
            print(f"  📋 Coldkey: {wallet.coldkeypub.ss58_address}")
            print(f"  🔑 Hotkey: {wallet.hotkey.ss58_address}")
            
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            return None
    
    # Fund wallets on testnet
    if network == "test":
        print(f"\n🚰 Funding wallets on testnet...")
        
        for name, wallet in wallets.items():
            if name in ["owner", "validator1"]:  # Fund key wallets
                try:
                    balance = float(subtensor.get_balance(wallet.coldkeypub.ss58_address))
                    print(f"  💰 {name} balance: {balance:.8f} TAO")
                    
                    if balance < 100:  # Fund if low balance
                        result = subtensor.faucet(wallet=wallet, wait_for_inclusion=True)
                        print(f"  ✅ Funded {name}: {result}")
                    else:
                        print(f"  ✅ {name} already funded")
                        
                except Exception as e:
                    print(f"  ❌ Failed to fund {name}: {e}")
    
    # Save wallet info
    wallet_info = {}
    for name, wallet in wallets.items():
        wallet_info[name] = {
            "coldkey": wallet.coldkeypub.ss58_address,
            "hotkey": wallet.hotkey.ss58_address,
        }
    
    output_file = Path(f"wallets_{network}.json")
    with open(output_file, 'w') as f:
        json.dump(wallet_info, f, indent=2)
    
    print(f"\n💾 Wallet info saved to {output_file}")
    return wallets


def check_balances(network: str = "test"):
    """Check wallet balances."""
    print(f"💰 Checking balances on {network} network")
    
    try:
        with open(f"wallets_{network}.json") as f:
            wallet_info = json.load(f)
    except FileNotFoundError:
        print(f"❌ Wallet file not found: wallets_{network}.json")
        return
    
    subtensor = bt.Subtensor(network=network)
    
    for name, info in wallet_info.items():
        try:
            wallet = bt.Wallet(name=name, hotkey="default")
            balance = float(subtensor.get_balance(wallet.coldkeypub.ss58_address))
            print(f"  {name}: {balance:.8f} TAO")
        except Exception as e:
            print(f"  {name}: Error - {e}")


def main():
    parser = argparse.ArgumentParser(description="Setup INVARIANT wallets")
    parser.add_argument("--network", type=str, default="test", help="Network (test/finney)")
    parser.add_argument("--check", action="store_true", help="Check balances only")
    
    args = parser.parse_args()
    
    if args.check:
        check_balances(args.network)
    else:
        setup_wallets(args.network)


if __name__ == "__main__":
    main()
