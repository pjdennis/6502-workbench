# Display probe (see README.md): the FPGA becomes a slow SPI master for the ILI9341, driven from the PC
# over the Cmod's USB serial port, to check the display and its wiring independently of Michael.
#   make test    simulations          make prog    load into the FPGA (the spi-display design stays in flash)
#   make probe   load, read the display's registers, initialise it as Michael's driver does, cycle colours
include ../kit.mk

TOP    := display_probe
RTL    := rtl/display_probe.v $(addprefix $(FPGA_KIT)/lib/rtl/,uart_tx.v uart_rx.v uart_line_tx.v)
XDC    := build/display_probe.xdc
TB_DIR := sim

include $(FPGA_KIT)/boards/cmod_a7_35t.mk
include $(FPGA_KIT)/mk/sim.mk
include $(FPGA_KIT)/mk/openxc7.mk

# The spi-display pins, the USB serial port and the display's SDO (MISO)
$(XDC): ../spi-display/constr/cmod_a7.xdc ../constr/uart.xdc constr/miso.xdc
	@mkdir -p $(dir $@)
	cat $^ > $@

.DEFAULT_GOAL := all
.PHONY: all probe test-py
all: test bit

test: test-py
test-py:
	python3 -m unittest test_probe

probe: prog
	python3 probe.py
