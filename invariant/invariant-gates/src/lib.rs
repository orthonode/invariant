// invariant-gates/src/lib.rs
// ─────────────────────────────────────────────────────────────────
// Crate root.  Wires all modules together and exposes the PyO3
// Python extension module when compiled with --features python-ext.
//
// Build as a Python extension:
//   maturin develop --features python-ext
//   maturin build   --features python-ext --release
//
// Build as a pure Rust library (tests / benchmarks):
//   cargo test
//   cargo bench
// ─────────────────────────────────────────────────────────────────

pub mod crypto;
pub mod receipt;
pub mod registry;
pub mod verifier;

pub use crypto::{
    compute_execution_hash, compute_receipt_digest, derive_hardware_agent_id,
    derive_software_agent_id, hash_model_identifier,
};
pub use receipt::{GateResult, Receipt, ReceiptJson};
pub use registry::Registry;
pub use verifier::{build_receipt, Verifier, VerifyResult};

// ─── Python extension (compiled only with the python-ext feature) ──

#[cfg(feature = "python-ext")]
mod python {
    use pyo3::exceptions::PyValueError;
    use pyo3::prelude::*;

    use crate::crypto::{
        compute_execution_hash, compute_receipt_digest, derive_hardware_agent_id,
        derive_software_agent_id, hash_model_identifier,
    };
    use crate::receipt::{GateResult, Receipt, ReceiptJson};
    use crate::registry::Registry;
    use crate::verifier::{build_receipt, Verifier};

    // ── Python-visible types ──────────────────────────────────────

    /// Python wrapper around the Rust Verifier.
    /// Usage from Python:
    ///   from invariant_gates_rs import RsVerifier
    ///   v = RsVerifier("./registry.json", "./state.json")
    ///   result_json = v.verify_json(receipt_json_str)
    #[pyclass(name = "RsVerifier")]
    struct PyVerifier {
        inner: Verifier,
    }

    #[pymethods]
    impl PyVerifier {
        #[new]
        fn new(registry_path: &str, state_path: &str) -> Self {
            let registry = Registry::from_file(registry_path);
            PyVerifier {
                inner: Verifier::new(registry, state_path),
            }
        }

        /// Verify a JSON-encoded receipt.
        /// Returns JSON: {"result": "PASS"|"GATE1_...", "gate_number": 0-4, "detail": "..."}
        fn verify_json(&self, receipt_json: &str) -> PyResult<String> {
            let rj: ReceiptJson = serde_json::from_str(receipt_json)
                .map_err(|e| PyValueError::new_err(format!("parse error: {e}")))?;
            let receipt = rj
                .to_receipt()
                .map_err(|e| PyValueError::new_err(format!("hex decode error: {e}")))?;
            let vr = self.inner.verify(&receipt);
            let out = serde_json::json!({
                "result":      vr.result.code(),
                "gate_number": vr.gate_number,
                "detail":      vr.detail,
            });
            Ok(out.to_string())
        }

        /// Batch verify.  Input: JSON array of receipt objects.
        /// Returns: JSON array of result objects (same order).
        fn verify_batch_json(&self, receipts_json: &str) -> PyResult<String> {
            let rjs: Vec<ReceiptJson> = serde_json::from_str(receipts_json)
                .map_err(|e| PyValueError::new_err(format!("parse error: {e}")))?;
            let receipts: Vec<Receipt> = rjs
                .into_iter()
                .map(|rj| {
                    rj.to_receipt()
                        .map_err(|e| PyValueError::new_err(e.to_string()))
                })
                .collect::<PyResult<_>>()?;
            let results = self.inner.verify_batch(&receipts);
            let out: Vec<_> = results
                .iter()
                .map(|vr| {
                    serde_json::json!({
                        "result":      vr.result.code(),
                        "gate_number": vr.gate_number,
                        "detail":      vr.detail,
                    })
                })
                .collect();
            Ok(serde_json::to_string(&out).unwrap())
        }

        /// Get the last confirmed counter for an agent_id (hex string).
        fn get_counter(&self, agent_id_hex: &str) -> PyResult<u64> {
            let bytes = hex::decode(agent_id_hex)
                .map_err(|e| PyValueError::new_err(format!("hex: {e}")))?;
            if bytes.len() != 32 {
                return Err(PyValueError::new_err(
                    "agent_id must be 32 bytes (64 hex chars)",
                ));
            }
            let mut arr = [0u8; 32];
            arr.copy_from_slice(&bytes);
            Ok(self.inner.get_counter(&arr))
        }
    }

    // ── Free functions exposed to Python ──────────────────────────

    /// Derive software miner agent_id.
    /// Returns 64-character hex string.
    #[pyfunction]
    fn py_derive_software_agent_id(
        hotkey_ss58: &str,
        model_hash_hex: &str,
        registration_block: u64,
    ) -> PyResult<String> {
        let bytes = hex::decode(model_hash_hex)
            .map_err(|e| PyValueError::new_err(format!("model_hash hex: {e}")))?;
        if bytes.len() != 32 {
            return Err(PyValueError::new_err("model_hash must be 32 bytes"));
        }
        let mut model_hash = [0u8; 32];
        model_hash.copy_from_slice(&bytes);
        let id = derive_software_agent_id(hotkey_ss58, &model_hash, registration_block);
        Ok(hex::encode(id))
    }

    /// Derive DePIN hardware miner agent_id (Keccak-256).
    #[pyfunction]
    fn py_derive_hardware_agent_id(efuse_mac_hex: &str, chip_model_hex: &str) -> PyResult<String> {
        let mac = hex::decode(efuse_mac_hex)
            .map_err(|e| PyValueError::new_err(format!("efuse_mac hex: {e}")))?;
        let chip = hex::decode(chip_model_hex)
            .map_err(|e| PyValueError::new_err(format!("chip_model hex: {e}")))?;
        Ok(hex::encode(derive_hardware_agent_id(&mac, &chip)))
    }

    /// Hash a model identifier string → 64-char hex model_hash.
    #[pyfunction]
    fn py_hash_model(identifier: &str) -> String {
        hex::encode(hash_model_identifier(identifier))
    }

    /// Build a complete receipt (miner side).
    /// Returns JSON string.
    #[pyfunction]
    #[allow(clippy::too_many_arguments)]
    fn py_build_receipt(
        agent_id_hex: &str,
        model_hash_hex: &str,
        task_input: &str,
        output: &str,
        counter: u64,
        tempo_id: u64,
        timestamp: f64,
    ) -> PyResult<String> {
        let decode32 = |s: &str| -> PyResult<[u8; 32]> {
            let v = hex::decode(s).map_err(|e| PyValueError::new_err(format!("hex: {e}")))?;
            if v.len() != 32 {
                return Err(PyValueError::new_err("expected 32-byte field"));
            }
            let mut arr = [0u8; 32];
            arr.copy_from_slice(&v);
            Ok(arr)
        };
        let agent_id = decode32(agent_id_hex)?;
        let model_hash = decode32(model_hash_hex)?;
        let receipt = build_receipt(
            &agent_id,
            &model_hash,
            task_input,
            output,
            counter,
            tempo_id,
            timestamp,
        );
        let rj = ReceiptJson::from_receipt(&receipt);
        Ok(serde_json::to_string(&rj).unwrap())
    }

    // ── Module definition ─────────────────────────────────────────

    #[pymodule]
    pub fn invariant_gates_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
        m.add_class::<PyVerifier>()?;
        m.add_function(wrap_pyfunction!(py_derive_software_agent_id, m)?)?;
        m.add_function(wrap_pyfunction!(py_derive_hardware_agent_id, m)?)?;
        m.add_function(wrap_pyfunction!(py_hash_model, m)?)?;
        m.add_function(wrap_pyfunction!(py_build_receipt, m)?)?;
        m.add("__version__", env!("CARGO_PKG_VERSION"))?;
        Ok(())
    }
}

// Re-export the PyO3 module init function at crate root so maturin finds it.
#[cfg(feature = "python-ext")]
pub use python::invariant_gates_rs;
