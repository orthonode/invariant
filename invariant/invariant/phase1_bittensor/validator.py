"""
invariant/phase1_bittensor/validator.py
=========================================
INVARIANT subnet validator.  Three-tier deterministic scoring pipeline.
Imports all gate logic through the bridge — Rust when compiled, Python fallback.

v10.1.0 API fixes applied:
  - bt.Wallet / bt.Subtensor / bt.Metagraph / bt.Axon / bt.Dendrite (PascalCase)
  - bt.Config (not bt.config)
  - bt.logging.set_config (not bt.logging(config=...))
  - Removed circular import from miner.py — InvariantTask defined here
  - Per-miner unique task dispatch (not broadcasting one task to all miners)
  - Dendrite called as: await self.dendrite(axons=[axon], synapse=s, timeout=N)
  - axon.is_serving is a property on AxonInfo (ip != "0.0.0.0")

Launch:
    python validator.py \
        --wallet.name validator1 \
        --wallet.hotkey default \
        --netuid <NETUID> \
        --subtensor.network local \
        --subtensor.chain_endpoint ws://127.0.0.1:9944
"""

import argparse
import asyncio
import hashlib
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import bittensor as bt
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "phase1_core"))
from invariant_gates_bridge import (
    GateResult,
    Registry,
    Verifier,
    using_rust,
)

from invariant_oap import OAPEngine, ViolationType

# ── Synapse (defined here — identical fields to miner.py, wire-compatible) ──


class InvariantTask(bt.Synapse):
    task_input: str = ""
    tempo_id: int = 0
    task_type: str = "hash"
    output: str = ""
    receipt_json: str = ""
    checkpoint_json: str = ""

    def deserialize(self) -> dict:
        return {
            "output": self.output,
            "receipt_json": self.receipt_json,
            "checkpoint_json": self.checkpoint_json,
        }


# ── Data paths ─────────────────────────────────────────────────────────────

DATA = Path("./validator_data")
DATA.mkdir(exist_ok=True)

REGISTRY_PATH = str(DATA / "registry.json")
OAP_PATH = str(DATA / "oap.json")
STATE_PATH = str(DATA / "state.json")

WINDOW_BLOCKS = 10  # 120 s submission window
LATE_BLOCKS = 15  # 180 s late window
MIN_QUALITY = 0.3  # minimum quality for non-zero score


# ── Task generation ────────────────────────────────────────────────────────


def generate_task(tempo: int, uid: int) -> Tuple[str, str]:
    """Deterministic per-(tempo, uid) pair — different for every miner every tempo."""
    seed = hashlib.sha256(f"{tempo}:{uid}".encode()).hexdigest()
    kind = ["math", "hash", "hash"][int(seed[0], 16) % 3]

    if kind == "math":
        a = int(seed[0:4], 16) % 500
        b = int(seed[4:8], 16) % 500
        op = ["+", "-", "*"][int(seed[8], 16) % 3]
        return f"{a} {op} {b}", "math"
    return f"INVARIANT:{tempo}:{uid}:{seed[:12]}", "hash"


def score_output(task_input: str, task_type: str, output: str) -> float:
    if not output or not output.strip():
        return 0.0
    try:
        if task_type == "math":
            allowed = set("0123456789+-*/().% ")
            if all(c in allowed for c in task_input):
                return 1.0 if output.strip() == str(eval(task_input)) else 0.0
            return 0.0
        # hash / default
        expected = hashlib.sha256(task_input.encode()).hexdigest()
        submitted = output.replace("PROCESSED:", "").strip()
        if submitted.lower() == expected.lower():
            return 1.0
        return 0.2 if len(output.strip()) > 5 else 0.0
    except Exception:
        return 0.0


# ── Validator ──────────────────────────────────────────────────────────────


class InvariantValidator:
    def __init__(self, config: bt.Config):
        self.config = config
        self.wallet = bt.Wallet(config=config)
        self.subtensor = bt.Subtensor(config=config)
        self.metagraph = bt.Metagraph(
            netuid=config.netuid,
            network=config.subtensor.network,
            sync=False,
        )
        # v10: bt.Dendrite (PascalCase)
        self.dendrite = bt.Dendrite(wallet=self.wallet)

        self.registry = Registry(REGISTRY_PATH)
        self.verifier = Verifier(REGISTRY_PATH, STATE_PATH)
        self.oap = OAPEngine(OAP_PATH)
        self.tempo = self._current_tempo()

        # uid → agent_id_hex cache; rebuilt on every metagraph sync
        self._uid_to_agent: Dict[int, str] = {}

        bt.logging.success(
            f"INVARIANT Validator ready | "
            f"backend={'Rust' if using_rust() else 'Python'} | "
            f"tempo={self.tempo}"
        )

    # ── Helpers ────────────────────────────────────────────────────────────

    def _current_tempo(self) -> int:
        try:
            block = self.subtensor.get_current_block()
            t = self.subtensor.get_subnet_hyperparameters(self.config.netuid).tempo
            return block // t
        except Exception:
            return 0

    def _build_uid_agent_map(self):
        """Rebuild uid → agent_id_hex from registry JSON + metagraph hotkeys."""
        self._uid_to_agent = {}
        hotkey_to_agent: Dict[str, str] = {}

        try:
            with open(REGISTRY_PATH) as f:
                data = json.load(f)
            for aid_hex, meta in data.get("agents", {}).items():
                hk = meta.get("hotkey", "")
                if hk:
                    hotkey_to_agent[hk] = aid_hex
        except Exception:
            pass

        for uid, hotkey in enumerate(self.metagraph.hotkeys):
            if hotkey in hotkey_to_agent:
                self._uid_to_agent[uid] = hotkey_to_agent[hotkey]

    # ── Tier 1: Gate verification ──────────────────────────────────────────

    def _verify_receipt(
        self, uid: int, receipt_json: str
    ) -> Tuple[float, str, int, str]:
        """Returns (gate_multiplier, result_code, gate_number, detail)."""
        if not receipt_json:
            return 0.0, GateResult.GATE1, 1, "No receipt"

        try:
            receipt_dict = json.loads(receipt_json)
        except json.JSONDecodeError as e:
            return 0.0, GateResult.PARSE_ERROR, 4, str(e)

        # Cross-check: receipt's agent_id must match our uid→agent mapping
        expected_agent = self._uid_to_agent.get(uid)
        if expected_agent and receipt_dict.get("agent_id") != expected_agent:
            return 0.0, GateResult.GATE1, 1, "agent_id mismatch with registry"

        result = self.verifier.verify(receipt_dict)
        if GateResult.is_pass(result["result"]):
            return 1.0, result["result"], 0, ""
        return 0.0, result["result"], result["gate_number"], result.get("detail", "")

    # ── Full per-miner score ───────────────────────────────────────────────

    def score_miner(
        self,
        uid: int,
        task_input: str,
        task_type: str,
        response: InvariantTask,
        tempo_start: float,
    ) -> float:
        agent_hex = self._uid_to_agent.get(uid, "")
        elapsed = time.time() - tempo_start
        block_s = 12.0
        in_window = elapsed <= WINDOW_BLOCKS * block_s
        late = elapsed <= LATE_BLOCKS * block_s
        freshness = 1.0 if in_window else (0.5 if late else 0.0)

        if freshness == 0.0:
            if agent_hex:
                self.oap.record_timeout(agent_hex, self.tempo)
            bt.logging.warning(f"UID {uid} timed out ({elapsed:.1f}s)")
            return 0.0

        # Tier 1 — four-gate verification
        gate_mult, result_code, gate_num, detail = self._verify_receipt(
            uid, response.receipt_json
        )

        if gate_mult == 0.0:
            if agent_hex:
                vtype_map = {
                    1: ViolationType.GATE1,
                    2: ViolationType.GATE2,
                    3: ViolationType.GATE3,
                    4: ViolationType.GATE4,
                }
                vtype = vtype_map.get(gate_num, ViolationType.NO_RECEIPT)
                self.oap.record_violation(
                    agent_hex, self.tempo, gate_num, vtype, detail
                )
            bt.logging.warning(f"UID {uid} gate fail: {result_code} | {detail}")
            return 0.0

        # Tier 2 — output quality
        quality = score_output(task_input, task_type, response.output)

        # Tier 3 — NTS multiplier
        nts = self.oap.get_nts(agent_hex) if agent_hex else 50.0
        if agent_hex:
            self.oap.record_clean(agent_hex, self.tempo)

        weight = OAPEngine.emission_weight(quality, nts, in_window, late)
        bt.logging.info(
            f"UID {uid} | quality={quality:.2f} × NTS={nts:.1f}/100 × "
            f"fresh={freshness:.1f} = weight={weight:.4f}"
        )
        return weight

    # ── Tempo loop ─────────────────────────────────────────────────────────

    async def run_tempo(self):
        self.metagraph.sync(subtensor=self.subtensor)
        self.tempo = self._current_tempo()
        self._build_uid_agent_map()

        # AxonInfo.is_serving is a property: True when ip != "0.0.0.0"
        miner_uids = [
            uid
            for uid, axon in enumerate(self.metagraph.axons)
            if getattr(axon, "is_serving", False)
            and not self.metagraph.validator_permit[uid]
        ]

        if not miner_uids:
            bt.logging.warning(
                "No active miners in metagraph (is_serving=False for all)"
            )
            return

        bt.logging.info(f"=== Tempo {self.tempo} | {len(miner_uids)} active miners ===")
        tempo_start = time.time()

        # Generate unique per-miner tasks
        tasks: Dict[int, Tuple[str, str]] = {
            uid: generate_task(self.tempo, uid) for uid in miner_uids
        }

        # Query each miner individually so they get their own unique task.
        # v10 Dendrite: await self.dendrite(axons=[axon], synapse=synapse, timeout=N)
        # Returns a list with one response per axon.
        responses: Dict[int, InvariantTask] = {}
        for uid in miner_uids:
            task_input, task_type = tasks[uid]
            synapse = InvariantTask(
                task_input=task_input,
                tempo_id=self.tempo,
                task_type=task_type,
            )
            try:
                result = await self.dendrite(
                    axons=[self.metagraph.axons[uid]],
                    synapse=synapse,
                    timeout=WINDOW_BLOCKS * 12,
                )
                # dendrite returns list[Synapse] — one per axon
                responses[uid] = result[0] if isinstance(result, list) else result
            except Exception as e:
                bt.logging.debug(f"UID {uid} dendrite error: {e}")
                responses[uid] = synapse  # empty / default response

        response_time = time.time()

        weights = np.zeros(len(self.metagraph.hotkeys), dtype=np.float32)

        for uid in miner_uids:
            response = responses.get(uid)
            if response is None:
                weights[uid] = 0.0
                continue

            task_input, task_type = tasks[uid]
            weights[uid] = self.score_miner(
                uid=uid,
                task_input=task_input,
                task_type=task_type,
                response=response,
                tempo_start=tempo_start,
            )

        # Normalise
        total = weights.sum()
        if total > 0:
            weights /= total

        # Set weights on chain
        try:
            nonzero = np.where(weights > 0)[0]
            if len(nonzero) > 0:
                self.subtensor.set_weights(
                    wallet=self.wallet,
                    netuid=self.config.netuid,
                    uids=nonzero.astype(np.int64),
                    weights=weights[nonzero].astype(np.float32),
                    wait_for_finalization=False,
                )
                bt.logging.success(
                    f"Weights set | tempo={self.tempo} | active_miners={len(nonzero)}"
                )
        except Exception as e:
            bt.logging.error(f"set_weights failed: {e}")

    # ── Main loop ──────────────────────────────────────────────────────────

    def run(self):
        bt.logging.success("INVARIANT Validator running...")
        while True:
            try:
                asyncio.run(self.run_tempo())
                try:
                    t = self.subtensor.get_subnet_hyperparameters(
                        self.config.netuid
                    ).tempo
                except Exception:
                    t = 100
                sleep = t * 12
                bt.logging.info(f"Tempo complete. Next in {sleep}s...")
                time.sleep(sleep)
            except KeyboardInterrupt:
                bt.logging.info("Validator shutting down...")
                break
            except Exception as e:
                bt.logging.error(f"Tempo error: {e}")
                traceback.print_exc()
                time.sleep(30)


# ── Entry point ────────────────────────────────────────────────────────────


def get_config() -> bt.Config:
    p = argparse.ArgumentParser(description="INVARIANT Validator")
    bt.Wallet.add_args(p)
    bt.Subtensor.add_args(p)
    bt.logging.add_args(p)
    p.add_argument("--netuid", type=int, default=1)
    return bt.Config(p)


if __name__ == "__main__":
    cfg = get_config()
    bt.logging.set_config(config=cfg)
    InvariantValidator(cfg).run()
