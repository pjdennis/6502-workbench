# Michael: FPGA bus check

Stage 1 of the [FPGA bus plan](../../../../docs/michael-fpga-bus-plan.md): proves that Michael can read
from the FPGA, through the data buffer that the FPGA now turns around, including when a keyboard interrupt
arrives in the middle of a read (the SOEB interlock). Passed on the board on 2026-10-03: 41,128 reads, 9 of
them paused by keyboard interrupts, every byte right and every transfer accounted for. It needs the stage 1 wiring
([`../spi-display/WIRING.md`](../spi-display/WIRING.md#stage-1-rewiring-for-the-fpga-bus)).

The design is loaded over JTAG (`make prog`), so the design in the Cmod's flash (the [bus design](../bus/)
since stage 2) stays there and comes back at the next power-up.

```
make test     # simulation, and check.py's tests
make check    # load the design, upload the Michael program, and judge what it reports
```

`make noise` measures the switching noise on E: with Michael switching all of port B continuously
([`michael_fpga_bus_noise.s`](../../../../firmware/programs/michael/michael_fpga_bus_noise.s)), it counts the
glitches per second with the data buffer working and then held off (`noise.py`). On 2026-10-04: about 4,000 a
second with it working and 3,200 with it held off, so most of the noise comes from Michael's side of the
buffer (likely the VIA's ground bouncing as port B switches), not from the buffer's fast outputs.

`make check` asks you to hold a key down on Michael's keyboard part-way through, until the program says
`DONE`: about 5 seconds, for 128 keys. Before loading the design, it puts Michael in an idle program
([`michael_fpga_bus_idle.s`](../../../../firmware/programs/michael/michael_fpga_bus_idle.s), E held low), so
that a program still running from before can't add to the design's counts: a graphics program's blinking
cursor once added 395 writes.

## The pieces

- [`../rtl/michael_bus.v`](../rtl/michael_bus.v): the bus's pins as transfers. It turns the data buffer
  around a step at a time, so that neither of its sides ever has two drivers, and gates the buffer's /OE
  with SOEB, pin to pin (one LUT, no clock). E is filtered (a level must hold for 250 ns): on the board, a
  glitch on E once made an extra read.
- [`../rtl/bus_control.v`](../rtl/bus_control.v): the control commands (`NOP`, `ID`, `RESET`, `ECHO`), the
  reply queue, the status byte, and `SERIAL_SEND` (`$50`, provisional), whose bytes go to the PC through the
  Cmod's USB serial port. Both modules carry on into stage 2's design.
- [`rtl/bus_check.v`](rtl/bus_check.v): the two, with the serial port. `?` from the PC adds a line of
  counts, in hex (`C wwww rrrr ...`; the comment at the top of `bus_check.v` has the list): the transfers
  written and read, the reads that the interlock paused, SOEB's falls, and a characterisation of what happens
  on E: glitches the bus filtered out (by E's level, and by what changed just before: D, D7, 4 or more bits
  of D, RS or RW), bounces at E's edges, the writes that were commands, and writes with short E pulses.
  On the board (2026-10-04), with the buffers at 3.3 V, about 500 glitches a run, all short positive spikes
  while E is low just after 4 or more bits of D switch: switching noise, which the filter rejects. LD1 flashes on bus traffic; LD2 lights once a read has been paused.
- [`sim/tb_bus_check.v`](sim/tb_bus_check.v): Michael ([`../sim/michael_fpga_bus.vh`](../sim/michael_fpga_bus.vh),
  with `fpga_bus.inc`'s timings and the keyboard driver's interrupt), the VIA, the keyboard board and the
  data buffer around the design. It checks every command, the status bits, reads across a keyboard
  interrupt, the turnaround's timing, and that no net ever has two drivers.
- [`firmware/lib/fpga/fpga_bus.inc`](../../../../firmware/lib/fpga/fpga_bus.inc): Michael's driver, and
  [`firmware/programs/michael/michael_fpga_bus_check.s`](../../../../firmware/programs/michael/michael_fpga_bus_check.s),
  the test program. It reports each part on the LCD and to the PC:

  | Line | Meaning |
  |---|---|
  | `ID OK` | `ID` replied `M`, `B`, version 2, and the status was clear |
  | `ECHO BAD nnnn` | 32 passes of 256 bytes echoed and read back: nnnn mismatches or status errors, in hex (BUSY, set while the program's report is still going out, isn't an error) |
  | `UNDERFLOW OK` | an empty reply queue read `$00` and set `UNDERFLOW`, which one status read cleared |
  | `HOLD A KEY` | the keyboard is on now: hold a key down until `DONE` |
  | `KEYBOARD BAD nnnn` | more passes, with the keyboard's interrupts landing at random points, until 128 keys have arrived (or about 15 s) |
  | `KEYS nnnn ROUNDS nn` | characters the keyboard driver received meanwhile, and the rounds of 16 passes run |
- [`check.py`](check.py): runs the program and judges its report and the FPGA's counts. It fails if no key
  arrived or if no read was paused, since then the interlock wasn't exercised, and says so if the FPGA never
  saw SOEB fall at all. After a clean run, the FPGA's counts must match the transfers the program made
  exactly; extra writes are split into commands and data. Everything that came from the serial port is
  saved, as it came, in `build/check-serial.log`.
