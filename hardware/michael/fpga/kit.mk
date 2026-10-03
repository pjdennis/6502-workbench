# Finds the artix7-open-toolchain kit (https://github.com/pjdennis/artix7-open-toolchain) for the designs here.
# `source <kit>/env.sh` sets FPGA_KIT; otherwise a checkout next to this repository is used.
ifndef FPGA_KIT
FPGA_KIT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))../../../../fpga-toolchain-research)
endif
ifeq ($(wildcard $(FPGA_KIT)/mk/openxc7.mk),)
$(error FPGA toolchain kit not found at '$(FPGA_KIT)': run `source <kit>/env.sh` or set FPGA_KIT)
endif
