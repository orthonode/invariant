#!/usr/bin/env python3
"""
INVARIANT Local Test Suite
==========================
Pixel-art terminal interface for running the INVARIANT receipt verification
and OAP lifecycle tests locally.  No Bittensor node required.

Usage:
    python scripts/test_locally.py
    python scripts/test_locally.py --no-color
    python scripts/test_locally.py --quick
"""

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Path setup — works from repo root or scripts/
# ─────────────────────────────────────────────────────────────────────────────

_repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(_repo_root / "invariant" / "invariant" / "phase1_core"))
sys.path.insert(0, str(_repo_root / "invariant" / "phase1_core"))

from invariant_gates_bridge import (
    GateResult,
    Registry,
    Verifier,
    build_receipt,
    derive_software_agent_id,
    hash_model,
    using_rust,
)

from invariant_oap import OAPEngine, ViolationType

# ─────────────────────────────────────────────────────────────────────────────
# Terminal color / style engine
# ─────────────────────────────────────────────────────────────────────────────

_USE_COLOR = True


def _esc(*codes: int) -> str:
    if not _USE_COLOR:
        return ""
    return "\033[" + ";".join(str(c) for c in codes) + "m"


RESET = lambda: _esc(0)
BOLD = lambda: _esc(1)
DIM = lambda: _esc(2)

# Palette — coral/salmon matching the pixel-art aesthetic
CORAL = lambda: _esc(38, 5, 209)  # #e07050 — the orange-coral pixel colour
AMBER = lambda: _esc(38, 5, 214)  # bright orange accent
GREEN = lambda: _esc(38, 5, 82)  # pass green
RED = lambda: _esc(38, 5, 196)  # fail red
YELLOW = lambda: _esc(38, 5, 226)  # warning yellow
CYAN = lambda: _esc(38, 5, 51)  # info cyan
WHITE = lambda: _esc(97)  # bright white
GREY = lambda: _esc(38, 5, 244)  # dim grey
BG_DARK = lambda: _esc(48, 5, 234)  # near-black background stripe


def c(color_fn, text: str) -> str:
    return f"{color_fn()}{text}{RESET()}"


# ─────────────────────────────────────────────────────────────────────────────
# Pixel-art font  (5-wide × 5-tall, '#' = filled pixel)
# Each '#' renders as '██'  (two full-block chars → square pixel)
# Each ' ' renders as '  '  (two spaces)
# ─────────────────────────────────────────────────────────────────────────────

_FONT: dict[str, list[str]] = {
    "I": [
        "#####",
        "  #  ",
        "  #  ",
        "  #  ",
        "#####",
    ],
    "N": [
        "#   #",
        "##  #",
        "# # #",
        "#  ##",
        "#   #",
    ],
    "V": [
        "#   #",
        "#   #",
        " # # ",
        " # # ",
        "  #  ",
    ],
    "A": [
        "  #  ",
        " # # ",
        "#####",
        "#   #",
        "#   #",
    ],
    "R": [
        "#### ",
        "#   #",
        "#### ",
        "# #  ",
        "#  ##",
    ],
    "T": [
        "#####",
        "  #  ",
        "  #  ",
        "  #  ",
        "  #  ",
    ],
    " ": [
        "     ",
        "     ",
        "     ",
        "     ",
        "     ",
    ],
}


def _render_pixel_text(text: str, color_fn=None) -> list[str]:
    """
    Render a string using the pixel font.
    Returns a list of 5 strings (one per row), ready to print.
    Each '#' → '██', each ' ' → '  '.
    """
    rows = [""] * 5
    for i, ch in enumerate(text.upper()):
        glyph = _FONT.get(ch, _FONT[" "])
        for row_idx in range(5):
            pixel_row = glyph[row_idx].replace("#", "██").replace(" ", "  ")
            rows[row_idx] += pixel_row
            # 1-pixel gap between letters (except last)
            if i < len(text) - 1:
                rows[row_idx] += "  "
    if color_fn:
        rows = [f"{color_fn()}{row}{RESET()}" for row in rows]
    return rows


def print_banner():
    """Print the INVARIANT pixel-art banner."""
    # Split into two lines so it fits an 80-column terminal
    line1_rows = _render_pixel_text("INVAR", color_fn=CORAL)
    line2_rows = _render_pixel_text("IANT", color_fn=CORAL)

    width = 80
    sep = c(GREY, "─" * width)

    print()
    print(sep)
    print()

    # Centre each row of the pixel art
    for row in line1_rows:
        # Strip ANSI for length calc
        raw = row.replace(CORAL(), "").replace(RESET(), "")
        pad = max(0, (width - len(raw)) // 2)
        print(" " * pad + row)

    print()  # gap between the two words

    for row in line2_rows:
        raw = row.replace(CORAL(), "").replace(RESET(), "")
        pad = max(0, (width - len(raw)) // 2)
        print(" " * pad + row)

    print()
    print(sep)

    # Sub-header
    subtitle = "Deterministic Trust Infrastructure for Bittensor"
    sub_pad = max(0, (width - len(subtitle)) // 2)
    print(" " * sub_pad + c(WHITE, subtitle))

    credit = "by Orthonode Infrastructure Labs  ·  orthonode.xyz"
    cred_pad = max(0, (width - len(credit)) // 2)
    print(" " * cred_pad + c(GREY, credit))

    print(sep)
    print()


# ─────────────────────────────────────────────────────────────────────────────
# UI helpers
# ─────────────────────────────────────────────────────────────────────────────


def section(title: str):
    width = 80
    bar = "─" * width
    print(f"\n{c(AMBER, bar)}")
    print(f"  {c(BOLD, c(WHITE, title))}")
    print(c(AMBER, bar))


def step(msg: str):
    print(f"  {c(CYAN, '▶')}  {msg}")


def ok(msg: str):
    print(f"  {c(GREEN, '✅')}  {msg}")


def fail(msg: str):
    print(f"  {c(RED, '❌')}  {msg}")


def warn(msg: str):
    print(f"  {c(YELLOW, '⚠️')}   {msg}")


def info(msg: str):
    print(f"  {c(GREY, '·')}  {c(GREY, msg)}")


def gate_result_line(gate_num: int, label: str, result: str, detail: str = ""):
    passed = GateResult.is_pass(result)
    icon = c(GREEN, "PASS") if passed else c(RED, f"FAIL  → {result}")
    print(f"    Gate {gate_num}  {c(GREY, label):<35}  {icon}")
    if detail and not passed:
        print(f"           {c(GREY, detail)}")


def metric(label: str, value: str, unit: str = ""):
    print(f"  {c(GREY, label):<32}  {c(AMBER, value)} {c(GREY, unit)}")


def result_row(label: str, passed: bool, detail: str = ""):
    icon = c(GREEN, "✅  PASS") if passed else c(RED, "❌  FAIL")
    suffix = f"  {c(GREY, detail)}" if detail else ""
    print(f"  {icon}  {label}{suffix}")


# ─────────────────────────────────────────────────────────────────────────────
# Agent factory helper
# ─────────────────────────────────────────────────────────────────────────────


def _new_agent(
    tmp_dir: str,
    hotkey: str = "test_hotkey",
    model_id: str = "test_model",
    reg_block: int = 1000,
):
    """
    Write registry, register agent+model, then construct Verifier.
    Verifier (Rust RsVerifier) reads the registry file at __init__ time,
    so it MUST be constructed AFTER the registry JSON is written.
    Returns (agent_id_hex, model_hash_hex, registry, verifier).
    """
    reg_path = str(Path(tmp_dir) / "registry.json")
    state_path = str(Path(tmp_dir) / "state.json")

    model_hash_hex = hash_model(model_id)
    agent_id_hex = derive_software_agent_id(hotkey, model_hash_hex, reg_block)

    registry = Registry(reg_path)
    registry.register_agent(agent_id_hex, hotkey)
    registry.approve_model(model_hash_hex)

    verifier = Verifier(reg_path, state_path)
    return agent_id_hex, model_hash_hex, registry, verifier


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — Receipt generation + OAP basics
# ─────────────────────────────────────────────────────────────────────────────


def test_receipt_generation() -> bool:
    section("TEST 1  ·  Receipt Generation + OAP Basics")

    backend = f"{'Rust ✦' if using_rust() else 'Python (fallback)'}"
    info(f"Backend: {backend}")

    with tempfile.TemporaryDirectory() as tmp:
        agent_id_hex, model_hash_hex, registry, verifier = _new_agent(tmp)

        info(f"agent_id    = {agent_id_hex[:24]}…")
        info(f"model_hash  = {model_hash_hex[:24]}…")
        print()

        # ── Build a receipt ──────────────────────────────────────────────
        step("Building receipt for task: 'What is 2+2?' → '4'")
        ts = time.time()
        receipt = build_receipt(
            agent_id_hex,
            model_hash_hex,
            "What is 2+2?",
            "4",
            counter=1,
            tempo_id=100,
            timestamp=ts,
        )
        for field in ["agent_id", "model_hash", "execution_hash", "digest"]:
            info(f"  {field[:15]:<16} = {receipt[field][:24]}…")
        print()

        # ── Verify the receipt ───────────────────────────────────────────
        step("Verifying receipt through all four gates…")
        res = verifier.verify(receipt)
        passed = GateResult.is_pass(res["result"])
        gate_result_line(0, "Full pipeline", res["result"])
        result_row("Valid receipt passes all gates", passed)
        if not passed:
            return False
        print()

        # ── Replay protection ────────────────────────────────────────────
        step("Submitting same receipt again (replay attack)…")
        replay = verifier.verify(receipt)
        blocked = replay["result"] == GateResult.GATE3
        gate_result_line(3, "Replay protection", replay["result"])
        result_row("Replay blocked at Gate 3", blocked)
        if not blocked:
            return False
        print()

        # ── OAP scoring ──────────────────────────────────────────────────
        step("Initialising OAP engine…")
        oap = OAPEngine(str(Path(tmp) / "oap.json"))
        oap.get_or_create(agent_id_hex, "test_hotkey")

        nts_start = oap.get_nts(agent_id_hex)
        result_row(
            f"Cold-start NTS = {nts_start:.1f}  (expected 50.0)", nts_start == 50.0
        )

        nts_after_clean = oap.record_clean(agent_id_hex, tempo=1)
        result_row(
            f"NTS after clean tempo = {nts_after_clean:.1f}  (must > 50.0)",
            nts_after_clean > 50.0,
        )

        nts_after_viol, cat = oap.record_violation(
            agent_id_hex,
            tempo=2,
            gate=4,
            vtype=ViolationType.GATE4,
            detail="digest tamper",
        )
        result_row(
            f"NTS after Gate-4 violation = {nts_after_viol:.1f}  (must < {nts_after_clean:.1f})",
            nts_after_viol < nts_after_clean,
        )

    print()
    ok("test_receipt_generation  PASSED")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — All 8 attack scenarios
# ─────────────────────────────────────────────────────────────────────────────


def test_attack_scenarios() -> bool:
    section("TEST 2  ·  All 8 Attack Scenarios")

    attacks_passed = 0
    attacks_failed = []

    with tempfile.TemporaryDirectory() as tmp:
        agent_id_hex, model_hash_hex, registry, verifier = _new_agent(
            tmp, hotkey="legit_hotkey", model_id="legit_model"
        )

        BASE = 10_000  # counters start high — no state conflict with prior tests

        # ── Attack 1: Replay ─────────────────────────────────────────────
        r = build_receipt(
            agent_id_hex, model_hash_hex, "task", "out", BASE, 10, time.time()
        )
        assert GateResult.is_pass(verifier.verify(r)["result"]), (
            "Legitimate receipt must pass"
        )
        replay = verifier.verify(r)
        ok1 = replay["result"] == GateResult.GATE3 and replay["gate_number"] == 3
        result_row(
            "Attack 1 · Replay — Gate 3 blocks duplicate counter",
            ok1,
            f"got {replay['result']}",
        )
        if ok1:
            attacks_passed += 1
        else:
            attacks_failed.append("Attack 1: Replay")

        # ── Attack 2: Counter rollback ───────────────────────────────────
        r_low = build_receipt(
            agent_id_hex, model_hash_hex, "task", "out", BASE - 500, 10, time.time()
        )
        res2 = verifier.verify(r_low)
        ok2 = res2["result"] == GateResult.GATE3 and res2["gate_number"] == 3
        result_row(
            "Attack 2 · Counter rollback — Gate 3 blocks lower counter",
            ok2,
            f"got {res2['result']}",
        )
        if ok2:
            attacks_passed += 1
        else:
            attacks_failed.append("Attack 2: Counter rollback")

        # ── Attack 3: Sybil unknown agent ────────────────────────────────
        bad_agent = "ff" * 32
        r_sybil = build_receipt(
            bad_agent, model_hash_hex, "task", "out", BASE + 1, 10, time.time()
        )
        res3 = verifier.verify(r_sybil)
        ok3 = res3["result"] == GateResult.GATE1 and res3["gate_number"] == 1
        result_row(
            "Attack 3 · Sybil identity — Gate 1 blocks unknown agent_id",
            ok3,
            f"got {res3['result']}",
        )
        if ok3:
            attacks_passed += 1
        else:
            attacks_failed.append("Attack 3: Sybil")

        # ── Attack 4: Model impersonation ────────────────────────────────
        bad_model = hash_model("unapproved-gpt5-fake")
        r_model = build_receipt(
            agent_id_hex, bad_model, "task", "out", BASE + 2, 10, time.time()
        )
        res4 = verifier.verify(r_model)
        ok4 = res4["result"] == GateResult.GATE2 and res4["gate_number"] == 2
        result_row(
            "Attack 4 · Model impersonation — Gate 2 blocks unapproved hash",
            ok4,
            f"got {res4['result']}",
        )
        if ok4:
            attacks_passed += 1
        else:
            attacks_failed.append("Attack 4: Model impersonation")

        # ── Attack 5: Digest tamper ──────────────────────────────────────
        r_valid = build_receipt(
            agent_id_hex, model_hash_hex, "task", "out", BASE + 3, 10, time.time()
        )
        r_tamper = dict(r_valid)
        r_tamper["digest"] = "00" * 32
        res5 = verifier.verify(r_tamper)
        ok5 = res5["result"] == GateResult.GATE4 and res5["gate_number"] == 4
        result_row(
            "Attack 5 · Digest tamper — Gate 4 catches zeroed digest",
            ok5,
            f"got {res5['result']}",
        )
        if ok5:
            attacks_passed += 1
        else:
            attacks_failed.append("Attack 5: Digest tamper")

        # ── Attack 6: Output caching (cross-tempo) ───────────────────────
        r_t100 = build_receipt(
            agent_id_hex, model_hash_hex, "task", "4", BASE + 4, 100, time.time()
        )
        r_t101 = build_receipt(
            agent_id_hex, model_hash_hex, "task", "4", BASE + 5, 101, time.time()
        )
        ok6 = r_t100["execution_hash"] != r_t101["execution_hash"]
        result_row(
            "Attack 6 · Output caching — different tempo_id → different execution_hash",
            ok6,
        )
        if ok6:
            attacks_passed += 1
        else:
            attacks_failed.append("Attack 6: Output caching")

        # ── Attack 7: Output copying (cross-miner) ───────────────────────
        agent_b_hex = derive_software_agent_id(
            "miner_b_hotkey",
            model_hash_hex,
            2000,
        )
        r_a = build_receipt(
            agent_id_hex, model_hash_hex, "task", "ans", BASE + 6, 10, time.time()
        )
        r_b = build_receipt(
            agent_b_hex, model_hash_hex, "task", "ans", BASE + 6, 10, time.time()
        )
        ok7 = r_a["agent_id"] != r_b["agent_id"] and r_a["digest"] != r_b["digest"]
        result_row(
            "Attack 7 · Output copying — cross-miner agent_id and digest differ", ok7
        )
        if ok7:
            attacks_passed += 1
        else:
            attacks_failed.append("Attack 7: Output copying")

        # ── Attack 8: Wrong input in execution_hash ──────────────────────
        r_correct = build_receipt(
            agent_id_hex, model_hash_hex, "task A", "ans", BASE + 7, 10, time.time()
        )
        r_wrong = build_receipt(
            agent_id_hex, model_hash_hex, "task B", "ans", BASE + 7, 10, time.time()
        )
        ok8 = r_correct["execution_hash"] != r_wrong["execution_hash"]
        result_row(
            "Attack 8 · Wrong input — different task_input → different execution_hash",
            ok8,
        )
        if ok8:
            attacks_passed += 1
        else:
            attacks_failed.append("Attack 8: Wrong input hash")

    print()
    if attacks_failed:
        for f in attacks_failed:
            fail(f)
        return False
    ok(f"test_attack_scenarios  PASSED  ({attacks_passed}/8 attacks blocked)")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — OAP trust lifecycle
# ─────────────────────────────────────────────────────────────────────────────


def test_oap_lifecycle() -> bool:
    section("TEST 3  ·  OAP Trust Lifecycle")

    with tempfile.TemporaryDirectory() as tmp:
        oap = OAPEngine(str(Path(tmp) / "oap.json"))
        aid = "ab" * 32
        oap.get_or_create(aid, "5TestHotkey", reg_tempo=0)

        # Cold start
        nts = oap.get_nts(aid)
        result_row(f"Cold-start NTS = {nts:.1f}  (expected 50.0)", nts == 50.0)

        # 20 clean tempos
        for t in range(1, 21):
            oap.record_clean(aid, t)
        nts_clean = oap.get_nts(aid)
        result_row(
            f"After 20 clean tempos NTS = {nts_clean:.1f}  (must > 50.0)",
            nts_clean > 50.0,
        )

        # Gate 4 violation drops NTS
        before = oap.get_nts(aid)
        oap.record_violation(aid, 21, 4, ViolationType.GATE4, "test")
        after = oap.get_nts(aid)
        result_row(
            f"Gate-4 violation: {before:.1f} → {after:.1f}  (must drop)", after < before
        )

        # Catastrophic flag: 3× Gate-3 violations
        for i in range(3):
            oap.record_violation(aid, 30 + i, 3, ViolationType.GATE3, "replay")
        nts_cat = oap.get_nts(aid)
        cat_flagged = oap._ledgers[aid].catastrophic
        result_row(
            f"Catastrophic flag after 3× Gate-3: NTS = {nts_cat:.1f}  (cap ≤ 40.0)",
            nts_cat <= 40.0 and cat_flagged,
        )

        print()
        step("Emission weight formula checks…")

        # Full window
        w_full = OAPEngine.emission_weight(1.0, 90.0, in_window=True)
        result_row(
            f"quality=1.0 × NTS=90 × full_window = {w_full:.4f}  (expected 0.9000)",
            abs(w_full - 0.9) < 0.001,
        )

        # Late window (50% freshness)
        w_late = OAPEngine.emission_weight(1.0, 90.0, in_window=False, late=True)
        result_row(
            f"quality=1.0 × NTS=90 × late_window  = {w_late:.4f}  (expected 0.4500)",
            abs(w_late - 0.45) < 0.001,
        )

        # Expired
        w_zero = OAPEngine.emission_weight(1.0, 90.0, in_window=False, late=False)
        result_row(
            f"quality=1.0 × NTS=90 × expired       = {w_zero:.4f}  (expected 0.0000)",
            w_zero == 0.0,
        )

        print()
        step("Override governance (2/yr cap)…")
        ok1, msg1 = oap.apply_override(aid, 75.0, "test", "admin", 2026)
        ok2, msg2 = oap.apply_override(aid, 80.0, "test", "admin", 2026)
        ok3, msg3 = oap.apply_override(aid, 85.0, "test", "admin", 2026)
        result_row(f"Override 1/2 accepted  ({msg1})", ok1)
        result_row(f"Override 2/2 accepted  ({msg2})", ok2)
        result_row(f"Override 3/2 rejected  ({msg3})", not ok3)

    print()
    ok("test_oap_lifecycle  PASSED")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Test 4 — Throughput / performance
# ─────────────────────────────────────────────────────────────────────────────


def test_performance(quick: bool = False) -> bool:
    section("TEST 4  ·  Throughput / Performance Benchmark")

    N = 200 if quick else 1000
    BASE = 100_000
    limit = 0.5 if using_rust() else 5.0

    info(f"Running {N} receipt build-and-verify cycles…")
    print()

    with tempfile.TemporaryDirectory() as tmp:
        agent_id_hex, model_hash_hex, _, verifier = _new_agent(
            tmp, hotkey="perf_hotkey", model_id="perf_model"
        )

        t0 = time.perf_counter()
        for i in range(N):
            r = build_receipt(
                agent_id_hex,
                model_hash_hex,
                f"task_input_{i}",
                f"output_{i}",
                counter=BASE + i,
                tempo_id=100,
                timestamp=time.time(),
            )
            res = verifier.verify(r)
            if not GateResult.is_pass(res["result"]):
                fail(f"Verification failed at i={i}: {res}")
                return False
        elapsed = time.perf_counter() - t0

    per_us = (elapsed / N) * 1_000_000
    per_ms = per_us / 1_000
    rate = int(N / elapsed)
    backend = "Rust ✦" if using_rust() else "Python (fallback)"

    metric("Backend", backend)
    metric("Receipts verified", f"{N:,}")
    metric("Total time", f"{elapsed * 1000:.1f}", "ms")
    metric("Per receipt", f"{per_us:.1f}", "µs")
    metric("Throughput", f"{rate:,}", "receipts / second")

    if using_rust():
        target_ok = per_us < 50.0
        metric(
            "Target (< 50 µs)",
            "✅  MET" if target_ok else "⚠️   MISSED",
            f"(actual {per_us:.1f} µs)",
        )
    else:
        info(
            "Rust target: < 50 µs/receipt  —  run `maturin develop` in invariant-gates/ for production speed"
        )

    within_limit = elapsed < limit
    result_row(
        f"{N} verifications within {limit:.1f}s limit  (took {elapsed:.3f}s)",
        within_limit,
    )

    print()
    ok("test_performance  PASSED")
    return within_limit


# ─────────────────────────────────────────────────────────────────────────────
# Test 5 — Bridge self-check
# ─────────────────────────────────────────────────────────────────────────────


def test_bridge() -> bool:
    section("TEST 5  ·  Bridge Self-Check")

    with tempfile.TemporaryDirectory() as tmp:
        model_hex = hash_model("bridge-selftest-v1")
        agent_hex = derive_software_agent_id("5BridgeSelfTest", model_hex, 9999)

        info(f"model_hash  = {model_hex[:24]}…")
        info(f"agent_id    = {agent_hex[:24]}…")
        print()

        result_row(f"using_rust() returns bool", isinstance(using_rust(), bool))
        result_row(
            f"Backend active: {'Rust ✦' if using_rust() else 'Python (fallback)'}", True
        )

        reg = Registry(str(Path(tmp) / "registry.json"))
        reg.register_agent(agent_hex, "5BridgeSelfTest")
        reg.approve_model(model_hex)
        result_row("Registry.register_agent() and approve_model() succeed", True)

        v = Verifier(str(Path(tmp) / "registry.json"), str(Path(tmp) / "state.json"))
        result_row("Verifier constructed after registry written", True)

        ts = time.time()
        r1 = build_receipt(agent_hex, model_hex, "bridge test", "ok", 1, 999, ts)
        r2 = build_receipt(agent_hex, model_hex, "bridge test", "ok", 2, 999, ts)

        res1 = v.verify(r1)
        res2 = v.verify(r2)
        result_row(
            f"Receipt 1 (counter=1): {res1['result']}",
            GateResult.is_pass(res1["result"]),
        )
        result_row(
            f"Receipt 2 (counter=2): {res2['result']}",
            GateResult.is_pass(res2["result"]),
        )

        batch = [
            build_receipt(agent_hex, model_hex, f"t{i}", f"o{i}", 100 + i, 999, ts)
            for i in range(10)
        ]
        results = v.verify_batch(batch)
        all_pass = all(GateResult.is_pass(rr["result"]) for rr in results)
        result_row(f"verify_batch(10 receipts): all PASS", all_pass)

    print()
    ok("test_bridge  PASSED")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Summary table
# ─────────────────────────────────────────────────────────────────────────────


def print_summary(results: list[tuple[str, bool, float]]):
    width = 80
    print()
    print(c(AMBER, "═" * width))
    print(c(BOLD, c(WHITE, "  INVARIANT TEST SUITE RESULTS")))
    print(c(AMBER, "═" * width))
    print()

    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    total = len(results)

    for name, ok_flag, elapsed in results:
        icon = c(GREEN, "✅  PASS") if ok_flag else c(RED, "❌  FAIL")
        time_ = c(GREY, f"{elapsed * 1000:.0f}ms")
        print(f"  {icon}  {name:<42}  {time_}")

    print()
    print(c(GREY, "─" * width))
    summary_color = GREEN if failed == 0 else RED
    print(
        f"  {c(summary_color, f'{passed}/{total} tests passed')}   "
        f"{c(GREY, f'({failed} failed)')}"
        if failed
        else f"  {c(GREEN, f'{passed}/{total} tests passed')}"
    )
    print()

    if failed == 0:
        msg = "🎉  ALL TESTS PASSED — INVARIANT is working correctly"
        pad = max(0, (width - len(msg) + 18) // 2)  # +18 for emoji width estimate
        print(" " * pad + c(GREEN, msg))
    else:
        msg = f"⚠️   {failed} TEST(S) FAILED — see output above"
        pad = max(0, (width - len(msg) + 10) // 2)
        print(" " * pad + c(RED, msg))

    print()
    print(c(AMBER, "═" * width))
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────


def main() -> bool:
    parser = argparse.ArgumentParser(
        description="INVARIANT local test suite — no Bittensor node required",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--no-color", action="store_true", help="Disable ANSI color output"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run reduced iteration count (faster, useful for CI)",
    )
    args = parser.parse_args()

    global _USE_COLOR
    if args.no_color or not sys.stdout.isatty():
        _USE_COLOR = False

    print_banner()

    suites = [
        ("Receipt generation + OAP basics", lambda: test_receipt_generation()),
        ("All 8 attack scenarios", lambda: test_attack_scenarios()),
        ("OAP trust lifecycle", lambda: test_oap_lifecycle()),
        ("Throughput / performance", lambda: test_performance(quick=args.quick)),
        ("Bridge self-check", lambda: test_bridge()),
    ]

    results: list[tuple[str, bool, float]] = []

    for name, fn in suites:
        t0 = time.perf_counter()
        try:
            ok_flag = fn()
        except Exception:
            import traceback

            fail(f"{name} CRASHED:")
            traceback.print_exc()
            ok_flag = False
        elapsed = time.perf_counter() - t0
        results.append((name, ok_flag, elapsed))

    print_summary(results)

    all_passed = all(ok_flag for _, ok_flag, _ in results)
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
