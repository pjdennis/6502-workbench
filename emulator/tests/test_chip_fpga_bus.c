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

SUITE(fpga_bus_suite) {
    RUN_TEST(writes_and_reads);
    RUN_TEST(e_held_high_is_one_transfer);
    RUN_TEST(e_as_an_input_is_held_low);
}

GREATEST_MAIN_DEFS();

int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(fpga_bus_suite);
    GREATEST_MAIN_END();
}
