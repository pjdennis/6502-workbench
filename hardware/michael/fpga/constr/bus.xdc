# The Michael FPGA bus pins beyond the spi-display interface's (docs/michael-fpga-bus-plan.md, stage 1 wiring)
set_property -dict { PACKAGE_PIN N3  IOSTANDARD LVCMOS33 } [get_ports {soeb}]
set_property -dict { PACKAGE_PIN P3  IOSTANDARD LVCMOS33 } [get_ports {rw}]
