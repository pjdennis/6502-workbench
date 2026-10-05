/* ili9341 tests: Michael's graphic display, the ILI9341 controller and its panel. Pixels through the window
 * (CASET, PASET, RAMWR) under MADCTL, what the glass shows through the scan direction and the hardware scroll
 * (VSCRDEF, VSCRSADD), checked as hardware/michael/fpga/text/test_ili9341.py checks its model, and the resets,
 * sleep and display on/off. */

#include <stdarg.h>
#include <stdint.h>
#include "greatest.h"
#include "../chips/ili9341.h"

enum { SWRESET = 0x01, SLPIN = 0x10, SLPOUT = 0x11, DISPOFF = 0x28, DISPON = 0x29, CASET = 0x2A, PASET = 0x2B,
       RAMWR = 0x2C, VSCRDEF = 0x33, MADCTL = 0x36, VSCRSADD = 0x37, RAMWRC = 0x3C, DFUNCTR = 0xB6 };
enum { MICHAEL_MADCTL = 0xA8, INIT_MADCTL = 0x48, MICHAEL_SCAN = 0xE2 };   /* MY MV BGR; MX BGR; GD_PANEL_SCAN */

static struct ili9341 panel;

/* A command and its parameter bytes */
static void send(uint8_t command, int n, ...) {
    ili9341_command(&panel, command);
    va_list ap;
    va_start(ap, n);
    for (int i = 0; i < n; i++) ili9341_data(&panel, (uint8_t)va_arg(ap, int));
    va_end(ap);
}

/* A command whose parameters are 16-bit words, high byte first */
static void send_words(uint8_t command, int n, ...) {
    ili9341_command(&panel, command);
    va_list ap;
    va_start(ap, n);
    for (int i = 0; i < n; i++) {
        int w = va_arg(ap, int);
        ili9341_data(&panel, (uint8_t)(w >> 8));
        ili9341_data(&panel, (uint8_t)w);
    }
    va_end(ap);
}

static void pixel(uint16_t v) {
    ili9341_data(&panel, (uint8_t)(v >> 8));
    ili9341_data(&panel, (uint8_t)v);
}

static void window(int c0, int c1, int p0, int p1) {
    send_words(CASET, 2, c0, c1);
    send_words(PASET, 2, p0, p1);
}

/* The display as Michael's driver leaves it (gd_prepare_vertical): initialised, on, MY MV BGR */
static void michael_setup(void) {
    ili9341_init(&panel);
    send(DFUNCTR, 3, 0x08, MICHAEL_SCAN, 0x27);
    send(SLPOUT, 0);
    send(DISPON, 0);
    send(MADCTL, 1, MICHAEL_MADCTL);
}

TEST blank_until_out_of_sleep_and_on(void) {
    ili9341_init(&panel);
    ASSERT_FALSE(ili9341_showing(&panel));
    ASSERT_EQ_FMT(0xFFFF, ili9341_glass_pixel(&panel, 0, 0), "%04X");
    send(SLPOUT, 0);
    ASSERT_FALSE(ili9341_showing(&panel));
    send(DISPON, 0);
    ASSERT(ili9341_showing(&panel));
    ASSERT_EQ_FMT(0x0000, ili9341_glass_pixel(&panel, 0, 0), "%04X");   /* the memory starts black */
    send(DISPOFF, 0);
    ASSERT_FALSE(ili9341_showing(&panel));
    send(DISPON, 0);
    send(SLPIN, 0);
    ASSERT_FALSE(ili9341_showing(&panel));
    ASSERT_EQ(255, panel.backlight);
    PASS();
}

TEST michaels_columns_are_lines_from_the_last_and_pages_are_pixels(void) {
    /* Text cell (1, 1) as gd_show_character draws it: columns 16-31, pages 12-23, column by column */
    michael_setup();
    window(16, 31, 12, 23);
    send(RAMWR, 0);
    for (int i = 0; i < 16 * 12; i++) pixel((uint16_t)(0x1000 + i));
    for (int i = 0; i < 16 * 12; i++) {
        int column = 16 + i % 16, page = 12 + i / 16;
        ASSERT_EQ_FMT(0x1000 + i, panel.memory[ILI9341_LINES - 1 - column][page], "%04X");
    }
    ASSERT_EQ_FMT(0x0000, panel.memory[ILI9341_LINES - 1 - 15][12], "%04X");
    PASS();
}

TEST michaels_glass_has_columns_down_and_pages_across(void) {
    michael_setup();
    window(100, 100, 7, 7);
    send(RAMWR, 0);
    pixel(0xF800);
    ASSERT_EQ_FMT(0xF800, ili9341_glass_pixel(&panel, 7, 100), "%04X");
    ASSERT_EQ_FMT(0x0000, ili9341_glass_pixel(&panel, 100, 7), "%04X");
    PASS();
}

TEST without_the_scan_reversed_the_picture_turns_over(void) {
    michael_setup();
    send(DFUNCTR, 3, 0x08, 0x82, 0x27);   /* the default: GS and SS clear */
    window(100, 100, 7, 7);
    send(RAMWR, 0);
    pixel(0xF800);
    ASSERT_EQ_FMT(0xF800, ili9341_glass_pixel(&panel, ILI9341_WIDTH - 1 - 7, ILI9341_LINES - 1 - 100), "%04X");
    PASS();
}

TEST the_init_tables_madctl_mirrors_columns(void) {
    /* MX BGR: columns (0-239) are a line's pixels from the last, pages (0-319) lines */
    michael_setup();
    send(MADCTL, 1, INIT_MADCTL);
    window(3, 3, 5, 5);
    send(RAMWR, 0);
    pixel(0x1234);
    ASSERT_EQ_FMT(0x1234, panel.memory[5][ILI9341_WIDTH - 1 - 3], "%04X");
    send(MADCTL, 1, 0x80 | 0x08);            /* MY BGR: lines from the last */
    window(3, 3, 5, 5);
    send(RAMWR, 0);
    pixel(0x4321);
    ASSERT_EQ_FMT(0x4321, panel.memory[ILI9341_LINES - 1 - 5][3], "%04X");
    PASS();
}

TEST rgb_order_swaps_red_and_blue(void) {
    michael_setup();
    send(MADCTL, 1, 0x20);                   /* MV, BGR clear */
    window(0, 0, 0, 1);
    send(RAMWR, 0);
    pixel(0xF800);
    pixel(0x07E0);
    ASSERT_EQ_FMT(0x001F, panel.memory[0][0], "%04X");
    ASSERT_EQ_FMT(0x07E0, panel.memory[0][1], "%04X");
    PASS();
}

TEST writes_wrap_to_the_windows_start_and_ramwrc_carries_on(void) {
    michael_setup();
    window(0, 1, 0, 0);
    send(RAMWR, 0);
    pixel(1); pixel(2); pixel(3);            /* the third wraps to the first */
    ASSERT_EQ_FMT(3, panel.memory[ILI9341_LINES - 1][0], "%u");
    ASSERT_EQ_FMT(2, panel.memory[ILI9341_LINES - 2][0], "%u");
    ili9341_command(&panel, 0x00);           /* NOP between */
    ili9341_command(&panel, RAMWRC);
    pixel(4);
    ASSERT_EQ_FMT(4, panel.memory[ILI9341_LINES - 2][0], "%u");
    PASS();
}

TEST a_command_drops_half_a_pixel(void) {
    michael_setup();
    window(0, 0, 0, 1);
    send(RAMWR, 0);
    ili9341_data(&panel, 0xAB);
    send(RAMWR, 0);
    pixel(0x0102);
    ASSERT_EQ_FMT(0x0102, panel.memory[ILI9341_LINES - 1][0], "%04X");
    ASSERT_EQ_FMT(0x0000, panel.memory[ILI9341_LINES - 1][1], "%04X");
    PASS();
}

/* A text row's mark, as test_ili9341.py's draw_row: the first pixel column of memory row r's 16 columns */
static void draw_row(int memory_row, uint16_t value) {
    window(memory_row * 16, memory_row * 16 + 15, 0, 0);
    send(RAMWR, 0);
    for (int i = 0; i < 16; i++) pixel(value);
}

/* The mark each text row of the glass shows */
static void shown_rows(int *rows) {
    for (int r = 0; r < 20; r++) rows[r] = ili9341_glass_pixel(&panel, 0, r * 16);
}

TEST the_graphic_drivers_whole_screen_scroll(void) {
    /* gd_scroll_up draws row r at memory row (r + scrolled) mod 20 and sets VSCRSADD to (20 - scrolled) * 16 */
    for (int scrolled = 0; scrolled < 20; scrolled++) {
        michael_setup();
        for (int r = 0; r < 20; r++) draw_row((r + scrolled) % 20, (uint16_t)r);
        send_words(VSCRSADD, 1, (20 - scrolled) % 20 * 16);
        int rows[20];
        shown_rows(rows);
        for (int r = 0; r < 20; r++) ASSERT_EQ_FMT(r, rows[r], "%d");
    }
    PASS();
}

TEST a_region_scrolls_between_fixed_areas(void) {
    /* Rows 3-17 scroll up a row; rows 0-2 and 18-19 stay. The top fixed area is the rows below the region. */
    michael_setup();
    for (int r = 0; r < 20; r++) draw_row(r, (uint16_t)r);
    send_words(VSCRDEF, 3, (19 - 17) * 16, (17 - 3 + 1) * 16, 3 * 16);
    send_words(VSCRSADD, 1, (19 - 17) * 16 + 14 * 16);
    int rows[20], want[20] = { 0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 3, 18, 19 };
    shown_rows(rows);
    for (int r = 0; r < 20; r++) ASSERT_EQ_FMT(want[r], rows[r], "%d");
    ASSERT_EQ(ILI9341_LINES - 1 - 4 * 16, ili9341_glass_line(&panel, 3 * 16));
    PASS();
}

TEST areas_not_adding_up_to_the_panel_are_ignored(void) {
    michael_setup();
    send_words(VSCRDEF, 3, 16, 300, 16);
    ASSERT_EQ(0, panel.tfa);
    ASSERT_EQ(320, panel.vsa);
    ASSERT_EQ(0, panel.bfa);
    PASS();
}

TEST resets_restore_the_registers_and_keep_the_memory(void) {
    michael_setup();
    window(0, 0, 0, 0);
    send(RAMWR, 0);
    pixel(0x5555);
    send_words(VSCRSADD, 1, 32);
    ili9341_reset_line(&panel, 0);
    ASSERT_FALSE(ili9341_showing(&panel));
    send(SLPOUT, 0);
    send(DISPON, 0);                         /* ignored while held in reset */
    ili9341_reset_line(&panel, 1);
    ASSERT_FALSE(ili9341_showing(&panel));
    ASSERT_EQ(0, panel.madctl);
    ASSERT_EQ(0, panel.ssa);
    ASSERT_EQ(0x82, panel.scan);
    ASSERT_EQ_FMT(0x5555, panel.memory[ILI9341_LINES - 1][0], "%04X");

    michael_setup();
    send_words(VSCRSADD, 1, 32);
    send(SWRESET, 0);
    ASSERT_FALSE(ili9341_showing(&panel));
    ASSERT_EQ(0, panel.ssa);
    ASSERT_EQ(0, panel.madctl);
    PASS();
}

SUITE(ili9341_suite) {
    RUN_TEST(blank_until_out_of_sleep_and_on);
    RUN_TEST(michaels_columns_are_lines_from_the_last_and_pages_are_pixels);
    RUN_TEST(michaels_glass_has_columns_down_and_pages_across);
    RUN_TEST(without_the_scan_reversed_the_picture_turns_over);
    RUN_TEST(the_init_tables_madctl_mirrors_columns);
    RUN_TEST(rgb_order_swaps_red_and_blue);
    RUN_TEST(writes_wrap_to_the_windows_start_and_ramwrc_carries_on);
    RUN_TEST(a_command_drops_half_a_pixel);
    RUN_TEST(the_graphic_drivers_whole_screen_scroll);
    RUN_TEST(a_region_scrolls_between_fixed_areas);
    RUN_TEST(areas_not_adding_up_to_the_panel_are_ignored);
    RUN_TEST(resets_restore_the_registers_and_keep_the_memory);
}

GREATEST_MAIN_DEFS();
int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(ili9341_suite);
    GREATEST_MAIN_END();
}
