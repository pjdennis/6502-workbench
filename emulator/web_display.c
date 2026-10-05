/* The graphic display's pixels as messages for a page (see web_display.h). */
#include <string.h>
#include "web_display.h"

#define LINES WEB_DISPLAY_LINES
#define WIDTH WEB_DISPLAY_WIDTH
enum { LITERAL, COLOUR, FIRST, SECOND };

void web_display_shadow_forget(struct web_display_shadow *s) { memset(s, 0, sizeof(*s)); }

struct writer {
    uint8_t *out;
    int pos;
    uint16_t colours[2];      /* remembered: the first, then the second */
};

static void put16(struct writer *w, int v) {
    w->out[w->pos++] = (uint8_t)v;
    w->out[w->pos++] = (uint8_t)(v >> 8);
}

static void put_run(struct writer *w, int kind, int n) {
    if (n < 64) {
        w->out[w->pos++] = (uint8_t)(kind << 6 | n);
    } else {
        w->out[w->pos++] = (uint8_t)(kind << 6);
        put16(w, n);
    }
}

/* Whether pixel i is alone (its neighbour differs) and not remembered */
static int lone(const struct writer *w, const uint16_t *px, int n, int i) {
    return (i + 1 == n || px[i + 1] != px[i]) && px[i] != w->colours[0] && px[i] != w->colours[1];
}

/* n pixels: runs of a remembered colour, of a new one, or (for pixels in a row that neither repeat nor are
 * remembered) the pixels themselves */
static void put_pixels(struct writer *w, const uint16_t *px, int n) {
    int literal = 0;          /* pixels waiting to go as themselves, before i */
    for (int i = 0; i < n; ) {
        uint16_t v = px[i];
        int run = 1;
        while (i + run < n && px[i + run] == v) run++;
        if (lone(w, px, n, i) && (literal || (i + 1 < n && lone(w, px, n, i + 1)))) {
            literal++;
            i++;
            continue;
        }
        if (literal) {
            put_run(w, LITERAL, literal);
            for (int k = i - literal; k < i; k++) put16(w, px[k]);
            literal = 0;
        }
        if (v == w->colours[0]) {
            put_run(w, FIRST, run);
        } else if (v == w->colours[1]) {
            put_run(w, SECOND, run);
            w->colours[1] = w->colours[0];
            w->colours[0] = v;
        } else {
            put_run(w, COLOUR, run);
            put16(w, v);
            w->colours[1] = w->colours[0];
            w->colours[0] = v;
        }
        i += run;
    }
    if (literal) {
        put_run(w, LITERAL, literal);
        for (int k = n - literal; k < n; k++) put16(w, px[k]);
    }
}

/* Where the line differs from what the page has: x0 to x1 - 1; 0 if nowhere */
static int changed(const struct web_display_shadow *s, const uint16_t *line, int l, int *x0, int *x1) {
    if (!s->known[l]) { *x0 = 0; *x1 = WIDTH; return 1; }
    const uint16_t *had = s->pixels[l];
    if (!memcmp(line, had, sizeof(s->pixels[l]))) return 0;
    int a = 0, b = WIDTH;
    while (line[a] == had[a]) a++;
    while (line[b - 1] == had[b - 1]) b--;
    *x0 = a;
    *x1 = b;
    return 1;
}

/* A rectangle of memory, lines l to l + h - 1, pixels x to x + width - 1, into the message */
static void put_rect(struct writer *w, const uint16_t (*memory)[WIDTH], int l, int h, int x, int width) {
    uint16_t px[WEB_DISPLAY_BAND * WIDTH];
    for (int i = 0; i < h; i++) memcpy(px + i * width, memory[l + i] + x, (size_t)width * sizeof(uint16_t));
    put16(w, l);
    w->out[w->pos++] = (uint8_t)x;
    w->out[w->pos++] = (uint8_t)(width - 1);
    w->out[w->pos++] = (uint8_t)(h - 1);
    put_pixels(w, px, width * h);
}

/* The page has the rectangle */
static void shadow_rect(struct web_display_shadow *s, const uint16_t (*memory)[WIDTH], int l, int h, int x,
                        int width) {
    for (int i = l; i < l + h; i++) {
        memcpy(s->pixels[i] + x, memory[i] + x, (size_t)width * sizeof(uint16_t));
        s->known[i] = 1;
    }
}

int web_display_encode(struct web_display_shadow *s, const uint16_t (*memory)[WIDTH], uint8_t *out,
                       int budget) {
    struct writer w = { out, 0, { 0x0000, 0xFFFF } };
    out[w.pos++] = WEB_DISPLAY_TAG;
    int band = -1, h = 0, x0 = 0, x1 = 0;    /* the band of changed lines being gathered */
    for (int i = 0; i <= LINES; i++) {
        int l = (s->next_line + i) % LINES, a = 0, b = 0;
        int more = i < LINES && changed(s, memory[l], l, &a, &b);
        if (more && band >= 0 && l == band + h && h < WEB_DISPLAY_BAND) {
            h++;
            if (a < x0) x0 = a;
            if (b > x1) x1 = b;
            continue;
        }
        if (band >= 0) {
            int before = w.pos;
            put_rect(&w, memory, band, h, x0, x1 - x0);
            if (w.pos > budget && before > 1) {
                s->next_line = band;      /* over budget: the next message starts with this rectangle */
                return before;
            }
            shadow_rect(s, memory, band, h, x0, x1 - x0);
        }
        band = more ? l : -1;
        h = 1;
        x0 = a;
        x1 = b;
    }
    return w.pos > 1 ? w.pos : 0;
}
