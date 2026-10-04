/* 22V10 PLD model: chip selects, RAM bank bits and the CPU clock, from clock_22v10_pld_generated.h (see clock_22v10.h). */
#include "clock_22v10.h"

#include <stddef.h>

/* The PLD combinational equations live in clock_22v10_pld_generated.h,
 * which is regenerated from 22V10-wendy2c.pld by pld_to_c.py whenever
 * the .pld source changes. Edits to the .pld flow through to the
 * emulator without touching this file. */
#include "clock_22v10_pld_generated.h"

/* The combinational outputs depend only on A15..A11 and the 5 bank
 * config bits, so they are worked out once for all 1024 combinations:
 * this runs on every oscillator tick, and evaluating the equations each
 * time was over a third of the emulator's time. Each entry is ROMCS
 * (bit 0), RAMCS (1), VIACS (2) and R18..R15 (bits 6..3), indexed by
 * A15..A11 << 5 | config. */
#define PLD_ROMCS 0x01
#define PLD_RAMCS 0x02
#define PLD_VIACS 0x04
#define PLD_R_SHIFT 3

static uint8_t pld_table[32 * 32];
static int pld_table_ready;

static void build_pld_table(void) {
    for (int a = 0; a < 32; a++) {
        int a15 = (a >> 4) & 1, a14 = (a >> 3) & 1, a13 = (a >> 2) & 1, a12 = (a >> 1) & 1, a11 = a & 1;
        for (int cb = 0; cb < 32; cb++) {
            int c4 = (cb >> 4) & 1, c3 = (cb >> 3) & 1, c2 = (cb >> 2) & 1, c1 = (cb >> 1) & 1, c0 = cb & 1;
            int r15 = pld_r15(a15, a14, a13, a12, a11, c4, c3, c2, c1, c0);
            int r16 = pld_r16(a15, a14, a13, a12, a11, c4, c3, c2, c1, c0);
            int r17 = pld_r17(a15, a14, a13, a12, a11, c4, c3, c2, c1, c0);
            int r18 = pld_r18(a15, a14, a13, a12, a11, c4, c3, c2, c1, c0);
            pld_table[a << 5 | cb] = (uint8_t)(
                (pld_romcs(a15, a14, a13, a12, a11, c4, c3, c2, c1, c0) ? PLD_ROMCS : 0) |
                (pld_ramcs(a15, a14, a13, a12, a11, c4, c3, c2, c1, c0) ? PLD_RAMCS : 0) |
                (pld_viacs(a15, a14, a13, a12, a11, c4, c3, c2, c1, c0) ? PLD_VIACS : 0) |
                ((r18 << 3 | r17 << 2 | r16 << 1 | r15) << PLD_R_SHIFT));
        }
    }
    pld_table_ready = 1;
}

void clock_22v10_refresh_combinational(struct bus *bus) {
    if (!pld_table_ready) build_pld_table();
    uint8_t out = pld_table[(bus->addr >> 11) << 5 | (bus->bank_config & 0x1F)];
    bus->romcs  = (out & PLD_ROMCS) != 0;
    bus->ramcs  = (out & PLD_RAMCS) != 0;
    bus->viacs  = (out & PLD_VIACS) != 0;
    bus->r_bits = (uint8_t)(out >> PLD_R_SHIFT);
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
