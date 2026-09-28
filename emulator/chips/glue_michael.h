#ifndef EMULATOR_CHIPS_GLUE_MICHAEL_H
#define EMULATOR_CHIPS_GLUE_MICHAEL_H

#include "../bus.h"

/* Michael's glue logic: Ben Eater's NAND-gate address decode and a
 * CPU clock that is the oscillator itself.
 *
 *   $0000-$3FFF  RAM   (A15 low, A14 low)
 *   $4000-$5FFF  nothing
 *   $6000-$7FFF  VIA   (A15 low, A14 high, A13 high; registers mirror
 *                every 16 bytes)
 *   $8000-$FFFF  ROM   (A15 high)
 *
 * Each tick asks the CPU for a cycle. Register it first so the VIA and
 * CPU see the cycle in the same tick. */

struct glue_michael_state {
    int dummy;
};

void glue_michael_init(struct chip *chip, struct glue_michael_state *state);

/* Set ROMCS, RAMCS and VIACS for bus->addr. */
void glue_michael_decode(struct bus *bus);

#endif
