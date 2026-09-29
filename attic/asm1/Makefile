all: emulator.out sidebyside.out asm4v.out

clean:
	rm -f *.out
	rm -f *.bin

emulator.out: emulator.c
	gcc -O2 -march=native -flto -DNDEBUG -o emulator.out emulator.c

sidebyside.out: sidebyside.cpp
	g++ -O2 -march=native -flto -DNDEBUG -o sidebyside.out sidebyside.cpp

asm4v.out: asm4v.asm
	vasm6502_oldstyle -quiet -wfail -Fbin -dotdir -esc -o asm4v.out asm4v.asm

