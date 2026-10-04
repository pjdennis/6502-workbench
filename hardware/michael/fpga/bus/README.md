# Michael: FPGA bus with the display

Stage 2 of the [FPGA bus plan](../../../../docs/michael-fpga-bus-plan.md): the Cmod A7 becomes a general bus
for Michael, with the ILI9341 display as its first device. It replaced the
[spi-display](../spi-display/) design in the Cmod's flash on 2026-10-04. Michael's display driver,
[`graphics_display.inc`](../../../../firmware/lib/graphics/graphics_display.inc), reaches the display through
the bus's raw display commands (`$1x`), so every graphics program, and BBC BASIC's graphics, use it
unchanged. It needs the stage 1 wiring
([`../spi-display/WIRING.md`](../spi-display/WIRING.md#stage-1-rewiring-for-the-fpga-bus)).

```
make test     # simulations, and debug.py's tests
make bit      # bitstreams
make prog     # load into the FPGA over JTAG (until the next power-up)
make flash    # write the Cmod's flash: loaded at every power-up
```

Put Michael in the idle program (`python3 ../board.py idle`) before loading a design, so that a program
still running doesn't send it half a transfer.

## The pieces

- [`rtl/top.v`](rtl/top.v): the design. LD1 flashes on bus traffic, and LD2 while the display has work.
- [`../rtl/michael_bus.v`](../rtl/michael_bus.v) (the pins as transfers, the data buffer's turnaround and
  the SOEB interlock) and [`../rtl/bus_control.v`](../rtl/bus_control.v) (the commands, the reply queue and
  the status byte), as proved in stage 1 ([`../bus-check/`](../bus-check/)).
- [`../rtl/display_spi.v`](../rtl/display_spi.v): the display, fed from a 512-entry queue of bytes, resets
  and backlight levels. SPI at 6 MHz, and the backlight's brightness (`BACKLIGHT`, 0 to 255) by PWM at
  47 kHz.
- [`../rtl/debug_port.v`](../rtl/debug_port.v): the debug port (below).
- [`sim/tb_top.v`](sim/tb_top.v): Michael (the driver's timings, its fill loop and the keyboard's
  interrupt), the board between, an ILI9341 model on the display's pins, and the PC on the serial port.

## The debug port

The Cmod's USB serial port (115200 8N1) carries the same transactions as Michael's bus, as text lines, so
the PC can drive every command without Michael. [`debug_port.v`](../rtl/debug_port.v) has the format:
`C hh ...` writes command bytes, `D hh ...` data bytes, `R n` reads n bytes of the reply queue (answering
`r` and the bytes in hex), and `S` reads the status (answering `s` and the byte). Michael's transfers come
first, and the PC's go in the clocks between them. `SERIAL_SEND`'s bytes from Michael go out of the same
port. They can land in the middle of an answer, so don't use the debug port while a Michael program is
sending.

[`debug.py`](debug.py) wraps it:

```
python3 debug.py id        # "MB, protocol version 1, capabilities $01"
python3 debug.py status    # the status byte
python3 debug.py pattern   # initialises the display as Michael's driver does, then draws four squares
```

## Michael's programs

- Every graphics program, through `graphics_display.inc`.
- [`michael_graphic_brightness.s`](../../../../firmware/programs/michael/michael_graphic_brightness.s):
  explores the backlight's brightness with the arrow keys, `+`/`-` and the digits.

## On the board

- **2026-10-04:** the graphics programs and the debug port's pattern work.
- **The backlight's PWM made snow.** Its edges disturbed the SPI lines, and the brightness tool
  showed stray pixels and misplaced characters at any level except 0 and 255.
  - The bus itself was clean: under bus-check, the FPGA counted exactly the transfers the emulator makes
    for the same program.
  - `display_spi.v` now changes the backlight only while CS is high, and starts the next byte no sooner than
    1 µs after a change. With that, there is no snow.
  - The pins already have slow slew and 12 mA drive, nextpnr-xilinx's defaults (as Vivado's). The XDC's
    `SLEW` and `DRIVE` properties do work if wanted.

## To do

The [plan's follow-ups](../../../../docs/michael-fpga-bus-plan.md#follow-ups): `OVERFLOW` for `SERIAL_SEND`'s
dropped bytes (never for the FPGA's own answers), and a serial output module shared with bus-check.
