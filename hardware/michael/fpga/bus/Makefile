# The Michael FPGA bus with the display (stage 2 of docs/michael-fpga-bus-plan.md), replacing spi-display.
#   make test    simulations          make bit     build bitstreams
#   make prog    load into the FPGA   make flash   write the Cmod's flash (survives power-off)
#   debug.py     the debug port: the PC drives the bus (id, status, a display test pattern)
include ../kit.mk

TOP    := top
RTL    := rtl/top.v ../rtl/michael_bus.v ../rtl/level_filter.v ../rtl/bus_control.v ../rtl/fifo.v \
          ../rtl/display_spi.v ../rtl/debug_port.v ../rtl/text_grid.v ../rtl/text_render.v \
          $(addprefix $(FPGA_KIT)/lib/rtl/,uart_tx.v uart_rx.v)
XDC    := build/top.xdc
TB_DIR := sim

include $(FPGA_KIT)/boards/cmod_a7_35t.mk
include $(FPGA_KIT)/mk/sim.mk
include $(FPGA_KIT)/mk/openxc7.mk

$(TB_PASS) $(BUILD)/$(TOP).json: ../rtl/cmod_a7.vh

$(TB_PASS): ../sim/michael_fpga_bus.vh ../sim/michael_board.vh ../sim/host_serial.vh ../sim/ili9341_model.vh

include ../bus.mk
include ../text.mk
$(BUILD)/$(TOP).json: $(FONT_VH)

.DEFAULT_GOAL := all
.PHONY: all test-py
all: test bit

test: test-py
test-py:
	python3 -m unittest test_debug
