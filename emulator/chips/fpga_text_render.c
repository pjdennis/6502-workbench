/* Text mode's renderer as a model (see fpga_text_render.h). */
#include <string.h>
#include "fpga_text_render.h"
#include "font_12x16.h"

enum { CASET = 0x2A, PASET = 0x2B, RAMWR = 0x2C, VSCRDEF = 0x33, MADCTL = 0x36, VSCRSADD = 0x37 };
#define MADCTL_TEXT 0xA8            /* MY, MV, BGR, as gd_prepare_vertical */
#define ROWS FPGA_TEXT_ROWS
#define COLS FPGA_TEXT_COLS
#define CELL_W 12
#define CELL_H 16
#define CURSOR_ROWS 2
#define REVERSE 0x100
#define CURSOR 0x200

void fpga_text_render_init(struct fpga_text_render *r) {
    memset(r, 0, sizeof(*r));
    memset(r->drawn, 0xFF, sizeof(r->drawn));
}

static void word(struct ili9341 *p, int w) {
    ili9341_data(p, (uint8_t)(w >> 8));
    ili9341_data(p, (uint8_t)w);
}

static void words(struct ili9341 *p, uint8_t command, int n, const int *w) {
    ili9341_command(p, command);
    for (int i = 0; i < n; i++) word(p, w[i]);
}

/* The memory row where row r shows, through the hardware scroll (text_render.v's memory_row) */
static int memory_row(const struct fpga_text_render *r, int row) {
    if (row < r->top || row > r->bottom) return row;
    int height = r->bottom - r->top + 1;
    return r->bottom - (r->offset + r->bottom - row) % height;
}

/* The scroll area is the region; the top fixed area the rows below it, as the memory runs from the bottom row */
static void send_scroll(struct ili9341 *p, const struct fpga_text_render *r) {
    int tfa = (ROWS - 1 - r->bottom) * CELL_H;
    words(p, VSCRDEF, 3, (const int[]){ tfa, (r->bottom - r->top + 1) * CELL_H, r->top * CELL_H });
    words(p, VSCRSADD, 1, (const int[]){ tfa + r->offset * CELL_H });
}

/* A cell, {cursor, reverse, code}, at memory row m, column c, as gd_show_character draws a character */
static void draw_cell(struct ili9341 *p, int m, int c, int cell) {
    int code = cell & 0xFF;
    const uint16_t *glyph = font_12x16[code];
    uint16_t invert = (cell & REVERSE ? 0xFFFF : 0) ^ (cell & CURSOR ? (uint16_t)(0xFFFF << (CELL_H - CURSOR_ROWS)) : 0);
    words(p, CASET, 2, (const int[]){ m * CELL_H, m * CELL_H + CELL_H - 1 });
    words(p, PASET, 2, (const int[]){ c * CELL_W, c * CELL_W + CELL_W - 1 });
    ili9341_command(p, RAMWR);
    for (int x = 0; x < CELL_W; x++) {
        uint16_t column = glyph[x] ^ invert;
        for (int y = 0; y < CELL_H; y++) word(p, (column >> y) & 1 ? 0xFFFF : 0x0000);
    }
}

/* The cursor shows at once when it moves (or is turned on or off), then blinks */
static void blink(struct fpga_text_render *r, const struct fpga_text *t, uint64_t now_us) {
    if (t->row != r->row || t->col != r->col || t->cursor != r->cursor || now_us < r->blink_us) {
        r->row = t->row;
        r->col = t->col;
        r->cursor = t->cursor;
        r->blink_on = 1;
        r->blink_us = now_us;
        return;
    }
    uint64_t periods = (now_us - r->blink_us) / FPGA_TEXT_BLINK_US;
    r->blink_on ^= (int)(periods & 1);
    r->blink_us += periods * FPGA_TEXT_BLINK_US;
}

void fpga_text_render_draw(struct fpga_text_render *r, const struct fpga_text *t, struct ili9341 *panel,
                           uint64_t now_us) {
    if (!r->set_up) {
        ili9341_command(panel, MADCTL);
        ili9341_data(panel, MADCTL_TEXT);
        r->set_up = 1;
    }
    if (!r->scroll_ok || t->top != r->top || t->bottom != r->bottom || t->offset != r->offset) {
        r->top = t->top;
        r->bottom = t->bottom;
        r->offset = t->offset;
        r->scroll_ok = 1;
        send_scroll(panel, r);
    }
    blink(r, t, now_us);
    int cursor_shown = t->cursor && t->col < COLS && r->blink_on;
    for (int row = 0; row < ROWS; row++) {
        int m = memory_row(r, row);
        for (int c = 0; c < COLS; c++) {
            int cell = t->chars[row][c] | (t->reverse_cells[row][c] ? REVERSE : 0) |
                       (cursor_shown && row == t->row && c == t->col ? CURSOR : 0);
            if (r->drawn[m][c] == cell) continue;
            draw_cell(panel, m, c, cell);
            r->drawn[m][c] = (int16_t)cell;
        }
    }
}
