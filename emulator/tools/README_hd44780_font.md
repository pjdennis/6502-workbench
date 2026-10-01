# HD44780 ROM Code A00 font extraction

This directory holds `extract_hd44780_font.py`, the tool that pulls
the bitmap pattern for every character in the HD44780U's ROM Code A00
charset from page 17 of the Hitachi datasheet.

The generated artifacts are committed to the repo:

* `emulator/chips/hd44780_a00_font.h`
  C arrays `hd44780_a00_font_5x8[256][8]` and `hd44780_a00_font_5x10[32][10]`.
  Each glyph byte's low 5 bits encode one dot row; bit 4 is the
  leftmost pixel.

* `emulator/web/hd44780_a00_font.js`
  The same two tables, base64-encoded into a small JS module that
  defines `window.HD44780_A00 = { font5x8, font5x10 }` as `Uint8Array`s.

The committed tables no longer come straight from this tool: codes
`0x20`-`0xFF` were since overwritten with the font captured from the real
wendy2c panel by `tools/lcd-ocr/apply_font_to_emulator.py` (see
`tools/lcd-ocr/README.md`), which also rewrites both file headers. Re-running
the extractor replaces the captured glyphs with the datasheet ones.

## Regenerating from the datasheet

To re-run:

```sh
# 1) Fetch the datasheet PDF (~330 KB) -- public availability:
mkdir -p /tmp/hd44780
curl -L -o /tmp/hd44780/HD44780.pdf https://eater.net/datasheets/HD44780.pdf

# 2) Render page 17 to a 300-DPI PNG using poppler-utils:
pdftoppm -r 300 /tmp/hd44780/HD44780.pdf /tmp/hd44780/page17 -f 17 -l 17 -png

# 3) Run the extractor (auto-detects the table grid; emits both files):
python3 emulator/tools/extract_hd44780_font.py \
    /tmp/hd44780/page17-17.png \
    -o   emulator/chips/hd44780_a00_font.h \
    --js emulator/web/hd44780_a00_font.js
```

## How it works

* The script grabs Table 4 from page 17, finds the 17 vertical + 17
  horizontal dividing lines via dark-pixel-row sums, and uses them to
  index 16x16 cells.
* Inside each cell it samples 5 known dot-center positions horizontally
  and 8 (5x8) or 10 (5x10) vertically; a small 7x7 mean-darkness probe
  classifies each dot as on or off.
* Columns 14 (0b1110) and 15 (0b1111) hold the 32 codes whose 5x10
  patterns also appear in the chart -- those use the 10-row sampling.
* Column 0 (0b0000) is the CGRAM-placeholder column; the chart shows
  literal "CG RAM (n)" labels there, not glyph data, so the script
  zeros those entries.

`emulator/tests/test_hd44780_font.c` spot-checks the
generated header against well-known canonical glyphs ('0', 'A', the
all-on 0xFF block, F0 descender). If a regeneration alters the bits
the test fires immediately.
