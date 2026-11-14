/* The BBC Model B+128 memory map: main RAM, ROMSEL, the sideways slots, private RAM, MOS ROM (see bbc_memory.h). */
#include "bbc_memory.h"

#include <stdio.h>
#include <string.h>

/* $FE30-$FE3F is ROMSEL's block, decoded on A0-A2 (as MAME's bbcbp does):
 * ROMSEL at $FE30 and $FE38; $FE34/$FE3C select the shadow screen (not
 * modelled); the rest do nothing */
static int is_romsel(uint16_t addr) {
    return (addr & 0xFFF7) == BBC_ROMSEL;
}

static int is_private(const struct bbc_memory_state *s, uint16_t addr) {
    return (s->romsel & 0x80) && addr >= 0x8000 && addr < 0xB000;
}

void bbc_memory_decode(struct bus *bus, const struct bbc_memory_state *s) {
    uint16_t a = bus->addr;
    bus->romcs = a >= 0x8000 && a < 0xC000 && s->kind[s->romsel & 0x0F] == BBC_SLOT_MODULE && !is_private(s, a);
}

static bool memory_read(struct chip *self, struct bus *bus, uint16_t addr, uint8_t *data_out) {
    (void)bus;
    struct bbc_memory_state *s = self->state;
    if (addr < 0x8000) {
        *data_out = s->ram[addr];
        return true;
    }
    if (addr < 0xC000) {
        if (is_private(s, addr)) {
            *data_out = s->private_ram[addr - 0x8000];
            return true;
        }
        int slot = s->romsel & 0x0F;
        if (s->kind[slot] == BBC_SLOT_ROM || s->kind[slot] == BBC_SLOT_RAM) {
            *data_out = s->slot[slot][addr - 0x8000];
            return true;
        }
        return false;   /* empty (or the module, which answered first): the open bus */
    }
    if (addr >= 0xFC00 && addr < 0xFF00) return false;   /* I/O: nothing to read here */
    *data_out = s->mos[addr - 0xC000];
    return true;
}

static bool memory_write(struct chip *self, struct bus *bus, uint16_t addr, uint8_t data) {
    (void)bus;
    struct bbc_memory_state *s = self->state;
    if (addr < 0x8000) {
        s->ram[addr] = data;
    } else if (addr < 0xC000) {
        if (is_private(s, addr)) {
            s->private_ram[addr - 0x8000] = data;
        } else {
            int slot = s->romsel & 0x0F;
            if (s->kind[slot] == BBC_SLOT_RAM) s->slot[slot][addr - 0x8000] = data;
        }
    } else if (is_romsel(addr)) {
        s->romsel = data;
    }
    return true;   /* ROM, empty slots and unmodelled I/O drop the write */
}

int bbc_memory_load_rom(struct bbc_memory_state *s, int slot, const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    static uint8_t buf[BBC_SLOT_SIZE + 1];
    size_t n = fread(buf, 1, sizeof buf, f);
    fclose(f);
    if (n > BBC_SLOT_SIZE) return -2;
    memset(s->slot[slot], 0xFF, BBC_SLOT_SIZE);
    memcpy(s->slot[slot], buf, n);
    if (s->kind[slot] != BBC_SLOT_RAM) s->kind[slot] = BBC_SLOT_ROM;
    return 0;
}

void bbc_memory_chip(struct chip *chip, struct bbc_memory_state *s) {
    static const struct chip_ops ops = { .read = memory_read, .write = memory_write };
    chip->ops = &ops;
    chip->name = "bbc_memory";
    chip->state = s;
}

void bbc_memory_init(struct chip *chip, struct bbc_memory_state *s) {
    memset(s, 0, sizeof *s);
    bbc_memory_chip(chip, s);
}
