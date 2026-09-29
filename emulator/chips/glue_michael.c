#include "glue_michael.h"

#include <stddef.h>

static enum glue_michael_ram ram_decode = GLUE_MICHAEL_RAM_16K;

void glue_michael_set_ram(enum glue_michael_ram ram) {
    ram_decode = ram;
}

uint16_t glue_michael_decode(struct bus *bus) {
    uint16_t a = bus->addr;
    bus->romcs = (a & 0x8000) != 0;
    bus->viacs = (a & 0xE000) == 0x6000;
    bus->r_bits = 0;
    switch (ram_decode) {
    case GLUE_MICHAEL_RAM_16K:
        bus->ramcs = a < 0x4000;
        break;
    case GLUE_MICHAEL_RAM_EATER:
        /* The RAM chip model leaves CPU A14 off, so $4000-$7FFF land in
         * $0000-$3FFF */
        bus->ramcs = bus->rwb ? a < 0x4000 : a < 0x8000;
        break;
    case GLUE_MICHAEL_RAM_FULL:
        bus->ramcs = a < 0x6000;
        bus->r_bits = (uint8_t)((a >> 14) & 1);   /* A14 to the RAM: $4000-$5FFF are its own */
        break;
    case GLUE_MICHAEL_RAM_MIRROR8K:
        bus->ramcs = a < 0x6000;
        if (bus->ramcs) return a & 0x1FFF;
        break;
    }
    return a;
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
