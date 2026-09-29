# `emulator/`

A three-machine 6502 emulator:

- **`nmos-default`** — the original direct-memory NMOS 6502 used by the
  assembler bootstrap and the editor. Memory-mapped I/O at
  `$F006`/`$F009`/`$F00C` (read/write/error byte ports) and the rest of
  the file/console/socket ports the assembler relies on.
- **`wendy2c`** — a board-level model of the wendy2c machine: 28C256
  ROM, 512 KiB banked RAM, 22V10 PLD clock + chip-select decoder, 6522
  VIA, HD44780 LCD, serial-USB bridge, LED + button, all wired to a
  W65C02S core. Selected with `--machine wendy2c`.
- **`michael`** — a board-level model of Michael (v2), the Ben Eater-style
  board: 16 KiB RAM at `$0000` (`--ram` picks another decoding), 6522 VIA
  at `$6000`, ROM at `$8000`, a 20x4 HD44780 in 8-bit mode, and the PS/2
  keyboard board (`chips/ps2_keyboard_board.c`). With `--load`, the code
  file is loaded into RAM there, and without `--rom` the ROM holds only
  the vectors (reset to the load address, IRQ to `$3F00`) and the LCD
  starts as the ROM leaves it (two lines, display on, no cursor, clear),
  as programs run from the ROM's loader expect; without `--load`, the
  code file is the ROM image. Selected with
  `--machine michael`. At exit it prints the LCD and a bus check: LCD
  strobes whose lines weren't driven, and spells of two devices driving
  PORTB at once.

The default machine is `nmos-default`; nothing about the assembler
bootstrap chain changed when the wendy2c work landed.

## Building and testing

Run these from the repository root (the tests open `emulator/...` paths
relative to the current directory):

```bash
make                     # build emulator/emulator.out
make test                # C unit tests + michael and wendy2c golden-LCD tests
make michael-goldens     # just the michael end-to-end tests
make wendy2c-goldens     # just the wendy2c end-to-end tests
make harte               # Tom-Harte ProcessorTests (opt-in; needs data)
```

`make test` runs the greatest C suites for every chip module and the
shell-based `michael_goldens.sh` and `wendy2c_goldens.sh`. The goldens
scripts skip with a
warning if `vasm6502_oldstyle` isn't on `PATH`, matching the Harte
runner so CI without vasm still passes.

## CLI

```
emulator <code file> [options] [<arguments>]
emulator --server
```

Common options (the full list is in `--help`):

| Option | Notes |
|---|---|
| `--machine <name>` | `nmos-default` (default), `wendy2c` or `michael` |
| `--cpu <variant>` | `nmos` or `65c02` (wendy2c and michael force `65c02`) |
| `--rom <path>` | wendy2c: ROM image; falls back to the positional code file. michael: ROM image; with `--load` the code file goes into RAM, without it the code file is the ROM |
| `--kbd-scancodes <list>` | michael: comma-separated hex bytes the keyboard sends once the program has set it up |
| `--keys <path>` | michael: keys to type once the program has set up the keyboard -- text, control codes and ANSI key sequences (see `ps2_keys.h`) |
| `--key-interval MS` | michael: milliseconds between typed keys (default 20) |
| `--kbd-fault <name>` | michael: `noedge`, `noirq`, `noack` or `resend` (see `tools/tests/test_michael_keyboard.py`) |
| `--ram <decode>` | michael: how RAM below the VIA is decoded: `16k` (the default: `$0000-$3FFF`), `eater` (Ben Eater's: reads of `$4000-$7FFF` find nothing, but writes there, the VIA's too, land in `$0000-$3FFF`), `full` (24K at `$0000-$5FFF`) or `mirror8k` (8K at `$0000-$1FFF`, repeated up to `$5FFF`); `firmware/programs/michael/michael_ram_map.s` shows which |
| `--serial-input <path>` | wendy2c, michael: bytes pre-queued into the SERIAL_USB chip |
| `--live` | wendy2c: live ANSI render of LCD, LED, button, VIA pins. michael: the LCD, with the terminal's keys typed on the PS/2 keyboard (Ctrl-] quits), paced to 2 MHz or `--mhz` |
| `--cycle-cap N` | max cycles before forced exit (decimal; default 200000000; no cap under `--live` unless this is given explicitly). For wendy2c this is oscillator ticks (~2 per CPU cycle); for `nmos-default` and `--server` it is CPU cycles. |
| `--load <hex>` | load address for the positional code file |
| `--input` / `--output` / `--error-output` | ports `$F006` / `$F009` / `$F00C` |
| `--dump` / `--no-dump` | memory dump on exit |
| `--console` / `--terminal` | full-screen UI modes (mutually exclusive) |
| `--mhz` / `--cpu-mhz` / `--baud` | wall-clock pacing + serial timing |
| `--pace-mask` / `--pace-log` / `--pace-polls` | test hook: after reading an input byte whose mask byte is not `0`, `con_ready` reports not-ready for N polls (default 2000), so the next key arrives only after the program went idle (a `wait_ready` in the pause times out, and the program's next request for input ends the pause); the log gets `<input read> <output written>` as each pause ends. In terminal mode the serial input is held before the first byte and after each such byte until the program asks for input with nothing pending and all its output sent, like a user who waits for the screen before typing (the log is not written there) |
| `--rows N` / `--cols N` | terminal-size overrides |
| `--strict-api` | test hook: each `$F006` call keeps only what its contract (`toolchain/asm2/17/environment.asm`) says. The flags it does not return come back inverted, and the screen calls change A and Y, so a program that relies on more fails its tests here rather than on a board. The server takes it as `API strict` / `API standard` |

## wendy2c demo

`emulator/demo_wendy2c.sh` is the end-to-end smoke launch. It:

1. Assembles `upload_and_run_eeprom_wendy2c.s` into a boot ROM.
2. Assembles a payload (default `hello_ram_4000_wendy2c.s`; override
   via `DEMO_PAYLOAD=...`).
3. Frames the payload (length + bytes + BSD checksum) using
   `wendy2_upload.py`.
4. Runs the emulator with the framed bytes pre-queued so the boot ROM
   uploads them into RAM, jumps to `$4000`, and the payload writes to
   the LCD.

Cycle cap default is 3,000,000 oscillator ticks (~150 ms wallclock).
Override with `DEMO_CYCLE_CAP=<N>`. The script fails fast if any
vasm invocation errors — older vasm releases that don't recognise
flags like `-ignore-mult-inc` will abort cleanly.

Pass `--live` to launch straight into the live render instead:

```sh
bash emulator/demo_wendy2c.sh --live
DEMO_PAYLOAD=wendy2c_led_test.s bash emulator/demo_wendy2c.sh --live
```

`--live` runs uncapped (`DEMO_CYCLE_CAP` still overrides if you want a
fixed-length recording); `q` / `ESC` / `Ctrl-C` in the panel quits.

## `--live` mode

`--live` (wendy2c only) enters an ANSI alternate-screen and renders
every ~30 ms:

```
  LCD:
  +----------------+
  |Hi! I'm Wendy 2.|
  |0042            |
  +----------------+

  LED PB6: [*]    BTN PA5: [ ]   (SPACE)

  PORTA bits:  1 0 1 0 0 1 1 0    DDRA=$FF
                D7  D6 BTN  D4  RW GDC GDR  RS

  PORTB bits:  0 1 0 0 0 1 0 1    DDRB=$3F
                T1 LED   E  B4  B3  B2  B1  B0

  osc:8200000  cpu:4087045  pc:$402E  irq:0  
```

Keys:
- `q` / `ESC` / `Ctrl-C` — quit (terminal contents are restored)
- `SPACE` — toggle the control button (drives PORTA bit 1)

Default live pacing matches the real wendy2c board: 19.44 MHz OSC
(9.72 MHz CPU after the 22V10 divide), derived from
`base_config_wendy2c.inc`'s `CLOCK_FREQ_KHZ = 9720`. Override with
`--mhz N`, where N is the OSC (crystal) frequency in MHz. `--mhz`
also throttles non-live wendy2c runs (which otherwise run at full
host speed); requesting a rate higher than the host can sustain
just runs at host speed.

The alternate-screen save/restore plumbing is shared with `--console`
and `--terminal` via `tty_alt_screen.{c,h}`.

## File layout

```
emulator/
├── emulator.c              main + nmos-default loop + server
├── cli.{c,h}               argument parsing + usage
├── emu_run.{c,h}           emu_run_default loop
├── emu_wendy2c.{c,h}       emu_run_wendy2c + the --live renderer
├── bus.{c,h}               chip vtable + bus walk
├── cpu_core.{c,h}          fake6502-derived CPU; NMOS + 65C02 variants
├── tty_alt_screen.{c,h}    alt-screen + raw termios save/restore
├── trace.{c,h}             E6502_TRACE ring buffers
├── console.{c,h}           full-screen console UI
├── file_io.{c,h}           the nmos-default file ports
├── chips/
│   ├── osc.c               oscillator (drives bus->osc_ticks)
│   ├── clock_22v10.c       PLD model: chip-selects + CPU clock
│   ├── rom_28c256.c        32 KiB ROM
│   ├── ram_628128.c        512 KiB banked RAM (name is historical)
│   ├── cpu_65c02.c         CPU-on-bus wrapper for the wendy2c machine
│   ├── via_6522.c          6522 VIA: regs + T1/T2 + IRQ + CB2/SR
│   ├── lcd_hd44780.c       4-bit HD44780 + DDRAM/CGRAM render
│   ├── serial_usb.c        USB serial -> VIA CB2 + SR shift
│   └── led_buttons.c       LED PB6 tap + control-button injection
├── demo_wendy2c.sh         end-to-end demo (assemble + upload + run)
├── wendy2_upload.py        framed-payload writer (length + BSD checksum)
└── tests/
    ├── test_chip_*.c       per-chip greatest suites
    ├── test_*.c            CLI / emu_run / bus / CPU tests
    ├── harte/              optional Tom-Harte ProcessorTests harness
    └── wendy2c_goldens.sh  end-to-end golden-LCD checks
```

## wendy2c memory map

Decoded by `22V10-wendy2c.pld` (emulated in `chips/clock_22v10.c` via
the generated `clock_22v10_pld_generated.h`). The config is `C4..C0` =
VIA `PB4..PB0`; it reads as `$00` after reset because DDRB is 0.

Wiring:

- ROM (28C256, 32 KiB) sees CPU `A14..A0`, so ROM offset = address & `$7FFF`.
- RAM (512 KiB) sees `R18..R15` from the PLD on its `A18..A15`, CPU `A15`
  on its `A14`, and CPU `A13..A0`. CPU `A14` goes only to the PLD.
  Physical = `R << 15 | A15 << 14 | A13..A0`.
- `/RAMCS` is asserted whenever `/ROMCS` and `/VIACS` are not.
- CK runs at half speed while ROM is selected.

Per config (RAM entries are the physical address of the region's first
byte; `n` = `C3..C0`, `m` = `C2..C0`):

| Config        | `$0000-$3FFF`  | `$4000-$7FFF` | `$8000-$BFFF`       | `$C000-$EFFF`       | `$F000-$F7FF` | `$F800-$FFFF` |
|---------------|----------------|---------------|---------------------|---------------------|---------------|---------------|
| `$00`         | `$08000`       | `$00000`      | ROM `$0000`         | ROM `$4000`         | VIA           | ROM `$7800`   |
| `$01-$0F`     | `n * $8000`    | `$00000`      | `$04000`            | `$0C000`            | VIA           | `$0F800`      |
| `$10`         | `$08000`       | `$00000`      | ROM `$0000`         | ROM `$4000`         | VIA           | `$0F800`      |
| `$18`         | `$10000`       | `$00000`      | ROM `$0000`         | ROM `$4000`         | VIA           | `$0F800`      |
| `$11-$17`     | `$08000`       | `$00000`      | `m * $10000 + $4000`| `m * $10000 + $C000`| VIA           | `$0F800`      |
| `$19-$1F`     | `$10000`       | `$00000`      | `m * $10000 + $4000`| `m * $10000 + $C000`| VIA           | `$0F800`      |

In words:

- `$4000-$7FFF` is common RAM and `$F000-$F7FF` is the VIA (16
  registers on `A3..A0`, mirrored) in every config. `$F800-$FFFF` is
  common RAM in every config except `$00`, where it is ROM.
- Configs `$01-$0F` give 60 KiB of flat RAM; only the lower window
  (which holds zero page and the stack) switches, across banks 1-15.
  `$00` and `$01` share lower bank 1.
- With `C4` set, `C3` picks lower bank 1 or 2 and `C2..C0` picks the
  upper window: `0` maps ROM (`$10`, `$18`), `1-7` map a 28 KiB RAM
  upper bank.

Physical RAM, in 16 KiB halves of 32 KiB bank `k`:

| Physical                        | Reached from                                          |
|---------------------------------|-------------------------------------------------------|
| `$00000-$03FFF`                 | `$4000-$7FFF`, all configs                            |
| `$04000-$07FFF`                 | `$8000-$BFFF`, configs `$01-$0F`                      |
| `$08000-$0BFFF`                 | lower bank 1                                          |
| `$0C000-$0EFFF`                 | `$C000-$EFFF`, configs `$01-$0F`                      |
| `$0F800-$0FFFF`                 | `$F800-$FFFF`, all configs except `$00`               |
| `k * $8000 + $0000-$3FFF`, k≥2  | lower bank `k`                                        |
| `k * $8000 + $4000-$7FFF`, k≥2  | upper bank `m = k / 2` (`$C000` half when `k` is odd) |

Lower banks only ever use the low half of a 32 KiB bank and upper
windows only the high half, so the two windows never alias. Never
reachable: `$0F000-$0F7FF` and `m * $10000 + $F000-$FFFF` for
`m = 1-7` (30 KiB in total). `tests/test_pld_config_map.c` pins these
mappings, including that all 32 configs are distinct.

## Testing references

- **Klaus Dormann's** 6502 functional tests — `tests/dormann/`. Built
  by `tests/test_dormann.c` for the NMOS and 65C02 variants.
- **Tom Harte's ProcessorTests** — `tests/harte/`. Fetched on demand
  via `tests/harte/fetch.sh`. `make harte` runs them when the data is
  present; otherwise prints a warning and exits 0.
- **wendy2c goldens** — `tests/wendy2c_goldens.sh`. Builds and
  uploads real wendy2c programs through the boot-ROM upload protocol
  and checks the resulting LCD frame.

## See also

- `WENDY2_EMULATOR_PLAN.md` — phase-by-phase plan with the design
  rationale for the bus / chip-vtable layout, cycle-pacing strategy,
  and the (still-open) audio + ST7920 + snapshot phases.
- `INVESTIGATION-wendy2c.md` — pre-phase-0 notes on the 22V10 PLD
  decode, serial RX timing, RAM bank ordering, and LCD pin map.
- `NOTES-timing-accuracy.md` — where CPU and VIA cycle timing still
  differs from the W65C02S / W65C22 (instruction-atomic CPU, free
  interrupt entry, SR-under-T2 shift rate, unmodelled VIA features)
  and how to fix each.
