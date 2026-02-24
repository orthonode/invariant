// invariant-gates/benches/gate_bench.rs
// Run: cargo bench --features python-ext
// (python-ext not strictly needed for bench, but builds the full crate)

use criterion::{black_box, criterion_group, criterion_main, Criterion, BenchmarkId};

use invariant_gates::{
    Registry, Verifier, build_receipt,
    derive_software_agent_id, hash_model_identifier,
};

fn setup_verifier() -> (Verifier, [u8; 32], [u8; 32]) {
    let registry   = Registry::new();
    let model_hash = hash_model_identifier("bench-model-v1");
    let agent_id   = derive_software_agent_id("5BenchHotkey", &model_hash, 1000);

    registry.register_agent(&agent_id, "5BenchHotkey", serde_json::Value::Null);
    registry.approve_model(&model_hash);

    let verifier = Verifier::new(registry, "/tmp/bench_state.json");
    (verifier, agent_id, model_hash)
}

/// Benchmark a single receipt verification (all four gates, PASS path).
fn bench_single_verify(c: &mut Criterion) {
    let (verifier, agent_id, model_hash) = setup_verifier();

    // Pre-warm: each bench iteration needs a fresh counter
    let mut counter: u64 = 1_000_000;

    c.bench_function("verify_single_receipt_pass", |b| {
        b.iter(|| {
            counter += 1;
            let receipt = build_receipt(
                black_box(&agent_id),
                black_box(&model_hash),
                black_box("What is 2+2?"),
                black_box("4"),
                counter,
                100,
                1_700_000_000.0,
            );
            black_box(verifier.verify(&receipt))
        })
    });
}

/// Benchmark Gate 1 failure path (fastest path — returns immediately).
fn bench_gate1_fail(c: &mut Criterion) {
    let (verifier, _, model_hash) = setup_verifier();
    let unknown_agent = [0xFFu8; 32];
    let mut counter: u64 = 2_000_000;

    c.bench_function("verify_gate1_fail", |b| {
        b.iter(|| {
            counter += 1;
            let receipt = build_receipt(
                black_box(&unknown_agent),
                black_box(&model_hash),
                black_box("task"),
                black_box("output"),
                counter,
                100,
                0.0,
            );
            black_box(verifier.verify(&receipt))
        })
    });
}

/// Benchmark batch verification: 32 receipts (one subnet tempo).
fn bench_batch_32(c: &mut Criterion) {
    let (verifier, agent_id, model_hash) = setup_verifier();

    // Use different agents for batch so counters don't conflict
    let registry = Registry::new();
    let mut agents = Vec::new();
    for i in 0u64..32 {
        let m = hash_model_identifier(&format!("model-{i}"));
        let a = derive_software_agent_id(&format!("5Hotkey{i}"), &m, 1000);
        registry.register_agent(&a, &format!("5Hotkey{i}"), serde_json::Value::Null);
        registry.approve_model(&m);
        agents.push((a, m));
    }
    let batch_verifier = Verifier::new(registry, "/tmp/bench_batch_state.json");
    let mut base_counter: u64 = 3_000_000;

    c.bench_function("verify_batch_32_miners", |b| {
        b.iter(|| {
            base_counter += 1;
            let receipts: Vec<_> = agents
                .iter()
                .map(|(a, m)| {
                    build_receipt(a, m, "task input", "output", base_counter, 100, 0.0)
                })
                .collect();
            black_box(batch_verifier.verify_batch(&receipts))
        })
    });
}

/// Parametric benchmark: batch size scaling (8, 32, 64, 128, 192).
fn bench_batch_scaling(c: &mut Criterion) {
    let mut group = c.benchmark_group("batch_scaling");

    for size in [8u64, 32, 64, 128, 192] {
        let registry = Registry::new();
        let mut agents = Vec::new();
        for i in 0..size {
            let m = hash_model_identifier(&format!("scale-model-{size}-{i}"));
            let a = derive_software_agent_id(&format!("5ScaleHotkey{size}{i}"), &m, 1000);
            registry.register_agent(&a, &format!("5ScaleHotkey{size}{i}"), serde_json::Value::Null);
            registry.approve_model(&m);
            agents.push((a, m));
        }
        let path = format!("/tmp/bench_scale_{size}_state.json");
        let verifier = Verifier::new(registry, &path);
        let mut base: u64 = 4_000_000 + size * 100_000;

        group.bench_with_input(BenchmarkId::from_parameter(size), &size, |b, _| {
            b.iter(|| {
                base += 1;
                let receipts: Vec<_> = agents
                    .iter()
                    .map(|(a, m)| build_receipt(a, m, "input", "output", base, 100, 0.0))
                    .collect();
                black_box(verifier.verify_batch(&receipts))
            })
        });
    }

    group.finish();
}

criterion_group!(
    benches,
    bench_single_verify,
    bench_gate1_fail,
    bench_batch_32,
    bench_batch_scaling,
);
criterion_main!(benches);
