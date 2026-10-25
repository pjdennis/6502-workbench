# Michael's SPI interface in logic chips: 2022 to 2025

Michael drives its ILI9341 display, an SPI device, from a VIA: a byte on port B and a strobe, E. Between the
two sat an interface that turns each strobe into eight SPI clocks. From 2022 to 2025 it was designed in logic
chips, four times over: in Logisim and Digital in September 2022 (the board Michael used until 2026), and as a
two-way interface in 74LS chips and then in a GAL20RA10 in October 2025. The FPGA designs that ran alongside
from 2024 are in [`michael-fpga-display-earlier-designs.md`](michael-fpga-display-earlier-designs.md), and the
Cmod A7 replaced the board on 2026-10-03 ([`spi-display`](../hardware/michael/fpga/spi-display/)).

The files are now in [`hardware/michael/spi-interface/`](../hardware/michael/spi-interface/), byte for byte as
found on 2026-10-25, with SVG pictures of the Digital circuits. They came from:

- Windows `Documents/From work computer via tesla drive/Phil/Misc/Personal/`: the 2022 Logisim and Digital files,
  the CUPL export and `test.v` (the 2024 copies in the Ubuntu install's `Documents/digitaldisplaydriver/` are
  identical);
- Windows `Documents/PS2 Keyboard and mouse interface/SPI Interface/`: the 2025 KiCad project;
- `~/research/pld/` (WSL, its own git repository): the GAL design; `~/research/GALasm/examples/test/`: the GAL
  bring-up files.

**Not found:** notes of logic equations worked by hand to minimise the interface. Text, Markdown, Office and
OneNote files were searched in WSL's home directory, the copy of the external drive and Windows `Documents`,
`Desktop`, `Downloads` and OneDrive, for the designs' signal names (BRST, srS1, MISOr, 74HC299 and others).
What survives of the minimising is in the designs themselves: Digital's CUPL export (2022) and the
GAL equations' history (2025).

## Timeline

| Date | What | Files |
|---|---|---|
| 2022-09-13 | The interface in Logisim: one flat circuit of D flip-flops and gates | `logisim/SPI.circ` |
| 2022-09-15 | Logisim again, with sub-circuits for the 4017 counter and the shift register | `logisim/SPI2.circ`, `SPI3.circ` |
| 2022-09-15 | A 74299 for reading MISO back, tried in Logisim and in Digital | `logisim/299.circ`, `digital/shtest.dig` |
| 2022-09-15 | The circuit in Digital, with a 4017 of its own and the 74299 read path | `digital/D-SPI.dig`, `e-4017.dig` |
| 2022-09-16 08:20 | Active-low E, Digital's 74HC4017, and a test, which passes | `digital/D-SPI2.dig` |
| 2022-09-16 08:42 | One of D-SPI2's functions exported to CUPL for a GAL16V8 | `digital/CUPL_D-SPI2/CUPL.PLD` |
| 2022-09-16 09:32 | A state machine from Digital: E starts a burst of SCLK, then waits for E to fall | `digital/test.v` |
| 2022-09-16 | `hello_michael_spi.s` committed (13:31), then `graphics_display.inc` (19:46): the board is in use | [`firmware/programs/michael/hello_michael_spi.s`](../firmware/programs/michael/hello_michael_spi.s) |
| 2024-10-15 | The write-only circuit, exported to Verilog for the first FPGA try | `digital/D-SPI-WriteOnly.dig`, `.v` |
| 2025-10-03/04 | "Bidirectional SPI interface" rev 0.1 in 74LS chips, drawn in KiCad overnight | `kicad/SPI Interface.kicad_sch` |
| 2025-10-04 | GAL20RA10 bring-up: GALasm and the TL866II+ programmer, register by register | `gal/bring-up/` |
| 2025-10-04 to 10 | The same interface in a GAL20RA10 and a 74HC299 | `gal/spi-control.pld` |
| 2025-10-11 | minipro: "Fix bit order for gal20ra10 negation flags" (`~/research/minipro`, `366c50f`) | — |
| 2026-10-03 | The Cmod A7 replaces the 2022 board | [`fpga/spi-display/`](../hardware/michael/fpga/spi-display/) |

## 2022: the board Michael used

The circuit is a 74HC165 shift register and a 4017 decade counter, clocked by Michael's CPU clock. While the
counter is at 0 the '165 follows port B. E starts the count, SCLK is the CPU clock for counts 1 to 8, and the
counter waits at 9 until E falls. [`michael-fpga-display-earlier-designs.md`](michael-fpga-display-earlier-designs.md#the-74-series-circuits)
describes it, and what went wrong when it was put in an FPGA.

The dates now tie it to the board: the Digital files are from 15 and 16 September 2022, and Michael's first
SPI program was committed at 13:31 on the 16th. The board was the write-only part: the driver has only ever
written, with E active high, as in `D-SPI.dig` and `D-SPI-WriteOnly.dig` (`D-SPI2.dig` has E active low). So
the 74299 read path (`D-SPI.dig`, `D-SPI2.dig`) went unused, if it was built at all.

Two files from the morning of the 16th look like the first attempts to shrink the logic:

- **`CUPL_D-SPI2/CUPL.PLD`**: Digital's export of one combinational function, Y of five inputs (A, B, C, E, F),
  as a sum of six products for a GAL16V8. Digital's analysis renamed the signals, so which part of D-SPI2 it
  is isn't recorded.
- **`test.v`**: Digital's Verilog of a state machine it synthesised (its `Z_n` state names): three flip-flops,
  inputs E and the clock, output SPICK. E starts two SCLK pulses at half the clock rate, and the machine then
  waits until E falls (checked by simulation). It's the shape of the 2025 designs, with a burst of two.

`logisim/299.circ` names a Logisim 74x299 library (`Logisim/74x299.circ`, one of several downloaded 7400
libraries) that isn't committed here. The '299 it uses is its own sub-circuit.

## 2025: two-way, in 74LS chips

A KiCad schematic, rev 0.1, dated 2025-10-04: a 74LS74, 74LS08 ×2, 74LS32, 74LS04, a 74LS163 counter and a
74LS299, with connectors for the data (d0–d7), the controls (CLK, E, /RST) and SPI (SCLK, MOSI, MISO). The
sheet describes it:

> Supports SPI mode 0 as a master.
> - While E is low, data is loaded on every rising edge of CLK
> - When E goes high, data is clocked out of MOSI and into MISO
> - If E remains high after 8 clocks, received data is output until E goes low
> - If E goes low before 8 clocks then received data is not output

There's no `~read` connector: the read strobe is internal, and it turns the '299's outputs onto the data lines.
The PCB file has the footprints placed but no tracks: the board was never routed.

The logic, from the schematic's netlist (KiCad wasn't available, so the netlist was extracted from the file;
every junction of wires has its dot, so it isn't ambiguous):

| Signal | Logic |
|---|---|
| BRST (74LS74 2Q) | D = (BRST + E) · /TC, clocked by CLK; cleared by /RST |
| SCLK | /CLK · BRST |
| MISOr (74LS74 1Q) | MISO, clocked by SCLK; cleared by /RST |
| Counter ('163) | loads 8 when (E · /BRST · /TC) + (/E · TC); counts when CEP = **/BRST** · /TC; TC at 15 |
| read (the '299's S0 and output enables, active low) | /BRST · TC |
| '299 S1 | /BRST · /read |
| '299 | MOSI from Q7; MISOr into DS0 (and DS7); clocked by CLK |

**It doesn't work as drawn.** The counter's count enable is gated by /BRST, the flip-flop's inverted output,
so the counter stands still at 8 during a burst, TC never comes, and SCLK never stops. Fed from BRST instead
(one wire, U5 pin 1 from U1 pin 9 instead of pin 8), a gate-level simulation of the netlist behaves as the
sheet says: E loads 8 and starts the burst, the count runs 8 to 15 (eight SCLK pulses), and at 15 the burst
ends. If E is still high, the '299 holds the received byte with its outputs on, until E falls. When E falls
the counter reloads 8. All the backups from the night (01:27 to 08:00 on 4 October) have the same wiring.

## 2025: the same in a GAL20RA10

The next day the glue logic went into a GAL20RA10, leaving the 74HC299. The 20RA10 suits it: every output has
its own register with a product-term clock, and an asynchronous reset and preset.

**Bring-up first (4 October).** `gal/bring-up/` holds the day's test designs, assembled with GALasm
(`~/research/GALasm`, daveho/GALasm with the fixes made for this work in 2022–2023) and programmed with
minipro on a TL866II+ (its GAL20RA10B support was added to minipro for this work in 2022, `c2718bf`).
`my_20ra10.pld` (combinational, "tested OK"),
`my_20ra10_sequential*.pld` and `try_01` to `try_07` (registered outputs, an inverted clock, then asynchronous
reset and preset, never both at once) built up to the registered features the interface needs. The readbacks
compared along the way (`before-2`, `after-3` and so on) stayed in `~/research/GALasm/examples/test/`.
A week later, minipro got "Fix bit order for gal20ra10 negation flags" (2025-10-11).

**The design, `gal/spi-control.pld`.** Its history is in `~/research/pld`:

| Commit | When | Change |
|---|---|---|
| `707836c` | 10-04 23:59 | First version: a 3-bit counter (C0–C2), burst (nBRST) and wait (nWAIT) registers, SCLK, MISOr |
| `609fcce` | 10-05 00:17 | `program-spi.sh`: `minipro -p GAL20RA10B -P -w spi-control.jed` |
| `0adca39` | 10-05 00:23 | srS1, the '299's S1; comments |
| `c9d192c` | 10-05 00:51 | /RST, a synchronous reset in every register |
| `af84dfd`, `0c8efef`, `38ee59d` | 10-05 00:57–01:05 | The active-low signals as GALasm's `/X` instead of `nX` |
| `c97edf2` | 10-05 01:30 | "Shift register S0 and output enable – fix for them going low too soon": a separate srS0OE output. (`Documents/spi-control.pld` on Windows is this version.) |
| `3ddabaa`, `c1cf844` | 10-06 23:03 | "Simplify logic": WAIT becomes OUTPUT, which drives S0 and the output enable itself; the counter and BRST outputs active low |
| uncommitted | 10-10 | /dBRST, BRST delayed outside the GAL, gates SCLK. The committed `spi-control.jed` is built from this version (reassembled on 2026-10-25: identical). |

How it works: BRST is set on a rising CLK (Phi2) when E is high, OUTPUT is clear and the count is 0, and holds
while the count runs 0 to 7. SCLK is /CLK · dBRST, so its eight pulses are the CPU clock's low halves. MISOr
samples MISO on SCLK's rising edge, and the '299 shifts it in on the next rising CLK, while Q7 shifts out on
MOSI. At the count of 7, if E is still high, OUTPUT is set: the '299 holds (S0 = S1 = 0) and drives the byte
onto the data lines until E falls. The '299 loads from the data lines on every clock while idle. A simulation
of the equations with a '299 and a mode 0 device sends 0x3C and holds 0xA5 for reading. With a short E the byte
still goes out and nothing is held.

Notes on it, from the review of 2026-10-25:

- **The 74LS design's counter fault isn't here.** The GAL design counts only during the burst from its first
  version.
- **E is sampled on Phi2.** Unlike the 2022 board and the first FPGA design, a spike on E can't start a
  byte between clock edges.
- **dBRST.** In the GAL, the rising CLK reaches SCLK's AND term through the array as BRST's register does
  through its product-term clock, with similar delays. If BRST arrived first, SCLK would show a runt pulse as a
  burst begins. Delaying BRST outside the chip (pin 17 to pin 5) removes the race. What made the delay isn't
  recorded.
- **A second strobe during a burst is lost.** If E rises again before the burst ends, it's taken as "hold the
  byte". Strobes must be at least nine clocks apart, as on the 2022 board.
- **Port B when reading.** The '299 drives the data lines from the end of the burst while E is high. Michael
  must turn port B to input before then.
- **Tie pin 1 (/PL) high and pin 13 (/OE) low**, and take /RST from the 6502's reset.
- **No chip select.** It's left to a separate VIA pin.
- **Stale comments.** The description says 74HC922 (the S0/S1 table is the 74HC299's) and names
  `WAITsrS0OE`, now /OUTPUT.

Whether a GAL was programmed with the final version and tried on a board isn't recorded, nor what the two-way
interface was for (the display, which can be read, or another SPI device).

## The files

[`hardware/michael/spi-interface/`](../hardware/michael/spi-interface/) lists them and how to open them.
