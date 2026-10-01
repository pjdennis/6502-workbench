/* CPU-on-the-bus wrapper that runs one instruction per CK fall and owes the rest of its cycles (see cpu_65c02.h). */
#include "cpu_65c02.h"

#include <stddef.h>

#include "../cpu_core.h"

static void cpu_65c02_tick(struct chip *self, struct bus *bus) {
    struct cpu_65c02_state *s = (struct cpu_65c02_state *)self->state;

    /* Sample edge-triggered control lines first. */
    if (bus->res && !s->prev_res) {
        reset6502();
        s->cycles_owed = 0;
    }
    s->prev_res = bus->res;

    if (bus->nmi && !s->prev_nmi) {
        nmi6502();
    }
    s->prev_nmi = bus->nmi;

    /* IRQ is level-sensitive; honor it on instruction boundaries when
     * the I flag is clear. The 'I masked' semantic is the host's: if
     * the program has SEI'd, we still wake from WAI but don't dispatch
     * the IRQ. cpu_core's irq6502 unconditionally dispatches; we gate
     * here so it isn't constantly re-entered.
     *
     * WAI wakes on any asserted IRQ/NMI regardless of the I mask -- a
     * masked interrupt still completes WAI and the CPU runs the next
     * instruction with the interrupt staying pending. The
     * multitasking_test_wendy2c.s scheduler relies on this: its IRQ
     * handler executes WAI when every task is sleeping, with I set
     * because we're inside the handler. */
    extern uint8_t status;
    extern uint16_t pc;
    (void)pc;
    if ((bus->irq || bus->nmi) && cpu_wai_pending()) {
        cpu_clear_wai();
    }
    if (bus->irq && s->cycles_owed == 0 && !(status & 0x04)) {
        irq6502();
    }

    if (!bus->cpu_cycle_due) return;
    bus->cpu_cycle_due = 0;

    if (s->cycles_owed > 0) {
        s->cycles_owed--;
        return;
    }

    /* Run one instruction. clockticks6502 advances by the instruction's
     * cycle count; we owe (count - 1) future cycle ticks before fetching
     * the next instruction. */
    extern uint64_t clockticks6502;
    uint64_t before = clockticks6502;
    step6502();
    uint64_t consumed = clockticks6502 - before;
    if (consumed > 0) {
        s->cycles_owed = consumed - 1;
    }
}

static void cpu_65c02_reset(struct chip *self) {
    struct cpu_65c02_state *s = (struct cpu_65c02_state *)self->state;
    s->cycles_owed = 0;
    s->prev_res = 0;
    s->prev_nmi = 0;
    reset6502();
}

void cpu_65c02_init(struct chip *chip, struct cpu_65c02_state *state) {
    static const struct chip_ops ops = {
        .tick  = cpu_65c02_tick,
        .read  = NULL,
        .write = NULL,
        .reset = cpu_65c02_reset,
    };
    state->cycles_owed = 0;
    state->prev_res = 0;
    state->prev_nmi = 0;
    chip->ops = &ops;
    chip->name = "cpu_65c02";
    chip->state = state;
}
