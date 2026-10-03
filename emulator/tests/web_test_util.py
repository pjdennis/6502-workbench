"""Helpers the --web Playwright tests share: tool checks, building
programs with vasm, starting the emulator's web server and reporting.

Each test's run_test(verbose) returns True (pass), False (fail) or
None (skipped); main() runs it and sets the exit status.
"""

import argparse
import re
import shutil
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# firmware/vasm: vasm6502_oldstyle with the firmware include path.
FW_VASM = REPO_ROOT / "firmware" / "vasm"
EMULATOR = REPO_ROOT / "emulator" / "emulator.out"


class Colors:
    RED = "\033[0;31m"; GREEN = "\033[0;32m"; YELLOW = "\033[0;33m"; NC = "\033[0m"
    @classmethod
    def disable(cls): cls.RED = cls.GREEN = cls.YELLOW = cls.NC = ""


def passed(msg): print(f"  {Colors.GREEN}PASS{Colors.NC} {msg}"); return True
def failed(msg): print(f"  {Colors.RED}FAIL{Colors.NC} {msg}"); return False
def skipped(msg): print(f"  {Colors.YELLOW}SKIP{Colors.NC} {msg}"); return None


def missing_tools(name):
    """The SKIP result when vasm or playwright is missing, else None."""
    if shutil.which("vasm6502_oldstyle") is None:
        return f"{name} (vasm6502_oldstyle not on PATH)"
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return (f"{name} (playwright not installed: "
                "pip3 install playwright && playwright install chromium)")
    return None


def out_dir_for(name):
    """A fresh-ish /tmp/<name>/ for the build outputs and screenshots."""
    out_dir = Path("/tmp") / name
    out_dir.mkdir(exist_ok=True)
    for f in out_dir.glob("*.png"):
        f.unlink()
    return out_dir


def run_vasm(src, out_path, log_path):
    r = subprocess.run(
        [str(FW_VASM), "-wdc02", "-wfail", "-Fbin", "-dotdir",
         "-ignore-mult-inc", "-esc", "-o", str(out_path), str(src)],
        capture_output=True, text=True
    )
    log_path.write_text(r.stdout + r.stderr)
    return r.returncode == 0


def build_wendy2c_upload(out_dir, payload_name, stem):
    """The wendy2c boot ROM and firmware/programs/wendy2/<payload_name>
    framed for upload over the serial line: (boot_rom, framed), or None
    if vasm or the framing failed (logs in out_dir)."""
    boot_src    = REPO_ROOT / "firmware" / "boards" / "wendy2" / "upload_and_run_eeprom_wendy2c.s"
    payload_src = REPO_ROOT / "firmware" / "programs" / "wendy2" / payload_name
    boot_rom    = out_dir / "boot.bin"
    payload_bin = out_dir / f"{stem}.bin"
    framed      = out_dir / f"{stem}.framed"

    if not run_vasm(boot_src,    boot_rom,    out_dir / "boot.vasm.log"):     return None
    if not run_vasm(payload_src, payload_bin, out_dir / f"{stem}.vasm.log"):  return None

    framer = REPO_ROOT / "emulator" / "wendy2_upload.py"
    r = subprocess.run(
        ["python3", str(framer), str(payload_bin), "-o", str(framed)],
        capture_output=True, text=True
    )
    if r.returncode != 0: return None
    return boot_rom, framed


@contextmanager
def web_emulator(args):
    """Runs emulator.out <args> --web --web-port 0 and yields the port it
    listens on (None if it never said), stopping it with SIGINT after."""
    proc = subprocess.Popen(
        [str(EMULATOR), *map(str, args), "--web", "--web-port", "0"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    try:
        port = None
        start = time.monotonic()
        while time.monotonic() - start < 3.0 and port is None:
            line = proc.stderr.readline()
            if not line: time.sleep(0.05); continue
            m = re.search(r"http://127\.0\.0\.1:(\d+)/", line)
            if m: port = int(m.group(1))
        yield port
    finally:
        proc.send_signal(signal.SIGINT)
        try: proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait(timeout=2)


def track_last_state(page):
    """Keeps the page's latest state snapshot in window._lastState."""
    page.add_init_script("""
        window._lastState = null;
        const origWS = window.WebSocket;
        window.WebSocket = function(...args) {
            const ws = new origWS(...args);
            ws.addEventListener('message', (e) => {
                if (typeof e.data === 'string') {
                    try {
                        const obj = JSON.parse(e.data);
                        if (obj.lcd) window._lastState = obj;
                    } catch {}
                }
            });
            return ws;
        };
        for (const k in origWS) window.WebSocket[k] = origWS[k];
    """)


def open_page(p, port, setup=None):
    """A headless Chromium page on the server, once it shows "connected".
    setup(page) runs before the page loads, to hook its WebSocket."""
    browser = p.chromium.launch()
    page = browser.new_context(viewport={"width": 900, "height": 700}).new_page()
    if setup: setup(page)
    page.goto(f"http://127.0.0.1:{port}/")
    page.wait_for_function(
        "document.getElementById('status-text')?.textContent.includes('connected')",
        timeout=5000,
    )
    return browser, page


def main(title, run_test):
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    if not sys.stdout.isatty(): Colors.disable()

    print("=" * 60)
    print(title)
    print("=" * 60)
    if EMULATOR.exists():
        result = run_test(verbose=args.verbose)
    else:
        result = failed(f"emulator not built at {EMULATOR}")
    print()
    print("=" * 60)
    if result is None:
        print(f"Results: {Colors.YELLOW}skipped{Colors.NC}")
        sys.exit(0)
    if result:
        print(f"Results: {Colors.GREEN}1 passed{Colors.NC} of 1 test")
        sys.exit(0)
    print(f"Results: {Colors.RED}1 failed{Colors.NC} of 1 test")
    sys.exit(1)
