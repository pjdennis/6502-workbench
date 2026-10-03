# Michael's FPGA SPI display interface on a Cmod A7-35T. Wiring: WIRING.md; design notes: README.md.
#   make test    simulations          make bit     build bitstreams
#   make prog    load into the FPGA   make flash   write the Cmod's flash (survives power-off)
# Builds with the artix7-open-toolchain kit (https://github.com/pjdennis/artix7-open-toolchain):
# `source <kit>/env.sh` sets FPGA_KIT; otherwise a checkout next to this repository is used.
FPGA_KIT ?= $(abspath $(CURDIR)/../../../../../fpga-toolchain-research)
ifeq ($(wildcard $(FPGA_KIT)/mk/openxc7.mk),)
$(error FPGA toolchain kit not found at '$(FPGA_KIT)': run `source <kit>/env.sh` or set FPGA_KIT)
endif

TOP    := top
RTL    := rtl/top.v rtl/spi_bridge.v
XDC    := constr/cmod_a7.xdc
TB_DIR := sim

include $(FPGA_KIT)/boards/cmod_a7_35t.mk
include $(FPGA_KIT)/mk/sim.mk
include $(FPGA_KIT)/mk/openxc7.mk

$(TB_PASS): ../sim/michael_via.vh   # shared Michael model, included by the testbench

.DEFAULT_GOAL := all
.PHONY: all
all: test bit
