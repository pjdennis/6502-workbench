#ifndef EMULATOR_CHIPS_GLUE_MICHAEL_H
#define EMULATOR_CHIPS_GLUE_MICHAEL_H

#include <string.h>

#include "../bus.h"

/* Michael's glue logic: the address decode and a CPU clock that is the
 * oscillator itself.
 *
 *   $0000-$3FFF  RAM   (A15 low, A14 low)
 *   $4000-$5FFF  nothing
 *   $6000-$7FFF  VIA   (A15 low, A14 high, A13 high; registers mirror
 *                every 16 bytes)
 *   $8000-$FFFF  ROM   (A15 high)
 *
 * with the RAM below the VIA decoded one of these ways (--ram):
 *   16k       as above (the default)
 *   eater     Ben Eater's: the RAM's A14 is grounded and address A14
 *             drives its OE, so reads of $4000-$7FFF find nothing but
 *             writes there land in $0000-$3FFF too (with the VIA's)
 *   full      24K at $0000-$5FFF
 *   mirror8k  8K at $0000-$1FFF, repeated up to $5FFF
 *
 * Each tick asks the CPU for a cycle. Register it first so the VIA and
 * CPU see the cycle in the same tick. */

struct glue_michael_state {
    int dummy;
};

void glue_michael_init(struct chip *chip, struct glue_michael_state *state);

enum glue_michael_ram {
    GLUE_MICHAEL_RAM_16K,
    GLUE_MICHAEL_RAM_EATER,
    GLUE_MICHAEL_RAM_FULL,
    GLUE_MICHAEL_RAM_MIRROR8K,
};

/* The RAM decoding by its --ram name; returns 0, or -1 for an unknown name.
 * (Inline so that cli.c can check the name without linking the glue.) */
static inline int glue_michael_ram_by_name(const char *name, enum glue_michael_ram *ram) {
    static const char *const names[] = {"16k", "eater", "full", "mirror8k"};
    for (int i = 0; i < (int)(sizeof names / sizeof *names); i++) {
        if (!strcmp(name, names[i])) {
            *ram = (enum glue_michael_ram)i;
            return 0;
        }
    }
    return -1;
}

void glue_michael_set_ram(enum glue_michael_ram ram);

/* Set ROMCS, RAMCS, VIACS and the RAM's high address bits for bus->addr
 * and bus->rwb. Returns the address the selected chips see: bus->addr,
 * but for mirror8k's RAM the address without A13 and A14. */
uint16_t glue_michael_decode(struct bus *bus);

#endif
