# Michael programs

- `hello_michael_*.s`, `michael_decimal_test.s`, `michael_timer2_test2.s`, `michael_show_some_text.s`: LCD, LED and VIA tests.
- `michael_keyboard*.s`: keyboard driver demos and diagnostics (`michael_keyboard_new.s` is the current one; `michael_keyboard_info.s` shows the keyboard's ID, scan code set, lock keys and raw bytes; `michael_show_vectors.s` shows the installed loader ROM's IRQ, reset and load addresses and tests RAM, to tell which loader ROM a board has).
- `michael_graphic_*.s`: the SPI graphic display, its console and prompt, and `michael_graphic_bf.s`, a Brainfuck REPL.
- `michael_ram_map.s`: probes RAM.
- [`bringup/`](bringup/): the first standalone-board programs (2021-04), with hard-coded addresses.
- [`bbc-basic/`](bbc-basic/): BBC BASIC on Michael through a MOS shim. It needs the external `../BeebEater` tree, which is not in this repository.

Programs loaded by the ROM start at `PROGRAM_LOAD_ADDRESS` (`$2000`, from `base_config_v2.inc`) and need a `start` label. Upload with `tools/upload/compile_and_upload_michael.sh <program.s>`.
