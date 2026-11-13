#ifndef EMULATOR_HEX_TEXT_H
#define EMULATOR_HEX_TEXT_H

#include <stdio.h>

/* A hex listing: a program written out as bytes in text, as one would key it in at a front
 * panel or a hex keypad. The emulator's --hex loads its code file this way; the assembler
 * chain's seed (asm/00/asm.asm) is one.
 *
 * Each '$' followed by exactly two hex digits is a byte. A ';' starts a comment, to the end
 * of the line. Everything else is ignored, so a listing may carry words (the seed's "DATA",
 * whose letters are themselves hex digits) and layout. */

#define HEX_TEXT_BAD_BYTE (-1L)   /* a '$' not followed by exactly two hex digits */
#define HEX_TEXT_TOO_LONG (-2L)   /* more than max bytes */

/* Reads the listing in `in` into `out` (at most `max` bytes). Returns the number of bytes, or
 * one of the errors above with the line it is on (from 1) in *line. */
long hex_text_read(FILE *in, unsigned char *out, long max, int *line);

#endif
