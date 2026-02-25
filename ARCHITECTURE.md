# INVARIANT — Architecture

**Deterministic Trust Infrastructure for Bittensor**  
*by Orthonode Infrastructure Labs*

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Three-Layer Trust Stack](#three-layer-trust-stack)
3. [Receipt Lifecycle](#receipt-lifecycle)
4. [Four-Gate Verification Pipeline](#four-gate-verification-pipeline)
5. [OAP Lifecycle State Machine](#oap-lifecycle-state-machine)
6. [Miner Architecture](#miner-architecture)
7. [Validator Architecture](#validator-architecture)
8. [Tempo Cycle Sequence](#tempo-cycle-sequence)
9. [Rust/Python Bridge](#rustpython-bridge)
10. [Data Flow Diagram](#data-flow-diagram)
11. [Component Dependency Graph](#component-dependency-graph)
12. [NTS Scoring Formula](#nts-scoring-formula)
13. [Attack Vector Map](#attack-vector-map)
14. [Deployment Topology](#deployment-topology)

---

## System Overview

INVARIANT is a Bittensor subnet that produces a cryptographically-verified **INVARIANT Trust Score (NTS)** per miner. Where every other subnet scores miners on *outputs*, INVARIANT proves *how* those outputs were produced.

```mermaid
graph TD
    subgraph INVARIANT["INVARIANT Subnet — Trust Production Layer"]
        L1["Layer 1: SHA Identity<br/>Hardware/Software Agent ID<br/>Keccak-256 / SHA-256"]
        L2["Layer 2: Execution Receipt<br/>Four-Gate Verification<br/>SHA-256 Digest Binding"]
        L3["Layer 3: OAP Engine<br/>Lifecycle Trust Score<br/>Append-Only Behavioral History"]
        
        L1 --> L2
        L2 --> L3
        L3 --> NTS["NTS Score (0–100)"]
    end

    subgraph BITTENSOR["Bittensor Protocol Layer"]
        YUMA["Yuma Consensus"]
        EMISSIONS["TAO Emissions"]
        CHAIN["Subtensor Chain"]
    end

    NTS --> |"emission_weight = quality × (NTS/100) × freshness"| YUMA
    YUMA --> EMISSIONS
    CHAIN --> |"block / tempo"| INVARIANT
```

---

## Three-Layer Trust Stack

```mermaid
graph BT
    subgraph L1["LAYER 1 — Identity (SHA Model)"]
        direction LR
        EFUSE["eFuse MAC<br/>(DePIN hardware)"]
        HOTKEY["Bittensor Hotkey<br/>(software miners)"]
        MODEL_HASH["model_hash<br/>SHA-256(model_identifier)"]
        REG_BLOCK["registration_block"]
        
        EFUSE --> AGENT_HW["agent_id<br/>Keccak-256(eFuse‖chip)"]
        HOTKEY & MODEL_HASH & REG_BLOCK --> AGENT_SW["agent_id<br/>SHA-256(hotkey‖model_hash‖block)"]
    end

    subgraph L2["LAYER 2 — Execution Receipt (TON-SHA Model)"]
        direction LR
        AGENT_ID["agent_id (from L1)"]
        MODEL_H["model_hash"]
        EXEC_H["execution_hash<br/>SHA-256(input‖output‖tempo_id)"]
        CTR["counter (uint64, monotonic)"]
        DIGEST["digest<br/>SHA-256(agent_id‖model_hash‖exec_hash‖counter)"]
        
        AGENT_ID & MODEL_H & EXEC_H & CTR --> DIGEST
    end

    subgraph L3["LAYER 3 — OAP Engine"]
        direction LR
        LEDGER["MinerLedger<br/>append-only"]
        SCAR["Scar Accumulation<br/>non-linear penalty"]
        STREAK["Consistency Streak<br/>log-scale bonus"]
        CAT["Catastrophic Flag<br/>permanent cap @40"]
        ANCHOR["Adaptive Anchoring<br/>interval: 1/5/10 tempos"]
        OVERRIDE["Override Governance<br/>max 2/year, logged"]
        
        LEDGER --> SCAR & STREAK & CAT
        CAT --> NTS2["NTS (0–100)"]
        SCAR & STREAK & OVERRIDE --> NTS2
        NTS2 --> ANCHOR
    end

    L1 --> L2
    L2 --> L3
```

---

## Receipt Lifecycle

```mermaid
sequenceDiagram
    participant V as Validator
    participant M as Miner
    participant GE as Gate Engine
    participant OAP as OAP Engine
    participant BT as Bittensor Chain

    Note over V,BT: Every Bittensor tempo (~12s/block × tempo_length blocks)

    BT->>V: New block / tempo tick
    V->>V: generate_task(tempo, uid)<br/>→ deterministic per (tempo, uid)
    V->>M: InvariantTask(task_input, tempo_id, task_type)
    
    Note over M: Part 1 — Execute Task
    M->>M: output = execute_task(task_input, task_type)
    M->>M: counter += 1; save_counter()
    
    Note over M: Part 2 — Build Receipt
    M->>M: execution_hash = SHA-256(task_input ‖ output ‖ tempo_id)
    M->>M: digest = SHA-256(agent_id ‖ model_hash ‖ execution_hash ‖ counter)
    M->>M: receipt = {agent_id, model_hash, execution_hash, counter, digest}
    
    Note over M: Part 3 — OAP Checkpoint (if due)
    M->>OAP: should_anchor(agent_id, tempo)?
    OAP-->>M: True/False
    opt Anchor due
        M->>OAP: checkpoint(agent_id, tempo)
        OAP-->>M: signed checkpoint dict
    end
    
    M->>V: InvariantTask(output, receipt_json, checkpoint_json)
    
    Note over V,GE: Tier 1 — Four-Gate Verification
    V->>GE: verifier.verify(receipt_dict)
    GE->>GE: Gate 1: agent_id in registry?
    GE->>GE: Gate 2: model_hash approved?
    GE->>GE: Gate 3: counter > last_confirmed?
    GE->>GE: Gate 4: SHA-256(...) == digest?
    GE-->>V: {result, gate_number, detail}
    
    Note over V,OAP: Tier 2 — Quality Scoring
    V->>V: quality = score_output(task_input, task_type, output)
    
    Note over V,OAP: Tier 3 — NTS Multiplier
    V->>OAP: get_nts(agent_id)
    OAP-->>V: nts (0–100)
    
    alt All gates passed
        V->>OAP: record_clean(agent_id, tempo)
        V->>V: weight = quality × (nts/100) × freshness
    else Gate failed
        V->>OAP: record_violation(agent_id, tempo, gate, vtype, detail)
        V->>V: weight = 0.0
    end
    
    V->>BT: set_weights(uids, weights)
    BT->>BT: Yuma Consensus aggregation
    BT->>M: TAO emission (proportional to weight)
```

---

## Four-Gate Verification Pipeline

```mermaid
flowchart TD
    START([Receipt Received]) --> PARSE{Parse JSON}
    PARSE -->|Parse error| FAIL_PARSE[/"❌ PARSE_ERROR\ngate_number: 4\nScore: 0.0"/]
    PARSE -->|Valid JSON| G1

    G1{Gate 1\nIdentity Authorization\nIs agent_id in\nauthorized registry?}
    G1 -->|NO| FAIL1[/"❌ GATE1_AGENT_NOT_AUTHORIZED\ngate_number: 1\nScore: 0.0\n\nBlocks: Sybil, unknown agents,\ncross-miner copying"/]
    G1 -->|YES| G2

    G2{Gate 2\nModel Approval\nIs model_hash in\napproved list?}
    G2 -->|NO| FAIL2[/"❌ GATE2_MODEL_NOT_APPROVED\ngate_number: 2\nScore: 0.0\n\nBlocks: Model impersonation,\nundeclared model swaps"/]
    G2 -->|YES| G3

    G3{Gate 3\nReplay Protection\ncounter > last_confirmed\nfor this agent_id?}
    G3 -->|NO| FAIL3[/"❌ GATE3_REPLAY_DETECTED\ngate_number: 3\nScore: 0.0\n\nBlocks: Replay attacks,\ncounter rollback"/]
    G3 -->|YES| G4

    G4{Gate 4\nDigest Verification\nSHA-256(agent_id ‖ model_hash\n‖ execution_hash ‖ counter)\n== receipt.digest?}
    G4 -->|NO| FAIL4[/"❌ GATE4_DIGEST_MISMATCH\ngate_number: 4\nScore: 0.0\n\nBlocks: Any field tampering,\noutput forgery, caching"/]
    G4 -->|YES| PASS

    PASS[/"✅ PASS\ngate_number: 0\nProceeds to quality scoring"/]

    style PASS fill:#1a4a1a,color:#00ff00
    style FAIL1 fill:#4a1a1a,color:#ff6666
    style FAIL2 fill:#4a1a1a,color:#ff6666
    style FAIL3 fill:#4a1a1a,color:#ff6666
    style FAIL4 fill:#4a1a1a,color:#ff6666
    style FAIL_PARSE fill:#4a1a1a,color:#ff6666
```

---

## OAP Lifecycle State Machine

```mermaid
stateDiagram-v2
    [*] --> UNREGISTERED

    UNREGISTERED --> PROBATION: get_or_create(agent_id)\nNTS = 50.0

    PROBATION --> TRUSTED: 20+ clean tempos\nNTS > 70
    PROBATION --> WARNED: Any gate violation\nNTS drops

    TRUSTED --> ELITE: 50+ clean tempos\nNTS > 90
    TRUSTED --> WARNED: Gate violation\nNTS drops
    TRUSTED --> TRUSTED: Clean tempo\nNTS += log(streak) × 0.5

    ELITE --> TRUSTED: Gate violation\nNTS drops
    ELITE --> ELITE: Clean tempo\nAnchor interval: 10 tempos

    WARNED --> TRUSTED: Clean tempos\nScar decays slowly
    WARNED --> CRITICAL: 3× Gate 3 violations\nCatastrophic flag

    CRITICAL --> CRITICAL: ⚠️ PERMANENT\nNTS capped at 40.0\nOnly override can raise above 40

    note right of CRITICAL
        Catastrophic flag conditions:
        - 3+ Gate 3 (replay) violations
        - Cannot be cleared programmatically
        - Max 2 overrides/year
        - Override logged immutably
    end note

    note right of ELITE
        NTS > 80:
        Anchor every 10 tempos
        Full emission weight
        Reputation moat
    end note
```

---

## Miner Architecture

```mermaid
graph TD
    subgraph MINER["InvariantMiner — Bittensor Axon"]
        CONFIG["bt.Config\n(wallet, subtensor, netuid)"]
        WALLET["bt.Wallet\n(hotkey ss58)"]
        AXON["bt.Axon\n(HTTP server, port 8091+)"]
        
        subgraph IDENTITY["Identity Layer (Phase 1)"]
            MODEL_ID["model_identifier\n(config arg)"]
            MODEL_H["model_hash\nSHA-256(model_id)"]
            AGENT["agent_id\nSHA-256(hotkey‖model_hash‖reg_block)"]
            ID_CACHE["identity.json\n(persisted)"]
            
            MODEL_ID --> MODEL_H --> AGENT --> ID_CACHE
        end
        
        subgraph STATE["Persistent State"]
            COUNTER["counter.json\nmonotonic uint64"]
            OAP_S["oap.json\nMinerLedger"]
            REG["registry.json\nagents + models"]
        end
        
        subgraph HANDLER["Task Handler"]
            RECV["handle_task(InvariantTask)"]
            EXEC["execute_task(input, type)\n→ output string"]
            RECEIPT_B["build_receipt(\n  agent_id, model_hash,\n  task_input, output,\n  counter, tempo_id,\n  timestamp\n)"]
            CHKPT["OAPEngine.checkpoint()\n(if should_anchor)"]
        end
        
        CONFIG --> WALLET --> AXON
        IDENTITY --> HANDLER
        STATE --> HANDLER
        RECV --> EXEC --> RECEIPT_B --> CHKPT
    end

    VALIDATOR["Validator Dendrite"] -->|"InvariantTask\n(task_input, tempo_id)"| RECV
    CHKPT -->|"InvariantTask\n(output, receipt_json, checkpoint_json)"| VALIDATOR
```

---

## Validator Architecture

```mermaid
graph TD
    subgraph VALIDATOR["InvariantValidator — Three-Tier Pipeline"]
        CONFIG2["bt.Config\n(wallet, subtensor, netuid)"]
        DENDRITE["bt.Dendrite\n(query miners)"]
        META["bt.Metagraph\n(UIDs, hotkeys, axons)"]
        
        subgraph TIER1["Tier 1 — Identity + Gate Verification"]
            UID_MAP["_build_uid_agent_map()\nhotkey → agent_id_hex"]
            VRFY["Verifier.verify(receipt_dict)\nFour-gate pipeline"]
            GATE_MULT["gate_multiplier\n0.0 or 1.0"]
            
            UID_MAP --> VRFY --> GATE_MULT
        end
        
        subgraph TIER2["Tier 2 — Output Quality"]
            SCORE["score_output(\n  task_input,\n  task_type,\n  output\n)"]
            QUALITY["quality ∈ [0.0, 1.0]"]
            SCORE --> QUALITY
        end
        
        subgraph TIER3["Tier 3 — NTS Multiplier + Freshness"]
            NTS_Q["OAPEngine.get_nts(agent_id)"]
            FRESH["freshness\n1.0 / 0.5 / 0.0\n(in-window / late / expired)"]
            EMIT["emission_weight\n= quality × (nts/100) × freshness"]
            NTS_Q & FRESH & QUALITY --> EMIT
        end
        
        subgraph SETW["Weight Setting"]
            WEIGHTS["np.zeros(n_uids)"]
            NORM["normalize weights"]
            SET["subtensor.set_weights(\n  uids, weights\n)"]
            WEIGHTS --> NORM --> SET
        end
        
        CONFIG2 --> DENDRITE & META
        TIER1 --> TIER2 --> TIER3 --> SETW
    end

    MINERS["Active Miners\n(metagraph.axons\nwhere is_serving=True)"] -->|"InvariantTask responses"| TIER1
    SET -->|"weight vector"| YUMA2["Yuma Consensus"]
```

---

## Tempo Cycle Sequence

```mermaid
gantt
    title INVARIANT Validator Tempo Cycle (tempo = 100 blocks × 12s = 1200s)
    dateFormat X
    axisFormat %Ls

    section Setup
    Metagraph sync           :a1, 0, 5000
    Build UID→agent map      :a2, 5000, 8000

    section Task Dispatch
    Generate tasks (per UID) :b1, 8000, 10000
    Query miner 1            :b2, 10000, 30000
    Query miner 2            :b3, 10000, 30000
    Query miner N            :b4, 10000, 30000

    section Scoring
    Tier 1 gate verification :c1, 30000, 35000
    Tier 2 quality scoring   :c2, 35000, 40000
    Tier 3 NTS multiplication:c3, 40000, 42000
    Weight normalization      :c4, 42000, 43000

    section Commit
    set_weights on chain     :d1, 43000, 50000
    OAP ledger save          :d2, 50000, 52000
    Sleep until next tempo   :d3, 52000, 120000
```

---

## Rust/Python Bridge

```mermaid
graph TD
    subgraph BRIDGE["invariant_gates_bridge.py — THE BRIDGE"]
        IMPORT_ATTEMPT["try: import invariant_gates_rs"]
        
        IMPORT_ATTEMPT -->|Success: .so found| RUST_PATH["Rust Backend\ninvariant_gates_rs\n(PyO3 extension)"]
        IMPORT_ATTEMPT -->|ImportError: no .so| PY_PATH["Python Backend\ninvariant_gates.py\n(pure fallback)"]
        
        subgraph PUBLIC_API["Public API — identical regardless of backend"]
            F1["derive_software_agent_id(hotkey, model_hash, block) → str"]
            F2["derive_hardware_agent_id(efuse_mac, chip_model) → str"]
            F3["hash_model(identifier) → str"]
            F4["build_receipt(agent_id, model_hash, input, output, counter, tempo, ts) → dict"]
            F5["Registry(path).register_agent(agent_id, hotkey)"]
            F6["Registry(path).approve_model(model_hash)"]
            F7["Verifier(reg, state).verify(receipt_dict) → dict"]
            F8["Verifier(reg, state).verify_batch(receipts) → list"]
        end
        
        RUST_PATH --> PUBLIC_API
        PY_PATH --> PUBLIC_API
    end

    subgraph RUST_CRATE["invariant-gates/ (Rust Crate)"]
        CARGO["Cargo.toml\nmaturin features: python-ext"]
        LIB["lib.rs\nPyO3 module root"]
        CRYPTO["crypto.rs\nSHA-256, Keccak-256"]
        RECEIPT["receipt.rs\n136-byte receipt struct"]
        REGISTRY["registry.rs\nthread-safe RwLock registry"]
        VERIFIER["verifier.rs\nstateful four-gate verifier"]
        BENCHES["benches/gate_bench.rs\nCriterion benchmarks"]
        
        CARGO --> LIB
        LIB --> CRYPTO & RECEIPT & REGISTRY & VERIFIER
        VERIFIER --> BENCHES
    end

    subgraph PERF["Performance"]
        P1["Python fallback:\n~500 receipts/sec\n~2ms per receipt"]
        P2["Rust production:\n~9,000+ receipts/sec\n<50µs per receipt"]
        P3["Speedup: ~50–100×"]
        P1 & P2 --> P3
    end

    RUST_PATH -.->|"maturin develop\n--features python-ext"| RUST_CRATE
    RUST_CRATE -.-> PERF
    PY_PATH -.-> P1
```

---

## Data Flow Diagram

```mermaid
flowchart LR
    subgraph INPUTS["Inputs"]
        HOTKEY_IN["Bittensor hotkey\n(ss58 address)"]
        MODEL_IN["Model identifier\n(string)"]
        TASK_IN["Task input\n(from validator)"]
        TEMPO_IN["Tempo ID\n(from chain)"]
    end

    subgraph LAYER1["Layer 1: Identity"]
        AID["agent_id\n32-byte hex"]
        MH["model_hash\n32-byte hex"]
    end

    subgraph LAYER2["Layer 2: Receipt"]
        EH["execution_hash\nSHA-256(input‖output‖tempo)"]
        CTR["counter\nuint64 monotonic"]
        DIG["digest\nSHA-256(aid‖mh‖eh‖ctr)"]
        RECEIPT_OUT["RECEIPT\n{agent_id, model_hash,\nexecution_hash, counter, digest}"]
    end

    subgraph LAYER3["Layer 3: OAP"]
        LEDGER_OUT["MinerLedger\n{nts, scar, streak,\nviolation_log, ...}"]
        NTS_OUT["NTS score\n0.0 – 100.0"]
    end

    subgraph OUTPUT["Emission Weight"]
        QQ["Quality score\n0.0 – 1.0"]
        WEIGHT_OUT["emission_weight\nquality × (NTS/100)\n× freshness"]
    end

    HOTKEY_IN & MODEL_IN --> AID & MH
    TASK_IN & TEMPO_IN & AID & MH --> EH
    EH & CTR & AID & MH --> DIG
    AID & MH & EH & CTR & DIG --> RECEIPT_OUT
    RECEIPT_OUT --> LEDGER_OUT --> NTS_OUT
    NTS_OUT & QQ --> WEIGHT_OUT
```

---

## Component Dependency Graph

```mermaid
graph TD
    subgraph EXTERNAL["External Dependencies"]
        BT["bittensor>=9.12.0"]
        NP["numpy"]
        RUST_EXT["invariant_gates_rs\n(optional, via maturin)"]
    end

    subgraph CORE["Core Engine"]
        BRIDGE["invariant_gates_bridge.py\nTHE BRIDGE — import this only"]
        GATES_PY["invariant_gates.py\nPure Python fallback"]
        OAP["invariant_oap.py\nOAP lifecycle engine"]
        PROTO["protocol.py\nInvariantTask synapse"]
    end

    subgraph BITTENSOR_LAYER["Bittensor Layer"]
        MINER_BT["phase1_bittensor/miner.py"]
        VALIDATOR_BT["phase1_bittensor/validator.py"]
    end

    subgraph SCRIPTS_LAYER["Scripts"]
        TEST_LOCAL["scripts/test_locally.py"]
        DEPLOY["scripts/deploy_testnet.py"]
        SETUP_W["scripts/setup_wallets.py"]
        REG_S["scripts/register_subnet.py"]
        LAUNCH["scripts/launch_nodes.py"]
    end

    subgraph TESTS["Tests"]
        PYTEST["invariant/tests/test_invariant.py\n21 tests"]
    end

    RUST_EXT -.->|"optional fast path"| BRIDGE
    GATES_PY -->|"fallback"| BRIDGE
    BRIDGE --> MINER_BT & VALIDATOR_BT
    OAP --> MINER_BT & VALIDATOR_BT
    PROTO --> MINER_BT & VALIDATOR_BT
    BT --> MINER_BT & VALIDATOR_BT
    NP --> VALIDATOR_BT
    BRIDGE --> TEST_LOCAL & PYTEST
    OAP --> TEST_LOCAL & PYTEST
    MINER_BT & VALIDATOR_BT --> LAUNCH & DEPLOY
```

---

## NTS Scoring Formula

```mermaid
graph LR
    subgraph FORMULA["NTS Computation"]
        SCAR_V["scar value\n(accumulated violations)"]
        CLEAN_V["clean ratio\nclean / total"]
        STREAK_V["consistency streak\n(consecutive clean tempos)"]
        CAT_FLAG["catastrophic flag\n(bool)"]

        PENALTY["penalty\n= min(50 × (1 − e^(−scar/50)), 50)"]
        RECOVERY["recovery\n= (50) × (clean/total) × 0.8"]
        BONUS["consistency bonus\n= min(log(1+streak) × 0.5, 10)"]

        SCAR_V --> PENALTY
        CLEAN_V --> RECOVERY
        STREAK_V --> BONUS

        SUM["raw_score\n= 50 − penalty + recovery + bonus"]
        PENALTY & RECOVERY & BONUS --> SUM

        CAP["if catastrophic:\n  score = min(score, 40.0)"]
        CAT_FLAG --> CAP
        SUM --> CAP

        CLAMP["NTS = clamp(score, 0.0, 100.0)"]
        CAP --> CLAMP
    end

    subgraph EMISSION["Emission Weight"]
        NTS_IN["NTS (0–100)"]
        QUAL["output_quality (0–1)"]
        FRESH["freshness\n1.0 / 0.5 / 0.0"]
        WEIGHT["emission_weight\n= quality × (NTS/100) × freshness"]

        NTS_IN & QUAL & FRESH --> WEIGHT
    end

    CLAMP --> NTS_IN
```

---

## Attack Vector Map

```mermaid
mindmap
    root((ATTACK<br/>VECTORS))
        IDENTITY
            Sybil creation
                unknown agent_id → Gate 1 ❌
                NTS = 50 cold start
                costs real tempo time
            Output copying
                agent_id is hotkey-bound
                can't forge another's ID → Gate 1 ❌
        REPLAY
            Same receipt twice
                monotonic counter → Gate 3 ❌
            Counter rollback
                must be strictly greater → Gate 3 ❌
        EXECUTION
            Output caching cross-tempo
                execution_hash includes tempo_id → Gate 4 ❌
            Wrong input in exec hash
                different input = different hash → Gate 4 ❌
            Model impersonation
                unapproved model_hash → Gate 2 ❌
        CRYPTOGRAPHIC
            Digest tamper
                any field change = digest mismatch → Gate 4 ❌
            Digest forgery
                SHA-256 preimage resistance → computationally infeasible
        BEHAVIORAL
            NTS gaming tank+recover
                catastrophic flag permanent cap
                scar accumulation non-linear
            Override abuse
                2/year hard cap
                immutable audit log
        COLLUSION
            Validator cartel
                gates deterministic
                disagreement is provable
                Yuma weight clipping
            Registry poisoning
                divergence detectable on-chain
```

---

## Deployment Topology

```mermaid
graph TB
    subgraph LOCALNET["Local Development (--subtensor.network local)"]
        LOCAL_NODE["node-subtensor --dev --one --validator\n(local chain, AURA consensus)"]
        LOCAL_M1["Miner 1\nport 8091\nwallet: miner1"]
        LOCAL_M2["Miner 2\nport 8092\nwallet: miner2"]
        LOCAL_V["Validator\nwallet: validator1\nstake: 1000 τ"]
        
        LOCAL_NODE <--> LOCAL_M1 & LOCAL_M2 & LOCAL_V
        LOCAL_V -->|"dendrite query"| LOCAL_M1 & LOCAL_M2
    end

    subgraph TESTNET["Testnet (--subtensor.network test)"]
        TEST_CHAIN["Bittensor Testnet\nFinney test nodes"]
        TEST_MINERS["3+ Test Miners\npublic IP required"]
        TEST_VALIDATORS["2+ Test Validators\nstaked on testnet"]
        
        TEST_CHAIN <--> TEST_MINERS & TEST_VALIDATORS
    end

    subgraph MAINNET["Mainnet (--subtensor.network finney)"]
        MAIN_CHAIN["Bittensor Mainnet\nFinney nodes"]
        MAIN_MINERS["INVARIANT Miners\nReal TAO emissions"]
        MAIN_VALIDATORS["INVARIANT Validators\nStaked TAO"]
        NTS_API["NTS Public API\nnts.invariant.network"]
        
        MAIN_CHAIN <--> MAIN_MINERS & MAIN_VALIDATORS
        MAIN_VALIDATORS --> NTS_API
    end

    LOCALNET -.->|"Phase 1 → Phase 2"| TESTNET
    TESTNET -.->|"Phase 2 → Phase 4"| MAINNET
```

---

## Phase 2 — Testnet Demonstration Targets

The following sequences will be demonstrated live on Bittensor testnet with block explorer links:

```mermaid
sequenceDiagram
    participant DEMO as Demo Observer
    participant V as Validator
    participant M as Miner
    participant BT as Testnet Explorer

    Note over DEMO,BT: Demo 1 — Valid receipt full cycle
    V->>M: Task for tempo T
    M->>V: Valid receipt + output
    V->>V: Gates 1,2,3,4 all PASS
    V->>BT: set_weights (miner has weight > 0)
    BT-->>DEMO: Block explorer shows weight update ✅

    Note over DEMO,BT: Demo 2 — Replay attack blocked
    M->>V: Same receipt (counter unchanged)
    V->>V: Gate 3 FAILS — REPLAY_DETECTED
    V->>BT: set_weights (miner weight = 0)
    BT-->>DEMO: Same tx hash, zero weight ✅

    Note over DEMO,BT: Demo 3 — Copy attack blocked
    M->>V: Miner B submits Miner A's receipt
    V->>V: Gate 1 FAILS — AGENT_NOT_AUTHORIZED
    V->>BT: set_weights (miner B weight = 0)
    BT-->>DEMO: Zero weight for cross-miner attempt ✅

    Note over DEMO,BT: Demo 4 — NTS degradation on violations
    V->>V: OAP records Gate 3 violation
    V->>V: NTS drops from 50 → 30
    V->>V: emission_weight *= (30/100) = 0.30
    BT-->>DEMO: Proportionally lower emissions ✅
```

---

*Architecture v1.0.0 — February 2026*  
*Orthonode Infrastructure Labs — orthonode.xyz*