"""
INVARIANT - Phase 1: OAP Trust Score Engine
=============================================
Lifecycle behavioral history + trust scoring.
Layer 3 of the INVARIANT stack.

This engine maintains an append-only behavioral ledger per miner.
No silent resets. No hidden forgiveness. History is permanent.

The NTS (INVARIANT Trust Score) is a deterministic 0-100 value
that multiplies directly against emission weights in Bittensor.

High NTS = higher ceiling on TAO earnings.
Low NTS = permanently reduced earnings until history is rebuilt.
"""

import json
import time
import math
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from enum import Enum


# ─────────────────────────────────────────────
# CONSTANTS — Tunable via subnet hyperparameters
# ─────────────────────────────────────────────

NTS_START_SCORE        = 50.0   # Cold-start score (neutral, not punished)
NTS_MAX_SCORE          = 100.0
NTS_MIN_SCORE          = 0.0
NTS_CATASTROPHIC_CAP   = 40.0   # Score cap after catastrophic violation (permanent)

# Scar severity by gate failure (gate number → deduction)
GATE_SCAR_WEIGHTS = {
    1: 25.0,  # Identity failure — most severe (Sybil signal)
    2: 15.0,  # Model mismatch — medium (drift/swap signal)
    3: 20.0,  # Replay attempt — high (deliberate attack signal)
    4: 25.0,  # Digest tamper — most severe (active forgery signal)
}

# Consistency bonus per clean tempo
CONSISTENCY_BONUS_PER_TEMPO  = 0.5
CONSISTENCY_BONUS_MAX        = 10.0  # Never more than 10 bonus points from streaks

# Minor violation decay: recover DECAY_RATE points per clean tempo
MINOR_DECAY_RATE             = 0.3
MINOR_VIOLATION_THRESHOLD    = 10.0  # Scars below this are "minor" (decay-eligible)

# Adaptive anchoring thresholds
ANCHOR_HIGH_NTS_INTERVAL     = 10    # tempos between anchors for trusted miners
ANCHOR_MED_NTS_INTERVAL      = 5
ANCHOR_LOW_NTS_INTERVAL      = 1     # every tempo (maximum surveillance)
HIGH_NTS_THRESHOLD           = 80.0
MED_NTS_THRESHOLD            = 40.0

# Override governance
MAX_OVERRIDES_PER_YEAR       = 2


class ViolationType(Enum):
    GATE1_IDENTITY   = "gate1_identity_failure"
    GATE2_MODEL      = "gate2_model_failure"
    GATE3_REPLAY     = "gate3_replay_attempt"
    GATE4_DIGEST     = "gate4_digest_tamper"
    TIMEOUT          = "submission_timeout"
    NO_RECEIPT       = "no_receipt_submitted"


@dataclass
class ViolationEvent:
    """A single recorded violation. Append-only. Never deleted."""
    tempo_id:       int
    violation_type: str
    gate_number:    Optional[int]
    severity:       float          # Scar weight applied
    timestamp:      float
    detail:         str = ""
    is_catastrophic: bool = False


@dataclass
class TrustCheckpoint:
    """
    Signed integrity state submitted by miner alongside receipt.
    Validator verifies the signature and uses the NTS as an emission multiplier.
    """
    agent_id_hex:     str
    nts_score:        float
    total_tempos:     int
    clean_streak:     int          # consecutive tempos without violations
    total_violations: int
    is_catastrophically_flagged: bool
    checkpoint_tempo: int
    timestamp:        float
    # In Phase 2 this will be signed with miner's hotkey
    # For Phase 1: computed deterministically, validator recomputes to verify


@dataclass 
class MinerLedger:
    """
    Per-miner append-only behavioral ledger.
    This is the core OAP data structure.
    
    Once written, records are never deleted.
    The only mutation is appending new entries.
    """
    agent_id_hex:              str
    hotkey:                    str
    registration_tempo:        int
    
    nts_score:                 float = NTS_START_SCORE
    total_tempos:              int   = 0
    clean_tempos:              int   = 0
    violation_tempos:          int   = 0
    clean_streak:              int   = 0
    max_clean_streak:          int   = 0
    
    is_catastrophically_flagged: bool = False
    flag_reason:               str   = ""
    
    accumulated_scar:          float = 0.0  # Total unrecovered scar load
    minor_scar_recoverable:    float = 0.0  # Portion eligible for decay
    
    violations:                List[dict] = field(default_factory=list)
    override_log:              List[dict] = field(default_factory=list)
    
    last_anchor_tempo:         int   = 0
    next_anchor_tempo:         int   = 1


class OAPEngine:
    """
    The OAP (Orthonode Adaptive Protocol) Trust Score Engine.
    
    Maintains per-miner ledgers. Updates scores after each tempo.
    Provides checkpoint generation and adaptive anchoring decisions.
    
    Phase 1: File-backed storage.
    Phase 2: Subtensor extrinsic anchoring.
    """
    
    def __init__(self, storage_path: str = "./invariant_oap_ledgers.json"):
        self.storage_path = storage_path
        self._ledgers: Dict[str, MinerLedger] = {}
        self._load()
    
    # ── Storage ──────────────────────────────────────────────────
    
    def _load(self):
        try:
            with open(self.storage_path, "r") as f:
                raw = json.load(f)
                for agent_id, data in raw.items():
                    # Reconstruct ledger from dict
                    ledger = MinerLedger(**{
                        k: v for k, v in data.items()
                        if k in MinerLedger.__dataclass_fields__
                    })
                    self._ledgers[agent_id] = ledger
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            self._ledgers = {}
    
    def _save(self):
        raw = {}
        for agent_id, ledger in self._ledgers.items():
            raw[agent_id] = asdict(ledger)
        with open(self.storage_path, "w") as f:
            json.dump(raw, f, indent=2)
    
    # ── Ledger Access ─────────────────────────────────────────────
    
    def get_or_create_ledger(self, agent_id_hex: str, hotkey: str, 
                              registration_tempo: int = 0) -> MinerLedger:
        """Get existing ledger or create new one for a miner."""
        if agent_id_hex not in self._ledgers:
            self._ledgers[agent_id_hex] = MinerLedger(
                agent_id_hex       = agent_id_hex,
                hotkey             = hotkey,
                registration_tempo = registration_tempo,
                next_anchor_tempo  = registration_tempo + ANCHOR_MED_NTS_INTERVAL,
            )
            self._save()
        return self._ledgers[agent_id_hex]
    
    def get_nts(self, agent_id_hex: str) -> float:
        """Get current NTS score. Returns cold-start score if not registered."""
        if agent_id_hex not in self._ledgers:
            return NTS_START_SCORE
        return self._ledgers[agent_id_hex].nts_score
    
    # ── Score Update (called after each tempo) ────────────────────
    
    def record_clean_tempo(self, agent_id_hex: str, tempo_id: int) -> float:
        """
        Record a clean tempo (receipt passed all gates, output quality > 0).
        
        Applies:
        - Minor scar decay
        - Consistency bonus accumulation
        - Clean streak increment
        
        Returns: Updated NTS score
        """
        ledger = self._ledgers.get(agent_id_hex)
        if not ledger:
            return NTS_START_SCORE
        
        ledger.total_tempos    += 1
        ledger.clean_tempos    += 1
        ledger.clean_streak    += 1
        ledger.max_clean_streak = max(ledger.max_clean_streak, ledger.clean_streak)
        
        # Decay minor scars
        if ledger.minor_scar_recoverable > 0:
            decay = min(MINOR_DECAY_RATE, ledger.minor_scar_recoverable)
            ledger.minor_scar_recoverable -= decay
            ledger.accumulated_scar       -= decay
        
        # Consistency bonus (logarithmic — not linear, to prevent score farming)
        if ledger.clean_streak > 0:
            bonus = min(
                CONSISTENCY_BONUS_PER_TEMPO * math.log1p(ledger.clean_streak),
                CONSISTENCY_BONUS_MAX
            )
        else:
            bonus = 0.0
        
        # Recompute score
        ledger.nts_score = self._compute_nts(ledger, extra_bonus=bonus)
        ledger.last_anchor_tempo = tempo_id
        
        self._update_anchor_schedule(ledger, tempo_id)
        self._save()
        return ledger.nts_score
    
    def record_violation(
        self,
        agent_id_hex:   str,
        tempo_id:       int,
        gate_number:    int,
        violation_type: ViolationType,
        detail:         str = "",
    ) -> Tuple[float, bool]:
        """
        Record a gate failure / violation.
        
        Applies scar accumulation.
        Checks for catastrophic violation escalation.
        Resets clean streak.
        
        Returns: (updated_nts_score, is_catastrophically_flagged)
        """
        ledger = self._ledgers.get(agent_id_hex)
        if not ledger:
            return NTS_START_SCORE, False
        
        severity = GATE_SCAR_WEIGHTS.get(gate_number, 10.0)
        
        # Determine if catastrophic
        # Catastrophic = Gate 3 failure after already having Gate 3 violations
        is_catastrophic = False
        prior_gate3 = sum(
            1 for v in ledger.violations
            if v.get("gate_number") == 3
        )
        if gate_number == 3 and prior_gate3 >= 2:
            is_catastrophic = True
            ledger.is_catastrophically_flagged = True
            ledger.flag_reason = f"Repeated replay attacks: {prior_gate3 + 1} Gate 3 failures"
        
        # Append violation (immutable history)
        event = {
            "tempo_id":       tempo_id,
            "violation_type": violation_type.value,
            "gate_number":    gate_number,
            "severity":       severity,
            "timestamp":      time.time(),
            "detail":         detail,
            "is_catastrophic": is_catastrophic,
        }
        ledger.violations.append(event)
        
        # Update scar state
        ledger.accumulated_scar += severity
        # Minor scars (small severity) are decay-eligible
        if severity < MINOR_VIOLATION_THRESHOLD:
            ledger.minor_scar_recoverable += severity
        
        # Reset streak
        ledger.clean_streak     = 0
        ledger.violation_tempos += 1
        ledger.total_tempos     += 1
        
        # Recompute score
        ledger.nts_score = self._compute_nts(ledger)
        
        self._update_anchor_schedule(ledger, tempo_id)
        self._save()
        return ledger.nts_score, is_catastrophic
    
    def record_timeout(self, agent_id_hex: str, tempo_id: int) -> float:
        """Record a no-receipt / timeout event."""
        return self.record_violation(
            agent_id_hex, tempo_id,
            gate_number=0,
            violation_type=ViolationType.NO_RECEIPT,
            detail="No receipt submitted within tempo window",
        )[0]
    
    # ── Score Computation ─────────────────────────────────────────
    
    def _compute_nts(self, ledger: MinerLedger, extra_bonus: float = 0.0) -> float:
        """
        Deterministic NTS computation from ledger state.
        
        Formula:
            base = NTS_START_SCORE
            penalty_factor = accumulated_scar / (NTS_MAX - NTS_MIN)  [0.0-1.0]
            score = base × (1 - penalty_factor) + recovery_bonus + extra_bonus
            if catastrophically_flagged: score = min(score, NTS_CATASTROPHIC_CAP)
            score = clamp(score, NTS_MIN, NTS_MAX)
        """
        base = NTS_START_SCORE
        
        # Penalty from accumulated scars (diminishing — logarithmic)
        if ledger.accumulated_scar > 0:
            penalty = min(
                base * (1 - math.exp(-ledger.accumulated_scar / 50.0)),
                base
            )
        else:
            penalty = 0.0
        
        # Recovery from clean history
        if ledger.total_tempos > 0:
            clean_ratio = ledger.clean_tempos / ledger.total_tempos
            recovery = (NTS_MAX_SCORE - base) * clean_ratio * 0.8  # 80% recovery ceiling
        else:
            recovery = 0.0
        
        score = base - penalty + recovery + extra_bonus
        
        # Catastrophic cap (permanent)
        if ledger.is_catastrophically_flagged:
            score = min(score, NTS_CATASTROPHIC_CAP)
        
        return max(NTS_MIN_SCORE, min(NTS_MAX_SCORE, score))
    
    # ── Adaptive Anchoring ────────────────────────────────────────
    
    def _update_anchor_schedule(self, ledger: MinerLedger, current_tempo: int):
        """Update anchor schedule based on current NTS."""
        nts = ledger.nts_score
        if nts >= HIGH_NTS_THRESHOLD:
            interval = ANCHOR_HIGH_NTS_INTERVAL
        elif nts >= MED_NTS_THRESHOLD:
            interval = ANCHOR_MED_NTS_INTERVAL
        else:
            interval = ANCHOR_LOW_NTS_INTERVAL
        
        ledger.next_anchor_tempo = current_tempo + interval
    
    def should_anchor(self, agent_id_hex: str, current_tempo: int) -> bool:
        """Should this miner submit a checkpoint this tempo?"""
        ledger = self._ledgers.get(agent_id_hex)
        if not ledger:
            return True  # New miners always anchor
        return current_tempo >= ledger.next_anchor_tempo
    
    # ── Checkpoint Generation ─────────────────────────────────────
    
    def generate_checkpoint(self, agent_id_hex: str, current_tempo: int) -> TrustCheckpoint:
        """
        Generate a signed trust checkpoint for submission.
        Miner submits this alongside their receipt.
        Validator recomputes to verify.
        """
        ledger = self._ledgers.get(agent_id_hex)
        if not ledger:
            return TrustCheckpoint(
                agent_id_hex     = agent_id_hex,
                nts_score        = NTS_START_SCORE,
                total_tempos     = 0,
                clean_streak     = 0,
                total_violations = 0,
                is_catastrophically_flagged = False,
                checkpoint_tempo = current_tempo,
                timestamp        = time.time(),
            )
        
        return TrustCheckpoint(
            agent_id_hex     = agent_id_hex,
            nts_score        = ledger.nts_score,
            total_tempos     = ledger.total_tempos,
            clean_streak     = ledger.clean_streak,
            total_violations = len(ledger.violations),
            is_catastrophically_flagged = ledger.is_catastrophically_flagged,
            checkpoint_tempo = current_tempo,
            timestamp        = time.time(),
        )
    
    # ── Emission Weight ───────────────────────────────────────────
    
    @staticmethod
    def compute_emission_weight(
        output_quality: float,   # 0.0 - 1.0 from validator's quality scorer
        nts_score:      float,   # 0 - 100 from OAP engine
        submitted_in_window: bool = True,
        late_submission: bool = False,
    ) -> float:
        """
        Compute final emission weight for Yuma Consensus.
        
        Formula:
            weight = output_quality × (nts_score / 100) × freshness_factor
        
        This is the value set via subtensor.set_weights().
        """
        freshness = 1.0 if submitted_in_window else (0.5 if late_submission else 0.0)
        nts_multiplier = nts_score / NTS_MAX_SCORE
        return output_quality * nts_multiplier * freshness
    
    # ── Override Governance ────────────────────────────────────────
    
    def apply_override(
        self,
        agent_id_hex:    str,
        new_nts:         float,
        reason:          str,
        authorized_by:   str,
        current_year:    int,
    ) -> Tuple[bool, str]:
        """
        Apply a governance override to a miner's NTS.
        Maximum 2 overrides per agent per rolling year.
        All overrides are logged immutably.
        
        Returns: (success, message)
        """
        ledger = self._ledgers.get(agent_id_hex)
        if not ledger:
            return False, "Agent not found"
        
        # Count overrides this year
        this_year_overrides = sum(
            1 for o in ledger.override_log
            if o.get("year") == current_year
        )
        
        if this_year_overrides >= MAX_OVERRIDES_PER_YEAR:
            return False, f"Override cap reached: {this_year_overrides}/{MAX_OVERRIDES_PER_YEAR} for {current_year}"
        
        old_nts = ledger.nts_score
        ledger.nts_score = max(NTS_MIN_SCORE, min(NTS_MAX_SCORE, new_nts))
        
        ledger.override_log.append({
            "timestamp":     time.time(),
            "year":          current_year,
            "old_nts":       old_nts,
            "new_nts":       ledger.nts_score,
            "reason":        reason,
            "authorized_by": authorized_by,
        })
        
        self._save()
        return True, f"Override applied: {old_nts:.1f} → {ledger.nts_score:.1f}"
    
    # ── Stats & Reporting ─────────────────────────────────────────
    
    def get_stats(self, agent_id_hex: str) -> dict:
        """Get full stats for a miner. Used by the cross-subnet API."""
        ledger = self._ledgers.get(agent_id_hex)
        if not ledger:
            return {"agent_id": agent_id_hex, "nts": NTS_START_SCORE, "status": "unregistered"}
        
        return {
            "agent_id":      agent_id_hex,
            "nts_score":     ledger.nts_score,
            "total_tempos":  ledger.total_tempos,
            "clean_tempos":  ledger.clean_tempos,
            "violation_count": len(ledger.violations),
            "clean_streak":  ledger.clean_streak,
            "max_streak":    ledger.max_clean_streak,
            "catastrophic":  ledger.is_catastrophically_flagged,
            "flag_reason":   ledger.flag_reason,
            "recent_violations": ledger.violations[-5:],  # Last 5 only
        }


# ─────────────────────────────────────────────
# SELF-TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import os
    test_path = "/tmp/test_oap.json"
    if os.path.exists(test_path):
        os.remove(test_path)
    
    engine = OAPEngine(test_path)
    agent  = "deadbeef" * 8  # 64-char hex
    
    engine.get_or_create_ledger(agent, "5FakeHotkey", registration_tempo=100)
    
    print("=" * 60)
    print("INVARIANT OAP Engine Self-Test")
    print("=" * 60)
    
    # Test cold start
    assert engine.get_nts(agent) == 50.0, "Cold start should be 50"
    print(f"✅ Cold start NTS: {engine.get_nts(agent)}")
    
    # Test clean tempos build score
    for t in range(101, 121):
        engine.record_clean_tempo(agent, t)
    score_after_20_clean = engine.get_nts(agent)
    assert score_after_20_clean > 50.0, f"Score should rise after clean tempos: {score_after_20_clean}"
    print(f"✅ After 20 clean tempos: NTS = {score_after_20_clean:.2f}")
    
    # Test violation drops score
    score_before = engine.get_nts(agent)
    engine.record_violation(agent, 121, 4, ViolationType.GATE4_DIGEST, "test violation")
    score_after = engine.get_nts(agent)
    assert score_after < score_before, f"Violation should drop score: {score_before} → {score_after}"
    print(f"✅ After Gate 4 violation: NTS = {score_after:.2f} (was {score_before:.2f})")
    
    # Test emission weight
    weight = OAPEngine.compute_emission_weight(
        output_quality = 1.0,
        nts_score      = score_after,
        submitted_in_window = True,
    )
    print(f"✅ Emission weight (quality=1.0, NTS={score_after:.1f}): {weight:.4f}")
    
    # Test catastrophic flagging
    for _ in range(3):
        engine.record_violation(agent, 122, 3, ViolationType.GATE3_REPLAY, "repeated replay")
    ledger = engine._ledgers[agent]
    assert ledger.is_catastrophically_flagged, "Should be catastrophically flagged after 3x Gate 3"
    assert engine.get_nts(agent) <= 40.0, "Catastrophic cap should be enforced"
    print(f"✅ Catastrophic flag: NTS capped at {engine.get_nts(agent):.2f} (cap={NTS_CATASTROPHIC_CAP})")
    
    # Test stats
    stats = engine.get_stats(agent)
    print(f"✅ Stats: {stats['total_tempos']} tempos, {stats['violation_count']} violations")
    
    print()
    print("All OAP engine tests passed.")
