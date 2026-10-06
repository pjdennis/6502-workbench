/* Tests for emulator/web_display.c: the graphic display's pixels as messages for a page, carrying only what
 * the page lacks. A reference decoder (the format in web_display.h; emulator/web/board.js has the page's)
 * applies each message to a page's copy, which must end up as the display's memory. */

#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "greatest.h"
#include "../web_display.h"

#define LINES WEB_DISPLAY_LINES
#define WIDTH WEB_DISPLAY_WIDTH

static uint16_t memory[LINES][WIDTH];
static uint16_t page[LINES][WIDTH];
static struct web_display_shadow shadow;
static uint8_t out[1 << 17];

static int u16(const uint8_t *b) { return b[0] | b[1] << 8; }

/* Applies a message to the page; 0 if it is well formed, else -1 */
static int apply(const uint8_t *m, int n) {
    if (n < 1 || m[0] != WEB_DISPLAY_TAG) return -1;
    uint16_t colours[2] = { 0x0000, 0xFFFF };
    int p = 1;
    while (p < n) {
        if (p + 5 > n) return -1;
        int line = u16(m + p), x = m[p + 2], w = m[p + 3] + 1, h = m[p + 4] + 1;
        p += 5;
        if (line + h > LINES || x + w > WIDTH) return -1;
        for (int at = 0; at < w * h; ) {
            if (p >= n) return -1;
            int kind = m[p] >> 6, count = m[p] & 63;
            p++;
            if (!count) { count = u16(m + p); p += 2; }
            if (count == 0 || at + count > w * h) return -1;
            uint16_t c = 0;
            if (kind == 1) { c = (uint16_t)u16(m + p); p += 2; colours[1] = colours[0]; colours[0] = c; }
            if (kind == 2) c = colours[0];
            if (kind == 3) { c = colours[1]; colours[1] = colours[0]; colours[0] = c; }
            for (int i = 0; i < count; i++, at++) {
                if (kind == 0) { c = (uint16_t)u16(m + p); p += 2; }
                page[line + at / w][x + at % w] = c;
            }
        }
    }
    return p == n ? 0 : -1;
}

/* Messages until there is nothing to send, each applied; how many it took, or -1 if one was bad */
static int sync(int budget) {
    int messages = 0, n;
    while ((n = web_display_encode(&shadow, memory, out, budget)) > 0) {
        if (apply(out, n) != 0 || messages++ > 1000) return -1;
    }
    return messages;
}

static void fresh_page(void) {
    memset(memory, 0, sizeof memory);
    memset(page, 0xAA, sizeof page);
    web_display_shadow_forget(&shadow);
}

TEST a_new_page_gets_everything_then_nothing(void) {
    fresh_page();
    int n = web_display_encode(&shadow, memory, out, 1 << 15);
    /* black, a band at a time: 20 rectangles of one run */
    ASSERT_EQ_FMT(1 + 20 * (5 + 3), n, "%d");
    ASSERT_EQ(0, apply(out, n));
    ASSERT_MEM_EQ(memory, page, sizeof memory);
    ASSERT_EQ(0, web_display_encode(&shadow, memory, out, 1 << 15));
    PASS();
}

TEST one_pixel_is_one_rectangle_of_one_run(void) {
    fresh_page();
    ASSERT_EQ(1, sync(1 << 15));
    memory[300][7] = 0xF800;
    int n = web_display_encode(&shadow, memory, out, 1 << 15);
    const uint8_t want[] = { WEB_DISPLAY_TAG, 44, 1, 7, 0, 0, 0x41, 0x00, 0xF8 };
    ASSERT_EQ_FMT((int)sizeof want, n, "%d");
    ASSERT_MEM_EQ(want, out, sizeof want);
    PASS();
}

TEST a_fill_is_a_run_a_band(void) {
    fresh_page();
    ASSERT_EQ(1, sync(1 << 15));
    for (int l = 0; l < LINES; l++)
        for (int x = 0; x < WIDTH; x++) memory[l][x] = 0x001F;
    int n = web_display_encode(&shadow, memory, out, 1 << 15);
    ASSERT_EQ_FMT(1 + (5 + 5) + 19 * (5 + 3), n, "%d");   /* a new colour, then the remembered one */
    ASSERT_EQ(0, apply(out, n));
    ASSERT_MEM_EQ(memory, page, sizeof memory);
    PASS();
}

TEST a_text_cell_is_small(void) {
    /* A character cell drawn as the FPGA draws one: 16 lines of 12 pixels, white on black */
    static const uint16_t columns[12] = { 0, 0x07F8, 0x1FFE, 0x1E06, 0x3303, 0x3183, 0x30C3, 0x3063, 0x3033,
                                          0x181E, 0x1FFE, 0x07F8 };   /* '0' */
    fresh_page();
    ASSERT_EQ(1, sync(1 << 15));
    for (int x = 0; x < 12; x++)
        for (int y = 0; y < 16; y++) memory[LINES - 1 - (32 + y)][24 + x] = (columns[x] >> y) & 1 ? 0xFFFF : 0;
    int n = web_display_encode(&shadow, memory, out, 1 << 15);
    ASSERT(n < 120);
    ASSERT_EQ(0, apply(out, n));
    ASSERT_MEM_EQ(memory, page, sizeof memory);
    PASS();
}

static void noise(int line0, int lines) {
    for (int l = line0; l < line0 + lines; l++)
        for (int x = 0; x < WIDTH; x++) memory[l][x] = (uint16_t)rand();
}

TEST a_budget_spreads_a_picture_over_messages(void) {
    fresh_page();
    srand(1);
    noise(0, LINES);
    int messages = sync(8192);
    ASSERT(messages > 10);
    ASSERT_MEM_EQ(memory, page, sizeof memory);
    PASS();
}

TEST a_rectangle_over_budget_still_goes(void) {
    fresh_page();
    srand(2);
    noise(0, 16);
    int n = web_display_encode(&shadow, memory, out, 100);
    ASSERT(n > 100);
    ASSERT(n <= 100 + WEB_DISPLAY_RECT_MAX);
    ASSERT_EQ(0, apply(out, n));
    PASS();
}

TEST a_part_that_keeps_changing_does_not_starve_the_rest(void) {
    /* The top band changes before every message; the rest still arrives, a budget at a time */
    fresh_page();
    srand(3);
    noise(0, LINES);
    for (int i = 0; i < 100; i++) {
        noise(0, 16);
        int n = web_display_encode(&shadow, memory, out, 8192);
        ASSERT(n > 0);
        ASSERT_EQ(0, apply(out, n));
    }
    ASSERT_MEM_EQ(memory[16], page[16], sizeof memory - sizeof memory[0] * 16);
    PASS();
}

TEST random_changes_arrive(void) {
    fresh_page();
    srand(4);
    for (int round = 0; round < 50; round++) {
        for (int k = rand() % 8; k >= 0; k--) {
            int l = rand() % LINES, x = rand() % WIDTH, h = 1 + rand() % 40, w = 1 + rand() % 60;
            uint16_t c = rand() % 3 ? (uint16_t)(rand() % 4) * 0x5555 : (uint16_t)rand();
            for (int i = l; i < l + h && i < LINES; i++)
                for (int j = x; j < x + w && j < WIDTH; j++) memory[i][j] = rand() % 5 ? c : (uint16_t)rand();
        }
        ASSERT(sync(rand() % 2 ? 1 << 15 : 2048) >= 0);
        ASSERT_MEM_EQ(memory, page, sizeof memory);
    }
    PASS();
}

SUITE(web_display_suite) {
    RUN_TEST(a_new_page_gets_everything_then_nothing);
    RUN_TEST(one_pixel_is_one_rectangle_of_one_run);
    RUN_TEST(a_fill_is_a_run_a_band);
    RUN_TEST(a_text_cell_is_small);
    RUN_TEST(a_budget_spreads_a_picture_over_messages);
    RUN_TEST(a_rectangle_over_budget_still_goes);
    RUN_TEST(a_part_that_keeps_changing_does_not_starve_the_rest);
    RUN_TEST(random_changes_arrive);
}

GREATEST_MAIN_DEFS();
int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(web_display_suite);
    GREATEST_MAIN_END();
}
