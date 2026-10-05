/* fpga_bus chip tests: the Michael FPGA bus as the emulator sees it (docs/michael-fpga-bus-plan.md). Each
 * rising edge of E (PA2) is a transfer, chosen by RS (PA5) and RW (PA6); writes carry port B. With a log,
 * each transfer is a line: "C hh" (command), "D hh" (data), "R" (reply read) or "S" (status read). */

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "greatest.h"
#include "../bus.h"
#include "../chips/via_6522.h"
#include "../chips/fpga_bus.h"
#include "../chips/font_12x16.h"

#define E 0x04                        /* PA2, the bus's E */

static struct via_6522_state vs;
static struct fpga_bus_state fs;
static struct chip vch, fch;
static struct bus bus_;
static char *log_text;
static size_t log_size;
static FILE *log_file;

static void setup(void) {
    log_file = open_memstream(&log_text, &log_size);
    via_6522_init(&vch, &vs);
    fpga_bus_init(&fch, &fs, &vs, log_file);
    bus_init(&bus_);
    bus_add_chip(&bus_, &vch);
    bus_add_chip(&bus_, &fch);
    bus_.viacs = 1;
}

static const char *logged(void) {
    fflush(log_file);
    return log_text;
}

static void teardown(void) {
    fclose(log_file);
    free(log_text);
}

/* Port A as Michael's driver leaves it, then E up and down, a few cycles each */
static void strobe(uint8_t porta) {
    bus_write(&bus_, 0xF001, porta);
    bus_step(&bus_); bus_step(&bus_);
    bus_write(&bus_, 0xF001, porta | E);
    bus_step(&bus_); bus_step(&bus_); bus_step(&bus_);
    bus_write(&bus_, 0xF001, porta);
    bus_step(&bus_); bus_step(&bus_);
}

TEST writes_and_reads(void) {
    setup();
    bus_write(&bus_, 0xF003, 0x60 | E);   /* DDRA: E, RS, RW outputs */
    bus_write(&bus_, 0xF002, 0xFF);   /* DDRB: port B an output */
    bus_write(&bus_, 0xF000, 0x2A);
    strobe(0x00);                     /* RS 0, RW 0: a command */
    bus_write(&bus_, 0xF000, 0x55);
    strobe(0x20);                     /* RS 1, RW 0: data */
    strobe(0x60);                     /* RS 1, RW 1: a reply read */
    strobe(0x40);                     /* RS 0, RW 1: a status read */
    ASSERT_STR_EQ("C 2A\nD 55\nR\nS\n", logged());
    ASSERT_EQ_FMT(4u, fs.transfers, "%u");
    teardown();
    PASS();
}

TEST e_held_high_is_one_transfer(void) {
    setup();
    bus_write(&bus_, 0xF003, 0x60 | E);
    bus_write(&bus_, 0xF001, 0x20 | E);
    for (int i = 0; i < 20; i++) bus_step(&bus_);
    ASSERT_STR_EQ("D 00\n", logged());
    teardown();
    PASS();
}

TEST e_as_an_input_is_held_low(void) {
    /* After a reset PA2 is an input; the board's pull-down keeps E low */
    setup();
    bus_write(&bus_, 0xF003, 0x60);
    bus_write(&bus_, 0xF001, E);
    for (int i = 0; i < 10; i++) bus_step(&bus_);
    ASSERT_STR_EQ("", logged() ? logged() : "");
    ASSERT_EQ_FMT(0u, fs.transfers, "%u");
    teardown();
    PASS();
}

/* The FPGA's side of the model: its commands, the reply queue and the status, and text mode */

static uint8_t driven(void *ctx) {
    uint8_t v = 0;
    return fpga_bus_output(ctx, &v) ? v : 0x00;
}

static void model_setup(void) {
    setup();
    via_6522_set_portb_input(&vs, driven, &fs);
    bus_write(&bus_, 0xF003, 0x70 | E);   /* DDRA: E, SOEB, RS, RW outputs */
}

#define SOEB 0x10                     /* high: the keyboard board off */

static void write_byte(int rs, uint8_t b) {
    bus_write(&bus_, 0xF002, 0xFF);
    bus_write(&bus_, 0xF000, b);
    strobe(SOEB | (rs ? 0x20 : 0x00));
}

static void command(uint8_t c) { write_byte(0, c); }
static void data(uint8_t d) { write_byte(1, d); }
static void text(uint8_t op) { command(0x80); data(op); }   /* a text mode operation: the long form */

/* A read as fpga_bus.inc makes it: port B an input, RW 1 (RS 1 the reply queue, 0 the status), E up; the byte
 * on port B while E is high */
static uint8_t read_byte(int rs) {
    uint8_t porta = SOEB | 0x40 | (rs ? 0x20 : 0x00);
    bus_write(&bus_, 0xF002, 0x00);
    bus_write(&bus_, 0xF001, porta);
    bus_step(&bus_); bus_step(&bus_);
    bus_write(&bus_, 0xF001, porta | E);
    bus_step(&bus_); bus_step(&bus_);
    uint8_t b = via_6522_portb_pins(&vs);
    bus_write(&bus_, 0xF001, porta);
    bus_step(&bus_); bus_step(&bus_);
    return b;
}

TEST id_and_geometry_reply(void) {
    model_setup();
    command(0x01);
    ASSERT_EQ_FMT('M', read_byte(1), "%02x");
    ASSERT_EQ_FMT('B', read_byte(1), "%02x");
    ASSERT_EQ_FMT(2, read_byte(1), "%02x");      /* the protocol's version */
    ASSERT_EQ_FMT(0x03, read_byte(1), "%02x");   /* raw display and text mode */
    text(0x10);                                  /* GEOMETRY */
    ASSERT_EQ_FMT(20, read_byte(1), "%02x");
    ASSERT_EQ_FMT(20, read_byte(1), "%02x");
    ASSERT_EQ_FMT(0x00, read_byte(0), "%02x");   /* a clean status */
    teardown();
    PASS();
}

TEST an_empty_reply_queue_underflows(void) {
    model_setup();
    ASSERT_EQ_FMT(0x00, read_byte(1), "%02x");
    ASSERT_EQ_FMT(0x08, read_byte(0), "%02x");   /* UNDERFLOW, which the read clears */
    ASSERT_EQ_FMT(0x00, read_byte(0), "%02x");
    teardown();
    PASS();
}

TEST echo_and_the_soeb_interlock(void) {
    model_setup();
    command(0x04); data(0x5A);
    /* SOEB low (the keyboard board on) stops the FPGA driving port B */
    bus_write(&bus_, 0xF002, 0x00);
    bus_write(&bus_, 0xF001, 0x60);
    bus_write(&bus_, 0xF001, 0x60 | E);
    bus_step(&bus_); bus_step(&bus_);
    uint8_t v;
    ASSERT_FALSE(fpga_bus_output(&fs, &v));
    bus_write(&bus_, 0xF001, 0x60 | SOEB | E);
    bus_step(&bus_);
    ASSERT(fpga_bus_output(&fs, &v));
    ASSERT_EQ_FMT(0x5A, v, "%02x");
    teardown();
    PASS();
}

static void put(const char *chars) {
    text(0x03);
    while (*chars) data((uint8_t)*chars++);
}

TEST text_mode_changes_the_grid(void) {
    model_setup();
    text(0x00);                                  /* TEXT_ON */
    put("Hi");
    text(0x02); data(2); data(3);                /* GOTO 2, 3 */
    text(0x0F); data(1);                         /* VIDEO reverse */
    put("x");
    text(0x0E); data(1);                         /* CURSOR on */
    char row[FPGA_TEXT_COLS + 1];
    fpga_text_row(&fs.text, 0, row);
    ASSERT_STR_EQ("Hi                  ", row);
    fpga_text_row(&fs.text, 2, row);
    ASSERT_STR_EQ("   x                ", row);
    ASSERT(fs.text.reverse_cells[2][3]);
    ASSERT_FALSE(fs.text.reverse_cells[0][0]);
    ASSERT_EQ(2, fs.text.row);
    ASSERT_EQ(4, fs.text.col);
    ASSERT(fs.text.cursor);
    teardown();
    PASS();
}

TEST whole_region_scrolls_move_the_offset(void) {
    /* As text_grid.v's HW_SCROLL: scrolling the whole region by fewer rows than it has moves its picture by
     * the display's hardware scroll, offset rows; a new region starts again at 0 */
    model_setup();
    text(0x00);
    text(0x08); data(1); data(19);               /* REGION 1-19: 19 rows */
    text(0x0A); data(1);                         /* SCROLL_UP 1 */
    ASSERT_EQ(18, fs.text.offset);
    text(0x0A); data(2);
    ASSERT_EQ(16, fs.text.offset);
    text(0x0B); data(3);                         /* SCROLL_DOWN 3 */
    ASSERT_EQ(0, fs.text.offset);
    text(0x0A); data(19);                        /* the whole region: cleared, not scrolled */
    ASSERT_EQ(0, fs.text.offset);
    text(0x02); data(1); data(4);                /* GOTO the region's top row */
    text(0x0C); data(2);                         /* INSERT_LINES 2: down */
    ASSERT_EQ(2, fs.text.offset);
    text(0x02); data(5); data(0);
    text(0x0D); data(1);                         /* DELETE_LINES below the top: moved, not scrolled */
    ASSERT_EQ(2, fs.text.offset);
    text(0x08); data(1); data(19);               /* the same region: kept */
    ASSERT_EQ(2, fs.text.offset);
    text(0x08); data(2); data(19);               /* another: back to 0 */
    ASSERT_EQ(0, fs.text.offset);
    text(0x0B); data(1);
    text(0x00);                                  /* TEXT_ON: 0 */
    ASSERT_EQ(0, fs.text.offset);
    teardown();
    PASS();
}

TEST text_mode_refuses_raw_display_commands(void) {
    model_setup();
    text(0x00);
    command(0x11); data(0x2A);                   /* DISP_COMMAND: refused */
    ASSERT_EQ_FMT(0x02, read_byte(0), "%02x");   /* UNKNOWN */
    ASSERT(fs.panel.command != 0x2A);
    command(0x13); data(0x80);                   /* BACKLIGHT: still fine */
    ASSERT_EQ(0x80, fs.panel.backlight);
    text(0x01);                                  /* TEXT_OFF */
    command(0x11); data(0x2A);
    ASSERT_EQ_FMT(0x00, read_byte(0), "%02x");
    ASSERT_EQ(0x2A, fs.panel.command);
    teardown();
    PASS();
}

/* An ILI9341 command and its parameters, through DISP_COMMAND */
static void display(uint8_t c, int n, const uint8_t *params) {
    command(0x11); data(c);
    for (int i = 0; i < n; i++) data(params[i]);
}

TEST raw_display_commands_drive_the_panel(void) {
    model_setup();
    command(0x10); data(0);                      /* DISP_RESET: held */
    ASSERT(fs.panel.in_reset);
    command(0x10); data(1);
    ASSERT_FALSE(fs.panel.in_reset);
    display(0x11, 0, NULL);                      /* SLPOUT */
    display(0x29, 0, NULL);                      /* DISPON */
    display(0x36, 1, (const uint8_t[]){ 0xA8 });                 /* MADCTL */
    display(0x2A, 4, (const uint8_t[]){ 0, 5, 0, 5 });           /* CASET 5-5 */
    display(0x2B, 4, (const uint8_t[]){ 0, 7, 0, 8 });           /* PASET 7-8 */
    display(0x2C, 2, (const uint8_t[]){ 0xF8, 0x00 });           /* RAMWR, a pixel */
    command(0x12); data(0x07); data(0xE0);       /* DISP_DATA: the next */
    ASSERT(ili9341_showing(&fs.panel));
    ASSERT_EQ_FMT(0xF800, fs.panel.memory[ILI9341_LINES - 1 - 5][7], "%04X");
    ASSERT_EQ_FMT(0x07E0, fs.panel.memory[ILI9341_LINES - 1 - 5][8], "%04X");
    command(0x13); data(0x40);                   /* BACKLIGHT */
    ASSERT_EQ(0x40, fs.panel.backlight);
    ASSERT_EQ_FMT(0x00, read_byte(0), "%02x");
    teardown();
    PASS();
}

/* Text mode on the display: drawn as text_render.v draws it */

/* The display as Michael's driver initialises it (gd_prepare_vertical) before TEXT_ON: out of reset, sleep
 * and off, with the panel's scans reversed (GD_PANEL_SCAN) */
static void display_setup(void) {
    model_setup();
    command(0x10); data(1);
    display(0x11, 0, NULL);
    display(0x29, 0, NULL);
    display(0xB6, 3, (const uint8_t[]){ 0x08, 0xE2, 0x27 });
}

/* Whether the glass shows the cell (row, col) as the character code, with reverse video and the cursor */
static int glass_shows(int row, int col, uint8_t code, int reverse, int cursor) {
    for (int x = 0; x < 12; x++) {
        uint16_t want = font_12x16[code][x] ^ (reverse ? 0xFFFF : 0) ^ (cursor ? 0xC000 : 0);
        for (int y = 0; y < 16; y++) {
            uint16_t lit = (want >> y) & 1 ? 0xFFFF : 0x0000;
            if (ili9341_glass_pixel(&fs.panel, col * 12 + x, row * 16 + y) != lit) return 0;
        }
    }
    return 1;
}

TEST text_mode_draws_the_grid(void) {
    display_setup();
    text(0x00);
    put("Hi");
    text(0x02); data(2); data(3);
    text(0x0F); data(1);
    put("x");
    fpga_bus_render(&fs, 0);
    ASSERT_EQ_FMT(0xA8, fs.panel.madctl, "%02X");   /* Michael's orientation */
    ASSERT(glass_shows(0, 0, 'H', 0, 0));
    ASSERT(glass_shows(0, 1, 'i', 0, 0));
    ASSERT(glass_shows(2, 3, 'x', 1, 0));
    ASSERT(glass_shows(19, 19, ' ', 0, 0));
    teardown();
    PASS();
}

TEST codes_from_del_up_show_their_glyphs(void) {
    /* Code page 437's: DEL's house, then accented, shaded and line-drawing characters */
    static const uint8_t codes[] = { 0x7F, 0x80, 0xB1, 0xC1 };
    display_setup();
    text(0x00);
    text(0x03);
    for (int c = 0; c < 4; c++) data(codes[c]);
    fpga_bus_render(&fs, 0);
    for (int c = 0; c < 4; c++) ASSERT(glass_shows(0, c, codes[c], 0, 0));
    ASSERT_FALSE(glass_shows(0, 1, 0x7F, 0, 0));   /* distinct glyphs */
    teardown();
    PASS();
}

TEST the_cursor_blinks_and_shows_at_once_when_it_moves(void) {
    display_setup();
    text(0x00);
    put("Hi");
    text(0x0E); data(1);
    fpga_bus_render(&fs, 1000);
    ASSERT(glass_shows(0, 2, ' ', 0, 1));       /* the bottom two rows inverted */
    fpga_bus_render(&fs, 1000 + 249999);
    ASSERT(glass_shows(0, 2, ' ', 0, 1));
    fpga_bus_render(&fs, 1000 + 250000);
    ASSERT(glass_shows(0, 2, ' ', 0, 0));
    fpga_bus_render(&fs, 1000 + 500000);
    ASSERT(glass_shows(0, 2, ' ', 0, 1));
    fpga_bus_render(&fs, 1000 + 750000);
    ASSERT(glass_shows(0, 2, ' ', 0, 0));
    put("A");
    fpga_bus_render(&fs, 1000 + 760000);
    ASSERT(glass_shows(0, 2, 'A', 0, 0));
    ASSERT(glass_shows(0, 3, ' ', 0, 1));
    text(0x02); data(0); data(20);               /* past the last column: not shown */
    fpga_bus_render(&fs, 1000 + 770000);
    ASSERT(glass_shows(0, 3, ' ', 0, 0));
    teardown();
    PASS();
}

TEST a_region_scrolls_by_the_hardware_scroll(void) {
    /* Rows 1-19 up a row: the display's scroll registers move the picture, and only the row that comes in
     * blank is drawn. A mark in the memory of a row that only moves stays. */
    display_setup();
    text(0x00);
    for (int r = 0; r < 20; r++) {
        text(0x02); data((uint8_t)r); data(0);
        text(0x03); data((uint8_t)('A' + r));
    }
    text(0x08); data(1); data(19);
    fpga_bus_render(&fs, 0);
    uint16_t *mark = &fs.panel.memory[ILI9341_LINES - 1 - 5 * 16][5], was = *mark;   /* row 5's memory */
    *mark = 0x1234;
    text(0x0A); data(1);
    fpga_bus_render(&fs, 0);
    ASSERT_EQ(0, fs.panel.tfa);
    ASSERT_EQ(19 * 16, fs.panel.vsa);
    ASSERT_EQ(16, fs.panel.bfa);
    ASSERT_EQ(18 * 16, fs.panel.ssa);
    ASSERT_EQ_FMT(0x1234, *mark, "%04X");
    *mark = was;
    ASSERT(glass_shows(0, 0, 'A', 0, 0));
    for (int r = 1; r < 19; r++) ASSERT(glass_shows(r, 0, (uint8_t)('A' + r + 1), 0, 0));
    ASSERT(glass_shows(19, 0, ' ', 0, 0));
    teardown();
    PASS();
}

TEST text_off_leaves_the_picture_for_raw_mode(void) {
    display_setup();
    text(0x00);
    put("Z");
    text(0x01);                                  /* TEXT_OFF, before any render */
    ASSERT(glass_shows(0, 0, 'Z', 0, 0));
    display(0x2A, 4, (const uint8_t[]){ 0, 0, 0, 0 });
    display(0x2B, 4, (const uint8_t[]){ 0, 0, 0, 0 });
    display(0x2C, 2, (const uint8_t[]){ 0xF8, 0x00 });
    ASSERT_EQ_FMT(0xF800, ili9341_glass_pixel(&fs.panel, 0, 0), "%04X");
    text(0x00);                                  /* TEXT_ON again: everything redrawn */
    fpga_bus_render(&fs, 0);
    ASSERT(glass_shows(0, 0, ' ', 0, 0));
    teardown();
    PASS();
}

TEST random_operations_show_the_grid(void) {
    /* Text operations at random, rendered now and then: the glass must always show the grid, whatever the
     * hardware scroll has done to where its rows are in memory */
    static const uint8_t ops[] = { 0x22, 0x23, 0x23, 0x23, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x2B, 0x2C,
                                   0x2D, 0x2E, 0x2F };
    display_setup();
    text(0x00);
    srand(9341);
    for (int step = 0; step < 400; step++) {
        uint8_t op = ops[rand() % (int)sizeof ops];
        command(op);
        if (op == 0x23) for (int n = rand() % 6; n >= 0; n--) data((uint8_t)(rand() % 4 ? 0x20 + rand() % 95 : '\n'));
        else if (op == 0x22 || op == 0x28) { data((uint8_t)(rand() % 21)); data((uint8_t)(rand() % 21)); }
        else if (op != 0x25 && op != 0x29) data((uint8_t)(rand() % 4));
        if (rand() % 8) continue;
        fpga_bus_render(&fs, 0);
        const struct fpga_text *t = &fs.text;
        for (int r = 0; r < FPGA_TEXT_ROWS; r++)
            for (int c = 0; c < FPGA_TEXT_COLS; c++) {
                int cursor = t->cursor && r == t->row && c == t->col;
                if (!glass_shows(r, c, t->chars[r][c], t->reverse_cells[r][c], cursor)) {
                    fprintf(stderr, "step %d: cell %d, %d\n", step, r, c);
                    FAIL();
                }
            }
    }
    teardown();
    PASS();
}

TEST disp_reset_ends_text_mode(void) {
    /* A graphics program after a text one: its display reset is taken, and ends text mode */
    model_setup();
    text(0x00);
    command(0x10); data(0x00);                   /* DISP_RESET */
    ASSERT_FALSE(fs.text_mode);
    command(0x11); data(0x2A);                   /* DISP_COMMAND: taken */
    ASSERT_EQ_FMT(0x00, read_byte(0), "%02x");
    teardown();
    PASS();
}

TEST the_long_forms_errors(void) {
    model_setup();
    text(0x11); data(0x05);                      /* an unknown operation: UNKNOWN, its data ignored */
    ASSERT_EQ_FMT(0x02, read_byte(0), "%02x");
    command(0x80); command(0x00);                /* a command before the operation: ABANDONED */
    ASSERT_EQ_FMT(0x01, read_byte(0), "%02x");
    command(0x20);                               /* version 1's TEXT_ON: unknown */
    ASSERT_EQ_FMT(0x02, read_byte(0), "%02x");
    ASSERT_FALSE(fs.text_mode);
    teardown();
    PASS();
}

TEST an_absent_fpga_never_answers(void) {
    /* Unconfigured, the FPGA keeps the data buffer off: port B floats (reads 0 here) and nothing changes */
    model_setup();
    fs.absent = 1;
    command(0x01);
    ASSERT_EQ_FMT(0x00, read_byte(1), "%02x");
    text(0x00);
    ASSERT_FALSE(fs.text.used);
    teardown();
    PASS();
}

SUITE(fpga_bus_suite) {
    RUN_TEST(writes_and_reads);
    RUN_TEST(e_held_high_is_one_transfer);
    RUN_TEST(e_as_an_input_is_held_low);
    RUN_TEST(id_and_geometry_reply);
    RUN_TEST(an_empty_reply_queue_underflows);
    RUN_TEST(echo_and_the_soeb_interlock);
    RUN_TEST(text_mode_changes_the_grid);
    RUN_TEST(whole_region_scrolls_move_the_offset);
    RUN_TEST(text_mode_refuses_raw_display_commands);
    RUN_TEST(raw_display_commands_drive_the_panel);
    RUN_TEST(text_mode_draws_the_grid);
    RUN_TEST(codes_from_del_up_show_their_glyphs);
    RUN_TEST(the_cursor_blinks_and_shows_at_once_when_it_moves);
    RUN_TEST(a_region_scrolls_by_the_hardware_scroll);
    RUN_TEST(text_off_leaves_the_picture_for_raw_mode);
    RUN_TEST(random_operations_show_the_grid);
    RUN_TEST(disp_reset_ends_text_mode);
    RUN_TEST(the_long_forms_errors);
    RUN_TEST(an_absent_fpga_never_answers);
}

GREATEST_MAIN_DEFS();

int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(fpga_bus_suite);
    GREATEST_MAIN_END();
}
