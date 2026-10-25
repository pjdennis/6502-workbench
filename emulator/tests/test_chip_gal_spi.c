/* gal_spi chip tests: the GAL20RA10 SPI interface and its 74HC299 (chips/gal_spi.h,
 * hardware/michael/spi-interface/gal/spi-control.pld), a tick per Phi2 cycle. E (PA2) starts a burst of 8 SCLK
 * pulses that sends the byte the '299 loaded from port B; if E is still high at its end, the '299 drives the byte
 * it received onto port B until E falls. */

#include <stdint.h>
#include "greatest.h"
#include "../bus.h"
#include "../chips/via_6522.h"
#include "../chips/gal_spi.h"

#define E 0x04                        /* PA2 */

static struct via_6522_state vs;
static struct gal_spi_state gs;
static struct chip vch, gch;
static struct bus bus_;

/* The device on the SPI side: records what arrives, answers with reply */
static struct { uint8_t got, reply; int pulses; } dev;

static int dev_pulse(void *ctx, int mosi) {
    (void)ctx;
    int miso = (dev.reply >> (7 - dev.pulses % 8)) & 1;
    dev.got = (uint8_t)(dev.got << 1 | mosi);
    dev.pulses++;
    return miso;
}

static uint8_t portb_input(void *ctx) {
    (void)ctx;
    uint8_t v = 0x00;
    return gal_spi_output(&gs, &v) ? v : 0x00;
}

static void setup(uint8_t reply) {
    dev.got = 0; dev.reply = reply; dev.pulses = 0;
    via_6522_init(&vch, &vs);
    gal_spi_init(&gch, &gs, &vs, (struct spi_device){ NULL, dev_pulse });
    via_6522_set_portb_input(&vs, portb_input, NULL);
    bus_init(&bus_);
    bus_add_chip(&bus_, &vch);
    bus_add_chip(&bus_, &gch);
    bus_.viacs = 1;
    bus_write(&bus_, 0xF003, E);      /* DDRA: E an output, low */
    bus_write(&bus_, 0xF002, 0xFF);   /* DDRB: port B an output */
}

/* n Phi2 cycles; counts those in which the '299 drove port B */
static int cycles(int n) {
    int driving = 0;
    uint8_t v;
    for (int i = 0; i < n; i++) {
        bus_step(&bus_);
        driving += gal_spi_output(&gs, &v);
    }
    return driving;
}

static void e(int high) { bus_write(&bus_, 0xF001, high ? E : 0); }

TEST a_write_sends_the_byte_without_driving_port_b(void) {
    setup(0x00);
    bus_write(&bus_, 0xF000, 0x3C);
    e(1);
    int driving = cycles(6);          /* tsb PORTA ... trb PORTA */
    e(0);
    driving += cycles(10);
    ASSERT_EQ(8, dev.pulses);
    ASSERT_EQ_FMT(0x3C, dev.got, "%02X");
    ASSERT_EQ(0, driving);
    PASS();
}

TEST a_read_holds_the_reply_on_port_b_while_e_is_high(void) {
    setup(0xA5);
    bus_write(&bus_, 0xF000, 0x00);   /* the byte sent */
    e(1);
    cycles(3);
    bus_write(&bus_, 0xF002, 0x00);   /* port B an input */
    cycles(9);
    ASSERT_EQ(8, dev.pulses);
    ASSERT_EQ_FMT(0xA5, via_6522_portb_pins(&vs), "%02X");
    e(0);
    cycles(1);
    uint8_t v;
    ASSERT_FALSE(gal_spi_output(&gs, &v));
    PASS();
}

TEST a_short_e_still_sends_a_whole_byte_and_holds_nothing(void) {
    setup(0xA5);
    bus_write(&bus_, 0xF000, 0x81);
    e(1);
    cycles(1);
    e(0);
    int driving = cycles(12);
    ASSERT_EQ(8, dev.pulses);
    ASSERT_EQ_FMT(0x81, dev.got, "%02X");
    ASSERT_EQ(0, driving);
    PASS();
}

TEST e_held_after_a_byte_sends_no_more(void) {
    setup(0x00);
    e(1);
    cycles(40);
    ASSERT_EQ(8, dev.pulses);
    PASS();
}

TEST e_as_an_input_is_low(void) {
    setup(0x00);
    bus_write(&bus_, 0xF001, E);
    bus_write(&bus_, 0xF003, 0x00);   /* PA2 an input */
    cycles(20);
    ASSERT_EQ(0, dev.pulses);
    PASS();
}

TEST bytes_back_to_back(void) {
    setup(0x00);
    const uint8_t bytes[3] = { 0x00, 0x39, 0x00 };
    uint8_t got[3];
    for (int i = 0; i < 3; i++) {
        bus_write(&bus_, 0xF000, bytes[i]);
        e(1);
        cycles(6);
        e(0);
        cycles(4);
        got[i] = dev.got;
    }
    ASSERT_EQ(24, dev.pulses);
    ASSERT_MEM_EQ(bytes, got, 3);
    PASS();
}

TEST reset_ends_a_burst(void) {
    setup(0x00);
    e(1);
    cycles(3);
    gch.ops->reset(&gch);
    e(0);
    cycles(1);                        /* the low half after this edge has no pulse */
    ASSERT_EQ(3, dev.pulses);
    PASS();
}

SUITE(gal_spi) {
    RUN_TEST(a_write_sends_the_byte_without_driving_port_b);
    RUN_TEST(a_read_holds_the_reply_on_port_b_while_e_is_high);
    RUN_TEST(a_short_e_still_sends_a_whole_byte_and_holds_nothing);
    RUN_TEST(e_held_after_a_byte_sends_no_more);
    RUN_TEST(e_as_an_input_is_low);
    RUN_TEST(bytes_back_to_back);
    RUN_TEST(reset_ends_a_burst);
}

GREATEST_MAIN_DEFS();

int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(gal_spi);
    GREATEST_MAIN_END();
}
