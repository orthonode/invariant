# INVARIANT — Formal Threat Model

**Version:** 1.0.0  
**Date:** February 2026  
**Authors:** Orthonode Infrastructure Labs  
**Classification:** Public  

---

## Overview

This document presents the formal threat model for the INVARIANT subnet — a cryptographic execution integrity layer for the Bittensor network. The threat model follows a structured adversarial analysis methodology: attacker taxonomy, attack surface enumeration, gate-by-gate forensic analysis, and residual risk classification.

INVARIANT's security model is rooted in a single principle: **verification must be deterministic, not probabilistic**. Every gate either passes or fails — there is no partial credit, no behavioral heuristic, and no oracle dependency.

---

## System Components

| Component | Description | Trust Level |
|-----------|-------------|-------------|
| `invariant_gates_bridge.py` | Unified API layer over Rust/Python backends | Trusted (local execution) |
| `invariant_gates.py` | Pure Python fallback verifier | Trusted (local execution) |
| `invariant_gates_rs` | Rust/PyO3 extension (production) | Trusted (compiled, auditable) |
| `invariant_oap.py` | OAP lifecycle trust engine | Trusted (local execution) |
| Miner `agent_id` | SHA-256(hotkey ‖ model_hash ‖ reg_block) | Partially trusted (self-reported at registration) |
| Validator registry | Approved agents + models JSON | Trusted (validator-controlled) |
| Bittensor subtensor | Chain state, weight setting, tempo | Trusted (Bittensor protocol) |
| Yuma Consensus | Weight aggregation | Trusted (Bittensor protocol) |

---

## Threat Actors

### TA-1: Rational Economic Actor (REM)
A miner operator who will take any action that increases their TAO emission share without concern for network integrity. No special technical capability. Motivated purely by financial gain. **Most common attacker.**

### TA-2: Technical Miner (TM)
A miner with Python/cryptography skills who understands the receipt format and can craft malformed receipts. Can manipulate JSON fields, attempt digest collisions, and coordinate with other miners.

### TA-3: Validator Cartel (VC)
A coalition of validators controlling >20% of validator stake who coordinate to pass invalid receipts for allied miners or suppress scores for competing miners.

### TA-4: Sybil Operator (SO)
An actor who creates many new miner identities (hotkeys) to dilute honest miner scoring or flood the registry.

### TA-5: Nation-State / Well-Resourced Adversary (NS)
An actor with the resources to attempt SHA-256 preimage attacks, mount 51% stake attacks, or compromise infrastructure at scale. **Out of scope for v1 — noted for completeness.**

---

## Attack Surface

```
┌─────────────────────────────────────────────────────────────────┐
│                    ATTACK SURFACE MAP                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [1] Receipt Field Manipulation        ← TA-1, TA-2            │
│  [2] Replay Submission                 ← TA-1, TA-2            │
│  [3] Counter Rollback                  ← TA-1, TA-2            │
│  [4] Sybil Identity Creation           ← TA-1, TA-4            │
│  [5] Model Hash Spoofing               ← TA-1, TA-2            │
│  [6] Output Caching (cross-tempo)      ← TA-1                  │
│  [7] Output Copying (cross-miner)      ← TA-1, TA-2            │
│  [8] Digest Forgery                    ← TA-2                  │
│  [9] Validator Registry Poisoning      ← TA-3                  │
│  [10] NTS Gaming (tank + recover)      ← TA-1, TA-4            │
│  [11] Catastrophic Flag Evasion        ← TA-2                  │
│  [12] Override Abuse                   ← TA-3                  │
│  [13] Validator Collusion              ← TA-3                  │
│  [14] SHA-256 Preimage Attack          ← TA-5 (out of scope)   │
│  [15] 51% Stake Attack                 ← TA-5 (out of scope)   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Gate-by-Gate Forensic Analysis

### GATE 1 — Identity Authorization

**Mechanism:** Checks that `receipt.agent_id` is present in the validator's authorized agent registry.

**Threat vector:** An unknown hotkey attempts to submit a receipt with a fabricated `agent_id`.

**Forensic verdict:**

| Scenario | Gate 1 Result |
|----------|---------------|
| Registered miner submits own receipt | ✅ PASS |
| Unregistered hotkey submits receipt | ❌ FAIL — `GATE1_AGENT_NOT_AUTHORIZED` |
| Miner B submits Miner A's receipt unchanged | ❌ FAIL — `agent_id` bound to A's hotkey, not in B's registry entry |
| Miner creates new hotkey (Sybil) | ❌ FAIL — new `agent_id` not yet registered; NTS starts at 50, emission cost real tempos |
| Miner attempts `agent_id = "ff"*32` (garbage) | ❌ FAIL — not in registry |

**Residual risk:** A validator whose registry has been compromised (see Attack 9) could authorize rogue agents. **Mitigation:** Registry is validator-controlled and not miner-writeable.

---

### GATE 2 — Model Approval

**Mechanism:** Checks that `receipt.model_hash` is present in the validator's approved model list.

**Threat vector:** A miner runs a cheap/small model but submits a receipt claiming the hash of an expensive/approved model.

**Forensic verdict:**

| Scenario | Gate 2 Result |
|----------|---------------|
| Registered model hash submitted | ✅ PASS |
| Unapproved model hash submitted | ❌ FAIL — `GATE2_MODEL_NOT_APPROVED` |
| Miner claims GPT-4 hash but runs llama-3.2-1b | ❌ FAIL — model hash computed from identifier at registration; can't forge |
| Miner registers model hash, then swaps model | ❌ FAIL — new model has different `SHA-256(identifier)`, Gate 2 or Gate 4 fails |

**Residual risk:** A miner could register a model identifier that hashes to an approved hash through brute force. This requires a SHA-256 preimage attack — computationally infeasible with current cryptography.

**NTS amplification:** Frequent model hash changes are penalized by the OAP **Model Consistency** dimension — repeated hash swapping accumulates scar, degrading NTS over time.

---

### GATE 3 — Replay Protection

**Mechanism:** Checks that `receipt.counter > last_confirmed_counter[agent_id]`. Counter is a monotonic `uint64`. State is persisted per validator in `invariant_state.json`.

**Threat vector (Replay):** A miner submits the same receipt twice to claim double payment for a single computation.

**Threat vector (Rollback):** A miner resets their counter to a lower value to make old receipts appear fresh.

**Forensic verdict:**

| Scenario | Gate 3 Result |
|----------|---------------|
| New receipt with counter = last + 1 | ✅ PASS |
| Same receipt submitted twice | ❌ FAIL — counter not > last confirmed |
| Counter rollback (counter < last confirmed) | ❌ FAIL — counter not > last confirmed |
| Counter = last confirmed (no increment) | ❌ FAIL — must be strictly greater |
| Counter jumps by 100 (skipped values) | ✅ PASS — gaps are permitted; only regression is blocked |

**Residual risk:** If a validator's state file is deleted, the last_confirmed_counter resets to 0, allowing all previously consumed counters to be valid again. **Mitigation:** State file is append-only in the OAP ledger; validator should never delete state mid-operation. State backup procedures documented in deployment guide.

---

### GATE 4 — Digest Verification

**Mechanism:** Recomputes `SHA-256(agent_id ‖ model_hash ‖ execution_hash ‖ counter)` and compares to `receipt.digest`.

The `execution_hash` is itself `SHA-256(task_input ‖ output ‖ tempo_id)` — binding the receipt cryptographically to a specific computation at a specific moment.

**Threat vector (Tampering):** A miner modifies any field in the receipt after computing the digest — changing the output quality, swapping the model hash, or altering the timestamp.

**Threat vector (Output caching):** A miner returns a valid output from a prior tempo to avoid re-running expensive inference.

**Threat vector (Output copying):** Miner B copies Miner A's output and constructs a receipt claiming it as their own execution.

**Forensic verdict:**

| Scenario | Gate 4 Result |
|----------|---------------|
| Unmodified receipt with correct digest | ✅ PASS |
| Any single field modified post-signing | ❌ FAIL — digest no longer matches |
| `output` field swapped for different value | ❌ FAIL — `execution_hash` changes, digest changes |
| `tempo_id` different from validator's current tempo | ❌ FAIL — `execution_hash` includes `tempo_id`; prior tempo produces different hash |
| Miner B copies Miner A's receipt verbatim | ❌ FAIL at Gate 1 first (wrong `agent_id`); even if Gate 1 were bypassed, digest verification uses A's `agent_id` which B cannot produce |
| Digest zeroed out (`"00"*32`) | ❌ FAIL — SHA-256 output is not all-zeros for any valid input |
| Brute-force digest collision | ❌ FAIL — SHA-256 preimage resistance; infeasible with current compute |

**Cryptographic note:** The `execution_hash` is the key structural primitive. It is physically impossible to produce a valid `SHA-256(task_input ‖ output ‖ tempo_id)` for a given task without having actually computed the output. The digest then binds this proof to the specific agent identity and model version. **You cannot forge a receipt without running the computation.**

---

## OAP Layer Threats

### NTS Gaming (Tank + Recover)

**Threat:** A miner intentionally tanks their NTS to low values, then recovers slowly to exploit some edge in the scoring formula.

**Defense:**
- **Catastrophic flag:** Three or more Gate 3 violations within any window triggers permanent NTS cap at 40.0. This flag cannot be cleared programmatically — only via a governance override, which is capped at 2 per year and fully logged.
- **Scar accumulation:** Violations add to a permanent scar value. The NTS formula uses `1 - exp(-scar/50)` which means scar compounds non-linearly. A miner cannot fully recover from a high-scar state.
- **Bounded recovery:** Clean tempos raise NTS at `log(1 + streak) × 0.5` per tempo, capped at +10 total bonus. A heavily scarred miner recovers slowly.

**Residual risk:** A miner who has never violated and then begins gaming faces slower NTS degradation than one with prior violations. The cold-start NTS of 50 provides some cushion. **Mitigation:** Validators may tune `GATE_SCAR` weights and `NTS_CATASTROPHIC` threshold in subnet hyperparameters (Phase 2).

---

### Override Abuse

**Threat:** A compromised or colluding validator applies override after override to keep a rogue miner's NTS artificially high.

**Defense:**
- Hard cap: **2 overrides per calendar year per agent.**
- Every override is appended to an immutable log in the OAP ledger with: timestamp, year, old NTS, new NTS, reason, authorized_by.
- The validator's override log is part of the NTS state submitted for cross-validator consensus.

**Residual risk:** Within the 2-per-year cap, a validator can raise an agent's NTS twice per year. Maximum elevation from 40 (catastrophic cap) to 100 would require 2 overrides. Third override is programmatically rejected regardless of reason.

---

### Validator Registry Poisoning

**Threat:** A validator approves a malicious model hash or registers a rogue agent identity, providing false Gate 1/2 passes to allied miners.

**Defense:**
- The registry is validator-controlled — other validators running the same deterministic four-gate check will produce different results if their registries differ.
- Divergent gate results across validators are detectable on-chain (validators set different weights for the same miner UID).
- Yuma Consensus clips weights from outlier validators — a single rogue validator cannot shift final weights significantly.

**Residual risk:** A cartel controlling >33% of validator stake could potentially sustain divergent registry states. This is a Bittensor-level threat beyond INVARIANT's individual defense scope. **At the gate level, INVARIANT's determinism ensures the attack is detectable even if not immediately preventable.**

---

### Validator Collusion

**Threat:** Multiple validators coordinate to pass invalid receipts for allied miners or uniformly suppress scores for competitors.

**Defense:** INVARIANT's four gates are **deterministic**. Two honest validators running the same receipt against the same registry **always** produce identical gate results. Any divergence in gate results between validators is cryptographically provable evidence of either:
1. A compromised registry (validator poisoning — see above)
2. A modified verifier binary
3. Deliberate false reporting

This makes collusion **detectable** in a way that behavioral scoring systems cannot achieve. Yuma Consensus's stake-weighted averaging further dilutes individual validator manipulation.

**Residual risk:** Coordinated collusion by a majority stake coalition. Out of scope for subnet-level defenses; requires Bittensor protocol-level governance intervention.

---

## Threat-Gate Matrix

| Threat | G1 | G2 | G3 | G4 | OAP | Yuma |
|--------|----|----|----|----|-----|------|
| Replay attack | — | — | ✅ | — | — | — |
| Counter rollback | — | — | ✅ | — | — | — |
| Sybil identity | ✅ | — | — | — | ✅ | — |
| Model impersonation | — | ✅ | — | — | — | — |
| Output tampering | — | — | — | ✅ | — | — |
| Output caching (cross-tempo) | — | — | — | ✅ | — | — |
| Output copying (cross-miner) | ✅ | — | — | ✅ | — | — |
| Digest forgery | — | — | — | ✅ | — | — |
| NTS gaming | — | — | — | — | ✅ | — |
| Override abuse | — | — | — | — | ✅ | — |
| Registry poisoning | — | — | — | — | — | ✅ |
| Validator collusion | — | — | — | — | — | ✅ |

✅ = Primary defense  
— = Not this layer's responsibility

---

## Comparison to Existing Bittensor Defenses

| Defense | Existing Bittensor | INVARIANT |
|---------|-------------------|-----------|
| Output quality scoring | Behavioral (validator-defined) | Deterministic (hash-bound) |
| Replay prevention | None | Gate 3: monotonic counter |
| Identity binding | Hotkey (stake-based) | Gate 1: agent_id + OAP history |
| Model verification | None | Gate 2: approved hash list |
| Execution proof | None | Gate 4: SHA-256 execution binding |
| Behavioral history | None | OAP: append-only ledger, permanent scar |
| Anti-collusion | Yuma probabilistic | Deterministic gates + Yuma structural |

---

## Out-of-Scope Threats

The following threats are acknowledged but explicitly out of scope for INVARIANT v1:

| Threat | Reason Out of Scope |
|--------|-------------------|
| SHA-256 preimage attack | Requires 2^128 operations; computationally infeasible |
| 51% stake attack on Bittensor | Protocol-level threat; beyond subnet defenses |
| Physical key exfiltration from validator | Infrastructure security; outside cryptographic scope |
| Zero-day in Python/Rust runtime | Dependency security; mitigated by pinned versions |
| Social engineering of subnet owner | Operational security; out of technical scope |
| Malicious Bittensor protocol upgrade | Governance risk; monitored, not preventable |

---

## Residual Risk Summary

| Risk | Severity | Likelihood | Mitigated By |
|------|----------|-----------|--------------|
| Validator registry poisoning | Medium | Low | Yuma weight clipping + determinism |
| Override abuse within cap | Low | Very Low | 2/yr hard cap + immutable audit log |
| Catastrophic miner NTS recovery gaming | Low | Low | Bounded recovery rate |
| Cold-start NTS exploitation | Low | Medium | 50 start point is not exploitable |
| Validator state file deletion | Medium | Very Low | Operational procedures |
| Majority stake cartel collusion | High | Very Low | Bittensor governance (out of scope) |

**Overall residual risk:** Low for all threats within INVARIANT's control boundary.

---

## Security Assumptions

1. SHA-256 is preimage-resistant (standard cryptographic assumption).
2. Keccak-256 is preimage-resistant (standard cryptographic assumption).
3. The Bittensor subtensor chain is live and producing blocks (operational assumption).
4. The validator's registry file is not externally writable (operational assumption).
5. The validator's state file is not deleted between sessions (operational assumption).
6. Python `json` library correctly parses and serializes receipt fields (dependency assumption).

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | Feb 2026 | Initial threat model. Covers all four gates + OAP layer. |

---

*This threat model will be updated at each major protocol version. Security researchers who identify gaps are encouraged to open a GitHub issue or contact security@orthonode.xyz.*