# graphics

Michael's SPI/parallel graphic display and a text console on it.

- `graphics_display.inc`: the display driver (`gd_send_data`, drawing primitives, character output). `CHAR_RESOLUTION` picks 6x8 or 12x16 glyphs.
- `character_patterns*.inc`: the glyph tables (8x8 default, 6x8, 12x16).
- `graphics_display_cursor.inc`, `graphics_macros.inc`, `graphics_out.inc`, `write_string_to_screen.inc` (`gc_putstring`): cursor, macros and output helpers.
- `graphics_console.inc`: prompt and line editing (`gc_show_prompt`, `gc_getline`); `graphics_console_full.inc` combines it with the keyboard driver and an interrupt handler.

Needs `keyboard_driver.inc` and `multiply8x8.inc`, and constants such as `GC_ZERO_PAGE_BASE` and `GC_LINE_BUFFER`. Example users: `firmware/programs/michael/michael_graphic_*.s`.
