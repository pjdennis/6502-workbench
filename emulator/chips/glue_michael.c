#include "glue_michael.h"

#include <stddef.h>

void glue_michael_decode(struct bus *bus) {
    uint16_t a = bus->addr;
    bus->romcs = (a & 0x8000) != 0;
    bus->ramcs = (a & 0xC000) == 0x0000;
    bus->viacs = (a & 0xE000) == 0x6000;
    bus->r_bits = 0;
}

static void glue_michael_tick(struct chip *self, struct bus *bus) {
    (void)self;
    glue_michael_decode(bus);
    bus->cpu_cycle_due = 1;
}

void glue_michael_init(struct chip *chip, struct glue_michael_state *state) {
    static const struct chip_ops ops = {
        .tick  = glue_michael_tick,
        .read  = NULL,
        .write = NULL,
        .reset = NULL,
    };
    chip->ops = &ops;
    chip->name = "glue_michael";
    chip->state = state;
}
