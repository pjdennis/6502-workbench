// The Cmod A7's clock, and the rate of its USB serial port to the PC, for the designs here. The host tools
// open the port at the same rate (the kit's scripts/uart_check.py).
`ifndef CMOD_A7_VH
`define CMOD_A7_VH
`define CMOD_CLK_HZ 12_000_000
`define PC_BAUD     115_200
// Clocks per bit at a baud rate, rounded: 104 at 115200
`define CLKS_PER_BIT(baud) ((`CMOD_CLK_HZ + (baud) / 2) / (baud))
`endif
