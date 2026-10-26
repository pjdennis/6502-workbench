/* net_client tests: a client on the network (chips/net_client.h) for the W5500's TCP sockets: it connects once
 * a socket listens on its port, sends its request after its latency, keeps what the server sends, and connects
 * again after the server closes, as many times as it was asked. The W5500 is driven through its SPI device, as
 * the FPGA does. */

#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "greatest.h"
#include "../bus.h"
#include "../chips/w5500.h"
#include "../chips/net_client.h"

#define S0 0x08                        /* socket 0's registers and TX buffer, as control bytes */
#define S0_TX 0x10
#define WRITE 0x04
#define SN_MR 0x00
#define SN_CR 0x01
#define SN_SR 0x03
#define SN_PORT 0x04
#define SN_TX_WR 0x24
#define SN_RX_RSR 0x26
#define OPEN 0x01
#define LISTEN 0x02
#define DISCON 0x08
#define SEND 0x20
#define SOCK_ESTABLISHED 0x17

static struct w5500_state ws;
static struct net_client nc;
static struct chip wch, nch;
static struct spi_device dev;
static char response[256];
static FILE *response_file;

static void frame(uint8_t block, uint16_t addr, uint8_t *data, int n) {
    spi_select(&dev, 1);
    spi_byte(&dev, addr >> 8);
    spi_byte(&dev, addr & 0xFF);
    spi_byte(&dev, block);
    for (int i = 0; i < n; i++) data[i] = spi_byte(&dev, data[i]);
    spi_select(&dev, 0);
}

static void set_s0(uint16_t reg, uint8_t v) {
    frame(S0 | WRITE, reg, &v, 1);
}

static unsigned s0_16(uint16_t reg) {
    uint8_t v[2] = { 0, 0 };
    frame(S0, reg, v, 2);
    return (unsigned)v[0] << 8 | v[1];
}

static uint8_t s0(uint16_t reg) {
    uint8_t v = 0;
    frame(S0, reg, &v, 1);
    return v;
}

static void listen_(void) {
    set_s0(SN_MR, 0x01);
    uint8_t port[2] = { 0, 80 };
    frame(S0 | WRITE, SN_PORT, port, 2);
    set_s0(SN_CR, OPEN);
    set_s0(SN_CR, LISTEN);
}

/* The server's reply: text into the TX buffer, SEND, then DISCON */
static void reply(const char *text) {
    unsigned wr = s0_16(SN_TX_WR), n = (unsigned)strlen(text);
    uint8_t data[64];
    memcpy(data, text, n);
    frame(S0_TX | WRITE, (uint16_t)wr, data, (int)n);
    uint8_t new_wr[2] = { (uint8_t)((wr + n) >> 8), (uint8_t)(wr + n) };
    frame(S0 | WRITE, SN_TX_WR, new_wr, 2);
    set_s0(SN_CR, SEND);
    set_s0(SN_CR, DISCON);
}

static void ticks(int n) {
    while (n-- > 0) nch.ops->tick(&nch, NULL);
}

static void setup(unsigned connections) {
    static const uint8_t request[] = "GET / HTTP/1.0\r\n\r\n";
    w5500_init(&wch, &ws, NULL, 0);
    dev = w5500_spi(&ws);
    memset(response, 0, sizeof response);
    if (response_file) fclose(response_file);
    response_file = fmemopen(response, sizeof response, "w");
    net_client_init(&nch, &nc, &ws, 80, request, sizeof request - 1, connections, 10, response_file);
}

TEST it_waits_for_a_socket_to_listen(void) {
    setup(1);
    ticks(5);
    ASSERT_EQ_FMT(0u, nc.made, "%u");
    listen_();
    ticks(1);
    ASSERT_EQ_FMT(1u, nc.made, "%u");
    ASSERT_EQ_FMT(SOCK_ESTABLISHED, s0(SN_SR), "%02X");
    PASS();
}

TEST the_request_comes_after_the_latency(void) {
    setup(1);
    listen_();
    ticks(1);
    ticks(9);
    ASSERT_EQ_FMT(0u, s0_16(SN_RX_RSR), "%u");
    ticks(1);
    ASSERT_EQ_FMT(18u, s0_16(SN_RX_RSR), "%u");
    PASS();
}

TEST it_keeps_the_reply_and_connects_again(void) {
    setup(2);
    listen_();
    ticks(20);
    reply("HTTP/1.0 200 OK\r\n");
    ASSERT_EQ_FMT(1u, nc.closed, "%u");
    ticks(5);
    ASSERT_EQ_FMT(1u, nc.made, "%u");                  /* not listening yet */
    listen_();
    ticks(20);
    ASSERT_EQ_FMT(2u, nc.made, "%u");
    reply("again");
    listen_();
    ticks(20);
    ASSERT_EQ_FMT(2u, nc.made, "%u");                  /* two were asked for */
    fflush(response_file);
    ASSERT_STR_EQ("HTTP/1.0 200 OK\r\nagain", response);
    ASSERT_EQ_FMT(22u, nc.received, "%u");
    PASS();
}

TEST the_report(void) {
    setup(2);
    listen_();
    ticks(20);
    reply("HTTP/1.0 200 OK\r\n");
    char buf[256] = { 0 };
    FILE *fp = fmemopen(buf, sizeof buf, "w");
    net_client_report(fp, "michael", &nc);
    fclose(fp);
    ASSERT_STR_EQ("michael: net client: port 80: 1 of 2 connections, 1 closed by the server, 17 bytes received\n",
                  buf);
    PASS();
}

SUITE(net_client) {
    RUN_TEST(it_waits_for_a_socket_to_listen);
    RUN_TEST(the_request_comes_after_the_latency);
    RUN_TEST(it_keeps_the_reply_and_connects_again);
    RUN_TEST(the_report);
}

GREATEST_MAIN_DEFS();
int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(net_client);
    GREATEST_MAIN_END();
}
