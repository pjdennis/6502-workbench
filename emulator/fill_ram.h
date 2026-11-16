#ifndef EMULATOR_FILL_RAM_H
#define EMULATOR_FILL_RAM_H

#include <stddef.h>
#include <stdint.h>

#include "chips/bbc_memory.h"
#include "chips/bbc_module.h"

/* --fill-ram: every machine starts with RAM that is not 0, as a real one
 * does, so that a program which reads a variable before it writes it fails
 * here and not on the board (emulator/README.md, "--fill-ram").
 *
 * The pattern is a hash of each byte's place in the machine's RAM (its
 * physical address, so every bank differs): no byte is 0, every other
 * value occurs, neighbours seldom agree, and it is the same on every run,
 * so a failure can be repeated. Only RAM is filled; ROM, the MOS, I/O,
 * empty slots and what the loader writes afterwards (the program, the
 * stubs, the arguments) are not. Without the option nothing changes. */

/* The byte at place `where`: never 0 */
uint8_t fill_ram_byte(uint32_t where);

/* ram[i] = fill_ram_byte(first + i) for i < size */
void fill_ram(uint8_t *ram, size_t size, uint32_t first);

/* The default machine: all 64K but the I/O ports $F000-$F005 and $FFE0-$FFFF
 * (the high ports and the vectors), which stay as they are */
void fill_ram_default(uint8_t *memory);

/* The B+128: main RAM, the private RAM and every sideways RAM slot (call it
 * after the slots' kinds are set and before ROM images are loaded) */
void fill_ram_bbc(struct bbc_memory_state *mem);

/* The module in its RAM form (call it before --bbc-module preloads it); the
 * ROM form is left as it is */
void fill_ram_bbc_module(struct bbc_module_state *module);

/* Where each part of a machine's RAM starts in the places fill_ram_byte
 * takes, so that no two parts hold the same bytes */
#define FILL_RAM_BBC_PRIVATE  0x10000u
#define FILL_RAM_BBC_SLOTS    0x20000u    /* + slot * BBC_SLOT_SIZE */
#define FILL_RAM_BBC_MODULE   0x100000u

#endif
