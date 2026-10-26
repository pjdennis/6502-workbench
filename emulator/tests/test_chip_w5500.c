/* w5500 chip tests: the WIZnet W5500 as an SPI device (chips/w5500.h), its chip select on Michael's PA0. A
 * frame is two address bytes, a control byte (the block, read or write, and the mode) and data; in variable
 * length mode it lasts until the chip select rises. */

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
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

/* n bytes from addr in the block (a control byte), in a frame */
static void read_block(uint8_t block, uint16_t addr, uint8_t *data, int n) {
    select_(1);
    byte(addr >> 8);
    byte(addr & 0xFF);
    byte(block);
    for (int i = 0; i < n; i++) data[i] = byte(0x00);
    select_(0);
}

static void write_block(uint8_t block, uint16_t addr, const uint8_t *data, int n) {
    select_(1);
    byte(addr >> 8);
    byte(addr & 0xFF);
    byte(block | WRITE);
    for (int i = 0; i < n; i++) byte(data[i]);
    select_(0);
}

static uint8_t read_common(uint16_t addr) {
    uint8_t v;
    read_block(COMMON, addr, &v, 1);
    return v;
}

static void write_common(uint16_t addr, const uint8_t *data, int n) {
    write_block(COMMON, addr, data, n);
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

TEST the_report_shows_the_network_settings(void) {
    setup();
    const uint8_t net[18] = { 192, 168, 8, 1,   255, 255, 255, 0,   0x02, 0x65, 0x02, 0x00, 0x00, 0x01,
                              192, 168, 8, 50 };   /* GAR, SUBR, SHAR, SIPR: one run from $0001 */
    write_common(GAR, net, 18);
    char *text; size_t size;
    FILE *fp = open_memstream(&text, &size);
    w5500_report(fp, "michael", &ws);
    fclose(fp);
    ASSERT_STR_EQ("michael: w5500: ip 192.168.8.50 mask 255.255.255.0 gateway 192.168.8.1 mac 02:65:02:00:00:01\n",
                  text);
    free(text);
    PASS();
}

/* A capacitor on the chip select (against glitches) delays it: the W5500 sees it change cs_delay ticks late */
TEST a_slow_chip_select_ignores_a_frame_that_starts_too_soon(void) {
    setup();
    ws.cs_delay = 10;
    select_(1);                        /* one tick: too soon */
    ASSERT_EQ_FMT(0xFF, byte(0x00), "%02X");
    for (int i = 0; i < 10; i++) bus_step(&bus_);
    ASSERT_EQ_FMT(0x01, byte(VERSIONR >> 8), "%02X");   /* now it's selected */
    ASSERT_EQ_FMT(0x02, byte(VERSIONR & 0xFF), "%02X");
    ASSERT_EQ_FMT(0x03, byte(COMMON), "%02X");
    ASSERT_EQ_FMT(0x04, byte(0x00), "%02X");
    select_(0);
    for (int i = 0; i < 10; i++) bus_step(&bus_);
    ASSERT_EQ_FMT(0xFF, byte(0x00), "%02X");            /* deselected again */
    PASS();
}

/* A glitch on the chip select shorter than the delay doesn't end the frame */
TEST a_slow_chip_select_ignores_a_glitch(void) {
    setup();
    ws.cs_delay = 10;
    select_(1);
    for (int i = 0; i < 10; i++) bus_step(&bus_);
    byte(VERSIONR >> 8);
    select_(0);                        /* a glitch, one tick wide */
    select_(1);
    byte(VERSIONR & 0xFF);
    byte(COMMON);
    ASSERT_EQ_FMT(0x04, byte(0x00), "%02X");
    select_(0);
    PASS();
}

/* A glitch on the chip select while it's low: the W5500 starts a new frame */
TEST a_chip_select_glitch_restarts_the_frame(void) {
    setup();
    select_(1);
    byte(VERSIONR >> 8);
    w5500_cs_glitch(&ws);
    ASSERT_EQ_FMT(0x01, byte(VERSIONR >> 8), "%02X");   /* the header again from its first byte */
    ASSERT_EQ_FMT(0x02, byte(VERSIONR & 0xFF), "%02X");
    ASSERT_EQ_FMT(0x03, byte(COMMON), "%02X");
    ASSERT_EQ_FMT(0x04, byte(0x00), "%02X");
    select_(0);
    PASS();
}

/* On the FPGA's net pins the FPGA drives the chip select: no VIA pin, select through the SPI device */
TEST selected_through_the_spi_device(void) {
    static struct w5500_state w;
    static struct chip c;
    w5500_init(&c, &w, NULL, 0);
    struct spi_device d = w5500_spi(&w);
    ASSERT_EQ_FMT(1, spi_pulse(&d, 0), "%d");          /* deselected: MISO undriven */
    spi_select(&d, 1);
    uint8_t in = 0;
    const uint8_t frame[4] = { 0x00, 0x39, 0x00, 0x00 };
    for (int k = 0; k < 4; k++) {
        in = 0;
        for (int i = 7; i >= 0; i--) in = (uint8_t)(in << 1 | spi_pulse(&d, (frame[k] >> i) & 1));
    }
    ASSERT_EQ_FMT(0x04, in, "%02X");
    spi_select(&d, 0);
    c.ops->tick(&c, &bus_);                            /* no VIA: the tick leaves the selection alone */
    ASSERT_EQ_FMT(1, spi_pulse(&d, 0), "%d");
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

/* Socket 0's TCP side, with a peer on the network (w5500_attach_peer) */
#define S0 0x08                        /* socket 0's registers, TX buffer and RX buffer */
#define S0_TX 0x10
#define S0_RX 0x18
#define SN_MR 0x00
#define SN_CR 0x01
#define SN_IR 0x02
#define SN_SR 0x03
#define SN_PORT 0x04
#define SN_TX_FSR 0x20
#define SN_TX_RD 0x22
#define SN_TX_WR 0x24
#define SN_RX_RSR 0x26
#define SN_RX_RD 0x28
#define SN_RX_WR 0x2A
#define OPEN 0x01
#define LISTEN 0x02
#define DISCON 0x08
#define CLOSE 0x10
#define SEND 0x20
#define RECV 0x40
#define IR_CON 0x01
#define IR_DISCON 0x02
#define IR_RECV 0x04
#define IR_SEND_OK 0x10
#define SOCK_CLOSED 0x00
#define SOCK_INIT 0x13
#define SOCK_LISTEN 0x14
#define SOCK_ESTABLISHED 0x17
#define SOCK_CLOSE_WAIT 0x1C

static uint8_t s0(uint16_t reg) {
    uint8_t v;
    read_block(S0, reg, &v, 1);
    return v;
}

static unsigned s0_16(uint16_t reg) {
    uint8_t v[2];
    read_block(S0, reg, v, 2);
    return (unsigned)v[0] << 8 | v[1];
}

static void set_s0(uint16_t reg, uint8_t v) {
    write_block(S0, reg, &v, 1);
}

static void set_s0_16(uint16_t reg, unsigned v) {
    const uint8_t b[2] = { (uint8_t)(v >> 8), (uint8_t)v };
    write_block(S0, reg, b, 2);
}

/* What the peer saw */
static uint8_t peer_got[4096];
static unsigned peer_len;
static int peer_closed_socket;

static void peer_receive(void *ctx, int socket, const uint8_t *data, unsigned len) {
    (void)ctx; (void)socket;
    for (unsigned i = 0; i < len && peer_len < sizeof peer_got; i++) peer_got[peer_len++] = data[i];
}

static void peer_closed(void *ctx, int socket) {
    (void)ctx;
    peer_closed_socket = socket;
}

static void listening_on(unsigned port) {
    setup();
    peer_len = 0;
    peer_closed_socket = -1;
    w5500_attach_peer(&ws, (struct w5500_peer){ NULL, peer_receive, peer_closed });
    set_s0(SN_MR, 0x01);               /* TCP */
    set_s0_16(SN_PORT, port);
    set_s0(SN_CR, OPEN);
    set_s0(SN_CR, LISTEN);
}

TEST a_tcp_socket_opens_then_listens(void) {
    setup();
    set_s0(SN_MR, 0x01);
    set_s0(SN_CR, OPEN);
    ASSERT_EQ_FMT(0x00, s0(SN_CR), "%02X");            /* the command taken */
    ASSERT_EQ_FMT(SOCK_INIT, s0(SN_SR), "%02X");
    set_s0(SN_CR, LISTEN);
    ASSERT_EQ_FMT(SOCK_LISTEN, s0(SN_SR), "%02X");
    ASSERT_EQ_FMT(0x0800, s0_16(SN_TX_FSR), "%04X");
    ASSERT_EQ_FMT(0x0000, s0_16(SN_RX_RSR), "%04X");
    PASS();
}

TEST a_peer_connects_to_the_listening_port(void) {
    listening_on(80);
    ASSERT_EQ_FMT(-1, w5500_peer_connect(&ws, 81), "%d");
    ASSERT_EQ_FMT(SOCK_LISTEN, s0(SN_SR), "%02X");
    ASSERT_EQ_FMT(0, w5500_peer_connect(&ws, 80), "%d");
    ASSERT_EQ_FMT(SOCK_ESTABLISHED, s0(SN_SR), "%02X");
    ASSERT_EQ_FMT(IR_CON, s0(SN_IR), "%02X");
    set_s0(SN_IR, IR_CON);                             /* a 1 clears it */
    ASSERT_EQ_FMT(0x00, s0(SN_IR), "%02X");
    ASSERT_EQ_FMT(-1, w5500_peer_connect(&ws, 80), "%d");   /* no longer listening */
    PASS();
}

TEST what_the_peer_sends_arrives_in_the_rx_buffer(void) {
    listening_on(80);
    w5500_peer_connect(&ws, 80);
    ASSERT_EQ_FMT(3u, w5500_peer_send(&ws, 0, (const uint8_t *)"GET", 3), "%u");
    ASSERT_EQ_FMT(3u, s0_16(SN_RX_RSR), "%u");
    ASSERT_EQ_FMT(IR_CON | IR_RECV, s0(SN_IR), "%02X");
    unsigned rd = s0_16(SN_RX_RD);
    uint8_t got[3];
    read_block(S0_RX, (uint16_t)rd, got, 3);
    ASSERT_MEM_EQ("GET", got, 3);
    set_s0_16(SN_RX_RD, rd + 3);
    ASSERT_EQ_FMT(3u, s0_16(SN_RX_RSR), "%u");         /* until RECV */
    set_s0(SN_CR, RECV);
    ASSERT_EQ_FMT(0u, s0_16(SN_RX_RSR), "%u");
    ASSERT_EQ_FMT(rd + 3, s0_16(SN_RX_WR), "%u");
    PASS();
}

TEST the_rx_buffer_takes_what_fits(void) {
    static uint8_t big[0x900];
    listening_on(80);
    w5500_peer_connect(&ws, 80);
    ASSERT_EQ_FMT(0x800u, w5500_peer_send(&ws, 0, big, sizeof big), "%u");
    ASSERT_EQ_FMT(0u, w5500_peer_send(&ws, 0, big, 1), "%u");
    PASS();
}

TEST send_gives_the_peer_the_tx_buffer_from_rd_to_wr(void) {
    listening_on(80);
    w5500_peer_connect(&ws, 80);
    unsigned wr = s0_16(SN_TX_WR);
    write_block(S0_TX, (uint16_t)wr, (const uint8_t *)"HTTP", 4);
    set_s0_16(SN_TX_WR, wr + 4);
    ASSERT_EQ_FMT(0x0800u - 4, s0_16(SN_TX_FSR), "%u");
    ASSERT_EQ_FMT(0u, peer_len, "%u");
    set_s0(SN_CR, SEND);
    ASSERT_EQ_FMT(4u, peer_len, "%u");
    ASSERT_MEM_EQ("HTTP", peer_got, 4);
    ASSERT_EQ_FMT(wr + 4, s0_16(SN_TX_RD), "%u");
    ASSERT_EQ_FMT(0x0800u, s0_16(SN_TX_FSR), "%u");
    ASSERT_EQ_FMT(IR_CON | IR_SEND_OK, s0(SN_IR), "%02X");
    PASS();
}

TEST the_tx_buffer_wraps(void) {
    listening_on(80);
    w5500_peer_connect(&ws, 80);
    set_s0_16(SN_TX_WR, 0xFFFE);                       /* as if 64 KB had gone */
    set_s0(SN_CR, SEND);                               /* TX_RD catches up with it */
    peer_len = 0;
    write_block(S0_TX, 0xFFFE, (const uint8_t *)"ab", 2);
    write_block(S0_TX, 0x0000, (const uint8_t *)"cd", 2);
    set_s0_16(SN_TX_WR, 0x0002);
    set_s0(SN_CR, SEND);
    ASSERT_EQ_FMT(4u, peer_len, "%u");
    ASSERT_MEM_EQ("abcd", peer_got, 4);
    PASS();
}

TEST discon_closes_the_connection(void) {
    listening_on(80);
    w5500_peer_connect(&ws, 80);
    set_s0(SN_CR, DISCON);
    ASSERT_EQ_FMT(SOCK_CLOSED, s0(SN_SR), "%02X");
    ASSERT_EQ_FMT(0, peer_closed_socket, "%d");
    ASSERT_EQ_FMT(IR_CON | IR_DISCON, s0(SN_IR), "%02X");
    PASS();
}

TEST the_peer_closing_leaves_close_wait(void) {
    listening_on(80);
    w5500_peer_connect(&ws, 80);
    w5500_peer_close(&ws, 0);
    ASSERT_EQ_FMT(SOCK_CLOSE_WAIT, s0(SN_SR), "%02X");
    ASSERT_EQ_FMT(IR_CON | IR_DISCON, s0(SN_IR), "%02X");
    ASSERT_EQ_FMT(-1, peer_closed_socket, "%d");
    set_s0(SN_CR, CLOSE);
    ASSERT_EQ_FMT(SOCK_CLOSED, s0(SN_SR), "%02X");
    PASS();
}

TEST reopened_the_socket_has_nothing_left_to_read(void) {
    listening_on(80);
    w5500_peer_connect(&ws, 80);
    w5500_peer_send(&ws, 0, (const uint8_t *)"GET", 3);
    set_s0(SN_CR, CLOSE);
    set_s0(SN_CR, OPEN);
    ASSERT_EQ_FMT(0u, s0_16(SN_RX_RSR), "%u");
    ASSERT_EQ_FMT(s0_16(SN_RX_RD), s0_16(SN_RX_WR), "%u");
    PASS();
}

TEST the_status_is_read_only(void) {
    listening_on(80);
    set_s0(SN_SR, SOCK_ESTABLISHED);
    ASSERT_EQ_FMT(SOCK_LISTEN, s0(SN_SR), "%02X");
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
    RUN_TEST(the_report_shows_the_network_settings);
    RUN_TEST(a_slow_chip_select_ignores_a_frame_that_starts_too_soon);
    RUN_TEST(a_slow_chip_select_ignores_a_glitch);
    RUN_TEST(a_chip_select_glitch_restarts_the_frame);
    RUN_TEST(selected_through_the_spi_device);
    RUN_TEST(reset_values);
    RUN_TEST(reset_clears_what_was_written);
    RUN_TEST(a_tcp_socket_opens_then_listens);
    RUN_TEST(a_peer_connects_to_the_listening_port);
    RUN_TEST(what_the_peer_sends_arrives_in_the_rx_buffer);
    RUN_TEST(the_rx_buffer_takes_what_fits);
    RUN_TEST(send_gives_the_peer_the_tx_buffer_from_rd_to_wr);
    RUN_TEST(the_tx_buffer_wraps);
    RUN_TEST(discon_closes_the_connection);
    RUN_TEST(the_peer_closing_leaves_close_wait);
    RUN_TEST(reopened_the_socket_has_nothing_left_to_read);
    RUN_TEST(the_status_is_read_only);
}

GREATEST_MAIN_DEFS();
int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(w5500);
    GREATEST_MAIN_END();
}
