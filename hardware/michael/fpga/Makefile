# Tests for the modules the designs share (rtl/), with their testbenches in sim/:  make test
include kit.mk

RTL    := $(wildcard rtl/*.v)
TB_DIR := sim

include $(FPGA_KIT)/mk/sim.mk

.DEFAULT_GOAL := test
