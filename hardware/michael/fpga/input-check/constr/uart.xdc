
# Cmod A7 USB serial port (FT2232H channel B); names are from the host's point of view
set_property -dict { PACKAGE_PIN J18 IOSTANDARD LVCMOS33 } [get_ports {uart_rxd_out}]
set_property -dict { PACKAGE_PIN J17 IOSTANDARD LVCMOS33 } [get_ports {uart_txd_in}]
