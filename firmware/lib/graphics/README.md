# graphics

Michael's SPI/parallel graphic display and a text console on it.

- `graphics_display.inc`: the display driver (`gd_send_data`, drawing primitives, character output). `CHAR_RESOLUTION` picks 6x8 or 12x16 glyphs.
- `character_patterns*.inc`: the glyph tables (8x8 default, 6x8, 12x16). The 12x16 one, which the FPGA's text mode shares, is generated from the original C font, `firmware/fonts/font-12x16.c` (code page 437's glyphs; the table has `$20`–`$7F`, the FPGA all of them): after changing it, or to use another font in its format, run `python3 tools/font_12x16.py`. It also writes `font_12x16.txt`, every glyph drawn in `#` and `.`, for viewing (generated: don't edit it).
- `graphics_display_cursor.inc`, `graphics_macros.inc`, `graphics_out.inc`, `write_string_to_screen.inc` (`gc_putstring`): cursor, macros and output helpers.
- `graphics_console.inc`: prompt and line editing (`gc_show_prompt`, `gc_getline`); `graphics_console_full.inc` combines it with the keyboard driver and an interrupt handler.

Needs `keyboard_driver.inc` and `multiply8x8.inc`, and constants such as `GC_ZERO_PAGE_BASE` and `GC_LINE_BUFFER`. Example users: `firmware/programs/michael/michael_graphic_*.s`.
