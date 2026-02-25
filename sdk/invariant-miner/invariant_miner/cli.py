"""
invariant_miner/cli.py
=====================
Command-line entry points for the invariant-miner SDK.

Commands
--------
invariant-info   Print SDK version, backend status, and system info.
invariant-check  Run a self-test: build a receipt, verify it, check all gates.

These are installed as console scripts via pyproject.toml:
    [project.scripts]
    invariant-info  = "invariant_miner.cli:info"
    invariant-check = "invariant_miner.cli:check"
"""

from __future__ import annotations

import json
import sys
import time

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _print_banner() -> None:
    print()
    print("  ██╗ ███╗   ██╗ ██╗   ██╗  █████╗  ██████╗  ██╗  █████╗  ███╗   ██╗ ████████╗")
    print("  ██║ ████╗  ██║ ██║   ██║ ██╔══██╗ ██╔══██╗ ██║ ██╔══██╗ ████╗  ██║ ╚══██╔══╝")
    print("  ██║ ██╔██╗ ██║ ██║   ██║ ███████║ ██████╔╝ ██║ ███████║ ██╔██╗ ██║    ██║   ")
    print("  ██║ ██║╚██╗██║ ╚██╗ ██╔╝ ██╔══██║ ██╔══██╗ ██║ ██╔══██║ ██║╚██╗██║    ██║   ")
    print("  ██║ ██║ ╚████║  ╚████╔╝  ██║  ██║ ██║  ██║ ██║ ██║  ██║ ██║ ╚████║    ██║   ")
    print("  ╚═╝ ╚═╝  ╚═══╝   ╚═══╝   ╚═╝  ╚═╝ ╚═╝  ╚═╝ ╚═╝ ╚═╝  ╚═╝ ╚═╝  ╚═══╝    ╚═╝   ")
    print()
    print("  invariant-miner — INVARIANT Miner SDK")
    print("  by Orthonode Infrastructure Labs · orthonode.xyz")
    print()


def _green(s: str) -> str:
    return f"\033[92m{s}\033[0m"


def _red(s: str) -> str:
    return f"\033[91m{s}\033[0m"


def _yellow(s: str) -> str:
    return f"\033[93m{s}\033[0m"


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m"


def _supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _ok(msg: str) -> str:
    prefix = _green("✅  PASS") if _supports_color() else "PASS"
    return f"  {prefix}  {msg}"


def _fail(msg: str) -> str:
    prefix = _red("❌  FAIL") if _supports_color() else "FAIL"
    return f"  {prefix}  {msg}"


def _info(msg: str) -> str:
    prefix = _bold("  ·") if _supports_color() else "  ·"
    return f"{prefix}  {msg}"


# ─────────────────────────────────────────────────────────────────────────────
# invariant-info
# ─────────────────────────────────────────────────────────────────────────────


def info() -> None:
    """Print SDK version, backend status, and system information.

    Entry point for the ``invariant-info`` console script.
    """
    _print_banner()

    # ── Import SDK ────────────────────────────────────────────────────────────
    try:
        import invariant_miner as vm
    except ImportError as e:
        print(_fail(f"Failed to import invariant_miner: {e}"))
        sys.exit(1)

    # ── Version ───────────────────────────────────────────────────────────────
    print(_bold("  SDK Information"))
    print("  " + "─" * 50)
    print(_info(f"Version:        {vm.__version__}"))
    print(_info(f"Author:         {vm.__author__}"))
    print(_info(f"License:        {vm.__license__}"))

    # ── Backend ───────────────────────────────────────────────────────────────
    print()
    print(_bold("  Backend"))
    print("  " + "─" * 50)
    is_rust = vm.using_rust()
    if is_rust:
        backend_str = (
            _green("Rust (invariant_gates_rs)")
            if _supports_color()
            else "Rust (invariant_gates_rs)"
        )
        speed_str = "~50–100× faster than Python fallback"
    else:
        backend_str = (
            _yellow("Python (fallback)") if _supports_color() else "Python (fallback)"
        )
        speed_str = "functional but slower — build Rust for production"

    print(_info(f"Active backend: {backend_str}"))
    print(_info(f"Speed note:     {speed_str}"))

    if not is_rust:
        print()
        print(
            "  " + _yellow("To enable the Rust backend:")
            if _supports_color()
            else "  To enable the Rust backend:"
        )
        print("    cd invariant/invariant-gates")
        print("    maturin develop --features python-ext --release")

    # ── Python info ───────────────────────────────────────────────────────────
    print()
    print(_bold("  Python Environment"))
    print("  " + "─" * 50)
    print(_info(f"Python version: {sys.version.split()[0]}"))
    print(_info(f"Executable:     {sys.executable}"))

    # ── Quick throughput benchmark ────────────────────────────────────────────
    print()
    print(_bold("  Quick Benchmark (100 receipts)"))
    print("  " + "─" * 50)

    try:
        import tempfile

        from invariant_miner import (
            Registry,
            Verifier,
            build_receipt,
            derive_agent_id,
            hash_model,
        )

        with tempfile.TemporaryDirectory() as tmp:
            mh = hash_model("bench-model-v1")
            aid = derive_agent_id("5BenchHotkey", "bench-model-v1", 1000)

            reg = Registry(path=f"{tmp}/registry.json")
            reg.register_agent(aid, "5BenchHotkey")
            reg.approve_model(mh)
            reg.save()

            verifier = Verifier(registry=reg, state_path=f"{tmp}/state.json")

            # Warmup
            for i in range(10):
                r = build_receipt(
                    agent_id=aid,
                    model_identifier="bench-model-v1",
                    task_input=f"warmup{i}",
                    output=f"out{i}",
                    counter=i + 1,
                    tempo_id=0,
                )
                verifier.verify(r)

            # Timed
            N = 100
            BASE = 100_000
            t0 = time.perf_counter()
            for i in range(N):
                r = build_receipt(
                    agent_id=aid,
                    model_identifier="bench-model-v1",
                    task_input=f"task_{i}",
                    output=f"output_{i}",
                    counter=BASE + i,
                    tempo_id=1,
                )
                verifier.verify(r)
            elapsed = time.perf_counter() - t0
            per_us = (elapsed / N) * 1_000_000
            rate = int(N / elapsed)
            print(_info(f"Per receipt:    {per_us:.1f} µs"))
            print(_info(f"Throughput:     {rate:,} receipts/second"))
    except Exception as exc:
        print(_info(f"Benchmark skipped: {exc}"))

    print()


# ─────────────────────────────────────────────────────────────────────────────
# invariant-check
# ─────────────────────────────────────────────────────────────────────────────


def check() -> None:
    """Run a comprehensive self-test of the SDK.

    Tests all four gates, attack vectors, and the receipt round-trip.
    Exit code 0 = all passed. Exit code 1 = one or more failures.

    Entry point for the ``invariant-check`` console script.
    """
    _print_banner()
    print(_bold("  Running self-test..."))
    print("  " + "═" * 60)
    print()

    failures = 0

    # ── Import ────────────────────────────────────────────────────────────────
    try:
        import tempfile

        from invariant_miner import (
            GateResult,
            Receipt,
            Registry,
            Verifier,
            build_receipt,
            derive_agent_id,
            hash_model,
            using_rust,
        )
    except ImportError as e:
        print(_fail(f"Import failed: {e}"))
        sys.exit(1)

    backend = "Rust" if using_rust() else "Python (fallback)"
    print(_info(f"Backend: {backend}"))
    print()

    with tempfile.TemporaryDirectory() as tmp:
        # ── Setup ─────────────────────────────────────────────────────────────
        MODEL_ID = "invariant-check-model-v1"
        HOTKEY = "5InvariantCheckHotkey"

        mh = hash_model(MODEL_ID)
        aid = derive_agent_id(HOTKEY, MODEL_ID, registration_block=1)

        reg = Registry(path=f"{tmp}/registry.json")
        reg.register_agent(aid, HOTKEY)
        reg.approve_model(mh)
        reg.save()

        verifier = Verifier(registry=reg, state_path=f"{tmp}/state.json")

        # ── Test 1: Valid receipt passes all four gates ───────────────────────
        try:
            r = build_receipt(
                agent_id=aid,
                model_identifier=MODEL_ID,
                task_input="What is 2+2?",
                output="4",
                counter=1,
                tempo_id=100,
            )
            result = verifier.verify(r)
            assert result.is_pass(), f"Expected PASS, got {result.result}"
            print(_ok("Test 1 — Valid receipt passes all four gates"))
        except Exception as e:
            print(_fail(f"Test 1 — Valid receipt: {e}"))
            failures += 1

        # ── Test 2: Gate 3 — Replay blocked ──────────────────────────────────
        try:
            r = build_receipt(
                agent_id=aid,
                model_identifier=MODEL_ID,
                task_input="replay task",
                output="answer",
                counter=2,
                tempo_id=100,
            )
            res1 = verifier.verify(r)
            assert res1.is_pass(), f"First verify should pass, got {res1.result}"
            res2 = verifier.verify(r)  # replay — same counter
            assert res2.result == GateResult.GATE3, (
                f"Replay should trigger Gate 3, got {res2.result}"
            )
            print(_ok("Test 2 — Gate 3: replay correctly blocked"))
        except Exception as e:
            print(_fail(f"Test 2 — Gate 3 replay: {e}"))
            failures += 1

        # ── Test 3: Gate 3 — Counter rollback blocked ─────────────────────────
        try:
            r_high = build_receipt(
                agent_id=aid,
                model_identifier=MODEL_ID,
                task_input="t",
                output="o",
                counter=500,
                tempo_id=100,
            )
            r_low = build_receipt(
                agent_id=aid,
                model_identifier=MODEL_ID,
                task_input="t",
                output="o",
                counter=3,
                tempo_id=100,
            )
            verifier.verify(r_high)
            res = verifier.verify(r_low)
            assert res.result == GateResult.GATE3, (
                f"Counter rollback should trigger Gate 3, got {res.result}"
            )
            print(_ok("Test 3 — Gate 3: counter rollback correctly blocked"))
        except Exception as e:
            print(_fail(f"Test 3 — Gate 3 counter rollback: {e}"))
            failures += 1

        # ── Test 4: Gate 1 — Unknown agent blocked ────────────────────────────
        try:
            unknown_aid = "ff" * 32  # not in registry
            r = build_receipt(
                agent_id=unknown_aid,
                model_identifier=MODEL_ID,
                task_input="t",
                output="o",
                counter=1,
                tempo_id=100,
            )
            res = verifier.verify(r)
            assert res.result == GateResult.GATE1, (
                f"Unknown agent should trigger Gate 1, got {res.result}"
            )
            print(_ok("Test 4 — Gate 1: unknown agent correctly blocked"))
        except Exception as e:
            print(_fail(f"Test 4 — Gate 1 unknown agent: {e}"))
            failures += 1

        # ── Test 5: Gate 2 — Unapproved model blocked ─────────────────────────
        try:
            bad_model_hash = "ee" * 32  # not in approved list
            r = build_receipt(
                agent_id=aid,
                model_identifier="",  # supply model_hash directly
                task_input="t",
                output="o",
                counter=600,
                tempo_id=100,
                model_hash=bad_model_hash,
            )
            res = verifier.verify(r)
            assert res.result == GateResult.GATE2, (
                f"Unapproved model should trigger Gate 2, got {res.result}"
            )
            print(_ok("Test 5 — Gate 2: unapproved model correctly blocked"))
        except Exception as e:
            print(_fail(f"Test 5 — Gate 2 unapproved model: {e}"))
            failures += 1

        # ── Test 6: Gate 4 — Tampered digest blocked ──────────────────────────
        try:
            r = build_receipt(
                agent_id=aid,
                model_identifier=MODEL_ID,
                task_input="t",
                output="o",
                counter=700,
                tempo_id=100,
            )
            # Tamper: replace digest with zeros
            tampered = Receipt(
                agent_id=r.agent_id,
                model_hash=r.model_hash,
                execution_hash=r.execution_hash,
                counter=r.counter,
                digest="00" * 32,  # zeroed digest
                version=r.version,
                timestamp=r.timestamp,
                tempo_id=r.tempo_id,
            )
            res = verifier.verify(tampered)
            assert res.result == GateResult.GATE4, (
                f"Tampered digest should trigger Gate 4, got {res.result}"
            )
            print(_ok("Test 6 — Gate 4: tampered digest correctly blocked"))
        except Exception as e:
            print(_fail(f"Test 6 — Gate 4 tampered digest: {e}"))
            failures += 1

        # ── Test 7: Receipt JSON round-trip ───────────────────────────────────
        try:
            r = build_receipt(
                agent_id=aid,
                model_identifier=MODEL_ID,
                task_input="round trip test",
                output="result",
                counter=800,
                tempo_id=200,
            )
            json_str = r.to_json()
            r2 = Receipt.from_json(json_str)
            assert r.agent_id == r2.agent_id
            assert r.model_hash == r2.model_hash
            assert r.execution_hash == r2.execution_hash
            assert r.counter == r2.counter
            assert r.digest == r2.digest
            print(_ok("Test 7 — Receipt JSON round-trip (to_json / from_json)"))
        except Exception as e:
            print(_fail(f"Test 7 — JSON round-trip: {e}"))
            failures += 1

        # ── Test 8: Receipt binary round-trip (136 bytes) ─────────────────────
        try:
            r = build_receipt(
                agent_id=aid,
                model_identifier=MODEL_ID,
                task_input="binary round trip",
                output="result",
                counter=900,
                tempo_id=300,
            )
            raw = r.to_bytes()
            assert len(raw) == 136, f"Expected 136 bytes, got {len(raw)}"
            r2 = Receipt.from_bytes(raw)
            assert r.agent_id == r2.agent_id
            assert r.counter == r2.counter
            assert r.digest == r2.digest
            print(_ok("Test 8 — Receipt binary round-trip (136 bytes)"))
        except Exception as e:
            print(_fail(f"Test 8 — Binary round-trip: {e}"))
            failures += 1

        # ── Test 9: Batch verify ──────────────────────────────────────────────
        try:
            receipts = [
                build_receipt(
                    agent_id=aid,
                    model_identifier=MODEL_ID,
                    task_input=f"batch_task_{i}",
                    output=f"out_{i}",
                    counter=1_000_000 + i,
                    tempo_id=400,
                )
                for i in range(10)
            ]
            results = verifier.verify_batch(receipts)
            passing = [rv for rv in results if rv.is_pass()]
            assert len(passing) == 10, f"Expected 10/10 passing, got {len(passing)}/10"
            print(_ok("Test 9 — Batch verify: 10/10 receipts passed"))
        except Exception as e:
            print(_fail(f"Test 9 — Batch verify: {e}"))
            failures += 1

        # ── Test 10: execution_hash binds to task input ───────────────────────
        try:
            r1 = build_receipt(
                agent_id=aid,
                model_identifier=MODEL_ID,
                task_input="task A",
                output="4",
                counter=2_000_001,
                tempo_id=500,
            )
            r2 = build_receipt(
                agent_id=aid,
                model_identifier=MODEL_ID,
                task_input="task B",
                output="4",  # same output, different input
                counter=2_000_002,
                tempo_id=500,
            )
            assert r1.execution_hash != r2.execution_hash, (
                "Different task inputs must produce different execution_hashes"
            )
            print(
                _ok(
                    "Test 10 — execution_hash binds to task input (copy attack impossible)"
                )
            )
        except Exception as e:
            print(_fail(f"Test 10 — execution_hash binding: {e}"))
            failures += 1

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("  " + "═" * 60)
    total = 10
    passed = total - failures
    print(f"  {passed}/{total} tests passed")

    if failures == 0:
        msg = (
            _green("ALL TESTS PASSED — invariant-miner is working correctly")
            if _supports_color()
            else "ALL TESTS PASSED — invariant-miner is working correctly"
        )
        print(f"\n  🎉  {msg}\n")
        sys.exit(0)
    else:
        msg = (
            _red(f"{failures} test(s) FAILED")
            if _supports_color()
            else f"{failures} test(s) FAILED"
        )
        print(f"\n  ❌  {msg}\n")
        sys.exit(1)
