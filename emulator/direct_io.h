#ifndef EMULATOR_DIRECT_IO_H
#define EMULATOR_DIRECT_IO_H

#include <stdint.h>

/* --direct-io: the screen and key interface of the asm2 editor's
 * define:direct_io build, which calls screen services instead of
 * writing ANSI sequences and reads key codes instead of decoding them.
 * The emulator turns each screen call back into the ANSI sequence the
 * other builds write, and decodes ANSI input into key codes the way
 * their read_key does, so both builds produce the same output. */

/* Screen calls, in vector order from ENV_BASE + $42, 3 bytes apart. */
enum direct_io_screen_op {
    SCR_GOTO,          /* A = row, Y = column (1-based): ESC[row;colH (a 1 left out) */
    SCR_CLEAR,         /* ESC[2J ESC[H */
    SCR_CLEAR_EOL,     /* ESC[K */
    SCR_CURSOR_ON,     /* ESC[?25h */
    SCR_CURSOR_OFF,    /* ESC[?25l */
    SCR_REVERSE,       /* ESC[7m */
    SCR_NORMAL,        /* ESC[m */
    SCR_REGION,        /* A = top, Y = bottom (1-based): ESC[top;bottomr */
    SCR_REGION_RESET,  /* ESC[r */
    SCR_INSERT,        /* A = count: ESC[n@ (and the rest: a count of 1 left out) */
    SCR_DELETE,        /* A = count: ESC[nP */
    SCR_SCROLL_UP,     /* A = count: ESC[nS */
    SCR_SCROLL_DOWN,   /* A = count: ESC[nT */
    SCR_INSERT_LINES,  /* A = count: ESC[nL */
    SCR_DELETE_LINES,  /* A = count: ESC[nM */
    SCR_OP_COUNT
};

#define DIRECT_IO_SCREEN_MAX 16   /* longest sequence, with room to spare */

/* Write the ANSI sequence for a screen call to out (not terminated).
 * Returns its length, or 0 for an unknown op. */
int direct_io_screen(uint8_t op, uint8_t a, uint8_t y, char *out);

/* The editor's key codes. */
#define KEY_UP        0x80
#define KEY_DOWN      0x81
#define KEY_LEFT      0x82
#define KEY_RIGHT     0x83
#define KEY_HOME      0x84
#define KEY_END       0x85
#define KEY_PGUP      0x86
#define KEY_PGDN      0x87
#define KEY_DEL       0x88
#define KEY_WORD_FWD  0x89
#define KEY_WORD_BACK 0x8A
#define KEY_ESC       0x1B
#define KEY_BS        0x08

/* Where decoding reads input: read returns the next byte (blocking; 0
 * at end of input), wait returns $FF if a byte arrives within ms
 * milliseconds, else $00 (or $01 at end of input). */
struct direct_io_input {
    uint8_t (*read)(void);
    uint8_t (*wait)(uint16_t ms);
};

/* Read one key: a key code for an escape sequence, KEY_ESC for a bare
 * Escape, KEY_BS for DEL, the byte itself for other ASCII, and $00 for
 * input that is no key. Bytes read past the key are kept for the next
 * call. */
uint8_t direct_io_read_key(const struct direct_io_input *in);

/* Nonzero while bytes read past the last key are waiting. */
int direct_io_pending(void);

/* Forget waiting bytes (tests). */
void direct_io_reset(void);

#endif
