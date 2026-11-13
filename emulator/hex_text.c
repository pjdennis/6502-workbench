#include "hex_text.h"

static int hex_digit(int c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}

long hex_text_read(FILE *in, unsigned char *out, long max, int *line) {
    long count = 0;
    int at_line = 1;
    int c = fgetc(in);
    while (c != EOF) {
        if (c == '\n') {
            at_line++;
            c = fgetc(in);
        } else if (c == ';') {
            while (c != EOF && c != '\n') c = fgetc(in);
        } else if (c == '$') {
            int high = hex_digit(c = fgetc(in));
            int low = high < 0 ? -1 : hex_digit(c = fgetc(in));
            if (low >= 0) c = fgetc(in);
            if (low < 0 || hex_digit(c) >= 0) {
                *line = at_line;
                return HEX_TEXT_BAD_BYTE;
            }
            if (count >= max) {
                *line = at_line;
                return HEX_TEXT_TOO_LONG;
            }
            out[count++] = (unsigned char)(high << 4 | low);
        } else {
            c = fgetc(in);
        }
    }
    return count;
}
