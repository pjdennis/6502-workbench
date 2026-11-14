#ifndef EMULATOR_CHIPS_BBC_MEMORY_H
#define EMULATOR_CHIPS_BBC_MEMORY_H

#include <stdint.h>
#include "../bus.h"

/* The BBC Model B+128's memory map, as far as a batch tool sees it:
 *
 *   $0000-$7FFF  main RAM (32 KB; the shadow screen RAM is not modelled)
 *   $8000-$BFFF  the sideways window: the slot ROMSEL selects. With
 *                ROMSEL bit 7 set, $8000-$AFFF is the B+'s 12 KB private
 *                RAM and only $B000-$BFFF shows the selected slot.
 *   $C000-$FBFF  the MOS ROM
 *   $FC00-$FEFF  I/O: only ROMSEL is modelled, write only, at $FE30 and
 *                its mirror $FE38 (bits 0-3 the slot, bit 7 the private
 *                RAM); other reads find the open bus and other writes
 *                are dropped ($FE34, the shadow screen select, too)
 *   $FF00-$FFFF  the MOS ROM
 *
 * Each of the sixteen slots is empty (reads find the open bus), a 16 KB
 * ROM image, 16 KB of sideways RAM (written through the window while its
 * slot is selected) or the banked module (chips/bbc_module.h), which is
 * a chip of its own: bbc_memory_decode() sets bus->romcs for an access
 * the module must answer, and the module chip goes on the bus ahead of
 * this one. "The open bus" is the last byte the data bus carried, which
 * the machine keeps in open_bus; this chip leaves an empty slot's reads
 * unclaimed so the caller keeps that value. */

#define BBC_SLOTS 16
#define BBC_SLOT_SIZE 0x4000
#define BBC_PRIVATE_RAM_SIZE 0x3000
#define BBC_ROMSEL 0xFE30

enum bbc_slot_kind { BBC_SLOT_EMPTY, BBC_SLOT_ROM, BBC_SLOT_RAM, BBC_SLOT_MODULE };

struct bbc_memory_state {
    uint8_t ram[0x8000];
    uint8_t private_ram[BBC_PRIVATE_RAM_SIZE];
    uint8_t mos[0x4000];
    uint8_t slot[BBC_SLOTS][BBC_SLOT_SIZE];
    uint8_t kind[BBC_SLOTS];        /* enum bbc_slot_kind */
    uint8_t romsel;                 /* the ROMSEL latch, as last written */
    uint8_t open_bus;               /* the last byte on the data bus (kept by the machine) */
};

/* All RAM zero, every slot empty, ROMSEL 0, the MOS ROM zero. */
void bbc_memory_init(struct chip *chip, struct bbc_memory_state *state);

/* Wire chip to an existing memory map, leaving its contents. */
void bbc_memory_chip(struct chip *chip, struct bbc_memory_state *state);

/* Put a ROM image in a slot (up to 16 KB; the rest reads $FF). Returns 0,
 * or -1 if the file can't be read, -2 if it is larger than 16 KB. A slot
 * that is sideways RAM keeps being RAM, with the image in it. */
int bbc_memory_load_rom(struct bbc_memory_state *state, int slot, const char *path);

/* Decode bus->addr (and bus->rwb): bus->romcs is set when the module's
 * slot is selected and the address is in the part of the window it
 * shows. */
void bbc_memory_decode(struct bus *bus, const struct bbc_memory_state *state);

#endif
