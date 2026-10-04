# `emulator/tests/`

Run everything from the repository root: the tests open `emulator/...`
paths relative to the current directory. `tools/check_all.sh emulator` runs
`make -s clean && make test`, then `terminal_tests.py` and
`emulator_tests.py`.

## C unit tests (greatest)

`test_*.c`, one binary each in `out/` (built by the Makefile's `C_TESTS`
list; `make sanitizers` rebuilds most of them under ASan/UBSan via
`run_sanitizers.sh`, which has its own copy of the source lists, so a new
test goes in both. It currently leaves out `test_stubs`, `test_serial_link`,
`test_pld_literal`, `test_pld_config_map` and `test_hd44780_font`). They cover:

- CPU core: `test_cpu_variant`, `test_cpu_65c02_*` (fixes, groups A and B,
  bit ops, WAI/STP), `test_cpu_bus_tap`, and `test_dormann` (needs the
  Dormann binaries; see `dormann/README.md`).
- Bus and chips: `test_bus`, `test_chip_*` (clock, rom, ram, via, lcd,
  serial_usb, led_buttons, osc, cpu_65c02), `test_pld_literal` and
  `test_pld_config_map` (the PLD equations and the per-config memory map),
  `test_hd44780_font`.
- Machines and front ends: `test_machine_dispatch`, `test_emu_run`,
  `test_cli`, `test_serial_link`, `test_ps2_keys`, `test_audio`,
  `test_web_json`, `test_web_smoke`.
- nmos-default services: `test_console`, `test_file_io`, `test_stubs`,
  `test_trace`, `test_direct_io`, `test_smoke`.

## End-to-end tests

The shell and Python tests below assemble firmware with `firmware/vasm`
and SKIP (exit 0) when `vasm6502_oldstyle` is missing, except
`timer2_cycles_test.py`, which needs it; the Playwright ones also SKIP
without `playwright`.

| Make target | Script | What it checks |
|---|---|---|
| `michael-goldens` | `michael_goldens.sh` | Michael programs loaded into RAM leave the expected final LCD frame, and the EEPROM loader boots from a ROM image to its ready screen |
| `michael-web` | `michael_web_playwright_test.py` | michael's `--web` page in headless Chromium: the 20x4 LCD and pin table, keys typed and pasted on the page reaching the program through the PS/2 keyboard, reset, the PA2 LED |
| `wendy2c-goldens` | `wendy2c_goldens.sh` | wendy2c programs uploaded through the boot ROM (`--serial-input`) leave the expected LCD frame |
| `wendy2c-lcd-trace` | `lcd_trace_test.sh` | `--lcd-trace` records intermediate LCD frames |
| `wendy2c-merge-sort` | `merge_sort_goldens.sh` | the wendy2 merge-sort demo, asserted on intermediate frames; the full 57344-element case is opt-in with `MERGE_SORT_FULL_N=1` (~60 s) |
| `wendy2c-serial-link` | `wendy2c_serial_link_test.sh` | upload over the `--serial-link` socket with `../wendy2c_emu_link.py` |
| `wendy2c-live-sigint` | `live_sigint_test.py` | Ctrl-C during `--live` restores the terminal |
| `wendy2c-web` | `web_playwright_test.py` | the `--web` UI in headless Chromium: CGRAM rendering, the pin table, state and audio frames, button and reset round trips |
| `wendy2c-lcd5x10` | `lcd_5x10_playwright_test.py` | 5x10 LCD mode in the web UI |
| `web-machine-switch` | `web_machine_switch_playwright_test.py` | one open page follows the emulator on its port from wendy2c to michael and back: title, controls, LCD, and michael's keyboard |
| `web-audio-buffer` | `web_audio_buffer_test.py` | the web page's audio jitter buffer with simulated time: steady streams, jitter, background-tab bursts, a stall, a producer 0.3% slow or fast, a backlog |
| `timer2-cycles` | `timer2_cycles_test.py` + `via_t2_runner.c` | T2 tick timing of `michael_timer2_test2.s` on the CPU and VIA chips |

The Playwright tests share `web_test_util.py` (tool checks, building
programs, starting the `--web` server, opening the page).

## Tests that need the assembler chain

`terminal_tests.py` (`--terminal` mode, serial I/O, `wait_ready`) and
`emulator_tests.py` (file ports, arguments, `--direct-io`, `--strict-api`)
assemble the `*.asm` files here with `asm/17/out/asm.out` (`make -C asm`
or `tools/build_all.sh`) and run them through `../persistent_emulator.py`.
`sigtstp_test.py` (Ctrl-Z / `fg` redraw in terminal mode) uses
`sigtstp_test.asm` and is not wired into `make test` or `check_all`; run
it by hand.

## Opt-in

- `make harte`: Tom Harte's ProcessorTests, see `harte/README.md` and
  `harte/known-deltas.md`. Needs `harte/fetch.sh` first (multi-GB).
- `make -C emulator/tests/dormann`: builds the Dormann binaries (needs
  cc65); until then `test_dormann` reports SKIP.
- `lsan_suppressions.txt`: LeakSanitizer suppressions for `make sanitizers`.
