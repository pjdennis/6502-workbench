#include <stdio.h>
#include <string.h>

#include "greatest.h"
#include "../hex_text.h"

/* Reads `text` as a hex listing into `out`; returns hex_text_read's result. */
static long read_text(const char *text, unsigned char *out, long max, int *line) {
    FILE *f = tmpfile();
    if (!f) return -99;
    fputs(text, f);
    rewind(f);
    long n = hex_text_read(f, out, max, line);
    fclose(f);
    return n;
}

TEST hex_text_reads_bytes_after_dollar(void) {
    unsigned char out[8];
    int line = 0;
    long n = read_text("$20 $06 $f0\n$4C\n", out, sizeof out, &line);
    ASSERT_EQ_FMT(4L, n, "%ld");
    ASSERT_EQ_FMT(0x20, out[0], "%02x");
    ASSERT_EQ_FMT(0x06, out[1], "%02x");
    ASSERT_EQ_FMT(0xF0, out[2], "%02x");
    ASSERT_EQ_FMT(0x4C, out[3], "%02x");
    PASS();
}

/* The seed's listing: the word DATA, though its letters are hex digits, is not bytes, and a
 * comment may hold anything, a '$' and digits included. */
TEST hex_text_ignores_words_and_comments(void) {
    unsigned char out[8];
    int line = 0;
    long n = read_text("; asm0: DATA $FF only\n"
                       "\n"
                       "DATA $20 $06 $F0  ; 2000: JSR read ($F006)\n"
                       "\tDATA $90 $03\t; BCC $2008\n", out, sizeof out, &line);
    ASSERT_EQ_FMT(5L, n, "%ld");
    ASSERT_EQ_FMT(0x20, out[0], "%02x");
    ASSERT_EQ_FMT(0x90, out[3], "%02x");
    ASSERT_EQ_FMT(0x03, out[4], "%02x");
    PASS();
}

TEST hex_text_empty_is_no_bytes(void) {
    unsigned char out[2];
    int line = 0;
    ASSERT_EQ_FMT(0L, read_text("; nothing\n", out, sizeof out, &line), "%ld");
    PASS();
}

/* A byte is exactly two digits: one, or three and more (a 16-bit value), is refused with its line. */
TEST hex_text_refuses_other_lengths(void) {
    unsigned char out[8];
    int line = 0;
    ASSERT_EQ_FMT((long)HEX_TEXT_BAD_BYTE, read_text("$01\n$2\n", out, sizeof out, &line), "%ld");
    ASSERT_EQ_FMT(2, line, "%d");
    line = 0;
    ASSERT_EQ_FMT((long)HEX_TEXT_BAD_BYTE, read_text("$01\n\n$2000\n", out, sizeof out, &line), "%ld");
    ASSERT_EQ_FMT(3, line, "%d");
    line = 0;
    ASSERT_EQ_FMT((long)HEX_TEXT_BAD_BYTE, read_text("$G1\n", out, sizeof out, &line), "%ld");
    ASSERT_EQ_FMT(1, line, "%d");
    line = 0;
    ASSERT_EQ_FMT((long)HEX_TEXT_BAD_BYTE, read_text("$0", out, sizeof out, &line), "%ld");
    ASSERT_EQ_FMT(1, line, "%d");
    PASS();
}

TEST hex_text_refuses_more_than_fits(void) {
    unsigned char out[2];
    int line = 0;
    ASSERT_EQ_FMT(2L, read_text("$01 $02\n", out, sizeof out, &line), "%ld");
    ASSERT_EQ_FMT((long)HEX_TEXT_TOO_LONG, read_text("$01 $02\n$03\n", out, sizeof out, &line), "%ld");
    ASSERT_EQ_FMT(2, line, "%d");
    PASS();
}

SUITE(hex_text_suite) {
    RUN_TEST(hex_text_reads_bytes_after_dollar);
    RUN_TEST(hex_text_ignores_words_and_comments);
    RUN_TEST(hex_text_empty_is_no_bytes);
    RUN_TEST(hex_text_refuses_other_lengths);
    RUN_TEST(hex_text_refuses_more_than_fits);
}

GREATEST_MAIN_DEFS();

int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(hex_text_suite);
    GREATEST_MAIN_END();
}
