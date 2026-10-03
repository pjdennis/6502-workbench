# Michael FPGA: input check

Checks the wiring from Michael's VIA through the 74LVC245s to the Cmod (see
[`../spi-display/WIRING.md`](../spi-display/WIRING.md)) before the display is connected.

```bash
cd hardware/michael/fpga/input-check
make check      # load the input-check design into the FPGA, upload the test program to Michael, compare
```

- **FPGA side:** [`rtl/input_check.v`](rtl/input_check.v) reports over the Cmod's USB serial port. It sends
  every settled state of the 13 inputs (held 1 ms; also on `?`), and every byte the spi-display bridge
  latches. Events wait in a block-RAM FIFO, so even Michael's fastest loop is reported in full.
- **Michael side:** [`michael_fpga_input_check.s`](../../../../firmware/programs/michael/michael_fpga_input_check.s)
  walks a one across port B, moves each control line away from idle and back, then sends 322 bytes
  through the display driver.
- **Host:** [`check.py`](check.py) uploads the program (Michael's port is chosen as the upload tools
  usually choose it; `--michael-port` overrides) and compares the report step by step. Any mismatch names
  the wire involved, e.g. `PB1 (Cmod 2) expected 1, got 0`.

A pass ends with `PASS: all 350 steps matched`. `make test` runs the simulation and `check.py`'s unit tests.

## If the report stalls or starts with nonsense: the flash

Loading a design over JTAG (`make prog`) can leave its registers at **wrong initial values** while the
Cmod's flash holds a design that boots quickly. This happens with any design made by the kit's
`make flash`, which boots in about 30 ms. The JTAG load makes the FPGA start booting from flash, and
when that boot finishes first, the JTAG design is written into an already-started FPGA. Here that showed
up as a FIFO whose pointers started 218 entries apart: the report stalled part-way, with lines still
queued.

Measured on this board: with a fast-booting design in flash, 7 of 12 JTAG loads came up with wrong
initial values; with the flash erased, 16 of 16 were right. Booting from flash is always correct.
So for JTAG work:

- erase the flash first (`openFPGALoader -b cmoda7_35t --bulk-erase`), or
- use `make flash` instead of `make prog`, since boots from flash are correct.
