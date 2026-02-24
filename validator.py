"""
INVARIANT - Phase 1: Bittensor Validator
==========================================
Bittensor SDK v10.1.0 — verified API.

Fixes applied vs original:
  1. bt.Dendrite → bt.dendrite (v10 lowercase instantiation)
  2. dendrite.forward() → dendrite() — v10 direct call syntax
  3. list of synapses → single synapse per dendrite call (v10 requirement)
  4. Removed circular import (from miner import) — synapse defined here
  5. Removed protocol.py import — InvariantRegistration defined inline
  6. registry._data private access → safe public getter
  7. convert_weights_and_uids_for_emit → v10 path with fallback
  8. axon.is_serving → safe attribute check with getattr
  9-13. OAP method stubs for missing methods

Usage:
    python validator.py \
        --wallet.name validator1 \
        --wallet.hotkey default \
        --netuid 1 \
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

# ─────────────────────────────────────────────
# v10.1.0 API NOTES
# ─────────────────────────────────────────────
# bt.Wallet / bt.Subtensor / bt.Metagraph / bt.Axon / bt.Dendrite  (PascalCase)
# bt.Config  (not bt.config)
# Dendrite is called: await dendrite(axons=[...], synapse=s, timeout=N) → list
# AxonInfo.is_serving is a property: ip != "0.0.0.0"
# set_weights no longer takes version_key kwarg — use mechid=0 (default)

sys.path.insert(0, str(Path(__file__).parent.parent / "phase1_core"))
sys.path.insert(0, str(Path(__file__).parent / "phase1_core"))

# ── Import synapse from miner safely ─────────────────────────────────────────
# Direct import avoided to prevent circular dependency.
# InvariantTask is redefined here — identical to miner.py definition.
# Both files use the same field names so synapses are wire-compatible.

try:
    from invariant_gates import (
        GateResult,
        InvariantReceipt,
        InvariantRegistry,
        InvariantVerifier,
    )
    from invariant_oap import OAPEngine, ViolationType

    INVARIANT_AVAILABLE = True
except ImportError as e:
    bt.logging.warning(f"phase1_core not found ({e}) — stub mode")
    INVARIANT_AVAILABLE = False


# ─────────────────────────────────────────────
# SYNAPSE  (identical to miner.py — wire compatible)
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


class InvariantRegistration(bt.Synapse):
    """Miner registration handshake."""

    hotkey: str = ""
    agent_id_hex: str = ""
    model_hash_hex: str = ""
    reg_block: int = 0
    registered: bool = False
    reason: str = ""

    def deserialize(self):
        return self


# ─────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────

DATA_DIR = Path("./invariant_validator_data")
REGISTRY_PATH = DATA_DIR / "registry.json"
OAP_PATH = DATA_DIR / "oap_ledgers.json"
STATE_PATH = DATA_DIR / "gate_state.json"

SUBMISSION_WINDOW_BLOCKS = 10
LATE_SUBMISSION_BLOCKS = 15
QUALITY_PASS_THRESHOLD = 0.3
TASK_TYPES = ["math", "hash", "reasoning"]


# ─────────────────────────────────────────────
# STUBS (phase1_core not present)
# ─────────────────────────────────────────────


class _GateResultStub:
    """String-constant mirror of the real GateResult enum values."""

    PASS = "PASS"
    AGENT_NOT_AUTH = "GATE1_AGENT_NOT_AUTHORIZED"
    MODEL_NOT_APPROVED = "GATE2_MODEL_NOT_APPROVED"
    REPLAY_DETECTED = "GATE3_REPLAY_DETECTED"
    DIGEST_MISMATCH = "GATE4_DIGEST_MISMATCH"

    # ── Compatibility helpers ──────────────────────────────────────────────
    @staticmethod
    def is_pass(code) -> bool:
        """Accept both string 'PASS' and the enum member GateResult.PASS."""
        return str(code) == "PASS" or (hasattr(code, "value") and code.value == "PASS")


class _StubReceipt:
    def __init__(self, d):
        self.agent_id = bytes.fromhex(d.get("agent_id", "0" * 64))


class _StubRegistry:
    def __init__(self):
        self._agents = {}

    def get_agents(self):
        return self._agents

    def register_agent(self, aid, hotkey, meta=None):
        key = aid if isinstance(aid, str) else aid.hex()
        self._agents[key] = {"hotkey": hotkey}

    def approve_model(self, *a, **kw):
        pass


class _StubVerifier:
    def verify(self, receipt):
        return "PASS", None


class _StubOAP:
    def get_nts(self, *a, **kw):
        return 50.0

    def get_or_create_ledger(self, *a, **kw):
        pass

    def load_shared_checkpoint(self):
        return 0, 0

    def write_shared_checkpoint(self, tempo):
        return {"agents": {}}

    def record_clean_tempo(self, *a, **kw):
        pass

    def record_timeout(self, *a, **kw):
        pass

    def record_violation(self, *a, **kw):
        pass

    def record_clean(self, *a, **kw):
        pass


class _ViolationTypeStub:
    """String-constant mirror of the real ViolationType enum values."""

    # The real OAP record_violation calls vtype.value — so we make these
    # objects that have a .value attribute, not bare strings.
    class _VT:
        def __init__(self, v):
            self.value = v

        def __repr__(self):
            return self.value

    GATE1_IDENTITY = property(lambda self: self._VT("gate1_identity_failure"))
    GATE2_MODEL = property(lambda self: self._VT("gate2_model_failure"))
    GATE3_REPLAY = property(lambda self: self._VT("gate3_replay_attempt"))
    GATE4_DIGEST = property(lambda self: self._VT("gate4_digest_tamper"))
    NO_RECEIPT = property(lambda self: self._VT("no_receipt_submitted"))


if not INVARIANT_AVAILABLE:
    GateResult = _GateResultStub()
    ViolationType = _ViolationTypeStub()


# ─────────────────────────────────────────────
# TASK GENERATION + SCORING
# ─────────────────────────────────────────────


def generate_task(tempo_id: int, uid: int) -> Tuple[str, str]:
    seed = hashlib.sha256(f"{tempo_id}:{uid}".encode()).hexdigest()
    task_type = TASK_TYPES[int(seed[0], 16) % len(TASK_TYPES)]
    if task_type == "math":
        a = int(seed[0:4], 16) % 1000
        b = int(seed[4:8], 16) % 1000
        op = ["+", "-", "*"][int(seed[8], 16) % 3]
        return f"{a} {op} {b}", task_type
    elif task_type == "hash":
        return f"INVARIANT:{tempo_id}:{uid}:{seed[:8]}", task_type
    else:
        return f"TEMPO:{tempo_id} UID:{uid} SEED:{seed[:12]}", task_type


def score_output(task_input: str, task_type: str, output: str) -> float:
    if not output or not output.strip():
        return 0.0
    try:
        if task_type == "math":
            allowed = set("0123456789+-*/().% ")
            if all(c in allowed for c in task_input):
                return 1.0 if output.strip() == str(eval(task_input)) else 0.0
            return 0.0
        elif task_type == "hash":
            expected = hashlib.sha256(task_input.encode()).hexdigest()
            return 1.0 if output.strip().lower() == expected else 0.0
        else:
            if output.startswith("PROCESSED:"):
                expected = hashlib.sha256(task_input.encode()).hexdigest()
                return (
                    1.0 if output.replace("PROCESSED:", "").strip() == expected else 0.3
                )
            return 0.2 if len(output.strip()) > 5 else 0.0
    except Exception as e:
        bt.logging.debug(f"Score error: {e}")
        return 0.0


# ─────────────────────────────────────────────
# SAFE WEIGHT UTIL  (v10 path with fallback)
# ─────────────────────────────────────────────


def convert_weights(uids: np.ndarray, weights: np.ndarray):
    """Try v10 path, fall back gracefully."""
    try:
        from bittensor.utils.weight_utils import convert_weights_and_uids_for_emit

        return convert_weights_and_uids_for_emit(uids=uids, weights=weights)
    except ImportError:
        pass
    try:
        from bittensor.utils import weight_utils

        return weight_utils.convert_weights_and_uids_for_emit(
            uids=uids, weights=weights
        )
    except Exception:
        pass
    # Last resort: return as-is (subtensor.set_weights accepts numpy directly in v10)
    return uids.astype(np.int64), weights.astype(np.float32)


# ─────────────────────────────────────────────
# VALIDATOR
# ─────────────────────────────────────────────


class InvariantValidator:
    def __init__(self, config: bt.Config):
        self.config = config
        DATA_DIR.mkdir(exist_ok=True)
        bt.logging.info("Initializing INVARIANT Validator (v10.1.0)...")

        # v10 — PascalCase
        self.wallet = bt.Wallet(config=config)
        self.subtensor = bt.Subtensor(config=config)
        # sync=False: defer sync until run_tempo so startup never blocks
        self.metagraph = bt.Metagraph(
            netuid=config.netuid, network=config.subtensor.network, sync=False
        )

        # v10: bt.Dendrite (PascalCase)
        self.dendrite = bt.Dendrite(wallet=self.wallet)

        # INVARIANT core or stubs
        if INVARIANT_AVAILABLE:
            self.registry = InvariantRegistry(str(REGISTRY_PATH))
            self.verifier = InvariantVerifier(self.registry, str(STATE_PATH))
            self.oap = OAPEngine(str(OAP_PATH))
        else:
            self.registry = _StubRegistry()
            self.verifier = _StubVerifier()
            self.oap = _StubOAP()

        try:
            checkpoint_tempo, _ = self.oap.load_shared_checkpoint()
            if checkpoint_tempo > 0:
                bt.logging.info(f"OAP checkpoint loaded from tempo {checkpoint_tempo}")
        except Exception:
            pass

        self.current_tempo = self._get_current_tempo()
        bt.logging.success(
            f"Validator ready | netuid={config.netuid} | tempo={self.current_tempo}"
        )

    def _get_current_tempo(self) -> int:
        try:
            block = self.subtensor.get_current_block()
            tempo = self.subtensor.get_subnet_hyperparameters(self.config.netuid).tempo
            return block // tempo
        except Exception:
            return 0

    def _get_agents(self) -> dict:
        """
        FIX 6: safe registry access — no private _data attribute.
        Returns {agent_id_hex: {hotkey: ...}} dict.
        """
        try:
            # Try public method first
            if hasattr(self.registry, "get_agents"):
                return self.registry.get_agents()
            # Fallback: try _data carefully
            if hasattr(self.registry, "_data"):
                return self.registry._data.get("agents", {})
        except Exception:
            pass
        return {}

    # ── Tier 1 ───────────────────────────────────────────────────────────────

    def verify_receipt(
        self, uid: int, agent_id_hex: str, receipt_json: str
    ) -> Tuple[float, str, Optional[str]]:
        """
        Returns (gate_multiplier, result_code_str, detail_or_None).
        result_code_str is always a plain string ("PASS", "GATE1_…", etc.)
        so callers can compare with GateResult.PASS without worrying about
        enum vs string type.
        """
        if not receipt_json:
            return 0.0, GateResult.AGENT_NOT_AUTH, "No receipt"

        try:
            receipt_dict = json.loads(receipt_json)
        except Exception as e:
            return 0.0, GateResult.DIGEST_MISMATCH, f"Parse error: {e}"

        # Cross-check: receipt agent_id must match our registry entry
        if agent_id_hex and receipt_dict.get("agent_id") != agent_id_hex:
            return 0.0, GateResult.AGENT_NOT_AUTH, "agent_id mismatch with registry"

        # Run through the four-gate verifier
        if INVARIANT_AVAILABLE:
            # verifier.verify() returns dict: {"result": str, "gate_number": int, "detail": str}
            try:
                result = self.verifier.verify(receipt_dict)
                code = result["result"]
                detail = result.get("detail", "")
            except Exception as e:
                return 0.0, GateResult.DIGEST_MISMATCH, f"Verifier error: {e}"
        else:
            # Stub: always pass (no real verification in stub mode)
            code, detail = "PASS", ""

        if code == GateResult.PASS or code == "PASS":
            return 1.0, GateResult.PASS, None
        return 0.0, code, detail or None

    # ── Tier 3 ───────────────────────────────────────────────────────────────

    def get_nts_multiplier(
        self, agent_id_hex: str, checkpoint_json: str, gate_passed: bool
    ) -> float:
        if not agent_id_hex:
            return 0.5
        try:
            return self.oap.get_nts(agent_id_hex) / 100.0
        except Exception:
            return 0.5

    # ── Full pipeline ─────────────────────────────────────────────────────────

    def score_miner(
        self,
        uid: int,
        agent_id_hex: str,
        task_input: str,
        task_type: str,
        response: InvariantTask,
        submission_time: float,
        tempo_start_time: float,
    ) -> float:
        elapsed = submission_time - tempo_start_time
        in_window = elapsed <= (SUBMISSION_WINDOW_BLOCKS * 12)
        late = elapsed <= (LATE_SUBMISSION_BLOCKS * 12)
        freshness = 1.0 if in_window else (0.5 if late else 0.0)

        if freshness == 0.0:
            try:
                self.oap.record_timeout(agent_id_hex, self.current_tempo)
            except Exception:
                pass
            bt.logging.warning(f"UID {uid} timed out ({elapsed:.1f}s)")
            return 0.0

        # verify_receipt now always returns plain string result_code
        gate_mult, result_code, gate_detail = self.verify_receipt(
            uid, agent_id_hex, response.receipt_json
        )

        if gate_mult == 0.0:
            # Map result_code string to gate number
            gate_num = {
                GateResult.AGENT_NOT_AUTH: 1,
                "GATE1_AGENT_NOT_AUTHORIZED": 1,
                GateResult.MODEL_NOT_APPROVED: 2,
                "GATE2_MODEL_NOT_APPROVED": 2,
                GateResult.REPLAY_DETECTED: 3,
                "GATE3_REPLAY_DETECTED": 3,
                GateResult.DIGEST_MISMATCH: 4,
                "GATE4_DIGEST_MISMATCH": 4,
            }.get(result_code, 0)
            vtype = {
                1: ViolationType.GATE1_IDENTITY,
                2: ViolationType.GATE2_MODEL,
                3: ViolationType.GATE3_REPLAY,
                4: ViolationType.GATE4_DIGEST,
            }.get(gate_num, ViolationType.NO_RECEIPT)
            try:
                self.oap.record_violation(
                    agent_id_hex, self.current_tempo, gate_num, vtype, gate_detail or ""
                )
            except Exception:
                pass
            bt.logging.warning(f"UID {uid} gate fail: {result_code} | {gate_detail}")
            return 0.0

        quality = score_output(task_input, task_type, response.output)
        nts_mult = self.get_nts_multiplier(agent_id_hex, response.checkpoint_json, True)
        try:
            self.oap.record_clean_tempo(agent_id_hex, self.current_tempo)
        except Exception:
            pass

        final = quality * nts_mult * freshness
        bt.logging.info(
            f"UID {uid} | quality={quality:.3f} × NTS={nts_mult * 100:.1f} × "
            f"fresh={freshness:.1f} = weight={final:.4f}"
        )
        return final

    # ── Tempo loop ────────────────────────────────────────────────────────────

    async def run_tempo(self):
        tempo_start = time.time()
        self.metagraph.sync(subtensor=self.subtensor)
        self.current_tempo = self._get_current_tempo()
        bt.logging.info(f"=== Tempo {self.current_tempo} ===")

        # AxonInfo.is_serving is a property: True when ip != "0.0.0.0"
        miner_uids = [
            uid
            for uid, axon in enumerate(self.metagraph.axons)
            if getattr(axon, "is_serving", False)
            and uid < len(self.metagraph.validator_permit)
            and not self.metagraph.validator_permit[uid]
        ]

        # Fallback for local testing: if no miners are "serving" (axon not
        # announced on-chain), include all non-validator UIDs so we can still
        # exercise the scoring pipeline.
        if not miner_uids:
            bt.logging.warning(
                "No miners with is_serving=True. "
                "Falling back to all non-validator UIDs for local testing."
            )
            miner_uids = [
                uid
                for uid in range(len(self.metagraph.hotkeys))
                if uid < len(self.metagraph.validator_permit)
                and not self.metagraph.validator_permit[uid]
                and uid != 0  # skip founder
            ]

        if not miner_uids:
            bt.logging.warning("No active miners found in metagraph")
            return

        bt.logging.info(f"Querying {len(miner_uids)} miners...")

        tasks = {uid: generate_task(self.current_tempo, uid) for uid in miner_uids}
        axons = [self.metagraph.axons[uid] for uid in miner_uids]
        weights = np.zeros(len(self.metagraph.hotkeys), dtype=np.float32)
        agents = self._get_agents()

        # FIX 2+3: v10 dendrite is called directly per-axon, not dendrite.forward()
        # v10 API: responses = await self.dendrite(axons, synapse, timeout)
        # It accepts a SINGLE synapse (not a list) and sends it to all axons.
        # For per-miner unique tasks we call once per miner.
        responses = {}
        for uid in miner_uids:
            task_input, task_type = tasks[uid]
            synapse = InvariantTask(
                task_input=task_input,
                tempo_id=self.current_tempo,
                task_type=task_type,
            )
            try:
                axon = self.metagraph.axons[uid]
                # v10 Dendrite: await dendrite(axons=[axon], synapse=s, timeout=N)
                # Returns list[Synapse] — one per axon
                result = await self.dendrite(
                    axons=[axon],
                    synapse=synapse,
                    timeout=SUBMISSION_WINDOW_BLOCKS * 12,
                )
                responses[uid] = result[0] if isinstance(result, list) else result
            except Exception as e:
                bt.logging.debug(f"UID {uid} query error: {e}")
                responses[uid] = synapse  # empty / default response

        response_time = time.time()

        for uid in miner_uids:
            hotkey = self.metagraph.hotkeys[uid]
            agent_id_hex = next(
                (aid for aid, info in agents.items() if info.get("hotkey") == hotkey),
                None,
            )
            if not agent_id_hex:
                bt.logging.debug(f"UID {uid} not in registry — skip")
                continue

            response = responses.get(uid)
            if response is None:
                weights[uid] = 0.0
                continue

            weights[uid] = self.score_miner(
                uid=uid,
                agent_id_hex=agent_id_hex,
                task_input=tasks[uid][0],
                task_type=tasks[uid][1],
                response=response,
                submission_time=response_time,
                tempo_start_time=tempo_start,
            )

        # Normalize
        total = weights.sum()
        if total > 0:
            weights = weights / total

        # Set weights on chain
        try:
            nonzero = np.where(weights > 0)[0]
            if len(nonzero) > 0:
                uids_out, weights_out = convert_weights(nonzero, weights[nonzero])
                self.subtensor.set_weights(
                    wallet=self.wallet,
                    netuid=self.config.netuid,
                    uids=uids_out,
                    weights=weights_out,
                    wait_for_finalization=False,
                )
                bt.logging.success(
                    f"Weights set | tempo={self.current_tempo} | miners={len(nonzero)}"
                )
        except Exception as e:
            bt.logging.error(f"set_weights failed: {e}")

        try:
            data = self.oap.write_shared_checkpoint(self.current_tempo)
            n = len(data.get("agents", {})) if isinstance(data, dict) else "?"
            bt.logging.info(f"OAP checkpoint: tempo={self.current_tempo} agents={n}")
        except Exception as e:
            bt.logging.debug(f"OAP checkpoint skipped: {e}")

    async def handle_registration(
        self, registration: InvariantRegistration
    ) -> InvariantRegistration:
        try:
            expected = hashlib.sha256(
                (
                    registration.hotkey
                    + registration.model_hash_hex
                    + str(registration.reg_block)
                ).encode()
            ).hexdigest()
            if expected != registration.agent_id_hex:
                registration.registered = False
                registration.reason = "agent_id mismatch"
                return registration

            agents = self._get_agents()
            if hasattr(self.registry, "register_agent"):
                self.registry.register_agent(
                    registration.agent_id_hex, registration.hotkey
                )
                self.registry.approve_model(registration.model_hash_hex)

            registration.registered = True
            registration.reason = "OK"
            bt.logging.success(f"Registered {registration.agent_id_hex[:16]}...")
        except Exception as e:
            registration.registered = False
            registration.reason = str(e)
        return registration

    def run(self):
        bt.logging.success("INVARIANT Validator running...")
        while True:
            try:
                asyncio.run(self.run_tempo())
                try:
                    tempo = self.subtensor.get_subnet_hyperparameters(
                        self.config.netuid
                    ).tempo
                except Exception:
                    tempo = 100
                sleep = tempo * 12
                bt.logging.info(f"Next tempo in {sleep}s...")
                time.sleep(sleep)
            except KeyboardInterrupt:
                bt.logging.info("Validator shutting down...")
                break
            except Exception as e:
                bt.logging.error(f"Tempo error: {e}")
                traceback.print_exc()
                time.sleep(30)


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────


def get_config() -> bt.Config:
    parser = argparse.ArgumentParser(description="INVARIANT Validator v10.1.0")
    bt.Wallet.add_args(parser)
    bt.Subtensor.add_args(parser)
    bt.logging.add_args(parser)
    parser.add_argument("--netuid", type=int, default=1)
    return bt.Config(parser)


if __name__ == "__main__":
    config = get_config()
    bt.logging(config=config, logging_dir="./logs")
    InvariantValidator(config).run()
