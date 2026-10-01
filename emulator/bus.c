/* Bus: chip registration, read/write dispatch in registration order, and bus_step (see bus.h). */
#include "bus.h"

#include <string.h>

void bus_init(struct bus *b) {
    memset(b, 0, sizeof(*b));
    b->rwb = 1;  /* idle = read */
}

int bus_add_chip(struct bus *b, struct chip *chip) {
    if (b->chip_count >= BUS_MAX_CHIPS) return -1;
    b->chips[b->chip_count++] = chip;
    return 0;
}

void bus_reset(struct bus *b) {
    for (int i = 0; i < b->chip_count; i++) {
        struct chip *c = b->chips[i];
        if (c && c->ops && c->ops->reset) {
            c->ops->reset(c);
        }
    }
}

int bus_read(struct bus *b, uint16_t addr, uint8_t *data_out) {
    for (int i = 0; i < b->chip_count; i++) {
        struct chip *c = b->chips[i];
        if (c && c->ops && c->ops->read) {
            if (c->ops->read(c, b, addr, data_out)) return 1;
        }
    }
    return 0;
}

int bus_write(struct bus *b, uint16_t addr, uint8_t data) {
    for (int i = 0; i < b->chip_count; i++) {
        struct chip *c = b->chips[i];
        if (c && c->ops && c->ops->write) {
            if (c->ops->write(c, b, addr, data)) return 1;
        }
    }
    return 0;
}

void bus_step(struct bus *b) {
    b->osc_ticks++;
    for (int i = 0; i < b->chip_count; i++) {
        struct chip *c = b->chips[i];
        if (c && c->ops && c->ops->tick) {
            c->ops->tick(c, b);
        }
    }
}
