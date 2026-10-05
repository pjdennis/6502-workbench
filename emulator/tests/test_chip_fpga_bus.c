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

TEST text_mode_refuses_raw_display_commands(void) {
    model_setup();
    text(0x00);
    command(0x11); data(0x2A);                   /* DISP_COMMAND: refused */
    ASSERT_EQ_FMT(0x02, read_byte(0), "%02x");   /* UNKNOWN */
    command(0x13); data(0x80);                   /* BACKLIGHT: still fine */
    text(0x01);                                  /* TEXT_OFF */
    command(0x11); data(0x2A);
    ASSERT_EQ_FMT(0x00, read_byte(0), "%02x");
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
    RUN_TEST(text_mode_refuses_raw_display_commands);
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
