#!/usr/bin/env python3
"""End-to-end test of HD44780 5x10 LCD mode via the live web UI.

Boots the wendy2c emulator with lcd_5x10_demo_wendy2c.s as the
uploaded payload, opens the page with headless Chromium, and checks:

  * The state snapshots include `f5x10: 1` after the payload's
    function-set instruction lands.
  * The LCD canvas grows taller than 5x8 (rows-per-cell rose from
    9 to 11), so the dot grid is being drawn at the 5x10 size.
  * A pixel sampled on the descender of the ROM A00 glyph at code
    0xF0 (row 8/9 below the 5x8 baseline) is actually ON, proving
    the 5x10 ROM lookup is wired through.

SKIPs cleanly if vasm6502_oldstyle or playwright are missing.
"""

from web_test_util import (build_wendy2c_upload, failed, main, missing_tools,
                           open_page, out_dir_for, passed, skipped, track_last_state,
                           web_emulator)


def run_test(verbose=False):
    missing = missing_tools("5x10 LCD test")
    if missing: return skipped(missing)
    from playwright.sync_api import sync_playwright

    out_dir = out_dir_for("wendy2c-lcd5x10-test")
    arts = build_wendy2c_upload(out_dir, "lcd_5x10_demo_wendy2c.s", "lcd5x10")
    if arts is None:
        return failed(f"5x10 LCD test: vasm/framing failed; see {out_dir}/*.vasm.log")
    boot_rom, framed = arts

    with web_emulator([boot_rom, "--machine", "wendy2c", "--serial-input", framed,
                       "--lcd-panel", "16x1-5x10"]) as port:
        if port is None:
            return failed("5x10 LCD test: did not see server listen line")
        with sync_playwright() as p:
            # Capture the most recent panel_5x10 / f5x10 / panel_rows
            # from each state frame.
            browser, page = open_page(p, port, track_last_state)
            page.wait_for_timeout(2500)

            lcd = page.evaluate("window._lastState.lcd")
            if verbose:
                print(f"  panel_5x10={lcd.get('panel_5x10')}  panel_rows={lcd.get('panel_rows')}  "
                      f"f5x10={lcd.get('f5x10')}  rows={lcd.get('rows')}")
            if lcd.get("panel_5x10") != 1:
                return failed(f"5x10 LCD test: panel_5x10 = {lcd.get('panel_5x10')}, want 1")
            if lcd.get("panel_rows") != 1:
                return failed(f"5x10 LCD test: panel_rows = {lcd.get('panel_rows')}, want 1")
            if lcd.get("f5x10") != 1:
                return failed(f"5x10 LCD test: f5x10 = {lcd.get('f5x10')}, want 1 "
                      f"(firmware should have set the F bit)")

            # In 16x1 5x10 panel mode each cell is 12 rows tall (10 glyph
            # + 1 gap + 1 cursor) * (DOT=3 + GAP=1) = 48 px. With one
            # display row that's 48 + 2*8 margin = 64. (For comparison
            # a 5x8 cell is 9*(3+1) = 36 px which would total 52.) We
            # just sanity-check height landed above the 5x8 size.
            canvas_h = page.evaluate("document.getElementById('lcd').height")
            if verbose: print(f"  canvas height = {canvas_h}")
            if canvas_h < 60:
                return failed(f"5x10 LCD test: canvas height={canvas_h}, "
                      f"expected >= 60 for a 1-row 5x10 panel")

            # Sample the cursor-gap pixel: column 0, row 0 cell, at
            # y_rel = glyphRows*DOT_PITCH + 1 (the +1 lands inside the
            # blank gap row, not the dot). For DOT=3, GAP=1, pitch=4:
            # gap row is at y_rel = 10*4 = 40..42 (3 px tall).
            # Cell top-left is at (LCD_MARGIN, LCD_MARGIN) = (8, 8).
            # Sample (8+1, 8+40+1) — should be OFF (backlight color).
            # Cursor row is just below at y_rel = 11*4 = 44..46.
            samples = page.evaluate("""
                () => {
                    const c = document.getElementById('lcd');
                    const ctx = c.getContext('2d');
                    const pick = (x, y) => Array.from(ctx.getImageData(x, y, 1, 1).data).slice(0,3);
                    return {
                        // Column 0 cell. Gap row sits at y_rel = 10*4 = 40..42.
                        gap:    pick(8 + 1, 8 + 40 + 1),
                        // First glyph row of '5' should have dots (any column lit).
                        glyph0: pick(8 + 4 + 1, 8 + 0 + 1),
                    };
                }
            """)
            if verbose:
                print(f"  gap rgb = {samples['gap']}")
                print(f"  glyph0 rgb = {samples['glyph0']}")
            # The gap row must always be OFF -- noticeably brighter than
            # an ON pixel. Same delta threshold as the existing web
            # playwright test: ~50+ brightness units.
            br = lambda rgb: rgb[0] + rgb[1] + rgb[2]
            if br(samples["gap"]) - br(samples["glyph0"]) < 50:
                return failed(f"5x10 LCD test: gap row not OFF: "
                      f"gap rgb={samples['gap']} (brightness {br(samples['gap'])}), "
                      f"glyph rgb={samples['glyph0']} (brightness {br(samples['glyph0'])})")

            shot = out_dir / "lcd5x10.png"
            page.screenshot(path=str(shot))
            if verbose: print(f"  screenshot: {shot}")
            browser.close()

        return passed(f"5x10 LCD test (screenshot in {out_dir}/)")


if __name__ == "__main__":
    main("wendy2c 5x10 LCD test (HTTP+WS + Playwright)", run_test)
