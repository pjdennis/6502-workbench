#ifndef EMULATOR_CHIPS_BBC_MODULE_H
#define EMULATOR_CHIPS_BBC_MODULE_H

#include <stdint.h>
#include "../bus.h"

/* A banked ROM module in one BBC sideways ROM socket. A ROM socket has
 * no write line, so the module switches banks on reads of addresses at
 * the top of its 16 KB window ($8000-$BFFF; offset = address - $8000):
 *
 * BBC_MODULE_CC128: the Computer Concepts 128K ROM carrier (SpellMaster,
 *   1987), eight banks, as MAME's bbc_ccispell_device
 *   (src/devices/bus/bbc/rom/pal.cpp) models it. On every read: offset
 *   $3FE0 selects bank 0; otherwise, only while the bank is 0, a read in
 *   $3FC0-$3FDF selects bank 1, $3FA0-$3FBF bank 2, ... $3F00-$3F1F
 *   bank 7. The byte returned comes from the bank selected after the
 *   switch.
 * BBC_MODULE_DIRECT16: this project's own design in the same manner,
 *   sixteen banks: a read of offset $3FF0+n selects bank n, from any
 *   bank; no other address switches. The byte returned comes from the
 *   newly selected bank.
 * BBC_MODULE_DIRECT8: the same scheme for one 128 KB EPROM, eight banks:
 *   a read of offset $3FF0+n selects bank n (0 to 7), from any bank, and
 *   $3FF8-$3FFF mirror $3FF0-$3FF7 (the latch takes A0-A2 and the decode
 *   ignores A3), so a read of $3FF0+n selects bank n AND 7 for n 0 to 15.
 *
 * Writes never switch. In the ROM form they are ignored; in the RAM form
 * (the developer's module holding RAM) they write the selected bank.
 *
 * On the bus the chip claims $8000-$BFFF only while bus->romcs is set:
 * the B+ decode (bbc_memory.h) sets it when the module's slot is
 * selected and the private RAM does not cover the address. */

#define BBC_MODULE_BANK_SIZE 0x4000
#define BBC_MODULE_MAX_BANKS 16
#define BBC_MODULE_MAX_SIZE (BBC_MODULE_MAX_BANKS * BBC_MODULE_BANK_SIZE)

enum bbc_module_scheme { BBC_MODULE_CC128, BBC_MODULE_DIRECT16, BBC_MODULE_DIRECT8 };

struct bbc_module_state {
    uint8_t data[BBC_MODULE_MAX_SIZE];
    enum bbc_module_scheme scheme;
    int ram;            /* the RAM form: writes land in the selected bank */
    uint8_t bank;       /* the selected bank */
    uint64_t switches;  /* reads that changed the bank */
};

/* Banks the scheme has: 8 (cc128, direct8) or 16 (direct16). */
/* Its name: "cc128", "direct16" or "direct8". */
const char *bbc_module_scheme_name(enum bbc_module_scheme scheme);

int bbc_module_banks(enum bbc_module_scheme scheme);

/* Empty module (all bytes $FF in the ROM form, as an erased EPROM; 0 in
 * the RAM form), bank `bank` selected. */
void bbc_module_init(struct chip *chip, struct bbc_module_state *state,
                     enum bbc_module_scheme scheme, int ram, int bank);

/* Wire chip to an existing module, leaving its contents and bank. */
void bbc_module_chip(struct chip *chip, struct bbc_module_state *state);

/* Load an image, bank 0 first, up to the scheme's size. Returns the
 * bytes loaded, -1 if the file can't be read, -2 if it is too large. */
long bbc_module_load(struct bbc_module_state *state, const char *path);

/* A read of window offset 0..$3FFF, switching as the scheme does. */
uint8_t bbc_module_read(struct bbc_module_state *state, uint16_t offset);

/* A write of window offset 0..$3FFF: the selected bank in the RAM form,
 * nothing in the ROM form; never switches. */
void bbc_module_write(struct bbc_module_state *state, uint16_t offset, uint8_t data);

#endif
