# Michael's W5500 on the FPGA bus: plan

The W5500 Ethernet module moves from the GAL20RA10 SPI interface
([`michael-spi-interface-logic-designs.md`](michael-spi-interface-logic-designs.md#assessment)) to the Cmod A7, as a
device on the [FPGA bus](michael-fpga-bus-plan.md). The FPGA runs the SPI from its own clock, on short 3.3 V wires
at slow slew, behind the bus's filtered strobe and SOEB interlock, so Michael's port B noise never reaches the
W5500. Michael asks for whole W5500 frames; the FPGA makes them and checks them.

**Status (2026-10-25): plan.** The pins are chosen; the order along the module's header is to be confirmed.

## Wiring

The Cmod sits with its USB end away from Michael's near edge: its left side is DIP pins 25–48, pin 25 (GND) at
the USB end and 48 nearest the W5500. Pins 26–32 are the display and 33–37 are kept for its touch controller, so
the W5500 takes the free pins at the near end, **48 down to 43**, all in bank 34 (3.3 V):

| Cmod pin | FPGA pin | Signal | Direction (FPGA) | W5500 |
|---|---|---|---|---|
| 48 | V8 | to be assigned | | the signal pin furthest from the Cmod |
| 47 | U8 | | | the next |
| 46 | W7 | | | |
| 45 | U7 | | | |
| 44 | U3 | | | |
| 43 | W6 | | | the signal pin nearest the Cmod |

The order follows the module's header so the wires nest, each passing over the last: the Cmod pin nearest the
W5500 goes to the module's signal pin furthest away. The six signals:

| Signal | Direction (FPGA) | Notes |
|---|---|---|
| `net_sclk` | out | SPI clock, mode 0, idle low |
| `net_mosi` | out | |
| `net_miso` | in | |
| `net_cs_n` | out | SCSn; the module pulls it up (10 kΩ), so the W5500 is deselected while the FPGA is unconfigured |
| `net_rst_n` | out | RSTn, held low for 1 ms after configuration and by `NET_RESET` |
| `net_int_n` | in | INTn, for a later interrupt to Michael (the bus plan's CA1); pulled up in the XDC |

- **Power:** the module's 5 V pin from Michael's 5 V rail (its regulator makes the 3.3 V), its GND to the rail
  beside the Cmod's GND. No level shifting: the W5500's I/O is 3.3 V, as the FPGA's.
- **Edges:** the outputs `SLEW SLOW` and `DRIVE 4` in the XDC (nextpnr-xilinx honours both), to keep the edges
  gentle on breadboard wires. Keep the CS wire apart from SCLK where the nesting allows.

## The FPGA design

A device in `bus_control.v` and an SPI engine, `rtl/net_spi.v`:

- **SPI** at 6 MHz (the 12 MHz clock halved; a parameter), mode 0, MSB first. CS falls before the first SCLK and
  rises after the last, with a few clocks either side.
- **Frames:** Michael gives the address, the control byte and either a byte count (a read) or the data (a write).
  While the address and control bytes go out, the W5500 answers `$01 $02 $03`; the FPGA checks them, and a
  frame that doesn't get them sets a sticky status bit, `NET_ERROR` (the read's data still comes, for
  diagnosis).
- **Reset:** RSTn low for 1 ms after configuration and on `NET_RESET`; `BUSY` until 2 ms after it rises.

### Commands: device `$81` (NET), a long form like text mode's `$80`

| Operation | Arguments (data bytes) | What it does |
|---|---|---|
| `$00` `NET_RESET` | — | pulses RSTn (1 ms) |
| `$01` `NET_READ` | address high, address low, control, count | a frame reading `count` bytes (0 means 256) into the reply queue |
| `$02` `NET_WRITE` | address high, address low, control, then data | a frame writing the data bytes that follow, as they come; the next command ends it |
| `$03` `NET_STATUS` | — | replies a byte: bit 0 INTn low, bit 1 a frame in progress |

`ID`'s capabilities byte gains bit 3, the network. The status byte gains `NET_ERROR` (sticky, cleared as the
others are).

## Michael's side

`firmware/lib/fpga/fpga_w5500.inc`, with `w5500.inc`'s interface (`w5500_read_common`, `w5500_write_common`,
the register names) over `NET_READ` and `NET_WRITE`, so `michael_w5500_ping.s` and what follows build for either
interface. The retries stay, as cheap insurance; on the FPGA they should never count.

## Bring-up

Test first throughout, as the bus's stages were:

1. **Simulation.** A W5500 model for the testbenches (`sim/w5500_model.vh`, as `ili9341_model.vh` is for the
   display): frames, the header's `$01 $02 $03`, register memory, VERSIONR. `net_spi.v` and the NET commands
   against it, through the existing Michael and debug-port models.
2. **The board, from the PC.** The debug port already carries every bus command, so `bus/debug.py` gets `net`
   commands (`net version`, `net read ADDR N`, `net write ADDR BYTES`, `net setup`), and the W5500 answers
   VERSIONR over the Cmod's USB serial before Michael is involved. Michael stays in its idle program.
3. **The emulator.** `chips/fpga_bus.c`'s NET device drives the existing W5500 model (`chips/w5500.c`) through
   `chips/spi.h`.
4. **Michael.** `fpga_w5500.inc`, and `michael_w5500_ping.s` built for the FPGA: the W5500 answers ping.
5. **Later:** a TCP socket and `webserver.asm` (`attic/assembler2/webserver/`); INTn as an interrupt to Michael.
