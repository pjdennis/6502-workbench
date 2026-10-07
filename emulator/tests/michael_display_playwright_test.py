#!/usr/bin/env python3
"""Michael's graphic display on the --web page: the ILI9341 that Michael drives through the FPGA bus, drawn
on a canvas from the display's memory (sent as deltas) and the snapshot's "gd" (on, backlight, scans, the
hardware scroll). The canvas is the glass, a canvas pixel a panel pixel.

1. michael_graphic_text.s, on the FPGA's text mode: the page's layout (the display on the left, level with
   the LCD's top, the status bar along the bottom), the reverse title, typed text, Tab's reverse video, the
   cursor blinking, and Enter at the bottom scrolling the region by the hardware scroll (VSCRSADD moves) with
   the rows in order on the glass. A typed character costs little on the wire.
2. michael_graphic_display_test.s, raw mode: its colour stripes, then its text, drawn by Michael's driver;
   then its STP stops the CPU but not the board, and reset starts it again.
3. michael_graphic_brightness.s: the backlight's level dims the glass.

The cells are read off the canvas against the 12x16 font (tools/font_12x16.py). SKIPs cleanly if
vasm6502_oldstyle or playwright are missing.
"""
import sys

from web_test_util import (MICHAEL_PROGRAMS, REPO_ROOT, board_runs_past_stp, failed, layout_problems, main,
                           michael_load_address, missing_tools, open_page, out_dir_for, passed, run_vasm, skipped,
                           track_last_state, web_emulator)

sys.path.insert(0, str(REPO_ROOT / "tools"))
import font_12x16  # noqa: E402

ROWS, COLS, CELL_W, CELL_H = 20, 20, 12, 16
TITLE = " MICHAEL TEXT MODE  "

# Counts the display's binary messages (tag 2) and their bytes, and keeps the latest snapshot
COUNT_DISPLAY = """
    window._displayBytes = 0;
    window._displayMessages = 0;
    const countWS = window.WebSocket;
    window.WebSocket = function(...args) {
        const ws = new countWS(...args);
        ws.addEventListener('message', (e) => {
            if (typeof e.data !== 'string' && new Uint8Array(e.data)[0] === 2) {
                window._displayBytes += e.data.byteLength;
                window._displayMessages++;
            }
        });
        return ws;
    };
    for (const k in countWS) window.WebSocket[k] = countWS[k];
"""

# The glass as the canvas shows it: a character a pixel, '#' lit (white) and '.' dark
GLASS = """() => {
    const c = document.getElementById('gd');
    const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    let s = '';
    for (let i = 0; i < d.length; i += 4) s += d[i] + d[i + 1] + d[i + 2] > 384 ? '#' : '.';
    return [c.width, c.height, s];
}"""

PIXEL = """([x, y]) => {
    const d = document.getElementById('gd').getContext('2d').getImageData(x, y, 1, 1).data;
    return [d[0], d[1], d[2]];
}"""


def font_cells():
    """{16 rows of '#'/'.': (character, reverse, cursor)}, every way a cell can show"""
    cells = {}
    flip = {'#': '.', '.': '#'}
    for code, rows in sorted(font_12x16.read_source().items(), reverse=True):   # ' ' last: it wins
        for reverse in (False, True):
            shown = [''.join(flip[p] for p in row) if reverse else row for row in rows]
            cells[tuple(shown)] = (chr(code), reverse, False)
            cursor = shown[:CELL_H - 2] + [''.join(flip[p] for p in row) for row in shown[CELL_H - 2:]]
            cells[tuple(cursor)] = (chr(code), reverse, True)
    return cells


CELLS = font_cells()


def read_screen(page):
    """The glass read as text: [(characters, reverse flags, cursor flags)] a row, '?' for a cell that isn't
    a character"""
    width, height, glass = page.evaluate(GLASS)
    assert (width, height) == (CELL_W * COLS, CELL_H * ROWS), (width, height)
    screen = []
    for r in range(ROWS):
        text, reverse, cursor = '', [], []
        for c in range(COLS):
            rows = tuple(glass[(r * CELL_H + y) * width + c * CELL_W:][:CELL_W] for y in range(CELL_H))
            ch, rev, cur = CELLS.get(rows, ('?', False, False))
            text += ch
            reverse.append(rev)
            cursor.append(cur)
        screen.append((text, reverse, cursor))
    return screen


def screen_becomes(page, want, timeout=8.0):
    """None once rows 0.. of the glass read as want (each row's text, trailing blanks dropped), else a
    failure message"""
    deadline = page.evaluate("performance.now()") + timeout * 1000
    while True:
        rows = [text.rstrip() for text, _, _ in read_screen(page)]
        if rows[:len(want)] == want:
            return None
        if page.evaluate("performance.now()") > deadline:
            return f"the glass shows {rows[:len(want)]}, want {want}"
        page.wait_for_timeout(150)


def gd(page):
    return page.evaluate("window._lastState && window._lastState.gd")


def check_layout(page):
    """The graphic display on the left, level with the LCD's top; the LCD,
    ports and title on its right; the status bar under them all, from the
    display's left edge to the ports' right (layout_problems has the rest).
    None, or a failure message."""
    page.wait_for_function("!document.getElementById('gd-frame').hidden", timeout=5000)
    box, problems = layout_problems(page, ["gd-bezel"])
    gd, lcd, pins, title, status = (box[i] for i in ("gd-bezel", "lcd-bezel", "pins", "title", "status"))
    if not (gd[2] < lcd[0] and gd[2] < pins[0] and gd[2] < title[0]):
        problems.append("the display isn't left of the LCD, ports and title")
    if abs(gd[1] - lcd[1]) > 2:
        problems.append("the display's top isn't level with the LCD's")
    if abs(gd[0] - status[0]) > 2:
        problems.append("the status bar's left edge isn't the display's")
    return f"layout: {'; '.join(problems)}: {box}" if problems else None


def check_text_mode(page, out_dir, verbose):
    problem = check_layout(page)
    if problem: return problem
    problem = screen_becomes(page, [TITLE.rstrip()])
    if problem: return problem
    text, reverse, _ = read_screen(page)[0]
    if not all(reverse): return f"the title isn't in reverse video: {reverse}"
    state = gd(page)
    if not state["on"] or state["gs"] != 1 or state["ss"] != 1:
        return f"gd state after the program's set-up: {state}"

    before = page.evaluate("window._displayBytes")
    page.keyboard.type("H")
    problem = screen_becomes(page, [TITLE.rstrip(), "H"])
    if problem: return problem
    page.wait_for_timeout(300)
    typed = page.evaluate("window._displayBytes") - before
    if verbose: print(f"  one key: {typed} bytes of display messages")
    if typed > 1500:
        return f"a typed character took {typed} bytes of display messages"

    page.keyboard.type("i there")
    page.keyboard.press("Tab")
    page.keyboard.type("R")
    page.keyboard.press("Tab")
    problem = screen_becomes(page, [TITLE.rstrip(), "Hi thereR"])
    if problem: return problem
    _, reverse, _ = read_screen(page)[1]
    if reverse[:10] != [False] * 8 + [True, False]:
        return f"Tab's reverse video: row 1 reverse flags {reverse[:10]}"

    # The cursor (after the R, at 1, 9) blinks: seen on and off
    seen = set()
    for _ in range(12):
        seen.add(read_screen(page)[1][2][9])
        page.wait_for_timeout(90)
    if seen != {True, False}:
        return f"the cursor at row 1, column 9 never blinked: shown {sorted(seen)}"

    before = page.evaluate("window._displayBytes")
    page.keyboard.press("Enter")
    for i in range(25):
        page.keyboard.type(f"L{i:02d}")
        page.keyboard.press("Enter")
    want = [TITLE.rstrip()] + [f"L{i:02d}" for i in range(7, 25)] + [""]
    problem = screen_becomes(page, want, timeout=15.0)
    if problem: return f"after 26 lines: {problem}"
    scroll = gd(page)["scroll"]
    lines = page.evaluate("window._displayBytes") - before
    if verbose: print(f"  scroll {scroll}; 26 lines typed: {lines} bytes of display messages")
    if scroll[:3] != [0, 304, 16] or scroll[3] == 0:
        return f"the region (rows 1-19) isn't scrolled by the hardware scroll: {scroll}"
    if lines > 40000:
        return f"typing 26 lines took {lines} bytes of display messages"
    page.screenshot(path=str(out_dir / "michael-text-mode.png"))
    return None


def check_raw_mode(page, out_dir, verbose):
    stripes = [(255, 0, 0), (255, 255, 255), (255, 165, 0), (255, 255, 0)]   # red, white, orange, yellow
    try:
        page.wait_for_function(
            """(want) => {
                   const d = document.getElementById('gd').getContext('2d').getImageData(0, 300, 40, 1).data;
                   return want.every((rgb, i) => rgb.every((v, k) => Math.abs(v - d[(5 + 10 * i) * 4 + k]) <= 8));
               }""", arg=stripes, timeout=15000)
    except Exception:
        got = [page.evaluate(PIXEL, [5 + 10 * i, 300]) for i in range(4)]
        return f"the stripes never showed: {got}"
    page.screenshot(path=str(out_dir / "michael-raw-stripes.png"))
    problem = screen_becomes(page, ["Hello, World! The", "quick brown fox"], timeout=20.0)
    if problem: return problem
    if verbose: print(f"  raw mode: {page.evaluate('window._displayMessages')} display messages, "
                      f"{page.evaluate('window._displayBytes')} bytes")
    page.screenshot(path=str(out_dir / "michael-raw-text.png"))

    # The program ends with STP: the CPU stops, the board runs on.
    return board_runs_past_stp(page)


def check_backlight(page, out_dir, verbose):
    try:
        page.wait_for_function("window._lastState && window._lastState.gd && window._lastState.gd.on",
                               timeout=8000)
    except Exception:
        return f"the display never came on: {gd(page)}"
    page.wait_for_timeout(500)
    page.keyboard.type("0")              # a preset: the backlight off
    try:
        page.wait_for_function("window._lastState.gd.bl === 0 && "
                               "document.getElementById('gd').style.filter === 'brightness(0)'", timeout=5000)
    except Exception:
        shown = page.evaluate("document.getElementById('gd') && document.getElementById('gd').style.filter")
        return f"backlight 0: gd {gd(page)}, canvas filter {shown!r}"
    page.keyboard.type("9")              # full
    try:
        page.wait_for_function("window._lastState.gd.bl === 255 && "
                               "document.getElementById('gd').style.filter === 'brightness(1)'", timeout=5000)
    except Exception:
        return f"backlight 255: gd {gd(page)}"
    return None


def run_test(verbose=False):
    missing = missing_tools("michael graphic display web test")
    if missing: return skipped(missing)
    from playwright.sync_api import sync_playwright

    out_dir = out_dir_for("michael-display-web-test")
    names = ("michael_graphic_text", "michael_graphic_display_test", "michael_graphic_brightness")
    binaries = {}
    for name in names:
        binaries[name] = out_dir / f"{name}.bin"
        if not run_vasm(MICHAEL_PROGRAMS / f"{name}.s", binaries[name], out_dir / f"{name}.vasm.log"):
            return failed(f"michael graphic display web test: vasm failed; see {out_dir}/{name}.vasm.log")

    checks = {"michael_graphic_text": check_text_mode, "michael_graphic_display_test": check_raw_mode,
              "michael_graphic_brightness": check_backlight}
    for name in names:
        with web_emulator([binaries[name], "--machine", "michael", "--load", michael_load_address()]) as port:
            if port is None:
                return failed(f"michael graphic display web test ({name}): no server listen line")
            with sync_playwright() as p:
                browser, page = open_page(p, port, lambda pg: (track_last_state(pg), pg.add_init_script(COUNT_DISPLAY)))
                try:
                    problem = checks[name](page, out_dir, verbose)
                finally:
                    browser.close()
            if problem:
                return failed(f"michael graphic display web test ({name}): {problem}")
    return passed(f"michael graphic display web test (screenshots in {out_dir}/)")


if __name__ == "__main__":
    main("michael graphic display web test (HTTP+WS + Playwright)", run_test)
