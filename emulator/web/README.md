# `web/`

The browser UI served by `emulator.out --machine wendy2c --web` or
`--machine michael --web` (default
`http://127.0.0.1:8080/`; `--web-port`, `--web-bind` and `--web-root`
adjust it). The server is `../web_server.c`; it serves these files from
the `web/` directory next to the binary unless `--web-root` says otherwise.

| File | Role |
|---|---|
| `index.html` | the page (served at `/`) for every machine: LCD canvas, controls, VIA port pin table, status line |
| `board.js` | the client: builds the page for the machine the server names (title, LEDs, control button, reset, keys, pin table), draws the LCD per pixel, lights the LEDs, handles the WebSocket, plays the audio |
| `machines.js` | each machine's description: wendy2c's two LEDs (PB6, PA2) and control button (SPACE holds it, R resets); michael's LED (PA2) and keyboard; their pin labels |
| `keyboard.js` | for michael: keys typed or pasted on the page as the bytes a terminal sends, for the PS/2 keyboard |
| `board.css` | styling |
| `hd44780_a00_font.js` | the HD44780 A00 character ROM as base64 tables, captured from the real wendy2c panel and written by `tools/lcd-ocr/apply_font_to_emulator.py` (which also writes `../chips/hd44780_a00_font.h`); the first version came from the datasheet via `../tools/extract_hd44780_font.py` (see `../tools/README_hd44780_font.md`) |

## Protocol

One WebSocket on the same port. Server to browser: first
`{"type":"hello","machine":"wendy2c"|"michael"}`, which picks the
machine description the page builds itself from (the page retries a lost
connection every 500 ms, and rebuilds itself if the hello names another
machine); then JSON text frames with a state snapshot (LCD contents and
CGRAM, VIA pins, `leds` in the order the page numbers them, `btn`,
`f5x10` mode, clock, and `mhz`, the clock's rate measured over the last
half second, against `target_mhz`, which the status line shows, red
below 98%) about every 33 ms, and, from wendy2c, binary frames tagged
`0x01` followed by little-endian int16 mono samples (the PB7 piezo line,
22050 Hz). Browser to server (parsed by `../web_json.c`):
`{"type":"reset"}`; wendy2c's `{"type":"button","down":0|1}`; and
michael's `{"type":"keys","bytes":[...]}`, up to 64 bytes of keys as a
terminal sends them (`../ps2_keys.h`), which the server types on the
PS/2 keyboard.

Tests: `../tests/web_playwright_test.py`,
`../tests/lcd_5x10_playwright_test.py`,
`../tests/michael_web_playwright_test.py` and
`../tests/web_machine_switch_playwright_test.py` (headless Chromium, need
`pip3 install playwright && playwright install chromium`).
`../NOTES-web-audio-drift.md` describes the audio scheduling and its
weakness.
