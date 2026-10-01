/* OSC chip (see osc.h). */
#include "osc.h"

#include <stddef.h>

static void osc_tick(struct chip *self, struct bus *bus) {
    (void)self;
    /* Nothing to do: bus_step() increments bus->osc_ticks itself. The
     * machines (emu_wendy2c.c, emu_michael.c) do not register this chip;
     * it only holds a frequency and is exercised by test_chip_osc.c. */
    (void)bus;
}

void osc_init(struct chip *chip, struct osc_state *state, uint64_t frequency_hz) {
    static const struct chip_ops ops = {
        .tick  = osc_tick,
        .read  = NULL,
        .write = NULL,
        .reset = NULL,
    };
    state->frequency_hz = frequency_hz;
    chip->ops = &ops;
    chip->name = "osc";
    chip->state = state;
}
