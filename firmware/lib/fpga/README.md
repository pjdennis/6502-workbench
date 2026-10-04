# fpga

- `fpga_bus.inc`: the Michael FPGA bus driver: commands, data, reads of the reply queue and the status, over port B with E (PA0) and the LCD's RS and RW. The protocol is in [`docs/michael-fpga-bus-plan.md`](../../../docs/michael-fpga-bus-plan.md). Used by `graphics_display.inc` (the display driver, since stage 2) and by the bus's own programs (`firmware/programs/michael/michael_fpga_bus_*.s`).
