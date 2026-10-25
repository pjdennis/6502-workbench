/* w5500 chip tests: the WIZnet W5500 as an SPI device (chips/w5500.h), its chip select on Michael's PA0. A
 * frame is two address bytes, a control byte (the block, read or write, and the mode) and data; in variable
 * length mode it lasts until the chip select rises. */

#include <stdint.h>
#include "greatest.h"
#include "../bus.h"
#include "../chips/via_6522.h"
#include "../chips/w5500.h"

#define CS 0x01                        /* PA0 */
#define COMMON 0x00                    /* the control byte's block select: the common registers */
#define WRITE 0x04
#define VERSIONR 0x0039
#define GAR 0x0001                     /* the gateway address, 4 bytes */

static struct via_6522_state vs;
static struct w5500_state ws;
static struct chip vch, wch;
static struct bus bus_;

static void setup(void) {
    via_6522_init(&vch, &vs);
    w5500_init(&wch, &ws, &vs, CS);
    bus_init(&bus_);
    bus_add_chip(&bus_, &vch);
    bus_add_chip(&bus_, &wch);
    bus_.viacs = 1;
    bus_write(&bus_, 0xF001, CS);      /* deselected */
    bus_write(&bus_, 0xF003, CS);      /* PA0 an output */
    bus_step(&bus_);
}

static void select_(int on) {
    bus_write(&bus_, 0xF001, on ? 0 : CS);
    bus_step(&bus_);
}

/* A byte each way, MSB first */
static uint8_t byte(uint8_t out) {
    uint8_t in = 0;
    for (int i = 7; i >= 0; i--) in = (uint8_t)(in << 1 | w5500_pulse(&ws, (out >> i) & 1));
    return in;
}

static uint8_t read_common(uint16_t addr) {
    select_(1);
    byte(addr >> 8);
    byte(addr & 0xFF);
    byte(COMMON);
    uint8_t v = byte(0x00);
    select_(0);
    return v;
}

static void write_common(uint16_t addr, const uint8_t *data, int n) {
    select_(1);
    byte(addr >> 8);
    byte(addr & 0xFF);
    byte(COMMON | WRITE);
    for (int i = 0; i < n; i++) byte(data[i]);
    select_(0);
}

TEST versionr_reads_4(void) {
    setup();
    ASSERT_EQ_FMT(0x04, read_common(VERSIONR), "%02X");
    PASS();
}

TEST versionr_is_read_only(void) {
    setup();
    const uint8_t v = 0x55;
    write_common(VERSIONR, &v, 1);
    ASSERT_EQ_FMT(0x04, read_common(VERSIONR), "%02X");
    PASS();
}

TEST registers_written_read_back_in_one_frame(void) {
    setup();
    const uint8_t gar[4] = { 192, 168, 1, 1 };
    write_common(GAR, gar, 4);
    select_(1);
    byte(GAR >> 8);
    byte(GAR & 0xFF);
    byte(COMMON);
    for (int i = 0; i < 4; i++) ASSERT_EQ_FMT(gar[i], byte(0x00), "%u");
    select_(0);
    PASS();
}

TEST deselected_it_ignores_the_bus(void) {
    setup();
    ASSERT_EQ_FMT(0xFF, byte(0x00), "%02X");   /* MISO undriven */
    ASSERT_EQ_FMT(0xFF, byte(0x39), "%02X");
    ASSERT_EQ_FMT(0x04, read_common(VERSIONR), "%02X");   /* and no frame was started */
    PASS();
}

TEST the_chip_select_rising_ends_a_frame(void) {
    setup();
    select_(1);
    byte(0x00);                        /* half an address */
    select_(0);
    ASSERT_EQ_FMT(0x04, read_common(VERSIONR), "%02X");
    PASS();
}

TEST fixed_length_mode_frames_without_the_chip_select(void) {
    setup();
    select_(1);
    byte(VERSIONR >> 8);
    byte(VERSIONR & 0xFF);
    byte(COMMON | 0x01);               /* OM 01: one data byte */
    ASSERT_EQ_FMT(0x04, byte(0x00), "%02X");
    byte(VERSIONR >> 8);               /* the next frame, with the chip select still low */
    byte(VERSIONR & 0xFF);
    byte(COMMON | 0x01);
    ASSERT_EQ_FMT(0x04, byte(0x00), "%02X");
    select_(0);
    PASS();
}

/* While the address and control bytes go in, MISO counts them: $01, $02, $03 (seen on the board) */
TEST the_header_bytes_answer_01_02_03(void) {
    setup();
    select_(1);
    ASSERT_EQ_FMT(0x01, byte(VERSIONR >> 8), "%02X");
    ASSERT_EQ_FMT(0x02, byte(VERSIONR & 0xFF), "%02X");
    ASSERT_EQ_FMT(0x03, byte(COMMON | 0x01), "%02X");   /* fixed length, one byte */
    ASSERT_EQ_FMT(0x04, byte(0x00), "%02X");
    ASSERT_EQ_FMT(0x01, byte(VERSIONR >> 8), "%02X");   /* the next frame, with the chip select still low */
    select_(0);
    select_(1);
    ASSERT_EQ_FMT(0x01, byte(0x00), "%02X");            /* and after the chip select rises */
    select_(0);
    PASS();
}

/* MR's RST bit (7) resets every register; MR reads 0 again once it's done */
TEST mr_rst_resets_the_registers(void) {
    setup();
    const uint8_t gar[4] = { 10, 0, 0, 1 }, rst = 0x80;
    write_common(GAR, gar, 4);
    write_common(0x0000, &rst, 1);
    ASSERT_EQ_FMT(0x00, read_common(0x0000), "%02X");
    ASSERT_EQ_FMT(0x00, read_common(GAR), "%02X");
    ASSERT_EQ_FMT(0x08, read_common(0x001B), "%02X");   /* RCR back to its reset value */
    PASS();
}

/* The emulated cable is plugged into a 100 Mbps full duplex port: PHYCFGR's LNK, SPD and DPX bits are set */
TEST phycfgr_reads_link_up(void) {
    setup();
    ASSERT_EQ_FMT(0xBF, read_common(0x002E), "%02X");
    PASS();
}

TEST reset_values(void) {
    setup();
    ASSERT_EQ_FMT(0x07, read_common(0x0019), "%02X");   /* RTR, $07D0 */
    ASSERT_EQ_FMT(0xD0, read_common(0x001A), "%02X");
    ASSERT_EQ_FMT(0x08, read_common(0x001B), "%02X");   /* RCR */
    PASS();
}

TEST reset_clears_what_was_written(void) {
    setup();
    const uint8_t gar[4] = { 10, 0, 0, 1 };
    write_common(GAR, gar, 4);
    wch.ops->reset(&wch);
    ASSERT_EQ_FMT(0x00, read_common(GAR), "%02X");
    PASS();
}

SUITE(w5500) {
    RUN_TEST(versionr_reads_4);
    RUN_TEST(versionr_is_read_only);
    RUN_TEST(registers_written_read_back_in_one_frame);
    RUN_TEST(deselected_it_ignores_the_bus);
    RUN_TEST(the_chip_select_rising_ends_a_frame);
    RUN_TEST(fixed_length_mode_frames_without_the_chip_select);
    RUN_TEST(the_header_bytes_answer_01_02_03);
    RUN_TEST(mr_rst_resets_the_registers);
    RUN_TEST(phycfgr_reads_link_up);
    RUN_TEST(reset_values);
    RUN_TEST(reset_clears_what_was_written);
}

GREATEST_MAIN_DEFS();
int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(w5500);
    GREATEST_MAIN_END();
}
