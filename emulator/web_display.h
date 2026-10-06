#ifndef EMULATOR_WEB_DISPLAY_H
#define EMULATOR_WEB_DISPLAY_H

#include <stdint.h>
#include "chips/ili9341.h"

/* The graphic display's pixels on their way to a page: binary WebSocket messages that carry only what the
 * page doesn't have yet. The server keeps a shadow per page of the display's memory as that page has it; each
 * snapshot, web_display_encode compares the memory with the shadow and sends what differs, up to a budget,
 * and the rest the next time (from where it stopped, so a part that keeps changing can't starve the rest).
 * A new page's shadow is unknown, so it gets everything, a budget at a time.
 *
 * The pixels are the display's frame memory (ili9341.h): WEB_DISPLAY_LINES lines of WEB_DISPLAY_WIDTH RGB565
 * pixels, as the panel scans them. How they show on the glass (the hardware scroll, the scan direction, on
 * or off, the backlight) is the snapshot's JSON, so a scroll is a few numbers, not pixels.
 *
 * A message is the tag byte WEB_DISPLAY_TAG, then rectangles, each a header and its pixels:
 *   u16 line, u8 x, u8 width - 1, u8 height - 1     (integers little-endian; height at most 16 lines)
 *   runs covering width * height pixels, row by row, a run carrying on into the next row:
 *     a byte, kind << 6 | n (n 1-63 pixels), or kind << 6 then a u16 n;
 *     kind 0: n pixels follow, u16 each;
 *     kind 1: a u16 colour follows: n pixels of it, and it becomes the first of two remembered colours;
 *     kind 2: n pixels of the first remembered colour;
 *     kind 3: n pixels of the second, which then becomes the first (they swap).
 *   The remembered colours start each message as black ($0000), then white ($FFFF).
 * The rectangles are bands of up to 16 changed lines, each as wide as its lines' changes. A fill is a run per
 * band; a text cell, mostly runs of black and white of one byte each. */

#define WEB_DISPLAY_TAG 0x02
#define WEB_DISPLAY_LINES ILI9341_LINES
#define WEB_DISPLAY_WIDTH ILI9341_WIDTH
#define WEB_DISPLAY_BAND 16
/* The most a rectangle can take: its header, and every pixel different */
#define WEB_DISPLAY_RECT_MAX (5 + 3 + 2 * WEB_DISPLAY_BAND * WEB_DISPLAY_WIDTH)

struct web_display_shadow {
    uint16_t pixels[WEB_DISPLAY_LINES][WEB_DISPLAY_WIDTH];
    uint8_t known[WEB_DISPLAY_LINES];   /* the page has the line */
    int next_line;                      /* where the next message starts */
};

/* A new page: it has nothing */
void web_display_shadow_forget(struct web_display_shadow *s);
/* A message of what memory has that the page (its shadow) doesn't, in out, which has room for budget +
 * WEB_DISPLAY_RECT_MAX bytes; the shadow then has what the message carries. Returns the message's length, or
 * 0 if the page has everything. The length is at most budget, unless the first rectangle alone is more: a
 * message always carries something. */
int web_display_encode(struct web_display_shadow *s, const uint16_t (*memory)[WEB_DISPLAY_WIDTH], uint8_t *out,
                       int budget);

#endif
