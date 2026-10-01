#ifndef EMULATOR_CHIPS_OSC_H
#define EMULATOR_CHIPS_OSC_H

#include <stdint.h>

#include "../bus.h"

/* OSC chip: holds the crystal frequency. Its tick() does nothing,
 * because bus_step() itself advances bus->osc_ticks; the machines do
 * not register it (emu_wendy2c.c paces from --mhz instead), so it is
 * only exercised by tests/test_chip_osc.c. */
struct osc_state {
    uint64_t frequency_hz;
};

void osc_init(struct chip *chip, struct osc_state *state, uint64_t frequency_hz);

#endif
