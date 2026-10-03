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

## Troubleshooting

- **The start marker never arrives, and Michael's LCD shows `Ready`:** the upload never reached Michael.
  The upload tools' serial daemon can get stuck; stop it with `python3 tools/upload/transfer.py --daemon stop`,
  and the next upload starts a new one. Auto-detection skips the Cmod's serial ports
  (`tools/upload/ignored-serial-ports.txt`), so Michael's is found even with the Cmod plugged in.
- **The report stalls part-way, or starts with nonsense:** the FPGA may have started with wrong register
  values. That's the JTAG/flash race described in the kit's README ("The JTAG/flash race"): a JTAG load
  restarts the boot from flash, and a fast flash boot can finish first. Bitstreams from kit commit
  `d5dc788` on guard against it. With an older or foreign image in flash, erase the flash first
  (`openFPGALoader -b cmoda7_35t --bulk-erase`), or use `make flash`. Measured here before the fix,
  7 of 12 JTAG loads came up wrong. With a guarded spi-display image in flash, 5 of 5 input checks
  loaded over JTAG passed.
