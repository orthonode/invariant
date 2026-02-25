#!/usr/bin/env python3
"""
run_tests.py — INVARIANT Master Test Controller
================================================
One-command end-to-end test runner.

Usage:
    python run_tests.py              # full interactive suite
    python run_tests.py --quick      # unit tests only  (no node needed)
    python run_tests.py --e2e        # e2e only         (node must be running)
    python run_tests.py --all        # everything, no prompts
"""

from __future__ import annotations
import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent

# ── ANSI palette ──────────────────────────────────────────────────────────────
OR = "\033[38;5;208m"   # orange
RE = "\033[31m"          # red
GR = "\033[32m"          # green
YE = "\033[33m"          # yellow
CY = "\033[36m"          # cyan
WH = "\033[97m"          # bright white
BO = "\033[1m"           # bold
DI = "\033[2m"           # dim
RS = "\033[0m"           # reset

# ── Pixel font — 5 rows each ──────────────────────────────────────────────────
_F: dict[str, list[str]] = {
    "I": ["███",  " █ ",  " █ ",  " █ ",  "███"],
    "N": ["█  █", "██ █", "█ ██", "█  █", "█  █"],
    "V": ["█   █", "█   █", " █ █ ", "  █  ", "  █  "],
    "A": [" ██ ", "█  █", "████", "█  █", "█  █"],
    "R": ["███ ", "█  █", "███ ", "█ █ ", "█  █"],
    "T": ["█████", "  █  ", "  █  ", "  █  ", "  █  "],
    " ": ["   ", "   ", "   ", "   ", "   "],
}


def _banner() -> None:
    word = "INVARIANT"
    letters = [_F.get(c, _F[" "]) for c in word]
    rows = ["  ".join(l[r] for l in letters) for r in range(5)]
    w = max(len(r) for r in rows)
    top = "╔" + "═" * (w + 4) + "╗"
    bot = "╚" + "═" * (w + 4) + "╝"
    print()
    print(OR + BO + top + RS)
    for row in rows:
        print(OR + BO + "║  " + row.ljust(w) + "  ║" + RS)
    print(OR + BO + bot + RS)
    sub = "  Three-Layer Trust Stack  ·  SHA · Receipt · OAP  ·  Bittensor Subnet"
    print(DI + CY + sub.center(w + 6) + RS)
    print()


# ── Result tracker ────────────────────────────────────────────────────────────
_results: list[tuple[str, bool | None]] = []


def _step(label: str, ok: bool | None) -> None:
    _results.append((label, ok))
    if ok is True:
        icon = GR + "✅ PASS" + RS
    elif ok is False:
        icon = RE + "❌ FAIL" + RS
    else:
        icon = YE + "⏭ SKIP" + RS
    print(f"  {icon}  {label}")


def run_cmd(
    label: str,
    cmd: list[str],
    *,
    cwd: Path = ROOT,
    timeout: int = 120,
    env: dict | None = None,
) -> bool:
    print(f"  {CY}▶ {label}{RS}", end="", flush=True)
    t0 = time.time()
    e = os.environ.copy()
    if env:
        e.update(env)
    try:
        r = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=e
        )
        elapsed = time.time() - t0
        ok = r.returncode == 0
        tag = GR + "✅ PASS" + RS if ok else RE + "❌ FAIL" + RS
        print(f"\r  {tag}  {label}  {DI}({elapsed:.1f}s){RS}")
        if not ok:
            out = (r.stderr or r.stdout or "").strip().splitlines()
            for line in out[-6:]:
                print(f"       {DI}{line}{RS}")
        _results.append((label, ok))
        return ok
    except subprocess.TimeoutExpired:
        print(f"\r  {YE}⏱ TIMEOUT{RS}  {label}")
        _results.append((label, False))
        return False
    except Exception as exc:
        print(f"\r  {RE}💥 ERROR{RS}  {label}: {exc}")
        _results.append((label, False))
        return False


# ── LAN IP detection ──────────────────────────────────────────────────────────
def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith("127."):
            return ip
    except Exception:
        pass
    # Fallback: parse ip addr
    try:
        out = subprocess.check_output(["ip", "addr", "show"], text=True)
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("inet ") and "127." not in line and "172." not in line:
                return line.split()[1].split("/")[0]
    except Exception:
        pass
    return "192.168.1.1"


# ── Terminal launcher ─────────────────────────────────────────────────────────
def _open_terminal(title: str, cmd: str) -> bool:
    """Open a new terminal window/tab running `cmd`. Returns True if succeeded."""
    venv_cmd = f"source {ROOT}/venv/bin/activate && cd {ROOT} && {cmd}"
    full = f"bash -c '{venv_cmd}; echo; echo [Process ended — press Enter]; read'"

    # 1. tmux new-window (works if already inside tmux)
    if os.environ.get("TMUX") and shutil.which("tmux"):
        subprocess.run(["tmux", "new-window", "-n", title, f"bash -c '{venv_cmd}'"])
        return True

    # 2. gnome-terminal
    if shutil.which("gnome-terminal"):
        subprocess.Popen(
            ["gnome-terminal", f"--title={title}", "--", "bash", "-c", full]
        )
        return True

    # 3. xterm
    if shutil.which("xterm"):
        subprocess.Popen(
            ["xterm", "-title", title, "-fa", "Monospace", "-fs", "10", "-e", full]
        )
        return True

    # 4. konsole (KDE)
    if shutil.which("konsole"):
        subprocess.Popen(["konsole", "--title", title, "-e", "bash", "-c", full])
        return True

    return False


# ── Phase 1: Quick tests (no node needed) ────────────────────────────────────
def phase_quick() -> bool:
    print(OR + BO + "\n── Phase 1: Unit & Integration Tests ──────────────────" + RS)

    venv_py = str(ROOT / "venv" / "bin" / "python")
    py = venv_py if Path(venv_py).exists() else sys.executable

    ok1 = run_cmd(
        "pytest — 21 gate/OAP tests",
        [py, "-m", "pytest", str(ROOT / "invariant" / "invariant" / "tests"), "-v", "--tb=short", "-q"],
    )
    ok2 = run_cmd(
        "Local harness — 5 attack scenarios",
        [py, str(ROOT / "scripts" / "test_locally.py")],
        timeout=30,
    )
    ok3 = run_cmd(
        "Bridge self-test — Rust backend active",
        [py, str(ROOT / "invariant" / "invariant" / "phase1_core" / "invariant_gates_bridge.py")],
        timeout=15,
    )
    return ok1 and ok2 and ok3


# ── Rust checks (optional) ────────────────────────────────────────────────────
def phase_rust() -> bool:
    print(OR + BO + "\n── Phase 1b: Rust Checks ───────────────────────────────" + RS)
    rust_dir = ROOT / "invariant" / "invariant-gates"
    ok1 = run_cmd("cargo fmt --check", ["cargo", "fmt", "--check"], cwd=rust_dir, timeout=60)
    ok2 = run_cmd(
        "cargo clippy — zero warnings",
        ["cargo", "clippy", "--", "-D", "warnings"],
        cwd=rust_dir, timeout=120,
    )
    ok3 = run_cmd("cargo test", ["cargo", "test"], cwd=rust_dir, timeout=120)
    return ok1 and ok2 and ok3


# ── Phase 2: End-to-end ───────────────────────────────────────────────────────
def _node_running() -> bool:
    try:
        r = subprocess.run(
            ["curl", "-s", "--connect-timeout", "2",
             "-H", "Content-Type: application/json",
             "-d", '{"id":1,"jsonrpc":"2.0","method":"system_health","params":[]}',
             "http://127.0.0.1:9944"],
            capture_output=True, text=True, timeout=5,
        )
        return '"peers"' in r.stdout
    except Exception:
        return False


def _miner_axon_up(ip: str, port: int = 8091, timeout: int = 3) -> bool:
    try:
        r = subprocess.run(
            ["curl", "-s", f"--connect-timeout", str(timeout),
             f"http://{ip}:{port}/"],
            capture_output=True, text=True, timeout=timeout + 2,
        )
        return "InvariantTask" in r.stdout
    except Exception:
        return False


def phase_e2e(lan_ip: str) -> bool:
    print(OR + BO + "\n── Phase 2: End-to-End on Local Chain ──────────────────" + RS)

    # ── Node check ────────────────────────────────────────────────────────────
    if _node_running():
        _step("Local subtensor node reachable", True)
    else:
        _step("Local subtensor node reachable", False)
        print(f"  {YE}Start the node first:{RS}")
        print(f"  {DI}  ./start_local.sh{RS}")
        print(f"  {DI}  (or: {ROOT}/subtensor/target/release/node-subtensor --dev --one --validator ...){RS}")
        return False

    # ── Miner ─────────────────────────────────────────────────────────────────
    miner_log = Path("/tmp/invariant_miner.log")
    miner_cmd = (
        f"python {ROOT}/miner.py "
        f"--wallet.name miner1 --wallet.hotkey default "
        f"--netuid 1 --subtensor.network local "
        f"--axon.port 8091 --logging.debug"
        # LAN IP is auto-detected inside miner.py via _ensure_external_ip()
    )

    # Check miner on LAN IP or localhost fallback
    miner_up = _miner_axon_up(lan_ip) or _miner_axon_up("127.0.0.1")
    if miner_up:
        _step(f"Miner axon reachable ({lan_ip}:8091)", True)
    else:
        print(f"  {CY}▶ Starting miner (LAN IP auto-detected)...{RS}")
        launched = _open_terminal("INVARIANT Miner", miner_cmd)
        if not launched:
            # Background fallback
            with open(miner_log, "w") as f:
                subprocess.Popen(
                    f"source {ROOT}/venv/bin/activate && {miner_cmd}",
                    shell=True, stdout=f, stderr=f, cwd=ROOT,
                )
            print(f"  {DI}Miner started in background → {miner_log}{RS}")

        # Wait for axon to come up (max 25s)
        deadline = time.time() + 25
        while time.time() < deadline:
            if _miner_axon_up(lan_ip) or _miner_axon_up("127.0.0.1"):
                break
            print(f"  {DI}  waiting for miner axon...{RS}", end="\r")
            time.sleep(2)
        else:
            print()
        miner_up = _miner_axon_up(lan_ip) or _miner_axon_up("127.0.0.1")
        _step(f"Miner axon reachable ({lan_ip}:8091)", miner_up)
        if not miner_up:
            print(f"  {DI}Check log: {miner_log}{RS}")
            return False

    # ── Validator (one tempo) ─────────────────────────────────────────────────
    print(f"  {CY}▶ Running validator (one tempo — up to 45s)...{RS}")
    val_log = Path("/tmp/invariant_validator.log")
    venv_py = str(ROOT / "venv" / "bin" / "python")
    py = venv_py if Path(venv_py).exists() else sys.executable

    proc = subprocess.Popen(
        [py, str(ROOT / "validator.py"),
         "--wallet.name", "validator1", "--wallet.hotkey", "default",
         "--netuid", "1", "--subtensor.network", "local", "--logging.debug"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        raw_out, _ = proc.communicate(timeout=45)
    except subprocess.TimeoutExpired:
        proc.kill()
        raw_out, _ = proc.communicate()

    clean = "\n".join(
        line for line in raw_out.split("\n")
        if not any(skip in line for skip in ["loggingmachine", "Enabling debug", "DEBUG"])
    )
    val_log.write_text(clean)

    # Parse results — use raw_out so DEBUG lines (status=200) are also checked
    got_response   = "status=200"        in raw_out
    auto_reg       = "Auto-registered"   in raw_out
    got_quality    = "quality=1.00"      in raw_out
    weights_set    = "Weights set"       in raw_out
    gate_fail      = "gate fail"         in raw_out.lower()

    print()
    print(f"  {DI}Validator output:{RS}")
    for line in clean.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        col = GR if any(k in line for k in ["SUCCESS", "quality=", "Weights"]) \
              else RE if any(k in line for k in ["ERROR", "gate fail"]) \
              else YE if "WARNING" in line \
              else DI
        print(f"    {col}{line}{RS}")
    print()

    _step("Dendrite reached miner (status=200)",        got_response)
    if auto_reg:
        _step("Agent auto-registered (first-run Gate 1)", True)
    _step("Output quality = 1.00 (correct computation)", got_quality)
    _step("All four gates passed",                       not gate_fail and got_quality)
    _step("Weights committed to chain",                  weights_set)

    return got_quality and not gate_fail and weights_set


# ── Summary ───────────────────────────────────────────────────────────────────
def _summary() -> None:
    print(OR + BO + "\n── Test Summary ────────────────────────────────────────" + RS)
    passed = sum(1 for _, ok in _results if ok is True)
    failed = sum(1 for _, ok in _results if ok is False)
    skipped = sum(1 for _, ok in _results if ok is None)
    total = passed + failed

    for label, ok in _results:
        icon = GR + "✅" + RS if ok is True else RE + "❌" + RS if ok is False else YE + "⏭" + RS
        print(f"  {icon}  {label}")

    print()
    pct = int(100 * passed / total) if total else 0
    col = GR if failed == 0 else YE if pct >= 70 else RE
    print(f"  {col}{BO}{passed}/{total} passed ({pct}%){RS}", end="")
    if skipped:
        print(f"  {DI}({skipped} skipped){RS}", end="")
    print()

    if failed == 0:
        print(f"\n  {OR}{BO}✦ INVARIANT MVP — ALL SYSTEMS GO ✦{RS}\n")
    else:
        print(f"\n  {RE}{BO}Some tests failed. See output above.{RS}\n")


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description="INVARIANT Master Test Controller")
    ap.add_argument("--quick",  action="store_true", help="Unit tests only (no node)")
    ap.add_argument("--e2e",    action="store_true", help="E2E only (node must run)")
    ap.add_argument("--rust",   action="store_true", help="Also run cargo checks")
    ap.add_argument("--all",    action="store_true", help="Everything, no prompts")
    ap.add_argument("--lan-ip", default=None,        help="Override LAN IP for miner axon")
    args = ap.parse_args()

    _banner()

    lan_ip = args.lan_ip or _lan_ip()
    print(f"  {DI}Detected LAN IP: {WH}{lan_ip}{RS}  {DI}(override with --lan-ip X.X.X.X){RS}\n")

    run_quick = args.quick or args.all or not (args.e2e)
    run_e2e   = args.e2e   or args.all
    run_rust  = args.rust  or args.all

    if run_quick:
        quick_ok = phase_quick()
        if run_rust:
            phase_rust()

    if not (args.quick or args.e2e or args.all):
        # Interactive: ask about e2e
        print(f"\n  {CY}Run end-to-end test on local chain? (requires running node + wallets){RS}")
        ans = input(f"  {BO}[y/N]{RS} → ").strip().lower()
        run_e2e = ans == "y"

    if run_e2e:
        phase_e2e(lan_ip)

    _summary()


if __name__ == "__main__":
    main()
