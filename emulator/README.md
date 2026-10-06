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
  `--machine michael`. At exit it prints the LCD, the PA2 LED (lit while
  the pin is low) and a bus check: LCD
  strobes whose lines weren't driven, and spells of two devices driving
  PORTB at once. `--live` runs it in the terminal and `--web` in the
  browser (see [`--web` mode](#--web-mode)).

The default machine is `nmos-default`; nothing about the assembler
bootstrap chain changed when the wendy2c work landed.

## Building and testing

Run these from the repository root (the tests open `emulator/...` paths
relative to the current directory):

```bash
make                     # build emulator/emulator.out
make test                # C unit tests + every end-to-end target below
make michael-goldens     # just the michael end-to-end tests
make wendy2c-goldens     # just the wendy2c end-to-end tests
make sanitizers          # most C tests again under ASan/UBSan/LSan
make harte               # Tom-Harte ProcessorTests (opt-in; needs data)
```

`make test` runs the end-to-end targets first (they are its prerequisites),
then the C unit tests (written with the greatest framework). The end-to-end
targets are (`michael-goldens`, `michael-web`, `michael-display-web`, `wendy2c-goldens`,
`wendy2c-lcd-trace`, `wendy2c-merge-sort`, `wendy2c-serial-link`,
`wendy2c-live-sigint`, `wendy2c-web`, `wendy2c-lcd5x10`, `web-machine-switch`,
`web-audio-buffer`, `timer2-cycles`).
All but `timer2-cycles` and `web-audio-buffer` skip with a warning if
`vasm6502_oldstyle` isn't on `PATH`, and the web tests also if Playwright
is missing (`web-audio-buffer` needs only Playwright); `timer2-cycles`
needs vasm.
The nmos-default tests (`terminal_tests.py`, `emulator_tests.py`) need the
assembler chain and run from `tools/check_all.sh emulator`. See
`tests/README.md` for each suite and the slow opt-in ones.

## CLI

```
emulator <code file> [options] [<arguments>]
emulator --server
```

Common options (run `emulator.out` with no arguments for the full list):

| Option | Notes |
|---|---|
| `--machine <name>` | `nmos-default` (default), `wendy2c` or `michael` |
| `--cpu <variant>` | `nmos` or `65c02` (wendy2c and michael force `65c02`) |
| `--rom <path>` | wendy2c: ROM image; falls back to the positional code file. michael: ROM image; with `--load` the code file goes into RAM, without it the code file is the ROM |
| `--kbd-scancodes <list>` | michael: comma-separated hex bytes the keyboard sends once the program has set it up |
| `--keys <path>` | michael: keys to type once the program has set up the keyboard -- text, control codes and ANSI key sequences (see `ps2_keys.h`) |
| `--key-interval MS` | michael: milliseconds between typed keys (default 20) |
| `--fpga-log <path>` | michael: a line per FPGA bus transfer (a rising edge of E on PA0): `C hh` (command), `D hh` (data), `R` (reply read), `S` (status read) |
| `--kbd-fault <name>` | michael: `noedge`, `noirq`, `noack` or `resend` (see `tools/tests/test_michael_keyboard.py`) |
| `--ram <decode>` | michael: how RAM below the VIA is decoded: `16k` (the default: `$0000-$3FFF`), `eater` (Ben Eater's: reads of `$4000-$7FFF` find nothing, but writes there, the VIA's too, land in `$0000-$3FFF`), `full` (24K at `$0000-$5FFF`) or `mirror8k` (8K at `$0000-$1FFF`, repeated up to `$5FFF`); `firmware/programs/michael/michael_ram_map.s` shows which |
| `--serial-input <path>` | wendy2c, michael: bytes pre-queued into the SERIAL_USB chip |
| `--live` | wendy2c: live ANSI render of LCD, LED, button, VIA pins. michael: the LCD, with the terminal's keys typed on the PS/2 keyboard (Ctrl-] quits), paced to 2 MHz or `--mhz` |
| `--cycle-cap N` | max cycles before forced exit (decimal; default 200000000; no cap under `--live` unless this is given explicitly). For wendy2c this is oscillator ticks (~2 per CPU cycle); for `nmos-default` and `--server` it is CPU cycles. |
| `--load <hex>` | load address for the positional code file |
| `--input` / `--output` / `--error-output` | ports `$F006` / `$F009` / `$F00C` |
| `--dump` / `--no-dump` | memory dump on exit |
| `--console` / `--terminal` | full-screen UI modes (mutually exclusive) |
| `--mhz` / `--cpu-mhz` / `--baud` | wall-clock pacing + serial timing. `--mhz` is the CPU clock for nmos-default and michael (michael `--live` and `--web` default to 2; other michael runs are not paced), but the OSC crystal for wendy2c (CPU = OSC / 2) |
| `--pace-mask` / `--pace-log` / `--pace-polls` | test hook: after reading an input byte whose mask byte is not `0`, `con_ready` reports not-ready for N polls (default 2000), so the next key arrives only after the program went idle (a `wait_ready` in the pause times out, and the program's next request for input ends the pause); the log gets `<input read> <output written>` as each pause ends. In terminal mode the serial input is held before the first byte and after each such byte until the program asks for input with nothing pending and all its output sent, like a user who waits for the screen before typing (the log is not written there) |
| `--rows N` / `--cols N` | terminal-size overrides |
| `--direct-io` | the program calls the `scr_*` screen vectors and `con_read` returns key codes; the emulator converts to and from ANSI (`direct_io.c`) |
| `--wendy2-prog <path>` | wendy2c: preload a raw program into RAM at `--load` (default `$4000`) and start it there, skipping the serial boot |
| `--disk <dir>` | wendy2c: host directory behind the `$F800-$F80F` file-I/O port block (`chips/syscall_ports.h`) |
| `--serial-link <path>` | wendy2c: Unix socket on which a client drives the serial RX line bit by bit (`wendy2c_emu_link.py`) |
| `--web` / `--web-port N` / `--web-bind ADDR` / `--web-root PATH` | wendy2c, michael: browser UI over HTTP + WebSocket (see [`--web` mode](#--web-mode) and `web/README.md`) |
| `--audio` / `--wav <path>` | wendy2c: play the PB7 piezo line live, or record it to a WAV |
| `--lcd-trace <path>` | wendy2c, michael: append an LCD frame to the file each time the LCD changes |
| `--lcd-panel <type>` | wendy2c: `16x2` (default) or `16x1-5x10` render layout |
| `--show-repaints` | debug: flash repainted cells in `--console` / `--terminal` |
| `--strict-api` | test hook: each `$F006` call keeps only what its contract (`asm/17/environment.asm`) says. The flags it does not return come back inverted, and the screen calls change A and Y, so a program that relies on more fails its tests here rather than on a board. The server takes it as `API strict` / `API standard` |

## wendy2c demo

`emulator/demo_wendy2c.sh` is the end-to-end smoke launch. It:

1. Assembles `firmware/boards/wendy2/upload_and_run_eeprom_wendy2c.s`
   into a boot ROM.
2. Assembles a payload (default
   `firmware/programs/wendy2/hello_ram_4000_wendy2c.s`; override via
   `DEMO_PAYLOAD=...`).
3. Frames the payload (length + bytes + BSD checksum) using
   `wendy2_upload.py`.
4. Runs the emulator with the framed bytes pre-queued so the boot ROM
   uploads them into RAM, jumps to `$4000`, and the payload writes to
   the LCD.

Cycle cap default is 3,000,000 oscillator ticks (~150 ms wallclock).
Override with `DEMO_CYCLE_CAP=<N>`. The script fails fast if any
vasm invocation errors — older vasm releases that don't recognise
flags like `-ignore-mult-inc` will abort cleanly. It also takes `--web`
(browser UI), `--audio` and `--wav PATH`; see its header.

Pass `--live` to launch straight into the live render instead:

```sh
bash emulator/demo_wendy2c.sh --live
DEMO_PAYLOAD=firmware/programs/wendy2/wendy2c_led_test.s bash emulator/demo_wendy2c.sh --live
```

`--live` runs uncapped (`DEMO_CYCLE_CAP` still overrides if you want a
fixed-length recording); `q` / `ESC` / `Ctrl-C` in the panel quits.

### Uploading to a running emulator

`wendy2c_emu_serve.sh` starts the emulator with the boot ROM and a
`--serial-link` socket (`--live` by default, or `--web`), like plugging
in the real board. In another terminal,
`compile_and_upload_wendy2c_emu.sh foo.s` assembles, frames and uploads a
program through `wendy2c_emu_upload.py` and `wendy2c_emu_link.py` (the
emulator-side counterparts of `tools/upload/`).

## `--web` mode

`--web` serves the board on `http://127.0.0.1:8080/` (`--web-port`,
`--web-bind`): the LCD drawn dot by dot (CGRAM included), the LEDs, a
reset button, the VIA's port pins and the clock, updated about 30 times
a second. A program's STP stops only the CPU: the board runs on (as it
does under `--live`) until the reset button starts it again; a plain run
ends at STP. The status line shows the emulated clock's measured rate
against the board's (red below 98%: the host isn't keeping up, and the
audio breaks up). It runs uncapped and paced to the board's clock (or `--mhz`)
until Ctrl-C. The page (`web/index.html`) shows the machine the server
names, and an open page that reconnects to a different machine on the
same port rebuilds itself for it; `web/README.md` has the files and the
protocol.

- **wendy2c**: the 16x2 LCD (or `--lcd-panel 16x1-5x10`), the LEDs on
  PB6 and PA2, the control button (SPACE holds it, R resets), and the
  PB7 piezo as audio. `emulator/demo_wendy2c.sh --web` boots a demo.
- **michael**: the 20x4 LCD, the graphic display (the ILI9341 Michael
  drives through the FPGA bus, in raw mode or the FPGA's text mode, its
  hardware scroll and backlight included) and the LED on PA2 (lit while
  PA2 is low, as on the board). Keys typed or pasted on the page go to the PS/2
  keyboard, encoded as `--keys` encodes a terminal's (`ps2_keys.h`): text, Enter, Backspace, Tab, Esc, the
  arrows, Home/End/PgUp/PgDn/Insert/Delete and Ctrl+letter.

```sh
# michael: a program loaded into RAM (the keyboard echo demo)
firmware/vasm -wdc02 -Fbin -dotdir -ignore-mult-inc -esc \
    -o /tmp/kbd.bin firmware/programs/michael/michael_keyboard_new.s
emulator/emulator.out /tmp/kbd.bin --machine michael --load 2000 --web

# michael: the editor, through the ROM's loader
editor/bin/editor-michael.sh --web
```

## `--live` mode

`--live` on wendy2c (michael's `--live` shows just the LCD) enters an ANSI alternate-screen and renders
every ~30 ms:

```
  LCD:
  +----------------+
  |Hi! I'm Wendy 2.|
  |0042            |
  +----------------+

  LED PB6: [*]   LED PA2: [ ]   BTN PA1: [ ]   (SPACE)

  PORTA bits:     1   0   1   0   0   1   1   0    DDRA=$FF
                 D7  D6  D5  D4  RW LED BTN  RS

  PORTB bits:     0   1   0   0   0   1   0   1    DDRB=$3F
                 T1 LED   E  B4  B3  B2  B1  B0

  osc:8200000  cpu:4087045  pc:$402E  irq:0
```

Keys:
- `q` / `ESC` / `Ctrl-C` — quit (terminal contents are restored)
- `SPACE` — toggle the control button (drives PORTA bit 1)
- `R` — pulse RES

Default live pacing matches the real wendy2c board: 19.44 MHz OSC
(9.72 MHz CPU after the 22V10 divide), derived from
`firmware/boards/wendy2/base_config_wendy2c.inc`'s `CLOCK_FREQ_KHZ = 9720`. Override with
`--mhz N`, where N is the OSC (crystal) frequency in MHz. `--mhz`
also throttles non-live wendy2c runs (which otherwise run at full
host speed); requesting a rate higher than the host can sustain
just runs at host speed.

The alternate-screen save/restore plumbing is shared with `--console`
and `--terminal` via `tty_alt_screen.{c,h}`.

## File layout

```
emulator/
├── emulator.c              main + nmos-default port interception + --server
├── cli.{c,h}               argument parsing + usage
├── emu_run.{c,h}           emu_run_default loop (nmos-default)
├── emu_wendy2c.{c,h}       wendy2c machine: chip wiring, run loops, --live renderer
├── emu_michael.{c,h}       michael machine: chip wiring, run loops, --live renderer
├── bus.{c,h}               chip vtable + bus walk
├── cpu_core.{c,h}          fake6502-derived CPU; NMOS + 65C02 variants
├── stubs.{c,h}, file_io.{c,h}, console.{c,h}, direct_io.{c,h}
│                           nmos-default $F006 services, file ports, console/terminal UI
├── tty_alt_screen.{c,h}    alt-screen + raw termios save/restore
├── trace.{c,h}             E6502_TRACE ring buffer / histogram
├── pace.{c,h}, lcd_report.{c,h}, ps2_keys.{c,h}
│                           wall-clock pacing, --lcd-trace output, PS/2 scan codes
├── audio.{c,h}             PB7 -> WAV / miniaudio live playback (vendor/miniaudio.h)
├── serial_link.{c,h}       --serial-link socket transport
├── web_server.{c,h}, web_json.{c,h}, web_run.{c,h}, web_display.{c,h}, web/
│                           --web server, its JSON parser, the shared --web
│                           run loop, the graphic display's deltas, the browser UI
├── chips/                  chip models (see chips/README.md)
├── pld_to_c.py             22V10 .pld -> chips/clock_22v10_pld_generated.h
├── persistent_emulator.py  --server wrapper the Python tests use
├── demo_wendy2c.sh, wendy2c_emu_serve.sh, compile_and_upload_wendy2c_emu.sh,
│   wendy2_upload.py, wendy2c_emu_upload.py, wendy2c_emu_link.py
│                           demo and upload tooling for the emulated wendy2c
├── tools/                  HD44780 font extraction
├── tests/                  see tests/README.md
└── vendor/                 miniaudio
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

- **Klaus Dormann's** 6502 functional tests — `tests/dormann/`. Build the
  binaries there with `make` (needs cc65); `tests/test_dormann.c` runs them
  for the NMOS and 65C02 variants and reports SKIP until they exist.
- **Tom Harte's ProcessorTests** — `tests/harte/`. Fetched on demand
  via `tests/harte/fetch.sh`. `make harte` runs them when the data is
  present; otherwise prints a warning and exits 0.
- **Everything else** — `tests/README.md`.
- **wendy2c goldens** — `tests/wendy2c_goldens.sh`. Builds and
  uploads real wendy2c programs through the boot-ROM upload protocol
  and checks the resulting LCD frame.

## See also

- `chips/README.md`, `tests/README.md`, `web/README.md`,
  `tools/README_hd44780_font.md` — the chip models, the test suites, the
  browser UI and the font extraction tool.
- `WENDY2_EMULATOR_PLAN.md` — the phase-by-phase plan for the wendy2c
  machine (done through phase 13, plus 16-17; phase 14, the ST7920 stub,
  and phase 15, bus-trace mode, snapshots and `--selftest`, were never
  built), with the design rationale for the bus / chip-vtable layout and
  cycle pacing.
- `INVESTIGATION-wendy2c.md` — pre-phase-0 notes on the 22V10 PLD
  decode, serial RX timing, RAM bank ordering, and LCD pin map.
- `NOTES-timing-accuracy.md` — where CPU and VIA cycle timing still
  differs from the W65C02S / W65C22 (instruction-atomic CPU, free
  interrupt entry, SR-under-T2 shift rate, unmodelled VIA features)
  and how to fix each.
- `NOTES-web-audio-drift.md` — how web audio was scheduled, and the
  jitter buffer and drift correction that replaced it.
