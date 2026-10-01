/* wendy2c 512 KiB banked RAM (see ram_628128.h). */
#include "ram_628128.h"

#include <string.h>

static uint32_t physical_addr(struct bus *bus, uint16_t addr) {
    /* RAM physical address layout on the wendy2c breadboard:
     *
     *   bits 18..15 = bus->r_bits  (R18..R15 PLD outputs)
     *   bit  14     = CPU A15      (NOT CPU A14)
     *   bits 13..0  = CPU A13..A0
     *
     * CPU A14 is consumed by the PLD's chip-select / R-bit decoding
     * (so $2000 and $6000 produce different R-bits, putting them in
     * different physical banks) but does NOT reach the RAM chip
     * itself. Instead CPU A15 drives RAM A14, splitting each 32 KiB
     * physical bank into two 16 KiB halves: CPU $0000-$7FFF uses the
     * low half, CPU $8000-$FFFF uses the high half. This is what
     * makes verification_wendy2c.s pass on real hardware: the lower-
     * bank window at $2000 (CPU A15=0) and the upper-L window at
     * $a000 (CPU A15=1) land in disjoint halves of whatever bank the
     * PLD selects, so writes don't alias even when their R-bits
     * collide.
     */
    int cpu_a15 = (addr >> 15) & 1;
    return ((uint32_t)(bus->r_bits & 0x0F) << 15)
         | ((uint32_t)cpu_a15 << 14)
         | (addr & 0x3FFF);
}

static bool ram_628128_read(struct chip *self, struct bus *bus,
                            uint16_t addr, uint8_t *data_out) {
    if (!bus->ramcs || !bus->rwb) return false;
    struct ram_628128_state *s = (struct ram_628128_state *)self->state;
    uint32_t pa = physical_addr(bus, addr);
    *data_out = s->contents[pa];
    return true;
}

static bool ram_628128_write(struct chip *self, struct bus *bus,
                             uint16_t addr, uint8_t data) {
    if (!bus->ramcs || bus->rwb) return false;
    struct ram_628128_state *s = (struct ram_628128_state *)self->state;
    uint32_t pa = physical_addr(bus, addr);
    s->contents[pa] = data;
    return true;
}

static void ram_628128_reset(struct chip *self) {
    (void)self;
}

void ram_628128_init(struct chip *chip, struct ram_628128_state *state) {
    static const struct chip_ops ops = {
        .tick  = NULL,
        .read  = ram_628128_read,
        .write = ram_628128_write,
        .reset = ram_628128_reset,
    };
    memset(state->contents, 0, RAM_628128_SIZE);
    chip->ops = &ops;
    chip->name = "ram_628128";
    chip->state = state;
}
