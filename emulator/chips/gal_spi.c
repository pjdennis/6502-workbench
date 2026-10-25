/* The GAL20RA10 SPI interface and its 74HC299 (see gal_spi.h). */
#include <string.h>
#include "gal_spi.h"

#define E 0x04   /* PA2 */

/* A Phi2 cycle: spi-control.pld's registers and the '299 on the rising edge, then the burst's SCLK pulse */
static void gal_spi_tick(struct chip *self, struct bus *bus) {
    (void)bus;
    struct gal_spi_state *s = self->state;
    int e = (s->via->ddra & E) && (via_6522_porta_pins(s->via) & E);
    int s0 = !s->output, s1 = !s->output && !s->brst;          /* /OUTPUT and srS1, before the edge */
    int brst = (e && !s->output && s->count == 0) || (s->brst && s->count != 7);
    int output = e && (s->output || (s->brst && s->count == 7));
    if (s0 && s1) s->sr = via_6522_portb_pins(s->via);            /* load */
    else if (s0) s->sr = (uint8_t)(s->sr << 1 | s->misor);         /* shift, Q7 out on MOSI */
    if (brst && !s->brst) s->bytes++;
    s->count = s->brst ? (uint8_t)((s->count + 1) & 7) : 0;
    s->brst = (uint8_t)brst;
    s->output = (uint8_t)output;
    if (s->brst) s->misor = (uint8_t)spi_pulse(&s->spi, s->sr >> 7);
}

/* /RST: the registers clear */
static void gal_spi_reset(struct chip *self) {
    struct gal_spi_state *s = self->state;
    s->brst = s->output = s->count = s->misor = 0;
}

void gal_spi_init(struct chip *chip, struct gal_spi_state *state, const struct via_6522_state *via,
                  struct spi_device spi) {
    static const struct chip_ops ops = { .tick = gal_spi_tick, .reset = gal_spi_reset };
    memset(state, 0, sizeof *state);
    state->via = via;
    state->spi = spi;
    chip->ops = &ops;
    chip->name = "gal_spi";
    chip->state = state;
}

int gal_spi_output(const struct gal_spi_state *s, uint8_t *value) {
    if (!s->output) return 0;
    *value = s->sr;
    return 1;
}
