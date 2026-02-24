#!/usr/bin/env python3
"""
INVARIANT Testnet Deployment Script
==================================
Complete testnet deployment automation for INVARIANT subnet.

Usage:
    python scripts/deploy_testnet.py --netuid <NETUID> --wallet <OWNER_WALLET>
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List

import bittensor as bt

# Add invariant to path
sys.path.insert(0, str(Path(__file__).parent.parent / "invariant"))
from invariant.protocol import InvariantRegistration


class TestnetDeployer:
    def __init__(self, netuid: int, owner_wallet: str, network: str = "test"):
        self.netuid = netuid
        self.owner_wallet = owner_wallet
        self.network = network
        self.subtensor = bt.Subtensor(network=network)
        
    def create_wallets(self) -> Dict[str, bt.Wallet]:
        """Create required wallets for testnet deployment."""
        wallets = {}
        wallet_names = ["owner", "miner1", "validator1"]
        
        for name in wallet_names:
            try:
                wallet = bt.Wallet(name=name, hotkey="default")
                if not wallet.coldkeypub_file.exists_on_device():
                    wallet.create_new_coldkey(use_password=False, overwrite=True)
                    print(f"✅ Created coldkey for {name}")
                
                if not wallet.hotkey_file.exists_on_device():
                    wallet.create_new_hotkey(use_password=False, overwrite=True)
                    print(f"✅ Created hotkey for {name}")
                
                wallets[name] = wallet
                print(f"📋 {name}: {wallet.coldkeypub.ss58_address}")
                
            except Exception as e:
                print(f"❌ Failed to create wallet {name}: {e}")
                raise
        
        return wallets
    
    def fund_wallets(self, wallets: Dict[str, bt.Wallet]):
        """Fund wallets using testnet faucet."""
        print("\n🚰 Funding wallets...")
        
        for name, wallet in wallets.items():
            if name in ["owner", "validator1"]:  # Only fund these initially
                try:
                    result = self.subtensor.faucet(wallet=wallet, wait_for_inclusion=True)
                    print(f"✅ Funded {name}: {result}")
                except Exception as e:
                    print(f"❌ Failed to fund {name}: {e}")
    
    def create_subnet(self, owner_wallet: bt.Wallet) -> int:
        """Create INVARIANT subnet."""
        print("\n🏗️  Creating INVARIANT subnet...")
        
        try:
            # Load subnet parameters
            with open("SUBNET_PARAMS.json") as f:
                params = json.load(f)
            
            subnet_params = params["subnet_params"]
            
            result = self.subtensor.register_subnet(
                wallet=owner_wallet,
                wait_for_inclusion=True,
                wait_for_finalization=True,
                **subnet_params
            )
            
            print(f"✅ Subnet created: {result}")
            return self.netuid
            
        except Exception as e:
            print(f"❌ Failed to create subnet: {e}")
            raise
    
    def register_miners_validators(self, wallets: Dict[str, bt.Wallet]):
        """Register miners and validators to subnet."""
        print("\n📝 Registering miners and validators...")
        
        registrations = [
            ("miner1", wallets["miner1"]),
            ("validator1", wallets["validator1"]),
        ]
        
        for name, wallet in registrations:
            try:
                result = self.subtensor.register(
                    wallet=wallet,
                    netuid=self.netuid,
                    wait_for_inclusion=True,
                    wait_for_finalization=True,
                )
                print(f"✅ Registered {name}: {result}")
                
            except Exception as e:
                print(f"❌ Failed to register {name}: {e}")
    
    def stake_validator(self, validator_wallet: bt.Wallet):
        """Stake TAO for validator."""
        print("\n💰 Staking validator...")
        
        try:
            result = self.subtensor.add_stake(
                wallet=validator_wallet,
                netuid=self.netuid,
                amount=1000,  # 1000 TAO
                wait_for_inclusion=True,
                wait_for_finalization=True,
            )
            print(f"✅ Staked validator: {result}")
            
        except Exception as e:
            print(f"❌ Failed to stake validator: {e}")
    
    def launch_miner(self, miner_wallet: bt.Wallet):
        """Launch INVARIANT miner."""
        print("\n⛏️  Launching miner...")
        
        cmd = [
            "python", "miner.py",
            "--wallet.name", "miner1",
            "--wallet.hotkey", "default", 
            "--netuid", str(self.netuid),
            "--subtensor.network", self.network,
            "--logging.debug"
        ]
        
        try:
            process = subprocess.Popen(
                cmd,
                cwd=Path(__file__).parent.parent,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            print(f"✅ Miner launched (PID: {process.pid})")
            return process
            
        except Exception as e:
            print(f"❌ Failed to launch miner: {e}")
            raise
    
    def launch_validator(self, validator_wallet: bt.Wallet):
        """Launch INVARIANT validator."""
        print("\n🔍 Launching validator...")
        
        cmd = [
            "python", "validator.py",
            "--wallet.name", "validator1",
            "--wallet.hotkey", "default",
            "--netuid", str(self.netuid), 
            "--subtensor.network", self.network,
            "--logging.debug"
        ]
        
        try:
            process = subprocess.Popen(
                cmd,
                cwd=Path(__file__).parent.parent,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            print(f"✅ Validator launched (PID: {process.pid})")
            return process
            
        except Exception as e:
            print(f"❌ Failed to launch validator: {e}")
            raise
    
    def monitor_subnet(self):
        """Monitor subnet activity."""
        print("\n📊 Monitoring subnet activity...")
        
        while True:
            try:
                # Get subnet info
                subnet_info = self.subtensor.get_subnet_info(self.netuid)
                metagraph = bt.metagraph(netuid=self.netuid, network=self.network)
                metagraph.sync()
                
                print(f"\n=== Tempo {subnet_info.blocks_since_epoch} ===")
                print(f"📡 Registered miners: {len([n for n in metagraph.neurons if n.validator_trust < 0.5])}")
                print(f"🔍 Registered validators: {len([n for n in metagraph.neurons if n.validator_trust > 0.5])}")
                print(f"⚖️  Total stake: {sum(n.stake for n in metagraph.neurons):.4f} TAO")
                
                time.sleep(30)  # Update every 30 seconds
                
            except KeyboardInterrupt:
                print("\n👋 Stopping monitor...")
                break
            except Exception as e:
                print(f"❌ Monitor error: {e}")
                time.sleep(10)
    
    def deploy(self):
        """Complete testnet deployment."""
        print(f"🚀 Deploying INVARIANT to {self.network} testnet (netuid: {self.netuid})")
        
        # 1. Create wallets
        wallets = self.create_wallets()
        
        # 2. Fund wallets
        self.fund_wallets(wallets)
        
        # 3. Create subnet
        self.create_subnet(wallets["owner"])
        
        # 4. Register miners and validators
        self.register_miners_validators(wallets)
        
        # 5. Stake validator
        self.stake_validator(wallets["validator1"])
        
        # 6. Launch miner and validator
        miner_process = self.launch_miner(wallets["miner1"])
        validator_process = self.launch_validator(wallets["validator1"])
        
        print("\n✅ INVARIANT testnet deployment complete!")
        print(f"🌐 Subnet: {self.netuid}")
        print(f"👛 Owner: {wallets['owner'].coldkeypub.ss58_address}")
        print(f"⛏️  Miner: {wallets['miner1'].coldkeypub.ss58_address}")
        print(f"🔍 Validator: {wallets['validator1'].coldkeypub.ss58_address}")
        
        try:
            # Monitor the subnet
            self.monitor_subnet()
        finally:
            # Cleanup processes
            print("\n🛑 Shutting down processes...")
            miner_process.terminate()
            validator_process.terminate()


def main():
    parser = argparse.ArgumentParser(description="Deploy INVARIANT to testnet")
    parser.add_argument("--netuid", type=int, required=True, help="Subnet netuid")
    parser.add_argument("--wallet", type=str, default="owner", help="Owner wallet name")
    parser.add_argument("--network", type=str, default="test", help="Network (test/finney)")
    
    args = parser.parse_args()
    
    deployer = TestnetDeployer(args.netuid, args.wallet, args.network)
    deployer.deploy()


if __name__ == "__main__":
    main()
