/* Tests for the state snapshot the --web server sends the page (web_snapshot_json in emulator/web_server.c):
 * its JSON, field by field. */

#include <stdio.h>
#include <string.h>
#include "greatest.h"
#include "../web_server.h"

static struct web_snapshot snap;
static char json[8192];

static void fill(void) {
    memset(&snap, 0, sizeof(snap));
    snap.lcd_rows = 1;
    snap.lcd_cols = 2;
    snap.ddram_visible[0] = 'H';
    snap.ddram_visible[1] = 'i';
    snap.cgram[0] = 0xFF;                 /* only the low 5 bits are pixels */
    snap.cursor_row = 0; snap.cursor_col = 1;
    snap.cursor_on = 1; snap.display_on = 1; snap.panel_rows = 1;
    snap.porta = 0x21; snap.portb = 0x42; snap.ddra = 0x61; snap.ddrb = 0xFF;
    snap.osc_ticks = 1000; snap.cpu_cycles = 500; snap.clock_mhz = 1.999; snap.target_mhz = 2.0;
    snap.pc = 0x1234;
    snap.n_leds = 2; snap.leds[0] = 1; snap.leds[1] = 0;
}

/* Whether the JSON holds want */
static int has(const char *want) {
    return strstr(json, want) != NULL;
}

TEST the_lcd_pins_clock_and_leds(void) {
    fill();
    int n = web_snapshot_json(&snap, json, sizeof(json));
    ASSERT_EQ_FMT((int)strlen(json), n, "%d");
    ASSERT(has("{\"lcd\":{\"rows\":1,\"cols\":2,\"ddram\":[72,105],\"cgram\":[31,0,"));
    ASSERT(has("\"cur\":[0,1],\"cur_on\":1,\"blink_on\":0,\"disp_on\":1,\"f5x10\":0,\"panel_rows\":1,"
               "\"panel_5x10\":0},"));
    ASSERT(has("\"porta\":33,\"portb\":66,\"ddra\":97,\"ddrb\":255,"));
    ASSERT(has("\"osc\":1000,\"cpu\":500,\"mhz\":1.999,\"target_mhz\":2.000,\"pc\":4660,\"irq\":0,\"stp\":0,"));
    ASSERT_EQ('}', json[n - 1]);
    ASSERT(has("\"leds\":[1,0]}"));
    PASS();
}

TEST no_graphic_display_no_gd(void) {
    fill();
    web_snapshot_json(&snap, json, sizeof(json));
    ASSERT_FALSE(has("\"gd\""));
    PASS();
}

TEST the_graphic_displays_glass(void) {
    /* How the glass shows the display's memory (which goes to the page as deltas, not JSON): on or blank, the
     * backlight, the scans and the hardware scroll */
    static struct ili9341 panel;
    ili9341_init(&panel);
    fill();
    snap.display = &panel;
    web_snapshot_json(&snap, json, sizeof(json));
    ASSERT(has(",\"gd\":{\"on\":0,\"bl\":255,\"gs\":0,\"ss\":0,\"scroll\":[0,320,0,0]}}"));
    panel.sleeping = 0;
    panel.on = 1;
    panel.backlight = 128;
    panel.scan = ILI9341_GS | ILI9341_SS;
    panel.tfa = 16; panel.vsa = 288; panel.bfa = 16; panel.ssa = 48;
    web_snapshot_json(&snap, json, sizeof(json));
    ASSERT(has(",\"gd\":{\"on\":1,\"bl\":128,\"gs\":1,\"ss\":1,\"scroll\":[16,288,16,48]}}"));
    PASS();
}

TEST too_small_a_buffer_is_refused(void) {
    fill();
    ASSERT_EQ(-1, web_snapshot_json(&snap, json, 64));
    PASS();
}

SUITE(web_snapshot_suite) {
    RUN_TEST(the_lcd_pins_clock_and_leds);
    RUN_TEST(no_graphic_display_no_gd);
    RUN_TEST(the_graphic_displays_glass);
    RUN_TEST(too_small_a_buffer_is_refused);
}

GREATEST_MAIN_DEFS();
int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(web_snapshot_suite);
    GREATEST_MAIN_END();
}
