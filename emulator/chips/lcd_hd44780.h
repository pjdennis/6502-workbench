#ifndef EMULATOR_CHIPS_LCD_HD44780_H
#define EMULATOR_CHIPS_LCD_HD44780_H

#include <stdint.h>
#include "../bus.h"
#include "via_6522.h"

/* HD44780 LCD controller, wendy2c wiring (per base_config_wendy2c.inc):
 *
 *   PORTA bit 0      RS  (0 = command, 1 = data)
 *   PORTA bit 3      RW  (0 = write, 1 = read busy flag)
 *   PORTA bits 4..7  D4..D7 (4-bit data nibble)
 *   PORTB bit 5      E   (data latched on falling edge)
 *
 * Default 16x2 (per the active block in base_config_wendy2c.inc); 20x4
 * supported via lcd_hd44780_set_geometry().
 *
 * The chip subscribes to VIA pin state by polling via inspectors on each
 * tick; a falling-edge on E captures the current data nibble. We model
 * the standard 4-bit init dance: after reset the controller is in
 * 8-bit mode, and a function-set with DL=0 transitions to 4-bit mode. */

#define LCD_DDRAM_SIZE  80
#define LCD_CGRAM_SIZE  64

struct lcd_hd44780_state {
    /* Display memory. */
    uint8_t ddram[LCD_DDRAM_SIZE];
    uint8_t cgram[LCD_CGRAM_SIZE];

    /* Geometry. */
    uint8_t rows;     /* default 2 */
    uint8_t cols;     /* default 16 */

    /* HD44780 registers. */
    uint8_t ac;              /* address counter (DDRAM or CGRAM) */
    uint8_t cgram_mode;      /* 1 if AC addresses CGRAM */
    uint8_t entry_id;        /* 1 = increment, 0 = decrement */
    uint8_t entry_s;         /* shift bit */
    uint8_t display_on;
    uint8_t cursor_on;
    uint8_t blink_on;
    uint8_t two_line_mode;
    uint8_t four_bit_mode;   /* 0 = 8-bit (default after reset), 1 = 4-bit */
    uint8_t font_5x10;       /* 0 = 5x8 (default), 1 = 5x10 (only valid in 1-line mode) */

    /* 4-bit nibble assembly state. */
    uint8_t high_nibble;
    uint8_t high_nibble_pending;

    /* E-line edge detection. */
    uint8_t prev_e;

    /* Dirty since last lcd_render. */
    uint8_t dirty;

    /* External hookup. */
    const struct via_6522_state *via;

    /* HD44780 byte-write masks. */
    uint8_t rs_bit;   /* default $01 -- PORTA bit 0 */
    uint8_t rw_bit;   /* default $08 -- PORTA bit 3 */
    uint8_t data_mask;/* default $F0 -- PORTA bits 4..7 */
    uint8_t e_bit_b;  /* default $20 -- PORTB bit 5 */
};

void lcd_hd44780_init(struct chip *chip, struct lcd_hd44780_state *state,
                      const struct via_6522_state *via);

/* Override the default 16x2 geometry. cols up to 20, rows up to 4. */
void lcd_hd44780_set_geometry(struct lcd_hd44780_state *state,
                              uint8_t rows, uint8_t cols);

/* Render the currently-visible DDRAM into a buffer of (rows*cols+1)
 * bytes (a NUL terminator is written). Output uses 7-bit ASCII for
 * 0x20..0x7E; CGRAM slots 6 and 7 are rendered as '~' and '\\' per the
 * plan; everything else falls back to '?'. Returns 1 if state was
 * dirty since the last render (and clears the dirty flag). */
int lcd_hd44780_render(struct lcd_hd44780_state *state, char *out_buf);

/* Copy the currently-visible DDRAM bytes, unmapped, into a buffer of
 * rows*cols bytes in the same row order as lcd_hd44780_render. */
void lcd_hd44780_visible_bytes(const struct lcd_hd44780_state *state,
                               uint8_t *out_buf);

#endif
