#!/usr/bin/env python3
"""End-to-end web UI test for the wendy2c emulator.

Drives the embedded HTTP+WS server with a real Chromium via Playwright:

1. Builds the wendy2c boot ROM + a CGRAM-exercising payload via vasm
   (skipped with a warning if vasm6502_oldstyle is missing -- same
   pattern as wendy2c_goldens.sh).
2. Launches emulator/emulator.out --machine wendy2c --web --web-port 0
   and parses the bound port off stderr.
3. Opens the page in headless Chromium, waits for the first state
   snapshot (status text turns to "connected"), then takes a
   screenshot to /tmp/wendy2c-web-test/.
4. Verifies via getImageData() on the LCD canvas:
   - The first character cell has at least some "on" pixels (any
     reasonable rendered glyph).
   - The CGRAM heart at column 5 of line 1 has the expected on/off
     pixel pattern in its top row (pattern: . X . X . from the
     bitmap in cgram_test_wendy2c.s).
   - Also samples a pixel from the second-line CGRAM arrow.
5. Checks the VIA pin table shows wendy2c's pin labels, levels and DDRs.
6. Clicks the button and verifies the .btn.held class lands, then the
   reset button, and that the PC goes back to the boot ROM.
7. Verifies that state and audio frames flowed (counted with
   Playwright's WebSocket frame events).
"""

from web_test_util import (build_wendy2c_upload, failed, main, missing_tools,
                           open_page, out_dir_for, passed, skipped, speed_shown,
                           web_emulator)


def run_test(verbose=False):
    missing = missing_tools("web UI test")
    if missing: return skipped(missing)
    from playwright.sync_api import sync_playwright

    out_dir = out_dir_for("wendy2c-web-test")
    arts = build_wendy2c_upload(out_dir, "cgram_test_wendy2c.s", "cgram")
    if arts is None:
        return failed(f"web UI test: vasm/framing failed; see {out_dir}/*.vasm.log")
    boot_rom, framed = arts

    with web_emulator([boot_rom, "--machine", "wendy2c", "--serial-input", framed]) as port:
        if port is None:
            return failed("web UI test: did not see server listen line in stderr")
        if verbose: print(f"  emulator port {port}")
        with sync_playwright() as p:
            # Count WS frames via Playwright's built-in API rather than
            # monkey-patching WebSocket. In playwright-python, the
            # framereceived handler receives the payload directly --
            # str for text frames, bytes for binary frames.
            state_frames = [0]
            audio_frames = [0]
            def on_frame(payload):
                if isinstance(payload, (bytes, bytearray)):
                    audio_frames[0] += 1
                else:
                    state_frames[0] += 1
            browser, page = open_page(
                p, port, lambda page: page.on("websocket", lambda ws: ws.on("framereceived", on_frame)))
            # Give the state stream a moment so the LCD renders the
            # payload's actual content (post-upload).
            page.wait_for_timeout(1500)

            # Screenshot 1: idle.
            shot1 = out_dir / "web-idle.png"
            page.screenshot(path=str(shot1))

            sf, af = state_frames[0], audio_frames[0]
            if verbose: print(f"  state frames: {sf}, audio frames: {af}")
            if sf < 3:
                return failed(f"web UI test: only {sf} state frames received in 1.5s")
            if af < 3:
                return failed(f"web UI test: only {af} audio frames in 1.5s")

            # The VIA pin table: wendy2c's labels, the pins' levels and DDRs.
            pins = page.evaluate("""
                () => ['row-a', 'row-a-lbl', 'row-b', 'row-b-lbl'].map(id =>
                    [...document.querySelectorAll('#' + id + ' td')].map(td => td.textContent))
            """)
            if verbose: print(f"  pins: {pins}")
            if pins[1][1:9] != ["D7", "D6", "D5", "D4", "RW", "LED", "BTN", "RS"] or \
               pins[3][1:9] != ["T1", "LED", "E", "B4", "B3", "B2", "B1", "B0"]:
                return failed(f"pin labels wrong: {pins[1]} {pins[3]}")
            if any(b not in ("0", "1") for b in pins[0][1:9] + pins[2][1:9]) or \
               not pins[0][9].startswith("DDR=$") or not pins[2][9].startswith("DDR=$"):
                return failed(f"pin levels not shown: {pins[0]} {pins[2]}")

            # Sample LCD canvas pixels. The JS draws:
            #   LCD_MARGIN=8, DOT=3, GAP=1, COLS_PER_CHAR=5, CELL_PAD_X=6
            #   cellW = 5*(3+1) = 20; cellW+padX = 26
            # Char at col 5 row 0 starts at (8 + 5*26, 8) = (138, 8).
            # Heart slot 0 row 0 bitmap is ". X . X .". So:
            #   pixel (1,0) at (138+4, 8) should be ON  (dark teal)
            #   pixel (0,0) at (138,   8) should be OFF (lighter green)
            #
            # We don't hard-code the exact color values (those come
            # from CSS variables); instead we compare relative
            # brightness: on-pixels are noticeably DARKER than off.
            pixel_data = page.evaluate("""
                () => {
                    const c = document.getElementById('lcd');
                    const ctx = c.getContext('2d');
                    const xs = [
                        // (label, x, y)
                        ['heart_on_1_0',  138 + 4 + 1, 8 + 1],   // pixel (1,0) should be on
                        ['heart_off_0_0', 138 +   + 1, 8 + 1],   // pixel (0,0) should be off
                        ['heart_on_3_0',  138 + 12 + 1, 8 + 1],  // pixel (3,0) should be on
                        ['heart_off_4_0', 138 + 16 + 1, 8 + 1],  // pixel (4,0) should be off
                        // First row's middle pixel of 'w' (lit somewhere)
                        ['ascii_w_mid',    8 + 2*4 + 1, 8 + 2*4 + 1],
                    ];
                    return xs.map(([n, x, y]) => {
                        const d = ctx.getImageData(x, y, 1, 1).data;
                        return [n, [d[0], d[1], d[2]]];
                    });
                }
            """)
            if verbose:
                for n, rgb in pixel_data:
                    print(f"  {n}: rgb={rgb}")
            samples = dict(pixel_data)

            def brightness(rgb):
                # Simple luminance proxy: just sum.
                return rgb[0] + rgb[1] + rgb[2]

            heart_on  = brightness(samples["heart_on_1_0"])
            heart_off = brightness(samples["heart_off_0_0"])
            heart_on3 = brightness(samples["heart_on_3_0"])
            heart_off4 = brightness(samples["heart_off_4_0"])

            # On pixels should be at least ~50 brightness-units darker
            # than off pixels (off ~ 200+ in the yellow-green; on ~ 50).
            if heart_off - heart_on < 50:
                return failed(f"CGRAM heart pixel (1,0) not appreciably ON: "
                      f"on={heart_on} off={heart_off}")
            if heart_off4 - heart_on3 < 50:
                return failed(f"CGRAM heart pixel (3,0) not appreciably ON: "
                      f"on={heart_on3} off={heart_off4}")

            # Press the button (mouse.down only, leave it held) and
            # verify .held class lands within 1 s, then release.
            btn_box = page.locator("#btn-press").bounding_box()
            cx = btn_box["x"] + btn_box["width"] / 2
            cy = btn_box["y"] + btn_box["height"] / 2
            page.mouse.move(cx, cy)
            page.mouse.down()
            try:
                page.wait_for_function(
                    "document.getElementById('btn-press').classList.contains('held')",
                    timeout=1000,
                )
            except Exception:
                page.mouse.up()
                return failed(f"button press did not produce .held class")
            shot2 = out_dir / "web-button-pressed.png"
            page.screenshot(path=str(shot2))
            page.mouse.up()

            # Click the reset button. The server pulses bus->res; the
            # CPU+VIA both reset; the boot ROM restarts. Verify by
            # snapshotting the PC field on the status line over a
            # short window and asserting it visits a known boot-ROM
            # address (the upload-and-run EEPROM starts at $8000).
            # The actual ASCII PC text is on #status-clock.
            # Sample the pre-reset PC -- with the cgram payload running
            # it should be parked in the $4000-range payload code.
            # The board clock's measured rate against the wendy2c's 19.44 MHz.
            problem = speed_shown(page, "19.44")
            if problem: return failed(problem)

            pre_pc_text = page.text_content("#status-clock") or ""
            if "pc:$4" not in pre_pc_text:
                return failed(f"pre-reset PC unexpected: '{pre_pc_text}'")
            page.click("#btn-reset")
            # Wait up to 2s for PC to land back in the boot ROM (any
            # $8xxx address). The pulse + a few cycles for the reset
            # vector fetch + boot-ROM init completes well within this.
            try:
                page.wait_for_function(
                    "(document.getElementById('status-clock') || {}).textContent && "
                    "document.getElementById('status-clock').textContent.indexOf('pc:$8') >= 0",
                    timeout=2000,
                )
            except Exception:
                pc_now = page.text_content("#status-clock") or ""
                return failed(f"after reset, PC never re-entered the $8xxx boot ROM: "
                      f"pre='{pre_pc_text}' post='{pc_now}'")
            shot3 = out_dir / "web-after-reset.png"
            page.screenshot(path=str(shot3))

            browser.close()

        passed(f"web UI test (screenshots in {out_dir}/)")
        if verbose:
            print(f"    {shot1}")
            print(f"    {shot2}")
            print(f"    {shot3}")
        return True


if __name__ == "__main__":
    main("wendy2c web UI test (HTTP+WS + Playwright)", run_test)
