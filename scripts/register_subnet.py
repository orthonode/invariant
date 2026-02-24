#!/usr/bin/env python3
"""
INVARIANT Subnet Registration Script
===================================
Register INVARIANT subnet on testnet/mainnet.

Usage:
    python scripts/register_subnet.py --netuid <NETUID> --wallet owner --network test
"""

import argparse
import json
import sys
from pathlib import Path

import bittensor as bt


def register_subnet(netuid: int, wallet_name: str, network: str = "test"):
    """Register INVARIANT subnet."""
    print(f"🏗️  Registering INVARIANT subnet (netuid: {netuid}) on {network}")
    
    try:
        # Load subnet parameters
        with open("SUBNET_PARAMS.json") as f:
            params = json.load(f)
        
        subnet_params = params["subnet_params"]
        print(f"📋 Subnet parameters: {subnet_params}")
        
        # Initialize components
        wallet = bt.Wallet(name=wallet_name, hotkey="default")
        subtensor = bt.Subtensor(network=network)
        
        print(f"👛 Using wallet: {wallet.coldkeypub.ss58_address}")
        
        # Check if subnet already exists
        if subtensor.subnet_exists(netuid):
            print(f"⚠️  Subnet {netuid} already exists")
            return False
        
        # Register subnet
        print("📝 Registering subnet...")
        result = subtensor.register_subnet(
            wallet=wallet,
            wait_for_inclusion=True,
            wait_for_finalization=True,
        )
        
        print(f"✅ Subnet registered: {result}")
        
        # Verify registration
        if subtensor.subnet_exists(netuid):
            subnet_info = subtensor.get_subnet_info(netuid)
            print(f"📊 Subnet info: {subnet_info}")
            return True
        else:
            print(f"❌ Subnet registration failed")
            return False
            
    except Exception as e:
        print(f"❌ Registration failed: {e}")
        return False


def register_entities(netuid: int, network: str = "test"):
    """Register miners and validators to subnet."""
    print(f"📝 Registering entities to subnet {netuid}")
    
    try:
        with open(f"wallets_{network}.json") as f:
            wallet_info = json.load(f)
    except FileNotFoundError:
        print(f"❌ Wallet file not found: wallets_{network}.json")
        return False
    
    subtensor = bt.Subtensor(network=network)
    
    # Register miners and validators
    entities = [
        ("miner1", "miner"),
        ("validator1", "validator"),
    ]
    
    for name, role in entities:
        try:
            wallet = bt.Wallet(name=name, hotkey="default")
            print(f"📝 Registering {role} {name}: {wallet.coldkeypub.ss58_address}")
            
            result = subtensor.register(
                wallet=wallet,
                netuid=netuid,
                wait_for_inclusion=True,
                wait_for_finalization=True,
            )
            
            print(f"✅ Registered {name}: {result}")
            
        except Exception as e:
            print(f"❌ Failed to register {name}: {e}")
    
    return True


def stake_validator(netuid: int, network: str = "test"):
    """Stake validator."""
    print(f"💰 Staking validator for subnet {netuid}")
    
    try:
        wallet = bt.Wallet(name="validator1", hotkey="default")
        subtensor = bt.Subtensor(network=network)
        
        print(f"👛 Validator wallet: {wallet.coldkeypub.ss58_address}")
        
        # Check balance
        balance = wallet.get_balance()
        print(f"💰 Balance: {balance:.8f} TAO")
        
        if balance < 1000:
            print(f"❌ Insufficient balance for staking (need 1000 TAO)")
            return False
        
        # Stake
        print("💰 Staking 1000 TAO...")
        result = subtensor.add_stake(
            wallet=wallet,
            netuid=netuid,
            amount=1000,
            wait_for_inclusion=True,
            wait_for_finalization=True,
        )
        
        print(f"✅ Staked: {result}")
        return True
        
    except Exception as e:
        print(f"❌ Staking failed: {e}")
        return False


def check_subnet(netuid: int, network: str = "test"):
    """Check subnet status."""
    print(f"📊 Checking subnet {netuid} on {network}")
    
    try:
        subtensor = bt.Subtensor(network=network)
        metagraph = bt.metagraph(netuid=netuid, network=network)
        metagraph.sync()
        
        subnet_info = subtensor.get_subnet_info(netuid)
        print(f"📊 Subnet info: {subnet_info}")
        
        print(f"📡 Total registered: {len(metagraph.neurons)}")
        
        miners = [n for n in metagraph.neurons if n.validator_trust < 0.5]
        validators = [n for n in metagraph.neurons if n.validator_trust > 0.5]
        
        print(f"⛏️  Miners: {len(miners)}")
        print(f"🔍 Validators: {len(validators)}")
        
        total_stake = sum(n.stake for n in metagraph.neurons)
        print(f"💰 Total stake: {total_stake:.4f} TAO")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to check subnet: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Register INVARIANT subnet")
    parser.add_argument("--netuid", type=int, required=True, help="Subnet netuid")
    parser.add_argument("--wallet", type=str, default="owner", help="Owner wallet name")
    parser.add_argument("--network", type=str, default="test", help="Network (test/finney)")
    parser.add_argument("--register-only", action="store_true", help="Only register entities")
    parser.add_argument("--stake-only", action="store_true", help="Only stake validator")
    parser.add_argument("--check-only", action="store_true", help="Only check subnet status")
    
    args = parser.parse_args()
    
    if args.check_only:
        check_subnet(args.netuid, args.network)
    elif args.stake_only:
        stake_validator(args.netuid, args.network)
    elif args.register_only:
        register_entities(args.netuid, args.network)
    else:
        # Full registration process
        if register_subnet(args.netuid, args.wallet, args.network):
            register_entities(args.netuid, args.network)
            stake_validator(args.netuid, args.network)
        
        check_subnet(args.netuid, args.network)


if __name__ == "__main__":
    main()
