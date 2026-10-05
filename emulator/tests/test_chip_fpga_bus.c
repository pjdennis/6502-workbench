/* fpga_bus chip tests: the Michael FPGA bus as the emulator sees it (docs/michael-fpga-bus-plan.md). Each
 * rising edge of E (PA0) is a transfer, chosen by RS (PA5) and RW (PA6); writes carry port B. With a log,
 * each transfer is a line: "C hh" (command), "D hh" (data), "R" (reply read) or "S" (status read). */

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "greatest.h"
#include "../bus.h"
#include "../chips/via_6522.h"
#include "../chips/fpga_bus.h"

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
    bus_write(&bus_, 0xF001, porta | 0x01);
    bus_step(&bus_); bus_step(&bus_); bus_step(&bus_);
    bus_write(&bus_, 0xF001, porta);
    bus_step(&bus_); bus_step(&bus_);
}

TEST writes_and_reads(void) {
    setup();
    bus_write(&bus_, 0xF003, 0x61);   /* DDRA: E, RS, RW outputs */
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
    bus_write(&bus_, 0xF003, 0x61);
    bus_write(&bus_, 0xF001, 0x21);
    for (int i = 0; i < 20; i++) bus_step(&bus_);
    ASSERT_STR_EQ("D 00\n", logged());
    teardown();
    PASS();
}

TEST e_as_an_input_is_held_low(void) {
    /* After a reset PA0 is an input; the board's pull-down keeps E low */
    setup();
    bus_write(&bus_, 0xF003, 0x60);
    bus_write(&bus_, 0xF001, 0x01);
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
    bus_write(&bus_, 0xF003, 0x71);   /* DDRA: E, SOEB, RS, RW outputs */
}

#define SOEB 0x10                     /* high: the keyboard board off */

static void write_byte(int rs, uint8_t b) {
    bus_write(&bus_, 0xF002, 0xFF);
    bus_write(&bus_, 0xF000, b);
    strobe(SOEB | (rs ? 0x20 : 0x00));
}

static void command(uint8_t c) { write_byte(0, c); }
static void data(uint8_t d) { write_byte(1, d); }

/* A read as fpga_bus.inc makes it: port B an input, RW 1 (RS 1 the reply queue, 0 the status), E up; the byte
 * on port B while E is high */
static uint8_t read_byte(int rs) {
    uint8_t porta = SOEB | 0x40 | (rs ? 0x20 : 0x00);
    bus_write(&bus_, 0xF002, 0x00);
    bus_write(&bus_, 0xF001, porta);
    bus_step(&bus_); bus_step(&bus_);
    bus_write(&bus_, 0xF001, porta | 0x01);
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
    ASSERT_EQ_FMT(1, read_byte(1), "%02x");
    ASSERT_EQ_FMT(0x03, read_byte(1), "%02x");   /* raw display and text mode */
    command(0x30);
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
    bus_write(&bus_, 0xF001, 0x61);
    bus_step(&bus_); bus_step(&bus_);
    uint8_t v;
    ASSERT_FALSE(fpga_bus_output(&fs, &v));
    bus_write(&bus_, 0xF001, 0x60 | SOEB | 0x01);
    bus_step(&bus_);
    ASSERT(fpga_bus_output(&fs, &v));
    ASSERT_EQ_FMT(0x5A, v, "%02x");
    teardown();
    PASS();
}

static void put(const char *text) {
    command(0x23);
    while (*text) data((uint8_t)*text++);
}

TEST text_mode_changes_the_grid(void) {
    model_setup();
    command(0x20);                               /* TEXT_ON */
    put("Hi");
    command(0x22); data(2); data(3);             /* GOTO 2, 3 */
    command(0x2F); data(1);                      /* VIDEO reverse */
    put("x");
    command(0x2E); data(1);                      /* CURSOR on */
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

TEST text_mode_refuses_raw_display_commands(void) {
    model_setup();
    command(0x20);
    command(0x11); data(0x2A);                   /* DISP_COMMAND: refused */
    ASSERT_EQ_FMT(0x02, read_byte(0), "%02x");   /* UNKNOWN */
    ASSERT(fs.panel.command != 0x2A);
    command(0x13); data(0x80);                   /* BACKLIGHT: still fine */
    ASSERT_EQ(0x80, fs.panel.backlight);
    command(0x21);                               /* TEXT_OFF */
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

TEST an_absent_fpga_never_answers(void) {
    /* Unconfigured, the FPGA keeps the data buffer off: port B floats (reads 0 here) and nothing changes */
    model_setup();
    fs.absent = 1;
    command(0x01);
    ASSERT_EQ_FMT(0x00, read_byte(1), "%02x");
    command(0x20);
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
    RUN_TEST(text_mode_refuses_raw_display_commands);
    RUN_TEST(raw_display_commands_drive_the_panel);
    RUN_TEST(an_absent_fpga_never_answers);
}

GREATEST_MAIN_DEFS();

int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(fpga_bus_suite);
    GREATEST_MAIN_END();
}
