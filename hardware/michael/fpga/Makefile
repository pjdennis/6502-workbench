# Tests for the modules the designs share (rtl/), with their testbenches in sim/, and the text mode's (text/):
#   make test
include kit.mk

RTL    := $(wildcard rtl/*.v)
TB_DIR := sim

include $(FPGA_KIT)/mk/sim.mk

.DEFAULT_GOAL := test
.PHONY: test-py
test: test-py

# The text mode's model, and its RTL against the model (text/)
test-py:
	python3 -m unittest discover -s text
