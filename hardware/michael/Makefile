# Michael's ROM on its EEPROM (an AT28C256), with a TL866-style programmer and minipro:
#   make rom        build michael_rom.bin: firmware/boards/michael/michael_rom.s, as the firmware manifest records
#                   its build (tools/michael_rom.py; it refuses an image the manifest doesn't record)
#   make program    build it, back up what's on the EEPROM to backups/, then write the image
# MINIPRO_FLAGS adds to minipro's (e.g. --no-write-protect, if the chip has software write protection on).
# The build always runs: it takes a second, and checks the image against the manifest again.

REPO          := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))../..)
ROM           := $(REPO)/hardware/michael/michael_rom.bin
BACKUPS       := $(REPO)/hardware/michael/backups
CHIP          := AT28C256
MINIPRO_FLAGS ?=

.PHONY: rom program
rom:
	python3 $(REPO)/tools/michael_rom.py $(ROM)

program: rom
	mkdir -p $(BACKUPS)
	minipro -p $(CHIP) $(MINIPRO_FLAGS) -r $(BACKUPS)/michael-rom-$$(date +%Y%m%d-%H%M%S).bin
	minipro -p $(CHIP) $(MINIPRO_FLAGS) -w $(ROM)
