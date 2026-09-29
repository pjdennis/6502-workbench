# The emulator is built by the repository-level Makefile.

all: emu 00/out/asm_c.out

emu:
	@$(MAKE) -s -C ../.. emulator/emulator.out

clean:
	find . -type d -name "out" -exec rm -rf {} +
	find . -type f -name "*.tmp" -delete

00/out/asm_c.out: 00/asm.c
	@mkdir -p 00/out
	gcc -O2 -o 00/out/asm_c.out 00/asm.c

.PHONY: all emu clean
