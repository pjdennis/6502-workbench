# tasks

`prg_*.inc` are small programs for the cooperative multitasking demos (for example `firmware/programs/wendy2/multitasking_test_wendy2c.s` and `firmware/programs/wendy/4bit_multitasking_test_with_mini_display.s`; the other Wendy multitasking tests are `FAIL` in `firmware/manifest.txt`). A demo includes the ones it wants and starts each with `initialize_additional_process`.

- Display: `prg_chase`, `prg_counters`, `prg_print_ticks_counter`, `prg_console_demo`, `prg_small_display_demo` (graphics on a mini display).
- Sound: `prg_play_song` (engine), `prg_ditty`, `prg_repeated_notes`, `prg_play_chromatic_scale`, `prg_star_spangled_banner`, `prg_morse_demo`.
- LED: `prg_flash_led`, `prg_led_control` (button-toggled LED).

They use `lock_screen` from `core/utilities.inc` to share the LCD.
