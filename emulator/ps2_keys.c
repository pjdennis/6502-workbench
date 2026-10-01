/* ps2_encode_key: terminal key bytes to PS/2 scan code set 2 (see ps2_keys.h). */
#include "ps2_keys.h"

#include <string.h>

#define SHIFT     0x12
#define CTRL      0x14
#define ENTER     0x5A
#define BACKSPACE 0x66
#define TAB       0x0D
#define ESCAPE    0x76
#define EXTENDED  0x100    /* E0-prefixed key */
#define RELEASE   0xF0
#define PREFIX    0xE0

/* Unshifted and shifted characters of the main keys, by scan code. The
 * letters come first, a to z: control codes $01-$1A index them. */
static const struct { uint8_t code; char plain, shifted; } main_keys[] = {
    {0x1C, 'a', 'A'}, {0x32, 'b', 'B'}, {0x21, 'c', 'C'}, {0x23, 'd', 'D'},
    {0x24, 'e', 'E'}, {0x2B, 'f', 'F'}, {0x34, 'g', 'G'}, {0x33, 'h', 'H'},
    {0x43, 'i', 'I'}, {0x3B, 'j', 'J'}, {0x42, 'k', 'K'}, {0x4B, 'l', 'L'},
    {0x3A, 'm', 'M'}, {0x31, 'n', 'N'}, {0x44, 'o', 'O'}, {0x4D, 'p', 'P'},
    {0x15, 'q', 'Q'}, {0x2D, 'r', 'R'}, {0x1B, 's', 'S'}, {0x2C, 't', 'T'},
    {0x3C, 'u', 'U'}, {0x2A, 'v', 'V'}, {0x1D, 'w', 'W'}, {0x22, 'x', 'X'},
    {0x35, 'y', 'Y'}, {0x1A, 'z', 'Z'},
    {0x16, '1', '!'}, {0x1E, '2', '@'}, {0x26, '3', '#'}, {0x25, '4', '$'},
    {0x2E, '5', '%'}, {0x36, '6', '^'}, {0x3D, '7', '&'}, {0x3E, '8', '*'},
    {0x46, '9', '('}, {0x45, '0', ')'},
    {0x0E, '`', '~'}, {0x4E, '-', '_'}, {0x55, '=', '+'}, {0x54, '[', '{'},
    {0x5B, ']', '}'}, {0x5D, '\\', '|'}, {0x4C, ';', ':'}, {0x52, '\'', '"'},
    {0x41, ',', '<'}, {0x49, '.', '>'}, {0x4A, '/', '?'}, {0x29, ' ', ' '},
};

/* ESC sequences (after the ESC) and their extended keys. */
static const struct { const char *seq; int key; uint8_t modifier; } sequences[] = {
    {"[1;5C", EXTENDED | 0x74, CTRL}, {"[1;5D", EXTENDED | 0x6B, CTRL},
    {"[1~", EXTENDED | 0x6C, 0}, {"[2~", EXTENDED | 0x70, 0}, {"[3~", EXTENDED | 0x71, 0},
    {"[4~", EXTENDED | 0x69, 0}, {"[5~", EXTENDED | 0x7D, 0}, {"[6~", EXTENDED | 0x7A, 0},
    {"[7~", EXTENDED | 0x6C, 0}, {"[8~", EXTENDED | 0x69, 0},
    {"[A", EXTENDED | 0x75, 0}, {"[B", EXTENDED | 0x72, 0},
    {"[C", EXTENDED | 0x74, 0}, {"[D", EXTENDED | 0x6B, 0},
    {"[H", EXTENDED | 0x6C, 0}, {"[F", EXTENDED | 0x69, 0},
    {"OA", EXTENDED | 0x75, 0}, {"OB", EXTENDED | 0x72, 0},
    {"OC", EXTENDED | 0x74, 0}, {"OD", EXTENDED | 0x6B, 0},
    {"OH", EXTENDED | 0x6C, 0}, {"OF", EXTENDED | 0x69, 0},
};

/* Press and release `key`, holding `modifier` (0 for none) around it. */
static int press(int key, uint8_t modifier, uint8_t *out) {
    int n = 0;
    uint8_t code = (uint8_t)(key & 0xFF);
    if (modifier) out[n++] = modifier;
    if (key & EXTENDED) out[n++] = PREFIX;
    out[n++] = code;
    if (key & EXTENDED) out[n++] = PREFIX;
    out[n++] = RELEASE;
    out[n++] = code;
    if (modifier) { out[n++] = RELEASE; out[n++] = modifier; }
    return n;
}

int ps2_encode_key(const uint8_t *in, size_t len, size_t *consumed, uint8_t *out) {
    uint8_t c = in[0];
    *consumed = 1;
    if (c == 0x1B) {
        for (size_t i = 0; i < sizeof(sequences) / sizeof(sequences[0]); i++) {
            size_t n = strlen(sequences[i].seq);
            if (len > n && !memcmp(in + 1, sequences[i].seq, n)) {
                *consumed = n + 1;
                return press(sequences[i].key, sequences[i].modifier, out);
            }
        }
        return press(ESCAPE, 0, out);
    }
    if (c == '\r' || c == '\n') return press(ENTER, 0, out);
    if (c == 0x08 || c == 0x7F) return press(BACKSPACE, 0, out);
    if (c == '\t') return press(TAB, 0, out);
    if (c >= 0x01 && c <= 0x1A) return press(main_keys[c - 1].code, CTRL, out);
    for (size_t i = 0; i < sizeof(main_keys) / sizeof(main_keys[0]); i++) {
        if (c == (uint8_t)main_keys[i].plain)   return press(main_keys[i].code, 0, out);
        if (c == (uint8_t)main_keys[i].shifted) return press(main_keys[i].code, SHIFT, out);
    }
    return 0;
}
