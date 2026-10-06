# The pins of the designs on the FPGA bus (bus/, bus-check/): spi-display's pin file, with its pins named
# for what they carry on the bus since stage 4's pin shuffle (docs/michael-fpga-bus-plan.md): RSTB's pin
# (Cmod 11) carries E from PA2, DC's is RS, and E's old pin (Cmod 9), CSB's (10) and the backlight input (13)
# are unused (pio9, pio10, backlight_tie); then the Cmod's USB serial port and the bus's own pins. Include
# after XDC is set.
$(if $(XDC),,$(error bus.mk: set XDC before including it))
BUS_MK := $(lastword $(MAKEFILE_LIST))
BUS_MK_DIR := $(dir $(BUS_MK))
$(XDC): $(BUS_MK_DIR)spi-display/constr/cmod_a7.xdc $(BUS_MK_DIR)constr/uart.xdc $(BUS_MK_DIR)constr/bus.xdc $(BUS_MK)
	@mkdir -p $(dir $@)
	sed 's/{e}/{pio9}/; s/{rstb}/{e}/; s/{dc}/{rs}/; s/{csb}/{pio10}/; s/{bl}/{backlight_tie}/' $(filter %.xdc,$^) > $@
