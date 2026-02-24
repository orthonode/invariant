# INVARIANT — Security Policy

**Maintained by:** Orthonode Infrastructure Labs  
**Contact:** security@orthonode.xyz  
**PGP:** Available on request  

---

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x (current) | ✅ Active security fixes |
| 0.x.x | ❌ End of life |

---

## Reporting a Vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.**

If you discover a security vulnerability in INVARIANT, please report it responsibly:

### Primary Contact

**Email:** security@orthonode.xyz  
**Subject line:** `[INVARIANT SECURITY] <brief description>`  
**Response time:** We aim to acknowledge all reports within **48 hours**.

### What to Include

A high-quality report includes:

1. **Affected component** — Which file, function, or layer (Gate 1–4, OAP, bridge, Bittensor integration)
2. **Attack vector** — How the vulnerability is triggered (local / network / cryptographic)
3. **Impact assessment** — What an attacker can achieve (emission fraud, NTS manipulation, replay bypass, etc.)
4. **Proof of concept** — Minimal reproduction steps or code snippet (do not include live exploit code targeting production)
5. **Suggested fix** — If you have one (optional but appreciated)

### What Happens Next

| Timeline | Action |
|----------|--------|
| 0–48h | Acknowledgement email sent |
| 48h–7d | Triage, reproduction, severity classification |
| 7–14d | Fix developed and reviewed internally |
| 14–21d | Fix deployed to testnet, reporter notified |
| 21–30d | Public disclosure (coordinated with reporter) |
| 30d | CVE requested if applicable |

We will keep you informed at each stage. If you want to remain anonymous, say so explicitly — we will never disclose your identity without consent.

---

## Severity Classification

We use the following severity levels based on impact to the INVARIANT protocol:

### Critical

Vulnerabilities that allow an attacker to:
- Forge a valid four-gate receipt without running the actual computation
- Bypass Gate 4 digest verification without a SHA-256 preimage
- Clear or reset the OAP catastrophic flag programmatically
- Silently corrupt the validator state file (counter state) across multiple validators
- Drain TAO emissions to a rogue miner across a full tempo cycle

**Response:** Immediate hotfix, emergency disclosure within 7 days.

### High

Vulnerabilities that allow an attacker to:
- Bypass Gate 3 replay protection for a single receipt reuse
- Force Gate 1 or Gate 2 to pass for an unauthorized agent or unapproved model
- Apply more than 2 OAP overrides per year via any code path
- Cause a validator to produce non-deterministic gate results for the same receipt

**Response:** Fix within 14 days, coordinated disclosure.

### Medium

Vulnerabilities that allow an attacker to:
- Manipulate NTS scoring outside the documented formula parameters
- Cause denial-of-service on the validator via malformed receipt inputs
- Read another miner's OAP ledger data without authorization
- Cause the bridge to silently fall back to Python without warning when Rust is expected

**Response:** Fix within 30 days.

### Low / Informational

- Logic edge cases that produce unexpected but non-exploitable behavior
- Documentation gaps that could lead to misuse
- Performance degradation that does not affect correctness
- Non-security bugs in test or script files

**Response:** Fix in next scheduled release.

---

## Cryptographic Scope

INVARIANT's security guarantees rest on the following cryptographic primitives:

| Primitive | Usage | Standard |
|-----------|-------|----------|
| SHA-256 | Receipt digest, execution hash, agent_id derivation | FIPS 180-4 |
| Keccak-256 | Hardware agent_id derivation (DePIN path) | Ethereum standard |

**Out of scope (assumed secure):**

The following are treated as trusted primitives and are not within INVARIANT's security boundary:

- SHA-256 and Keccak-256 preimage resistance (computational hardness assumption)
- Bittensor subtensor chain integrity (Bittensor protocol responsibility)
- Python `hashlib` and `json` standard library correctness
- Rust `sha2` crate correctness (open-source, community-audited)
- Bittensor hotkey signing security (Bittensor wallet responsibility)

If you discover a vulnerability in any of these upstream dependencies, please report directly to the relevant maintainers. You may also notify us so we can communicate impact to our users.

---

## Bug Bounty

INVARIANT is currently in pre-mainnet development. We do not have a formal paid bug bounty program yet.

However, we publicly acknowledge all responsible disclosures in:
- The `CHANGELOG.md` (with reporter's name/handle if they consent)
- A dedicated **Security Researchers** section in the repository README
- Orthonode's public communications on X / Twitter

We are committed to establishing a formal paid bounty program at mainnet launch (Phase 4, Q2 2026). Researchers who report Critical or High severity findings before mainnet launch will be given priority status and retroactive recognition when the program launches.

---

## Known Non-Issues

The following behaviors are **by design** and are not security vulnerabilities:

| Behavior | Reason |
|----------|--------|
| NTS starts at 50 for new agents | Cold-start calibration; not exploitable for significant gain |
| Counter gaps are permitted (e.g., jump from 100 to 200) | Only regression is blocked; gaps are valid in the monotonic model |
| Python fallback is slower than Rust | Performance difference only; gate logic is identical |
| Registry is a plain JSON file | Phase 1 design; on-chain registry in Phase 2 |
| OAP ledger is not encrypted | Ledger contains non-sensitive behavioral metadata only |
| `execute_task` uses `eval()` for math tasks | Input is whitelist-filtered to `[0-9+-*/().% ]` before eval |

---

## Security Architecture Summary

For the full cryptographic threat model, see [THREAT_MODEL.md](THREAT_MODEL.md).

The key structural security properties of INVARIANT are:

1. **Determinism:** Two honest validators running the same receipt against the same registry always produce identical gate results. Any divergence is cryptographically provable evidence of tampering.

2. **Physical unforgeability:** The `execution_hash = SHA-256(task_input ‖ output ‖ tempo_id)` field cannot be produced without running the actual computation. This is the foundational "proof of execution" guarantee.

3. **Append-only history:** The OAP ledger never silently resets. Past violations permanently affect future NTS via scar accumulation. The catastrophic flag has no programmatic clear path.

4. **Bounded governance:** Override governance is capped at 2 per calendar year per agent. Every override is written to an immutable append-only log with timestamp, justification, and authorizing identity.

5. **No trusted intermediary:** INVARIANT's verification is self-contained. No oracle, no off-chain service, and no centralized authority is required to verify a receipt. Any validator with the same registry can independently reproduce the verification result.

---

## Disclosure Policy

We follow a **coordinated disclosure** model:

- We will work with the reporter to understand and reproduce the vulnerability before any public disclosure.
- We will not disclose any vulnerability publicly until a fix has been tested and deployed.
- We commit to a maximum 90-day embargo from the date of first report. After 90 days, we will disclose regardless of fix status, to protect users.
- We will credit researchers in all public disclosures unless they request anonymity.
- We will never threaten legal action against researchers who act in good faith.

---

## Version History of This Document

| Version | Date | Notes |
|---------|------|-------|
| 1.0.0 | Feb 2026 | Initial security policy. |

---

*Orthonode Infrastructure Labs — Building deterministic verification infrastructure.*  
*orthonode.xyz · security@orthonode.xyz*