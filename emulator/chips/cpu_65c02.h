#ifndef EMULATOR_CHIPS_CPU_65C02_H
#define EMULATOR_CHIPS_CPU_65C02_H

#include <stdint.h>
#include "../bus.h"

/* CPU-on-the-bus chip wrapper. Per-instruction strategy:
 *
 *   When the clock_22v10 sets bus->cpu_cycle_due (CK falling edge):
 *     - if cycles_owed > 0, decrement (the CPU is finishing a multi-
 *       cycle instruction it executed at burst start)
 *     - if cycles_owed == 0, run step6502() which executes one full
 *       instruction in C-time, then record cycles_owed = (cycles
 *       consumed by that instruction - 1).
 *
 * IRQ / NMI / RES bus lines are sampled at instruction boundaries and
 * dispatched into irq6502 / nmi6502 / reset6502. */

struct cpu_65c02_state {
    uint64_t cycles_owed;
    uint8_t  prev_res;  /* edge detect for RES line */
    uint8_t  prev_nmi;  /* NMI is edge-triggered */
};

void cpu_65c02_init(struct chip *chip, struct cpu_65c02_state *state);

#endif
