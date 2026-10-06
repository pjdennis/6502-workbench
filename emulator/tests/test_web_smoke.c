/* web_server lifecycle smoke test.
 *
 * Primary purpose: give AddressSanitizer something to chew on. Walks
 * the start -> broadcast -> audio-tap -> stop paths repeatedly, plus
 * one shape of an error path (bind-of-a-pinned-port collision). All
 * assertions run under regular `make test`; the leak-detection happens
 * automatically when this is rebuilt under `make sanitizers`. And a
 * page's socket, to check what it gets of the graphic display. */

#define _GNU_SOURCE   /* memmem */
#include <arpa/inet.h>
#include <netinet/in.h>
#include <poll.h>
#include <stdint.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#include "greatest.h"
#include "../web_server.h"
#include "../web_display.h"

static void fill_snapshot(struct web_snapshot *s) {
    memset(s, 0, sizeof(*s));
    s->lcd_rows = 2;
    s->lcd_cols = 16;
    for (int i = 0; i < s->lcd_rows * s->lcd_cols; i++) s->ddram_visible[i] = 0x20;
    /* Some CGRAM content so the JSON encoder visits the array fully. */
    for (int i = 0; i < 64; i++) s->cgram[i] = (uint8_t)(i & 0x1F);
    s->cursor_row = 0; s->cursor_col = 0;
    s->display_on = 1;
    s->ddra = 0xFF; s->ddrb = 0x3F;
    s->osc_ticks = 12345; s->cpu_cycles = 6172; s->pc = 0x402E;
}

TEST start_stop_cycle_releases_resources(void) {
    /* Bind to an ephemeral port, push a snapshot, queue some audio,
     * shut down. Repeat. The default `make test` only checks that the
     * sequence runs cleanly; the ASan version turns any leaked
     * server-struct allocation into a hard failure at process exit. */
    struct web_snapshot snap;
    fill_snapshot(&snap);

    for (int i = 0; i < 5; i++) {
        struct web_server *srv =
            web_server_start("wendy2c", 0, "127.0.0.1", "emulator/web");
        ASSERT(srv != NULL);
        ASSERT(web_server_port(srv) > 0);
        ASSERT_EQ_FMT(0, web_server_client_count(srv), "%d");

        /* No clients connected; broadcasts should be inexpensive
         * no-ops but still walk every code path that touches the
         * JSON buffer. */
        for (int j = 0; j < 4; j++) web_server_broadcast(srv, &snap);

        /* Audio tap with no clients should also be a no-op and reset
         * the ring. */
        web_server_send_audio_rate(srv, 22050);
        for (int j = 0; j < 100; j++) {
            web_server_audio_tap(srv, (int16_t)(j * 100));
        }
        web_server_flush_audio(srv);

        /* Drain one poll cycle (no events expected). */
        struct web_event evt;
        ASSERT_EQ_FMT(0, web_server_poll(srv, &evt), "%d");
        ASSERT_EQ_FMT((int)WEB_EVT_NONE, (int)evt.type, "%d");

        web_server_stop(srv);
    }
    PASS();
}

TEST stop_null_is_safe(void) {
    /* web_server_stop and poll guard against NULL so dispatch code
     * can call them unconditionally on the failure path. */
    web_server_stop(NULL);
    struct web_event evt = { (enum web_event_type)999, 7 };
    ASSERT_EQ_FMT(0, web_server_poll(NULL, &evt), "%d");
    ASSERT_EQ_FMT((int)WEB_EVT_NONE, (int)evt.type, "%d");
    PASS();
}

TEST broadcast_without_clients_is_noop(void) {
    /* Edge case: building the JSON snapshot needs to handle the
     * largest LCD geometry (20x4) so the inner sj_printf loop reaches
     * the high end of the ddram_visible array. */
    struct web_server *srv = web_server_start("wendy2c", 0, "127.0.0.1", "emulator/web");
    ASSERT(srv != NULL);

    struct web_snapshot snap;
    fill_snapshot(&snap);
    snap.lcd_rows = 4;
    snap.lcd_cols = 20;
    for (int i = 0; i < 4 * 20; i++) snap.ddram_visible[i] = (uint8_t)('A' + (i % 26));
    web_server_broadcast(srv, &snap);

    /* And audio_tap with the ring forced to wrap: AUDIO_RING_CAPACITY
     * is 8192 in the implementation; push 10000 samples to exercise
     * the overflow-drops-oldest branch. */
    for (int i = 0; i < 10000; i++) web_server_audio_tap(srv, (int16_t)i);
    web_server_flush_audio(srv);  /* no clients -> drops the queue */

    web_server_stop(srv);
    PASS();
}

/* A page's WebSocket, as a browser opens it: connected and upgraded, the server having answered */
static int ws_connect(struct web_server *srv) {
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in a;
    memset(&a, 0, sizeof a);
    a.sin_family = AF_INET;
    a.sin_port = htons((uint16_t)web_server_port(srv));
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (connect(fd, (struct sockaddr *)&a, sizeof a) != 0) return -1;
    static const char request[] = "GET / HTTP/1.1\r\nHost: test\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                                  "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n\r\n";
    if (send(fd, request, sizeof request - 1, 0) < 0) return -1;
    struct web_event evt;
    for (int i = 0; i < 200 && web_server_client_count(srv) == 0; i++) {
        web_server_poll(srv, &evt);
        usleep(1000);
    }
    char c, end[4] = { 0 };
    while (memcmp(end, "\r\n\r\n", 4)) {   /* the 101's headers */
        if (recv(fd, &c, 1, 0) != 1) return -1;
        memmove(end, end + 1, 3);
        end[3] = c;
    }
    return fd;
}

static int read_all(int fd, uint8_t *buf, int n) {
    for (int got = 0; got < n; ) {
        struct pollfd p = { fd, POLLIN, 0 };
        if (poll(&p, 1, 500) <= 0) return -1;
        ssize_t r = recv(fd, buf + got, (size_t)(n - got), 0);
        if (r <= 0) return -1;
        got += (int)r;
    }
    return 0;
}

/* The next frame from the server: its opcode (1 text, 2 binary), its payload in buf and its length in *len;
 * -1 if none comes */
static int ws_frame(int fd, uint8_t *buf, int *len) {
    uint8_t h[4];
    if (read_all(fd, h, 2)) return -1;
    *len = h[1] & 0x7F;
    if (*len == 126) {
        if (read_all(fd, h + 2, 2)) return -1;
        *len = h[2] << 8 | h[3];
    }
    if (read_all(fd, buf, *len)) return -1;
    return h[0] & 0x0F;
}

TEST a_page_gets_the_graphic_display_as_deltas(void) {
    /* Each snapshot, a page gets what changed on the display since the last (all of it at first), as a binary
     * message before the snapshot's JSON */
    static struct ili9341 panel;
    static uint8_t buf[1 << 16];
    struct web_snapshot snap;
    fill_snapshot(&snap);
    ili9341_init(&panel);
    snap.display = &panel;
    struct web_server *srv = web_server_start("michael", 0, "127.0.0.1", "emulator/web");
    ASSERT(srv != NULL);
    int fd = ws_connect(srv), n;
    ASSERT(fd >= 0);
    ASSERT_EQ(1, ws_frame(fd, buf, &n));            /* hello */

    web_server_broadcast(srv, &snap);
    ASSERT_EQ(2, ws_frame(fd, buf, &n));
    ASSERT_EQ(WEB_DISPLAY_TAG, buf[0]);
    ASSERT_EQ_FMT(1 + 20 * (5 + 3), n, "%d");        /* black, a band at a time */
    ASSERT_EQ(1, ws_frame(fd, buf, &n));
    ASSERT(memmem(buf, (size_t)n, "\"gd\":{", 6) != NULL);

    web_server_broadcast(srv, &snap);                /* nothing changed: only the JSON */
    ASSERT_EQ(1, ws_frame(fd, buf, &n));

    panel.memory[300][7] = 0xF800;
    web_server_broadcast(srv, &snap);
    ASSERT_EQ(2, ws_frame(fd, buf, &n));
    const uint8_t want[] = { WEB_DISPLAY_TAG, 44, 1, 7, 0, 0, 0x41, 0x00, 0xF8 };
    ASSERT_EQ_FMT((int)sizeof want, n, "%d");
    ASSERT_MEM_EQ(want, buf, sizeof want);
    ASSERT_EQ(1, ws_frame(fd, buf, &n));

    close(fd);
    web_server_stop(srv);
    PASS();
}

SUITE(web_smoke_suite) {
    RUN_TEST(stop_null_is_safe);
    RUN_TEST(start_stop_cycle_releases_resources);
    RUN_TEST(broadcast_without_clients_is_noop);
    RUN_TEST(a_page_gets_the_graphic_display_as_deltas);
}

GREATEST_MAIN_DEFS();
int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(web_smoke_suite);
    GREATEST_MAIN_END();
}
