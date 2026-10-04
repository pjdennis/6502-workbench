/* The Michael FPGA bus's transfers, logged (see fpga_bus.h). */
#include "fpga_bus.h"

#define BUS_E  0x01
#define BUS_RS 0x20
#define BUS_RW 0x40

static void fpga_bus_tick(struct chip *self, struct bus *bus) {
    (void)bus;
    struct fpga_bus_state *s = self->state;
    uint8_t pins = via_6522_porta_pins(s->via);
    uint8_t e = (s->via->ddra & BUS_E) ? (pins & BUS_E) : 0;
    if (e && !s->e_was) {
        s->transfers++;
        if (s->log) {
            if (!(pins & BUS_RW))
                fprintf(s->log, "%c %02X\n", (pins & BUS_RS) ? 'D' : 'C', via_6522_portb_pins(s->via));
            else
                fputs((pins & BUS_RS) ? "R\n" : "S\n", s->log);
        }
    }
    s->e_was = e;
}

void fpga_bus_init(struct chip *chip, struct fpga_bus_state *state, const struct via_6522_state *via, FILE *log) {
    static const struct chip_ops ops = { .tick = fpga_bus_tick };
    state->via = via;
    state->log = log;
    state->e_was = 0;
    state->transfers = 0;
    chip->ops = &ops;
    chip->name = "fpga_bus";
    chip->state = state;
}
