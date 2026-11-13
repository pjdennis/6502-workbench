# The emulator is built by the repository-level Makefile.

all: emu

emu:
	@$(MAKE) -s -C .. emulator/emulator.out

clean:
	find . -type d -name "out" -exec rm -rf {} +
	find . -type f -name "*.tmp" -delete

.PHONY: all emu clean
