# Michael: FPGA SPI display interface

A Digilent Cmod A7-35T between Michael's VIA and the ILI9341 240×320 TFT. It replaces an earlier interface
board that had no schematic. Michael's display driver,
[`firmware/lib/graphics/graphics_display.inc`](../../../../firmware/lib/graphics/graphics_display.inc), is
unchanged: the FPGA reproduces what that driver expects.

Worked from 2026-10-03 with an Adafruit ILI9341 display, running `michael_graphic_display_test.s` and
`michael_graphic_keyboard.s` unchanged.

**Replaced in the Cmod's flash on 2026-10-04** by the [FPGA bus design](../bus/) (stage 2 of the
[FPGA bus plan](../../../../docs/michael-fpga-bus-plan.md)). Michael's driver now speaks the bus's protocol,
so today's graphics programs need the bus design. This design works only with programs that use the
driver's older pin interface (`GD_PIN_INTERFACE`, as `michael_fpga_input_check.s` does) or binaries built
before stage 2, and is kept for that and for the record. The wiring, [`WIRING.md`](WIRING.md), is the bus's
too.

- Wiring, pin by pin: [`WIRING.md`](WIRING.md)
- Schematic: [`michael-fpga-display.svg`](../../schematics/michael-fpga-display.svg), sheet 3 of
  [Michael's schematics](../../schematics/)
- Design: [`rtl/spi_bridge.v`](rtl/spi_bridge.v) (the interface), [`rtl/top.v`](rtl/top.v) (pins, backlight,
  touch, LEDs); testbench [`sim/tb_top.v`](sim/tb_top.v), which replays the driver's own write timings
  ([`../sim/michael_via.vh`](../sim/michael_via.vh)) against an ILI9341 model
- Bring-up tools, each a separate FPGA design loaded over JTAG:
  - [`../input-check/`](../input-check/): checks the wiring from Michael's VIA to the FPGA, end to end.
  - [`../display-probe/`](../display-probe/): checks the display and its wiring without Michael.

![Schematic](../../schematics/michael-fpga-display.svg)

## What Michael's driver expects

There was no schematic for the old board, so its behaviour was worked out from the driver:

| Signal | VIA pin | How the driver uses it | What the FPGA does |
|---|---|---|---|
| D0–D7 | PB0–PB7 | Written before each E pulse, held until after E falls. | Latches the byte on E's rising edge. |
| E | PA0 | One high pulse per byte: `tsb`/`trb` in `gd_send_data`, or `sta PORTA,Y`/`stx PORTA` in the fill loops (a byte every 9 cycles, 4.5 µs at 2 MHz, E high for 2 µs). | One byte per rising edge, taken at E's first high sample. E is filtered: a level must hold for 250 ns, so spikes from switching noise (seen on the board, see [`../bus-check/`](../bus-check/README.md)) aren't strobes. |
| DC | PA5, shared with the LCD's RS and the keyboard's START/ACK | Low for command bytes, raised again only after E falls. | Latched with the byte, because the keyboard interrupt can drive PA5 at any time. |
| CSB | PA1 | Low for a whole session (`gd_select` … `gd_unselect`). | Strobes count only while CSB is low; port B and PA5 carry other traffic otherwise. Display CS is low while CSB is, and until the last byte is out. |
| RSTB | PA2, shared with Michael's LED | `gd_reset` holds it low for 10 ms and waits 120 ms, before `gd_select`. | Drives the display's RESET directly, not gated by CS, and abandons any byte in progress. |
| Backlight | none | Michael has no pin left for it. | The level on the spare buffer input (B5) is copied to the display's LED pin. It's tied high for now. |

## Timing

The FPGA runs from the Cmod's 12 MHz clock and sends SPI mode 0, MSB first, at 6 MHz. That's within the ILI9341's
10 MHz write limit. A byte takes 16 clocks after a 2–3 clock input synchroniser: about 1.5 µs.

Michael's fastest loop sends a byte every 9 CPU cycles, 4.5 µs at 2 MHz. So the interface keeps up with any
CPU clock up to about 5 MHz with no handshake, which is why the buffers only go one way. A faster CPU would need a
faster SPI clock (the Cmod's MMCM can provide one) or a FIFO.

## Building and loading

Needs the [artix7-open-toolchain](https://github.com/pjdennis/artix7-open-toolchain) kit. Either
`source <kit>/env.sh` first, or keep a checkout of the kit next to this repository as
`../fpga-toolchain-research`.

```bash
cd hardware/michael/fpga/spi-display
make            # simulate, then build build/top.bit and the compact build/top.fast.bit
make prog       # load into the FPGA (until power-off)
make flash      # write the Cmod's flash: the interface then starts on its own at power-up
```

The Cmod runs from Michael's 5 V through its VU pin, so USB is only needed for programming.

## Bring-up

1. Wire as in [`WIRING.md`](WIRING.md). With the Cmod on USB, `make flash`: the interface then starts on its own
   at every power-up. LD1 and LD2 stay off and the backlight comes on.
2. Check the inputs: `make -C ../input-check check` uploads a test program to Michael and compares what
   the FPGA sees, wire by wire.
3. Check the display: `make -C ../display-probe probe` reads the display's registers back, initialises it
   exactly as Michael's driver does, and cycles colours. None of this involves Michael.
4. Upload a graphics program built before stage 2 (today's need the [bus design](../bus/)), e.g.
   `michael_graphic_display_test.s` from before commit 8fc84438. LD2 lights while the display is selected,
   and LD1 flashes while bytes go out.

Steps 2 and 3 load their own designs into the FPGA. Power-cycle the Cmod, or `make reset` here, to go back to
the interface in flash.

A display that stays plain white while the probe reports it awake and on is faulty. The first module
tried (a red "240X320 V1.2" board, which had worked before) was such a case. It answered every register read
correctly (ID `00 93 41`, power mode `9C`), and even read back the colours written to its memory. But its
panel never showed anything, whatever the supply or initialisation. An Adafruit module on the same wiring
worked at once.

## Reserved for later

- **Backlight brightness:** drive B5 from a spare output (or PWM it in the FPGA) instead of the tie.
- **Reading the display:** SDO (MISO) is wired to Cmod pin 32. Only the display probe reads it.
- **Touch:** Cmod pins 33–37 are reserved for the touch controller, which isn't connected yet. The FPGA holds
  T_CS high so a connected controller would stay idle.
