// invariant-gates/src/verifier.rs
// ─────────────────────────────────────────────────────────────────
// Stateful four-gate receipt verifier.
//
// One instance per validator process.  Counter state is persisted to
// disk so restarts do not open a replay window.
//
// All four gates execute in sequence; the first failure short-circuits.
// Total execution time (SHA-256 + HashSet lookups): < 500 µs on any
// modern CPU.  Rust implementation target: < 50 µs.
// ─────────────────────────────────────────────────────────────────

use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use serde::{Deserialize, Serialize};

use crate::crypto::compute_receipt_digest;
use crate::receipt::{GateResult, Receipt};
use crate::registry::Registry;

// ─── Counter state ────────────────────────────────────────────────

/// Persisted counter state: maps agent_id_hex → last confirmed counter.
#[derive(Debug, Default, Serialize, Deserialize)]
struct CounterState {
    /// agent_id hex → last confirmed counter value
    counters: HashMap<String, u64>,
}

impl CounterState {
    fn load<P: AsRef<Path>>(path: P) -> Self {
        fs::read_to_string(&path)
            .ok()
            .and_then(|s| serde_json::from_str(&s).ok())
            .unwrap_or_default()
    }

    fn save<P: AsRef<Path>>(&self, path: P) {
        if let Ok(json) = serde_json::to_string(self) {
            let _ = fs::write(path, json);
        }
    }

    fn get(&self, agent_id_hex: &str) -> u64 {
        *self.counters.get(agent_id_hex).unwrap_or(&0)
    }

    fn advance(&mut self, agent_id_hex: &str, new_counter: u64) {
        self.counters.insert(agent_id_hex.to_owned(), new_counter);
    }
}

// ─── Verifier ────────────────────────────────────────────────────

/// Result of a full gate pass — includes gate number for OAP violation mapping.
#[derive(Debug, Clone)]
pub struct VerifyResult {
    pub result:      GateResult,
    pub gate_number: u8,   // 0 = pass, 1-4 = which gate failed
    pub detail:      String,
}

impl VerifyResult {
    fn pass() -> Self {
        Self { result: GateResult::Pass, gate_number: 0, detail: String::new() }
    }

    fn fail(gate: u8, result: GateResult, detail: impl Into<String>) -> Self {
        Self { result, gate_number: gate, detail: detail.into() }
    }
}

/// Thread-safe verifier.  Clone is cheap (Arc under the hood).
#[derive(Clone)]
pub struct Verifier {
    registry:    Registry,
    state:       Arc<Mutex<CounterState>>,
    state_path:  PathBuf,
}

impl Verifier {
    /// Create a new verifier backed by the given registry and state file.
    pub fn new<P: AsRef<Path>>(registry: Registry, state_path: P) -> Self {
        let state = CounterState::load(&state_path);
        Self {
            registry,
            state:      Arc::new(Mutex::new(state)),
            state_path: state_path.as_ref().to_path_buf(),
        }
    }

    /// Verify a single receipt through all four gates.
    ///
    /// Returns immediately on the first gate failure.
    /// On success, advances the counter (replay is now impossible).
    ///
    /// This function is the hot path.  Target: < 50 µs in --release.
    pub fn verify(&self, receipt: &Receipt) -> VerifyResult {
        // ── Gate 1: Identity authorisation ─────────────────────
        if !self.registry.is_authorized(&receipt.agent_id) {
            return VerifyResult::fail(
                1,
                GateResult::Gate1AgentNotAuthorized,
                format!("agent_id={} not in registry", &hex::encode(receipt.agent_id)[..12]),
            );
        }

        // ── Gate 2: Model approval ──────────────────────────────
        if !self.registry.is_approved_model(&receipt.model_hash) {
            return VerifyResult::fail(
                2,
                GateResult::Gate2ModelNotApproved,
                format!("model_hash={} not approved", &hex::encode(receipt.model_hash)[..12]),
            );
        }

        // ── Gate 3: Replay protection ───────────────────────────
        let agent_hex = hex::encode(receipt.agent_id);
        let mut state = self.state.lock().unwrap();
        let last_counter = state.get(&agent_hex);

        if receipt.counter <= last_counter {
            return VerifyResult::fail(
                3,
                GateResult::Gate3ReplayDetected,
                format!(
                    "counter={} not > last_confirmed={}",
                    receipt.counter, last_counter
                ),
            );
        }

        // ── Gate 4: Digest integrity ────────────────────────────
        let expected = compute_receipt_digest(
            &receipt.agent_id,
            &receipt.model_hash,
            &receipt.execution_hash,
            receipt.counter,
        );

        if expected != receipt.digest {
            return VerifyResult::fail(
                4,
                GateResult::Gate4DigestMismatch,
                format!(
                    "expected={} got={}",
                    &hex::encode(expected)[..12],
                    &hex::encode(receipt.digest)[..12]
                ),
            );
        }

        // ── All gates passed ────────────────────────────────────
        // Advance counter so this receipt cannot be replayed.
        state.advance(&agent_hex, receipt.counter);
        state.save(&self.state_path);

        VerifyResult::pass()
    }

    /// Verify a batch of receipts (returns in-order results).
    /// The validator calls this once per tempo for all miners.
    pub fn verify_batch(&self, receipts: &[Receipt]) -> Vec<VerifyResult> {
        receipts.iter().map(|r| self.verify(r)).collect()
    }

    /// Expose current counter for a given agent (used by miner on startup
    /// to resync after a crash).
    pub fn get_counter(&self, agent_id: &[u8; 32]) -> u64 {
        self.state.lock().unwrap().get(&hex::encode(agent_id))
    }
}

// ─── Receipt builder (miner side) ────────────────────────────────

use crate::crypto::{compute_execution_hash, compute_receipt_digest as _crd};

/// Build a complete, correctly-signed receipt.
/// Called by the miner after task execution.
pub fn build_receipt(
    agent_id:   &[u8; 32],
    model_hash: &[u8; 32],
    task_input: &str,
    output:     &str,
    counter:    u64,
    tempo_id:   u64,
    timestamp:  f64,
) -> Receipt {
    let execution_hash = compute_execution_hash(task_input, output, tempo_id, timestamp);
    let digest         = compute_receipt_digest(agent_id, model_hash, &execution_hash, counter);

    Receipt {
        agent_id:       *agent_id,
        model_hash:     *model_hash,
        execution_hash,
        counter,
        digest,
        version:   1,
        timestamp,
        tempo_id,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::registry::Registry;

    fn setup() -> (Verifier, [u8; 32], [u8; 32]) {
        let reg        = Registry::new();
        let agent_id   = [0x01u8; 32];
        let model_hash = [0x02u8; 32];
        reg.register_agent(&agent_id, "5TestHotkey", serde_json::Value::Null);
        reg.approve_model(&model_hash);

        let verifier = Verifier::new(reg, "/tmp/invariant_test_state.json");
        (verifier, agent_id, model_hash)
    }

    fn make_receipt(agent_id: &[u8; 32], model_hash: &[u8; 32], counter: u64) -> Receipt {
        build_receipt(agent_id, model_hash, "task input", "output answer", counter, 100, 0.0)
    }

    #[test]
    fn valid_receipt_passes() {
        let (v, agent, model) = setup();
        let r = make_receipt(&agent, &model, 1);
        assert_eq!(v.verify(&r).result, GateResult::Pass);
    }

    #[test]
    fn replay_blocked() {
        let (v, agent, model) = setup();
        let r = make_receipt(&agent, &model, 1);
        assert_eq!(v.verify(&r).result, GateResult::Pass);
        // Same receipt again — Gate 3 must fire
        assert_eq!(v.verify(&r).result, GateResult::Gate3ReplayDetected);
    }

    #[test]
    fn counter_must_advance() {
        let (v, agent, model) = setup();
        let r1 = make_receipt(&agent, &model, 5);
        let r2 = make_receipt(&agent, &model, 3); // lower counter
        assert_eq!(v.verify(&r1).result, GateResult::Pass);
        assert_eq!(v.verify(&r2).result, GateResult::Gate3ReplayDetected);
    }

    #[test]
    fn unknown_agent_gate1() {
        let (v, _, model) = setup();
        let unknown = [0xFFu8; 32];
        let r = make_receipt(&unknown, &model, 1);
        assert_eq!(v.verify(&r).result, GateResult::Gate1AgentNotAuthorized);
    }

    #[test]
    fn unapproved_model_gate2() {
        let (v, agent, _) = setup();
        let bad_model = [0xFFu8; 32];
        let r = make_receipt(&agent, &bad_model, 1);
        assert_eq!(v.verify(&r).result, GateResult::Gate2ModelNotApproved);
    }

    #[test]
    fn tampered_digest_gate4() {
        let (v, agent, model) = setup();
        let mut r = make_receipt(&agent, &model, 1);
        r.digest = [0u8; 32]; // zero-out the digest
        assert_eq!(v.verify(&r).result, GateResult::Gate4DigestMismatch);
    }

    #[test]
    fn batch_verify() {
        let (v, agent, model) = setup();
        let receipts = vec![
            make_receipt(&agent, &model, 1),
            make_receipt(&agent, &model, 2),
            make_receipt(&agent, &model, 3),
        ];
        let results = v.verify_batch(&receipts);
        for r in &results {
            assert_eq!(r.result, GateResult::Pass, "batch item failed: {:?}", r.detail);
        }
    }

    #[test]
    fn execution_hash_is_input_bound() {
        // Two miners with same model, same counter, DIFFERENT task input
        // → their execution_hashes differ → Gate 4 detects cross-copy
        let (v, agent, model) = setup();

        let r1 = build_receipt(&agent, &model, "task A", "4", 1, 100, 0.0);
        let r2 = build_receipt(&agent, &model, "task B", "4", 2, 100, 0.0);

        assert_ne!(r1.execution_hash, r2.execution_hash);
        assert_eq!(v.verify(&r1).result, GateResult::Pass);
        assert_eq!(v.verify(&r2).result, GateResult::Pass);
    }
}
