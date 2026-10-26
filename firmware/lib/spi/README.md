# `spi/`

Michael's SPI devices through the GAL20RA10 interface ([`hardware/michael/spi-interface/`](../../../hardware/michael/spi-interface/)),
with the FPGA board unplugged. Each file's header says what it requires.

| File | What |
|---|---|
| `gal_spi.inc` | A byte out, or a byte out and one back, through the GAL and its 74HC299 (E on PA2, port B), never letting more than two port B lines fall at once (the board's ground bounce glitches the W5500's chip select) |
| `w5500.inc` | The W5500 Ethernet controller on it (chip select on PA0): frames whose header count (`$01 $02 $03` on MISO) is checked, its common registers, and register reads and writes that check themselves and retry |
| `w5500_registers.inc` | The W5500's control bytes and register names, for its drivers here and on the FPGA bus (`fpga_w5500.inc`) |
