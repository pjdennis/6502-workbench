# Michael

The second board (v2, 2021). It started as an alternative way to build Ben Eater's 6502 computer. Instead of wiring the whole machine and then hoping it works, you **start with just the CPU and an Arduino**. The Arduino plays the part of every missing component, and each real part replaces its emulated stand-in as it goes onto the breadboard. The build ends identical to the Ben Eater board. It was later extended with an 8-bit LCD interface, a shift-register keyboard, an SPI graphic display and BBC BASIC.

The schematics are in [`schematics/`](schematics/): Michael as built, in three sheets, plus Ben Eater's schematic and the keyboard board's.

The keyboard board ([`schematics/michael-bidirectional-PS2-keyboard-interface-schematic-v-1.0.pdf`](schematics/michael-bidirectional-PS2-keyboard-interface-schematic-v-1.0.pdf)) finds the end of each byte by waiting for the clock to go idle. Some keyboards send their command replies too quickly for that, and a byte is lost. See [`docs/michael-keyboard-frame-detection.md`](../../docs/michael-keyboard-frame-detection.md) for the measurements and the recommended change.

The SPI graphic display's interface board was replaced by an FPGA (a Digilent Cmod A7-35T) on 2026-10-03, first as a drop-in for the old board ([`fpga/spi-display/`](fpga/spi-display/), which has the wiring; the schematic is sheet 3), with bring-up tools for the inputs ([`fpga/input-check/`](fpga/input-check/)) and the display ([`fpga/display-probe/`](fpga/display-probe/)). Since 2026-10-04 it is a general bus to the FPGA ([`docs/michael-fpga-bus-plan.md`](../../docs/michael-fpga-bus-plan.md)), with the display as its first device and the display driver moved onto it: [`fpga/bus/`](fpga/bus/) is the design in the Cmod's flash, and [`fpga/bus-check/`](fpga/bus-check/) checks its reads.

Firmware for the finished board: `firmware/boards/michael/` (`base_config_v2.inc`) and `firmware/programs/michael/`.

## Bring-up stages

The Arduino sits on the CPU's address bus (16 lines), data bus (8 lines) and control lines (clock, reset, R/W, RDY, chip selects). The sketches use digital pins 22–53, the Arduino Mega layout. A host PC talks to the Arduino over USB serial at 115200 baud.

| Stage | Sketch / programs | What's real, what the Arduino provides |
|---|---|---|
| **1. CPU only** | [`arduino/6502-environment/`](arduino/6502-environment/) (2021-01-22 → 02-12), [`arduino/programs/`](arduino/programs/) | Only the 65C02 is real. The Arduino generates the **clock** (slow, fast or free-running, or single cycles), drives **reset** and **RDY**, and on every cycle answers the bus as **ROM** (1 KB at `$FC00`, including the vectors), **RAM** (1 KB at `$0000`) and a **character output port** (`$7000`). Its output is forwarded to the host. Programs are loaded into the emulated memory over serial. |
| **2. RAM added** | [`arduino/6502-ram-test/`](arduino/6502-ram-test/) (2021-01-22), then `6502-environment` with `a` (switch to real RAM) | The real RAM chip goes on the board. `6502-ram-test` first checks it by driving the buses directly. Then the Arduino writes the program into the **real RAM** and releases the bus so the CPU runs from it. The Arduino still supplies the clock and the I/O port. |
| **3. EEPROM added** | [`arduino/6502-environment-eeprom/`](arduino/6502-environment-eeprom/) (2021-01-28) | The 28C256 EEPROM goes in at `$8000`. The Arduino **programs it in circuit** (`p` copies the ROM image it holds into the real EEPROM, page by page). `e` switches the CPU over to the real EEPROM, so no separate EEPROM programmer is needed. |
| **4. Standalone board** | [`firmware/programs/michael/bringup/`](../../firmware/programs/michael/bringup/) (2021-04-06) | The board now matches Ben Eater's: VIA at `$6000`, EEPROM at `$8000`, its own clock. The Arduino is no longer needed. The bring-up programs test the LEDs, the LCD and interrupts, and led to the keyboard scan-code console (2021-04-09). Three days later (2021-04-09, `eb3853c`, "RAM upload to Michael working"), `base_config_v2.inc` and the serial upload-and-run loader took over. |

[`arduino/6502-environment-simplified/`](arduino/6502-environment-simplified/) (2021-01-25) is a trimmed-down stage-1 sketch that runs free only and has fewer commands.

### Arduino serial commands (`6502-environment`)

Speed and running:

| Command | Action |
|---|---|
| `f` | fast clock |
| `w` | slow clock |
| `e` | free run |
| `s` | stop |
| `g` | go |
| `c` | one clock cycle |
| `r` | reset |

Memory:

| Command | Action |
|---|---|
| `l` | load memory from serial |
| `d` | dump RAM |
| `m` | dump ROM |
| `a` | switch to real RAM |
| `i` | switch back to emulated RAM |
| `b` | boot |

The EEPROM sketch replaces `a` and `i` with these:

| Command | Action |
|---|---|
| `p` | program the real EEPROM |
| `e` | switch to real EEPROM |
| `i` | switch to emulated EEPROM |
| `t` | show state |
| `x` | dump EEPROM |

## Files

- `arduino/6502-*/`: the sketches (each directory is one Arduino IDE project).
- `arduino/programs/`: 6502 test programs for the **emulated** machine of stages 1–2. They run from `$FC00` (or `$0000`) and print through `$7000` or the character buffer at `$0200` that the sketch's `IO.ino` defines.
  - `hello.s`, `hello-2.s`, `hello-buffer.s`, `hello-interlocked.s`: character output, first direct, then buffered, then interlocked with the Arduino.
  - `counter.s`: a counter running from emulated RAM.
  - `memory.s`: a test pattern in the ROM area.
  - `compile_and_upload.sh <program.s>` assembles a program and loads it with `l`.
- `arduino/host/`: host-side scripts.
  - `transfer_with_length.py` sends the Arduino's `l` command plus the raw bytes. This is *not* the board's serial loader protocol.
  - `makebin.py` writes a 1 KB test pattern.
  - `monitor_arduino.py` and `arduino-console.py` show the Arduino's serial output.
  - `asciimatics-*.py`, `try-curses.py` and `with-thread.py` are terminal-UI experiments for that console.
- `michael-2023-12-04.rom`: a ROM image from 2023-12-04 (committed on michael_keyboard_wip).
- `michael_rom.bin` (not committed: built by `tools/michael_rom.py`): the current ROM, `firmware/boards/michael/michael_rom.s` as the firmware manifest records its build. Its loader takes uploads in format 3 (`tools/upload/transfer.py --format=3`) to zero page and anywhere from `$0200` to `$3EFF`, and it carries the LCD and keyboard services at `$F006`. `firmware/boards/michael/michael_rom.inc` names their entry points and says what RAM they use. See "Programming the ROM" below.

## Programming the ROM

The EEPROM is an AT28C256, programmed with a TL866-style programmer and `minipro`:

```
make -C hardware/michael program
```

It builds the image (`tools/michael_rom.py` builds `michael_rom.s` and checks it against the firmware manifest's hash, so it's the recorded build), backs up what's on the chip to `hardware/michael/backups/`, then writes the image. `make -C hardware/michael rom` only builds it. Add `MINIPRO_FLAGS=--no-write-protect` if the chip has software write protection on. To go back, write a backup with `minipro -p AT28C256 -w <backup>`.

After a reset, the LCD shows "Michael ROM 5" (4 before the FPGA bus's stage 4) and "Ready"; "Received" replaces "Ready" once data arrives. The ROM only understands format 3 uploads (`docs/michael-upload-format-3-plan.md`):

- `tools/upload/compile_and_upload_michael.sh <program.s>` assembles to S-records and sends them, so a program loads at its `.org` and starts at its `start` label, which every uploaded program needs. Programs that follow `base_config_v2.inc` load at `PROGRAM_LOAD_ADDRESS`, `$2000`.
- `tools/upload/transfer.py --baudrate=57600 --format=3 FILE` sends a flat binary to `$2000`, or elsewhere with `--load-address`. For example, `editor/bin/editor-michael-upload.sh` builds the editor and uploads it to `$0200`.
- An upload can also load zero page. Writing 0 where a program specified nothing is harmless, so the sender merges nearby pieces, with zeros between, to stay within the loader's 32 entries.

While an upload arrives, the first two rows show the entry ("Block") arriving, where its next byte will end up, and how many bytes have come in. They're redrawn about five times a second, so a stalled upload shows exactly where it stopped. When the upload is complete, the loader clears the screen and runs it. A bad upload leaves "Upload failed" and the reason on the screen, with the LED lit, until reset.
