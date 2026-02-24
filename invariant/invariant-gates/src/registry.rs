// invariant-gates/src/registry.rs
// ─────────────────────────────────────────────────────────────────
// In-memory registry of authorised agents and approved model hashes.
//
// Phase 1: loaded from JSON file on disk.
// Phase 2: synced from subtensor extrinsics (on-chain anchor).
//
// All lookups are O(1) HashSet operations.
// Thread-safe: uses std::sync::RwLock — many readers, single writer.
// ─────────────────────────────────────────────────────────────────

use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::Path;
use std::sync::{Arc, RwLock};

use serde::{Deserialize, Serialize};

// ─── Persisted schema ─────────────────────────────────────────────

#[derive(Debug, Serialize, Deserialize)]
pub struct RegistryFile {
    pub version: u32,
    /// hex agent_id → metadata
    pub agents: HashMap<String, AgentMeta>,
    /// list of approved model hashes (hex)
    pub models: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentMeta {
    pub hotkey: String,
    pub registered: f64, // unix timestamp
    #[serde(default)]
    pub metadata: serde_json::Value,
}

impl Default for RegistryFile {
    fn default() -> Self {
        Self {
            version: 1,
            agents: HashMap::new(),
            models: Vec::new(),
        }
    }
}

// ─── Runtime registry (hot-path lookups) ─────────────────────────

#[derive(Debug, Default)]
struct Inner {
    /// Set of authorised agent_ids (raw bytes as hex strings for easy JSON round-trip)
    agents: HashSet<String>,
    /// Set of approved model hashes (hex strings)
    models: HashSet<String>,
    /// Full metadata for informational queries
    meta: HashMap<String, AgentMeta>,
}

/// Thread-safe registry shared between the verifier and registration code.
#[derive(Debug, Clone)]
pub struct Registry(Arc<RwLock<Inner>>);

impl Registry {
    /// Create empty registry.
    pub fn new() -> Self {
        Registry(Arc::new(RwLock::new(Inner::default())))
    }

    /// Load from JSON file.  Returns empty registry if file absent/corrupt.
    pub fn from_file<P: AsRef<Path>>(path: P) -> Self {
        let reg = Self::new();
        if let Ok(data) = fs::read_to_string(&path) {
            if let Ok(file) = serde_json::from_str::<RegistryFile>(&data) {
                let mut inner = reg.0.write().unwrap();
                for (aid, meta) in &file.agents {
                    inner.agents.insert(aid.clone());
                    inner.meta.insert(aid.clone(), meta.clone());
                }
                for m in &file.models {
                    inner.models.insert(m.clone());
                }
            }
        }
        reg
    }

    /// Save current state to JSON file.
    pub fn save<P: AsRef<Path>>(&self, path: P) -> std::io::Result<()> {
        let inner = self.0.read().unwrap();
        let file = RegistryFile {
            version: 1,
            agents: inner.meta.clone(),
            models: inner.models.iter().cloned().collect(),
        };
        let json = serde_json::to_string_pretty(&file)
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;
        fs::write(path, json)
    }

    // ── Gate 1 check ──────────────────────────────────────────────

    /// Returns true if the agent_id is registered.
    /// Called on the hot path — must be < 1 µs.
    #[inline]
    pub fn is_authorized(&self, agent_id: &[u8; 32]) -> bool {
        let hex = hex::encode(agent_id);
        self.0.read().unwrap().agents.contains(&hex)
    }

    // ── Gate 2 check ──────────────────────────────────────────────

    /// Returns true if the model hash is in the approved set.
    #[inline]
    pub fn is_approved_model(&self, model_hash: &[u8; 32]) -> bool {
        let hex = hex::encode(model_hash);
        self.0.read().unwrap().models.contains(&hex)
    }

    // ── Write operations (registration path, not hot) ─────────────

    pub fn register_agent(&self, agent_id: &[u8; 32], hotkey: &str, metadata: serde_json::Value) {
        let hex = hex::encode(agent_id);
        let mut inner = self.0.write().unwrap();
        let meta = AgentMeta {
            hotkey: hotkey.to_owned(),
            registered: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_secs_f64())
                .unwrap_or(0.0),
            metadata,
        };
        inner.agents.insert(hex.clone());
        inner.meta.insert(hex, meta);
    }

    pub fn approve_model(&self, model_hash: &[u8; 32]) {
        let hex = hex::encode(model_hash);
        self.0.write().unwrap().models.insert(hex);
    }

    pub fn get_agent_meta(&self, agent_id: &[u8; 32]) -> Option<AgentMeta> {
        let hex = hex::encode(agent_id);
        self.0.read().unwrap().meta.get(&hex).cloned()
    }

    pub fn agent_count(&self) -> usize {
        self.0.read().unwrap().agents.len()
    }

    pub fn model_count(&self) -> usize {
        self.0.read().unwrap().models.len()
    }
}

impl Default for Registry {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_registry() -> (Registry, [u8; 32], [u8; 32]) {
        let reg = Registry::new();
        let agent_id = [0xAAu8; 32];
        let model_hash = [0xBBu8; 32];
        reg.register_agent(&agent_id, "5FakeHotkey", serde_json::Value::Null);
        reg.approve_model(&model_hash);
        (reg, agent_id, model_hash)
    }

    #[test]
    fn gate1_authorized() {
        let (reg, agent_id, _) = test_registry();
        assert!(reg.is_authorized(&agent_id));
    }

    #[test]
    fn gate1_unauthorized() {
        let (reg, _, _) = test_registry();
        assert!(!reg.is_authorized(&[0xFFu8; 32]));
    }

    #[test]
    fn gate2_approved() {
        let (reg, _, model_hash) = test_registry();
        assert!(reg.is_approved_model(&model_hash));
    }

    #[test]
    fn gate2_unapproved() {
        let (reg, _, _) = test_registry();
        assert!(!reg.is_approved_model(&[0xFFu8; 32]));
    }

    #[test]
    fn counts() {
        let (reg, _, _) = test_registry();
        assert_eq!(reg.agent_count(), 1);
        assert_eq!(reg.model_count(), 1);
    }
}
