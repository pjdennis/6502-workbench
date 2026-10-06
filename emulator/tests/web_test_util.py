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
MICHAEL_PROGRAMS = REPO_ROOT / "firmware" / "programs" / "michael"


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


def michael_load_address():
    """PROGRAM_LOAD_ADDRESS from michael's base_config_v2.inc, in hex: where --load puts programs."""
    base_config = REPO_ROOT / "firmware" / "boards" / "michael" / "base_config_v2.inc"
    return re.search(r"^PROGRAM_LOAD_ADDRESS\s*=\s*\$([0-9a-fA-F]+)",
                     base_config.read_text(), re.M).group(1)


@contextmanager
def web_emulator(args, port=0):
    """Runs emulator.out <args> --web --web-port <port> (by default one the
    kernel picks) and yields the port it listens on (None if it never
    said), stopping it with SIGINT after."""
    proc = subprocess.Popen(
        [str(EMULATOR), *map(str, args), "--web", "--web-port", str(port)],
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


# The LCD's lines from the latest snapshot (see track_last_state),
# trailing blanks dropped.
LCD_LINES = """() => {
    const l = window._lastState && window._lastState.lcd;
    if (!l) return null;
    const lines = [];
    for (let r = 0; r < l.rows; r++)
        lines.push(String.fromCharCode(...l.ddram.slice(r * l.cols, (r + 1) * l.cols)).trimEnd());
    return lines;
}"""


def first_line_becomes(page, want, timeout=3000):
    """None once the LCD's first line reads want, else a failure message."""
    try:
        page.wait_for_function(f"(want) => {{ const l = ({LCD_LINES})(); return l && l[0] === want; }}",
                               arg=want, timeout=timeout)
        return None
    except Exception:
        return f"LCD's first line never became {want!r}: {page.evaluate(LCD_LINES)}"


def speed_shown(page, target, timeout=3000):
    """None once the status line shows the emulated clock's measured rate
    against target ("clock 19.43 / 19.44 MHz (100%)"), else a failure
    message."""
    pattern = r"clock (\d+\.\d\d) / (\d+\.\d\d) MHz \((\d+)%\)"
    try:
        page.wait_for_function("(p) => new RegExp(p).test(document.getElementById('status-speed').textContent)",
                               arg=pattern, timeout=timeout)
    except Exception:
        shown = page.evaluate("document.getElementById('status-speed')?.textContent")
        return f"no clock speed readout: {shown!r}"
    text = page.text_content("#status-speed")
    mhz, shown_target, percent = re.search(pattern, text).groups()
    if shown_target != target or float(mhz) <= 0 or int(percent) != round(100 * float(mhz) / float(target)):
        return f"clock speed readout {text!r}; want the measured rate against {target} MHz"
    return None


# Where the page's parts are: {id: [left, top, right, bottom]}
BOXES = """(ids) => Object.fromEntries(ids.map(id => {
    const r = document.getElementById(id).getBoundingClientRect();
    return [id, [r.left, r.top, r.right, r.bottom]];
}))"""

# The LCD's left edge before and after the status text grows, as the
# connection's state and the readouts change it.
LCD_MOVES = """() => {
    const left = () => document.getElementById('lcd-bezel').getBoundingClientRect().left;
    const text = document.getElementById('status-text'), old = text.textContent;
    const before = left();
    text.textContent = 'disconnected, retrying… and a good deal longer';
    const after = left();
    text.textContent = old;
    return [before, after];
}"""


def layout_problems(page, ids):
    """On a 1280 by 900 screen: the board's parts at {id: box} for ids (with
    pins, title and status), and a list of what's wrong with the layout every
    machine shares: the title below the ports, the status bar along the
    bottom, as wide as the board's contents, the LCD staying put while the
    status text changes, and no scrolling."""
    page.set_viewport_size({"width": 1280, "height": 900})
    box = page.evaluate(BOXES, list(dict.fromkeys(ids + ["lcd-bezel", "pins", "title", "status"])))
    pins, title, status = box["pins"], box["title"], box["status"]
    problems = []
    if not (pins[3] <= title[1] and title[3] <= status[1]):
        problems.append("the title isn't between the ports and the status bar")
    if any(b[3] > status[1] for i, b in box.items() if i != "status"):
        problems.append("the status bar isn't below everything else")
    if abs(status[2] - pins[2]) > 2:
        problems.append("the status bar's right edge isn't the ports'")
    before, after = page.evaluate(LCD_MOVES)
    if before != after:
        problems.append(f"the LCD moves from {before} to {after} when the status text grows")
    if page.evaluate("document.documentElement.scrollWidth") > 1280:
        problems.append("the page scrolls sideways at 1280 pixels")
    if page.evaluate("document.documentElement.scrollHeight") > 900:
        problems.append("the page scrolls down at 900 pixels")
    return box, problems


def board_runs_past_stp(page, timeout=10000):
    """None if, once the program's STP stops the CPU, the board runs on (the
    page stays connected, the clock counting) until the reset button starts
    the CPU again; else a failure message. Needs track_last_state."""
    try:
        page.wait_for_function("window._lastState && window._lastState.stp === 1", timeout=timeout)
    except Exception:
        return f"the program never reached its STP: pc ${page.evaluate('window._lastState.pc'):04X}"
    osc = page.evaluate("window._lastState.osc")
    page.wait_for_timeout(1500)
    if page.evaluate("window._lastState.osc") <= osc or page.text_content("#status-text") != "connected":
        return (f"after STP the board stopped: osc {osc} -> {page.evaluate('window._lastState.osc')}, "
                f"{page.text_content('#status-text')!r}")
    page.click("#btn-reset")
    try:
        page.wait_for_function("window._lastState.stp === 0", timeout=5000)
    except Exception:
        return "the reset button didn't start the CPU again after its STP"
    return None


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
