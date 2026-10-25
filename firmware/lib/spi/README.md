# `spi/`

Michael's SPI devices through the GAL20RA10 interface ([`hardware/michael/spi-interface/`](../../../hardware/michael/spi-interface/)),
with the FPGA board unplugged. Each file's header says what it requires.

| File | What |
|---|---|
| `gal_spi.inc` | A byte out, or a byte out and one back, through the GAL and its 74HC299 (E on PA2, port B) |
| `w5500.inc` | The W5500 Ethernet controller on it (chip select on PA0): frames whose header count (`$01 $02 $03` on MISO) is checked, and its common registers |
