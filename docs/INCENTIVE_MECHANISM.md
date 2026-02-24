# INVARIANT — Incentive Mechanism Deep Dive

**Deterministic Trust Infrastructure for Bittensor**
*by Orthonode Infrastructure Labs*

---

## Overview

INVARIANT's incentive mechanism transforms the question "did this miner produce a good output?" into "did this miner provably execute what they claimed, and have they consistently done so?" The emission formula is:

```
emission_weight = output_quality × (NTS / 100) × freshness_factor
```

Every term in this formula is either cryptographically enforced or append-only computed. None of it can be gamed without triggering a gate failure or a permanent NTS penalty.

---

## The Three Dimensions of Miner Value

### Dimension 1: Output Quality (0.0 – 1.0)

Measures whether the miner produced a correct answer to the validator-assigned task.

**Phase 1 task types:**

| Task Type | Scoring Method | Score |
|-----------|---------------|-------|
| `math` | Exact evaluation match (`eval(expr)`) | 1.0 correct / 0.0 wrong |
| `hash` | SHA-256 of input matches submitted `PROCESSED:` prefix | 1.0 correct / 0.2 partial / 0.0 nothing |

**Phase 3+ task types (adversarial reasoning):**

| Task Type | Scoring Method |
|-----------|---------------|
| Code generation | CI test suite execution (sandboxed) — pass rate 0.0–1.0 |
| Math proof | Formal verification or numeric spot-check |
| Logical deduction | Reference answer comparison with fuzzy matching |

Output quality is the only dimension that measures *what* the miner produced. The other two dimensions measure *who* produced it and *when*. All three are required to earn full emissions.

### Dimension 2: NTS — INVARIANT Trust Score (0.0 – 100.0)

The NTS is a continuous float computed by the OAP engine from the miner's entire behavioral history. It is the permanent multiplier on output quality.

**NTS formula:**

```
penalty  = min(50 × (1 − exp(−scar / 50.0)), 50)
recovery = 50 × (clean / total) × 0.8
bonus    = min(log(1 + streak) × 0.5, 10.0)

raw_score = 50 − penalty + recovery + bonus

if catastrophic_flag:
    score = min(raw_score, 40.0)

NTS = clamp(score, 0.0, 100.0)
```

**NTS at representative states:**

| Miner History | Approximate NTS |
|--------------|----------------|
| Cold start | 50.0 |
| 10 clean tempos | ~55–57 |
| 20 clean tempos | ~60–63 |
| 50 clean tempos | ~72–78 |
| 100 clean tempos (streak intact) | ~82–88 |
| 1 Gate-4 violation, then 20 clean | ~48–55 |
| 3 Gate-3 violations (catastrophic) | ≤ 40.0 (permanent cap) |
| Zero violations, 200 clean tempos | ~90–96 |

### Dimension 3: Freshness Factor (0.0, 0.5, or 1.0)

Rewards prompt task execution. Penalizes late and absent responses.

| Response Time | Freshness Factor |
|--------------|-----------------|
| ≤ 120 seconds (10 blocks) | **1.0** — full credit |
| 121 – 180 seconds (10–15 blocks) | **0.5** — 50% credit |
| > 180 seconds (15+ blocks) | **0.0** — zero credit |

The freshness factor creates a continuous incentive to run hardware capable of executing tasks promptly. A miner who consistently responds in the late window earns at most 50% of what a fast miner earns, even at identical quality and NTS.

---

## Emission Calculation Examples

### Example 1: High-trust, fast, correct miner

```
quality   = 1.0     (correct answer)
NTS       = 88.0    (200 clean tempos, no violations)
freshness = 1.0     (responded in 45 seconds)

weight    = 1.0 × (88.0 / 100) × 1.0 = 0.880
```

This miner receives 88% of the maximum possible weight. The remaining 12% reflects the NTS cap from starting at 50 — a miner cannot reach NTS 100 from a cold start without extraordinary streak length.

### Example 2: New miner, correct answer, slow response

```
quality   = 1.0     (correct answer)
NTS       = 50.0    (cold start)
freshness = 0.5     (responded in 145 seconds — late window)

weight    = 1.0 × (50.0 / 100) × 0.5 = 0.250
```

Same quality as Example 1, but the miner earns only 25% of the weight. The cold-start NTS penalty and the late response penalty compound. This is by design: new miners need to earn reputation, and slow hardware is penalized.

### Example 3: Catastrophically flagged miner, perfect otherwise

```
quality   = 1.0     (correct answer)
NTS       = 38.0    (catastrophic flag — 3× Gate-3 violations, some recovery)
freshness = 1.0     (fast response)

weight    = 1.0 × (38.0 / 100) × 1.0 = 0.380
```

This miner operates permanently at ≤40% maximum weight. Even with perfect quality and perfect speed, their reputation history caps their earnings. The economic signal: **systematic replay behavior is permanently costly**.

### Example 4: Gate failure — zero weight

```
quality   = 1.0     (correct answer, but...)
gate      = GATE3_REPLAY_DETECTED  (counter not advanced)
NTS       = n/a

weight    = 0.0
```

Gate failures short-circuit the entire scoring pipeline. Output quality is irrelevant. No partial credit. The receipt must pass all four gates before any quality evaluation occurs.

---

## Why This Is the Nash Equilibrium

For a rational miner, the dominant strategy analysis:

### Strategy A: Fake receipt (cache old output)

```
Expected Value = P(gate_pass) × emission
              = 0   (Gate 4: execution_hash includes tempo_id — cannot cache)
```

This strategy yields zero with certainty. There is no probability of success.

### Strategy B: Copy another miner's receipt

```
Expected Value = P(gate_pass) × emission
              = 0   (Gate 1: cannot forge another miner's agent_id)
```

Zero with certainty.

### Strategy C: Run approved model, submit honest receipt

```
Expected Value = quality × (NTS / 100) × freshness × emission_per_weight
```

This is the only strategy with nonzero expected value. Every component of the formula rewards genuine, prompt, consistent computation.

### Strategy D: Build NTS strategically (tank + recover)

A miner might attempt to tank NTS to avoid scrutiny, then recover. The OAP model closes this:

```
Recovery rate = log(1 + streak) × 0.5 per clean tempo (max +10 total)
Catastrophic flag = triggered at 3× Gate-3 violations (permanent cap at 40)
Scar decay = only minor scar (<10 severity) decays, and only slowly
```

A miner who has accumulated scar through systematic violations cannot fully recover. The penalty function `1 - exp(-scar/50)` means scar compounds non-linearly. With scar=50, the penalty is 31.6 points. With scar=100, it is 43.2 points. The incremental cost of each additional violation *increases* as scar accumulates.

---

## Cold Start Economics

Every new miner enters with NTS=50. This means:

```
max_first_tempo_weight = quality × (50/100) × freshness
                       = 0.5 × freshness
                       ≤ 0.5
```

A new miner earns at most 50% of what an established miner earns. This creates:

1. **Sybil cost:** A Sybil operator creating 100 new identities gets 100 miners each earning ≤50% of an established miner. The 50% discount is the minimum cost of Sybil creation beyond registration fees.

2. **Time to parity:** Reaching NTS=80 requires approximately 50+ clean tempos. At standard Bittensor tempo lengths (100–360 blocks × 12s/block), this represents 100 minutes to 12+ hours of honest operation. Gaming by creating new identities requires burning this time.

3. **Legitimate miner advantage:** An honest miner who has operated for 200 tempos at NTS=90 earns approximately 1.8× what a new miner earns, simply through behavioral history. This creates a meaningful reputation moat.

---

## Validator Economics

Validators in INVARIANT run the four-gate pipeline plus quality scoring. Their economic incentive structure:

### Honest validator
- Runs deterministic gate verification (microseconds per receipt on Rust)
- Runs objective quality scoring (exact match / hash comparison)
- Sets weights accurately reflecting genuine miner performance
- Receives standard validator emissions from Yuma Consensus

### Dishonest validator (passing invalid receipts)
- Must run a modified registry that passes invalid receipts
- Other validators running the same receipt will produce GATE_FAIL results
- The divergence in weights across validators is visible on-chain
- Yuma Consensus clips outlier validators' weights proportionally
- The dishonest validator's influence on final weights diminishes as more honest validators weight-clip them

**The key anti-collusion property:** Because all four gates are deterministic, two honest validators on the same receipt always agree. A colluding validator who passes an invalid receipt will produce a weight that every honest validator can independently verify is incorrect. The on-chain disagreement is the evidence.

---

## Emission Formula Governance

The emission formula coefficients are validator-controlled in Phase 1 and will transition to DAO governance in Phase 6. Current constants:

| Parameter | Value | Governs |
|-----------|-------|---------|
| `NTS_START` | 50.0 | Cold-start NTS |
| `NTS_MAX` | 100.0 | Maximum achievable NTS |
| `NTS_CATASTROPHIC` | 40.0 | Permanent cap after catastrophic flag |
| `GATE_SCAR[1]` | 25.0 | Scar severity for Gate 1 violations |
| `GATE_SCAR[2]` | 15.0 | Scar severity for Gate 2 violations |
| `GATE_SCAR[3]` | 20.0 | Scar severity for Gate 3 violations |
| `GATE_SCAR[4]` | 25.0 | Scar severity for Gate 4 violations |
| `CONSISTENCY_BONUS_RATE` | 0.5 | Streak bonus per log unit |
| `CONSISTENCY_BONUS_MAX` | 10.0 | Maximum streak bonus |
| `MINOR_DECAY_RATE` | 0.3 | Scar decay per clean tempo (minor scar only) |
| `ANCHOR_HIGH` | 10 | Anchor interval for NTS ≥ 80 |
| `ANCHOR_MED` | 5 | Anchor interval for NTS 40–79 |
| `ANCHOR_LOW` | 1 | Anchor interval for NTS < 40 |
| `MAX_OVERRIDES` | 2 | Maximum governance overrides per year |
| Freshness full | 120s | Full freshness window |
| Freshness late | 180s | Late freshness window |

---

## Comparison to Standard Bittensor Scoring

| Property | Standard Bittensor | INVARIANT |
|----------|-------------------|-----------|
| Scores miners on | Output value | Execution integrity × quality × history |
| Anti-replay | None | Monotonic counter (Gate 3) |
| Anti-caching | None | tempo_id in execution_hash (Gate 4) |
| Anti-copying | None | agent_id is hotkey-bound (Gate 1) |
| Historical reputation | None | OAP append-only ledger |
| Anti-Sybil (economic) | Registration fee only | NTS cold-start penalty + time cost |
| Collusion detection | Probabilistic (Yuma) | Deterministic (gate disagreement is provable) |
| Emission formula | Validator-defined, variable | `quality × (NTS/100) × freshness` — canonical |

---

*Incentive Mechanism v1.0.0 — February 2026*
*Orthonode Infrastructure Labs — orthonode.xyz*