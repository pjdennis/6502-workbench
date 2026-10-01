# `web/`

The browser UI served by `emulator.out --machine wendy2c --web` (default
`http://127.0.0.1:8080/`; `--web-port`, `--web-bind` and `--web-root`
adjust it). The server is `../wendy2c_web.c`; it serves these files from
the `web/` directory next to the binary unless `--web-root` says otherwise.

| File | Role |
|---|---|
| `index.html` | page: LCD canvas, the two LEDs (PB6, PA2), control and reset buttons, VIA port pin tables, status line |
| `wendy2c.js` | client: draws the LCD per pixel, handles the WebSocket, plays the audio, sends button/reset messages (SPACE also presses the button) |
| `wendy2c.css` | styling |
| `hd44780_a00_font.js` | the HD44780 A00 character ROM as base64 tables, captured from the real wendy2c panel and written by `tools/lcd-ocr/apply_font_to_emulator.py` (which also writes `../chips/hd44780_a00_font.h`); the first version came from the datasheet via `../tools/extract_hd44780_font.py` (see `../tools/README_hd44780_font.md`) |

## Protocol

One WebSocket on the same port. Server to browser: JSON text frames with
a state snapshot (LCD contents and CGRAM, VIA pins, LEDs, `f5x10` mode,
clock) about every 33 ms, and binary frames tagged `0x01` followed by
little-endian int16 mono samples (the PB7 piezo line, 22050 Hz). Browser
to server: `{"type":"button","down":0|1}` and `{"type":"reset"}`
(parsed by `../web_json.c`).

Tests: `../tests/web_playwright_test.py` and
`../tests/lcd_5x10_playwright_test.py` (headless Chromium, need
`pip3 install playwright && playwright install chromium`).
`../NOTES-web-audio-drift.md` describes the audio scheduling and its
weakness.
