#ifndef EMULATOR_LCD_REPORT_H
#define EMULATOR_LCD_REPORT_H

#include <stdint.h>
#include <stdio.h>

#include "chips/lcd_hd44780.h"

/* LCD output shared by the bus-model machines.
 *
 * --lcd-trace: lcd_report_trace appends a frame to fp if the LCD changed
 * since the last render. Format (so tests can grep / split by separator):
 *
 *   --- osc=<N> cpu=<N> pc=$<HHHH> ---
 *   |row0|
 *   |row1|
 *   ...
 *
 * Hooking on a "dirty since last render" basis means an LCD that
 * settles between batches captures one frame per stable state, which
 * is what tests want -- not one per character write. Does nothing when
 * fp is NULL. */
void lcd_report_trace(FILE *fp, struct lcd_hd44780_state *lcd, uint64_t osc_ticks);

/* The end-of-run summary: "<prefix>: lcd:" with one "|...|" line per
 * row, then "<prefix>: lcd-hex:" with the raw DDRAM bytes, so CGRAM
 * custom characters (which the text frame can only show as '?') are
 * distinguishable. */
void lcd_report_final(FILE *fp, const char *prefix, struct lcd_hd44780_state *lcd);

#endif
