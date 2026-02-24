#!/usr/bin/env python3
"""
INVARIANT Node Launch Script
============================
Launch miners and validators for INVARIANT subnet.

Usage:
    python scripts/launch_nodes.py --netuid <NETUID> --network test --role miner
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Optional


class NodeLauncher:
    def __init__(self, netuid: int, network: str = "test"):
        self.netuid = netuid
        self.network = network
        self.processes: Dict[str, subprocess.Popen] = {}
    
    def launch_miner(self, wallet_name: str = "miner1") -> subprocess.Popen:
        """Launch INVARIANT miner."""
        print(f"⛏️  Launching miner {wallet_name}")
        
        cmd = [
            "python", "miner.py",
            "--wallet.name", wallet_name,
            "--wallet.hotkey", "default",
            "--netuid", str(self.netuid),
            "--subtensor.network", self.network,
            "--logging.debug",
            "--axon.port", str(8091 + len(self.processes))
        ]
        
        env = {
            "PYTHONPATH": str(Path(__file__).parent.parent / "invariant"),
            **dict(os.environ)
        }
        
        try:
            process = subprocess.Popen(
                cmd,
                cwd=Path(__file__).parent.parent,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            self.processes[f"miner_{wallet_name}"] = process
            print(f"✅ Miner {wallet_name} launched (PID: {process.pid})")
            return process
            
        except Exception as e:
            print(f"❌ Failed to launch miner {wallet_name}: {e}")
            raise
    
    def launch_validator(self, wallet_name: str = "validator1") -> subprocess.Popen:
        """Launch INVARIANT validator."""
        print(f"🔍 Launching validator {wallet_name}")
        
        cmd = [
            "python", "validator.py", 
            "--wallet.name", wallet_name,
            "--wallet.hotkey", "default",
            "--netuid", str(self.netuid),
            "--subtensor.network", self.network,
            "--logging.debug"
        ]
        
        env = {
            "PYTHONPATH": str(Path(__file__).parent.parent / "invariant"),
            **dict(os.environ)
        }
        
        try:
            process = subprocess.Popen(
                cmd,
                cwd=Path(__file__).parent.parent,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            self.processes[f"validator_{wallet_name}"] = process
            print(f"✅ Validator {wallet_name} launched (PID: {process.pid})")
            return process
            
        except Exception as e:
            print(f"❌ Failed to launch validator {wallet_name}: {e}")
            raise
    
    def monitor_processes(self):
        """Monitor all launched processes."""
        print(f"📊 Monitoring {len(self.processes)} processes...")
        
        try:
            while True:
                for name, process in list(self.processes.items()):
                    if process.poll() is not None:
                        print(f"❌ Process {name} exited with code {process.returncode}")
                        del self.processes[name]
                
                if not self.processes:
                    print("🔚 All processes exited")
                    break
                
                print(f"📡 Active processes: {list(self.processes.keys())}")
                time.sleep(30)
                
        except KeyboardInterrupt:
            print("\n👋 Stopping monitor...")
    
    def stop_all(self):
        """Stop all processes."""
        print("🛑 Stopping all processes...")
        
        for name, process in self.processes.items():
            try:
                process.terminate()
                print(f"🛑 Stopped {name}")
            except Exception as e:
                print(f"❌ Failed to stop {name}: {e}")
        
        # Wait for graceful shutdown
        time.sleep(5)
        
        # Force kill if needed
        for name, process in self.processes.items():
            try:
                if process.poll() is None:
                    process.kill()
                    print(f"💀 Killed {name}")
            except Exception as e:
                print(f"❌ Failed to kill {name}: {e}")
    
    def launch_all(self):
        """Launch complete INVARIANT network."""
        print(f"🚀 Launching INVARIANT network (netuid: {self.netuid})")
        
        try:
            # Launch validator first
            validator_process = self.launch_validator("validator1")
            time.sleep(5)  # Give validator time to start
            
            # Launch miner
            miner_process = self.launch_miner("miner1")
            
            print("✅ INVARIANT network launched")
            print(f"📡 Processes: {list(self.processes.keys())}")
            
            # Monitor processes
            self.monitor_processes()
            
        except KeyboardInterrupt:
            print("\n👋 Shutting down...")
        finally:
            self.stop_all()


def launch_single(role: str, wallet: str, netuid: int, network: str):
    """Launch a single node."""
    launcher = NodeLauncher(netuid, network)
    
    if role == "miner":
        process = launcher.launch_miner(wallet)
    elif role == "validator":
        process = launcher.launch_validator(wallet)
    else:
        print(f"❌ Unknown role: {role}")
        return
    
    try:
        # Monitor single process
        while process.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Stopping...")
    finally:
        process.terminate()


def main():
    parser = argparse.ArgumentParser(description="Launch INVARIANT nodes")
    parser.add_argument("--netuid", type=int, required=True, help="Subnet netuid")
    parser.add_argument("--network", type=str, default="test", help="Network (test/finney)")
    parser.add_argument("--role", type=str, choices=["miner", "validator", "all"], default="all", help="Role to launch")
    parser.add_argument("--wallet", type=str, help="Wallet name (for single role)")
    
    args = parser.parse_args()
    
    if args.role == "all":
        launcher = NodeLauncher(args.netuid, args.network)
        launcher.launch_all()
    else:
        if not args.wallet:
            print("❌ --wallet required for single role launch")
            sys.exit(1)
        launch_single(args.role, args.wallet, args.netuid, args.network)


if __name__ == "__main__":
    import os
    main()
