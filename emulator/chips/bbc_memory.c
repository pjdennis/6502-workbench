/* The BBC memory maps (the Model B+128's, the Model B's, a Master-like machine's): main RAM, ROMSEL, the sideways slots, private RAM, MOS ROM (see bbc_memory.h). */
#include "bbc_memory.h"

#include <stdio.h>
#include <string.h>

/* $FE30-$FE3F is ROMSEL's block, decoded on A0-A2 (as MAME's bbcbp does):
 * ROMSEL at $FE30 and $FE38; $FE34/$FE3C select the shadow screen (not
 * modelled); the rest do nothing. On the Model B every address of the
 * block is ROMSEL (MAME's bbcb decodes it so too); on the Master
 * $FE30-$FE33 (MAME's bbcm), $FE34-$FE3F being ACCCON and the Econet
 * interrupt flip-flop (not modelled) */
static int is_romsel(const struct bbc_memory_state *s, uint16_t addr) {
    if (s->model_b) return (addr & 0xFFF0) == BBC_ROMSEL;   /* the Model B: all of $FE30-$FE3F */
    if (s->master) return (addr & 0xFFFC) == BBC_ROMSEL;    /* the Master: $FE30-$FE33 (MAME's bbcm) */
    return (addr & 0xFFF7) == BBC_ROMSEL;
}

static int is_private(const struct bbc_memory_state *s, uint16_t addr) {
    if (s->master) return (s->romsel & 0x80) && addr >= 0x8000 && addr < 0x8000 + BBC_ANDY_SIZE;
    return !s->model_b && (s->romsel & 0x80) && addr >= 0x8000 && addr < 0xB000;
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
    if (s->master && is_romsel(s, addr)) {      /* the Master's ROMSEL reads back its slot */
        *data_out = s->romsel & 0x0F;
        return true;
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
    } else if (is_romsel(s, addr)) {
        s->romsel = s->model_b ? (uint8_t)(data & 0x0F) : data;
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

void bbc_memory_stand_in_rom(struct bbc_memory_state *s, int slot, const char *title) {
    static const char copyright[] = "(C)";
    uint8_t *r = s->slot[slot];
    memset(r, 0xFF, BBC_SLOT_SIZE);
    r[0] = r[1] = r[2] = 0x00;          /* no language entry */
    r[3] = 0x60;                        /* the service entry: RTS, claiming nothing */
    r[4] = r[5] = 0x00;
    r[6] = 0x82;                        /* a service ROM, 6502 code */
    r[8] = 0x00;                        /* the version */
    size_t n = strlen(title);
    memcpy(r + 9, title, n + 1);        /* the title, then the copyright string's 0 */
    r[7] = (uint8_t)(9 + n);
    memcpy(r + 9 + n + 1, copyright, sizeof copyright);
    s->kind[slot] = BBC_SLOT_ROM;
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
