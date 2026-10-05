#ifndef EMULATOR_CHIPS_FPGA_TEXT_RENDER_H
#define EMULATOR_CHIPS_FPGA_TEXT_RENDER_H

#include <stdint.h>
#include "fpga_text.h"
#include "ili9341.h"

/* Text mode's renderer as a model (hardware/michael/fpga/rtl/text_render.v): it draws the grid (fpga_text.h)
 * on the display (ili9341.h) as the FPGA does, through the display's commands. First the orientation
 * Michael's driver uses (MADCTL $A8); then the hardware scroll (VSCRDEF, VSCRSADD) as the grid's region and
 * offset have it; then each cell the display's memory doesn't hold yet, as Michael's driver draws a character
 * (a window, RAMWR, 12 columns of 16 pixels from font_12x16.h), white on black, in the memory row the scroll
 * shows where the cell belongs. Reverse video inverts a cell. The cursor inverts its cell's bottom two pixel
 * rows, blinking with a half-period of FPGA_TEXT_BLINK_US, and shows at once when it moves. Codes outside
 * ' '-'~' show blank.
 *
 * The FPGA draws in the background as the grid changes; the model draws everything at once, when asked, so its
 * picture is the FPGA's once the FPGA has caught up. It remembers what each cell of the memory holds, and
 * draws only the cells that differ from what the glass should show there. */

#define FPGA_TEXT_BLINK_US 250000

struct fpga_text_render {
    int16_t drawn[FPGA_TEXT_ROWS][FPGA_TEXT_COLS];   /* each memory row's cells: {cursor, reverse, code}, -1 unknown */
    int set_up;                       /* the orientation sent */
    int scroll_ok, top, bottom, offset;   /* the hardware scroll sent */
    int row, col, cursor;             /* the cursor when its blink last restarted */
    int blink_on;
    uint64_t blink_us;                /* when the blink last changed */
};

/* Text mode coming on: the display's memory and scroll are unknown, so everything is to send */
void fpga_text_render_init(struct fpga_text_render *r);
/* Draws what changed in the grid since, as the FPGA would have by now_us (for the cursor's blink) */
void fpga_text_render_draw(struct fpga_text_render *r, const struct fpga_text *t, struct ili9341 *panel,
                           uint64_t now_us);

#endif
