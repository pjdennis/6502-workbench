# Wendy 2 programs

- `hello_ram_4000_wendy2c.s`, `hello_ram_5000_wendy2c.s`: RAM-loader hello programs (the ones used in the README's quick start).
- `verification_wendy2c.s`: memory-map check against the PLD, reporting ticks and crosses on the LCD; run by the emulator tests.
- `wendy2_merge_sort.s`: a merge sort over banked RAM (`N_ELEMENTS` build option); the emulator's `merge_sort_goldens.sh` runs it.
- `lcd_*.s`, `cgram_test_wendy2c.s`, `pd_char_test_wendy2c.s`: LCD tests, font calibration (used with `tools/lcd-ocr/`) and character-set browsing. `lcd_5x10_demo_wendy2c.s` with `lcd_5x10_demo.sh`, which runs it in the emulator's web front end.
- `wendy2c_*.s`: EEPROM read/write, LED, interrupt and graphic-display tests. `multitasking_test_wendy2c.s`: the multitasking demo.

All include `base_config_wendy2c.inc`. Upload with `tools/upload/compile_and_upload_wendy2.sh <program.s>` or run in the emulator with `emulator/demo_wendy2c.sh`.
