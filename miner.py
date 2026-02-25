"""
miner.py  (project root runner)
=================================
INVARIANT subnet miner.  Imports exclusively through the bridge.
Rust extension used automatically when compiled; falls back to Python.

Usage (from project root):
    python miner.py \
        --wallet.name miner1 \
        --wallet.hotkey default \
        --netuid 1 \
        --subtensor.network local \
        --axon.port 8091

    The miner auto-detects its LAN IP for axon registration.
    Override with --axon.external_ip X.X.X.X if needed.

Register first (local dev):
    python instant_register.py
"""

import argparse
import json
import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Tuple

import bittensor as bt

# ── Phase1-core path (from project root) ──────────────────────────
# Resolves to: <repo>/invariant/invariant/phase1_core/
sys.path.insert(0, str(Path(__file__).parent / "invariant" / "invariant" / "phase1_core"))

# All gate logic through the bridge — never import invariant_gates directly
from invariant_gates_bridge import (  # noqa: E402
    GateResult,
    Registry,
    Verifier,
    build_receipt,
    derive_software_agent_id,
    hash_model,
    using_rust,
)

from invariant_oap import OAPEngine  # noqa: E402


# ── LAN IP detection ──────────────────────────────────────────────


def _detect_lan_ip() -> str:
    """Return first non-loopback, non-Docker LAN IP, or empty string on failure."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith("127."):
            return ip
    except Exception:
        pass
    # Fallback: parse `ip addr show`
    try:
        out = subprocess.check_output(["ip", "addr", "show"], text=True, timeout=3)
        for line in out.splitlines():
            line = line.strip()
            if not line.startswith("inet "):
                continue
            ip = line.split()[1].split("/")[0]
            # Skip loopback and Docker bridge ranges
            if not any(ip.startswith(pfx) for pfx in ("127.", "172.17.", "172.18.", "172.16.")):
                return ip
    except Exception:
        pass
    return ""


def _ensure_external_ip(config: bt.Config) -> None:
    """
    If the user did not supply a valid --axon.external_ip, auto-detect the
    LAN IP and set it.  The Bittensor chain rejects 127.0.0.1 (loopback) so
    we must resolve to an actual interface address before serve_axon.
    """
    current = getattr(config.axon, "external_ip", None) or ""
    if current and not current.startswith("127.") and current != "0.0.0.0":
        return  # user provided a valid IP — honour it
    detected = _detect_lan_ip()
    if detected:
        config.axon.external_ip = detected
        bt.logging.info(f"Auto-detected axon external_ip: {detected}")
    else:
        bt.logging.warning(
            "Could not detect a non-loopback IP. "
            "serve_axon may fail — pass --axon.external_ip manually."
        )


# ── Data paths ────────────────────────────────────────────────────
DATA = Path("./miner_data")
DATA.mkdir(exist_ok=True)

REGISTRY_PATH = str(DATA / "registry.json")
OAP_PATH = str(DATA / "oap.json")
COUNTER_PATH = DATA / "counter.json"
IDENTITY_PATH = DATA / "identity.json"


def load_counter() -> int:
    try:
        return json.loads(COUNTER_PATH.read_text()).get("counter", 0)
    except Exception:
        return 0


def save_counter(n: int):
    COUNTER_PATH.write_text(json.dumps({"counter": n}))


def load_identity() -> dict:
    try:
        return json.loads(IDENTITY_PATH.read_text())
    except Exception:
        return {}


def save_identity(d: dict):
    IDENTITY_PATH.write_text(json.dumps(d, indent=2))


# ── Synapse ────────────────────────────────────────────────────────


class InvariantTask(bt.Synapse):
    task_input: str = ""
    tempo_id: int = 0
    task_type: str = "hash"
    output: str = ""
    receipt_json: str = ""
    checkpoint_json: str = ""

    def deserialize(self) -> "InvariantTask":
        return self


# ── Task executor ─────────────────────────────────────────────────


def execute_task(task_input: str, task_type: str) -> str:
    """
    Phase 1: deterministic proof-of-computation tasks.
    Phase 2: real LLM inference.
    The execution_hash cryptographically binds this output to this input.
    """
    import hashlib

    if task_type == "math":
        allowed = set("0123456789+-*/().% ")
        if all(c in allowed for c in task_input):
            try:
                return str(eval(task_input))  # safe: whitelist chars only
            except Exception:
                pass
        return "ERROR"
    # default: SHA-256 proof of execution
    return f"PROCESSED:{hashlib.sha256(task_input.encode()).hexdigest()}"


# ── Miner ─────────────────────────────────────────────────────────


class InvariantMiner:
    def __init__(self, config: bt.Config):
        self.config = config
        self.wallet = bt.Wallet(config=config)
        self.subtensor = bt.Subtensor(config=config)
        self.metagraph = bt.Metagraph(
            netuid=config.netuid, network=config.subtensor.network, sync=False
        )
        _ensure_external_ip(config)  # resolve LAN IP before axon binds
        self.axon = bt.Axon(wallet=self.wallet, config=config)

        self.registry = Registry(REGISTRY_PATH)
        self.oap = OAPEngine(OAP_PATH)
        self.counter = load_counter()

        self.agent_id_hex, self.model_hash_hex = self._init_identity()

        self.axon.attach(
            forward_fn=self.handle_task,
            blacklist_fn=self.blacklist,
            priority_fn=self.priority,
        )

        bt.logging.success(
            f"INVARIANT Miner ready | "
            f"backend={'Rust' if using_rust() else 'Python'} | "
            f"agent={self.agent_id_hex[:16]}... | "
            f"NTS={self.oap.get_nts(self.agent_id_hex):.1f} | "
            f"counter={self.counter}"
        )

    def _init_identity(self):
        identity = load_identity()
        if identity.get("agent_id_hex"):
            return identity["agent_id_hex"], identity["model_hash_hex"]

        model_id = getattr(self.config, "model_identifier", "invariant-v1")
        model_hex = hash_model(model_id)
        try:
            reg_block = self.subtensor.get_current_block()
        except Exception:
            reg_block = 0

        agent_hex = derive_software_agent_id(
            self.wallet.hotkey.ss58_address, model_hex, reg_block
        )

        self.registry.register_agent(agent_hex, self.wallet.hotkey.ss58_address)
        self.registry.approve_model(model_hex)
        self.oap.get_or_create(agent_hex, self.wallet.hotkey.ss58_address)

        save_identity(
            {
                "agent_id_hex": agent_hex,
                "model_hash_hex": model_hex,
                "hotkey": self.wallet.hotkey.ss58_address,
                "model_identifier": model_id,
            }
        )
        bt.logging.success(f"Identity derived: {agent_hex[:16]}...")
        return agent_hex, model_hex

    async def handle_task(self, synapse: InvariantTask) -> InvariantTask:
        try:
            output = execute_task(synapse.task_input, synapse.task_type)
            self.counter += 1
            save_counter(self.counter)

            receipt = build_receipt(
                self.agent_id_hex,
                self.model_hash_hex,
                synapse.task_input,
                output,
                self.counter,
                synapse.tempo_id,
                time.time(),
            )

            checkpoint = {}
            if self.oap.should_anchor(self.agent_id_hex, synapse.tempo_id):
                checkpoint = self.oap.checkpoint(self.agent_id_hex, synapse.tempo_id)

            synapse.output = output
            synapse.receipt_json = json.dumps(receipt)
            synapse.checkpoint_json = json.dumps(checkpoint)

            bt.logging.info(
                f"Task done | tempo={synapse.tempo_id} | "
                f"counter={self.counter} | digest={receipt['digest'][:12]}..."
            )
        except Exception as e:
            bt.logging.error(f"handle_task error: {e}")
            traceback.print_exc()
        return synapse

    async def blacklist(self, synapse: InvariantTask) -> Tuple[bool, str]:
        # Allow any registered neuron on the subnet (validator_permit requires stake
        # which is unavailable on local dev chains; block only unknown hotkeys).
        if synapse.dendrite.hotkey not in self.metagraph.hotkeys:
            return True, "Unknown hotkey — not registered on subnet"
        return False, "OK"

    async def priority(self, synapse: InvariantTask) -> float:
        try:
            uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
            return float(self.metagraph.S[uid])
        except Exception:
            return 0.0

    def run(self):
        self.axon.start()
        bt.logging.success(f"Axon started on port {self.axon.port}")

        # Announce axon to chain — retry once, but never abort if it fails.
        # On local --dev nodes serve_axon may return Custom Error 10 if the
        # subnet was just created and state is still settling; the axon is
        # already reachable by IP so we can still serve tasks.
        try:
            resp = self.subtensor.serve_axon(
                netuid=self.config.netuid,
                axon=self.axon,
                wait_for_inclusion=True,
                wait_for_finalization=False,
            )
            if resp.success:
                bt.logging.success("✅ Axon announced to chain")
            else:
                bt.logging.warning(
                    f"serve_axon returned non-success: {resp.message} — "
                    "continuing anyway (axon is reachable by IP)"
                )
        except Exception as e:
            bt.logging.warning(
                f"serve_axon failed ({e}) — continuing anyway (axon is reachable by IP)"
            )

        step = 0
        while True:
            try:
                if step % 5 == 0:
                    self.metagraph.sync(subtensor=self.subtensor)
                    bt.logging.info(
                        f"[step={step}] NTS={self.oap.get_nts(self.agent_id_hex):.1f} "
                        f"counter={self.counter}"
                    )
                step += 1
                time.sleep(12)
            except KeyboardInterrupt:
                bt.logging.info("Shutting down...")
                self.axon.stop()
                break
            except Exception as e:
                bt.logging.error(f"Loop error: {e}")
                time.sleep(30)


def get_config() -> bt.Config:
    p = argparse.ArgumentParser(description="INVARIANT Miner")
    bt.Wallet.add_args(p)
    bt.Subtensor.add_args(p)
    bt.logging.add_args(p)
    bt.Axon.add_args(p)
    p.add_argument("--netuid", type=int, default=1)
    p.add_argument("--model_identifier", type=str, default="invariant-v1")
    return bt.Config(p)


if __name__ == "__main__":
    cfg = get_config()
    bt.logging.set_config(config=cfg)
    InvariantMiner(cfg).run()
