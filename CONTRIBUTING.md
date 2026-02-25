# Contributing to INVARIANT

**Deterministic Trust Infrastructure for Bittensor**  
*by Orthonode Infrastructure Labs*

Thank you for your interest in contributing to INVARIANT. This document explains how to contribute effectively and what standards we hold all contributions to.

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [What We're Looking For](#what-were-looking-for)
3. [Getting Started](#getting-started)
4. [Development Setup](#development-setup)
5. [Making Changes](#making-changes)
6. [Testing Requirements](#testing-requirements)
7. [Pull Request Process](#pull-request-process)
8. [Coding Standards](#coding-standards)
9. [Documentation Standards](#documentation-standards)
10. [Security Contributions](#security-contributions)

---

## Code of Conduct

INVARIANT is a professional infrastructure project. All contributors are expected to:

- Be direct, precise, and technical in communications
- Critique ideas, not people
- Back claims with evidence or code
- Respect that determinism is a non-negotiable design principle — do not propose changes that introduce probabilistic or behavioral security where cryptographic guarantees are possible
- Respect the security-first posture — no shortcuts in gate logic, ever

---

## What We're Looking For

### High Priority

- **Gate engine improvements** — performance, correctness, new attack vector coverage
- **OAP engine refinements** — scoring formula improvements, edge case handling
- **Bittensor integration fixes** — API compatibility updates, metagraph handling
- **Test coverage** — additional attack scenarios, edge cases, property-based tests
- **Documentation** — technical accuracy corrections, deployment guides, integration examples
- **Rust crate** — performance improvements, additional PyO3 bindings, benchmarks

### Medium Priority

- **Scripts** — wallet setup, subnet registration, deployment automation
- **CI/CD** — GitHub Actions workflows for automated test runs
- **Benchmarks** — additional throughput and latency measurements

### Out of Scope

- Changes that weaken the four-gate cryptographic guarantees
- Changes that introduce behavioral or probabilistic security where deterministic gates exist
- Features that require centralized infrastructure without a decentralization migration path
- UI/frontend work (INVARIANT is a protocol, not an application)

---

## Getting Started

### 1. Fork and clone

```bash
git clone https://github.com/orthonode/invariant.git
cd invariant
```

### 2. Create a branch

```bash
git checkout -b feat/your-feature-name
# or
git checkout -b fix/issue-description
# or
git checkout -b docs/what-you-are-documenting
```

Branch naming conventions:
- `feat/` — new features
- `fix/` — bug fixes
- `docs/` — documentation only
- `test/` — test additions/improvements
- `perf/` — performance improvements
- `refactor/` — code restructuring without behavior change

---

## Development Setup

### Python only (minimum setup)

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

pip install -r requirements.txt
pip install pytest pytest-asyncio

# Verify everything works
python scripts/test_locally.py
pytest invariant/invariant/tests/ -v
```

### With Rust (recommended for gate engine work)

```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"

# Install maturin
pip install maturin

# Build the Rust extension
cd invariant/invariant-gates
maturin develop --features python-ext --release
cd ../..

# Verify Rust backend active
python -c "
import sys
sys.path.insert(0, 'invariant/invariant/phase1_core')
from invariant_gates_bridge import using_rust
print('Rust:', using_rust())
"
# → Rust: True

# Run benchmarks
cd invariant/invariant-gates
cargo bench
```

### Full stack (with local Bittensor node)

```bash
# Clone and build subtensor
git clone https://github.com/opentensor/subtensor.git
cd subtensor
cargo build -p node-subtensor --release --features pow-faucet
./target/release/node-subtensor --dev --one --validator --rpc-external --rpc-cors=all --rpc-methods=unsafe &
cd ..

# One-shot wallet + subnet + neuron registration for local dev
python instant_register.py

# Launch miner and validator (root-level runners)
python miner.py --wallet.name miner1 --wallet.hotkey default --netuid 1 --subtensor.network local --axon.port 8091
python validator.py --wallet.name validator1 --wallet.hotkey default --netuid 1 --subtensor.network local
```

---

## Making Changes

### Gate engine changes

The four-gate logic in `invariant_gates.py` and the Rust crate `invariant-gates/src/verifier.rs` must remain **byte-for-byte equivalent**. Any change to gate logic must:

1. Be updated in both `invariant_gates.py` (Python fallback) AND `invariant-gates/src/` (Rust)
2. Produce identical results on all existing test vectors
3. Include new tests specifically covering the changed behavior
4. Update `THREAT_MODEL.md` if the change affects any threat vector

The bridge (`invariant_gates_bridge.py`) must never contain gate logic — it is a routing layer only.

### OAP engine changes

The OAP scoring formula in `invariant_oap.py` affects miner economics. Changes must:

1. Include explicit before/after comparison of NTS values for representative scenarios
2. Not introduce any path that allows NTS to exceed 100.0 or go below 0.0
3. Not introduce any mechanism for silent NTS resets (the append-only guarantee is absolute)
4. Update the `emission_weight` formula documentation if the formula changes

### Bittensor integration changes

Any change to `miner.py` or `validator.py` must:

1. Be compatible with Bittensor v10+ (PascalCase API)
2. Not break the graceful fallback for `serve_axon` Custom Error 10
3. Maintain the per-miner unique task dispatch pattern (not broadcast)
4. Be tested against a local subtensor node before PR submission

---

## Testing Requirements

**All PRs must pass all existing tests.** No exceptions.

```bash
# Full test suite — must all pass
pytest invariant/invariant/tests/ -v

# Local harness — must complete without failure
python scripts/test_locally.py

# Bridge self-test
python invariant/invariant/phase1_core/invariant_gates_bridge.py
```

### New tests required for

- Any new gate behavior → new test in `TestGateEngine`
- Any new OAP behavior → new test in `TestOAPEngine`
- Any new attack vector addressed → new test in `TestGateEngine` with explicit assertion on which gate fires and which gate number is returned
- Any performance-sensitive change → updated throughput assertion in `TestThroughput`

### Test standards

```python
# GOOD — isolated, explicit, documents the attack and defense
def test_attack_counter_rollback(self, verifier, agent_hex, model_hex):
    """Submitting a lower counter is blocked at Gate 3 (replay protection)."""
    r_high = build_receipt(agent_hex, model_hex, "t", "o", 500, 100, time.time())
    r_low  = build_receipt(agent_hex, model_hex, "t", "o", 3,   100, time.time())
    assert GateResult.is_pass(verifier.verify(r_high)["result"])
    result = verifier.verify(r_low)
    assert result["result"] == GateResult.GATE3
    assert result["gate_number"] == 3

# BAD — no assertion on which gate fired, no docstring, no counter isolation
def test_replay(self, verifier, receipt_factory):
    r = receipt_factory()
    verifier.verify(r)
    result = verifier.verify(r)
    assert result["result"] != "PASS"  # too vague
```

---

## Pull Request Process

### Before opening a PR

- [ ] All existing tests pass (`pytest invariant/invariant/tests/ -v`)
- [ ] Local harness passes (`python scripts/test_locally.py`)
- [ ] New tests added for new behavior
- [ ] Docstrings updated for any changed public functions
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] No new credentials, seed phrases, or wallet JSON files committed
- [ ] `.gitignore` includes any new file patterns that should not be committed

### PR description template

```
## Summary
One paragraph explaining what this changes and why.

## Type
- [ ] feat (new feature)
- [ ] fix (bug fix)
- [ ] docs (documentation)
- [ ] test (test improvements)
- [ ] perf (performance)
- [ ] refactor (no behavior change)

## Testing
- Existing tests: all pass (pytest invariant/invariant/tests/ -v)
- New tests added: [list test names]
- Local harness: passes (python scripts/test_locally.py)

## Gate/OAP Impact
[If applicable: describe any change to gate logic, OAP scoring, or emission formula]

## Breaking Changes
[None / describe breaking changes]
```

### Review criteria

PRs are reviewed for:

1. **Correctness** — Does it do what it claims? Are edge cases handled?
2. **Security** — Does it maintain or improve the cryptographic guarantees?
3. **Test coverage** — Are the new behaviors tested with clear assertions?
4. **Determinism** — Does it preserve deterministic behavior where determinism is required?
5. **Compatibility** — Does it remain compatible with Python 3.10+ and Bittensor v10+?
6. **Documentation** — Are public APIs documented? Is `CHANGELOG.md` updated?

---

## Coding Standards

### Python

- **Style:** PEP 8, 100-character line limit
- **Type hints:** Required on all public function signatures
- **Docstrings:** Required on all public classes and functions
- **Imports:** `import x` before `from x import y`; stdlib before third-party before local
- **Error handling:** Explicit exception types; never bare `except:`
- **Naming:** `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_CASE` for module-level constants

```python
# GOOD
def derive_software_agent_id(
    hotkey_ss58: str,
    model_hash_hex: str,
    registration_block: int,
) -> str:
    """
    Derive a 64-char hex agent_id for a software-only miner.

    Args:
        hotkey_ss58:        Bittensor hotkey in SS58 encoding.
        model_hash_hex:     Hex-encoded SHA-256 of the model identifier.
        registration_block: Block number at which the miner registered.

    Returns:
        64-character lowercase hex string (32 bytes).
    """

# BAD — missing type hints, missing docstring, unclear naming
def get_id(h, m, b):
    pass
```

### Rust

- **Style:** `cargo fmt` before every commit
- **Lints:** `cargo clippy -- -D warnings` must pass
- **Error handling:** `Result<T, E>` with descriptive error types; never `unwrap()` in library code
- **Safety:** No `unsafe` blocks without explicit justification comment

```bash
# Run before every commit (Rust changes)
cd invariant/invariant-gates
cargo fmt
cargo clippy -- -D warnings
cargo test
cargo bench --no-run  # ensure benchmarks compile
```

### Commit messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): short description (max 72 chars)

Optional longer body explaining WHY, not WHAT.
The diff shows what changed; the commit message explains why.

Closes #123
```

Types: `feat`, `fix`, `docs`, `test`, `perf`, `refactor`, `chore`

Scopes: `gates`, `oap`, `bridge`, `miner`, `validator`, `rust`, `tests`, `scripts`, `docs`

Examples:
```
feat(oap): add scar decay for minor violations after 10 clean tempos

fix(bridge): use counter+1 in tamper test to avoid Gate 3 false positive

test(gates): add counter rollback attack scenario to TestGateEngine

perf(rust): use batch SHA-256 computation for verify_batch
```

---

## Documentation Standards

### Technical accuracy

All documentation claims must be verifiable. Do not write:
- "INVARIANT is the fastest subnet" (unverified superlative)
- "This is impossible to hack" (no security absolute)
- "Works on all chains" (scope not verified)

Write instead:
- "INVARIANT achieves <50µs per receipt on the Rust backend (benchmarked on commodity hardware)"
- "SHA-256 preimage attacks are computationally infeasible with current hardware"
- "INVARIANT is deployed on Bittensor and tested against Arbitrum Sepolia and TON Testnet"

### Mermaid diagrams

All architecture diagrams use Mermaid syntax. Test diagrams at [mermaid.live](https://mermaid.live) before committing.

### Code blocks in documentation

All command examples must be tested on a clean environment before documentation is merged. Mark untested examples with `# [UNTESTED]` in a comment.

---

## Security Contributions

See [SECURITY.md](SECURITY.md) for the full vulnerability disclosure policy.

**Summary:** Do not open public GitHub issues for security vulnerabilities. Email `security@orthonode.xyz` with a description and proof-of-concept. We respond within 48 hours.

Security contributions that responsibly disclose gate bypass vulnerabilities, OAP score manipulation techniques, or cryptographic weaknesses will be credited in `CHANGELOG.md` and `THREAT_MODEL.md`.

---

## Questions

- **GitHub Issues** — for bugs, feature requests, and documentation improvements
- **GitHub Discussions** — for design questions and architectural proposals
- **Email** — `contact@orthonode.xyz` for everything else

---

*Thank you for helping make INVARIANT more robust, more secure, and more useful to the Bittensor ecosystem.*

*— Orthonode Infrastructure Labs*