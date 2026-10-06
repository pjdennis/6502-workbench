#ifndef EMULATOR_CHIPS_FPGA_TEXT_H
#define EMULATOR_CHIPS_FPGA_TEXT_H

#include <stdint.h>

/* The FPGA bus's text mode as a model: the character grid text mode's operations ($00-$0F) change, by the rules
 * of hardware/michael/fpga/text/text_screen.py (the ROM's LCD screen's, lcd_screen.inc, with reverse video
 * and 0-based rows and columns). How the FPGA draws it isn't modelled. */

#define FPGA_TEXT_ROWS 20
#define FPGA_TEXT_COLS 20

struct fpga_text {
    uint8_t chars[FPGA_TEXT_ROWS][FPGA_TEXT_COLS];
    uint8_t reverse_cells[FPGA_TEXT_ROWS][FPGA_TEXT_COLS];
    int row, col;            /* col FPGA_TEXT_COLS: past the end of the row */
    int top, bottom;         /* the scroll region */
    int offset;              /* rows the region's picture has moved by the display's hardware scroll */
    int cursor, reverse;
    int used;                /* text mode has been turned on */
};

void fpga_text_init(struct fpga_text *t);
/* A text operation: text mode's operation ($00-$0F) and its arguments (0 if it has none) */
void fpga_text_op(struct fpga_text *t, uint8_t code, uint8_t a, uint8_t b);
/* The row's characters, FPGA_TEXT_COLS of them, and a NUL */
void fpga_text_row(const struct fpga_text *t, int row, char *out);

#endif
