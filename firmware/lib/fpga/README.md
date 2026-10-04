# fpga

- `fpga_bus.inc`: the Michael FPGA bus driver: commands, data, reads of the reply queue and the status, over port B with E (PA0) and the LCD's RS and RW. The protocol is in [`docs/michael-fpga-bus-plan.md`](../../../docs/michael-fpga-bus-plan.md). Used by `firmware/programs/michael/michael_fpga_bus_check.s`; the display driver moves onto it in stage 2 of the plan.
