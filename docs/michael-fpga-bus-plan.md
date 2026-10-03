# Plan: the Michael FPGA bus

Goal: turn the FPGA display interface ([`hardware/michael/fpga/spi-display/`](../hardware/michael/fpga/spi-display/))
into a small general-purpose bus between Michael and the Cmod A7's FPGA. The FPGA then provides devices that
Michael reaches through commands rather than dedicated VIA pins:

- the display, raw (as today) and as a **text mode** for the editor;
- later, storage (FPGA RAM, an SD card or the spare configuration flash), a serial port to the PC through the
  Cmod's USB, and more.

It uses one dedicated VIA pin, E (PA0). Two shared pins are sampled only when E rises: F (PA5) and G (PA6).
The FPGA also watches the keyboard board's output enable (SOEB, PA4), so a keyboard interrupt can safely
pause a read. This frees PA1 (the display's chip select today), PA2 (back to being only the LED) and the
backlight tie on the control buffer's B5.

**Status (2026-10-03): stage 0, this document, for review.** Revised the same day: reads use E with the shared
pin G instead of a dedicated PA1, and a SOEB interlock lets interrupts pause a read.

## Stages

Each stage leaves Michael working, is built test-first, and ends in a PR.

### 0. This specification
The protocol below is the contract that the FPGA design, the firmware and the emulator are tested against.

### 1. Hardware preparation, and proving reads
1. **FPGA first.** The spi-display design drives two new pins: the data buffer's /OE low and DIR low (Michael
   to FPGA). It's written to flash and works exactly as today, since the pins aren't connected yet.
2. **Rewire** ([Wiring changes](#wiring-changes)): the data buffer's /OE and DIR go to the FPGA, plus the pull
   resistors. PA4 and PA6 go to two of the control buffer's spare inputs, and the E pull-down is added. Doing it
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
   undriven.

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
  the background. It implements the text commands ([`$2x`, `$3x`](#text-mode-2x-and-3x)), which mirror the
  editor's screen calls one for one.
- **Testing:** first in simulation, with a display model that decodes the ILI9341 writes into a frame buffer
  and checks the characters drawn. Then on the board, driven from the PC through the debug port.
- **The grid's shape and font** are decided here, for example 40×30 with 8×8 characters in landscape.
- **Look into the panel's windowed scrolling** to speed up the editor's scrolling.
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
- **One EEPROM programming** (the programmer and `minipro` are ready on the bench):
  `minipro -p AT28C256 -w hardware/michael/michael_rom.bin`, after backing up the current chip.

### 5. The editor on the graphic display
- `editor/bin/editor-michael-upload.sh --graphic` adds a few-byte launcher that selects the graphic display and
  then starts the editor. The editor itself doesn't change: it reads its screen size at run time.
- Emulator tests in graphic mode, then on the board.

### 6. Later
Storage ([`$4x`](#reserved)): FPGA RAM first, then an SD card or the configuration flash's spare space (the
flash's clock goes through `STARTUPE2`, unproven with the open toolchain). Also a serial port to the PC, and an
FPGA interrupt on the VIA's CA1 (unused on Michael; input-only, so a 3.3 V FPGA pin can drive it directly).

## Wiring changes

Done in stage 1, after the FPGA drives the new pins ([`WIRING.md`](../hardware/michael/fpga/spi-display/WIRING.md)
is updated to match).

| Change | Why |
|---|---|
| Data buffer (upper 74LVC245): /OE (pin 19) from ground to **Cmod pin 14**, with **10 kΩ to 3.3 V** | The FPGA enables the buffer. The pull-up keeps it off whenever the FPGA isn't configured or isn't powered. |
| Data buffer: DIR (pin 1) from ground to **Cmod pin 17**, with **10 kΩ to ground** | The FPGA turns the bus around for reads. Michael to FPGA by default. |
| Control buffer B6 (pin 13): its 10 kΩ tie replaced by **PA4** (VIA pin 6), and A6 (pin 7) to **Cmod pin 18** | SOEB, for the interlock |
| Control buffer B7 (pin 12): its 10 kΩ tie replaced by **PA6** (VIA pin 8), and A7 (pin 8) to **Cmod pin 19** | G |
| Control buffer B2 (PA1) | Used as CSB by the current interface until the stage 2 cutover, then unused, so PA1 is free. Can stay wired. |
| Control buffer B1 (PA0, E): **10 kΩ to ground** | No stray strobes while the VIA pins are inputs after a reset. It's the only bias Michael's side needs: without an E edge, nothing else matters. |
| Control buffer B3 (PA2) | Unused by the FPGA from stage 2 (PA2 is only the LED). Can stay wired. |
| Control buffer B5 (backlight tie) | Unused from stage 2 (the backlight is a command). Can stay as a tie. |

The VIA reads 2.0 V as high on every input at 5 V ([W65C22 datasheet](https://www.westerndesigncenter.com/documentation/w65c22.pdf),
DC characteristics), so the data buffer's 3.3 V outputs are valid highs on port B.

# The protocol (version 1)

## Signals

| Signal | VIA pin | Direction | Use |
|---|---|---|---|
| D0–D7 | PB0–PB7 | both | data; the FPGA drives them only during a read |
| E | PA0 | to the FPGA | the strobe: each rising edge starts one transfer. Dedicated to the bus; idle low |
| F | PA5 | to the FPGA | sampled when E rises. Shared with the LCD's RS and the keyboard's START/ACK |
| G | PA6 | to the FPGA | sampled when E rises. Shared with the LCD's R/W and the keyboard's PARITY |
| SOEB | PA4 | to the FPGA | the keyboard board's output enable (active low), watched for the [interlock](#the-soeb-interlock) |

The shared pins are harmless to their other users. The LCD only looks at RS and R/W while its own E (PA7)
strobes; the keyboard driver's interrupt saves and restores port A. And F and G only matter at the instant E
rises. E's rising edge chooses the transfer:

| G | F | Transfer |
|---|---|---|
| 0 | 0 | write a command byte |
| 0 | 1 | write a data byte |
| 1 | 1 | read the next byte of the reply queue |
| 1 | 0 | read the status byte (the reply queue is left alone) |

## Writing a byte
1. Port B is an output, holding the byte. G is 0 and F is set, by an instruction before the one that raises E.
2. Raise E, then lower it.

The FPGA takes port B, F and G at E's rising edge. They must be stable from before E rises until at least
0.5 µs after, and E must stay high, then low, for at least 0.5 µs each. At 2 MHz every instruction takes at
least 1 µs, so `tsb`/`trb` on PA0 (as `gd_send_data` does) and `sta PORTA,Y`/`stx PORTA` (as the fill loops do)
meet this.

The FPGA accepts a byte every 2 µs indefinitely. Faster bursts go into a 512-byte command queue. Michael's
fastest loop sends a byte every 4.5 µs.

## Reading a byte
1. Port B is an input. G is 1, and F is 1 for the reply queue or 0 for the status byte, set by an instruction
   before the one that raises E.
2. Raise E. Within 0.5 µs the FPGA turns the bus around and drives the byte.
3. Read port B, at least 0.5 µs after raising E.
4. Lower E. The FPGA releases the bus within 0.5 µs, and for a reply-queue read moves to the next byte.

Don't make port B an output again until 0.5 µs after lowering E; at 2 MHz the next instruction is late
enough. A byte takes about 6 µs (`tsb`, `lda`, `trb`).

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
- **A byte with F = 0 is a command.** It always starts a new command, abandoning any unfinished one. That
  makes the bus self-synchronising: if Michael resets mid-command, the next command puts the FPGA right.
- **Bytes with F = 1 are data:** first the command's fixed arguments, then, for streaming commands, any
  number of data bytes until the next command.
- Extra data after a non-streaming command's arguments is ignored.

Errors don't stop anything. They set sticky bits that the status read (G = 1, F = 0) reports and clears:

| Bit | Name | Set when |
|---|---|---|
| 0 | `ABANDONED` | a command arrived before the previous one's arguments were complete |
| 1 | `UNKNOWN` | an unknown command (its data is then ignored) |
| 2 | `EXTRA` | data after a non-streaming command's arguments |
| 3 | `UNDERFLOW` | a read with the reply queue empty |
| 4 | `OVERFLOW` | the command queue or the reply queue overflowed |
| 7 | `BUSY` | (not sticky) the FPGA is still working through queued commands |

## Command map

Commands are grouped by their high nibble. Arguments are listed in order; all are data (F = 1) bytes.

### Control (`$0x`)

| Code | Name | Arguments | Data | Effect |
|---|---|---|---|---|
| `$00` | `NOP` | — | — | Nothing. Safe as padding or a resync |
| `$01` | `ID` | — | — | Replies 4 bytes: `'M'`, `'B'`, the protocol version (1), and a capabilities byte (bit 0 raw display, bit 1 text mode, bit 2 storage) |
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

In text mode the raw commands are ignored, and set `UNKNOWN`.

### Text mode (`$2x` and `$3x`)

Provisional: the details are settled in stage 3. They mirror the editor's screen calls (`asm/17/environment.asm`,
`scr_*`), so the ROM's graphic services are a thin translation. Rows and columns are 0-based.

| Code | Name | Arguments | Data | Mirrors |
|---|---|---|---|---|
| `$20` | `TEXT_ON` | — | — | Enter text mode: clear the grid and draw it |
| `$21` | `TEXT_OFF` | — | — | Back to raw mode |
| `$22` | `GOTO` | row, column | — | `scr_goto` |
| `$23` | `PUT` | — | streams | `write_b`: characters at the cursor, advancing |
| `$24` | `CLEAR` | — | — | `scr_clear` |
| `$25` | `CLEAR_EOL` | — | — | `scr_clear_eol` |
| `$26` | `INSERT` | count | — | `scr_insert` |
| `$27` | `DELETE` | count | — | `scr_delete` |
| `$28` | `REGION` | top, bottom | — | `scr_region` |
| `$29` | `REGION_RESET` | — | — | `scr_region_reset` |
| `$2A` | `SCROLL_UP` | count | — | `scr_scroll_up` |
| `$2B` | `SCROLL_DOWN` | count | — | `scr_scroll_down` |
| `$2C` | `INSERT_LINES` | count | — | `scr_insert_lines` |
| `$2D` | `DELETE_LINES` | count | — | `scr_delete_lines` |
| `$2E` | `CURSOR` | 0 off, 1 on | — | `scr_cursor_off`/`scr_cursor_on` |
| `$2F` | `VIDEO` | 0 normal, 1 reverse | — | `scr_normal`/`scr_reverse` |
| `$30` | `GEOMETRY` | — | — | Replies 2 bytes: rows and columns (for `term_rows`, `term_cols`) |

The character grid changes as each command arrives, and the renderer catches the screen up in the
background. So text commands never make Michael wait, and Michael never needs to read before writing.

### Reserved

| Range | For |
|---|---|
| `$4x` | storage |
| `$5x` | a serial port to the PC |
| `$31`–`$3F` | more text mode |
| `$02`, `$05`–`$0F`, `$14`–`$1F` | more control and display commands |
| `$60`–`$FF` | later devices |

## Rules for Michael's software
- **PA0 (E) is an output, idle low,** set up before the first transfer.
- **Set G and F for every transfer, by an instruction before the one that raises E.** The LCD routines and
  the keyboard driver also use PA5 and PA6, so their levels can't be assumed. If both changed in the same
  instruction as E, the FPGA might sample either value.
- **G must be 0 for writes.** A write with G = 1 would be taken as a read, and the FPGA would drive port B
  against the VIA while E is high.
- **Start with `RESET`,** then check `ID` before relying on the FPGA.
- Reads need no other care: interrupts may arrive at any point ([the SOEB interlock](#the-soeb-interlock)).

## The debug port
The Cmod's USB serial port carries the same transactions, so a PC can drive every device without Michael
(stage 2 onwards). The framing (how a serial byte carries F, and how reads come back) is specified in stage 2.
