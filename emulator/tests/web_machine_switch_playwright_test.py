#!/usr/bin/env python3
"""The web page follows the machine the server runs.

One page stays open while the emulator on its port is replaced: wendy2c
(the CGRAM demo uploaded through its boot ROM), then michael
(michael_keyboard_new.s, which echoes keys after a '>' prompt), then
wendy2c again. Each time the page reconnects, it must rebuild itself
for the new machine: its title, its controls (wendy2c's control button,
michael's keyboard), its LCD, and keys typed on michael's page must
reach michael's keyboard.

SKIPs cleanly if vasm6502_oldstyle or playwright are missing.
"""

from web_test_util import (MICHAEL_PROGRAMS, build_wendy2c_upload, failed,
                           first_line_becomes, main, michael_load_address,
                           missing_tools, open_page, out_dir_for, passed, run_vasm,
                           skipped, track_last_state, web_emulator)

# What the page shows of its machine.
PAGE = """() => ({
    machine: document.body.dataset.machine,
    title: document.getElementById('title').textContent,
    button: !!document.getElementById('btn-press'),
    led: !!document.getElementById('led'),
    lcd: window._lastState && [window._lastState.lcd.rows, window._lastState.lcd.cols],
})"""


WANT = {"wendy2c": {"title": "wendy2c", "button": True, "led": False, "lcd": [2, 16]},
        "michael": {"title": "michael v2", "button": False, "led": True, "lcd": [4, 20]}}


def page_shows(page, machine, timeout=10000):
    """None once the page has rebuilt itself for machine and shows its LCD,
    else a failure message."""
    want = WANT[machine]
    try:
        page.wait_for_function("([m, lcd]) => document.body.dataset.machine === m && window._lastState && "
                               "window._lastState.lcd.rows === lcd[0] && window._lastState.lcd.cols === lcd[1]",
                               arg=[machine, want["lcd"]], timeout=timeout)
    except Exception:
        return f"the page never switched to {machine}: {page.evaluate(PAGE)}"
    shown = page.evaluate(PAGE)
    if {k: shown[k] for k in want} != want:
        return f"the page for {machine} shows {shown}; want {want}"
    return None


def run_test(verbose=False):
    missing = missing_tools("machine switch test")
    if missing: return skipped(missing)
    from playwright.sync_api import sync_playwright

    out_dir = out_dir_for("web-machine-switch-test")
    arts = build_wendy2c_upload(out_dir, "cgram_test_wendy2c.s", "cgram")
    keyboard = out_dir / "michael_keyboard_new.bin"
    if arts is None or not run_vasm(MICHAEL_PROGRAMS / "michael_keyboard_new.s", keyboard,
                                    out_dir / "michael_keyboard_new.vasm.log"):
        return failed(f"machine switch test: vasm/framing failed; see {out_dir}/*.vasm.log")
    boot_rom, framed = arts
    wendy2c = [boot_rom, "--machine", "wendy2c", "--serial-input", framed]
    michael = [keyboard, "--machine", "michael", "--load", michael_load_address()]

    with sync_playwright() as p:
        browser = page = None
        port = 0
        try:
            for machine, args in (("wendy2c", wendy2c), ("michael", michael), ("wendy2c", wendy2c)):
                with web_emulator(args, port) as bound:
                    if bound is None:
                        return failed(f"machine switch test: {machine} did not listen on port {port}")
                    port = bound
                    if page is None:
                        browser, page = open_page(p, port, track_last_state)
                    problem = page_shows(page, machine)
                    if not problem and machine == "michael":
                        problem = first_line_becomes(page, ">", timeout=5000)
                        if not problem:
                            page.keyboard.type("hi")
                            problem = first_line_becomes(page, ">hi")
                    if verbose: print(f"  {machine} on port {port}: {page.evaluate(PAGE)}")
                    page.screenshot(path=str(out_dir / f"switch-{machine}.png"))
                    if problem:
                        return failed(f"machine switch test: {problem}")
        finally:
            if browser: browser.close()
    return passed(f"machine switch test (screenshots in {out_dir}/)")


if __name__ == "__main__":
    main("web page machine switch test (HTTP+WS + Playwright)", run_test)
