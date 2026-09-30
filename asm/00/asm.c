/*
 * asm0c.c - Minimal bootstrap assembler for 6502
 *
 * Syntax:
 *   DATA $XX $XX ...   - emit hex bytes
 *   DATA "string"      - emit ASCII string (\n for newline)
 *   ; comment          - ignored
 *   blank lines        - ignored
 *
 * Output: raw binary (start address must be in source via DATA)
 * Usage: ./asm0c input.asm output.bin
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

static FILE *out;

static void emit(unsigned char b) {
    fputc(b, out);
}

static int hex_digit(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}

static int parse_hex(const char **p) {
    /* Parse $XX or $XXXX, return value or -1 on error */
    if (**p != '$') return -1;
    (*p)++;

    int d1 = hex_digit(**p);
    if (d1 < 0) return -1;
    (*p)++;

    int d2 = hex_digit(**p);
    if (d2 < 0) return -1;
    (*p)++;

    int value = (d1 << 4) | d2;

    /* Check for 4-digit hex */
    int d3 = hex_digit(**p);
    if (d3 >= 0) {
        (*p)++;
        int d4 = hex_digit(**p);
        if (d4 < 0) return -1;
        (*p)++;
        value = (value << 8) | (d3 << 4) | d4;
    }

    return value;
}

static void skip_whitespace(const char **p) {
    while (**p == ' ' || **p == '\t') (*p)++;
}

static int process_data(const char *p) {
    /* Skip "DATA" */
    p += 4;

    while (1) {
        skip_whitespace(&p);

        /* End of line or comment */
        if (*p == '\0' || *p == '\n' || *p == ';') break;

        if (*p == '$') {
            /* Hex value */
            int value = parse_hex(&p);
            if (value < 0) {
                fprintf(stderr, "Error: invalid hex value\n");
                return -1;
            }
            if (value > 0xFF) {
                /* 16-bit value: emit little-endian */
                emit(value & 0xFF);
                emit((value >> 8) & 0xFF);
            } else {
                emit(value);
            }
        } else if (*p == '"') {
            /* String */
            p++;
            while (*p && *p != '"') {
                if (*p == '\\' && *(p+1)) {
                    p++;
                    if (*p == 'n') {
                        emit('\n');
                    } else {
                        emit(*p);
                    }
                } else {
                    emit(*p);
                }
                p++;
            }
            if (*p == '"') p++;
        } else {
            fprintf(stderr, "Error: unexpected character '%c'\n", *p);
            return -1;
        }
    }

    return 0;
}

int main(int argc, char *argv[]) {
    if (argc != 3) {
        fprintf(stderr, "Usage: %s input.asm output.bin\n", argv[0]);
        return 1;
    }

    FILE *in = fopen(argv[1], "r");
    if (!in) {
        perror(argv[1]);
        return 1;
    }

    out = fopen(argv[2], "wb");
    if (!out) {
        perror(argv[2]);
        fclose(in);
        return 1;
    }

    char line[1024];
    int line_num = 0;

    while (fgets(line, sizeof(line), in)) {
        line_num++;
        const char *p = line;

        skip_whitespace(&p);

        /* Skip empty lines and comments */
        if (*p == '\0' || *p == '\n' || *p == ';') continue;

        /* Check for DATA */
        if (strncmp(p, "DATA", 4) == 0 && (p[4] == ' ' || p[4] == '\t')) {
            if (process_data(p) < 0) {
                fprintf(stderr, "  at line %d\n", line_num);
                fclose(in);
                fclose(out);
                return 1;
            }
        } else {
            fprintf(stderr, "Error: unrecognized directive at line %d\n", line_num);
            fclose(in);
            fclose(out);
            return 1;
        }
    }

    fclose(in);
    fclose(out);

    return 0;
}
