/* The W5500 as an SPI device (see w5500.h). */
#include <string.h>
#include "w5500.h"

#define MR       0x0000
#define MR_RST   0x80
#define VERSIONR 0x0039

/* A socket's registers */
#define SN_MR      0x00
#define SN_CR      0x01
#define SN_IR      0x02
#define SN_SR      0x03
#define SN_PORT    0x04
#define SN_TX_FSR  0x20
#define SN_TX_RD   0x22
#define SN_TX_WR   0x24
#define SN_RX_RSR  0x26
#define SN_RX_RD   0x28
#define SN_RX_WR   0x2A
#define MR_TCP     0x01
#define CR_OPEN    0x01
#define CR_LISTEN  0x02
#define CR_DISCON  0x08
#define CR_CLOSE   0x10
#define CR_SEND    0x20
#define CR_RECV    0x40
#define IR_CON     0x01
#define IR_DISCON  0x02
#define IR_RECV    0x04
#define IR_SEND_OK 0x10
#define SOCK_CLOSED      0x00
#define SOCK_INIT        0x13
#define SOCK_LISTEN      0x14
#define SOCK_ESTABLISHED 0x17
#define SOCK_CLOSE_WAIT  0x1C

static void reset_registers(struct w5500_state *s) {
    memset(s->common, 0, sizeof s->common);
    memset(s->socket, 0, sizeof s->socket);
    s->common[0x19] = 0x07; s->common[0x1A] = 0xD0;   /* RTR: 200 ms */
    s->common[0x1B] = 0x08;                           /* RCR */
    s->common[0x2E] = 0xBF;                           /* PHYCFGR: auto-negotiation; link up, 100 Mbps, full duplex */
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

static unsigned get16(const uint8_t *r, unsigned reg) {
    return (unsigned)r[reg] << 8 | r[reg + 1];
}

static void put16(uint8_t *r, unsigned reg, unsigned v) {
    r[reg] = (uint8_t)(v >> 8);
    r[reg + 1] = (uint8_t)v;
}

static void update_free(struct w5500_state *s, int n) {
    uint8_t *r = s->socket[n];
    put16(r, SN_TX_FSR, W5500_BUFFER - (uint16_t)(get16(r, SN_TX_WR) - get16(r, SN_TX_RD)));
}

static int connected(const uint8_t *r) {
    return r[SN_SR] == SOCK_ESTABLISHED || r[SN_SR] == SOCK_CLOSE_WAIT;
}

/* The connection closed from this end: the peer is told */
static void close_socket(struct w5500_state *s, int n) {
    if (connected(s->socket[n]) && s->peer.closed) s->peer.closed(s->peer.ctx, n);
    s->socket[n][SN_SR] = SOCK_CLOSED;
}

/* The TX buffer from Sn_TX_RD to Sn_TX_WR, to the peer */
static void send_data(struct w5500_state *s, int n) {
    uint8_t *r = s->socket[n], data[W5500_BUFFER];
    unsigned rd = get16(r, SN_TX_RD), len = (uint16_t)(get16(r, SN_TX_WR) - rd);
    if (len > W5500_BUFFER) len = W5500_BUFFER;
    for (unsigned i = 0; i < len; i++) data[i] = s->tx[n][(rd + i) % W5500_BUFFER];
    if (len && s->peer.receive) s->peer.receive(s->peer.ctx, n, data, len);
    put16(r, SN_TX_RD, get16(r, SN_TX_WR));
    r[SN_IR] |= IR_SEND_OK;
}

static void command(struct w5500_state *s, int n, uint8_t cmd) {
    uint8_t *r = s->socket[n];
    switch (cmd) {
    case CR_OPEN:
        if ((r[SN_MR] & 0x0F) != MR_TCP) break;
        close_socket(s, n);
        r[SN_SR] = SOCK_INIT;
        put16(r, SN_TX_RD, get16(r, SN_TX_WR));    /* nothing left over to send or to read */
        put16(r, SN_RX_WR, get16(r, SN_RX_RD));
        put16(r, SN_RX_RSR, 0);
        break;
    case CR_LISTEN:
        if (r[SN_SR] == SOCK_INIT) r[SN_SR] = SOCK_LISTEN;
        break;
    case CR_DISCON:
        if (connected(r)) r[SN_IR] |= IR_DISCON;
        close_socket(s, n);
        break;
    case CR_CLOSE:
        close_socket(s, n);
        break;
    case CR_SEND:
        if (connected(r)) send_data(s, n);
        break;
    case CR_RECV:
        put16(r, SN_RX_RSR, (uint16_t)(get16(r, SN_RX_WR) - get16(r, SN_RX_RD)));
        break;
    }
    update_free(s, n);
}

/* A socket register written: Sn_CR acts, Sn_IR clears, what the W5500 keeps is read-only */
static void write_socket(struct w5500_state *s, int n, unsigned reg, uint8_t v) {
    switch (reg) {
    case SN_CR: command(s, n, v); return;
    case SN_IR: s->socket[n][SN_IR] &= (uint8_t)~v; return;
    case SN_SR:
    case SN_TX_FSR: case SN_TX_FSR + 1: case SN_TX_RD: case SN_TX_RD + 1:
    case SN_RX_RSR: case SN_RX_RSR + 1: case SN_RX_WR: case SN_RX_WR + 1: return;
    }
    s->socket[n][reg] = v;
    update_free(s, n);
}

static void write_cell(struct w5500_state *s, uint8_t v) {
    uint8_t *c = cell(s, s->addr);
    unsigned bsb = s->control >> 3;
    if (bsb == 0 && s->addr == MR && (v & MR_RST)) reset_registers(s);   /* a software reset; MR reads 0 after */
    else if (bsb == 0 && s->addr == VERSIONR) return;
    else if (c && bsb % 4 == 1) write_socket(s, (bsb - 1) / 4, s->addr, v);
    else if (c) *c = v;
}

/* The next frame's first byte; MISO counts the header's bytes, $01 to $03 */
static void end_frame(struct w5500_state *s) {
    s->phase = 0;
    s->bits = 0;
    s->out = 0x01;
}

static void byte_done(struct w5500_state *s, uint8_t b) {
    static const uint8_t fixed[4] = { 0, 1, 2, 4 };
    int writes = (s->control & 0x04) != 0;
    switch (s->phase) {
    case 0: s->addr = (uint16_t)(b << 8); s->phase = 1; s->out = 0x02; return;
    case 1: s->addr |= b; s->phase = 2; s->out = 0x03; return;
    case 2:
        s->control = b;
        s->data_left = fixed[b & 0x03];
        s->phase = 3;
        s->frames++;
        s->out = (b & 0x04) ? 0x00 : read_cell(s);
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

/* SCSn follows the pin once it has held a level cs_delay ticks (as through a capacitor: shorter glitches don't
   reach it); a rise ends the frame */
static void w5500_tick(struct chip *self, struct bus *bus) {
    (void)bus;
    struct w5500_state *s = self->state;
    if (!s->via) return;   /* its chip select is the FPGA's (w5500_select) */
    int pin = (s->via->ddra & s->cs_mask) && !(via_6522_porta_pins(s->via) & s->cs_mask);
    if (pin != s->pin_selected) {
        s->pin_selected = pin;
        s->pin_ticks = 0;
    } else if (s->pin_ticks < s->cs_delay) {
        s->pin_ticks++;
    }
    int selected = s->pin_ticks >= s->cs_delay ? pin : s->selected;
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
    end_frame(state);
    chip->ops = &ops;
    chip->name = "w5500";
    chip->state = state;
}

void w5500_cs_glitch(struct w5500_state *s) {
    if (s->selected) end_frame(s);
}

void w5500_report(FILE *fp, const char *prefix, const struct w5500_state *s) {
    const uint8_t *c = s->common;   /* GAR $01, SUBR $05, SHAR $09, SIPR $0F */
    fprintf(fp, "%s: w5500: ip %u.%u.%u.%u mask %u.%u.%u.%u gateway %u.%u.%u.%u "
                "mac %02x:%02x:%02x:%02x:%02x:%02x\n", prefix,
            c[0x0F], c[0x10], c[0x11], c[0x12], c[0x05], c[0x06], c[0x07], c[0x08],
            c[0x01], c[0x02], c[0x03], c[0x04], c[0x09], c[0x0A], c[0x0B], c[0x0C], c[0x0D], c[0x0E]);
}

void w5500_select(void *state, int selected) {
    struct w5500_state *s = state;
    if (s->selected && !selected) end_frame(s);
    s->selected = selected;
}

static void w5500_reset_line(void *state) {
    struct w5500_state *s = state;
    end_frame(s);
    reset_registers(s);
}

struct spi_device w5500_spi(struct w5500_state *state) {
    return (struct spi_device){ state, w5500_pulse, w5500_select, w5500_reset_line };
}

void w5500_attach_peer(struct w5500_state *s, struct w5500_peer peer) {
    s->peer = peer;
}

int w5500_peer_connect(struct w5500_state *s, uint16_t port) {
    for (int n = 0; n < W5500_SOCKETS; n++) {
        uint8_t *r = s->socket[n];
        if (r[SN_SR] == SOCK_LISTEN && get16(r, SN_PORT) == port) {
            r[SN_SR] = SOCK_ESTABLISHED;
            r[SN_IR] |= IR_CON;
            return n;
        }
    }
    return -1;
}

unsigned w5500_peer_send(struct w5500_state *s, int n, const uint8_t *data, unsigned len) {
    uint8_t *r = s->socket[n];
    if (r[SN_SR] != SOCK_ESTABLISHED) return 0;
    unsigned room = W5500_BUFFER - get16(r, SN_RX_RSR), wr = get16(r, SN_RX_WR);
    if (len > room) len = room;
    for (unsigned i = 0; i < len; i++) s->rx[n][(wr + i) % W5500_BUFFER] = data[i];
    put16(r, SN_RX_WR, (uint16_t)(wr + len));
    put16(r, SN_RX_RSR, get16(r, SN_RX_RSR) + len);
    if (len) r[SN_IR] |= IR_RECV;
    return len;
}

void w5500_peer_close(struct w5500_state *s, int n) {
    uint8_t *r = s->socket[n];
    if (r[SN_SR] != SOCK_ESTABLISHED) return;
    r[SN_SR] = SOCK_CLOSE_WAIT;
    r[SN_IR] |= IR_DISCON;
}
