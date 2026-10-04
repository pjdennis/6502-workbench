# Michael FPGA SPI display interface: wiring

The FPGA board turns Michael's parallel display writes (VIA port B plus four port A control bits) into SPI
for the ILI9341 240×320 display. It replaces the earlier interface board, which had no schematic. Michael's
firmware (`firmware/lib/graphics/graphics_display.inc`) is unchanged.

```
Michael VIA (5 V) ──► 2 × 74LVC245 (3.3 V, B→A) ──► Cmod A7-35T pins 1–13 ──► FPGA ──► Cmod pins 25–32 ──► ILI9341 display
```

Cmod pin numbers below are the DIP pin numbers printed on the Cmod (1–48; 24 is VU, 25 is GND).
VIA pin numbers are for the 40-pin W65C22.

## Power and ground

| From | To | Notes |
|---|---|---|
| Michael 5 V | 5 V rail | Feeds the 3.3 V regulator (an LM1117T-3.3) and the Cmod (through the diode). 1 µF electrolytic across the rail. |
| Michael GND | GND rails | **Required**: Michael, the '245s, the Cmod and the display must share ground. |
| 5 V rail | Diode (silver band towards the Cmod) → Cmod pin 24 (VU) | As built. The Cmod runs from Michael's supply, so USB is only needed for programming. |
| 3.3 V regulator output | 3.3 V rail | Both '245s' VCC (pin 20) and the display's VCC. **To do:** it measured 4.07 V on 2026-10-03, too high for the Cmod's inputs; see the to-do list in [Michael's schematics](../../schematics/README.md#to-do). |
| Regulator IN and OUT | 10 µF tantalum to GND, each | **To do:** not fitted yet. The LM1117's data sheet asks for them, the output one for stability. |
| GND rail | Cmod pin 25 (GND) | As built. |

## Data buffer (upper 74LVC245)

GND (pin 10) to ground and VCC (pin 20) to 3.3 V, with a 100 nF cap. Since the [stage 1 rewiring](#stage-1-rewiring-for-the-fpga-bus),
the FPGA controls the buffer; every design here holds both pins low (on, Michael to the FPGA):

| Pin | To | Pull |
|---|---|---|
| /OE (19) | Cmod pin 14, `d_oeb` | 10 kΩ to 3.3 V: off while the FPGA isn't configured |
| DIR (1) | Cmod pin 17, `d_dir` | 10 kΩ to ground: Michael to the FPGA by default |

| Michael signal | VIA pin | '245 B side (pin) | '245 A side (pin) | Cmod pin | FPGA signal |
|---|---|---|---|---|---|
| PB0 | 10 | B1 (18) | A1 (2) | 1 | `d[0]` |
| PB1 | 11 | B2 (17) | A2 (3) | 2 | `d[1]` |
| PB2 | 12 | B3 (16) | A3 (4) | 3 | `d[2]` |
| PB3 | 13 | B4 (15) | A4 (5) | 4 | `d[3]` |
| PB4 | 14 | B5 (14) | A5 (6) | 5 | `d[4]` |
| PB5 | 15 | B6 (13) | A6 (7) | 6 | `d[5]` |
| PB6 | 16 | B7 (12) | A7 (8) | 7 | `d[6]` |
| PB7 | 17 | B8 (11) | A8 (9) | 8 | `d[7]` |

## Control buffer (lower 74LVC245)

Same power connections as the data buffer; DIR (pin 1) and /OE (pin 19) to ground (always on, Michael to the FPGA).

| Michael signal | VIA pin | '245 B side (pin) | '245 A side (pin) | Cmod pin | FPGA signal |
|---|---|---|---|---|---|
| PA0, `GD_E` (byte strobe), with **10 kΩ to ground** | 2 | B1 (18) | A1 (2) | 9 | `e` |
| PA1, `GD_CSB` (select, active low) | 3 | B2 (17) | A2 (3) | 10 | `csb` |
| PA2, `GD_RSTB` (reset, active low; shared with Michael's LED) | 4 | B3 (16) | A3 (4) | 11 | `rstb` |
| PA5, `GD_DC` (data/command; shared with LCD RS, keyboard START/ACK) | 7 | B4 (15) | A4 (5) | 12 | `dc` |
| **Backlight**: for now, **10 kΩ to the 3.3 V rail** (on) | — | B5 (14) | A5 (6) | 13 | `bl` |
| PA4, SOEB (the keyboard board's output enable), for the bus's interlock | 6 | B6 (13) | A6 (7) | 18 | `soeb` |
| PA6, RW (shared with LCD R/W, keyboard PARITY), for the bus | 8 | B7 (12) | A7 (8) | 19 | `rw` |
| unused: 10 kΩ tie to ground | — | B8 (11) | A8 | — | — |

The display's backlight input is active high, so tying B5 high keeps the backlight on. The FPGA copies it to
the display's LED pin, so later a VIA output or PWM source can drive B5 instead with no other change.

SOEB and RW are unused by the display interface; the FPGA bus's designs (from [`../bus-check/`](../bus-check/))
read them. The pull-down on B1 keeps E low while the VIA's pins are inputs after a reset, so the FPGA sees
no stray strobes.

## Display (ILI9341, SPI)

Connect the display by signal. Modules name the pins differently: the second column gives the names on
Adafruit's ILI9341 breakouts. The red "240X320 V1.2" modules have the pins in this table's order along
their header (VCC end first). With one of those, put the VCC/GND end towards the Cmod's USB end, so the
wires run in order to Cmod pins 25 upwards.

| Display signal | Adafruit | Connect to | Cmod pin | FPGA signal | Direction (FPGA) |
|---|---|---|---|---|---|
| VCC | Vin | **3.3 V rail** | — | — | — |
| GND | GND | GND | 25 | — | — |
| CS | CS | Cmod | 26 | `lcd_cs` | out |
| RESET | RST | Cmod | 27 | `lcd_reset` | out |
| DC | D/C | Cmod | 28 | `lcd_dc` | out |
| SDI (MOSI) | MOSI | Cmod | 29 | `lcd_mosi` | out |
| SCK | CLK | Cmod | 30 | `lcd_sck` | out |
| LED (backlight, active high) | Lite | Cmod | 31 | `lcd_led` | out |
| SDO (MISO) | MISO | Cmod | 32 | `lcd_miso` | in: read by the [display probe](../display-probe/), not by the interface |

The touch controller (T_CLK, T_CS, T_DIN, T_DO, T_IRQ) is not connected. Cmod pins 33–37 are reserved for
it, and the interface holds T_CS high (idle) and T_CLK and T_DIN low.

Both kinds of module work from 3.3 V. Each has its own regulator, so they also take 5 V, but the red
modules only while their jumper J1 is open.

## Before powering up

- [ ] Every '245 B-side input goes either to a Michael signal or to a 10 kΩ tie; none floating.
- [ ] The data buffer's /OE has its pull-up to 3.3 V and its DIR its pull-down.
- [ ] Nothing at 5 V connects directly to a Cmod pin. Michael signals reach the Cmod only through '245 A outputs.
- [ ] Michael and this board share ground.
- [ ] The display's VCC is on 3.3 V and its GND on Cmod pin 25 / the GND rail.
- [ ] The FPGA has the interface design in its flash (`make flash` in this directory). Otherwise the Cmod's
      pins carry whatever design is in its flash.

## Stage 1 rewiring for the FPGA bus

Step 2 of stage 1 in [`docs/michael-fpga-bus-plan.md`](../../../../docs/michael-fpga-bus-plan.md). **Done
(2026-10-03)**: the tables above and Michael's schematics show the result. The FPGA designs here drove Cmod
pin 14 (`d_oeb`) and pin 17 (`d_dir`) low first, which is what the data buffer's /OE and DIR were tied to, so
the display kept working through each step.

With Michael and the Cmod powered off:

- [x] Data buffer /OE (pin 19): remove its link to ground, wire it to **Cmod pin 14**, and add **10 kΩ to the
      3.3 V rail**. The pull-up keeps the buffer off while the FPGA isn't configured.
- [x] Data buffer DIR (pin 1): remove its link to ground, wire it to **Cmod pin 17**, and add **10 kΩ to ground**.
      The pull-down keeps the buffer pointing from Michael to the FPGA.
- [x] Control buffer B6 (pin 13): remove its 10 kΩ tie and wire it to **PA4** (VIA pin 6, SOEB). Wire A6 (pin 7)
      to **Cmod pin 18**.
- [x] Control buffer B7 (pin 12): remove its 10 kΩ tie and wire it to **PA6** (VIA pin 8, RW). Wire A7 (pin 8)
      to **Cmod pin 19**.
- [x] Control buffer B1 (pin 18, PA0, E): add **10 kΩ to ground**, so E idles low while the VIA's pins are inputs.

Then power up and run `michael_graphic_display_test.s`: the display should work exactly as before.
