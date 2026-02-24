// invariant-gates/src/receipt.rs
// ─────────────────────────────────────────────────────────────────
// INVARIANT receipt data structures.
// These are the canonical types.  Python code converts to/from JSON.
// The 136-byte serialised form is what travels over Axon/Dendrite.
// ─────────────────────────────────────────────────────────────────

use serde::{Deserialize, Serialize};

/// Fixed-size receipt — exactly 136 bytes on the wire.
///
/// Field layout (big-endian):
///   agent_id        32 bytes   SHA-256(hotkey || model_hash || reg_block)
///   model_hash      32 bytes   SHA-256(model identifier / weights)
///   execution_hash  32 bytes   SHA-256(task_input || output || tempo_id || ts)
///   counter          8 bytes   monotonic uint64
///   digest          32 bytes   SHA-256(agent_id || model_hash || execution_hash || counter)
///   ─────────────────────────
///   TOTAL          136 bytes
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Receipt {
    pub agent_id: [u8; 32],
    pub model_hash: [u8; 32],
    pub execution_hash: [u8; 32],
    pub counter: u64,
    pub digest: [u8; 32],

    // ── Metadata (not included in digest) ───────────────────────
    #[serde(default)]
    pub version: u8,
    #[serde(default)]
    pub timestamp: f64,
    #[serde(default)]
    pub tempo_id: u64,
}

impl Receipt {
    /// Serialise to exactly 136 bytes (digest fields only).
    pub fn to_bytes(&self) -> [u8; 136] {
        let mut buf = [0u8; 136];
        buf[0..32].copy_from_slice(&self.agent_id);
        buf[32..64].copy_from_slice(&self.model_hash);
        buf[64..96].copy_from_slice(&self.execution_hash);
        buf[96..104].copy_from_slice(&self.counter.to_be_bytes());
        buf[104..136].copy_from_slice(&self.digest);
        buf
    }

    /// Deserialise from 136 bytes.
    pub fn from_bytes(b: &[u8; 136]) -> Self {
        let mut agent_id = [0u8; 32];
        let mut model_hash = [0u8; 32];
        let mut execution_hash = [0u8; 32];
        let mut digest = [0u8; 32];

        agent_id.copy_from_slice(&b[0..32]);
        model_hash.copy_from_slice(&b[32..64]);
        execution_hash.copy_from_slice(&b[64..96]);
        let counter = u64::from_be_bytes(b[96..104].try_into().unwrap());
        digest.copy_from_slice(&b[104..136]);

        Receipt {
            agent_id,
            model_hash,
            execution_hash,
            counter,
            digest,
            version: 1,
            timestamp: 0.0,
            tempo_id: 0,
        }
    }
}

/// JSON-serialisable form used for transport over Axon (hex strings).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReceiptJson {
    pub version: u8,
    pub agent_id: String,       // hex
    pub model_hash: String,     // hex
    pub execution_hash: String, // hex
    pub counter: u64,
    pub digest: String, // hex
    pub timestamp: f64,
    pub tempo_id: u64,
}

impl ReceiptJson {
    pub fn from_receipt(r: &Receipt) -> Self {
        Self {
            version: r.version,
            agent_id: hex::encode(r.agent_id),
            model_hash: hex::encode(r.model_hash),
            execution_hash: hex::encode(r.execution_hash),
            counter: r.counter,
            digest: hex::encode(r.digest),
            timestamp: r.timestamp,
            tempo_id: r.tempo_id,
        }
    }

    pub fn to_receipt(&self) -> Result<Receipt, hex::FromHexError> {
        let decode32 = |s: &str| -> Result<[u8; 32], hex::FromHexError> {
            let v = hex::decode(s)?;
            let mut arr = [0u8; 32];
            arr.copy_from_slice(&v);
            Ok(arr)
        };
        Ok(Receipt {
            agent_id: decode32(&self.agent_id)?,
            model_hash: decode32(&self.model_hash)?,
            execution_hash: decode32(&self.execution_hash)?,
            counter: self.counter,
            digest: decode32(&self.digest)?,
            version: self.version,
            timestamp: self.timestamp,
            tempo_id: self.tempo_id,
        })
    }
}

/// Outcome of the four-gate verification pass.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum GateResult {
    Pass,
    Gate1AgentNotAuthorized,
    Gate2ModelNotApproved,
    Gate3ReplayDetected,
    Gate4DigestMismatch,
    ParseError(String),
}

impl GateResult {
    pub fn is_pass(&self) -> bool {
        matches!(self, GateResult::Pass)
    }

    /// Human-readable code (used by Python side for OAP violation mapping).
    pub fn code(&self) -> &'static str {
        match self {
            GateResult::Pass => "PASS",
            GateResult::Gate1AgentNotAuthorized => "GATE1_AGENT_NOT_AUTHORIZED",
            GateResult::Gate2ModelNotApproved => "GATE2_MODEL_NOT_APPROVED",
            GateResult::Gate3ReplayDetected => "GATE3_REPLAY_DETECTED",
            GateResult::Gate4DigestMismatch => "GATE4_DIGEST_MISMATCH",
            GateResult::ParseError(_) => "PARSE_ERROR",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trip_bytes() {
        let r = Receipt {
            agent_id: [1u8; 32],
            model_hash: [2u8; 32],
            execution_hash: [3u8; 32],
            counter: 42,
            digest: [4u8; 32],
            version: 1,
            timestamp: 0.0,
            tempo_id: 100,
        };
        let bytes = r.to_bytes();
        assert_eq!(bytes.len(), 136);
        let r2 = Receipt::from_bytes(&bytes);
        assert_eq!(r.agent_id, r2.agent_id);
        assert_eq!(r.counter, r2.counter);
        assert_eq!(r.digest, r2.digest);
    }

    #[test]
    fn round_trip_json() {
        let r = Receipt {
            agent_id: [0xABu8; 32],
            model_hash: [0xCDu8; 32],
            execution_hash: [0xEFu8; 32],
            counter: 999,
            digest: [0x12u8; 32],
            version: 1,
            timestamp: 1_700_000_000.0,
            tempo_id: 50,
        };
        let j = ReceiptJson::from_receipt(&r);
        let r2 = j.to_receipt().unwrap();
        assert_eq!(r.agent_id, r2.agent_id);
        assert_eq!(r.counter, r2.counter);
    }
}
