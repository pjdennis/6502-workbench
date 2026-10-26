# The W5500 Ethernet module on the FPGA bus design (docs/michael-fpga-w5500-plan.md): Cmod pins 48 to 43, nearest
# the module, wired nearest to nearest so the wires nest. Outputs at slow slew and 4 mA, gentle on breadboard
# wires; the inputs pulled up (INTn is open-drain; MISO floats while the W5500 is deselected).
set_property -dict { PACKAGE_PIN V8  IOSTANDARD LVCMOS33 PULLTYPE PULLUP } [get_ports {net_miso}]
set_property -dict { PACKAGE_PIN U8  IOSTANDARD LVCMOS33 SLEW SLOW DRIVE 4 } [get_ports {net_rst_n}]
set_property -dict { PACKAGE_PIN W7  IOSTANDARD LVCMOS33 PULLTYPE PULLUP } [get_ports {net_int_n}]
set_property -dict { PACKAGE_PIN U7  IOSTANDARD LVCMOS33 SLEW SLOW DRIVE 4 } [get_ports {net_cs_n}]
set_property -dict { PACKAGE_PIN U3  IOSTANDARD LVCMOS33 SLEW SLOW DRIVE 4 } [get_ports {net_sclk}]
set_property -dict { PACKAGE_PIN W6  IOSTANDARD LVCMOS33 SLEW SLOW DRIVE 4 } [get_ports {net_mosi}]
