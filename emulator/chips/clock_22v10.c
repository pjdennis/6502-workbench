/* 22V10 PLD model: chip selects, RAM bank bits and the CPU clock, from clock_22v10_pld_generated.h (see clock_22v10.h). */
#include "clock_22v10.h"

#include <stddef.h>

/* The PLD combinational equations live in clock_22v10_pld_generated.h,
 * which is regenerated from 22V10-wendy2c.pld by pld_to_c.py whenever
 * the .pld source changes. Edits to the .pld flow through to the
 * emulator without touching this file. */
#include "clock_22v10_pld_generated.h"

void clock_22v10_refresh_combinational(struct bus *bus) {
    uint16_t a = bus->addr;
    int a15 = (a >> 15) & 1;
    int a14 = (a >> 14) & 1;
    int a13 = (a >> 13) & 1;
    int a12 = (a >> 12) & 1;
    int a11 = (a >> 11) & 1;
    uint8_t cb = bus->bank_config;
    int c4 = (cb >> 4) & 1;
    int c3 = (cb >> 3) & 1;
    int c2 = (cb >> 2) & 1;
    int c1 = (cb >> 1) & 1;
    int c0 = cb & 1;

    int r15 = pld_r15(a15, a14, a13, a12, a11, c4, c3, c2, c1, c0);
    int r16 = pld_r16(a15, a14, a13, a12, a11, c4, c3, c2, c1, c0);
    int r17 = pld_r17(a15, a14, a13, a12, a11, c4, c3, c2, c1, c0);
    int r18 = pld_r18(a15, a14, a13, a12, a11, c4, c3, c2, c1, c0);

    bus->romcs  = (uint8_t)pld_romcs(a15, a14, a13, a12, a11, c4, c3, c2, c1, c0);
    bus->ramcs  = (uint8_t)pld_ramcs(a15, a14, a13, a12, a11, c4, c3, c2, c1, c0);
    bus->viacs  = (uint8_t)pld_viacs(a15, a14, a13, a12, a11, c4, c3, c2, c1, c0);
    bus->r_bits = (uint8_t)((r18 << 3) | (r17 << 2) | (r16 << 1) | r15);
    bus->wr     = (bus->rwb ? 0 : 1) & bus->ck;
}

static void clock_22v10_tick(struct chip *self, struct bus *bus) {
    (void)self;

    /* Refresh combinational outputs from the current address/RWB/bank. */
    clock_22v10_refresh_combinational(bus);

    /* Registered: cks_next = NOT cks_prev. */
    uint8_t prev_cks = bus->cks;
    uint8_t prev_ck = bus->ck;
    uint8_t new_cks = prev_cks ? 0 : 1;

    /* Registered ck_next = ck_prev AND NOT cks_prev
     *               PLUS  NOT ck_prev AND cks_prev
     *               PLUS  NOT romcs AND NOT ck_prev. */
    uint8_t new_ck = 0;
    if (prev_ck && !prev_cks) new_ck = 1;
    if (!prev_ck && prev_cks) new_ck = 1;
    if (!bus->romcs && !prev_ck) new_ck = 1;

    if (prev_ck && !new_ck) bus->cpu_cycle_due = 1;

    bus->cks = new_cks;
    bus->ck  = new_ck;
    /* WR depends on new CK; recompute. */
    bus->wr  = (bus->rwb ? 0 : 1) & new_ck;
}

static void clock_22v10_reset(struct chip *self) {
    (void)self;
}

void clock_22v10_init(struct chip *chip, struct clock_22v10_state *state) {
    static const struct chip_ops ops = {
        .tick  = clock_22v10_tick,
        .read  = NULL,
        .write = NULL,
        .reset = clock_22v10_reset,
    };
    state->dummy = 0;
    chip->ops = &ops;
    chip->name = "clock_22v10";
    chip->state = state;
}
