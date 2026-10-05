/* The ILI9341 display controller and its panel (see ili9341.h). */
#include <string.h>
#include "ili9341.h"

enum { SWRESET = 0x01, SLPIN = 0x10, SLPOUT = 0x11, DISPOFF = 0x28, DISPON = 0x29, CASET = 0x2A, PASET = 0x2B,
       RAMWR = 0x2C, VSCRDEF = 0x33, MADCTL = 0x36, VSCRSADD = 0x37, RAMWRC = 0x3C, DFUNCTR = 0xB6 };
enum { MY = 0x80, MX = 0x40, MV = 0x20, BGR = 0x08 };

/* The registers as a reset leaves them */
static void reset(struct ili9341 *p) {
    p->command = 0;
    p->n_params = 0;
    p->have_high = 0;
    p->sc = p->sp = p->col = p->page = 0;
    p->ec = ILI9341_WIDTH - 1;
    p->ep = ILI9341_LINES - 1;
    p->madctl = 0;
    p->scan = 0x82;
    p->tfa = p->bfa = p->ssa = 0;
    p->vsa = ILI9341_LINES;
    p->sleeping = 1;
    p->on = 0;
}

void ili9341_init(struct ili9341 *p) {
    memset(p, 0, sizeof(*p));
    reset(p);
    p->backlight = 255;
}

void ili9341_reset_line(struct ili9341 *p, int level) {
    p->in_reset = !level;
    if (p->in_reset) reset(p);
}

void ili9341_command(struct ili9341 *p, uint8_t command) {
    if (p->in_reset) return;
    p->command = command;
    p->n_params = 0;
    p->have_high = 0;
    switch (command) {
    case SWRESET: reset(p); break;
    case SLPIN:   p->sleeping = 1; break;
    case SLPOUT:  p->sleeping = 0; break;
    case DISPOFF: p->on = 0; break;
    case DISPON:  p->on = 1; break;
    case RAMWR:   p->col = p->sc; p->page = p->sp; break;
    }
}

static uint16_t word(const uint8_t *b) { return (uint16_t)(b[0] << 8 | b[1]); }

/* A pixel where the window's counters are, through MADCTL; then the counters move on */
static void write_pixel(struct ili9341 *p, uint16_t v) {
    int mv = (p->madctl & MV) != 0;
    int line = mv ? p->col : p->page, x = mv ? p->page : p->col;
    if (p->madctl & MY) line = ILI9341_LINES - 1 - line;
    if (p->madctl & MX) x = ILI9341_WIDTH - 1 - x;
    if (!(p->madctl & BGR)) v = (uint16_t)((v & 0x07E0) | v >> 11 | (v & 0x1F) << 11);
    if (line >= 0 && line < ILI9341_LINES && x >= 0 && x < ILI9341_WIDTH) p->memory[line][x] = v;
    if (p->col++ >= p->ec) {
        p->col = p->sc;
        if (p->page++ >= p->ep) p->page = p->sp;
    }
}

/* A command's parameters, once it has them all */
static void parameters(struct ili9341 *p) {
    const uint8_t *b = p->params;
    switch (p->command) {
    case CASET:
        if (p->n_params == 4) { p->sc = word(b); p->ec = word(b + 2); }
        break;
    case PASET:
        if (p->n_params == 4) { p->sp = word(b); p->ep = word(b + 2); }
        break;
    case MADCTL:
        if (p->n_params == 1) p->madctl = b[0];
        break;
    case DFUNCTR:
        if (p->n_params == 2) p->scan = b[1];
        break;
    case VSCRSADD:
        if (p->n_params == 2) p->ssa = word(b);
        break;
    case VSCRDEF:
        if (p->n_params == 6 && word(b) + word(b + 2) + word(b + 4) == ILI9341_LINES) {
            p->tfa = word(b);
            p->vsa = word(b + 2);
            p->bfa = word(b + 4);
        }
        break;
    }
}

void ili9341_data(struct ili9341 *p, uint8_t data) {
    if (p->in_reset) return;
    if (p->command == RAMWR || p->command == RAMWRC) {
        if (p->have_high) write_pixel(p, (uint16_t)(p->high << 8 | data));
        else p->high = data;
        p->have_high = !p->have_high;
    } else if (p->n_params < (int)sizeof(p->params)) {
        p->params[p->n_params++] = data;
        parameters(p);
    }
}

int ili9341_showing(const struct ili9341 *p) {
    return !p->in_reset && !p->sleeping && p->on;
}

int ili9341_glass_line(const struct ili9341 *p, int y) {
    int k = (p->scan & ILI9341_GS) ? ILI9341_LINES - 1 - y : y;   /* the scan line */
    if (k < p->tfa || k >= p->tfa + p->vsa) return k;
    int at = ((int)p->ssa - p->tfa + k - p->tfa) % p->vsa;
    return p->tfa + (at < 0 ? at + p->vsa : at);
}

uint16_t ili9341_glass_pixel(const struct ili9341 *p, int x, int y) {
    if (!ili9341_showing(p)) return 0xFFFF;
    return p->memory[ili9341_glass_line(p, y)][(p->scan & ILI9341_SS) ? x : ILI9341_WIDTH - 1 - x];
}
