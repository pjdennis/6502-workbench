# Michael's FPGA display interface: the designs before 2026

Before [`spi-display`](../hardware/michael/fpga/spi-display/) (2026-10-03), two FPGA designs for the Cmod A7
were tried in place of the SPI display's 74-series interface board. Both were built in Vivado on a separate
Ubuntu install and were never in this repository. Both worked in part. They were reviewed on 2026-10-25, and
the second was run again on today's board.

The files are on that install, under `/home/phil`:

| What | Where |
|---|---|
| The 74-series circuits, in the [Digital](https://github.com/hneemann/Digital) simulator | `Documents/digitaldisplaydriver/`: `D-SPI.dig`, `D-SPI2.dig`, `D-SPI-WriteOnly.dig`, `e-4017.dig`. Now in [`hardware/michael/spi-interface/digital/`](../hardware/michael/spi-interface/digital/), from the 2022 originals ([`michael-spi-interface-logic-designs.md`](michael-spi-interface-logic-designs.md)) |
| The October 2024 design | `Documents/FPGA/graphics-spi/` (`graphics-spi-backup-74-series-emu/` is the same project) |
| The April 2025 design | `fpga/graphics-spi-native-verilog/` (11 April); `Documents/FPGA/graphics-spi-native-verilog/` is the 7 April copy, at 40 MHz |

## The 74-series circuits

A 74HC165 shift register and a 4017 decade counter, clocked by Michael's CPU clock (CK). While the counter is
at 0, the '165 follows port B. E starts the count, and SPICLK is CK for counts 1 to 8: a byte goes out at
2 MHz, MSB first. The counter then waits at 9 until E falls. `D-SPI.dig` and `D-SPI2.dig` add a 74299 that
shifts MISO in and drives port B while ~RD is low. `D-SPI2.dig` has active-low E, Digital's own 74HC4017 and
the only test (it passes, and covers writes only). These are the design of the interface board that the
spi-display README says had no schematic: the originals are from 15 and 16 September 2022, the day Michael's
first SPI program was committed ([`michael-spi-interface-logic-designs.md`](michael-spi-interface-logic-designs.md)).

## October 2024: the circuit in the FPGA (`graphics-spi`)

`D-SPI-WriteOnly.dig` exported to Verilog by Digital (exporting it again reproduces the project's file byte for
byte), with a top level that passes CSB, RSTB and DC straight to the display. Digital can't export the read
variants: its 74299 has outputs wired together.

- **E is a clock, unfiltered.** At count 0 the counter's clock is E and not CK, so a spike on E of a few ns
  starts a byte.
- **Nine CK cycles a byte, and no buffer.** A strobe that comes sooner is dropped. Michael's fill loop is
  exactly 9 cycles (the `sta PORTA,Y` that the [FPGA bus plan](michael-fpga-bus-plan.md#follow-ups) noted was
  slowed on purpose); an 8-cycle loop works or loses every other byte, depending on the VIA's output delay.
- Gated clocks, and flip-flops with both asynchronous set and clear (the '165's load), which the FPGA builds
  from latches: Vivado warns about all of them, though its timing checks pass.

**On the board** it partly worked, with slanted characters. In simulation, a spike on E as port B switches
($00 to $FF, between black and white pixels) adds a byte. A glyph column usually has two such changes, so each
column lands a pixel further down the 12-by-16 window than the one before, and the character shears.

## April 2025: hand-written Verilog (`graphics-spi-native-verilog`)

A 128 MHz clock from the MMCM (Vivado's clocking wizard), E through a two-flip-flop synchroniser and taken as a
level, port B loaded when a byte starts, and SPI at 2 MHz (`HALF_PERIOD_CYCLES = 32`). Vivado's build is clean.

- **E isn't filtered.** In simulation 3% of 5 ns spikes start a byte (22% of 50 ns ones). Whether that adds a
  byte or takes the real strobe's place depends on a few ns: the real strobe comes 4.000 µs after port B
  changes, as the spike's byte ends.
- **Strobes less than about 4.25 µs apart are dropped.** At the end of a byte, E high is taken for the strobe
  just sent, not a new one, so an 8-cycle loop loses every other byte.
- DC isn't latched with the byte, and the MMCM's lock is ignored.

The minimal fix is the filter the 2026 designs have ([`level_filter.v`](../hardware/michael/fpga/rtl/level_filter.v)):
E must hold a new level for 250 ns, which costs the 9-cycle loop none of its margin.

**On the board in 2025** it was flaky, with both display modules (the one later found faulty and today's):
slanted characters, and a display that stopped working at random.

**Run again on 2026-10-25** (the April `D_SPI_WriteOnly.v` unchanged, on today's wiring): it worked, with
and without the extra ground wire. Without it, `bus-check`'s `make noise` measured 5,100 glitches a second on
E (6,000 with the data buffer held off). From that rate the simulation predicts a few damaged characters a
line of text; none showed. So the 2025 faults remain unexplained. The rerun differed from 2025 in ways that
might matter:

- No CSB or RSTB, which the wiring hasn't carried since stage 4: the display was selected all the time and reset
  by SWRESET. In 2025 RSTB (PA2, shared with the LED) also reset the design's SPI logic through its
  synchroniser, so a spike on it would have cut a byte short.
- 120 MHz instead of 128: nextpnr-xilinx takes no feedback multiplier above 63, so the divider was 30 to keep
  SPI at 2 MHz.
- The firmware was the driver's pin interface as it has been since 2022 (`gd_send_x2` and the fill loop
  unchanged), with E moved to PA2.

## Lessons, as the 2026 designs apply them

- Filter a strobe from another board: a level must hold before it counts.
- Start on the strobe's edge, not its level, and latch everything that goes with it (DC) as it comes.
- Keep each transfer well inside the fastest strobe rate, or queue them.
