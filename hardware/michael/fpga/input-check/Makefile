# Bring-up check for the spi-display interface's inputs (see README.md): reports, over the Cmod's USB serial
# port, every settled state of the 13 inputs from Michael and every byte the SPI bridge would latch.
#   make test    simulations          make prog    load into the FPGA (the spi-display design stays in flash)
#   make check   upload the Michael test program and compare what the FPGA saw with what it should see
include ../kit.mk

TOP    := input_check
RTL    := rtl/input_check.v ../spi-display/rtl/spi_bridge.v ../rtl/level_filter.v \
          $(addprefix $(FPGA_KIT)/lib/rtl/,uart_tx.v uart_rx.v uart_line_tx.v)
XDC    := build/input_check.xdc
TB_DIR := sim

include $(FPGA_KIT)/boards/cmod_a7_35t.mk
include $(FPGA_KIT)/mk/sim.mk
include $(FPGA_KIT)/mk/openxc7.mk

$(TB_PASS) $(BUILD)/$(TOP).json: ../rtl/cmod_a7.vh

$(TB_PASS): ../sim/michael_via.vh

# The spi-display pins plus the Cmod's USB serial port
$(XDC): ../spi-display/constr/cmod_a7.xdc ../constr/uart.xdc
	@mkdir -p $(dir $@)
	cat $^ > $@

.DEFAULT_GOAL := all
.PHONY: all check test-py
all: test bit

test: test-py
test-py:
	python3 -m unittest test_check

check: prog
	python3 check.py
