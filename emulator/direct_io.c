#include "direct_io.h"

#include <stdio.h>

/* ---- Screen calls -> ANSI ---- */

int direct_io_screen(uint8_t op, uint8_t a, uint8_t y, char *out) {
    switch (op) {
        case SCR_GOTO:         return sprintf(out, "\x1b[%u;%uH", a, y);
        case SCR_CLEAR:        return sprintf(out, "\x1b[2J\x1b[H");
        case SCR_CLEAR_EOL:    return sprintf(out, "\x1b[K");
        case SCR_CURSOR_ON:    return sprintf(out, "\x1b[?25h");
        case SCR_CURSOR_OFF:   return sprintf(out, "\x1b[?25l");
        case SCR_REVERSE:      return sprintf(out, "\x1b[7m");
        case SCR_NORMAL:       return sprintf(out, "\x1b[0m");
        case SCR_REGION:       return sprintf(out, "\x1b[%u;%ur", a, y);
        case SCR_REGION_RESET: return sprintf(out, "\x1b[r");
        case SCR_INSERT:       return sprintf(out, "\x1b[%u@", a);
        case SCR_DELETE:       return sprintf(out, "\x1b[%uP", a);
        case SCR_SCROLL_UP:    return sprintf(out, "\x1b[%uS", a);
        case SCR_SCROLL_DOWN:  return sprintf(out, "\x1b[%uT", a);
    }
    return 0;
}

/* ---- ANSI input -> key codes ----
 *
 * A port of read_key in toolchain/asm2/editor/input.asm, with its
 * two-deep pushback: keep them in step. */

#define ESC_WAIT_MS 100

static uint8_t pushback[2];
static int pushback_count;

static uint8_t read_byte(const struct direct_io_input *in) {
    if (pushback_count) return pushback[--pushback_count];
    return in->read();
}

static void unread(uint8_t byte) {
    pushback[pushback_count++] = byte;
}

/* Unknown CSI sequence, `byte` the last read: drain through the final
 * byte ($40 and up) or a $00 (end of input). */
static uint8_t eat(const struct direct_io_input *in, uint8_t byte) {
    while (byte && byte < 0x40) byte = read_byte(in);
    return 0x00;
}

static uint8_t read_csi(const struct direct_io_input *in) {
    static const uint8_t final_keys[] = {       /* ESC[A .. ESC[H */
        KEY_UP, KEY_DOWN, KEY_RIGHT, KEY_LEFT, 0, KEY_END, 0, KEY_HOME
    };
    static const uint8_t tilde_keys[] = {       /* ESC[1~ .. ESC[8~ */
        KEY_HOME, 0, KEY_DEL, KEY_END, KEY_PGUP, KEY_PGDN, KEY_HOME, KEY_END
    };
    uint8_t b = read_byte(in);
    if (b >= 'A') return b <= 'H' ? final_keys[b - 'A'] : eat(in, b);
    if (b < '1' || b >= '9') return eat(in, b);
    uint8_t digit = b;
    b = read_byte(in);
    if (b == '~') return tilde_keys[digit - '1'];
    if (b != ';') return eat(in, b);
    b = read_byte(in);
    if (b != '5') return eat(in, b);                    /* Ctrl modifier only */
    b = read_byte(in);
    if (b == 'C') return KEY_WORD_FWD;
    if (b == 'D') return KEY_WORD_BACK;
    return eat(in, b);
}

uint8_t direct_io_read_key(const struct direct_io_input *in) {
    uint8_t b = read_byte(in);
    if (b < 0x7F && b != KEY_ESC) return b;
    if (b == 0x7F) return KEY_BS;
    if (b > 0x7F) return 0x00;                          /* not ASCII */
    if (in->wait(ESC_WAIT_MS) != 0xFF) return KEY_ESC;  /* bare Escape */
    b = read_byte(in);
    if (b == '[') return read_csi(in);
    if (b == 'O') {
        /* ESC O P..S are F1-F4: nothing. Anything else after ESC O, or
         * nothing in time, is Escape then O typed quickly. */
        if (in->wait(ESC_WAIT_MS) == 0xFF) {
            b = read_byte(in);
            if (b >= 'P' && b <= 'S') return 0x00;
            unread(b);
        }
        b = 'O';
    }
    unread(b);
    return KEY_ESC;
}

int direct_io_pending(void) { return pushback_count; }

void direct_io_reset(void) { pushback_count = 0; }
