"""
invariant/phase1_core/invariant_oap.py
=======================================
OAP (Orthonode Adaptive Protocol) trust score engine — Layer 3.
Append-only behavioral ledger per miner.  No silent resets.

Import via the bridge:
    from invariant_gates_bridge import ...  (gates)
    from invariant_oap import OAPEngine     (lifecycle trust)
"""

import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

NTS_START = 50.0
NTS_MAX = 100.0
NTS_MIN = 0.0
NTS_CATASTROPHIC = 40.0  # permanent cap after catastrophic flag

GATE_SCAR = {1: 25.0, 2: 15.0, 3: 20.0, 4: 25.0}
CONSISTENCY_BONUS_RATE = 0.5
CONSISTENCY_BONUS_MAX = 10.0
MINOR_DECAY_RATE = 0.3
MINOR_THRESH = 10.0

ANCHOR_HIGH = 10  # tempos between anchors for NTS ≥ 80
ANCHOR_MED = 5  # NTS 40-79
ANCHOR_LOW = 1  # NTS < 40 (every tempo)
HIGH_NTS = 80.0
MED_NTS = 40.0
MAX_OVERRIDES = 2


class ViolationType(Enum):
    GATE1 = "gate1_identity_failure"
    GATE2 = "gate2_model_failure"
    GATE3 = "gate3_replay_attempt"
    GATE4 = "gate4_digest_tamper"
    TIMEOUT = "submission_timeout"
    NO_RECEIPT = "no_receipt_submitted"


@dataclass
class MinerLedger:
    agent_id_hex: str
    hotkey: str
    reg_tempo: int
    nts: float = NTS_START
    total: int = 0
    clean: int = 0
    violations: int = 0
    streak: int = 0
    max_streak: int = 0
    catastrophic: bool = False
    flag_reason: str = ""
    scar: float = 0.0
    minor_scar: float = 0.0
    violation_log: List[dict] = field(default_factory=list)
    override_log: List[dict] = field(default_factory=list)
    last_anchor: int = 0
    next_anchor: int = 1


class OAPEngine:
    def __init__(self, path: str = "./oap_ledgers.json"):
        self.path = path
        self._ledgers: Dict[str, MinerLedger] = {}
        self._load()

    def _load(self):
        try:
            with open(self.path) as f:
                for k, v in json.load(f).items():
                    try:
                        self._ledgers[k] = MinerLedger(
                            **{
                                fk: fv
                                for fk, fv in v.items()
                                if fk in MinerLedger.__dataclass_fields__
                            }
                        )
                    except Exception:
                        pass
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save(self):
        with open(self.path, "w") as f:
            json.dump({k: asdict(v) for k, v in self._ledgers.items()}, f, indent=2)

    def get_or_create(
        self, agent_id_hex: str, hotkey: str, reg_tempo: int = 0
    ) -> MinerLedger:
        if agent_id_hex not in self._ledgers:
            self._ledgers[agent_id_hex] = MinerLedger(
                agent_id_hex=agent_id_hex,
                hotkey=hotkey,
                reg_tempo=reg_tempo,
                next_anchor=reg_tempo + ANCHOR_MED,
            )
            self._save()
        return self._ledgers[agent_id_hex]

    def get_nts(self, agent_id_hex: str) -> float:
        return (
            self._ledgers[agent_id_hex].nts
            if agent_id_hex in self._ledgers
            else NTS_START
        )

    def _compute_nts(self, L: MinerLedger, bonus: float = 0.0) -> float:
        penalty = (
            min(NTS_START * (1 - math.exp(-L.scar / 50.0)), NTS_START)
            if L.scar > 0
            else 0.0
        )
        recovery = (
            (NTS_MAX - NTS_START) * (L.clean / L.total) * 0.8 if L.total > 0 else 0.0
        )
        score = NTS_START - penalty + recovery + bonus
        if L.catastrophic:
            score = min(score, NTS_CATASTROPHIC)
        return max(NTS_MIN, min(NTS_MAX, score))

    def _update_anchor(self, L: MinerLedger, tempo: int):
        interval = (
            ANCHOR_HIGH
            if L.nts >= HIGH_NTS
            else (ANCHOR_MED if L.nts >= MED_NTS else ANCHOR_LOW)
        )
        L.next_anchor = tempo + interval

    def record_clean(self, agent_id_hex: str, tempo: int) -> float:
        L = self._ledgers.get(agent_id_hex)
        if not L:
            return NTS_START
        L.total += 1
        L.clean += 1
        L.streak += 1
        L.max_streak = max(L.max_streak, L.streak)
        if L.minor_scar > 0:
            d = min(MINOR_DECAY_RATE, L.minor_scar)
            L.minor_scar -= d
            L.scar -= d
        bonus = min(
            CONSISTENCY_BONUS_RATE * math.log1p(L.streak), CONSISTENCY_BONUS_MAX
        )
        L.nts = self._compute_nts(L, bonus)
        L.last_anchor = tempo
        self._update_anchor(L, tempo)
        self._save()
        return L.nts

    def record_violation(
        self,
        agent_id_hex: str,
        tempo: int,
        gate: int,
        vtype: ViolationType,
        detail: str = "",
    ) -> Tuple[float, bool]:
        L = self._ledgers.get(agent_id_hex)
        if not L:
            return NTS_START, False
        severity = GATE_SCAR.get(gate, 10.0)
        prior_g3 = sum(1 for v in L.violation_log if v.get("gate") == 3)
        catastrophic = gate == 3 and prior_g3 >= 2
        if catastrophic:
            L.catastrophic = True
            L.flag_reason = f"Repeated replay: {prior_g3 + 1}x Gate 3"
        L.violation_log.append(
            {
                "tempo": tempo,
                "type": vtype.value,
                "gate": gate,
                "severity": severity,
                "ts": time.time(),
                "detail": detail,
                "catastrophic": catastrophic,
            }
        )
        L.scar += severity
        if severity < MINOR_THRESH:
            L.minor_scar += severity
        L.streak = 0
        L.violations += 1
        L.total += 1
        L.nts = self._compute_nts(L)
        self._update_anchor(L, tempo)
        self._save()
        return L.nts, catastrophic

    def record_timeout(self, agent_id_hex: str, tempo: int) -> float:
        return self.record_violation(
            agent_id_hex, tempo, 0, ViolationType.NO_RECEIPT, "timeout"
        )[0]

    def should_anchor(self, agent_id_hex: str, tempo: int) -> bool:
        L = self._ledgers.get(agent_id_hex)
        return True if not L else tempo >= L.next_anchor

    def checkpoint(self, agent_id_hex: str, tempo: int) -> dict:
        L = self._ledgers.get(agent_id_hex)
        if not L:
            return {
                "agent_id_hex": agent_id_hex,
                "nts": NTS_START,
                "total": 0,
                "streak": 0,
                "violations": 0,
                "catastrophic": False,
                "tempo": tempo,
                "ts": time.time(),
            }
        return {
            "agent_id_hex": agent_id_hex,
            "nts": L.nts,
            "total": L.total,
            "streak": L.streak,
            "violations": len(L.violation_log),
            "catastrophic": L.catastrophic,
            "tempo": tempo,
            "ts": time.time(),
        }

    def write_shared_checkpoint(
        self, tempo: int, shared_path: str = "/tmp/invariant_oap_checkpoint.json"
    ):
        """Write OAP state to shared file for validator consensus."""
        checkpoint_data = {"tempo": tempo, "timestamp": time.time(), "agents": {}}

        for agent_id_hex, ledger in self._ledgers.items():
            checkpoint_data["agents"][agent_id_hex] = self.checkpoint(
                agent_id_hex, tempo
            )

        # Atomic write to prevent corruption
        temp_path = shared_path + ".tmp"
        with open(temp_path, "w") as f:
            json.dump(checkpoint_data, f, indent=2)
        os.rename(temp_path, shared_path)

        return checkpoint_data

    def load_shared_checkpoint(
        self, shared_path: str = "/tmp/invariant_oap_checkpoint.json"
    ):
        """Load OAP state from shared file for validator consensus."""
        try:
            with open(shared_path, "r") as f:
                checkpoint_data = json.load(f)

            tempo = checkpoint_data.get("tempo", 0)
            timestamp = checkpoint_data.get("timestamp", 0)

            # Merge checkpoint data into current state
            for agent_id_hex, agent_data in checkpoint_data.get("agents", {}).items():
                if agent_id_hex not in self._ledgers:
                    # Create new ledger from checkpoint (best-effort restore)
                    nts_val = agent_data.get("nts", NTS_START)
                    self._ledgers[agent_id_hex] = MinerLedger(
                        agent_id_hex=agent_data.get("agent_id_hex", agent_id_hex),
                        hotkey=agent_data.get("hotkey", ""),
                        reg_tempo=agent_data.get("reg_tempo", 0),
                        nts=nts_val,
                        total=agent_data.get("total", 0),
                        clean=agent_data.get("clean", 0),
                        violations=agent_data.get("violations", 0),
                        streak=agent_data.get("streak", 0),
                        max_streak=agent_data.get("max_streak", 0),
                        catastrophic=agent_data.get("catastrophic", False),
                        flag_reason=agent_data.get("flag_reason", ""),
                        scar=agent_data.get("scar", 0.0),
                        minor_scar=agent_data.get("minor_scar", 0.0),
                        violation_log=[],
                        override_log=[],
                        last_anchor=agent_data.get("last_anchor", 0),
                        next_anchor=self._next_anchor_tempo(nts_val),
                    )

            self._save()
            return tempo, timestamp
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return 0, 0

    def _next_anchor_tempo(self, nts: float) -> int:
        """Calculate next anchor tempo based on NTS score."""
        if nts >= HIGH_NTS:
            return ANCHOR_HIGH
        elif nts >= MED_NTS:
            return ANCHOR_MED
        else:
            return ANCHOR_LOW

    @staticmethod
    def emission_weight(
        quality: float, nts: float, in_window: bool = True, late: bool = False
    ) -> float:
        freshness = 1.0 if in_window else (0.5 if late else 0.0)
        return quality * (nts / NTS_MAX) * freshness

    def apply_override(
        self,
        agent_id_hex: str,
        new_nts: float,
        reason: str,
        authorized_by: str,
        year: int,
    ) -> Tuple[bool, str]:
        L = self._ledgers.get(agent_id_hex)
        if not L:
            return False, "Agent not found"
        this_year = sum(1 for o in L.override_log if o.get("year") == year)
        if this_year >= MAX_OVERRIDES:
            return False, f"Override cap {MAX_OVERRIDES}/yr reached"
        old = L.nts
        L.nts = max(NTS_MIN, min(NTS_MAX, new_nts))
        L.override_log.append(
            {
                "ts": time.time(),
                "year": year,
                "old": old,
                "new": L.nts,
                "reason": reason,
                "by": authorized_by,
            }
        )
        self._save()
        return True, f"{old:.1f} → {L.nts:.1f}"

    def stats(self, agent_id_hex: str) -> dict:
        L = self._ledgers.get(agent_id_hex)
        if not L:
            return {
                "agent_id": agent_id_hex,
                "nts": NTS_START,
                "status": "unregistered",
            }
        return {
            "agent_id": agent_id_hex,
            "nts": L.nts,
            "total": L.total,
            "clean": L.clean,
            "violations": len(L.violation_log),
            "streak": L.streak,
            "max_streak": L.max_streak,
            "catastrophic": L.catastrophic,
            "flag": L.flag_reason,
        }
