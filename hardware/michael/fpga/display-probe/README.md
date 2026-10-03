# Michael FPGA: display probe

Checks the ILI9341 display and its wiring ([`../spi-display/WIRING.md`](../spi-display/WIRING.md))
without Michael. The FPGA becomes an SPI master for the display, commanded from the PC over the Cmod's USB
serial port.

```bash
make -C hardware/michael/fpga/display-probe probe   # load the probe design into the FPGA, then run probe.py
```

[`probe.py`](probe.py):

1. Resets the display and reads its status and ID registers back over SDO (MISO), once as wired and once
   with MOSI and SCK swapped.
2. Initialises it exactly as Michael's driver does. It replays `gd_prepare_vertical`, reading the
   `INIT_COMMANDS` table from `firmware/lib/graphics/graphics_display.inc`, at Michael's 6 MHz.
3. Cycles the screen through red, green, blue, black and white, 3 s each, printing each colour as it's sent.

With the probe already loaded, `python3 probe.py --cycles 5` repeats the colours more often, and `--speed 3`
uses 2 MHz instead of 6 MHz.

## Reading the results

| Seen | Means |
|---|---|
| ID4 `00 93 41`, power mode `08` after reset | the display answers: CS, DC, MOSI, SCK, SDO and RESET work |
| All `FF`s (SDO stays high) or all `00`s | no reply: check SDO, then CS, SCK and MOSI. If the swapped reading answers, MOSI and SCK are swapped |
| Power mode `94` after initialisation | awake and on, in the scrolling mode Michael's driver sets (`9C` without it) |
| Probe reports the display on, but the screen stays plain white | the panel isn't being driven: a faulty module (see the spi-display README) |

8-bit register reads have no dummy bit. The 24- and 32-bit ones (`04`, `09`) start with one.

## The design

[`rtl/display_probe.v`](rtl/display_probe.v) takes byte commands at 115200 baud and queues 64 of them:

| Bytes | Command |
|---|---|
| `01 n b1..bn` | write n bytes (MSB first) with the current CS and DC levels |
| `02 n` | read n bits (1–32) from SDO; replies `Rxxxxxxxx` |
| `03 c` | control lines: bit 0 CS, 1 DC, 2 RESET, 3 backlight, 4 swap the MOSI and SCK pins |
| `04 h` | SCK half period in 12 MHz clocks (1 = 6 MHz; default 6 = 1 MHz) |
| `05 c2 c1 c0 b1 b0` | write the byte pair `b1 b0` c2c1c0 times (fills) |
| `06` | replies `K00000000` once everything before it is done |

`make test` runs the testbench ([`sim/tb_display_probe.v`](sim/tb_display_probe.v)), which has an ILI9341
model that answers reads, and the unit tests for `probe.py`.
