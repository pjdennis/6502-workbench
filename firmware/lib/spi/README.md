# `spi/`

Michael's SPI devices through the GAL20RA10 interface ([`hardware/michael/spi-interface/`](../../../hardware/michael/spi-interface/)),
with the FPGA board unplugged. Each file's header says what it requires.

| File | What |
|---|---|
| `gal_spi.inc` | A byte out, or a byte out and one back, through the GAL and its 74HC299 (E on PA2, port B) |
