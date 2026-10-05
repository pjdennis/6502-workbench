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

Then runs hello_michael_led.s and checks the PA1 LED lights on the page
as the program toggles it: while PA1 is high, as on the board, where the
LED is wired from the pin to ground (since stage 4 of the FPGA bus plan).

SKIPs cleanly if vasm6502_oldstyle or playwright are missing.
"""

from web_test_util import (MICHAEL_PROGRAMS, failed, first_line_becomes, main,
                           michael_load_address, missing_tools, open_page, out_dir_for,
                           passed, run_vasm, skipped, speed_shown, track_last_state,
                           web_emulator)

PASTE = """(text) => {
    const data = new DataTransfer();
    data.setData('text/plain', text);
    document.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true }));
}"""


def check_keyboard_page(page, out_dir, verbose):
    """The keyboard program's checks; None if they pass, else a failure message."""
    problem = first_line_becomes(page, ">", timeout=5000)
    if problem: return problem
    problem = speed_shown(page, "2.00")     # michael's 2 MHz clock
    if problem: return problem
    page.mouse.click(5, 5)
    page.wait_for_timeout(500)
    if page.text_content("#status-audio"):     # michael has no audio
        return f"audio readout on michael: {page.text_content('#status-audio')!r}"

    lcd = page.evaluate("window._lastState.lcd")
    size = page.evaluate("[document.getElementById('lcd').width, document.getElementById('lcd').height]")
    if verbose: print(f"  lcd {lcd['rows']}x{lcd['cols']}, canvas {size}")
    # 20 cells of 5 dots at 4 px plus 19 gaps of 6 px and 8 px margins
    # across; 4 rows of 8 dots, 3 gaps and the margins down.
    if (lcd["rows"], lcd["cols"]) != (4, 20) or size != [530, 162]:
        return f"LCD geometry: {lcd['rows']}x{lcd['cols']}, canvas {size}; want 4x20, [530, 162]"

    labels = page.evaluate("""() => ['row-a-lbl', 'row-b-lbl'].map(id =>
        [...document.querySelectorAll('#' + id + ' td')].slice(1, 9).map(td => td.textContent))""")
    if labels != [["E", "RW", "RS", "SOEB", "SOLB", "FE", "LED", "A0"],
                  ["D7", "D6", "D5", "D4", "D3", "D2", "D1", "D0"]]:
        return f"pin labels: {labels}"

    # initialize_michael_ports leaves PA1 low: the LED is off.
    led = page.evaluate(LED_STATE)
    if led != [False, "0"]:
        return f"LED (lit, PA1) after the ports are set up: {led}; want it off"

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


# The LED and the PA1 pin's level as the page shows them: both drawn
# from the same snapshot, so they always agree with each other.
LED_STATE = """() => [document.getElementById('led').classList.contains('on'),
                     document.querySelector('#row-a .b1').textContent]"""


def check_led_page(page, verbose):
    """The PA1 LED goes on and off on the page as hello_michael_led.s toggles
    it. It is wired from the pin to ground, so it lights while PA1 is high."""
    page.wait_for_function("window._lastState", timeout=3000)
    seen = set()
    for _ in range(30):
        page.wait_for_timeout(100)
        seen.add(tuple(page.evaluate(LED_STATE)))
    if verbose: print(f"  led states (lit, PA1) seen: {sorted(seen)}")
    if seen != {(False, "0"), (True, "1")}:
        return (f"PA1 LED states (lit, PA1) seen: {sorted(seen)}; "
                "want it on while PA1 is high and off while it is low")
    return None


def run_test(verbose=False):
    missing = missing_tools("michael web UI test")
    if missing: return skipped(missing)
    from playwright.sync_api import sync_playwright

    out_dir = out_dir_for("michael-web-test")
    binaries = {}
    for name in ("michael_keyboard_new", "hello_michael_led"):
        binaries[name] = out_dir / f"{name}.bin"
        if not run_vasm(MICHAEL_PROGRAMS / f"{name}.s", binaries[name], out_dir / f"{name}.vasm.log"):
            return failed(f"michael web UI test: vasm failed; see {out_dir}/{name}.vasm.log")

    checks = [("michael_keyboard_new", lambda page: check_keyboard_page(page, out_dir, verbose)),
              ("hello_michael_led", lambda page: check_led_page(page, verbose))]
    for name, check in checks:
        with web_emulator([binaries[name], "--machine", "michael", "--load", michael_load_address()]) as port:
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
