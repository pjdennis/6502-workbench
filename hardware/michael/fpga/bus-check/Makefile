# Bring-up check for the Michael FPGA bus's reads (see README.md): the bus with its control commands, and
# SERIAL_SEND, through which Michael's test program reports to the PC.
#   make test    simulations          make prog    load into the FPGA (the design in flash returns at power-up)
#   make check   quiet Michael, load the design, then upload the Michael test program and check what it
#                and the FPGA report
include ../kit.mk

TOP    := bus_check
RTL    := rtl/bus_check.v ../rtl/michael_bus.v ../rtl/level_filter.v ../rtl/bus_control.v ../rtl/fifo.v \
          $(addprefix $(FPGA_KIT)/lib/rtl/,uart_tx.v uart_rx.v)
XDC    := build/bus_check.xdc
TB_DIR := sim

include $(FPGA_KIT)/boards/cmod_a7_35t.mk
include $(FPGA_KIT)/mk/sim.mk
include $(FPGA_KIT)/mk/openxc7.mk

$(TB_PASS) $(BUILD)/$(TOP).json: ../rtl/cmod_a7.vh

$(TB_PASS): ../sim/michael_fpga_bus.vh ../sim/michael_board.vh ../sim/host_serial.vh

include ../bus.mk

.DEFAULT_GOAL := all
.PHONY: all check noise test-py
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

# Glitches on E per second with port B switching, with the data buffer working and held off (noise.py)
noise: $(LOAD_BIT)
	python3 ../board.py idle
	$(MAKE) prog
	python3 noise.py
