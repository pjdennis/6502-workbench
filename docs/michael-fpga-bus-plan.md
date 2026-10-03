# Plan: the Michael FPGA bus

Goal: turn the FPGA display interface ([`hardware/michael/fpga/spi-display/`](../hardware/michael/fpga/spi-display/))
into a small general-purpose bus between Michael and the Cmod A7's FPGA. The FPGA then provides devices that
Michael reaches through commands rather than dedicated VIA pins:

- the display, raw (as today) and as a **text mode** for the editor;
- later, storage (FPGA RAM, an SD card or the spare configuration flash), a serial port to the PC through the
  Cmod's USB, and more.

It uses one dedicated VIA pin (E, PA0), one shared pin as a flag (PA5), and PA1 for reads. It frees PA2 (it
goes back to being only the LED) and the backlight tie on the control buffer's B5.

**Status (2026-10-03): stage 0, this document, for review.**

## Stages

Each stage leaves Michael working, is built test-first, and ends in a PR.

### 0. This specification
The protocol below is the contract that the FPGA design, the firmware and the emulator are tested against.

### 1. Hardware preparation, and proving reads
1. **FPGA first.** The spi-display design drives two new pins: the data buffer's /OE low and DIR low (Michael
   to FPGA). It's written to flash and works exactly as today, since the pins aren't connected yet.
2. **Rewire** ([Wiring changes](#wiring-changes)): the data buffer's /OE and DIR go to the FPGA, plus the pull
   resistors. Doing it in this order keeps the display working throughout. Rewiring first would leave the data
   buffer disabled until the FPGA caught up.
3. **Prove reads on the board.** A test design (an extension of
   [`input-check/`](../hardware/michael/fpga/input-check/)) answers read requests with known patterns, and a
   Michael test program checks them. This settles the open toolchain's support for bidirectional (tri-state)
   pins and the bus turnaround on real hardware.
4. **Check the safe default.** With the FPGA erased or held in configuration, Michael's port B must stay
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
  - the keyboard interrupt raising PA1 ([Rules for Michael's software](#rules-for-michaels-software));
  - the firmware manifest refreshed.
- **On the board:** the graphics programs, plus an ID read. The old pin protocol (CSB on PA1, RSTB on PA2)
  is retired: the new FPGA design and the new driver go onto the board together.

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
| Control buffer B2 (PA1): **10 kΩ to 5 V** | PA1 becomes R, the read request (active low). While Michael's VIA pins are inputs after a reset, it must read as "no read", or the FPGA would drive port B. |
| Control buffer B1 (PA0, E): **10 kΩ to ground** | No stray strobes while the VIA pins are inputs. |
| Control buffer B3 (PA2) | Unused by the FPGA from stage 2 (PA2 is only the LED). Can stay wired. |
| Control buffer B5 (backlight tie) | Unused from stage 2 (the backlight is a command). Can stay as a tie. |

The VIA reads 2.0 V as high on every input at 5 V ([W65C22 datasheet](https://www.westerndesigncenter.com/documentation/w65c22.pdf),
DC characteristics), so the data buffer's 3.3 V outputs are valid highs on port B.

# The protocol (version 1)

## Signals

| Signal | VIA pin | Direction | Use |
|---|---|---|---|
| D0–D7 | PB0–PB7 | both | data; the FPGA drives them only during a read |
| E | PA0 | to the FPGA | the strobe: each rising edge transfers one byte to the FPGA. Dedicated to the bus; idle low |
| F | PA5 | to the FPGA | the flag, sampled with each byte: 0 = command, 1 = data. Shared with the LCD's RS and the keyboard's START/ACK, which is harmless: it only matters when E rises |
| R | PA1 | to the FPGA | read request, active low. Dedicated to the bus; idle high |

## Writing a byte
1. Port B is an output, holding the byte; PA5 holds F.
2. Raise E, then lower it.

The FPGA takes port B and F at E's rising edge. They must be stable from before E rises until at least
0.5 µs after, and E must stay high, then low, for at least 0.5 µs each. At 2 MHz every instruction takes at
least 1 µs, so `tsb`/`trb` on PA0 (as `gd_send_data` does) and `sta PORTA,Y`/`stx PORTA` (as the fill loops do)
meet this.

The FPGA accepts a byte every 2 µs indefinitely. Faster bursts go into a 512-byte command queue. Michael's
fastest loop sends a byte every 4.5 µs.

## Reading a byte
1. Port B is an input.
2. Lower R. Within 0.5 µs the FPGA turns the bus around and drives the next byte of its **reply queue**.
3. Read port B, at least 0.5 µs after lowering R.
4. Raise R. The FPGA releases the bus within 0.5 µs and moves to the next byte.

Don't make port B an output again, or strobe E, until 0.5 µs after raising R; at 2 MHz the next instruction
is late enough. A byte takes about 6 µs (`trb`, `lda`, `tsb`).

Reading with an empty reply queue gives `$00` and sets the `UNDERFLOW` status bit. Replies are queued in
the order of the commands that asked for them. With the FPGA unconfigured, the data buffer stays off and a
read gives whatever port B floats to. That's why software checks for the FPGA with [`ID`](#control-0x).

## Commands
- **A byte with F = 0 is a command.** It always starts a new command, abandoning any unfinished one. That
  makes the bus self-synchronising: if Michael resets mid-command, the next command puts the FPGA right.
- **Bytes with F = 1 are data:** first the command's fixed arguments, then, for streaming commands, any
  number of data bytes until the next command.
- Extra data after a non-streaming command's arguments is ignored.

Errors don't stop anything. They set sticky bits that [`STATUS`](#control-0x) reports and clears:

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
| `$02` | `STATUS` | — | — | Replies the status byte (above), then clears its sticky bits |
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
| `$05`–`$0F`, `$14`–`$1F` | more control and display commands |
| `$60`–`$FF` | later devices |

## Rules for Michael's software
- **PA0 (E) and PA1 (R) are outputs, idle low and high respectively,** set up before the first transfer.
  PA5 (F) is set for each byte.
- **Start with `RESET`,** then check `ID` before relying on the FPGA.
- **No E strobes while R is low.**
- **The keyboard interrupt raises R before it enables the keyboard board's shift register onto port B (SOEB
  low), and restores R afterwards.** Otherwise a keyboard byte arriving mid-read would have both the FPGA and
  the keyboard board driving port B. It already saves and restores port A, and the FPGA lets go long before
  the interrupt reaches SOEB.

## The debug port
The Cmod's USB serial port carries the same transactions, so a PC can drive every device without Michael
(stage 2 onwards). The framing (how a serial byte carries F, and how reads come back) is specified in stage 2.
