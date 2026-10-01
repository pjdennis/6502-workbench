/* 28C256 32 KiB ROM loaded from a file (see rom_28c256.h). */
#include "rom_28c256.h"

#include <stdio.h>
#include <string.h>

static bool rom_28c256_read(struct chip *self, struct bus *bus,
                            uint16_t addr, uint8_t *data_out) {
    struct rom_28c256_state *s = (struct rom_28c256_state *)self->state;
    if (!bus->romcs || !bus->rwb) return false;
    /* The 32 KiB ROM lives at $8000..$FFFF on the wendy2c (clock_22v10
     * asserts ROMCS only for addresses in that range). */
    *data_out = s->contents[addr & (ROM_28C256_SIZE - 1)];
    return true;
}

static bool rom_28c256_write(struct chip *self, struct bus *bus,
                             uint16_t addr, uint8_t data) {
    (void)self; (void)addr; (void)data;
    /* Writes to ROMCS-asserted addresses are swallowed (real EEPROM
     * write protocol not modeled). */
    if (bus->romcs && !bus->rwb) return true;
    return false;
}

static void rom_28c256_reset(struct chip *self) {
    (void)self;
}

void rom_28c256_init(struct chip *chip, struct rom_28c256_state *state) {
    static const struct chip_ops ops = {
        .tick  = NULL,
        .read  = rom_28c256_read,
        .write = rom_28c256_write,
        .reset = rom_28c256_reset,
    };
    memset(state->contents, 0xFF, ROM_28C256_SIZE);  /* erased EEPROM */
    chip->ops = &ops;
    chip->name = "rom_28c256";
    chip->state = state;
}

int rom_28c256_load(struct rom_28c256_state *state, const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    size_t n = fread(state->contents, 1, ROM_28C256_SIZE, f);
    fclose(f);
    if (n == 0) return -1;
    /* Pad remainder with 0xFF if the file was shorter. */
    if (n < ROM_28C256_SIZE) {
        memset(state->contents + n, 0xFF, ROM_28C256_SIZE - n);
    }
    return 0;
}
