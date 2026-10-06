# `web/`

The browser UI served by `emulator.out --machine wendy2c --web` or
`--machine michael --web` (default
`http://127.0.0.1:8080/`; `--web-port`, `--web-bind` and `--web-root`
adjust it). The server is `../web_server.c`; it serves these files from
the `web/` directory next to the binary unless `--web-root` says otherwise.

| File | Role |
|---|---|
| `index.html` | the page (served at `/`) for every machine: LCD canvas, graphic display canvas (shown for a machine that has one, on the left from the LCD's top down, so the page fits a 1280x900 screen), controls, VIA port pin table, the machine's name, and the status line along the bottom (under the graphic display too, so its changing text can't move the rest) |
| `board.js` | the client: builds the page for the machine the server names (title, LEDs, control button, reset, keys, pin table), draws the LCD per pixel and the graphic display from its memory, lights the LEDs, handles the WebSocket, plays the audio |
| `machines.js` | each machine's description: wendy2c's two LEDs (PB6, PA2) and control button (SPACE holds it, R resets); michael's LED (PA2), keyboard and graphic display; their pin labels |
| `audio_worklet.js` | the AudioWorklet that plays the audio on the browser's audio thread, through the jitter buffer |
| `audio_buffer.js` | the jitter buffer: holds a little more than the longest wait between deliveries (about 150 ms steady, up to 1.5 s for a background tab's bursts), resamples to the sound card at up to 0.5% fast or slow to keep that fill, plays silence on an underrun and drops a backlog |
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
22050 Hz). From michael, also binary frames tagged `0x02`: the graphic
display's memory, as deltas (below), and in the snapshot `gd`, how the
glass shows it. Browser to server (parsed by `../web_json.c`):
`{"type":"reset"}`; wendy2c's `{"type":"button","down":0|1}`; and
michael's `{"type":"keys","bytes":[...]}`, up to 64 bytes of keys as a
terminal sends them (`../ps2_keys.h`), which the server types on the
PS/2 keyboard.

## The graphic display

Michael's graphic display is an ILI9341, 240 by 320 pixels, which Michael
drives through the FPGA bus: raw commands go to the display, and in text
mode the FPGA draws a 20 by 20 grid of characters on it. The emulator
models both (`../chips/ili9341.c`, `../chips/fpga_text_render.c`), so the
page needs only the display's frame memory and a few of its registers:

- **The memory, as deltas.** Each snapshot, the server compares the
  display's memory (320 lines of 240 RGB565 pixels, as the panel scans
  them) with what that page has been sent (a shadow per page) and sends a
  binary message, `0x02` then rectangles of what differs: bands of up to
  16 changed lines, each as wide as its lines' changes, the pixels in runs
  (a run of one of two remembered colours is a byte, a new colour three;
  pixels that neither repeat nor are remembered go as themselves).
  `../web_display.h` has the format. A message is at most 32 KB, less
  while the page's output buffer is filling, and the rest follows with the
  next snapshots, so a fill or a full redraw never floods the socket; a
  page that falls behind gets the latest picture, not every one. A new
  connection gets everything.
- **How the glass shows it: `gd`** in the JSON snapshot: `on` (out of
  reset and sleep and switched on; else the glass is blank, white),
  `bl` (the backlight, 0-255, shown as the canvas's brightness), `gs` and
  `ss` (the scans reversed, as Michael's init sets them: the glass then
  shows scan line 0 at the bottom and a line's pixel 0 at the left) and
  `scroll` (VSCRDEF's top fixed, scroll and bottom fixed areas, and
  VSCRSADD). The page maps each row of the glass to its memory line
  through these, so a hardware scroll is four numbers, not a redraw.

Text mode costs little on the wire this way: a character is a cell of
runs of black and white (about 30 bytes; a typed one, with the cursor's
cells, about 80), a screen full of text about 13 KB, a clear 153 bytes,
and a scroll by the hardware scroll only the row that comes in (blank: 9
bytes). The page redraws the canvas only when the memory or `gd` changed.

Tests: `../tests/michael_display_playwright_test.py`,
`../tests/web_playwright_test.py`,
`../tests/lcd_5x10_playwright_test.py`,
`../tests/michael_web_playwright_test.py`,
`../tests/web_machine_switch_playwright_test.py` and
`../tests/web_audio_buffer_test.py` (headless Chromium, need
`pip3 install playwright && playwright install chromium`).
`../NOTES-web-audio-drift.md` describes the audio pipeline and the
design of the jitter buffer.
