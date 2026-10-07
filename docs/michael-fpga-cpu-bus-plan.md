# Plan: the FPGA on Michael's CPU bus

**Proposed (2026-10-07); not started.** Stage 7 of the [Michael FPGA bus plan](michael-fpga-bus-plan.md), in a
document of its own. That plan's stages 0 to 5 put the FPGA behind the VIA and are on the board; nothing there
changes until this plan's cutover.

Move the FPGA from behind the VIA onto Michael's CPU bus, as a memory-mapped peripheral. The FPGA imitates a
hypothetical peripheral chip, beside the VIA, the RAM and the ROM: it has chip selects, register selects,
R/W, PHI2, RESB, a data bus and an IRQ output, and it knows nothing about the other chips. The glue stays
glue: the address decode and the combining of interrupts are gates on the board, not logic in the FPGA.

## Why
Every transfer today is several VIA accesses: port B's direction, RS and RW on port A, then E up and down. On
the CPU bus it is one access:

| Routine | Today | On the CPU bus |
|---|---|---|
| `fb_command`, `fb_data` | about 25 cycles | `sta`, 4 cycles (2 µs) |
| `fb_status`, `fb_read` | about 28 cycles | `lda` (or `bit`), 4 cycles |
| a fill loop's byte | 9 cycles (4.5 µs) | 4 cycles (2 µs), about the SPI's own rate |

A single `lda` or `sta` can't be split by an interrupt, so Michael's half of the
[interrupt handlers follow-up](michael-fpga-bus-plan.md#follow-ups) disappears: no port state to save, no RS,
RW or port B direction to disturb. The FPGA's half (an open command and the reply queue) remains, and option
2 there still applies. The FPGA leaves port B and port A: PA2 (E) is free again, PA4, PA5 and PA6 are only
the LCD's and the keyboard board's, and the SOEB interlock is no longer needed, because the keyboard board
never shares a bus with the FPGA.

## Address map
The FPGA takes **`$4000–$5FFF`**, which nothing uses today. The existing decode already nearly gives it:
`VIA/CS2` (U4B: NAND of A14 and /A15) is low for `$4000–$7FFF`, and the VIA is selected there when A13 is high.
So the FPGA is selected when `VIA/CS2` is low and A13 is low.

- **Two active-low chip selects, and no new gate.** The FPGA "chip" has two chip-select pins, both active
  low, as real peripheral chips mix their selects (the 6551 has one of each polarity): **CS1B** on A13 and
  **CS2B** on `VIA/CS2`. It is selected while both are low, and its logic ANDs them, as a chip would.
- **Not the spare NAND.** U4A (inputs tied high today) could make /A13 for a VIA-style active-high CS1. That
  works, but spends the board's last spare gate on what an active-low pin gets for free. U4A stays spare.
- **The VIA's chip select doesn't change.** The VIA stays at `$6000–$7FFF`, and the two windows never overlap.
- **Reads** of the window find only the FPGA: the RAM's /OE is A14, high there, and the ROM needs A15.
- **Writes** also land in the RAM's upper half, which can't be read (as for the VIA's window today): harmless.
- **PHI2 qualifies the selects inside the FPGA,** as the VIA does through its own PHI2 pin. `VIA/CS2` isn't
  gated by PHI2.
- With A0 to A2 decoded, the registers mirror every 8 bytes across the window, as the VIA's mirror every 16.

### Registers

| Address | Write | Read |
|---|---|---|
| `$4000` (A0 0) | a command | the **errors**, clearing them |
| `$4001` (A0 1) | a data byte | the reply queue's next byte |
| `$4002` | — | the **flags**, without side effects: for polling with `bit` |
| `$4003` | — | serial input's next byte, once the serial port takes input ([stage 6 of the first plan](michael-fpga-bus-plan.md#6-later)) |
| `$4004`–`$4007` | reserved | reserved |

A0 takes RS's place and RWB RW's, so the protocol's four transfers are as before, except that a status read
now gives only the errors. Every read has a side effect except `$4002`'s, so an interrupt handler or a wait
loop can poll the flags freely. Serial input gets a register of its own rather than the reply queue: it is an
unbounded stream, arriving whenever the PC sends, and in the reply queue it would interleave with the replies
to commands.

## The errors and the flags (protocol version 3)
Version 2 had one status byte: the sticky errors, cleared by reading it, and BUSY. Version 3 splits it in two,
so the flags that programs poll can be read without clearing the errors, and changes the meaning of BUSY, so
`ID` reports protocol version 3.

**The errors** (`$4000`), sticky, as in version 2, cleared by reading them:

| Bit | Name | Set when |
|---|---|---|
| 0 | `ABANDONED` | a command arrived before the previous one's arguments were complete |
| 1 | `UNKNOWN` | an unknown command |
| 2 | `EXTRA` | data after a non-streaming command's arguments |
| 3 | `UNDERFLOW` | a read of the reply queue (or of serial input) with nothing there |
| 4 | `OVERFLOW` | a queue overflowed |
| 5–7 | — | 0 |

**The flags** (`$4002`), each the state at that moment:

| Bit | Name | Set while |
|---|---|---|
| 7 | `IRQ` | an enabled interrupt source wants service, as the VIA's IFR bit 7 ([below](#the-fpgas-interrupt)) |
| 6 | `BUSY` | **the FPGA can't safely take more writes:** a queue that writes go into has 15 free entries or fewer. When clear, at least 16 more bytes (commands or data) are accepted without checking again |
| 5 | `REPLY` | the reply queue holds at least one byte |
| 4 | `REPLY16` | the reply queue holds at least 16 bytes: 16 reads without checking again |
| 3 | `RX` | serial input holds at least one byte (0 until the serial port takes input) |
| 2 | `RX16` | serial input holds at least 16 bytes |
| 0–1 | — | 0 |

`bit $4002` tests bits 7 and 6 directly (N and V), so the two flags that want the quickest checks are there.
Bit 7 for the interrupt follows the VIA's IFR (and most chips of its family). The others take `lda $4002` and
`and #mask`, which in a bulk transfer is once every 16 bytes. The 16s pair up: BUSY is "nearly full" for
writes, `REPLY16` and `RX16` are "nearly empty" for reads, and `REPLY` and `RX` say whether there's anything at
all, for reading everything received so far of an unbounded stream such as serial input. A byte written adds
at most one entry to a queue, so counting bytes is safe. Replies to today's commands are ready within a clock,
so a program reading a known number of them needs no flag; `REPLY16` is for slow producers to come, such as
storage reading a block.

**BUSY means "can't accept", nothing else.** In version 2 it also meant "still working": it was set while
the display, the text grid, the renderer or the serial output had anything to do, even with every queue
nearly empty. That made it useless as flow control (a program waiting on it would wait for the renderer to
finish drawing, not for room). In version 3 it is set while any of the queues that writes go into (the
display queue, the text grid's operation queue, the serial queue) has fewer than 16 free entries. No program
polls BUSY today (`michael_fpga_bus_check.s` only notes that it ignores it), so nothing needs migrating.

To decide: one BUSY for every queue is simple, but a long `SERIAL_SEND` backlog would then hold up display
writes too. The alternative is a room flag per device in each device's state reply (below). Start with the
single bit.

**"Is it finished?" moves to the devices,** each answering with a reply byte, so a program asks only when it
cares (before reading the display back, say, or before a timing measurement):

| Command | Replies 1 byte |
|---|---|
| text mode operation `$11` `DRAWN` | `$01` when the grid has applied every queued operation and the renderer has drawn them: the glass shows the grid. Else `$00` |
| `$14` `DISP_IDLE` | `$01` when the display queue is empty and the SPI has sent its last byte. Else `$00` |
| `$51` `SERIAL_IDLE` | `$01` when the serial queue is empty and the UART has sent its last bit. Else `$00` |

Each sits in its device's reserved range ([the command map](michael-fpga-bus-plan.md#reserved)).

## Flow control: what can outpace what
Writes are never held up on the bus (RDY isn't used: [below](#rdy-not-planned)), so a writer that's faster than
the FPGA's consumer fills a queue. With Michael's fastest writes, back-to-back `sta`s every 4 cycles (2 µs at
2 MHz):

- **Raw display commands can't be outpaced** at today's speeds. The SPI sends a byte in about 1.33 µs (8 bits
  at 6 MHz), faster than Michael can store one. That holds up to a CPU clock of about 3 MHz (4 cycles per 1.33
  µs). The [faster SPI clock](michael-fpga-bus-plan.md#follow-ups) would raise the limit (12 MHz SCK: about
  6 MHz). Check the SPI's real per-byte rate, gaps included, in simulation.
- **Text mode can be outpaced, during hardware scrolls.** Most operations change a cell, or move the cursor, in
  a clock or two, and the renderer draws behind them without holding them up. But the grid does wait for the
  renderer in one case ([`text_grid.v`](../hardware/michael/fpga/rtl/text_grid.v)): a scroll of the whole
  region, done by the display's hardware scroll, waits until the renderer has drawn every dirty cell (up to a
  full screen, about 0.2 s) and then a frame (16.7 ms). Operations queue meanwhile, 512 deep, which Michael fills
  in about 1 ms of `PUT`s. The editor writes a row or so after a scroll, well within it; a program that scrolls
  while it writes on (a listing, a `cat`) would overrun. Moving cells (inserting or deleting lines mid-region)
  also takes a clock or two a cell, but that is about 70 µs for a whole screen at 12 MHz, short of overrunning.
- **The serial port is easily outpaced:** 115200 baud is about 87 µs a byte, and its queue is 2048 deep.
- **The reply queue** only fills if a program asks for replies and never reads them.

So the guarantee holds for the raw display and not in general. The driver checks BUSY: `fb_command` and
`fb_data` start with `bit FB_FLAGS` (`$4002`) and wait while V is set, 6 cycles more a byte when clear. A fill
loop can check once every 16 bytes, which BUSY's definition allows. [Stage 2](#2-text-mode-without-stalls)
takes the stall out of text mode, which leaves serial as the only device that can be outpaced.

## Hardware

| Change | Why |
|---|---|
| Data buffer (U7): its B side from port B (PB0–PB7) to the **CPU's D0–D7**; its A side stays on Cmod pins 1–8 | The FPGA's data bus |
| U7 DIR (pin 1): from Cmod pin 17 to **RWB**; R16 (its pull-down) removed | The buffer turns with the CPU's own R/W. RWB changes only while PHI2 is low, when the buffer is off. Cmod pin 17 is freed |
| U7 /OE (pin 19): stays on Cmod pin 14 with R15's pull-up | On only while the FPGA is selected and PHI2 is high, reads and writes: on otherwise, it would drive the bus when the CPU reads RAM. Off while the FPGA is unconfigured |
| Control buffer (U8) B1–B8: **PHI2, RWB, CS2B (`VIA/CS2`), CS1B (A13), A0, A1, A2, RESB**, replacing PA2, PA5, PA4, PA6 and the ties (R12, R14, R17, R18, R9 removed) | The FPGA's inputs, all through a 5 V-tolerant '245 as today. A8 needs a Cmod pin (B8 has none today) |
| **74HCT08** (new) near the CPU: the VIA's IRQB and the FPGA's `irq_b` in, the CPU's IRQB out. The VIA's IRQB comes off the CPU's IRQB | The W65C22S drives IRQB both ways (only the W65C22N's is open-drain), so the two can't share a wire: active low, an AND is their OR. One NAND can't make it (it needs a NAND and an inverter), so U4A's spare doesn't do. HCT, unlike the rest of Michael's 74HC logic, because it shifts the level: its inputs take TTL levels (a high from 2.0 V), so the FPGA's 3.3 V is a valid high within spec, and it drives the CPU at 5 V. A 74HC08 may stand in if there's no HCT to hand, off the books: on paper an HC input needs 3.5 V ([Michael's README](../hardware/michael/README.md#known-departures-from-the-data-sheets)) |
| FPGA `irq_b` (a free Cmod pin) to the 74HCT08, with **10 kΩ to 3.3 V** | Unconfigured, the FPGA's pin floats and the pull-up keeps its input inactive, so the VIA's (the keyboard's) interrupts work without the FPGA. The pull-up is to 3.3 V so the FPGA's pin never sees more than its supply |
| None: the FPGA's 3.3 V reaches the CPU's data bus on reads | The W65C02S asks for 0.8 × VDD and in practice switches at about half VDD. Accepted out of spec ([Michael's README](../hardware/michael/README.md#known-departures-from-the-data-sheets)) |

RDY is left as it is: R2's pull-up to +5V, nothing else on it.

Cmod pins 9–13, 18 and 19 carry U8's A side as now (renamed); `irq_b` and U8's A8 need two free Cmod pins, to
choose (33–37 stay reserved for the touch controller). The 74HCT08's three spare gates are for later (an NMI
source, say). The schematics (`michael_schematic.py`, checked by `test_michael_schematic.py`),
[`WIRING.md`](../hardware/michael/fpga/spi-display/WIRING.md) and `michael-fpga-display.svg` follow.

## The FPGA's bus front end
A new `rtl/cpu_bus.v` replaces [`michael_bus.v`](../hardware/michael/fpga/rtl/michael_bus.v), with the same
interface to `bus_control.v` (`wr`, `wr_rs`, `wr_data`, `rd`, `rd_end`, `rd_rs`, `reply_byte`, `status_byte`),
plus the flags' read and serial input's, so the debug port and the command layer change only as the errors
and the flags do. The debug port's `S` reads the errors, and a new `F` the flags.

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

Instead the design runs on **one fast clock from the MMCM**, 96 MHz (12 MHz × 64 ÷ 8) as the target. The whole
design moves to it, not just the front end, so there is no crossing: the 12 MHz-derived parameters (the UART's
divider, the cursor's blink, the activity LEDs, the SPI's divider) scale with it. That also gives the
[faster SPI clock](michael-fpga-bus-plan.md#follow-ups).

**If the display side doesn't close timing,** in order:
1. One clock at 48 MHz. The sampling below still has margin: a filter of 2 samples, and k about 2 (40 to 60
   ns before the fall).
2. **Two clock domains, cut at the queues.** The bus front end, `bus_control.v`, the debug port and the UART
   stay on the fast clock; the text grid, its renderer and `display_spi.v` move to a slow one (12 MHz, as
   today, from the same MMCM), so the SPI's timing and the display side's parameters don't change. The cut
   goes where the design already decouples, its two queues:
   - the text grid's operation queue and the display queue become **asynchronous FIFOs** (Gray-coded
     pointers; `fifo.v` is single-clock, so a new module, tested with two unrelated clocks). Their fill
     levels on the fast side give `BUSY` and `OVERFLOW`, so neither has to cross;
   - `DRAWN` and `DISP_IDLE` take their answers from the slow side through synchronisers (two flip-flops),
     and also count the FIFOs' own contents on the fast side, so a query straight after a write can't see
     the write's effect as already done while it crosses;
   - **one ordering rule moves.** Today `bus_control.v`'s `text_mode` drops as `DISP_RESET` arrives, so the
     renderer stops before the reset's entry reaches the display. Across the cut the level and the entry
     would travel separately. Instead `display_spi.v` stops the renderer when the reset's entry reaches the
     head of its queue, which is all in the slow domain.

   Not the cut between the grid and the renderer: their interface is wide and tightly coupled (a cell read
   answered the next clock, the `take_dirty`, `moving` and hardware-scroll handshakes), so it would cross
   in a dozen places. A clock enable on one clock wouldn't help either: without multicycle constraints, which
   the open toolchain lacks, nextpnr would still time every path at the fast clock.

**Writes: a history of samples.** The CPU's write data is stable from shortly after PHI2 rises until about 10
ns after it falls. That is a window of about 200 ns at 2 MHz, of which only the end is short. So:

```
PHI2   ____/‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾\______
D      xxxxxxx<========== stable ==========>xxx
samples  |  |  |  |  |  |  |  |  |  |  |  |  |     every 10.4 ns at 96 MHz
                                  ^            ^
                     taken from here           the fall seen here
```

1. D, A0–A2, RWB, the selects and PHI2 go through synchronisers of equal depth, so samples of one clock line
   up.
2. A shift register keeps the last few samples of D, A0–A2 and RWB (4 to 6 deep).
3. When the synchronised, filtered PHI2 falls, take them from k samples earlier, about 30 ns before the fall
   (k about 3, plus the filter's delay), far from both ends of the window.

Only PHI2 can be caught changing, and its synchroniser settles it. The ±1 sample of uncertainty in when the fall
is seen is absorbed by looking back k samples. D is never sampled while it changes. This doesn't depend on
the CPU's speed, as long as PHI2's high phase lasts several samples. PHI2's glitch filter must be short, a few
samples (about 30 ns): E's 250 ns would swallow PHI2's whole 250 ns high phase. `michael_bus.v`'s `d_at_e`
(D as E first went high) is the same idea; here it's D before PHI2 fell. At 12 MHz this would be marginal (two
samples back is 83 to 166 ns before the fall). Fallback if the board shows skew: a 74LVC573 on U7's A side,
latched by PHI2, holding the byte through PHI2's low phase.

**Reads.** The address, RWB and the selects are valid from shortly after PHI2 falls, so the front end decodes
them into registers during PHI2's low phase. It drives D from them: the reply queue's head for `$4001`, the
errors for `$4000`, the flags for `$4002`, serial input for `$4003`. U7's /OE is the registered select gated
by the PHI2 pin with no clock in the path, as the SOEB interlock is today, so the buffer turns off within
about 10–15 ns of PHI2 falling. That is after the CPU's read hold time and long before anything else drives
the bus. A read's side effect (the reply queue or serial input moving on, the errors clearing) happens only
after the fall, so the byte on the bus never changes while it is read. The FPGA drives its D pins only during
a selected read cycle, when U7 points from the FPGA to the CPU.

**RESB** resets the front end and the command layer, as `RESET` does (the queues and the status), and
disables the FPGA's interrupt sources, as a peripheral chip's reset pin would. The display is left as it is.

**What goes:** E's 250 ns filter, the turnaround states, `paused` and the SOEB interlock.

## The FPGA's interrupt
`irq_b` is low while the status's `IRQ` bit is set: some source is active and enabled. A control command
(`$05` `IRQ_ENABLE`, argument a mask of sources; all off after a reset) chooses the sources. The first: the
reply queue not empty; later serial input and storage. A command to read which sources are active, and to
acknowledge them, comes with the first source that needs one. As with a real chip, the handler asks each chip
in turn: the VIA's IFR, then `bit $4002` (N set: the FPGA). This replaces stage 6's idea of an interrupt on
the VIA's CA1.

## RDY: not planned
The W65C02S's RDY can halt it on any cycle, writes included, so the FPGA could hold Michael while a queue is
full and programs would never check BUSY. It is not intended: a halted CPU does nothing else, not even take
the keyboard's interrupts, while it could have other work to do as it waits. Polling BUSY lets a program
choose. RDY stays as it is (R2 to +5V), and no Cmod pin is set aside for it.

If it were ever added: an open-drain output (driven low or left floating, since the W65C02S drives RDY low
itself in `WAI`), R2's pull-up moved to 3.3 V so the FPGA's pin never sees more than its supply, and a control
command switching it on and off, off by default, so a program asks to be held.

## Software
- **`fpga_bus.inc`** keeps its entry points. `fb_command` becomes `sta FB_COMMAND` (`$4000`), `fb_data`
  `sta FB_DATA` (`$4001`), each after waiting while BUSY is set
  ([flow control](#flow-control-what-can-outpace-what)); `fb_status` becomes `fb_errors`, `lda FB_ERRORS`, and
  `fb_read` is `lda FB_REPLY`, each still keeping A, X, Y and the processor flags as documented.
  `fb_initialize` sends `RESET`. A new `fb_flags` reads `FB_FLAGS` (`$4002`), which programs also test with
  `bit`.
- The flags' names: `FB_IRQ` %10000000, `FB_BUSY` %01000000, `FB_REPLY` %00100000, `FB_REPLY16` %00010000,
  `FB_RX` %00001000, `FB_RX16` %00000100. The errors keep version 2's names; `FB_ERRORS` the mask goes.
- `FPGA_E` leaves `base_config_v2.inc` and `initialize_michael_ports`: PA2 and PA0 are free.
- `graphics_display.inc`'s fill loops and `gd_send_x2` can store straight to `FB_DATA`, a byte every 4 cycles,
  checking BUSY every 16 bytes (or not at all for raw display writes, up to the CPU clock above: to decide).
- **The ROM changes** (its graphic screen and launcher use the bus), so a new ROM is programmed with the
  rewiring, as in stage 4. The firmware manifest is refreshed.
- **The rules for Michael's software** lose E, RS and RW and gain one: **reads have side effects**, except
  `$4002`'s (`$4000` clears the errors, `$4001` takes the reply queue's next byte, `$4003` serial input's). So no
  read-modify-write instructions (`inc`, `asl`, `tsb`, `trb` and the like) on the FPGA's registers, and no
  addressing modes whose extra cycles may read a register's address. Plain `lda`, `sta`, `stz` and `bit`
  absolute only.

## Emulator
`fpga_bus.c` leaves the VIA's pins and joins the CPU's bus at `$4000–$5FFF`, decoded by `glue_michael.c`. Its
`--fpga-log` lines (`C`, `D`, `R`, `S`) stay the same, plus one for the side-effect-free read, so the driver
test's expectations change little. It models the queues' fill levels, so the version 3 flags and errors are
tested. Its IRQ output goes through the board's AND with the VIA's. `--no-fpga` leaves the window empty:
reads find a floating bus.

## Stages
Each leaves Michael working, is built test-first, and ends in a PR.

### 1. In software
Tests first, then the code, all without the board:
- **The front end in simulation.** A testbench that drives PHI2 at random phases against the fast clock, with
  a few ns of skew between PHI2 and D each way, and D invalid outside the data sheet's window, so a wrong
  sample shows as a wrong byte. Every write arrives with its byte, address and RWB; a PHI2 glitch shorter than
  the filter makes no transfer; reads drive the byte through PHI2's high phase and release the bus within 15
  ns of the fall; reading `$4002` changes nothing; the buffer is never on while the CPU reads anything else.
  `michael_board.vh` and `michael_fpga_bus.vh` become a CPU bus model (address, RWB, PHI2 and the cycle
  timings of `fpga_bus.inc`), keeping the no-two-drivers checks.
- **Version 3's errors and flags in `bus_control.v`:** the errors alone at `$4000`; the flags at `$4002`, BUSY
  from the queues' room alone (set at 15 free or fewer, clear with a full renderer backlog), `REPLY` and
  `REPLY16` from the reply queue's count, `IRQ` in bit 7; and `DRAWN`, `DISP_IDLE` and `SERIAL_IDLE`. Then a
  test that overruns the serial queue without checking BUSY (`OVERFLOW` set), and doesn't when it checks every
  16 bytes.
- **The whole design on the fast clock:** `tb_top.v` and the text mode's testbenches still pass with the scaled
  parameters; nextpnr's report shows the clock met.
- **The emulator, the driver and the firmware:** `test_michael_fpga_bus_driver.py`, `test_michael_pins.py` (PA2
  and PA0 free, the LED unchanged), the ROM's tests on the graphic screen, and the editor's graphic tests.
- **The schematics:** `test_michael_schematic.py` against the new nets.

### 2. Text mode without stalls
The grid stops taking operations while a hardware scroll gets the glass ready (`text_grid.v`'s `ASK`, until
the renderer's `hw_ready`). Most of that wait is the renderer drawing every dirty cell first, up to a full
screen (0.2 s), and that part isn't needed: **a dirty cell that moved with the scroll can be drawn at its new
place in the display's memory before the scroll reaches the glass.** The memory row it is drawn in shows,
before the scroll, the screen row the cell was in before the scroll, and after it, the row it moved to: right
both times. Only two kinds of cell must wait for the scroll to reach the glass: the rows coming in (their
memory is where the leaving rows still show), and any cell changed after the scroll (drawn at its new place
early, it would show one scroll away from it for a frame).

So the grid stops waiting:
- **The grid applies the scroll at once** (moves the cells and their marks, changes `offset`) and tells the
  renderer: the scroll's direction and count. `ASK` goes.
- **A second kind of dirty mark:** cells marked after a scroll that hasn't reached the glass yet (including
  every cell of the rows coming in that is written) are "late". The renderer draws the other marks at once, by
  the grid's offset, as it does now, and late marks only once the scroll is on the glass.
- **The renderer performs the scroll in its own time:** the cursor off, the leaving rows blanked, VSCRSADD,
  then the frame's wait. Then the late marks become ordinary marks.
- **One hardware scroll in flight.** A scroll that arrives while one is in flight is done in the grid's cells
  only (as with no hardware scroll), with every cell it changes marked late, so the region is redrawn behind
  it, at the SPI's rate. A burst of scrolls (a listing) costs redrawing time, never a wait for Michael.
- **Region changes** while a scroll is in flight wait for it (they set the offset back to 0 and mark every
  cell), or are queued for the renderer the same way.

Then no text mode operation waits on the renderer, so the operation queue only fills if Michael outruns the
grid itself, a clock or two a cell, which it can't (moving a whole screen's cells for an `INSERT_LINES` is
about 70 µs at 12 MHz, 10 µs at 96 MHz).

Test first, against the model panel's frame-by-frame checks (`test_text_render.py`): that no frame ever shows
a cell anything it doesn't hold before, between or after the operations, now with operations arriving during
a scroll; that a scroll arriving while one is in flight is redrawn correctly; and in `tb_text_grid.v`, that
the grid never stops taking operations. This stage doesn't depend on the CPU bus: it can go onto the board
before the cutover, on today's bus.

### 3. The cutover, on the bench
As stage 4 of the first plan, all at once, with Michael powered off: program the new ROM
(`make -C hardware/michael program`), rewire (the hardware table, including the 74HCT08), then flash the new
design. Then:
1. **The safe default first:** with the Cmod's flash erased, Michael boots, the LCD and the keyboard work
   (interrupts through the AND gate), U7's /OE measures 3.3 V, and a read of `$4000` finds a floating bus.
2. **Writes only:** a check design that only listens (U7 on for selected writes, never driving) reports the
   bytes Michael writes to `$4000–$5FFF` over USB serial. It proves the sampling on the board before the FPGA
   ever drives the CPU's bus.
3. **Reads:** `bus-check` rebuilt for the CPU bus: `ECHO` patterns read back, with keyboard typing alongside
   (it no longer shares anything, which is the point of checking).
4. The graphics programs, `board_check.py`, the ROM's graphic screen and the editor on the graphic display.

### 4. The FPGA's interrupt
The 74HCT08 is wired at the cutover, with `irq_b` held high. Then `IRQ_ENABLE` and the first source
([above](#the-fpgas-interrupt)), with a keyboard handler that also checks the FPGA.

## To confirm
- The W65C02S's AC timings at 5 V (write data delay and hold, address delay, read setup and hold), from the
  data sheet's tables, against the sample window above.
- The two free Cmod pins.
- That the display side (the text grid's 400-cell priority search is the likely critical path, more than the
  renderer) closes timing at 96 MHz with the open toolchain, or 48 MHz, or the two-domain cut above.
- The SPI's real per-byte rate, for the raw display's no-overrun limit.
