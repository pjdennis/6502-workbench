# Plan: the Michael FPGA bus

Goal: turn the FPGA display interface ([`hardware/michael/fpga/spi-display/`](../hardware/michael/fpga/spi-display/))
into a small general-purpose bus between Michael and the Cmod A7's FPGA. The FPGA then provides devices that
Michael reaches through commands rather than dedicated VIA pins:

- the display, raw (as today) and as a **text mode** for the editor;
- later, storage (FPGA RAM, an SD card or the spare configuration flash), a serial port to the PC through the
  Cmod's USB, and more.

It uses one dedicated VIA pin, E. Two shared pins are sampled only when E rises: RS (PA5) and RW (PA6). They
are the LCD's own register select and read/write pins, and they mean the same here as on the LCD: RW chooses
a read or a write, and RS chooses commands and status (0) or data (1). The FPGA also watches the keyboard
board's output enable (SOEB, PA4), so a keyboard interrupt can safely pause a read.

E started on PA0. Stage 4 moved it to PA2 and the LED to PA1, which left PA0 free: the pins at that end of
the VIA are now the reusable ones. In the end the bus freed PA0, the display's chip select and reset (PA1 and
PA2 before the bus), and the backlight tie on the control buffer's B5.

**Status (2026-10-06): stages 0 to 5 done; stage 5 put the editor on the graphic display.** Stage 7, the
FPGA on the CPU bus with the bus's transfers as memory accesses, is proposed
([below](#7-the-fpga-on-the-cpu-bus-proposed-2026-10-07)). Stage 3 is text mode ([`hardware/michael/fpga/text/`](../hardware/michael/fpga/text/)); stage 4, the ROM's graphic
screen and the pin shuffle, is on the board ([below](#4-rom-support-and-switching-displays-at-run-time)).
Stage 0 is this document, reviewed. Stage 1 is
done (2026-10-03): the FPGA drives the data buffer's /OE and DIR, Michael is rewired, the read test
([`hardware/michael/fpga/bus-check/`](../hardware/michael/fpga/bus-check/)) passed on the board, with keyboard
interrupts pausing reads (the SOEB interlock) and every transfer accounted for, and the buffer stays off while
the FPGA is unconfigured. Stage 2 is done (2026-10-04): the [bus design](../hardware/michael/fpga/bus/) is in
the Cmod's flash, with the raw display commands and the debug port, and `graphics_display.inc` uses it. On the
board, the backlight's PWM made snow on the display until its edges were kept clear of the SPI bytes. In
review, reads came to use E with a shared pin instead of a dedicated PA1, a SOEB interlock came to let
interrupts pause a read, the shared pins (first F and G) were named RS and RW after their LCD meanings, and
stage 4 gained the pin shuffle. Michael's schematics, with the plan's wiring complete (stage 4's pin
shuffle included), are in [`hardware/michael/schematics/`](../hardware/michael/schematics/).

## Stages

Each stage leaves Michael working, is built test-first, and ends in a PR.

### 0. This specification
The protocol below is the contract that the FPGA design, the firmware and the emulator are tested against.

### 1. Hardware preparation, and proving reads
1. **FPGA first.** The spi-display design drives two new pins: the data buffer's /OE low and DIR low (Michael
   to FPGA). It's written to flash and works exactly as today, since the pins aren't connected yet.
2. **Rewire** ([Wiring changes](#wiring-changes)): the data buffer's /OE and DIR go to the FPGA, plus the pull
   resistors. PA4 (SOEB) and PA6 (RW) go to two of the control buffer's spare inputs, and the E pull-down is added. Doing it
   in this order keeps the display working throughout. Rewiring first would leave the data buffer disabled
   until the FPGA caught up. Nothing the current interface uses moves, so it keeps working until stage 2.
3. **Prove reads on the board.** A test design (an extension of
   [`input-check/`](../hardware/michael/fpga/input-check/)) implements `ECHO` and the read cycle. A Michael test
   program writes known patterns and reads them back. This settles the open toolchain's support for
   bidirectional (tri-state) pins and the bus turnaround on real hardware.
4. **Prove the SOEB interlock.** The same test reads thousands of bytes while a key is held down on the
   keyboard, so its repeated bytes interrupt reads at random points. Every read byte must be right and every
   keyboard byte must arrive. Also check, in nextpnr's timing report, that the interlock is a direct path from
   input pin to output pin.
5. **Check the safe default.** With the FPGA erased or held in configuration, Michael's port B must stay
   undriven:
   - `~/opt/fpga/oss-cad-suite/bin/openFPGALoader -b cmoda7_35t --bulk-erase` (or `openFPGALoader` after
     `source <kit>/env.sh`) empties the Cmod's flash, so after a power cycle the FPGA stays unconfigured;
   - the data buffer's /OE (pin 19) must then measure 3.3 V (off) and its DIR (pin 1) about 0 V;
   - `make -C hardware/michael/fpga/bus flash` puts the bus design back (before stage 2, the spi-display
     design: `make -C hardware/michael/fpga/spi-display flash`).

   Done on 2026-10-03: /OE at the 3.3 V rail, DIR at 0.014 V. But the "3.3 V" rail itself measured 4.07 V,
   above what the FPGA's inputs may see (VCCO + 0.55 V). The cause was found on 2026-10-04: 5 V had been fed
   into the 3.3 V rail by mistake. Rewired, it measures 3.297 V.

### 2. The new bus, with raw display access (the cutover)
- **FPGA:** a new design replacing spi-display, with:
  - the bus decoder and command dispatcher;
  - the control commands ([`$0x`](#control-0x));
  - the raw display commands ([`$1x`](#display-raw-1x));
  - the read path;
  - a **debug port**: the same transactions over the Cmod's USB serial port, so a PC can exercise every
    command without Michael, as the display probe does.
- **Firmware:**
  - `firmware/lib/fpga/fpga_bus.inc`: send a command, send data, read;
  - `graphics_display.inc`'s `gd_*` routines moved onto it, so every graphics program and BBC BASIC's
    graphics follow;
  - the firmware manifest refreshed.
- **On the board:** the graphics programs, plus an ID read. The old pin protocol (CSB and RSTB) is retired:
  the new FPGA design and the new driver go onto the board together. The keyboard driver doesn't change.

### 3. Text mode in the FPGA
- **The design:** a character grid and a font in block RAM, and a renderer that repaints changed cells in
  the background. It implements text mode's operations ([device `$80`](#text-mode-device-80)), which mirror the
  editor's screen calls one for one.
- **Testing:** first in simulation, with a display model that decodes the ILI9341 writes into a frame buffer
  and checks the characters drawn. Then on the board, driven from the PC through the debug port.
- **The grid's shape and font** should follow from the existing michael graphic display routines. The display
  is in portrait mode. We should derive the font information from the same source data, and add the font data
  generation for the existing display code and new FPGA display code to the build process.
- **Done (2026-10-04), in simulation and on the board through the debug port**
  ([`hardware/michael/fpga/text/`](../hardware/michael/fpga/text/)): the grid, the renderer, the text
  commands, and the windowed scrolling below. `board_check.py` reads the cells back out of the display's
  memory and finds them as the model has them. On the glass a region scrolled the right way between its
  fixed areas, but with flashes: the row that left showed for a moment where the new one comes in, and the
  cursor showed in rows it never reached. Fixed (below), and the clean scrolls confirmed on the glass
  (2026-10-05).
- **Look into the panel's windowed scrolling** to speed up the editor's scrolling. Done: scrolling the whole
  region (and inserting or deleting lines at its top row) moves its picture with VSCRDEF and VSCRSADD, and
  redraws only the rows that come in blank. The frame memory runs from the bottom row up (MADCTL's MY), so
  the top fixed area is the rows below the region, and VSCRSADD counts from there; the model panel
  ([`ili9341.py`](../hardware/michael/fpga/text/ili9341.py)) has this, checked against the graphic driver's
  own whole-screen scroll, which works on the board. Inserting or deleting lines below the region's top
  still redraws the rows that move, but only the cells that change: a blank moved onto a blank isn't drawn.
  - **Clean scrolls.** The display takes up a new VSCRSADD at its next frame (inferred from the flashes), and
    the rows coming in reuse the memory of the rows that leave. So before the grid moves its cells it asks the
    renderer, which draws what's dirty, takes the cursor off the glass and blanks the leaving rows; after
    sending the scroll it draws nothing for a frame (16.7 ms). The test model panel scans its glass frame by
    frame, and `test_text_render.py` checks that a scroll never shows a cell anything it doesn't hold
    before, between or after the operations.
  - The ILI9341's Vertical Scrolling Definition (`$33`: top fixed area, scroll area, bottom fixed area) and
    Vertical Scrolling Start Address (`$37`) scroll a band of the screen in hardware between fixed areas,
    with no redraw. The editor scrolls its text area and leaves the status line fixed, which is exactly
    that shape.
  - **Caveat: the hardware scroll runs along the panel's 320-line axis.** It moves text rows only when that
    axis is vertical (portrait), and the grid's orientation decides that. In landscape, region scrolls are
    redraws from the character grid: about 0.2 s for a full screen at today's 6 MHz SPI, less with a faster
    SPI clock from the Cmod's MMCM.
  - Arbitrary regions (`$28`) and inserting or deleting lines within them need the fixed areas set per region.
  - The 180° rotation (`GD_PANEL_SCAN`) reverses the scan, so the scroll direction needs checking against it.

### 4. ROM support, and switching displays at run time
- **Emulator:** a command-level model of the FPGA device in the Michael machine (a character grid), so the
  editor's differential tests (against `AnsiScreen`) also run against the graphic screen.
- **ROM:** graphic screen services behind the existing `scr_*` entries, `term_rows`/`term_cols` per display,
  and a new `SVC_SCREEN_SELECT` (LCD or graphic, kept in the ROM's spare RAM and reset to the LCD by the
  loader). ROM tests in the emulator.
- **Pin shuffle: E to PA2, the LED to PA1, PA0 free.** It goes with this stage's EEPROM programming because
  the ROM drives the LED: today's ROM sets the LED bit (PA2) high whenever it sets up the ports, and with
  port B an output. With E on PA2, that would start a read and the FPGA would drive port B against the VIA.
  So the firmware, the FPGA design, the ROM and the wiring change together:
  - firmware: `LED` becomes PA1 and E (`FPGA_E`) PA2 in `base_config_v2.inc`, and Michael's port set-up
    (`michael_ports.inc`) makes E an output, low, as it does the LCD's pins; every program is
    rebuilt and the firmware manifest refreshed. Comments that name PA2 for the LED (such as
    `michael_keyboard_scope.s`'s) follow;
  - firmware: the LED's polarity flips to active high, to match the rewired LED. `initialize_michael_ports`
    stops setting the LED bit to turn it off and clears it instead. Setting the bit kept the reversed LED dark
    and the display's reset released, and neither applies on PA1. `upload_v3.inc` already lights the LED by
    setting the bit, so a failed upload lights it again. Today it turns the reversed LED off. Test first: in the
    emulator, the LED pin is low after the ROM starts and high after a failed upload;
  - FPGA: E comes from Cmod pin 11, which the control buffer's B3 already carries from PA2, instead of pin 9.
    So E needs no new wire;
  - wiring ([Stage 4 wiring changes](#stage-4-wiring-changes)), with Michael powered off, then the EEPROM and
    the FPGA's flash programmed before powering on.
- **One EEPROM programming** (the programmer and `minipro` are ready on the bench):
  `make -C hardware/michael program` (it builds the image, backs up the chip, then writes it).
- **Done (2026-10-05), on the board.** ROM 5 is on the EEPROM (ROM 4 backed up), Michael is rewired and the
  stage 4 bus design is in the Cmod's flash. The bus check passed, keyboard interrupts included, as did
  `board_check.py`; the text demo, a graphics program, the graphic keyboard demo and the ROM's graphic screen
  (`tools/tests/michael/graphic_screen.s`) work on the glass. At the bench, port B's wires had worked loose
  (the low data bits read wrong) and were reseated, and `board_check.py` needs the panel initialised first,
  by a graphics program after a power cycle. In software:
  - The emulator models the FPGA at the level of its commands (`emulator/chips/fpga_bus.c`, `fpga_text.c`),
    checked against the text mode's model; `--no-fpga` leaves it out.
  - The ROM ("Michael ROM 5") has the graphic screen behind the screen calls (`michael_graphic_screen.inc`)
    and `SVC_SCREEN_SELECT`, tested on the emulator (`tools/tests/michael/graphic_*.s`).
  - The pin shuffle is in the firmware, the ROM, the emulator, the bus designs (`bus.mk`) and the schematics,
    which now show the board as this plan leaves it.
  - The editor's differential tests on the graphic screen need stage 5's launcher, which selects it.
- **On the bench**, in this order (done 2026-10-05):
  1. Program the new ROM (`make -C hardware/michael program`, which backs up the old one first).
  2. With Michael powered off, rewire ([the checklist](../hardware/michael/fpga/spi-display/WIRING.md#stage-4-rewiring-the-pin-shuffle)).
  3. Power on: the LCD shows "Michael ROM 5" and the LED stays dark. The flash still holds stage 2's bus
     design, which takes E from Cmod 9, now tied low, so it sees no transfers.
  4. With the Cmod on USB: `make -C hardware/michael/fpga/bus flash`, the design that takes E from Cmod 11.
  5. Check: `make -C hardware/michael/fpga/bus-check check` (reads and the interlock; power-cycle the Cmod
     after, to have the bus design back), a graphics program, `michael_graphic_text.s`, and
     `hardware/michael/fpga/text/board_check.py`.

### 5. The editor on the graphic display
- `editor/bin/editor-michael-upload.sh` chooses the screen: the 20x4 LCD as now, or with `--graphic` the
  graphic display, through a few-byte launcher that selects it and then starts the editor. The editor itself
  doesn't change: it reads its screen size at run time.
- The launcher also sets the scroll region to the editor's text rows (1-19), leaving the status bar outside
  it. The editor sets no region itself (it resets it only on exit), and its pairs of DL and IL still leave
  the same screen with a region set, but its view scrolls then start at the region's top: text mode's
  hardware scroll, with no editor change.
- Emulator tests in graphic mode, then on the board.
- **Done (2026-10-06), on the board:** `editor/michael_graphic_launcher.s` (in zero page, at $10: S-records can't
  start at 0) selects the graphic screen, starts the services and sets the region to rows 1-19, or does
  nothing more if there's no FPGA. `editor-michael.sh --graphic --web` runs it in the browser;
  `editor-michael-upload.sh --graphic` sends it to the board. `editor/tests/michael_tests.py`'s
  `MichaelGraphicEditorTest` checks the FPGA's grid and compares it with the console build at 20x20. It ran in
  the web emulator, then on the board, where a variety of editing worked as expected.

### 6. Later
Storage ([`$4x`](#reserved)): FPGA RAM first, then an SD card or the configuration flash's spare space (the
flash's clock goes through `STARTUPE2`, unproven with the open toolchain). Also a serial port to the PC, and an
FPGA interrupt on the VIA's CA1 (unused on Michael; input-only, so a 3.3 V FPGA pin can drive it directly).
Stage 7 would replace the CA1 idea with the CPU's IRQB, through an AND gate with the VIA's.

### 7. The FPGA on the CPU bus (proposed, 2026-10-07)
Move the FPGA from behind the VIA onto Michael's CPU bus, as a memory-mapped peripheral. The FPGA imitates a
hypothetical peripheral chip, beside the VIA, the RAM and the ROM: it has a chip select, register selects,
R/W, PHI2, RESB, a data bus, an IRQ output and a RDY output, and it knows nothing about the other chips. The
glue stays glue: the address decode and the combining of interrupts are gates on the board, not logic in the
FPGA. Not started; nothing in the stages above changes until its cutover.

**Why.** Every transfer today is several VIA accesses: port B's direction, RS and RW on port A, then E up and
down. On the CPU bus it is one access:

| Routine | Today | On the CPU bus |
|---|---|---|
| `fb_command`, `fb_data` | about 25 cycles | `sta`, 4 cycles (2 µs) |
| `fb_status`, `fb_read` | about 28 cycles | `lda`, 4 cycles |
| a fill loop's byte | 9 cycles (4.5 µs) | 4 cycles (2 µs), about the SPI's own rate |

A single `lda` or `sta` can't be split by an interrupt, so Michael's half of the
[interrupt handlers follow-up](#follow-ups) disappears: no port state to save, no RS, RW or port B direction
to disturb. The FPGA's half (an open command and the reply queue) remains, and option 2 there still applies.
The FPGA leaves port B and port A: PA2 (E) is free again, PA4, PA5 and PA6 are only the LCD's and the
keyboard board's, and the SOEB interlock is no longer needed, because the keyboard board never shares a bus
with the FPGA.

#### Address map
The FPGA takes **`$4000–$5FFF`**, which nothing uses today. The existing decode already nearly gives it:
`VIA/CS2` (U4B: NAND of A14 and /A15) is low for `$4000–$7FFF`, and the VIA is selected there when A13 is high.
So the FPGA is selected when `VIA/CS2` is low and A13 is low, and taps those two nets.

- **The VIA's chip select doesn't change.** The VIA stays at `$6000–$7FFF`, and the two windows never overlap.
- **Reads** of the window find only the FPGA: the RAM's /OE is A14, high there, and the ROM needs A15.
- **Writes** also land in the RAM's upper half, which can't be read (as for the VIA's window today): harmless.
- **PHI2 qualifies the select inside the FPGA,** as the VIA does through its own PHI2 pin. `VIA/CS2` isn't gated
  by PHI2.
- **Registers:** `$4000` writes a command and reads the status; `$4001` writes data and reads the reply queue.
  A0 takes RS's place and RWB RW's, so the protocol's four transfers are unchanged. With A0 to A2 decoded,
  the registers mirror every 8 bytes across the window, as the VIA's mirror every 16.
- The command layer ([`bus_control.v`](../hardware/michael/fpga/rtl/bus_control.v)) and every device are
  unchanged. Whether `ID`'s version moves to 3 for the new transport is to decide: nothing in the command
  layer differs.

#### Hardware
| Change | Why |
|---|---|
| Data buffer (U7): its B side from port B (PB0–PB7) to the **CPU's D0–D7**; its A side stays on Cmod pins 1–8 | The FPGA's data bus |
| U7 DIR (pin 1): from Cmod pin 17 to **RWB**; R16 (its pull-down) removed | The buffer turns with the CPU's own R/W. RWB changes only while PHI2 is low, when the buffer is off. Cmod pin 17 is freed |
| U7 /OE (pin 19): stays on Cmod pin 14 with R15's pull-up | On only while the FPGA is selected and PHI2 is high, reads and writes: on otherwise, it would drive the bus when the CPU reads RAM. Off while the FPGA is unconfigured |
| Control buffer (U8) B1–B8: **PHI2, RWB, `VIA/CS2`, A13, A0, A1, A2, RESB**, replacing PA2, PA5, PA4, PA6 and the ties (R12, R14, R17, R18, R9 removed) | The FPGA's inputs, all through a 5 V-tolerant '245 as today. A8 needs a Cmod pin (B8 has none today) |
| **74HCT08** (new) near the CPU: the VIA's IRQB and the FPGA's `irq_b` in, the CPU's IRQB out. The VIA's IRQB comes off the CPU's IRQB | The W65C22S drives IRQB both ways (only the W65C22N's is open-drain), so the two can't share a wire: active low, an AND is their OR. HCT, so 3.3 V is a valid high at its input, within spec, and it drives the CPU at 5 V |
| FPGA `irq_b` (a free Cmod pin) to the 74HCT08, with **10 kΩ to 3.3 V** | Unconfigured, the FPGA's pin floats and the pull-up keeps its input inactive, so the VIA's (the keyboard's) interrupts work without the FPGA |
| FPGA `rdy_b` (a free Cmod pin) to the CPU's **RDY**, open-drain (driven low or left floating); **R2's pull-up from +5V to 3.3 V** | Wait states ([7.4](#74-rdy-flow-control-optional)). The W65C02S drives RDY low itself (WAI), so nothing may drive it high. With the pull-up at 3.3 V the FPGA's pin never sees more than its supply. Out of spec: see the next row |
| None: the FPGA's 3.3 V reaches the CPU on the data bus (reads) and RDY | The W65C02S asks for 0.8 × VDD and in practice switches at about 0.5 × VDD: accepted out of spec ([Michael's README](../hardware/michael/README.md#known-departures-from-the-data-sheets)) |

Cmod pins 9–13, 18 and 19 carry U8's A side as now (renamed); `irq_b`, `rdy_b` and U8's A8 need three free
Cmod pins, to choose (33–37 stay reserved for the touch controller). The 74HCT08's three spare gates are for
later (an NMI source, say). The schematics (`michael_schematic.py`, checked by `test_michael_schematic.py`),
[`WIRING.md`](../hardware/michael/fpga/spi-display/WIRING.md) and `michael-fpga-display.svg` follow.

#### The FPGA's bus front end
A new `rtl/cpu_bus.v` replaces [`michael_bus.v`](../hardware/michael/fpga/rtl/michael_bus.v), with the same
interface to `bus_control.v` (`wr`, `wr_rs`, `wr_data`, `rd`, `rd_end`, `rd_rs`, `reply_byte`, `status_byte`),
so the debug port and the command layer don't change.

**PHI2 is a signal, not a clock** (decided 2026-10-07). As a clock it would sample where the CPU does, with no
synchronisers. But:
- a glitch on it would be a clock edge, and so a spurious bus cycle; E needed a filter on this board
  (stage 1), and a clock can't be filtered in logic;
- the Artix-7's MMCM won't take a 2 MHz input (it needs about 10 MHz or more), so the domain would be PHI2 as
  it comes;
- the rest of the design would sit across a clock crossing, with the debug port a second writer on the far
  side;
- the open toolchain has no input-delay timing checks (the repo has no clock constraints at all), so the
  timing would be proved only on the bench.

Instead the design runs on **one fast clock from the MMCM**, 96 MHz (12 MHz × 64 ÷ 8) as the target, 48 MHz if
the text renderer doesn't close timing there. The whole design moves to it, not just the front end, so there
is no crossing: the 12 MHz-derived parameters (the UART's divider, the cursor's blink, the activity LEDs, the
SPI's divider) scale with it. That also gives the [faster SPI clock](#follow-ups).

**Writes: a history of samples.** The CPU's write data is stable from shortly after PHI2 rises until about 10
ns after it falls. That is a window of about 200 ns at 2 MHz, of which only the end is short. So:

```
PHI2   ____/‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾\______
D      xxxxxxx<========== stable ==========>xxx
samples  |  |  |  |  |  |  |  |  |  |  |  |  |     every 10.4 ns at 96 MHz
                                  ^            ^
                     taken from here           the fall seen here
```

1. D, A0, RWB, the select and PHI2 go through synchronisers of equal depth, so samples of one clock line up.
2. A shift register keeps the last few samples of D, A0 and RWB (4 to 6 deep).
3. When the synchronised, filtered PHI2 falls, take D, A0 and RWB from k samples earlier, about 30 ns before
   the fall (k about 3, plus the filter's delay), far from both ends of the window.

Only PHI2 can be caught changing, and its synchroniser settles it. The ±1 sample of uncertainty in when the fall
is seen is absorbed by looking back k samples. D is never sampled while it changes. This doesn't depend on
the CPU's speed, as long as PHI2's high phase lasts several samples. PHI2's glitch filter must be short, a few
samples (about 30 ns): E's 250 ns would swallow PHI2's whole 250 ns high phase. `michael_bus.v`'s `d_at_e`
(D as E first went high) is the same idea; here it's D before PHI2 fell. At 12 MHz this would be marginal (two
samples back is 83 to 166 ns before the fall). Fallback if the board shows skew: a 74LVC573 on U7's A side,
latched by PHI2, holding the byte through PHI2's low phase.

**Reads.** The address, RWB and the select are valid from shortly after PHI2 falls, so the front end decodes
them into registers during PHI2's low phase. It drives D from them: the reply queue's head for A0 1, the status
for A0 0. U7's /OE is the registered select gated by the PHI2 pin with no clock in the path, as the SOEB
interlock is today, so the buffer turns off within about 10–15 ns of PHI2 falling. That is after the CPU's
read hold time and long before anything else drives the bus. The reply queue moves on (`rd_end`) only after
the fall, so the byte on the bus never changes while it is read. The FPGA drives its D pins only during a
selected read cycle, when U7 points from the FPGA to the CPU.

**RESB** resets the front end and the command layer, as `RESET` does (the queues and the status), as a
peripheral chip's reset pin would. The display is left as it is.

**What goes:** E's 250 ns filter, the turnaround states, `paused` and the SOEB interlock.

#### Software
- **`fpga_bus.inc`** keeps its entry points. `fb_command` becomes `sta FB_COMMAND` (`$4000`), `fb_data`
  `sta FB_DATA` (`$4001`), `fb_status` `lda FB_STATUS` and `fb_read` `lda FB_REPLY`, each still keeping A, X,
  Y and the flags as documented. `fb_initialize` sends `RESET`.
- `FPGA_E` leaves `base_config_v2.inc` and `initialize_michael_ports`: PA2 and PA0 are free.
- `graphics_display.inc`'s fill loops and `gd_send_x2` can store straight to `FB_DATA`, a byte every 4 cycles.
- **The ROM changes** (its graphic screen and launcher use the bus), so a new ROM is programmed with the
  rewiring, as in stage 4. The firmware manifest is refreshed.
- **The rules for Michael's software** lose E, RS and RW and gain one: **a read has a side effect** (it takes
  the reply queue's next byte, or clears the status's sticky bits). So no read-modify-write instructions
  (`inc`, `asl`, `tsb`, `trb` and the like) on the FPGA's registers, and no addressing modes whose extra
  cycles may read a register's address. Plain `lda`, `sta`, `stz` absolute only.

#### Emulator
`fpga_bus.c` leaves the VIA's pins and joins the CPU's bus at `$4000–$5FFF`, decoded by `glue_michael.c`. Its
`--fpga-log` lines (`C`, `D`, `R`, `S`) stay the same, so the driver test's expectations stay too. Its IRQ
output goes through the board's AND with the VIA's, and RDY holds the CPU. `--no-fpga` leaves the window
empty: reads find a floating bus.

#### Stages
Each leaves Michael working, is built test-first, and ends in a PR.

##### 7.1 In software
Tests first, then the code, all without the board:
- **The front end in simulation.** A testbench that drives PHI2 at random phases against the fast clock, with
  a few ns of skew between PHI2 and D each way, and D invalid outside the data sheet's window, so a wrong
  sample shows as a wrong byte. Every write arrives with its byte, A0 and RWB; a PHI2 glitch shorter than the
  filter makes no transfer; reads drive the byte through PHI2's high phase and release the bus within 15 ns
  of the fall; the buffer is never on while the CPU reads anything else. `michael_board.vh` and
  `michael_fpga_bus.vh` become a CPU bus model (address, RWB, PHI2 and the cycle timings of `fpga_bus.inc`),
  keeping the no-two-drivers checks.
- **The whole design on the fast clock:** `tb_top.v` and the text mode's testbenches still pass with the scaled
  parameters; nextpnr's report shows the clock met.
- **The emulator, the driver and the firmware:** `test_michael_fpga_bus_driver.py`, `test_michael_pins.py` (PA2
  and PA0 free, the LED unchanged), the ROM's tests on the graphic screen, and the editor's graphic tests.
- **The schematics:** `test_michael_schematic.py` against the new nets.

##### 7.2 The cutover, on the bench
As stage 4, all at once, with Michael powered off: program the new ROM (`make -C hardware/michael program`),
rewire (the hardware table, including the 74HCT08 and RDY's pull-up), then flash the new design. Then:
1. **The safe default first:** with the Cmod's flash erased, Michael boots, the LCD and the keyboard work
   (interrupts through the AND gate), U7's /OE measures 3.3 V, and a read of `$4000` finds a floating bus.
2. **Writes only:** a check design that only listens (U7 on for selected writes, never driving) reports the
   bytes Michael writes to `$4000–$5FFF` over USB serial. It proves the sampling on the board before the FPGA
   ever drives the CPU's bus.
3. **Reads:** `bus-check` rebuilt for the CPU bus: `ECHO` patterns read back, with keyboard typing alongside
   (it no longer shares anything, which is the point of checking).
4. The graphics programs, `board_check.py`, the ROM's graphic screen and the editor on the graphic display.

##### 7.3 The FPGA's interrupt
The 74HCT08 is wired at the cutover, with `irq_b` held high. Then: an interrupt status bit (bit 6 is free), an
enable command, and the first sources (the reply queue not empty; later serial input, storage). As with a real
chip, the handler asks each chip in turn: the VIA's IFR, then the FPGA's status. This replaces stage 6's idea of
an interrupt on the VIA's CA1.

##### 7.4 RDY flow control (optional)
The W65C02S's RDY halts it on any cycle, writes included. So the FPGA could hold RDY low while its command queue
is nearly full, and programs would never need to poll `BUSY`. The catch: a halted CPU takes no interrupts, so
the keyboard's bytes could be lost in a long stall (a full-screen redraw is about 0.2 s at today's SPI clock).
Measure first; stall only briefly, if at all.

#### To confirm
- The W65C02S's AC timings at 5 V (write data delay and hold, address delay, read setup and hold, RDY's setup),
  from the data sheet's tables, against the sample window above.
- The three free Cmod pins.
- That the text renderer closes timing at 96 MHz with the open toolchain, or settle on 48 MHz.

### Follow-ups
Found in the review of stages 1 and 2 (2026-10-04). None changes what runs on Michael today.

- **`OVERFLOW` for the serial queue.** `SERIAL_SEND`'s bytes beyond the 2048-byte serial queue are dropped
  without setting `OVERFLOW`, though [its definition](#commands) covers the queues a transaction fills.
  Set it for a `SERIAL_SEND` byte that is dropped, whoever sent it: Michael, or the PC through the debug
  port, since either can read the status. The FPGA's own use of the serial port must never set it, and
  needn't, since nothing of its own is dropped: the debug port's answers wait for room (`out_ready` in
  [`top.v`](../hardware/michael/fpga/bus/rtl/top.v)), and bus-check's counts line starts only once the
  queue is empty. Test first in `bus/sim/tb_top.v`. The bitstream changes, so it needs a board run and a
  flash.
- **One serial output module.** [`bus/rtl/top.v`](../hardware/michael/fpga/bus/rtl/top.v) and
  [`bus-check/rtl/bus_check.v`](../hardware/michael/fpga/bus-check/rtl/bus_check.v) build the same serial
  output (a FIFO into `uart_tx`, busy while either has work). A shared `rtl/serial_out.v` would hold it,
  with the full flag the item above needs. The activity LEDs' pulse stretchers are repeated in three designs
  too.
- **Faster fills and pixels.** The fill loop (`send_zero_data` in
  [`graphics_display.inc`](../firmware/lib/graphics/graphics_display.inc)) was slowed on purpose for the old
  interface board: `sta PORTA,Y` with Y = 0 spends one cycle more than `sta PORTA`, so a byte goes every 9
  cycles (4.5 µs) instead of 8, with E low for 2.5 µs instead of 2. Its only purpose is that cycle: the old
  board's first test program, `hello_michael_spi.s` (2022-09-16), has the same `sta PORTA,Y`, with a `nop`
  commented out beside it. The bus needs only 250 ns of E high and low, and drains a byte in about 1.4 µs, so:
  - `sta PORTA` in the fill loop: 8 cycles a byte, fills about 11% faster;
  - `gd_send_x2` (every character's pixels) strobes with `tsb`/`trb`, 12 cycles a byte; the fill loop's
    `sta`/`stx` would take 8;
  - far more: a fill command in the FPGA (in the reserved `$14`–`$1F`), so that a rectangle of one colour is
    a few bytes from Michael, not two per pixel.

  Each changes the graphics programs' timing, so each needs a board run.
- **Sharing the serial port between Michael and the debug port.** Michael's `SERIAL_SEND` bytes and the
  debug port's answers go out of the one USB serial port, mixed (an answer can be split by Michael's bytes).
  Plan a clean path by default, Michael's bytes only, as they are sent, and, only while debugging, a
  multiplexed one, which a host tool splits back into Michael's stream and the debug port's. Either would be
  chosen from the PC. Candidates: the modems' GSM 07.10 multiplexer (CMUX), which carries several virtual
  serial channels over one UART and has existing host-side drivers, or a simple framing of our own (an
  escape byte with a channel number, or SLIP or COBS frames). Decide when stage 6's serial port to the PC is
  designed.
- **Interrupt handlers on the bus.** With more peripherals, interrupt handlers will want to use the bus
  without upsetting what the main thread is doing. Today nothing does (the keyboard's handler never touches
  the bus), and a handler that did could break two kinds of state: Michael's (`fb_write` sets RS, port B and
  E in turn, so a handler between them changes port A's RS and RW and port B's direction) and the FPGA's
  (the open command, its arguments left, and the reply queue, where a handler's reply would interleave with
  a multi-byte reply the main thread is reading). A stream has no end marker: the next command ends it.
  Options, simplest first:
  1. **Handlers stay off the bus.** They note what happened (a flag, a byte in a buffer) and the main loop
     does the bus work: the usual embedded practice (deferred work, a "bottom half"), and the keyboard's way.
  2. **Atomic transactions, with resumable streams (recommended).** As drivers share an I²C or SPI bus: each
     transaction (a command and its arguments, a byte of a stream, or a command and the read of its reply)
     runs with interrupts off, so a handler runs only between transactions and may use the bus freely. The
     bus driver keeps the open stream's command in RAM; a handler that used the bus marks it closed, and the
     main thread's next stream byte sends the command again first, then carries on. Every stream resumes so:
     PUT at the grid's cursor, DISP_DATA in the display's write, SERIAL_SEND's bytes. It's the ROM's
     `ROM_PUTTING` ([`michael_graphic_screen.inc`](../firmware/boards/michael/michael_graphic_screen.inc))
     generalised into [`fpga_bus.inc`](../firmware/lib/fpga/fpga_bus.inc). No protocol change; interrupt
     latency grows by at most one transaction. Handlers still save and restore the port state they change.
  3. **Contexts in the FPGA,** if a handler ever needs to stream in the middle of the main thread's streams:
     two complete sets of parser state (main and interrupt), each with its own command, arguments left and
     reply queue, and a command (`CONTEXT n`) switching between them, leaving the other untouched. The
     precedents are banked registers (the Z80's alternate set, the ARM's FIQ registers), multiplexed channels
     (CMUX, above) and USB endpoints. One level is enough, as 6502 IRQ handlers don't nest (keep NMI off the
     bus). Handlers still save and restore Michael's port state.

  Decide with stage 6's peripherals; option 2 is the default either way.
- **Revisit text mode's control codes.** `PUT` acts on BS, LF and CR and drops the other codes below `$20`,
  while every code from `$20` up shows its glyph, so 32 of the font's glyphs (code page 437's ☺ … ▼) can't be
  shown. One option: no special meaning for any code, so every character written goes into its cell, with
  separate text mode operations for backspace, newline and carriage return. Undecided (2026-10-05).
- **The Cmod's RGB LED off.** It lights constantly with the bus design, meaning nothing. Its pins (B17 blue,
  B16 green, C17 red, active low) aren't driven by the designs here. Drive them high (off) in every
  design, as the toolchain kit's `bram_check` does, unless one is given a meaning.
- **A version for the FPGA design.** `ID` gives the protocol's version and capabilities, but nothing says which
  build of a design is loaded. Both the stage 2 snow fix and the review's clean-ups went into flash with `ID`
  unchanged. Add a design version that changes with every change to a design, readable by Michael and
  through the debug port (`debug.py id`). To decide:
  - **the format and size:** e.g. a minor number beside the protocol version, or major and minor, or a build
    number;
  - **where it's reported:** more bytes in `ID`'s reply (programs read only the first four today), or a
    command of its own (`$02` is free);
  - **how it's set:** by hand when a design changes, or at build time from git (a commit count or short
    hash), which can't be forgotten.

  While changing `ID`'s reply in [`bus_control.v`](../hardware/michael/fpga/rtl/bus_control.v), comment
  that `'M'`, `'B'` stands for "Michael Bus". It was left out of the review's clean-ups, because any edit
  there moves the placement away from the build in flash.
- **A faster SPI clock.** The display's SPI runs at 6 MHz (the 12 MHz clock halved), so a character cell's
  395 bytes take 0.5 ms and a full 20 by 20 screen 0.2 s: every redraw the hardware scroll can't save
  (inserting or deleting lines mid-screen, changing the region) runs at that rate. The Cmod's MMCM can make a
  faster clock: SCK at 12, 24 or more MHz. The ILI9341's data sheet gives a 100 ns write cycle (10 MHz), but
  these panels commonly run much faster. Find the board's safe limit with `board_check.py` (it reads every
  cell back) and the held-key brightness and snow checks, with the backlight PWM at several levels. Watch the
  timing of the design's other logic at the higher clock, or keep it at 12 MHz with the SPI shifter alone in
  the fast domain. Needs a board run and a flash.
- **The backlight off until the display is ready.** The FPGA starts with the backlight fully on
  ([`display_spi.v`](../hardware/michael/fpga/rtl/display_spi.v): brightness 255), so at power-up, and after
  every display reset, the panel glows plain white until a program has initialised it. Instead: start with
  it off, turn it off again with `DISP_RESET`'s reset (so a program's start-up hides the panel's noise too),
  and have the display's start-up (`ili9341_start.inc`, which the graphics driver and the ROM's graphic screen
  share) turn it on once the panel shows its first picture. The brightness program and anything else that sets
  a level keep doing so. Tests first: `display_spi.v`'s simulation (off at start and after a reset) and the
  firmware's bus logs (the backlight on after the start-up commands). The bitstream changes, so it needs a
  board run and a flash.
- **A minor version for the ROM.** The LCD shows "Michael ROM 5", the major version only; the review
  of stage 4 changed ROM 5 several times before it was programmed. As with the FPGA design's version: a minor
  number (e.g. "Michael ROM 5.1"), set by hand or from git at build time, and perhaps readable by programs.
- **The LCD beside the graphic display.** With the editor on the graphic display, Michael's 20x4 LCD is
  free: the editor, or the ROM's services, could show useful information there (the file and position,
  memory, diagnostics such as the bus's status or the keyboard's errors).
- **The ROM's busy flags in zero page.** `ROM_SCREEN` (read by every screen call's dispatch) and
  `ROM_PUTTING` (by every character) are in the interrupt page's RAM; in zero page each read and write is a
  cycle and a byte shorter, about 2 cycles of a character's 75 or so through the graphic screen. The strategy
  is there already: the top of zero page, `$F0`–`$FF`, is the ROM's (the keyboard's state, scratch,
  `ROM_FLAGS`; `$FD`–`$FF` free), and programs that use its services keep out. But the editor clears all of
  zero page as it starts, after a launcher may have chosen the graphic screen, so first:
- **The editor clears only its own zero page.** Its start-up zeroes `$00`–`$FF`; it should clear only the
  variables it owns (its memory map), leaving the ROM's `$F0`–`$FF`. Then `ROM_SCREEN` and `ROM_PUTTING`
  can move to `$FD` and `$FE` (`ROM_PUTTING` could move now: cleared, it only costs a PUT reopened).
- **One assemble-and-run helper for the Michael emulator tests.** `tools/tests/test_michael_keyboard.py` and
  `test_michael_display_orientation.py` have their own copies of what
  [`tools/tests/michael_emulator.py`](../tools/tests/michael_emulator.py) does.

## Wiring changes

Done in stage 1, after the FPGA drives the new pins ([`WIRING.md`](../hardware/michael/fpga/spi-display/WIRING.md)
is updated to match).

| Change | Why |
|---|---|
| Data buffer (upper 74LVC245): /OE (pin 19) from ground to **Cmod pin 14**, with **10 kΩ to 3.3 V** | The FPGA enables the buffer. The pull-up keeps it off whenever the FPGA isn't configured or isn't powered. |
| Data buffer: DIR (pin 1) from ground to **Cmod pin 17**, with **10 kΩ to ground** | The FPGA turns the bus around for reads. Michael to FPGA by default. |
| Control buffer B6 (pin 13): its 10 kΩ tie replaced by **PA4** (VIA pin 6), and A6 (pin 7) to **Cmod pin 18** | SOEB, for the interlock |
| Control buffer B7 (pin 12): its 10 kΩ tie replaced by **PA6** (VIA pin 8), and A7 (pin 8) to **Cmod pin 19** | RW |
| Control buffer B2 (PA1) | Used as CSB by the current interface until the stage 2 cutover, then unused, so PA1 is free. Can stay wired. |
| Control buffer B1 (PA0, E): **10 kΩ to ground** | No stray strobes while the VIA pins are inputs after a reset. It's the only bias Michael's side needs: without an E edge, nothing else matters. |
| Control buffer B3 (PA2) | Unused by the FPGA from stage 2 (PA2 is only the LED) until stage 4 makes it E. Stays wired. |
| Control buffer B5 (backlight tie) | Unused from stage 2 (the backlight is a command). Can stay as a tie. |

### Stage 4 wiring changes

| Change | Why |
|---|---|
| The LED and its resistor: from PA2 (VIA pin 4) to **PA1** (VIA pin 3), the right way round (PA1, resistor, LED, ground) | The LED is reversed today because it shares PA2 with the display's reset, which idles high. Alone on PA1 it lights when the pin is high, as the ROM expects. |
| Control buffer B3 (PA2): **10 kΩ to ground** | E's pull-down, now on PA2 |
| Control buffer B1: the wire from **PA0** removed; its 10 kΩ to ground stays, as a tie | PA0 is free |
| Control buffer B2: the wire from **PA1** removed, and **10 kΩ to ground** | PA1 is only the LED's. B2 isn't left floating. |

The VIA reads 2.0 V as high on every input at 5 V ([W65C22 datasheet](https://www.westerndesigncenter.com/documentation/w65c22.pdf),
DC characteristics), so the data buffer's 3.3 V outputs are valid highs on port B.

# The protocol (version 2)

## Signals

| Signal | VIA pin | Direction | Use |
|---|---|---|---|
| D0–D7 | PB0–PB7 | both | data; the FPGA drives them only during a read |
| E | PA0, PA2 from stage 4 | to the FPGA | the strobe: each rising edge starts one transfer. Dedicated to the bus; idle low |
| RS | PA5 | to the FPGA | register select, sampled when E rises: 0 for commands and status, 1 for data. Shared with the LCD's RS and the keyboard's START/ACK |
| RW | PA6 | to the FPGA | read/write, sampled when E rises: 1 to read. Shared with the LCD's R/W and the keyboard's PARITY |
| SOEB | PA4 | to the FPGA | the keyboard board's output enable (active low), watched for the [interlock](#the-soeb-interlock) |

The shared pins are harmless to their other users. The LCD only looks at RS and R/W while its own E (PA7)
strobes; the keyboard driver's interrupt saves and restores port A. And RS and RW only matter at the instant
E rises. E's rising edge chooses the transfer, as the same two pins do for the LCD:

| RW | RS | Transfer |
|---|---|---|
| 0 | 0 | write a command byte |
| 0 | 1 | write a data byte |
| 1 | 1 | read the next byte of the reply queue |
| 1 | 0 | read the status byte (the reply queue is left alone) |

## Writing a byte
1. Port B is an output, holding the byte. RW is 0 and RS is set, by an instruction before the one that raises E.
2. Raise E, then lower it.

The FPGA takes port B, RS and RW at E's rising edge. They must be stable from before E rises until at least
0.5 µs after, and E must stay high, then low, for at least 0.5 µs each. The FPGA filters E: a level counts
only once it has held for 250 ns, so glitches on the line (seen on the board in stage 1) can't make transfers.
At 2 MHz every instruction takes at least 1 µs, so `tsb`/`trb` on E (as `gd_send_data` does) and `sta
PORTA,Y`/`stx PORTA` (as the fill loops do) meet this.

The FPGA accepts a byte every 2 µs indefinitely. Faster bursts go into a 512-byte command queue. Michael's
fastest loop sends a byte every 4.5 µs.

## Reading a byte
1. Port B is an input. RW is 1, and RS is 1 for the reply queue or 0 for the status byte, set by an instruction
   before the one that raises E.
2. Raise E. Within 1 µs the FPGA turns the bus around and drives the byte.
3. Read port B, at least 1 µs after raising E (`fpga_bus.inc` reads it 2 µs after).
4. Lower E. The FPGA releases the bus within 1 µs, and for a reply-queue read moves to the next byte.

Don't make port B an output again until 1 µs after lowering E; `fb_read` returns later than that. A byte takes
about 6 µs (`tsb`, `lda`, `trb`).

Reading with an empty reply queue gives `$00` and sets the `UNDERFLOW` status bit. Replies are queued in
the order of the commands that asked for them. With the FPGA unconfigured, the data buffer stays off and a
read gives whatever port B floats to. That's why software checks for the FPGA with [`ID`](#control-0x).

### The SOEB interlock
The keyboard interrupt can arrive mid-read. It then enables the keyboard board's shift register onto port B
(SOEB low) while the FPGA is driving it. So the FPGA drives the data buffer only while a read is active **and**
SOEB is high. That gating is logic from the input pin straight to the data buffer's /OE pin, with no clock, so
the buffer turns off within about 10–15 ns of SOEB falling. That's as fast as the keyboard board's 74HC595s
turn on.

E stays high through the interrupt, so the byte isn't consumed. When the interrupt raises SOEB again, the byte
is back on port B within about 20 ns, long before `rti` finishes. Reads therefore need no `sei`/`cli`, and the
keyboard driver needs no change. The interlock also means no software mistake can make the FPGA and the
keyboard board drive port B at once.

## Commands
- **A byte with RS = 0 is a command.** It always starts a new command, abandoning any unfinished one. That
  makes the bus self-synchronising: if Michael resets mid-command, the next command puts the FPGA right.
- **Bytes with RS = 1 are data:** first the command's fixed arguments, then, for streaming commands, any
  number of data bytes until the next command.
- Extra data after a non-streaming command's arguments is ignored.
- **Commands `$00`–`$7F` are one byte; `$80`–`$FF` are long-form devices.** A device's command byte is
  followed by an operation, as its first data byte, then the operation's arguments and data. So there are 128
  devices of up to 256 operations each, and a device's operations are numbered on their own. The busy paths
  keep one-byte commands (the raw display); new peripherals become devices. An unknown operation sets
  `UNKNOWN`, and a command before the operation `ABANDONED`. Version 2 of the protocol made text mode
  (`$20`–`$30` in version 1) the first device.

Errors don't stop anything. They set sticky bits that the status read (RW = 1, RS = 0) reports and clears:

| Bit | Name | Set when |
|---|---|---|
| 0 | `ABANDONED` | a command arrived before the previous one's arguments were complete |
| 1 | `UNKNOWN` | an unknown command (its data is then ignored) |
| 2 | `EXTRA` | data after a non-streaming command's arguments |
| 3 | `UNDERFLOW` | a read with the reply queue empty |
| 4 | `OVERFLOW` | the command queue or the reply queue overflowed (the serial queue too: a [follow-up](#follow-ups)) |
| 7 | `BUSY` | (not sticky) the FPGA is still working through queued commands |

## Command map

One-byte commands are grouped by their high nibble; each long-form device has a section of its own.
Arguments are listed in order; all are data (RS = 1) bytes.

### Control (`$0x`)

| Code | Name | Arguments | Data | Effect |
|---|---|---|---|---|
| `$00` | `NOP` | — | — | Nothing. Safe as padding or a resync |
| `$01` | `ID` | — | — | Replies 4 bytes: `'M'`, `'B'` ("Michael Bus", a signature: the bus design is answering, not a floating port B), the protocol version (2), and a capabilities byte (bit 0 raw display, bit 1 text mode, bit 2 storage) |
| `$03` | `RESET` | — | — | Empties both queues and clears the status. The display is left as it is |
| `$04` | `ECHO` | — | streams | Each data byte is added to the reply queue: a loopback for testing reads |

### Display, raw (`$1x`)

For drawing pixels, as `graphics_display.inc` does today. The FPGA drives the display's CS itself.

| Code | Name | Arguments | Data | Effect |
|---|---|---|---|---|
| `$10` | `DISP_RESET` | level | — | The display's RESET line: 0 = held in reset, 1 = released |
| `$11` | `DISP_COMMAND` | ILI9341 command | streams | Sends the command with DC low, then each data byte with DC high (its parameters, or pixels after `RAMWR`) |
| `$12` | `DISP_DATA` | — | streams | Sends each data byte with DC high, continuing a previous `DISP_COMMAND` |
| `$13` | `BACKLIGHT` | level | — | Backlight brightness: 0 off to 255 full, by PWM |

The driver maps onto these directly:
- `gd_reset`: `DISP_RESET 0`, wait, `DISP_RESET 1`;
- `gd_send_command`: `DISP_COMMAND` with the command byte;
- `gd_send_data` and the fill loops: data bytes, unchanged in speed;
- `gd_select`/`gd_unselect`: nothing to do.

In text mode `DISP_COMMAND` and `DISP_DATA` are ignored, and set `UNKNOWN`; `DISP_RESET` ends text mode.

### Text mode (device `$80`)

Settled in stage 3 ([`rtl/text_grid.v`](../hardware/michael/fpga/rtl/text_grid.v),
[`rtl/text_render.v`](../hardware/michael/fpga/rtl/text_render.v)). They mirror the editor's screen calls
(`asm/17/environment.asm`, `scr_*`), so the ROM's graphic services are a thin translation, and they behave as
the ROM's screen on the LCD does ([`lcd_screen.inc`](../firmware/lib/lcd/lcd_screen.inc)), so the editor sees
the same screen on either display. The model they're tested against is
[`text/text_screen.py`](../hardware/michael/fpga/text/text_screen.py), itself checked against `lcd_screen.inc`.
Each operation is the device byte `$80` (RS = 0), then the operation and its arguments: `GOTO` 3, 4 is `$80`,
then data `$02`, `$03`, `$04`. A `PUT` stream sends `$80`, `$03` once, then a byte per character.

- **The grid** is 20 rows of 20 characters, 12 by 16 pixels from Michael's font
  ([`font_12x16.txt`](../firmware/lib/graphics/font_12x16.txt), generated from the original C font), white on
  black, in the portrait orientation Michael's driver uses. Rows and columns are 0-based.
- **Writing** (`PUT`) puts a character at the cursor and moves right, to the start of the next row after the
  last column. On the bottom row the cursor stays past the last column, and characters written there are
  dropped, so writing never scrolls. BS moves left, CR to the first column, LF to the first column of the next
  row (staying on the bottom row); other control codes are dropped. Every other code shows its glyph from the
  C font, in code page 437's order: `$7F` a house, then accented, shaded and line-drawing characters.
- **`GOTO`** past the last row goes to the last; past the last column, just past it.
- **Counts of 0 do nothing.** Counts larger than the cells or rows there are clear them all.
- **`REGION`** needs two rows or more (a smaller one is ignored), and homes the cursor, as does
  `REGION_RESET`. `INSERT_LINES` and `DELETE_LINES` work from the cursor's row to the region's bottom, only
  when the cursor is in the region, and move it to the row's first column.
- **`TEXT_ON`** hides the cursor, sets normal video and the whole screen as the region, clears the grid and
  homes the cursor. It sets the display's orientation (MADCTL `$A8`) and hardware scroll (0), and draws every
  cell; the display must already be initialised (as `gd_prepare_vertical` does).
- **Between `TEXT_ON` and `TEXT_OFF`**, the raw display commands `DISP_COMMAND` and `DISP_DATA` are refused
  (`UNKNOWN`): the renderer has the display. `BACKLIGHT` still works. `DISP_RESET` ends text mode, as a reset
  loses the orientation, the scroll and the picture the renderer keeps: so a graphics program, which starts by
  resetting the display, has it after a text one. The renderer stops at once (after the cell it's drawing), so
  nothing of its reaches the display after the reset.
- **The cursor** inverts the bottom two pixel rows of its cell, as Michael's graphic cursor does, blinking
  every 250 ms and shown at once when it moves.
- **Reverse video** inverts a cell, and is kept per cell.
- Text operations queue (512 deep, `OVERFLOW` beyond), and the renderer redraws the cells that changed, a cell
  at a time; `BUSY` is set until it has caught up.

| Operation | Name | Arguments | Data | Mirrors |
|---|---|---|---|---|
| `$00` | `TEXT_ON` | — | — | Enter text mode: clear the grid and draw it |
| `$01` | `TEXT_OFF` | — | — | Back to raw mode (`DISP_RESET` also ends text mode) |
| `$02` | `GOTO` | row, column | — | `scr_goto` |
| `$03` | `PUT` | — | streams | `write_b`: characters at the cursor, advancing |
| `$04` | `CLEAR` | — | — | `scr_clear` |
| `$05` | `CLEAR_EOL` | — | — | `scr_clear_eol` |
| `$06` | `INSERT` | count | — | `scr_insert` |
| `$07` | `DELETE` | count | — | `scr_delete` |
| `$08` | `REGION` | top, bottom | — | `scr_region` |
| `$09` | `REGION_RESET` | — | — | `scr_region_reset` |
| `$0A` | `SCROLL_UP` | count | — | `scr_scroll_up` |
| `$0B` | `SCROLL_DOWN` | count | — | `scr_scroll_down` |
| `$0C` | `INSERT_LINES` | count | — | `scr_insert_lines` |
| `$0D` | `DELETE_LINES` | count | — | `scr_delete_lines` |
| `$0E` | `CURSOR` | 0 off, 1 on | — | `scr_cursor_off`/`scr_cursor_on` |
| `$0F` | `VIDEO` | 0 normal, 1 reverse | — | `scr_normal`/`scr_reverse` |
| `$10` | `GEOMETRY` | — | — | Replies 2 bytes: rows and columns (for `term_rows`, `term_cols`) |

The character grid changes as each operation arrives, and the renderer catches the screen up in the
background. So text commands never make Michael wait, and Michael never needs to read before writing.

### Serial port to the PC (`$5x`)

Provisional: stage 1's check design implements `$50`, through which Michael's test program reports. In
stage 2's design its bytes share the Cmod's USB serial port with the debug port's answers, and can land
in the middle of one.

| Code | Name | Arguments | Data | Effect |
|---|---|---|---|---|
| `$50` | `SERIAL_SEND` | — | streams | Each data byte goes out of the Cmod's USB serial port |

### Reserved

| Range | For |
|---|---|
| `$4x` | storage |
| `$51`–`$5F` | more of the serial port |
| `$02`, `$05`–`$0F`, `$14`–`$1F` | more control and display commands |
| `$20`–`$3F`, `$60`–`$7F` | later one-byte commands, for busy paths |
| `$81`–`$FF` | later devices |
| text mode's `$11`–`$FF` | more text mode operations |

## Rules for Michael's software
- **E (PA0, then PA2 from stage 4) is an output, idle low,** set up before the first transfer.
- **The bus's RS and RW are the `RS` and `RW` bits of `base_config_v2.inc`,** so the driver uses those names.
- **Set RS and RW for every transfer, by an instruction before the one that raises E.** The LCD routines and
  the keyboard driver also use PA5 and PA6, so their levels can't be assumed. If both changed in the same
  instruction as E, the FPGA might sample either value.
- **Leave RS and RW low between transfers,** as the LCD routines do and expect. With RS high, the LCD's
  busy check would read its data instead of the busy flag. `fpga_bus.inc` does this.
- **RW must be 0 for writes.** A write with RW = 1 would be taken as a read, and the FPGA would drive port B
  against the VIA while E is high.
- **Start with `RESET`,** then check `ID` before relying on the FPGA.
- Reads need no other care: interrupts may arrive at any point ([the SOEB interlock](#the-soeb-interlock)).

## The debug port
The Cmod's USB serial port carries the same transactions, so a PC can drive every device without Michael
(stage 2 onwards). The framing is text lines: `C hh ...` writes commands, `D hh ...` data, `R n` reads n bytes
of the reply queue and `S` the status, each read answering with a line of hex
([`debug_port.v`](../hardware/michael/fpga/rtl/debug_port.v) has the details, and
[`debug.py`](../hardware/michael/fpga/bus/debug.py) wraps it).
