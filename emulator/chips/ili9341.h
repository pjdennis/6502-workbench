#ifndef EMULATOR_CHIPS_ILI9341_H
#define EMULATOR_CHIPS_ILI9341_H

#include <stdint.h>

/* The ILI9341 display controller and its 240 by 320 panel, Michael's graphic display. The bytes it receives (a
 * command, with DC low, then its parameters or pixels, with DC high) become pixels in its frame memory, which
 * the glass shows through the hardware scroll.
 *
 * The frame memory is ILI9341_LINES lines of ILI9341_WIDTH pixels (RGB565), line 0 the first the panel scans.
 * CASET and PASET set a window of columns and pages; RAMWR writes pixels into it, two bytes each, along a page's
 * columns, then the next page (wrapping to the window's start), and RAMWRC carries on from where RAMWR stopped.
 * MADCTL maps the window onto the memory: MV exchanges columns and pages, MY reverses the lines and MX the
 * pixels in a line. Michael's driver sets MY, MV and BGR ($A8): its columns (0-319) are lines, column 0 the
 * last line, and its pages (0-239) a line's pixels. With BGR clear, red and blue swap as pixels are written.
 *
 * The glass shows scan line k (0-319) from the memory line the hardware scroll gives: VSCRDEF's top fixed area,
 * scroll area and bottom fixed area (in lines, adding up to 320), and VSCRSADD, the line the scroll area starts
 * with. Display Function Control ($B6) reverses the scans: Michael's init sets GS and SS (GD_PANEL_SCAN), and
 * the display as mounted on Michael then shows scan line 0 at the bottom of the glass and a line's pixel 0 at
 * the left; without them, the picture turns over. hardware/michael/fpga/text/ili9341.py models the scroll the
 * same way, checked against the graphic driver's own scrolling.
 *
 * The glass is blank (white, as the panel is normally white) unless the controller is out of reset, out of
 * sleep (SLPOUT) and on (DISPON). A reset (the RESX line held low, or SWRESET) puts the registers back to their
 * defaults and leaves the memory as it was. Not modelled: reads, pixel formats other than 16 bits, partial,
 * idle and inverted modes, gamma, timing. */

#define ILI9341_LINES 320
#define ILI9341_WIDTH 240

struct ili9341 {
    uint16_t memory[ILI9341_LINES][ILI9341_WIDTH];
    uint8_t command;              /* the last command: data bytes are its parameters, or pixels */
    uint8_t params[6];
    int n_params;
    uint16_t sc, ec, sp, ep;      /* the window: start and end column, start and end page */
    uint16_t col, page;           /* where the next pixel goes */
    int have_high;                /* a pixel's first byte came: high */
    uint8_t high;
    uint8_t madctl;
    uint8_t scan;                 /* Display Function Control's second parameter (GS, SS) */
    uint16_t tfa, vsa, bfa, ssa;  /* the hardware scroll: VSCRDEF's areas, VSCRSADD */
    int in_reset, sleeping, on;
    uint8_t backlight;            /* the LED's brightness (its PWM duty), 0-255, as the FPGA drives it */
};

#define ILI9341_GS 0x40           /* in scan: the gate scan reversed */
#define ILI9341_SS 0x20           /* in scan: the source scan reversed */

/* Power on: the registers' defaults, the memory black, the backlight full */
void ili9341_init(struct ili9341 *p);
/* The RESX line: 0 holds the controller in reset, which ignores what it receives */
void ili9341_reset_line(struct ili9341 *p, int level);
void ili9341_command(struct ili9341 *p, uint8_t command);
void ili9341_data(struct ili9341 *p, uint8_t data);
/* Whether the glass shows the memory: out of reset and sleep, and on */
int ili9341_showing(const struct ili9341 *p);
/* The memory line shown at row y of the glass (0 the top), through the scan direction and the scroll */
int ili9341_glass_line(const struct ili9341 *p, int y);
/* The pixel at x, y on the glass (0, 0 the top left): white while blank */
uint16_t ili9341_glass_pixel(const struct ili9341 *p, int x, int y);

#endif
