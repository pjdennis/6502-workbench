/* A banked ROM module in one BBC sideways socket, switched by reads (see bbc_module.h). */
#include "bbc_module.h"

#include <stdio.h>
#include <string.h>

int bbc_module_banks(enum bbc_module_scheme scheme) {
    return scheme == BBC_MODULE_DIRECT16 ? 16 : 8;
}

static void select_bank(struct bbc_module_state *s, int bank) {
    if (s->bank != bank) s->switches++;
    s->bank = (uint8_t)bank;
}

uint8_t bbc_module_read(struct bbc_module_state *s, uint16_t offset) {
    offset &= BBC_MODULE_BANK_SIZE - 1;
    if (s->scheme == BBC_MODULE_DIRECT16) {
        if (offset >= 0x3FF0) select_bank(s, offset - 0x3FF0);
    } else if (offset == 0x3FE0) {
        select_bank(s, 0);
    } else if (s->bank == 0 && offset >= 0x3F00 && offset < 0x3FE0) {
        /* $3FC0-$3FDF bank 1, $3FA0-$3FBF bank 2, ... $3F00-$3F1F bank 7 */
        select_bank(s, 1 + (0x3FDF - offset) / 0x20);
    }
    return s->data[(uint32_t)s->bank * BBC_MODULE_BANK_SIZE + offset];
}

void bbc_module_write(struct bbc_module_state *s, uint16_t offset, uint8_t data) {
    if (!s->ram) return;
    offset &= BBC_MODULE_BANK_SIZE - 1;
    s->data[(uint32_t)s->bank * BBC_MODULE_BANK_SIZE + offset] = data;
}

long bbc_module_load(struct bbc_module_state *s, const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    long room = (long)bbc_module_banks(s->scheme) * BBC_MODULE_BANK_SIZE;
    static uint8_t buf[BBC_MODULE_MAX_SIZE + 1];
    size_t n = fread(buf, 1, sizeof buf, f);
    fclose(f);
    if ((long)n > room) return -2;
    memcpy(s->data, buf, n);
    return (long)n;
}

static bool module_read(struct chip *self, struct bus *bus, uint16_t addr, uint8_t *data_out) {
    if (!bus->romcs || addr < 0x8000 || addr >= 0xC000) return false;
    *data_out = bbc_module_read(self->state, (uint16_t)(addr - 0x8000));
    return true;
}

static bool module_write(struct chip *self, struct bus *bus, uint16_t addr, uint8_t data) {
    if (!bus->romcs || addr < 0x8000 || addr >= 0xC000) return false;
    bbc_module_write(self->state, (uint16_t)(addr - 0x8000), data);
    return true;
}

void bbc_module_chip(struct chip *chip, struct bbc_module_state *s) {
    static const struct chip_ops ops = { .read = module_read, .write = module_write };
    chip->ops = &ops;
    chip->name = "bbc_module";
    chip->state = s;
}

void bbc_module_init(struct chip *chip, struct bbc_module_state *s,
                     enum bbc_module_scheme scheme, int ram, int bank) {
    memset(s->data, ram ? 0x00 : 0xFF, sizeof s->data);
    s->scheme = scheme;
    s->ram = ram;
    s->bank = (uint8_t)(bank & (bbc_module_banks(scheme) - 1));
    s->switches = 0;
    bbc_module_chip(chip, s);
}
