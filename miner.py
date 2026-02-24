"""
INVARIANT - Phase 1: Bittensor Miner
======================================
Bittensor SDK v10.1.0 — verified API.

Custom error 10 = hotkey not registered on this subnet.
Run instant_register.py first, THEN start this.

Usage:
    python miner.py \
        --wallet.name miner1 \
        --wallet.hotkey default \
        --netuid 1 \
        --subtensor.chain_endpoint ws://127.0.0.1:9944
"""

import argparse
import hashlib
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Tuple

import bittensor as bt

# v10.1.0 API — all PascalCase except bt.logging
# bt.Wallet  bt.Subtensor  bt.Metagraph  bt.Axon  bt.Config  bt.Synapse
# blacklist_fn and priority_fn MUST be async def

sys.path.insert(0, str(Path(__file__).parent.parent / "phase1_core"))
sys.path.insert(0, str(Path(__file__).parent / "phase1_core"))

try:
    from invariant_gates import (
        InvariantRegistry,
        derive_software_agent_id,
        generate_receipt,
        hash_model,
    )
    from invariant_oap import OAPEngine

    INVARIANT_AVAILABLE = True
except ImportError as e:
    bt.logging.warning(f"phase1_core not found ({e}) — stub mode")
    INVARIANT_AVAILABLE = False

# ─────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────

DATA_DIR = Path("./invariant_miner_data")
COUNTER_PATH = DATA_DIR / "counter.json"
IDENTITY_PATH = DATA_DIR / "identity.json"
REGISTRY_PATH = DATA_DIR / "registry.json"
OAP_PATH = DATA_DIR / "oap_ledgers.json"


def load_counter() -> int:
    try:
        with open(COUNTER_PATH) as f:
            return json.load(f).get("counter", 0)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0


def save_counter(c: int):
    DATA_DIR.mkdir(exist_ok=True)
    with open(COUNTER_PATH, "w") as f:
        json.dump({"counter": c}, f)


def load_identity() -> dict:
    try:
        with open(IDENTITY_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_identity(d: dict):
    DATA_DIR.mkdir(exist_ok=True)
    with open(IDENTITY_PATH, "w") as f:
        json.dump(d, f, indent=2)


# ─────────────────────────────────────────────
# SYNAPSE  — imported by validator too
# ─────────────────────────────────────────────


class InvariantTask(bt.Synapse):
    task_input: str = ""
    tempo_id: int = 0
    task_type: str = "reasoning"
    output: str = ""
    receipt_json: str = ""
    checkpoint_json: str = ""

    def deserialize(self) -> dict:
        return {
            "output": self.output,
            "receipt_json": self.receipt_json,
            "checkpoint_json": self.checkpoint_json,
        }


# ─────────────────────────────────────────────
# TASK
# ─────────────────────────────────────────────


def execute_task(task_input: str, task_type: str) -> str:
    if task_type == "math":
        try:
            allowed = set("0123456789+-*/().% ")
            if all(c in allowed for c in task_input):
                return str(eval(task_input))
        except Exception:
            pass
        return "ERROR: invalid expression"
    elif task_type == "hash":
        return hashlib.sha256(task_input.encode()).hexdigest()
    else:
        return f"PROCESSED:{hashlib.sha256(task_input.encode()).hexdigest()}"


# ─────────────────────────────────────────────
# STUBS
# ─────────────────────────────────────────────


class _StubRegistry:
    def register_agent(self, *a, **kw):
        pass

    def approve_model(self, *a, **kw):
        pass


class _StubOAP:
    def get_nts(self, *a, **kw):
        return 50.0

    def get_or_create_ledger(self, *a, **kw):
        pass

    def should_anchor(self, *a, **kw):
        return False

    def generate_checkpoint(self, *a, **kw):
        return None


class _StubReceipt:
    def __init__(self, ti, o, c, t):
        self.digest = hashlib.sha256(f"{ti}{o}{c}{t}".encode()).digest()

    def to_dict(self):
        return {"stub": True, "digest": self.digest.hex()}


def _stub_derive(hotkey_ss58, model_hash, registration_block):
    return hashlib.sha256(
        f"{hotkey_ss58}{model_hash.hex()}{registration_block}".encode()
    ).digest()


def _stub_hash_model(s):
    return hashlib.sha256(s.encode()).digest()


def _stub_gen_receipt(agent_id, model_hash, task_input, output, counter, tempo_id):
    return _StubReceipt(task_input, output, counter, tempo_id)


# ─────────────────────────────────────────────
# REGISTRATION GUARD
# ─────────────────────────────────────────────


def check_registered(subtensor: bt.Subtensor, wallet: bt.Wallet, netuid: int) -> bool:
    """
    Custom error 10 = NotRegistered.
    Catch it HERE with a clear fix message instead of a cryptic stack trace.
    """
    import time

    bt.logging.info(
        f"🔍 Checking registration for hotkey: {wallet.hotkey.ss58_address}"
    )

    # Retry a few times in case of timing issues
    for attempt in range(3):
        try:
            registered = subtensor.is_hotkey_registered(
                netuid=netuid,
                hotkey_ss58=wallet.hotkey.ss58_address,
            )
            bt.logging.info(
                f"Attempt {attempt + 1}: is_hotkey_registered = {registered}"
            )
            if registered:
                bt.logging.success("✅ Hotkey is registered!")
                return True
            # If not registered, wait a bit and retry
            if attempt < 2:
                time.sleep(2)
        except Exception as e:
            bt.logging.warning(f"Exception in check_registered: {e}")
            return True  # can't check — don't block startup

    # Final check with alternative method
    try:
        uid = subtensor.get_uid_for_hotkey_on_subnet(wallet.hotkey.ss58_address, netuid)
        bt.logging.info(f"Alternative check - UID: {uid}")
        if uid is not None and uid >= 0:
            bt.logging.success("✅ Hotkey found via alternative method!")
            return True
    except Exception as e:
        bt.logging.warning(f"Alternative check failed: {e}")
        pass

    bt.logging.error(
        f"\n\n"
        f"  ✗  CUSTOM ERROR 10 — Hotkey not registered on subnet {netuid}\n"
        f"  ✗  Hotkey: {wallet.hotkey.ss58_address}\n\n"
        f"  FIX — run this first:\n\n"
        f"      python instant_register.py\n\n"
        f"  Or manually:\n\n"
        f"      btcli subnet register \\\n"
        f"        --wallet.name {wallet.name} \\\n"
        f"        --wallet.hotkey default \\\n"
        f"        --netuid {netuid} \\\n"
        f"        --subtensor.chain_endpoint ws://127.0.0.1:9944\n\n"
        f"  Then re-run miner.py\n"
    )
    return False


# ─────────────────────────────────────────────
# MINER
# ─────────────────────────────────────────────


class InvariantMiner:
    def __init__(self, config: bt.Config):
        self.config = config
        DATA_DIR.mkdir(exist_ok=True)
        bt.logging.info("Initializing INVARIANT Miner (v10.1.0)...")

        # v10 — PascalCase
        self.wallet = bt.Wallet(config=config)
        self.subtensor = bt.Subtensor(config=config)
        self.metagraph = bt.Metagraph(
            netuid=config.netuid, network=config.subtensor.network, sync=False
        )
        self.axon = bt.Axon(wallet=self.wallet, config=config)

        # Check registration BEFORE serve_axon — Custom Error 10 = not registered
        if not check_registered(self.subtensor, self.wallet, config.netuid):
            sys.exit(1)

        # INVARIANT core or stubs
        if INVARIANT_AVAILABLE:
            self.registry = InvariantRegistry(str(REGISTRY_PATH))
            self.oap = OAPEngine(str(OAP_PATH))
            self._derive_id = derive_software_agent_id
            self._hash_model = hash_model
            self._gen_receipt = generate_receipt
        else:
            self.registry = _StubRegistry()
            self.oap = _StubOAP()
            self._derive_id = _stub_derive
            self._hash_model = _stub_hash_model
            self._gen_receipt = _stub_gen_receipt

        self.counter = load_counter()
        self.agent_id, self.model_hash = self._init_identity()

        # v10: blacklist_fn and priority_fn MUST be async
        self.axon.attach(
            forward_fn=self.handle_task,
            blacklist_fn=self.blacklist,
            priority_fn=self.priority,
        )

        bt.logging.success(
            f"Miner ready | agent={self.agent_id.hex()[:16]}... | "
            f"NTS={self.oap.get_nts(self.agent_id.hex()):.1f} | "
            f"counter={self.counter}"
        )

    def _init_identity(self) -> Tuple[bytes, bytes]:
        identity = load_identity()
        if identity.get("agent_id_hex"):
            agent_id = bytes.fromhex(identity["agent_id_hex"])
            model_hash = bytes.fromhex(identity["model_hash_hex"])
            bt.logging.info(f"Identity loaded: {agent_id.hex()[:16]}...")
            return agent_id, model_hash

        model_id = getattr(self.config, "model_identifier", "invariant-default-v1")
        model_hash = self._hash_model(model_id)
        try:
            reg_block = self.subtensor.get_current_block()
        except Exception:
            reg_block = 0

        agent_id = self._derive_id(
            hotkey_ss58=self.wallet.hotkey.ss58_address,
            model_hash=model_hash,
            registration_block=reg_block,
        )
        self.registry.register_agent(
            agent_id,
            self.wallet.hotkey.ss58_address,
            {"model_identifier": model_id, "reg_block": reg_block},
        )
        self.registry.approve_model(model_hash)
        self.oap.get_or_create_ledger(
            agent_id.hex(), self.wallet.hotkey.ss58_address, registration_tempo=0
        )
        save_identity(
            {
                "agent_id_hex": agent_id.hex(),
                "model_hash_hex": model_hash.hex(),
                "hotkey": self.wallet.hotkey.ss58_address,
                "model_identifier": model_id,
            }
        )
        bt.logging.success(f"Identity created: {agent_id.hex()[:16]}...")
        return agent_id, model_hash

    async def handle_task(self, synapse: InvariantTask) -> InvariantTask:
        try:
            t0 = time.time()
            output = execute_task(synapse.task_input, synapse.task_type)
            self.counter += 1
            save_counter(self.counter)

            receipt = self._gen_receipt(
                agent_id=self.agent_id,
                model_hash=self.model_hash,
                task_input=synapse.task_input,
                output=output,
                counter=self.counter,
                tempo_id=synapse.tempo_id,
            )

            checkpoint = None
            if self.oap.should_anchor(self.agent_id.hex(), synapse.tempo_id):
                checkpoint = self.oap.generate_checkpoint(
                    self.agent_id.hex(), synapse.tempo_id
                )

            synapse.output = output
            synapse.receipt_json = json.dumps(receipt.to_dict())
            synapse.checkpoint_json = json.dumps(
                {
                    "agent_id_hex": checkpoint.agent_id_hex,
                    "nts_score": checkpoint.nts_score,
                    "total_tempos": checkpoint.total_tempos,
                    "clean_streak": checkpoint.clean_streak,
                    "total_violations": checkpoint.total_violations,
                    "catastrophic": checkpoint.is_catastrophically_flagged,
                    "tempo": checkpoint.checkpoint_tempo,
                    "timestamp": checkpoint.timestamp,
                }
                if checkpoint
                else {}
            )

            bt.logging.success(
                f"Task done | tempo={synapse.tempo_id} | counter={self.counter} | "
                f"{(time.time() - t0) * 1000:.1f}ms | digest={receipt.digest.hex()[:12]}..."
            )
        except Exception as e:
            bt.logging.error(f"handle_task error: {e}")
            traceback.print_exc()
            synapse.output = ""
            synapse.receipt_json = ""
        return synapse

    async def blacklist(self, synapse: InvariantTask) -> Tuple[bool, str]:
        try:
            hotkey = synapse.dendrite.hotkey
            if hotkey not in self.metagraph.hotkeys:
                return True, f"Unknown hotkey: {hotkey[:12]}..."
            uid = self.metagraph.hotkeys.index(hotkey)
            if not self.metagraph.validator_permit[uid]:
                return True, "No validator permit"
            return False, "OK"
        except Exception as e:
            return True, f"Blacklist error: {e}"

    async def priority(self, synapse: InvariantTask) -> float:
        try:
            hotkey = synapse.dendrite.hotkey
            if hotkey not in self.metagraph.hotkeys:
                return 0.0
            uid = self.metagraph.hotkeys.index(hotkey)
            return float(self.metagraph.S[uid])
        except Exception:
            return 0.0

    def run(self):
        self.axon.start()
        bt.logging.success(f"Axon started on port {self.axon.port}")

        # Announce axon to chain. On local --dev nodes this may return
        # Custom Error 10 if subnet state is still settling after registration.
        # We log the warning but never abort — the axon is reachable by IP.
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
                    f"serve_axon non-success: {resp.message} — "
                    "continuing (axon is still reachable by IP)"
                )
        except Exception as e:
            bt.logging.warning(
                f"serve_axon exception: {e} — "
                "continuing (axon is still reachable by IP)"
            )

        step = 0
        while True:
            try:
                if step % 5 == 0:
                    self.metagraph.sync(subtensor=self.subtensor)
                    bt.logging.info(
                        f"[{step}] block={self.subtensor.get_current_block()} | "
                        f"NTS={self.oap.get_nts(self.agent_id.hex()):.1f} | "
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


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────


def get_config() -> bt.Config:
    parser = argparse.ArgumentParser(description="INVARIANT Miner v10.1.0")
    bt.Wallet.add_args(parser)
    bt.Subtensor.add_args(parser)
    bt.logging.add_args(parser)
    bt.Axon.add_args(parser)
    parser.add_argument("--netuid", type=int, default=1)
    parser.add_argument("--model_identifier", type=str, default="invariant-default-v1")
    return bt.Config(parser)


if __name__ == "__main__":
    config = get_config()
    bt.logging(config=config, logging_dir=config.full_path)
    InvariantMiner(config).run()
