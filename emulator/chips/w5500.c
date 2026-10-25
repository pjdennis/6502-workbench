/* The W5500 as an SPI device (see w5500.h). */
#include <string.h>
#include "w5500.h"

#define VERSIONR 0x0039

static void reset_registers(struct w5500_state *s) {
    memset(s->common, 0, sizeof s->common);
    memset(s->socket, 0, sizeof s->socket);
    s->common[0x19] = 0x07; s->common[0x1A] = 0xD0;   /* RTR: 200 ms */
    s->common[0x1B] = 0x08;                           /* RCR */
    s->common[0x2E] = 0xB8;                           /* PHYCFGR: auto-negotiation, link down */
    s->common[VERSIONR] = 0x04;
    for (int n = 0; n < W5500_SOCKETS; n++) {
        uint8_t *r = s->socket[n];
        memset(r + 0x06, 0xFF, 6);                    /* Sn_DHAR */
        r[0x16] = 0x80;                               /* Sn_TTL */
        r[0x1E] = 0x02; r[0x1F] = 0x02;               /* Sn_RXBUF_SIZE, Sn_TXBUF_SIZE: 2 KB */
        r[0x20] = 0x08;                               /* Sn_TX_FSR: $0800 free */
        r[0x2D] = 0x40;                               /* Sn_FRAG: $4000 */
    }
}

/* The byte at addr in the control byte's block, or NULL where nothing is */
static uint8_t *cell(struct w5500_state *s, uint16_t addr) {
    unsigned bsb = s->control >> 3, n = (bsb - 1) / 4;
    if (bsb == 0) return addr < sizeof s->common ? &s->common[addr] : NULL;
    if (n >= W5500_SOCKETS) return NULL;
    switch ((bsb - 1) % 4) {
    case 0: return addr < sizeof s->socket[n] ? &s->socket[n][addr] : NULL;
    case 1: return &s->tx[n][addr % W5500_BUFFER];
    case 2: return &s->rx[n][addr % W5500_BUFFER];
    default: return NULL;
    }
}

static uint8_t read_cell(struct w5500_state *s) {
    const uint8_t *c = cell(s, s->addr);
    return c ? *c : 0x00;
}

static void write_cell(struct w5500_state *s, uint8_t v) {
    uint8_t *c = cell(s, s->addr);
    if (c && !(s->control >> 3 == 0 && s->addr == VERSIONR)) *c = v;
}

static void end_frame(struct w5500_state *s) {
    s->phase = 0;
    s->bits = 0;
    s->out = 0;
}

static void byte_done(struct w5500_state *s, uint8_t b) {
    static const uint8_t fixed[4] = { 0, 1, 2, 4 };
    int writes = (s->control & 0x04) != 0;
    switch (s->phase) {
    case 0: s->addr = (uint16_t)(b << 8); s->phase = 1; return;
    case 1: s->addr |= b; s->phase = 2; return;
    case 2:
        s->control = b;
        s->data_left = fixed[b & 0x03];
        s->phase = 3;
        s->frames++;
        if (!(b & 0x04)) s->out = read_cell(s);
        return;
    default:
        if (writes) write_cell(s, b);
        s->addr++;
        if (s->data_left && --s->data_left == 0) { end_frame(s); return; }
        if (!writes) s->out = read_cell(s);
    }
}

int w5500_pulse(void *state, int mosi) {
    struct w5500_state *s = state;
    if (!s->selected) return 1;
    int miso = s->out >> 7;
    s->out = (uint8_t)(s->out << 1);
    s->in = (uint8_t)(s->in << 1 | (mosi & 1));
    if (++s->bits == 8) {
        s->bits = 0;
        byte_done(s, s->in);
    }
    return miso;
}

/* SCSn follows the pin; a rise ends the frame */
static void w5500_tick(struct chip *self, struct bus *bus) {
    (void)bus;
    struct w5500_state *s = self->state;
    int selected = (s->via->ddra & s->cs_mask) && !(via_6522_porta_pins(s->via) & s->cs_mask);
    if (s->selected && !selected) end_frame(s);
    s->selected = selected;
}

static void w5500_reset(struct chip *self) {
    struct w5500_state *s = self->state;
    end_frame(s);
    reset_registers(s);
}

void w5500_init(struct chip *chip, struct w5500_state *state, const struct via_6522_state *via, uint8_t cs_mask) {
    static const struct chip_ops ops = { .tick = w5500_tick, .reset = w5500_reset };
    memset(state, 0, sizeof *state);
    state->via = via;
    state->cs_mask = cs_mask;
    reset_registers(state);
    chip->ops = &ops;
    chip->name = "w5500";
    chip->state = state;
}

struct spi_device w5500_spi(struct w5500_state *state) {
    return (struct spi_device){ state, w5500_pulse };
}
