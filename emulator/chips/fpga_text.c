/* The FPGA bus's text mode as a model (see fpga_text.h). */
#include <string.h>
#include "fpga_text.h"

enum { TEXT_ON = 0x00, TEXT_OFF, GOTO, PUT, CLEAR, CLEAR_EOL, INSERT, DELETE, REGION, REGION_RESET, SCROLL_UP,
       SCROLL_DOWN, INSERT_LINES, DELETE_LINES, CURSOR, VIDEO };
#define ROWS FPGA_TEXT_ROWS
#define COLS FPGA_TEXT_COLS

static void blank(struct fpga_text *t, int row, int col) {
    t->chars[row][col] = ' ';
    t->reverse_cells[row][col] = 0;
}

static void goto_cell(struct fpga_text *t, int row, int col) {
    t->row = row > ROWS - 1 ? ROWS - 1 : row;
    t->col = col > COLS ? COLS : col;
}

static void clear(struct fpga_text *t) {
    for (int r = 0; r < ROWS; r++)
        for (int c = 0; c < COLS; c++) blank(t, r, c);
    goto_cell(t, 0, 0);
}

/* A new region; with the picture scrolled, back to no scroll */
static void region(struct fpga_text *t, int top, int bottom) {
    if (bottom > ROWS - 1) bottom = ROWS - 1;
    if (top < bottom) {
        if (top != t->top || bottom != t->bottom) t->offset = 0;
        t->top = top;
        t->bottom = bottom;
        goto_cell(t, 0, 0);
    }
}

/* The cursor's row from its column on: n cells inserted (blanks in, the end lost) or deleted (blanks at the
 * end) */
static void shift_row(struct fpga_text *t, int n, int insert) {
    if (t->col >= COLS || n == 0) return;
    int col = t->col, span = COLS - col;
    if (n > span) n = span;
    uint8_t *ch = t->chars[t->row], *rv = t->reverse_cells[t->row];
    if (insert) {
        memmove(ch + col + n, ch + col, (size_t)(span - n));
        memmove(rv + col + n, rv + col, (size_t)(span - n));
        for (int c = col; c < col + n; c++) blank(t, t->row, c);
    } else {
        memmove(ch + col, ch + col + n, (size_t)(span - n));
        memmove(rv + col, rv + col + n, (size_t)(span - n));
        for (int c = COLS - n; c < COLS; c++) blank(t, t->row, c);
    }
}

/* Rows top to the region's bottom move up (or down) n rows, blank rows coming in. The whole region, by fewer
 * rows than it has, moves by the display's hardware scroll: its picture moves offset rows (text_grid.v). */
static void scroll(struct fpga_text *t, int top, int n, int up) {
    int height = t->bottom - top + 1;
    if (n == 0 || height <= 0) return;
    if (top == t->top && n < height) t->offset = (t->offset + (up ? height - n : n)) % height;
    if (n > height) n = height;
    for (int i = 0; i < height; i++) {
        int dst = up ? top + i : t->bottom - i;
        int src = up ? dst + n : dst - n;
        if (up ? src <= t->bottom : src >= top) {
            memcpy(t->chars[dst], t->chars[src], COLS);
            memcpy(t->reverse_cells[dst], t->reverse_cells[src], COLS);
        } else {
            for (int c = 0; c < COLS; c++) blank(t, dst, c);
        }
    }
}

static void lines(struct fpga_text *t, int n, int up) {
    if (t->top <= t->row && t->row <= t->bottom) {
        t->col = 0;
        scroll(t, t->row, n, up);
    }
}

static void put(struct fpga_text *t, uint8_t code) {
    if (code >= 0x20) {
        if (t->col < COLS) {
            t->chars[t->row][t->col] = code;
            t->reverse_cells[t->row][t->col] = (uint8_t)t->reverse;
            if (++t->col == COLS && t->row < ROWS - 1) { t->row++; t->col = 0; }
        }
    } else if (code == 0x08) {
        if (t->col > 0) t->col--;
    } else if (code == 0x0A) {
        if (t->row < ROWS - 1) t->row++;
        t->col = 0;
    } else if (code == 0x0D) {
        t->col = 0;
    }
}

void fpga_text_init(struct fpga_text *t) {
    memset(t, 0, sizeof(*t));
    t->bottom = ROWS - 1;
    clear(t);
}

void fpga_text_op(struct fpga_text *t, uint8_t code, uint8_t a, uint8_t b) {
    switch (code) {
    case TEXT_ON:      t->cursor = t->reverse = t->offset = 0; t->top = 0; t->bottom = ROWS - 1; clear(t); t->used = 1;
                       break;
    case TEXT_OFF:     break;
    case GOTO:         goto_cell(t, a, b); break;
    case PUT:          put(t, a); break;
    case CLEAR:        clear(t); break;
    case CLEAR_EOL:    shift_row(t, COLS, 0); break;
    case INSERT:       shift_row(t, a, 1); break;
    case DELETE:       shift_row(t, a, 0); break;
    case REGION:       region(t, a, b); break;
    case REGION_RESET: region(t, 0, ROWS - 1); break;
    case SCROLL_UP:    scroll(t, t->top, a, 1); break;
    case SCROLL_DOWN:  scroll(t, t->top, a, 0); break;
    case INSERT_LINES: lines(t, a, 0); break;
    case DELETE_LINES: lines(t, a, 1); break;
    case CURSOR:       t->cursor = a != 0; break;
    case VIDEO:        t->reverse = a != 0; break;
    }
}

void fpga_text_row(const struct fpga_text *t, int row, char *out) {
    memcpy(out, t->chars[row], COLS);
    out[COLS] = '\0';
}
