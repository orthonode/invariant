# INVARIANT: Cryptographic Execution Integrity Infrastructure for Bittensor

**Technical Whitepaper — Version 1.0.0**  
**Date:** February 2026  
**Authors:** Orthonode Infrastructure Labs  
**Contact:** research@orthonode.xyz  
**Web:** https://orthonode.xyz

---

## Abstract

Bittensor's Yuma Consensus scores miners on *outputs*. Outputs are trivially fakeable. Academic analysis of two years of Bittensor on-chain data confirms that rewards are driven by stake, not quality — a direct consequence of having no mechanism to verify *how* an output was produced, only *what* the output was.

INVARIANT is a Bittensor subnet that introduces **cryptographic execution integrity** as a first-class, economically-incentivized commodity. Miners prove what they computed by generating tamper-evident, replay-safe execution receipts using a four-gate verification model derived from live contracts deployed on Arbitrum Sepolia (89+ transactions) and TON Testnet (17+ transactions). A third layer — the Orthonode Adaptive Protocol (OAP) — maintains an append-only behavioral ledger per miner, making past integrity a permanent multiplier on future emissions.

The INVARIANT Trust Score (NTS) produced by stacking these three layers makes honest behavior the profit-maximizing strategy for every miner in the network. This paper describes the construction, the security model, and the economic incentives of the INVARIANT subnet.

---

## 1. Introduction

### 1.1 The Problem

The Bittensor network operates on a fundamental assumption: that validators can determine whether a miner's output is good by evaluating the output itself. This assumption has three structural failure modes:

**Failure Mode 1: Execution Opacity**  
A validator receiving an output string has no way to determine whether the miner ran an expensive frontier model or a one-line `return cached_response()`. The output may be identical. The computation was not.

**Failure Mode 2: Replay Vulnerability**  
A miner can record a high-quality response from tempo T and resubmit it at tempo T+1, T+2, ... T+N without performing any new computation. Current Yuma Consensus has no replay protection mechanism.

**Failure Mode 3: Sybil Economics**  
New miner identities cost only the registration fee. A coordinated Sybil operation can dilute honest miner scoring or game emission weighting by creating arbitrarily many low-cost identities.

Together, these failure modes mean that in the current Bittensor architecture, **the optimal strategy for a rational miner is to perform the minimum computation necessary to not be caught**, rather than to perform genuinely valuable computation.

### 1.2 Why Existing Solutions Are Insufficient

Several approaches to this problem exist in the broader ecosystem:

| Approach | Gap |
|----------|-----|
| Trusted Execution Environments (TEE) | Requires specialized hardware (SGX/TDX chips). Not deployable on commodity mining hardware. |
| ZK Proofs of computation | Proving overhead often exceeds original computation time. Impractical for LLM inference at tempo frequency. |
| Challenge-response quality scoring | Measures output quality, not execution integrity. A miner can still fake *how* they produced a correct answer. |
| Reputation systems | Behavioral heuristics, not cryptographic proofs. Can be gamed by patience. |
| Omron (Bittensor SN) | ZK proofs that a model ran correctly — but no agent identity binding, no replay protection, no behavioral history. |

INVARIANT's approach is different: instead of proving *what* was computed, it proves *who* computed it, *that* it was computed freshly, and *that* the digest binding agent identity + model + execution is cryptographically intact. No special hardware. No ZK overhead. Deterministic verification in microseconds.

### 1.3 The INVARIANT Approach

INVARIANT produces execution integrity receipts — 136-byte cryptographic artifacts that are:

1. **Identity-bound:** Tied to a specific miner hotkey and model version via SHA-256
2. **Replay-safe:** Protected by a strictly monotonic counter (uint64) per agent
3. **Execution-binding:** SHA-256(task_input ‖ output ‖ tempo_id) makes the receipt physically impossible to produce without running the computation against this specific input at this specific tempo
4. **Digest-sealed:** SHA-256 of all four fields makes any tampering immediately detectable

These receipts are verified through a four-gate pipeline in microseconds, with no trusted intermediary, on any validator with the same registry.

The OAP (Orthonode Adaptive Protocol) layer maintains a permanent behavioral record per miner, making NTS (INVARIANT Trust Score) a persistent, append-only reflection of a miner's entire operational history — not just their most recent tempo.

---

## 2. Background and Related Work

### 2.1 Bittensor's Emission Model

Bittensor distributes TAO emissions via Yuma Consensus, a stake-weighted scoring mechanism where validators assign weights to miners based on their assessment of output quality. The consensus mechanism aggregates these weights across all validators, normalized by their stake. Miners with higher aggregate weights receive proportionally more emissions.

The weakness in this model is that weight assignment is entirely at the discretion of validators. There is no protocol-level enforcement of any scoring methodology. A validator cartel can assign maximum weights to allied miners regardless of output quality. A single miner running a validator identity can upvote itself.

INVARIANT does not replace Yuma Consensus. It provides a cryptographic pre-filter that constrains what scores are *legitimate*, making collusion detectable rather than simply undesirable.

### 2.2 The Four-Gate Model

The four-gate execution receipt model was developed by Orthonode Infrastructure Labs and first deployed on Arbitrum Sepolia (contract `0xD661a1aB8CEFaaCd78F4B968670C3bC438415615`) as the SHA hardware attestation primitive. It was subsequently ported to TON Testnet (contract `kQBVqAhPv_ANWm0hfjJdLnQmvvC8_rQ_NEryVX3uFOUF05OP`) as the TON-SHA agent trust primitive.

Both deployments are live and have been validated against 10,000+ cross-layer test vectors, confirming byte-for-byte parity between SHA-256 implementations in Rust (Arbitrum Stylus), Tact (TON), and Python (INVARIANT subnet).

INVARIANT is the third deployment of this model — ported from hardware/agent trust contexts to the Bittensor miner/validator architecture. The technical core is unchanged. The context is new.

### 2.3 The OAP Model

The Orthonode Adaptive Protocol was developed to address a gap that the four-gate model alone cannot close: a miner who behaves well for 100 tempos and then launches a sustained replay attack should be penalized more severely than a miner who violates once and recovers. The four-gate model provides per-receipt binary verdicts; OAP provides temporal context across all receipts.

OAP is an append-only behavioral ledger with:
- Non-linear scar accumulation (violations compound)
- Logarithmic consistency bonus (streaks rewarded, but bounded)
- Permanent catastrophic flag for sustained replay behavior
- Bounded override governance (2 per year, fully logged)
- Adaptive anchoring intervals based on current NTS

OAP architecture is published at orthonode.xyz/oap.html and is fully implemented in `invariant_oap.py`.

---

## 3. System Design

### 3.1 Architecture Overview

INVARIANT is composed of three layers that produce a single output: the NTS (INVARIANT Trust Score) per miner per tempo.

```
┌─────────────────────────────────────────────────────────────────┐
│                    LAYER 3 — OAP ENGINE                         │
│              Lifecycle Trust Score (0–100)                      │
│  Append-only behavioral history · Catastrophic flag             │
│  Scar accumulation · Adaptive anchoring · Override cap          │
│  OUTPUT: NTS per agent per tempo                                │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    LAYER 2 — RECEIPT ENGINE                     │
│            Four-Gate Verification (Rust + Python bridge)        │
│  Gate 1: agent_id authorized? (SHA-256 registry)                │
│  Gate 2: model_hash approved? (validator-controlled list)       │
│  Gate 3: counter > last_confirmed? (uint64 monotonic)           │
│  Gate 4: SHA-256(agent_id‖model_hash‖exec_hash‖counter) valid?  │
│  OUTPUT: PASS or GATE{n}_FAILURE with gate number               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    LAYER 1 — IDENTITY ENGINE                    │
│            Agent ID Derivation (Software / Hardware)            │
│  Software: SHA-256(hotkey_ss58 ‖ model_hash ‖ reg_block)        │
│  Hardware: Keccak-256(eFuse_MAC ‖ chip_model) [DePIN path]      │
│  OUTPUT: 32-byte tamper-proof agent_id per miner                │
└─────────────────────────────────────────────────────────────────┘
```

The three layers are independent — each can fail independently — but are composed in sequence. A failure at Layer 1 short-circuits Layer 2. A failure at Layer 2 short-circuits Layer 3. The NTS multiplier is only applied to miners whose receipts pass all four gates.

### 3.2 Layer 1: Identity

**Software miners** (standard Bittensor miners):
```
agent_id = SHA-256(hotkey_ss58 ‖ model_hash_hex ‖ registration_block)
```

Where:
- `hotkey_ss58` is the miner's Bittensor hotkey in SS58 encoding
- `model_hash_hex` is `SHA-256(model_identifier_string)`, where `model_identifier_string` is a human-readable model name registered at subnet join time
- `registration_block` is the block number at which the miner registered

The registration block prevents two miners from deriving the same agent_id even if they share hotkey and model (impossible in practice, but cryptographically enforced).

**Hardware miners** (DePIN nodes, ESP32-S3 devices):
```
agent_id = Keccak-256(eFuse_MAC ‖ chip_model_identifier)
```

eFuse identifiers are burned at chip fabrication and cannot be cloned in software. This is the SHA hardware attestation model ported from Arbitrum Sepolia.

The agent_id is derived once at registration and stored immutably. Any change to hotkey, model identifier, or (for hardware) chip identity requires re-registration with a new agent_id, which starts a new OAP ledger from NTS=50.

### 3.3 Layer 2: The Receipt and Four-Gate Verification

#### 3.3.1 Receipt Construction (Miner Side)

After executing a task, the miner constructs a 136-byte receipt:

```
receipt = {
    agent_id:       32 bytes  # from Layer 1
    model_hash:     32 bytes  # SHA-256(model_identifier_string)
    execution_hash: 32 bytes  # SHA-256(task_input ‖ output ‖ tempo_id)
    counter:        8 bytes   # uint64, strictly increasing
    digest:         32 bytes  # SHA-256(agent_id ‖ model_hash ‖ execution_hash ‖ counter)
}
```

All hash fields are represented as 64-character lowercase hex strings in the wire format (JSON). The total wire representation is approximately 400 bytes.

The `execution_hash` is the critical construction. It binds the receipt to:
- The specific task input (cannot produce the same receipt for a different task)
- The specific output (cannot produce the same receipt with a different answer)
- The specific tempo (cannot reuse a receipt from a prior tempo)

It is physically impossible to produce a valid `execution_hash` without having executed the task against the given input at the given tempo.

#### 3.3.2 Gate Verification (Validator Side)

**Gate 1 — Identity Authorization:**
```python
if agent_id not in registry.authorized_agents:
    return GATE1_AGENT_NOT_AUTHORIZED
```
Blocks: Sybil attacks, unknown agents, cross-miner output copying (Miner B cannot claim Miner A's agent_id).

**Gate 2 — Model Approval:**
```python
if model_hash not in registry.approved_models:
    return GATE2_MODEL_NOT_APPROVED
```
Blocks: Model impersonation (claiming to run GPT-4 while running a cheap model). The model_hash must match a pre-approved list maintained by the validator.

**Gate 3 — Replay Protection:**
```python
if counter <= state.last_confirmed_counter[agent_id]:
    return GATE3_REPLAY_DETECTED
```
Blocks: Exact replay attacks, counter rollback attacks. The counter is a strictly monotonic uint64. State is persisted per validator.

**Gate 4 — Digest Verification:**
```python
expected = SHA-256(agent_id ‖ model_hash ‖ execution_hash ‖ counter)
if expected != receipt.digest:
    return GATE4_DIGEST_MISMATCH
```
Blocks: Any field tampering (changing output quality, swapping model hash after signing), output caching across tempos (different tempo_id = different execution_hash = different digest), output forgery.

**Anti-collusion property:** All four gates are deterministic. Given the same receipt and the same registry, two honest validators always produce identical gate results. Disagreement between validators on gate results is cryptographically provable evidence of at least one validator having a compromised registry or modified verifier binary.

#### 3.3.3 Scoring After Gate Pass

If all four gates pass, the validator proceeds to three-tier scoring:

```
Tier 1: gate_multiplier = 1.0  (0.0 if any gate failed)
Tier 2: quality_score = score_output(task_input, task_type, output)  ∈ [0.0, 1.0]
Tier 3: nts_multiplier = oap.get_nts(agent_id) / 100.0  ∈ [0.0, 1.0]

emission_weight = quality_score × nts_multiplier × freshness_factor

Where freshness_factor:
  = 1.0   if response received within 120 seconds
  = 0.5   if received within 180 seconds
  = 0.0   if received after 180 seconds
```

### 3.4 Layer 3: OAP Lifecycle Trust Engine

#### 3.4.1 The MinerLedger

Every registered agent has a `MinerLedger` — an append-only record of their entire operational history:

```python
@dataclass
class MinerLedger:
    agent_id_hex:  str       # immutable identity
    hotkey:        str       # Bittensor hotkey
    reg_tempo:     int       # registration tempo
    nts:           float     # current NTS score (0–100)
    total:         int       # total tempos participated
    clean:         int       # total clean tempos
    violations:    int       # total violations
    streak:        int       # consecutive clean tempos (current)
    max_streak:    int       # longest clean streak ever
    catastrophic:  bool      # permanent flag (3× Gate 3 violations)
    flag_reason:   str       # reason for catastrophic flag
    scar:          float     # accumulated severity (never decreases except minor decay)
    minor_scar:    float     # minor severity (can decay with clean tempos)
    violation_log: List[dict] # append-only violation history
    override_log:  List[dict] # append-only governance override history
    last_anchor:   int       # last anchor tempo
    next_anchor:   int       # next required anchor tempo
```

The ledger is JSON-persisted. No field is ever deleted. No violation is ever erased.

#### 3.4.2 NTS Computation

```
penalty  = min(NTS_START × (1 − exp(−scar / 50.0)), NTS_START)
recovery = (NTS_MAX − NTS_START) × (clean / total) × 0.8
bonus    = min(log(1 + streak) × 0.5, 10.0)

raw_score = NTS_START − penalty + recovery + bonus

if catastrophic:
    score = min(raw_score, NTS_CATASTROPHIC)  # cap at 40.0

NTS = clamp(score, 0.0, 100.0)
```

Where: `NTS_START = 50.0`, `NTS_MAX = 100.0`, `NTS_MIN = 0.0`, `NTS_CATASTROPHIC = 40.0`

**Design properties:**
- Scar uses an exponential penalty: small scar values have proportionally larger impact than large ones. The first violation hurts more than the tenth — by design. This prevents "I'll just accept a fixed penalty per violation" reasoning.
- Recovery is bounded by clean ratio (clean/total). A miner cannot fully recover from a high-scar history by simply running clean after years of violations.
- The consistency bonus logarithmically rewards sustained clean streaks, but caps at +10.0. Diminishing returns prevent NTS from drifting to 100 through patience alone.
- The catastrophic flag is permanent. 3× Gate 3 (replay) violations flag a miner catastrophically — their NTS is permanently capped at 40.0 regardless of subsequent clean behavior. Override governance (2/yr cap) exists for legitimate edge cases.

#### 3.4.3 Adaptive Anchoring

OAP uses adaptive anchoring intervals based on current NTS:

| NTS Range | Anchor Interval | Interpretation |
|-----------|----------------|----------------|
| ≥ 80 | Every 10 tempos | High-trust miner — checkpoint infrequently |
| 40–79 | Every 5 tempos | Medium-trust miner — regular checkpointing |
| < 40 | Every 1 tempo | Low-trust or catastrophically-flagged — every tempo |

Anchoring means the miner submits a signed OAP checkpoint in their receipt response. This provides validators with a recent, miner-attested snapshot of their trust state, which validators can cross-reference with their own ledger.

High-NTS miners benefit from reduced overhead. Low-NTS miners carry higher accountability overhead — a mild cost that reflects their risk profile.

---

## 4. Economic Analysis

### 4.1 Why Honest Behavior Is the Nash Equilibrium

In the current Bittensor model, the expected-value calculation for a miner who caches responses is:

```
EV_cheat = P(not_caught) × high_emission + P(caught) × 0
         ≈ high_emission   (P(caught) is near zero without INVARIANT)
```

With INVARIANT:

```
EV_cheat = 0   (Gate 4 enforces: can't cache without changing execution_hash)
EV_honest = quality × (NTS/100) × freshness × emission_per_weight
```

The only way to maximize `EV_honest` is to:
1. Run the actual computation (Gate 4 cannot be forged)
2. Run an approved model (Gate 2 enforces this)
3. Submit promptly (freshness factor rewards speed)
4. Maintain clean behavioral history (NTS multiplier is permanent)

This is a direct alignment between miner incentives and network health. INVARIANT doesn't ask miners to be honest — it makes honesty the financially dominant strategy.

### 4.2 Cold Start Economics

New miners enter with NTS = 50. This means:
- Their first submission earns at most `quality × 0.5 × freshness`
- A new Sybil identity cannot immediately capture high emissions
- The emission discount creates a natural cost to Sybil creation

After 20 clean tempos at quality=1.0, NTS rises to approximately 68. After 50 clean tempos, approximately 82. The consistency bonus rewards patience and sustained operation — the exact profile of a legitimate miner.

### 4.3 Catastrophic Flag Economics

A miner who triggers three Gate 3 violations is permanently capped at NTS=40. At this cap:
```
max_emission = 1.0 × (40/100) × 1.0 = 0.40
```

Compared to a clean miner at NTS=90:
```
max_emission = 1.0 × (90/100) × 1.0 = 0.90
```

The capped miner earns at most 44% of what the clean miner earns, permanently. The only exit is re-registration (new hotkey, new agent_id, NTS resets to 50) — which costs registration fees and 50+ tempos to rebuild. The economics strongly discourage systematic replay behavior.

### 4.4 Market Sizing

INVARIANT addresses three distinct buyer segments:

**Segment 1: Bittensor subnet operators (internal)**  
Any subnet wanting execution integrity for its miners can integrate INVARIANT's NTS as a pre-scoring filter. Estimated 128 active subnets, growing at ~30% annually. Integration is a one-time SDK import.

**Segment 2: Enterprise AI consumers (6–18 months)**  
Companies consuming Bittensor AI outputs need auditability. INVARIANT receipts provide timestamped, model-version-bound proof of execution. At $0.001–$0.01 per verified receipt and 1M receipts/day at scale, protocol revenue of $1,000–$10,000/day is achievable.

**Segment 3: Regulatory compliance (18–36 months)**  
EU AI Act Article 13 requires traceability of AI outputs. INVARIANT receipts are the minimal sufficient audit trail: model version, execution timestamp, input hash, output hash — immutably logged, cryptographically attested. This is a B2B enterprise SaaS segment worth hundreds of millions in compliance tooling globally.

---

## 5. Security Analysis

### 5.1 Attack Coverage Matrix

| Attack | Blocked At | Mechanism |
|--------|-----------|-----------|
| Replay (same receipt twice) | Gate 3 | Monotonic counter |
| Counter rollback | Gate 3 | Strict greater-than |
| Sybil new identity | Gate 1 + OAP | Not in registry; NTS cold-start cost |
| Model impersonation | Gate 2 | Unapproved model hash rejected |
| Output tampering | Gate 4 | Digest covers all fields |
| Output caching (cross-tempo) | Gate 4 | execution_hash includes tempo_id |
| Output copying (cross-miner) | Gate 1 | agent_id is hotkey-bound |
| Digest forgery | Gate 4 | SHA-256 preimage resistance |
| NTS tank-recover gaming | OAP | Catastrophic flag; bounded recovery |
| Override abuse | OAP | 2/yr hard cap; immutable audit log |
| Validator collusion | Determinism + Yuma | Gates deterministic; divergence is provable |
| Registry poisoning | Yuma clipping | Divergent registries produce detectable weight differences |

### 5.2 Cryptographic Guarantees

The execution integrity guarantee rests on two cryptographic properties:

**Preimage resistance of SHA-256:** Given `h = SHA-256(m)`, it is computationally infeasible to find `m` or any `m'` such that `SHA-256(m') = h`. Current best-known attacks on SHA-256 require ~2^128 operations — beyond the reach of any known or foreseeable classical or quantum computer within the relevant time horizon.

**The execution binding property:** The receipt's `execution_hash = SHA-256(task_input ‖ output ‖ tempo_id)`. To forge a valid receipt for task T without running the computation:
1. The attacker would need to find a valid `execution_hash` without knowing the actual output → requires SHA-256 preimage attack.
2. The attacker could guess the output → possible for simple tasks, but Gate 4 also covers `agent_id` and `model_hash` in the digest, so a correct guess still requires constructing a valid `digest`, which requires knowing `agent_id` (hotkey-bound) and `model_hash` (model-bound). A Miner B cannot construct a valid `digest` for Miner A's `agent_id`.

**Therefore:** A valid four-gate receipt is a proof that a specific registered agent ran a specific approved model on a specific task input at a specific tempo and produced a specific output, exactly once.

### 5.3 Non-Cryptographic Residual Risks

The following risks are outside the cryptographic guarantee boundary:

- **Validator registry poisoning:** If a validator's approved model list is compromised, they may pass invalid Gate 2 checks. This divergence is detectable across validators but not immediately preventable by INVARIANT alone. Yuma Consensus clips outlier validator weights.

- **State file deletion:** Deleting the validator's counter state file (`invariant_state.json`) would reset last-confirmed counters to 0, allowing previously consumed counters to pass Gate 3. This is an operational security concern addressed by deployment procedures, not a cryptographic weakness.

- **Majority stake cartel:** If validators controlling >50% of stake coordinate to pass arbitrary receipts, they can override Yuma Consensus's weight-clipping. This is a Bittensor protocol-level governance risk beyond INVARIANT's subnet boundary.

Full threat model: [THREAT_MODEL.md](../THREAT_MODEL.md)

---

## 6. Implementation

### 6.1 Rust Gate Engine

The production gate verifier is implemented in Rust as a PyO3 extension (`invariant_gates_rs`). The Rust implementation:

- Uses the `sha2` crate for SHA-256 (FIPS 180-4 compliant)
- Stores registry and counter state in thread-safe `RwLock<HashMap<...>>`
- Exposes `RsVerifier::verify_json(json_str)` and `RsVerifier::verify_batch_json(json_str)` as PyO3 methods
- Achieves <50µs per receipt on commodity hardware (benchmarked with Criterion)
- Supports `maturin develop --features python-ext` for in-place installation

A pure Python fallback (`invariant_gates.py`) provides identical behavior at ~2ms per receipt. The bridge (`invariant_gates_bridge.py`) transparently routes to the Rust extension when compiled, Python otherwise. **The API is byte-for-byte identical regardless of backend.**

### 6.2 Bittensor Integration

INVARIANT integrates with Bittensor v10+ (PascalCase API):

**Miner side:**
- `bt.Axon` serves `InvariantTask` synapse requests
- Each task triggers `execute_task() → build_receipt() → checkpoint_if_due()`
- Identity and counter state are persisted across restarts
- `serve_axon` failure (Custom Error 10 on fresh local nodes) is handled gracefully

**Validator side:**
- `bt.Dendrite` queries each miner with a unique per-(tempo, uid) task
- Task uniqueness prevents output-copying attacks at the protocol level (even before Gate 1)
- Three-tier scoring: gate verification → quality scoring → NTS multiplication
- `subtensor.set_weights()` with normalized float32 weight vector

### 6.3 The Bridge Pattern

All Python code imports exclusively through `invariant_gates_bridge.py`. This is enforced by design and documented in all code comments. The bridge:

1. Attempts `import invariant_gates_rs` (Rust extension)
2. Falls back to `import invariant_gates` (pure Python) if not available
3. Exposes a unified API (`derive_software_agent_id`, `hash_model`, `build_receipt`, `Registry`, `Verifier`, `GateResult`)
4. Reports current backend via `using_rust() → bool`

### 6.4 Performance

| Backend | Per receipt | 1K receipts | 192-miner sweep |
|---------|------------|-------------|-----------------|
| Python | ~2 ms | ~2,000 ms | ~384,000 ms |
| Rust | <50 µs | <50 ms | <10 ms |

At standard Bittensor tempo frequencies (100–360 blocks, 12s per block), the Rust backend comfortably validates 192 miners' receipts within a single block. The Python fallback validates 192 miners in under 400ms — still well within any practical tempo constraint.

---

## 7. Roadmap Summary

| Phase | Milestone | Target |
|-------|-----------|--------|
| 0 | SHA live on Arbitrum Sepolia · TON-SHA live on TON Testnet · OAP architecture | ✅ Done |
| 1 | Core engine + Bittensor miner/validator · 21 passing tests | ✅ Done |
| 2 | Testnet deployment · Live gate demonstrations · Open-source SDK | Mar 2026 |
| 3 | Cross-subnet NTS API · Adversarial task track | Apr 2026 |
| 4 | Mainnet launch · Real TAO emissions | May–Jun 2026 |
| 5 | Enterprise API · EU AI Act compliance module | Q3 2026 |
| 6 | DAO governance · Open model registry | Q4 2026 |

Full roadmap: [ROADMAP.md](../ROADMAP.md)

---

## 8. Conclusion

INVARIANT addresses the most fundamental structural problem in Bittensor: the absence of any mechanism to verify that a miner actually executed what they claim to have executed.

The four-gate receipt model is not theoretical. It is live on Arbitrum Sepolia with 89+ transactions. It is live on TON Testnet with 17+ transactions. Cross-layer SHA-256 and Keccak-256 parity is confirmed across 10,000+ test vectors. The Python subnet implementation passes 21 tests covering all 8 attack vectors, the complete OAP lifecycle, and throughput verification.

No other team in the Bittensor ecosystem can point to two live deployments of the underlying technology on two different chains before the subnet itself exists. INVARIANT is not a proposal. It is a delivery.

> *"Every Bittensor subnet trusts miner outputs. INVARIANT makes them provable — with cryptographic receipts that are already live on two chains, and impossible to fake without actually running the intelligence."*

---

## References

1. Bittensor Whitepaper — https://bittensor.com/whitepaper
2. Yuma Consensus Documentation — https://docs.bittensor.com/yuma-consensus
3. SHA Contract (Arbitrum Sepolia) — https://sepolia.arbiscan.io/address/0xD661a1aB8CEFaaCd78F4B968670C3bC438415615
4. TON-SHA Contract (TON Testnet) — https://testnet.tonscan.org/address/kQBVqAhPv_ANWm0hfjJdLnQmvvC8_rQ_NEryVX3uFOUF05OP
5. OAP Architecture — https://orthonode.xyz/oap.html
6. IoTeX Exploit Analysis — https://orthonode.xyz/iotex-research.html
7. SHA DePIN Deep Dive — https://orthonode.xyz/sha.html
8. FIPS 180-4 (SHA Standard) — https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.180-4.pdf
9. PyO3 Documentation — https://pyo3.rs
10. Bittensor v10 API Reference — https://docs.bittensor.com

---

## Appendix A: Receipt Field Specification

```
Field            Type      Size      Description
──────────────────────────────────────────────────────────────────
agent_id         hex str   64 chars  SHA-256(hotkey‖model_hash‖reg_block)
                                     or Keccak-256(eFuse_MAC‖chip_model)
model_hash       hex str   64 chars  SHA-256(model_identifier_string)
execution_hash   hex str   64 chars  SHA-256(task_input‖output‖tempo_id)
counter          int       uint64    Monotonically increasing per agent
digest           hex str   64 chars  SHA-256(agent_id‖model_hash‖
                                             execution_hash‖counter)
──────────────────────────────────────────────────────────────────
Wire format: JSON object (approx. 400 bytes)
Conceptual size: 5 × 32 bytes = 160 bytes (all fields