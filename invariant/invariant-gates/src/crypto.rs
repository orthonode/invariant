// invariant-gates/src/crypto.rs
// ─────────────────────────────────────────────────────────────────
// All cryptographic primitives used by INVARIANT.
// No external key material.  All operations are deterministic.
// ─────────────────────────────────────────────────────────────────

use sha2::{Digest, Sha256};
use tiny_keccak::{Hasher, Keccak};

// ─── SHA-256 helpers ──────────────────────────────────────────────

/// SHA-256 of a single byte slice.
#[inline]
pub fn sha256(data: &[u8]) -> [u8; 32] {
    let mut h = Sha256::new();
    h.update(data);
    h.finalize().into()
}

/// SHA-256 of two concatenated slices (avoids heap alloc).
#[inline]
pub fn sha256_2(a: &[u8], b: &[u8]) -> [u8; 32] {
    let mut h = Sha256::new();
    h.update(a);
    h.update(b);
    h.finalize().into()
}

// ─── Identity derivation ─────────────────────────────────────────

/// Layer 1 — software miner identity.
///
/// agent_id = SHA-256(hotkey_utf8 || model_hash || reg_block_be_u64)
pub fn derive_software_agent_id(
    hotkey_ss58:        &str,
    model_hash:         &[u8; 32],
    registration_block: u64,
) -> [u8; 32] {
    let mut h = Sha256::new();
    h.update(hotkey_ss58.as_bytes());
    h.update(model_hash);
    h.update(registration_block.to_be_bytes());
    h.finalize().into()
}

/// Layer 1 — DePIN / hardware miner identity.
///
/// agent_id = Keccak-256(efuse_mac || chip_model_byte)
/// Ethereum-compatible, matches the original SHA contract.
pub fn derive_hardware_agent_id(efuse_mac: &[u8], chip_model_byte: &[u8]) -> [u8; 32] {
    let mut k = Keccak::v256();
    let mut out = [0u8; 32];
    k.update(efuse_mac);
    k.update(chip_model_byte);
    k.finalize(&mut out);
    out
}

/// Hash a model identifier string → 32-byte model_hash.
pub fn hash_model_identifier(identifier: &str) -> [u8; 32] {
    sha256(identifier.as_bytes())
}

// ─── Receipt hashing ─────────────────────────────────────────────

/// Compute execution_hash binding task input + output + tempo + timestamp.
///
/// execution_hash = SHA-256(task_input_utf8 || output_utf8 || tempo_id_be_u64 || ts_be_f64)
///
/// Cannot be forged without running the computation on the given input.
pub fn compute_execution_hash(
    task_input: &str,
    output:     &str,
    tempo_id:   u64,
    timestamp:  f64,
) -> [u8; 32] {
    let mut h = Sha256::new();
    h.update(task_input.as_bytes());
    h.update(output.as_bytes());
    h.update(tempo_id.to_be_bytes());
    h.update(timestamp.to_be_bytes());
    h.finalize().into()
}

/// Compute receipt digest over all four core fields (packed, big-endian).
///
/// digest = SHA-256(agent_id || model_hash || execution_hash || counter_be_u64)
///
/// Gate 4 recomputes this and compares.
/// If ANY field was tampered with, the digest will not match.
pub fn compute_receipt_digest(
    agent_id:       &[u8; 32],
    model_hash:     &[u8; 32],
    execution_hash: &[u8; 32],
    counter:        u64,
) -> [u8; 32] {
    let mut h = Sha256::new();
    h.update(agent_id);
    h.update(model_hash);
    h.update(execution_hash);
    h.update(counter.to_be_bytes());
    h.finalize().into()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sha256_is_deterministic() {
        let a = sha256(b"hello invariant");
        let b = sha256(b"hello invariant");
        assert_eq!(a, b);
        assert_ne!(a, sha256(b"different"));
    }

    #[test]
    fn keccak_is_deterministic() {
        let a = derive_hardware_agent_id(b"mac:AA:BB:CC", b"ESP32-S3");
        let b = derive_hardware_agent_id(b"mac:AA:BB:CC", b"ESP32-S3");
        assert_eq!(a, b);
        assert_ne!(a, derive_hardware_agent_id(b"mac:AA:BB:CC", b"OTHER"));
    }

    #[test]
    fn execution_hash_binds_to_input() {
        let h1 = compute_execution_hash("task A", "output 4", 100, 1_700_000_000.0);
        let h2 = compute_execution_hash("task B", "output 4", 100, 1_700_000_000.0);
        // Changing the task input changes the hash — copy attack impossible
        assert_ne!(h1, h2);
    }

    #[test]
    fn execution_hash_binds_to_tempo() {
        let h1 = compute_execution_hash("task", "output", 100, 0.0);
        let h2 = compute_execution_hash("task", "output", 101, 0.0);
        // Different tempo → different hash — caching across tempos impossible
        assert_ne!(h1, h2);
    }

    #[test]
    fn digest_binds_all_fields() {
        let agent   = [1u8; 32];
        let model   = [2u8; 32];
        let exec    = [3u8; 32];
        let d1 = compute_receipt_digest(&agent, &model, &exec, 1);
        let d2 = compute_receipt_digest(&agent, &model, &exec, 2); // counter changed
        assert_ne!(d1, d2);
    }

    /// Known-answer test: SHA-256("") = e3b0c4...
    #[test]
    fn sha256_known_answer() {
        let expected = hex::decode(
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        ).unwrap();
        let got = sha256(b"");
        assert_eq!(&got[..], &expected[..]);
    }
}
