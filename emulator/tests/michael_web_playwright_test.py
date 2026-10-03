#!/usr/bin/env python3
"""End-to-end web UI test for the michael emulator.

Runs firmware/programs/michael/michael_keyboard_new.s (it echoes what
the PS/2 keyboard types after a '>' prompt) on --machine michael --web
and drives the page with headless Chromium:

1. The 20x4 LCD: the snapshot's geometry, the canvas size and the
   prompt on the first line.
2. The VIA pin table shows michael's pin labels.
3. Keys typed on the page reach the program through the PS/2 keyboard:
   shifted text, Backspace, an arrow key (an ESC sequence), Esc, and
   pasted text.
4. The reset button restarts the program, and the keyboard still works.

Then runs hello_michael_led.s and checks the PA2 LED lights on the page
as the program toggles it: while PA2 is low, as on the board, where the
LED is wired from +5V to the pin.

SKIPs cleanly if vasm6502_oldstyle or playwright are missing.
"""

import re

from web_test_util import (REPO_ROOT, failed, main, missing_tools, open_page,
                           out_dir_for, passed, run_vasm, skipped,
                           track_last_state, web_emulator)

PROGRAMS = REPO_ROOT / "firmware" / "programs" / "michael"
BASE_CONFIG = REPO_ROOT / "firmware" / "boards" / "michael" / "base_config_v2.inc"

# The LCD's lines from the latest snapshot, trailing blanks dropped.
LCD_LINES = """() => {
    const l = window._lastState && window._lastState.lcd;
    if (!l) return null;
    const lines = [];
    for (let r = 0; r < l.rows; r++)
        lines.push(String.fromCharCode(...l.ddram.slice(r * l.cols, (r + 1) * l.cols)).trimEnd());
    return lines;
}"""

PASTE = """(text) => {
    const data = new DataTransfer();
    data.setData('text/plain', text);
    document.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true }));
}"""


def load_address():
    return re.search(r"^PROGRAM_LOAD_ADDRESS\s*=\s*\$([0-9a-fA-F]+)",
                     BASE_CONFIG.read_text(), re.M).group(1)


def first_line_becomes(page, want, timeout=3000):
    """None once the LCD's first line reads want, else a failure message."""
    try:
        page.wait_for_function(f"(want) => {{ const l = ({LCD_LINES})(); return l && l[0] === want; }}",
                               arg=want, timeout=timeout)
        return None
    except Exception:
        return f"LCD's first line never became {want!r}: {page.evaluate(LCD_LINES)}"


def check_keyboard_page(page, out_dir, verbose):
    """The keyboard program's checks; None if they pass, else a failure message."""
    problem = first_line_becomes(page, ">", timeout=5000)
    if problem: return problem

    lcd = page.evaluate("window._lastState.lcd")
    size = page.evaluate("[document.getElementById('lcd').width, document.getElementById('lcd').height]")
    if verbose: print(f"  lcd {lcd['rows']}x{lcd['cols']}, canvas {size}")
    # 20 cells of 5 dots at 4 px plus 19 gaps of 6 px and 8 px margins
    # across; 4 rows of 8 dots, 3 gaps and the margins down.
    if (lcd["rows"], lcd["cols"]) != (4, 20) or size != [530, 162]:
        return f"LCD geometry: {lcd['rows']}x{lcd['cols']}, canvas {size}; want 4x20, [530, 162]"

    labels = page.evaluate("""() => ['row-a-lbl', 'row-b-lbl'].map(id =>
        [...document.querySelectorAll('#' + id + ' td')].slice(1, 9).map(td => td.textContent))""")
    if labels != [["E", "RW", "RS", "SOEB", "SOLB", "LED", "A1", "A0"],
                  ["D7", "D6", "D5", "D4", "D3", "D2", "D1", "D0"]]:
        return f"pin labels: {labels}"

    # initialize_michael_ports drives PA2 high: the LED is off.
    led = page.evaluate(LED_STATE)
    if led != ["0", False, 1]:
        return f"LED (snapshot, page, PA2) after the ports are set up: {led}; want it off"

    steps = [
        ("type", "Hi!", ">Hi!"),
        ("press", "Backspace", ">Hi"),
        ("press", "ArrowLeft", ">Hi"),
        ("type", "X", ">HXi"),
        ("press", "Escape", ">"),
        ("paste", "pasted text", ">pasted text"),
    ]
    for action, keys, want in steps:
        if action == "type": page.keyboard.type(keys)
        elif action == "press": page.keyboard.press(keys)
        else: page.evaluate(PASTE, keys)
        problem = first_line_becomes(page, want)
        if problem: return f"after {action} {keys!r}: {problem}"
    page.screenshot(path=str(out_dir / "michael-typed.png"))

    page.click("#btn-reset")
    problem = first_line_becomes(page, ">", timeout=5000)
    if problem: return f"after reset: {problem}"
    page.keyboard.type("ok")
    problem = first_line_becomes(page, ">ok", timeout=5000)
    if problem: return f"typing after reset: {problem}"
    return None


# The LED as the snapshot and the page show it, and the PA2 pin's level.
LED_STATE = """() => [window._lastState.leds.join(),
                     document.getElementById('led').classList.contains('on'),
                     (window._lastState.porta >> 2) & 1]"""


def check_led_page(page, verbose):
    """The PA2 LED goes on and off on the page as hello_michael_led.s toggles
    it. It is wired from +5V to the pin, so it lights while PA2 is low."""
    page.wait_for_function("window._lastState", timeout=3000)
    seen = set()
    for _ in range(30):
        page.wait_for_timeout(100)
        seen.add(tuple(page.evaluate(LED_STATE)))
    if verbose: print(f"  led states (snapshot, page, PA2) seen: {sorted(seen)}")
    if seen != {("0", False, 1), ("1", True, 0)}:
        return (f"PA2 LED states (snapshot, page, PA2) seen: {sorted(seen)}; "
                "want it on while PA2 is low and off while it is high")
    return None


def run_test(verbose=False):
    missing = missing_tools("michael web UI test")
    if missing: return skipped(missing)
    from playwright.sync_api import sync_playwright

    out_dir = out_dir_for("michael-web-test")
    binaries = {}
    for name in ("michael_keyboard_new", "hello_michael_led"):
        binaries[name] = out_dir / f"{name}.bin"
        if not run_vasm(PROGRAMS / f"{name}.s", binaries[name], out_dir / f"{name}.vasm.log"):
            return failed(f"michael web UI test: vasm failed; see {out_dir}/{name}.vasm.log")

    checks = [("michael_keyboard_new", lambda page: check_keyboard_page(page, out_dir, verbose)),
              ("hello_michael_led", lambda page: check_led_page(page, verbose))]
    for name, check in checks:
        with web_emulator([binaries[name], "--machine", "michael", "--load", load_address()]) as port:
            if port is None:
                return failed(f"michael web UI test ({name}): did not see server listen line in stderr")
            if verbose: print(f"  {name}: emulator port {port}")
            with sync_playwright() as p:
                browser, page = open_page(p, port, track_last_state)
                problem = check(page)
                browser.close()
            if problem:
                return failed(f"michael web UI test ({name}): {problem}")
    return passed(f"michael web UI test (screenshot in {out_dir}/)")


if __name__ == "__main__":
    main("michael web UI test (HTTP+WS + Playwright)", run_test)
