# Michael programs

- `hello_michael_*.s`, `michael_decimal_test.s`, `michael_timer2_test2.s`, `michael_show_some_text.s`: LCD, LED and VIA tests.
- `michael_keyboard*.s`: keyboard driver demos and diagnostics (`michael_keyboard_new.s` is the current one; `michael_keyboard_info.s` shows the keyboard's ID, scan code set, lock keys and raw bytes; `michael_keyboard_frame_detector.s` and `michael_keyboard_frame_timing.s` measure the keyboard board's frame timing, and `michael_keyboard_scope.s` repeats Read ID with a trigger on the LED output for an oscilloscope (see [`docs/michael-keyboard-frame-detection.md`](../../../docs/michael-keyboard-frame-detection.md)); `michael_show_vectors.s` shows the installed loader ROM's IRQ, reset and load addresses and tests RAM, to tell which loader ROM a board has).
- `michael_graphic_*.s`: the SPI graphic display, its console and prompt, and `michael_graphic_bf.s`, a Brainfuck REPL.
- `michael_fpga_input_check.s`: steps each signal the FPGA display interface reads, for its input check (see [`hardware/michael/fpga/input-check/`](../../../hardware/michael/fpga/input-check/)).
- `michael_fpga_bus_noise.s`: switches all of port B continuously with the FPGA bus's E held low, for measuring the noise that reaches E (`hardware/michael/fpga/bus-check/noise.py`).
- `michael_fpga_bus_idle.s`: holds the FPGA bus's E low and does nothing else, so a bus check starts from a quiet bus.
- `michael_fpga_bus_check.s`: echoes bytes through the FPGA bus and reads them back, without and then with the keyboard interrupting, and reports through the FPGA's serial port, for the bus check (see [`hardware/michael/fpga/bus-check/`](../../../hardware/michael/fpga/bus-check/)).
- `michael_ram_map.s`: probes RAM.
- [`bringup/`](bringup/): the first standalone-board programs (2021-04), with hard-coded addresses.
- [`bbc-basic/`](bbc-basic/): BBC BASIC on Michael through a MOS shim. It needs the external `../BeebEater` tree, which is not in this repository.

Programs loaded by the ROM start at `PROGRAM_LOAD_ADDRESS` (`$2000`, from `base_config_v2.inc`) and need a `start` label. Upload with `tools/upload/compile_and_upload_michael.sh <program.s>`.
