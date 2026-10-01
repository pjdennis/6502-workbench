# core

Board-independent building blocks.

- `6522.inc`: VIA register addresses from `BASE_ADDRESS_6522` (default `$6000`; Wendy 2 sets `$F000`).
- `macros.inc`: generic macros (`inc16` etc.). `ASCII.inc`: control-character constants.
- `delay_routines.inc`: `delay_hundredths` (A = count) and `delay_10_thousandths`, timed from `CLOCK_FREQ_KHZ`. `utilities.inc`: `lock_screen`/`unlock_screen` (a lock shared by tasks) and `delay_tenth`.
- `buffer.inc` (locking ring buffer for tasks: `buffer_initialize`, `buffer_read`, `buffer_write`, ...) and `simple_buffer.inc` (256-byte ring for interrupt-written bytes, used by the keyboard).
- `to_decimal.inc`, `convert_to_hex.inc`, `multiply8x8.inc`: number conversion and an 8x8 multiply.
- `copy_memory.inc` (macro `invoke_copy_memory`) and `copy_memory_inline.inc`: block copy, used to place interrupt handlers.
- `bf_compiler.inc`: a Brainfuck compiler used by `michael_graphic_bf.s`.
