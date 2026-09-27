/* Phase 10: HD44780 LCD chip tests.
 *
 * Drives the LCD by writing through the VIA's PORTA + PORTB and
 * pulsing the E line, exactly as the wendy2c on-target code does. */

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "greatest.h"
#include "../bus.h"
#include "../chips/via_6522.h"
#include "../chips/lcd_hd44780.h"

static struct via_6522_state vs;
static struct lcd_hd44780_state ls;
static struct chip vch, lch;
static struct bus bus_;

static void setup(void) {
    via_6522_init(&vch, &vs);
    lcd_hd44780_init(&lch, &ls, &vs);
    bus_init(&bus_);
    bus_add_chip(&bus_, &vch);
    bus_add_chip(&bus_, &lch);

    /* DDRA = 0xF9 -- bits 0 (RS), 3 (RW), 4..7 (data); DDRB = 0x20 (E). */
    bus_.viacs = 1;
    bus_write(&bus_, 0xF002, 0x20);  /* DDRB */
    bus_write(&bus_, 0xF003, 0xF9);  /* DDRA */
}

/* Write one nibble of one byte through the VIA: data nibble in bits
 * 7..4 of PORTA, RS in bit 0, RW=0 in bit 3, E pulses high then low
 * via PORTB bit 5. */
static void send_nibble(uint8_t nibble, uint8_t rs) {
    uint8_t porta = (uint8_t)((nibble & 0x0F) << 4) | (rs ? 0x01 : 0x00);
    bus_write(&bus_, 0xF001, porta);  /* ORA */
    /* E high. */
    bus_write(&bus_, 0xF000, 0x20);   /* ORB: E=1 */
    bus_step(&bus_);                   /* let chips see it */
    /* E low (latches). */
    bus_write(&bus_, 0xF000, 0x00);
    bus_step(&bus_);                   /* falling edge captured */
}

/* Send a full byte = high nibble then low nibble (4-bit mode). */
static void send_byte(uint8_t byte, uint8_t rs) {
    send_nibble((uint8_t)((byte >> 4) & 0x0F), rs);
    send_nibble((uint8_t)(byte & 0x0F), rs);
}

/* Send an 8-bit-mode command (one nibble of upper bits only). The
 * function-set for the 4-bit init dance is sent this way once. */
static void send_cmd_8bit(uint8_t upper_nibble) {
    send_nibble(upper_nibble, 0);
}

TEST init_4bit_then_write_hello(void) {
    setup();

    /* 4-bit init: send function-set with DL=0 in 8-bit mode. */
    send_cmd_8bit(0x2);  /* FUNCTION_SET (0x20) with DL=0, N=0 */

    /* Now in 4-bit mode. Set up: 2-line, 5x8 -> $28. */
    send_byte(0x28, 0);
    /* Display on + cursor off + blink off -> $0C. */
    send_byte(0x0C, 0);
    /* Entry mode: increment, no shift -> $06. */
    send_byte(0x06, 0);
    /* Clear display -> $01. */
    send_byte(0x01, 0);

    /* Set DDRAM addr to $00 (already there but be explicit). */
    send_byte(0x80, 0);

    /* Write "Hello". */
    send_byte('H', 1);
    send_byte('e', 1);
    send_byte('l', 1);
    send_byte('l', 1);
    send_byte('o', 1);

    char buf[40];
    lcd_hd44780_render(&ls, buf);
    /* Buffer is 16x2 = 32 chars (no separator). First 5 chars = "Hello". */
    ASSERT_STRN_EQ("Hello", buf, 5);
    /* DDRAM at $00..$04 directly. */
    ASSERT_EQ_FMT((uint8_t)'H', ls.ddram[0], "%c");
    ASSERT_EQ_FMT((uint8_t)'e', ls.ddram[1], "%c");
    ASSERT_EQ_FMT((uint8_t)'l', ls.ddram[2], "%c");
    ASSERT_EQ_FMT((uint8_t)'l', ls.ddram[3], "%c");
    ASSERT_EQ_FMT((uint8_t)'o', ls.ddram[4], "%c");
    PASS();
}

TEST cgram_slot_6_renders_as_tilde(void) {
    setup();
    send_cmd_8bit(0x2);  /* enter 4-bit mode */
    send_byte(0x28, 0);
    send_byte(0x80, 0);
    send_byte(0x06, 1);  /* CGRAM slot 6 byte */

    char buf[40];
    lcd_hd44780_render(&ls, buf);
    ASSERT_EQ_FMT((char)'~', buf[0], "%c");
    PASS();
}

TEST visible_bytes_are_raw_ddram_in_row_order(void) {
    setup();
    send_cmd_8bit(0x2);
    send_byte(0x28, 0);
    send_byte(0x80, 0);
    send_byte(0x03, 1);  /* CGRAM slot 3: render() can only show '?' */
    send_byte('A', 1);
    send_byte(0xC0, 0);  /* line 2 */
    send_byte(0x00, 1);  /* CGRAM slot 0: render() shows ' ' */

    uint8_t bytes[32];
    lcd_hd44780_visible_bytes(&ls, bytes);
    ASSERT_EQ_FMT(0x03, bytes[0], "%02x");
    ASSERT_EQ_FMT('A', bytes[1], "%02x");
    ASSERT_EQ_FMT(0x00, bytes[16], "%02x");
    PASS();
}

TEST line2_address_starts_at_40(void) {
    setup();
    send_cmd_8bit(0x2);
    send_byte(0x28, 0);
    /* Set DDRAM to $40 (start of line 2 in 16x2). */
    send_byte(0xC0, 0);
    send_byte('X', 1);
    send_byte('Y', 1);

    char buf[40];
    lcd_hd44780_render(&ls, buf);
    /* row 0: 16 chars of $20, row 1: "XY..." */
    ASSERT_EQ_FMT((char)'X', buf[16], "%c");
    ASSERT_EQ_FMT((char)'Y', buf[17], "%c");
    PASS();
}

TEST function_set_5x10_mode(void) {
    setup();

    /* 4-bit init. */
    send_cmd_8bit(0x2);

    /* Function set: DL=1 (4-bit handled by prior step; now we're in
     * 4-bit interface mode so DL bit in the second byte still controls
     * the 4/8-bit-mode setting; in 4-bit mode we keep DL=0 means stay
     * 4-bit, but the F bit is what we care about here).
     *
     * Send 0x24 ($20 | F=1, N=0, DL=0): 4-bit, 1-line, 5x10 font.
     * We expect font_5x10 = 1 and two_line_mode = 0. */
    send_byte(0x24, 0);
    ASSERT_EQ_FMT(0, (int)ls.two_line_mode, "%d");
    ASSERT_EQ_FMT(1, (int)ls.font_5x10, "%d");

    /* In 2-line mode the controller must IGNORE F. Send $2C
     * (N=1, F=1): expect two_line_mode=1, font_5x10=0. */
    send_byte(0x2C, 0);
    ASSERT_EQ_FMT(1, (int)ls.two_line_mode, "%d");
    ASSERT_EQ_FMT(0, (int)ls.font_5x10, "%d");

    /* Back to 1-line, 5x8 ($20 | N=0, F=0). */
    send_byte(0x20, 0);
    ASSERT_EQ_FMT(0, (int)ls.two_line_mode, "%d");
    ASSERT_EQ_FMT(0, (int)ls.font_5x10, "%d");

    PASS();
}

TEST cgram_5x10_slot_holds_10_byte_glyph(void) {
    /* In 5x10 mode the HD44780 stores 4 character patterns of 10 dot
     * rows each. The controller still exposes CGRAM as a flat 64-byte
     * memory accessed via Set-CGRAM-Address + write-data; the bytes for
     * slot 0 occupy addresses $00..$0A (10 rows + 1 cursor row, the
     * cursor row is ignored by the renderer). This test confirms that
     * writes through the 4-bit interface land in CGRAM unchanged. */
    setup();
    send_cmd_8bit(0x2);                     /* enter 4-bit */
    send_byte(0x24, 0);                     /* 4-bit, 1-line, 5x10 */
    send_byte(0x40, 0);                     /* Set CGRAM addr = $00 */

    static const uint8_t glyph[10] = {
        0x1F, 0x11, 0x11, 0x11, 0x11,
        0x11, 0x11, 0x11, 0x11, 0x1F,
    };
    for (int i = 0; i < 10; i++) send_byte(glyph[i], 1);

    for (int i = 0; i < 10; i++) {
        ASSERT_EQ_FMT(glyph[i], ls.cgram[i], "%u");
    }
    PASS();
}

TEST blink_underline_cursor_state_tracks_display_ctl(void) {
    setup();
    send_cmd_8bit(0x2);
    send_byte(0x24, 0);                     /* 1-line, 5x10 */
    /* Display ON + cursor ON + blink ON -> $0F. */
    send_byte(0x0F, 0);
    ASSERT_EQ_FMT(1, (int)ls.display_on, "%d");
    ASSERT_EQ_FMT(1, (int)ls.cursor_on,  "%d");
    ASSERT_EQ_FMT(1, (int)ls.blink_on,   "%d");

    /* Display ON + cursor ON + blink OFF -> $0E. */
    send_byte(0x0E, 0);
    ASSERT_EQ_FMT(1, (int)ls.cursor_on, "%d");
    ASSERT_EQ_FMT(0, (int)ls.blink_on,  "%d");

    /* Display ON, all cursor visuals off -> $0C. */
    send_byte(0x0C, 0);
    ASSERT_EQ_FMT(0, (int)ls.cursor_on, "%d");
    ASSERT_EQ_FMT(0, (int)ls.blink_on,  "%d");
    PASS();
}

TEST cursor_position_5x10_tracks_dd_address(void) {
    /* 5x10 mode is 1-line only, so all writes stay on row 0 and the
     * cursor row in the snapshot should always be 0. The column is
     * just AC. */
    setup();
    send_cmd_8bit(0x2);
    send_byte(0x24, 0);                     /* 1-line, 5x10 */
    send_byte(0x06, 0);                     /* entry: increment */
    send_byte(0x80, 0);                     /* DDRAM addr = 0 */
    send_byte('H', 1);
    send_byte('I', 1);
    /* AC has advanced past 'I' to position 2. */
    ASSERT_EQ_FMT(2, (int)(ls.ac & 0x7F), "%d");
    ASSERT_EQ_FMT(0, (int)ls.cgram_mode,  "%d");
    /* Now move cursor: shift-right cursor: $14 (cursor shift, S/C=0, R/L=1). */
    /* But we don't implement cursor shift; instead use Set DDRAM. */
    send_byte(0x80 | 0x10, 0);              /* AC = $10 (col 16) */
    ASSERT_EQ_FMT(0x10, (int)(ls.ac & 0x7F), "%d");
    PASS();
}

/* ---- Michael wiring: 8-bit data on PORTB, E/RW/RS on PA7/PA6/PA5 ---- */

#define M_E  0x80
#define M_RW 0x40
#define M_RS 0x20

static void setup_michael(void) {
    setup();
    lcd_hd44780_set_wiring(&ls, &LCD_WIRING_MICHAEL);
    bus_write(&bus_, 0xF003, M_E | M_RW | M_RS);  /* DDRA */
    bus_write(&bus_, 0xF002, 0xFF);               /* DDRB */
}

/* Strobe E with the given PORTA control bits (RS/RW). */
static void michael_strobe(uint8_t control) {
    bus_write(&bus_, 0xF001, control | M_E);
    bus_step(&bus_);
    bus_write(&bus_, 0xF001, control);
    bus_step(&bus_);
}

static void michael_write(uint8_t byte, uint8_t rs) {
    bus_write(&bus_, 0xF000, byte);
    michael_strobe(rs ? M_RS : 0);
}

static uint8_t lcd_portb(void *ctx) {
    uint8_t value = 0;
    lcd_hd44780_output((const struct lcd_hd44780_state *)ctx, &value);
    return value;
}

TEST michael_8bit_writes(void) {
    setup_michael();
    michael_write(0x38, 0);   /* 8-bit, 2 lines */
    michael_write(0x0C, 0);
    michael_write(0x01, 0);
    michael_write('H', 1);
    michael_write('i', 1);

    char buf[40];
    lcd_hd44780_render(&ls, buf);
    ASSERT_EQ_FMT((char)'H', buf[0], "%c");
    ASSERT_EQ_FMT((char)'i', buf[1], "%c");
    ASSERT_EQ_FMT(0u, (unsigned)ls.undriven_strobes, "%u");
    PASS();
}

/* With E high and RW high the LCD drives D7..D0: the busy flag (never
 * busy) and the address counter, or the data at the address counter. */
TEST michael_read_drives_busy_flag_and_address_then_data(void) {
    setup_michael();
    via_6522_set_portb_input(&vs, lcd_portb, &ls);
    michael_write(0x38, 0);
    michael_write(0x80 | 0x14, 0);  /* DDRAM $14 (row 3) */
    michael_write('Q', 1);          /* AC -> $15 */
    michael_write(0x80 | 0x14, 0);

    bus_write(&bus_, 0xF002, 0x00);                 /* DDRB input */
    bus_write(&bus_, 0xF001, M_RW | M_E);
    bus_step(&bus_);
    uint8_t v = 0;
    bus_read(&bus_, 0xF000, &v);
    ASSERT_EQ_FMT(0x14, v, "%02x");                 /* not busy, AC=$14 */
    bus_write(&bus_, 0xF001, M_RW);
    bus_step(&bus_);

    bus_write(&bus_, 0xF001, M_RS | M_RW | M_E);    /* data read */
    bus_step(&bus_);
    bus_read(&bus_, 0xF000, &v);
    ASSERT_EQ_FMT('Q', v, "%02x");
    bus_write(&bus_, 0xF001, M_RS | M_RW);
    bus_step(&bus_);
    ASSERT_EQ_FMT(0x15, ls.ac, "%02x");              /* a data read advances AC */

    bus_read(&bus_, 0xF000, &v);                    /* E low: LCD lets go */
    ASSERT_EQ_FMT(0x00, v, "%02x");
    ASSERT_EQ_FMT(0u, (unsigned)ls.contention, "%u");
    PASS();
}

/* A write strobed while the data pins are VIA inputs latches whatever
 * the bus floats to: counted as an undriven strobe. */
TEST michael_write_with_data_pins_as_inputs_is_undriven(void) {
    setup_michael();
    bus_write(&bus_, 0xF002, 0x00);
    michael_write('X', 1);
    ASSERT_EQ_FMT(1u, (unsigned)ls.undriven_strobes, "%u");
    PASS();
}

TEST michael_strobe_with_rs_as_input_is_undriven(void) {
    setup_michael();
    bus_write(&bus_, 0xF003, M_E | M_RW);           /* RS not driven */
    michael_write('X', 1);
    ASSERT_EQ_FMT(1u, (unsigned)ls.undriven_strobes, "%u");
    PASS();
}

/* A read while the VIA drives the data pins: both sides drive the bus. */
TEST michael_read_against_driven_data_pins_is_contention(void) {
    setup_michael();
    michael_strobe(M_RW);
    ASSERT_EQ_FMT(1u, (unsigned)ls.contention, "%u");
    PASS();
}

SUITE(lcd_hd44780_suite) {
    RUN_TEST(init_4bit_then_write_hello);
    RUN_TEST(cgram_slot_6_renders_as_tilde);
    RUN_TEST(visible_bytes_are_raw_ddram_in_row_order);
    RUN_TEST(line2_address_starts_at_40);
    RUN_TEST(function_set_5x10_mode);
    RUN_TEST(cgram_5x10_slot_holds_10_byte_glyph);
    RUN_TEST(blink_underline_cursor_state_tracks_display_ctl);
    RUN_TEST(cursor_position_5x10_tracks_dd_address);
    RUN_TEST(michael_8bit_writes);
    RUN_TEST(michael_read_drives_busy_flag_and_address_then_data);
    RUN_TEST(michael_write_with_data_pins_as_inputs_is_undriven);
    RUN_TEST(michael_strobe_with_rs_as_input_is_undriven);
    RUN_TEST(michael_read_against_driven_data_pins_is_contention);
}

GREATEST_MAIN_DEFS();
int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(lcd_hd44780_suite);
    GREATEST_MAIN_END();
}
