# INVARIANT — Roadmap

> **Deterministic Trust Infrastructure for Bittensor**
> *by Orthonode Infrastructure Labs*

---

## Vision

INVARIANT becomes the canonical trust layer for the Bittensor ecosystem — the primitive that every subnet, every validator, and every enterprise AI consumer relies on to answer the question: *"Did this miner actually run what they claim to have run?"*

---

## Status Overview

| Phase | Name | Target | Status |
|-------|------|--------|--------|
| **0** | Foundation — Live Contracts | Completed | ✅ Done |
| **1** | Core Engine + Local Subnet | Feb 2026 | ✅ Done |
| **2** | Testnet Deployment | Mar 2026 | 🔄 Active |
| **3** | Cross-Subnet NTS API | Apr 2026 | 📋 Planned |
| **4** | Mainnet Launch | May–Jun 2026 | 📋 Planned |
| **5** | Enterprise + Protocol Revenue | Q3 2026 | 📋 Planned |
| **6** | DAO Governance | Q4 2026 | 📋 Planned |

---

## Phase 0 — Foundation (Completed)

**What was built before INVARIANT as a Bittensor subnet:**

### SHA — Hardware Attestation Primitive (Arbitrum Sepolia)
- ✅ eFuse silicon identity binding (ESP32-S3 hardware)
- ✅ Four-gate execution receipt system (Keccak-256 on Arbitrum)
- ✅ Rust + Stylus on-chain verification
- ✅ 89+ live transactions on Arbitrum Sepolia
- ✅ Contract: `0xD661a1aB8CEFaaCd78F4B968670C3bC438415615`
- ✅ 10,000+ Keccak-256 test vectors — 100% cross-layer parity confirmed
- ✅ $25K grant application submitted (Stylus Sprint, Feb 2026)

### TON-SHA — Agent Trust Primitive (TON Testnet)
- ✅ Four-gate system ported to Tact 1.6 (TON blockchain)
- ✅ SHA-256 native verification on TON
- ✅ 17+ live transactions on TON Testnet
- ✅ Contract: `kQBVqAhPv_ANWm0hfjJdLnQmvvC8_rQ_NEryVX3uFOUF05OP`
- ✅ 0.03 TON per operation (gas efficient)
- ✅ TON Fast Grants application submitted

### OAP — Integrity Governance Engine (Architecture)
- ✅ Lifecycle trust scoring model (0–100)
- ✅ Append-only behavioral history design
- ✅ Catastrophic flag + scar accumulation model
- ✅ Adaptive anchoring system
- ✅ Override governance (2/yr cap)
- ✅ Architecture published at orthonode.xyz/oap.html

### Research
- ✅ IoTeX exploit forensic analysis published (Feb 22, 2026)
- ✅ SHA DePIN deep-dive article published
- ✅ Formal threat model (8 attacker assumptions, 5 out-of-scope vectors)

---

## Phase 1 — Core Engine + Local Subnet (Completed)

**INVARIANT Python/Rust subnet engine, local testability.**

### Engine
- ✅ `invariant_gates.py` — Pure Python four-gate verifier (fallback)
- ✅ `invariant_gates_bridge.py` — Unified Rust/Python bridge
- ✅ `invariant_oap.py` — Full OAP lifecycle engine
- ✅ Rust crate `invariant-gates` with PyO3 bindings
- ✅ 136-byte receipt format (agent_id, model_hash, execution_hash, counter, digest)
- ✅ Rust throughput: ~9,000+ receipts/second on local hardware
- ✅ Python fallback: ~500 receipts/second

### Bittensor Integration
- ✅ `miner.py` — Bittensor v10 Axon miner (PascalCase API)
- ✅ `validator.py` — Three-tier scoring pipeline
- ✅ Per-miner unique task dispatch (different task per miner per tempo)
- ✅ `emission_weight = output_quality × (NTS/100) × freshness`
- ✅ Graceful serve_axon fallback for Custom Error 10

### Testing
- ✅ 21 pytest tests passing (all 8 attack vectors + OAP lifecycle + throughput)
- ✅ `scripts/test_locally.py` — Full local harness, no node required
- ✅ Bridge self-test with throughput reporting

---

## Phase 2 — Testnet Deployment (March 2026)

**Target: Live INVARIANT subnet on Bittensor testnet. Demo-ready.**

### Week 1 (Mar 2–9): Port + Register
- [ ] Port Python SDK to pip-installable `veritas-miner` package
- [ ] Register INVARIANT on Bittensor testnet (obtain NETUID)
- [ ] Fund wallets via testnet faucet
- [ ] Deploy 3 miners + 2 validators on testnet

### Week 2 (Mar 10–16): Live Demonstration
- [ ] Run full tempo cycle: task → execution → receipt → verification → weights
- [ ] Demonstrate replay attack prevention live (Gate 3 fail, on-chain proof)
- [ ] Demonstrate copy attack prevention live (Gate 1 fail, on-chain proof)
- [ ] Demonstrate model impersonation prevention live (Gate 2 fail)
- [ ] Demonstrate digest tamper prevention live (Gate 4 fail)
- [ ] Record all demonstrations with block explorer links

### Week 3 (Mar 17–23): Open Source + Documentation
- [ ] Open-source miner SDK on GitHub under MIT
- [ ] Write integration guide for other subnet operators
- [ ] Record demo video: all four gates live on testnet explorer
- [ ] Publish INVARIANT as a complete Bittensor subnet template

### Week 4 (Mar 24–30): Stress Test
- [ ] Stress test with 10+ simultaneous miners
- [ ] Document gas/compute costs for validators
- [ ] Polish pitch materials for Hackquest Demo Day
- [ ] Prepare comparative analysis vs Omron, Targon, Chainlink

### Deliverables
- Working INVARIANT subnet on Bittensor testnet
- Block explorer links showing four-gate verification in live tempo cycles
- Open-source SDK published to PyPI
- Complete documentation suite

---

## Phase 3 — Cross-Subnet NTS API (April 2026)

**INVARIANT becomes infrastructure for the entire Bittensor ecosystem.**

### NTS Registry API
- [ ] REST API endpoint: `GET /nts/{hotkey}` → current NTS score + history
- [ ] WebSocket subscription: `SUBSCRIBE /nts/{hotkey}` → real-time NTS updates
- [ ] Batch endpoint: `POST /nts/batch` → query up to 256 hotkeys at once
- [ ] Signed response format: cryptographically verifiable NTS attestations

### Cross-Subnet Integration
- [ ] SubnetsAPI integration: other subnets can query INVARIANT NTS before accepting miner outputs
- [ ] Integration documentation for subnet operators
- [ ] Demo integration with one willing Bittensor subnet
- [ ] Validator plugin: drop-in Python module any validator can add

### Adversarial Task Track
- [ ] Deploy adversarial reasoning task track (math proofs, code generation with CI test suites)
- [ ] Task difficulty scaling (harder tasks as miner NTS rises)
- [ ] Objective scoring oracle for code generation tasks (sandboxed execution)

### Deliverables
- Public NTS API with documentation
- First cross-subnet integration (live)
- Adversarial task track live on testnet
- 3-page integration guide for subnet operators

---

## Phase 4 — Mainnet Launch (May–June 2026)

**INVARIANT goes live on Bittensor mainnet with real TAO emissions.**

### Technical
- [ ] Full security audit of four-gate Rust implementation
- [ ] Subtensor state persistence for counter/registry (Phase 2 uses JSON files)
- [ ] Extrinsic-based agent registration (on-chain, not JSON)
- [ ] Validator consensus threshold: require 2/3 validators to agree on NTS state
- [ ] Emergency circuit breaker: pause emissions if >50% of validators report collusion

### Economic
- [ ] Emission model: 18% to subnet owner (INVARIANT) for first 30 days (cold-start bonus)
- [ ] Transition to standard Bittensor emission schedule after day 30
- [ ] Anti-gaming analysis: model expected NTS distribution under adversarial miners
- [ ] TAO staking requirement for model registration (prevents spam)

### Community
- [ ] INVARIANT Discord server launch
- [ ] Miner onboarding guide (full video walkthrough)
- [ ] Validator onboarding guide
- [ ] First 100 miners outreach (target existing Bittensor miner community)
- [ ] Partnership announcement with Opentensor Foundation

### Deliverables
- INVARIANT live on Bittensor mainnet
- 50+ registered miners at launch
- Mainnet block explorer showing live NTS scores
- TAO emission flowing to miners with verified receipts

---

## Phase 5 — Enterprise + Protocol Revenue (Q3 2026)

**INVARIANT generates revenue independent of TAO emissions.**

### Enterprise API
- [ ] REST API for enterprise receipt verification queries
  - `POST /verify` → verify any receipt, returns signed attestation
  - `GET /audit/{agent_id}` → full behavioral history export
  - `GET /report/{agent_id}` → formatted compliance report
- [ ] EU AI Act compliance report generation
  - Article 13 traceability: model version, execution timestamp, input hash, output hash
  - PDF export with cryptographic attestation
- [ ] SLA: 99.9% uptime, <100ms response time
- [ ] Pricing: $0.001–$0.01 per verified receipt (micro-SaaS)

### Revenue Model
- [ ] Protocol fee: 0.1% of emission weight transactions → INVARIANT DAO treasury
- [ ] Enterprise API subscriptions: $500–$5,000/month per organization
- [ ] Compliance reports: $10–$50 per report
- [ ] Integration fees: one-time setup for subnet integrations

### Market Targets
| Segment | Target | Timeline |
|---------|--------|----------|
| Bittensor subnet operators | 10 integrations | Q3 2026 |
| DePIN networks (Helium, io.net) | 3 partnerships | Q3–Q4 2026 |
| Enterprise AI consumers | 5 pilot customers | Q4 2026 |
| EU AI Act compliance buyers | 2 enterprise pilots | Q1 2027 |

### Deliverables
- Enterprise API live with SLA
- First paid enterprise customer
- EU AI Act compliance module
- $10K+ monthly protocol revenue

---

## Phase 6 — DAO Governance (Q4 2026)

**INVARIANT transitions to community governance.**

### Governance Structure
- [ ] INVARIANT DAO: TAO-weighted voting on protocol parameters
- [ ] Approved model registry: community-governed (currently validator-controlled)
- [ ] Override governance: DAO ratifies overrides > 2/yr
- [ ] Emission parameter governance: DAO votes on NTS formula coefficients

### Approved Model Registry
- [ ] Open submission process: any miner can submit model hash for approval
- [ ] Community review: 7-day voting period, 2/3 majority required
- [ ] Automatic approval: models meeting automated quality benchmarks
- [ ] Emergency revocation: 24-hour fast-track for compromised models

### Protocol Upgrades
- [ ] INVARIANT Improvement Proposals (IIPs) — Bittensor BIP-style governance
- [ ] Upgrade timelock: 14 days between proposal and activation
- [ ] Emergency upgrade path: 24-hour timelock for critical security fixes

### Deliverables
- Governance smart contracts deployed
- First DAO vote completed
- Open model registry live
- INVARIANT foundation legal entity (India)

---

## Long-Term Vision (2027+)

### INVARIANT as Universal Trust Layer
- **Bittensor ecosystem:** NTS becomes the standard trust metric cited in subnet documentation
- **DePIN:** INVARIANT receipts become the audit trail for hardware reward networks
- **Regulatory:** EU AI Act Article 13 compliance is a solved problem for Bittensor miners
- **Enterprise:** Fortune 500 companies consuming decentralized AI verify outputs via INVARIANT

### Technical Evolution
- **Hardware path:** Full ESP32-S3 eFuse integration for DePIN miners
- **ZK receipts:** ZK-SNARK wrapper for privacy-preserving receipt verification
- **Cross-chain:** INVARIANT receipts valid on Arbitrum, TON, and Bittensor simultaneously
- **Autonomous agents:** INVARIANT as the trust root for agent-to-agent collaboration

---

## Metrics We Track

| Metric | Phase 2 Target | Phase 4 Target | 2027 Target |
|--------|---------------|----------------|-------------|
| Registered miners | 10 | 500 | 10,000 |
| Receipts verified / day | 1,000 | 100,000 | 10,000,000 |
| Subnet integrations | 0 | 5 | 50 |
| NTS queries / day | 100 | 10,000 | 1,000,000 |
| Protocol revenue / month | $0 | $1,000 | $100,000 |
| Test coverage | 21 tests | 100 tests | 500 tests |

---

## What We Will Never Do

- We will not centralize the approved model registry beyond the bootstrap period
- We will not allow NTS resets — the append-only behavioral history is a core guarantee
- We will not add special validator privileges that create cartel opportunities
- We will not require special hardware (no mandatory TEE servers, no mandatory eFuse chips)
- We will not modify the four-gate logic without a DAO vote and 14-day timelock

---

*Last updated: February 2026*
*Maintained by: Orthonode Infrastructure Labs — orthonode.xyz*