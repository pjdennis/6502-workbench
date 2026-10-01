# lcd

HD44780 LCD routines. Include `display_routines.inc`; it selects `display_routines_4bit.inc` or `_8bit.inc` (and the matching `display_update_routines_*`) from `DISPLAY_BITS`, which the board's `base_config_*.inc` defines (Wendy and Wendy 2: 4, Michael: 8).

Entry points (A, X, Y are preserved unless a file says otherwise):
- `reset_display`, `reset_and_enable_display_no_cursor` (`display_init_helpers.inc`)
- `display_command`, `display_character`, `display_data`, `wait_for_not_busy`
- `clear_display`, `move_cursor`, `display_space`, `display_cursor_on/off` (`display_update_helpers.inc`)
- `display_string` (A, X = address), `display_string_immediate` (string follows the `jsr`), `display_hex`, `display_hex_indirect`, `display_decimal`, `display_binary`
- `extend_character_set.inc`: with `EXTEND_CHARACTER_SET` defined, `display_character` also shows characters the panel lacks by loading custom glyphs.
- `lcd_screen.inc`: a character screen kept in RAM and flushed to the LCD (the `scr_*` calls of `asm/17/environment.asm`); used by the Michael ROM services.
- `display_parameters.inc`: HD44780 command constants.

Temporary parameters (e.g. `DISPLAY_STRING_PARAM`, `D_S_I_P`) are zero-page locations the program defines.
