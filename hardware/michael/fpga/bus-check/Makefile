# Bring-up check for the Michael FPGA bus's reads (see README.md): the bus with its control commands, and
# SERIAL_SEND, through which Michael's test program reports to the PC.
#   make test    simulations          make prog    load into the FPGA (the spi-display design stays in flash)
#   make check   quiet Michael, load the design, then upload the Michael test program and check what it
#                and the FPGA report
include ../kit.mk

TOP    := bus_check
RTL    := rtl/bus_check.v ../rtl/michael_bus.v ../rtl/bus_control.v \
          $(addprefix $(FPGA_KIT)/lib/rtl/,uart_tx.v uart_rx.v)
XDC    := build/bus_check.xdc
TB_DIR := sim

include $(FPGA_KIT)/boards/cmod_a7_35t.mk
include $(FPGA_KIT)/mk/sim.mk
include $(FPGA_KIT)/mk/openxc7.mk

$(TB_PASS): ../sim/michael_fpga_bus.vh

# The spi-display pins (its DC is the bus's RS), the Cmod's USB serial port and the bus's own pins
$(XDC): ../spi-display/constr/cmod_a7.xdc ../constr/uart.xdc ../constr/bus.xdc
	@mkdir -p $(dir $@)
	sed 's/{dc}/{rs}/' $^ > $@

.DEFAULT_GOAL := all
.PHONY: all check test-py
all: test bit

test: test-py
test-py:
	python3 -m unittest test_check

# Michael runs an idle program while the design loads, so that nothing from before (a graphics program's
# cursor, say) reaches the counts
check: $(LOAD_BIT)
	python3 ../board.py idle
	$(MAKE) prog
	python3 check.py
