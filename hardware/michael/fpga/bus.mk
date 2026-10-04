# The pins of the designs on the FPGA bus (bus/, bus-check/): spi-display's pin file, with its pins named
# for what they carry on the bus (DC is RS; CSB, RSTB and the backlight input, unused, are PA1, PA2 and the
# backlight tie), the Cmod's USB serial port and the bus's own pins. Include after XDC is set.
BUS_MK := $(lastword $(MAKEFILE_LIST))
BUS_MK_DIR := $(dir $(BUS_MK))
$(XDC): $(BUS_MK_DIR)spi-display/constr/cmod_a7.xdc $(BUS_MK_DIR)constr/uart.xdc $(BUS_MK_DIR)constr/bus.xdc $(BUS_MK)
	@mkdir -p $(dir $@)
	sed 's/{dc}/{rs}/; s/{csb}/{pa1}/; s/{rstb}/{pa2}/; s/{bl}/{backlight_tie}/' $(filter %.xdc,$^) > $@
