/* Host key bytes -> PS/2 scan code set 2 groups (ps2_keys.c). */

#include <stdint.h>
#include <string.h>

#include "greatest.h"
#include "../ps2_keys.h"

/* Encode the first key of `in`; check the bytes consumed and the codes. */
static enum greatest_test_res check(const char *in, size_t in_len, size_t consumed,
                                    const uint8_t *codes, int n) {
    uint8_t out[PS2_KEY_MAX_CODES];
    size_t used = 0;
    int got = ps2_encode_key((const uint8_t *)in, in_len, &used, out);
    ASSERT_EQ_FMT(consumed, used, "%zu");
    ASSERT_EQ_FMT(n, got, "%d");
    ASSERT_MEM_EQ(codes, out, (size_t)n);
    PASS();
}

#define CHECK(in, consumed, ...) do { \
    static const uint8_t codes[] = { __VA_ARGS__ }; \
    CHECK_CALL(check(in, sizeof(in) - 1, consumed, codes, (int)sizeof(codes))); \
} while (0)

TEST lowercase_letter(void) { CHECK("a", 1, 0x1C, 0xF0, 0x1C); PASS(); }

TEST uppercase_letter_holds_shift(void) {
    CHECK("A", 1, 0x12, 0x1C, 0xF0, 0x1C, 0xF0, 0x12);
    PASS();
}

TEST shifted_punctuation(void) {
    CHECK("!", 1, 0x12, 0x16, 0xF0, 0x16, 0xF0, 0x12);
    CHECK("~", 1, 0x12, 0x0E, 0xF0, 0x0E, 0xF0, 0x12);
    PASS();
}

TEST unshifted_punctuation_and_space(void) {
    CHECK(" ", 1, 0x29, 0xF0, 0x29);
    CHECK("/", 1, 0x4A, 0xF0, 0x4A);
    CHECK("0", 1, 0x45, 0xF0, 0x45);
    PASS();
}

TEST control_code_holds_ctrl(void) {
    CHECK("\x06", 1, 0x14, 0x2B, 0xF0, 0x2B, 0xF0, 0x14);   /* Ctrl-F */
    PASS();
}

TEST enter_backspace_tab(void) {
    CHECK("\r", 1, 0x5A, 0xF0, 0x5A);
    CHECK("\n", 1, 0x5A, 0xF0, 0x5A);
    CHECK("\x08", 1, 0x66, 0xF0, 0x66);
    CHECK("\x7f", 1, 0x66, 0xF0, 0x66);
    CHECK("\t", 1, 0x0D, 0xF0, 0x0D);
    PASS();
}

TEST bare_escape(void) {
    CHECK("\x1b", 1, 0x76, 0xF0, 0x76);
    CHECK("\x1bx", 1, 0x76, 0xF0, 0x76);
    PASS();
}

TEST ansi_arrows_are_extended_keys(void) {
    CHECK("\x1b[A", 3, 0xE0, 0x75, 0xE0, 0xF0, 0x75);
    CHECK("\x1b[B", 3, 0xE0, 0x72, 0xE0, 0xF0, 0x72);
    CHECK("\x1b[C", 3, 0xE0, 0x74, 0xE0, 0xF0, 0x74);
    CHECK("\x1b[D", 3, 0xE0, 0x6B, 0xE0, 0xF0, 0x6B);
    CHECK("\x1bOA", 3, 0xE0, 0x75, 0xE0, 0xF0, 0x75);
    PASS();
}

TEST ansi_editing_keys(void) {
    CHECK("\x1b[H", 3, 0xE0, 0x6C, 0xE0, 0xF0, 0x6C);
    CHECK("\x1b[F", 3, 0xE0, 0x69, 0xE0, 0xF0, 0x69);
    CHECK("\x1b[1~", 4, 0xE0, 0x6C, 0xE0, 0xF0, 0x6C);
    CHECK("\x1b[4~", 4, 0xE0, 0x69, 0xE0, 0xF0, 0x69);
    CHECK("\x1b[5~", 4, 0xE0, 0x7D, 0xE0, 0xF0, 0x7D);
    CHECK("\x1b[6~", 4, 0xE0, 0x7A, 0xE0, 0xF0, 0x7A);
    CHECK("\x1b[3~", 4, 0xE0, 0x71, 0xE0, 0xF0, 0x71);
    CHECK("\x1b[2~", 4, 0xE0, 0x70, 0xE0, 0xF0, 0x70);
    PASS();
}

TEST ctrl_arrows(void) {
    CHECK("\x1b[1;5C", 6, 0x14, 0xE0, 0x74, 0xE0, 0xF0, 0x74, 0xF0, 0x14);
    CHECK("\x1b[1;5D", 6, 0x14, 0xE0, 0x6B, 0xE0, 0xF0, 0x6B, 0xF0, 0x14);
    PASS();
}

TEST alt_keys_as_csi_u(void) {
    /* ESC [ <code> ; 3 u: the key with Alt held (modifier 3: 1 + Alt's 2), as terminals' "CSI u" sends it */
    CHECK("\x1b[97;3u", 7, 0x11, 0x1C, 0xF0, 0x1C, 0xF0, 0x11);                 /* Alt+a */
    CHECK("\x1b[55;3u", 7, 0x11, 0x3D, 0xF0, 0x3D, 0xF0, 0x11);                 /* Alt+7 */
    CHECK("\x1b[65;3u", 7, 0x11, 0x12, 0x1C, 0xF0, 0x1C, 0xF0, 0x12, 0xF0, 0x11);   /* Alt+Shift+a */
    PASS();
}

TEST non_ascii_byte_is_skipped(void) {
    uint8_t out[PS2_KEY_MAX_CODES];
    size_t used = 0;
    ASSERT_EQ_FMT(0, ps2_encode_key((const uint8_t *)"\xc3", 1, &used, out), "%d");
    ASSERT_EQ_FMT((size_t)1, used, "%zu");
    PASS();
}

SUITE(ps2_keys_suite) {
    RUN_TEST(lowercase_letter);
    RUN_TEST(uppercase_letter_holds_shift);
    RUN_TEST(shifted_punctuation);
    RUN_TEST(unshifted_punctuation_and_space);
    RUN_TEST(control_code_holds_ctrl);
    RUN_TEST(enter_backspace_tab);
    RUN_TEST(bare_escape);
    RUN_TEST(ansi_arrows_are_extended_keys);
    RUN_TEST(ansi_editing_keys);
    RUN_TEST(ctrl_arrows);
    RUN_TEST(alt_keys_as_csi_u);
    RUN_TEST(non_ascii_byte_is_skipped);
}

GREATEST_MAIN_DEFS();
int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(ps2_keys_suite);
    GREATEST_MAIN_END();
}
