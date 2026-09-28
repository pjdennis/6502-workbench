/* --direct-io: screen calls -> ANSI, ANSI input -> key codes (direct_io.c). */

#include <stdint.h>
#include <string.h>

#include "greatest.h"
#include "../direct_io.h"

static enum greatest_test_res screen_is(uint8_t op, uint8_t a, uint8_t y, const char *want) {
    char out[DIRECT_IO_SCREEN_MAX];
    int n = direct_io_screen(op, a, y, out);
    ASSERT_EQ_FMT((int)strlen(want), n, "%d");
    ASSERT_MEM_EQ(want, out, (size_t)n);
    PASS();
}

/* The sequences the editor's ANSI builds write (terminal.asm): a
 * parameter of 1 is left out, as a VT100 or xterm takes 1 when it is
 * missing, except a region's bottom row (missing: the last row). */
TEST screen_calls_write_the_ansi_sequences(void) {
    CHECK_CALL(screen_is(SCR_GOTO, 3, 17, "\x1b[3;17H"));
    CHECK_CALL(screen_is(SCR_GOTO, 1, 1, "\x1b[H"));
    CHECK_CALL(screen_is(SCR_GOTO, 5, 1, "\x1b[5H"));
    CHECK_CALL(screen_is(SCR_GOTO, 1, 9, "\x1b[;9H"));
    CHECK_CALL(screen_is(SCR_GOTO, 255, 100, "\x1b[255;100H"));
    CHECK_CALL(screen_is(SCR_CLEAR, 0, 0, "\x1b[2J\x1b[H"));
    CHECK_CALL(screen_is(SCR_CLEAR_EOL, 0, 0, "\x1b[K"));
    CHECK_CALL(screen_is(SCR_CURSOR_ON, 0, 0, "\x1b[?25h"));
    CHECK_CALL(screen_is(SCR_CURSOR_OFF, 0, 0, "\x1b[?25l"));
    CHECK_CALL(screen_is(SCR_REVERSE, 0, 0, "\x1b[7m"));
    CHECK_CALL(screen_is(SCR_NORMAL, 0, 0, "\x1b[m"));
    CHECK_CALL(screen_is(SCR_REGION, 2, 23, "\x1b[2;23r"));
    CHECK_CALL(screen_is(SCR_REGION, 1, 1, "\x1b[1;1r"));
    CHECK_CALL(screen_is(SCR_REGION_RESET, 0, 0, "\x1b[r"));
    CHECK_CALL(screen_is(SCR_INSERT, 4, 0, "\x1b[4@"));
    CHECK_CALL(screen_is(SCR_INSERT, 1, 0, "\x1b[@"));
    CHECK_CALL(screen_is(SCR_DELETE, 10, 0, "\x1b[10P"));
    CHECK_CALL(screen_is(SCR_DELETE, 1, 0, "\x1b[P"));
    CHECK_CALL(screen_is(SCR_SCROLL_UP, 1, 0, "\x1b[S"));
    CHECK_CALL(screen_is(SCR_SCROLL_UP, 2, 0, "\x1b[2S"));
    CHECK_CALL(screen_is(SCR_SCROLL_DOWN, 0, 0, "\x1b[0T"));
    PASS();
}

TEST unknown_screen_op_writes_nothing(void) {
    CHECK_CALL(screen_is(SCR_OP_COUNT, 0, 0, ""));
    PASS();
}

/* Scripted input: bytes to read, and whether each wait finds a byte. */
static const char *script;
static size_t script_len, script_at;
static int wait_times_out;      /* waits return $00 instead of $FF */
static int waits;
static uint16_t last_wait_ms;

static uint8_t script_read(void) {
    return script_at < script_len ? (uint8_t)script[script_at++] : 0;
}

static uint8_t script_wait(uint16_t ms) {
    last_wait_ms = ms;
    waits++;
    if (script_at >= script_len) return 0x01;
    return wait_times_out ? 0x00 : 0xFF;
}

static const struct direct_io_input input = { script_read, script_wait };

static void feed(const char *s, size_t len, int timeout) {
    direct_io_reset();
    script = s;
    script_len = len;
    script_at = 0;
    wait_times_out = timeout;
    waits = 0;
}

#define FEED(s) feed(s, sizeof(s) - 1, 0)

TEST plain_bytes_are_keys(void) {
    FEED("a\r\x06");
    ASSERT_EQ_FMT('a', direct_io_read_key(&input), "%02x");
    ASSERT_EQ_FMT('\r', direct_io_read_key(&input), "%02x");
    ASSERT_EQ_FMT(0x06, direct_io_read_key(&input), "%02x");
    PASS();
}

TEST del_is_backspace_and_high_bytes_are_nothing(void) {
    FEED("\x7f\xc3");
    ASSERT_EQ_FMT(KEY_BS, direct_io_read_key(&input), "%02x");
    ASSERT_EQ_FMT(0x00, direct_io_read_key(&input), "%02x");
    PASS();
}

TEST csi_letters(void) {
    FEED("\x1b[A\x1b[B\x1b[C\x1b[D\x1b[H\x1b[F");
    ASSERT_EQ_FMT(KEY_UP, direct_io_read_key(&input), "%02x");
    ASSERT_EQ_FMT(KEY_DOWN, direct_io_read_key(&input), "%02x");
    ASSERT_EQ_FMT(KEY_RIGHT, direct_io_read_key(&input), "%02x");
    ASSERT_EQ_FMT(KEY_LEFT, direct_io_read_key(&input), "%02x");
    ASSERT_EQ_FMT(KEY_HOME, direct_io_read_key(&input), "%02x");
    ASSERT_EQ_FMT(KEY_END, direct_io_read_key(&input), "%02x");
    PASS();
}

TEST csi_tilde_keys(void) {
    FEED("\x1b[1~\x1b[2~\x1b[3~\x1b[4~\x1b[5~\x1b[6~\x1b[7~\x1b[8~");
    static const uint8_t want[] = { KEY_HOME, 0, KEY_DEL, KEY_END, KEY_PGUP, KEY_PGDN, KEY_HOME, KEY_END };
    for (int i = 0; i < 8; i++) ASSERT_EQ_FMT(want[i], direct_io_read_key(&input), "%02x");
    PASS();
}

TEST ctrl_arrows(void) {
    FEED("\x1b[1;5C\x1b[1;5D");
    ASSERT_EQ_FMT(KEY_WORD_FWD, direct_io_read_key(&input), "%02x");
    ASSERT_EQ_FMT(KEY_WORD_BACK, direct_io_read_key(&input), "%02x");
    PASS();
}

TEST unknown_csi_is_eaten_through_its_final_byte(void) {
    FEED("\x1b[12;3xq\x1b[Zr\x1b[9~s");
    ASSERT_EQ_FMT(0x00, direct_io_read_key(&input), "%02x");
    ASSERT_EQ_FMT('q', direct_io_read_key(&input), "%02x");
    ASSERT_EQ_FMT(0x00, direct_io_read_key(&input), "%02x");   /* Z: past H */
    ASSERT_EQ_FMT('r', direct_io_read_key(&input), "%02x");
    ASSERT_EQ_FMT(0x00, direct_io_read_key(&input), "%02x");   /* 9: not 1-8, ~ eaten */
    ASSERT_EQ_FMT('s', direct_io_read_key(&input), "%02x");
    PASS();
}

TEST bare_escape_when_nothing_follows_in_time(void) {
    feed("\x1bx", 2, 1);
    ASSERT_EQ_FMT(KEY_ESC, direct_io_read_key(&input), "%02x");
    ASSERT_EQ_FMT(1, waits, "%d");
    ASSERT_EQ_FMT(100, last_wait_ms, "%u");
    ASSERT_EQ_FMT('x', direct_io_read_key(&input), "%02x");
    PASS();
}

TEST escape_then_other_byte_pushes_it_back(void) {
    FEED("\x1bx");
    ASSERT_EQ_FMT(KEY_ESC, direct_io_read_key(&input), "%02x");
    ASSERT(direct_io_pending());
    ASSERT_EQ_FMT('x', direct_io_read_key(&input), "%02x");
    ASSERT(!direct_io_pending());
    PASS();
}

TEST escape_o_f_keys_are_nothing(void) {
    FEED("\x1bOPa");
    ASSERT_EQ_FMT(0x00, direct_io_read_key(&input), "%02x");
    ASSERT_EQ_FMT('a', direct_io_read_key(&input), "%02x");
    PASS();
}

TEST escape_o_then_other_byte_is_escape_o_byte(void) {
    FEED("\x1bOx");
    ASSERT_EQ_FMT(KEY_ESC, direct_io_read_key(&input), "%02x");
    ASSERT_EQ_FMT('O', direct_io_read_key(&input), "%02x");
    ASSERT_EQ_FMT('x', direct_io_read_key(&input), "%02x");
    PASS();
}

TEST escape_o_at_end_of_input_is_escape_o(void) {
    FEED("\x1bO");
    ASSERT_EQ_FMT(KEY_ESC, direct_io_read_key(&input), "%02x");
    ASSERT_EQ_FMT('O', direct_io_read_key(&input), "%02x");
    PASS();
}

SUITE(direct_io_suite) {
    RUN_TEST(screen_calls_write_the_ansi_sequences);
    RUN_TEST(unknown_screen_op_writes_nothing);
    RUN_TEST(plain_bytes_are_keys);
    RUN_TEST(del_is_backspace_and_high_bytes_are_nothing);
    RUN_TEST(csi_letters);
    RUN_TEST(csi_tilde_keys);
    RUN_TEST(ctrl_arrows);
    RUN_TEST(unknown_csi_is_eaten_through_its_final_byte);
    RUN_TEST(bare_escape_when_nothing_follows_in_time);
    RUN_TEST(escape_then_other_byte_pushes_it_back);
    RUN_TEST(escape_o_f_keys_are_nothing);
    RUN_TEST(escape_o_then_other_byte_is_escape_o_byte);
    RUN_TEST(escape_o_at_end_of_input_is_escape_o);
}

GREATEST_MAIN_DEFS();
int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(direct_io_suite);
    GREATEST_MAIN_END();
}
