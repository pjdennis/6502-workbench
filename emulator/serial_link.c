/* --serial-link: the Unix-socket wire protocol that drives CB2 at emulated-time resolution (see serial_link.h). */
#include "serial_link.h"

#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

#include "bus.h"
#include "chips/via_6522.h"

#define RX_BUF_SIZE 4096

/* The recv buffer is sized to comfortably hold a few-bit run of UART
 * commands. Each "set + delay" command is 9 bytes (1 op + 8 ns), so
 * 4 KiB = ~450 transitions = ~45 bytes worth of 8N1 at the host's
 * preferred rate before we need another recv. A burst-uploader will
 * usually fill the kernel's socket buffer (~256 KiB) and we'll drain
 * it incrementally as the OSC clock advances. */

struct serial_link {
    int listen_fd;
    int client_fd;
    char sock_path[256];

    /* Receive buffer (raw bytes from the socket; we parse out one
     * command at a time). */
    uint8_t rx[RX_BUF_SIZE];
    int rx_len;

    /* The next command may not take effect until osc_ticks reaches
     * unblock_at_osc. `has_unblock` is 0 before the first delay-
     * carrying command, then stays 1. */
    uint64_t unblock_at_osc;
    int has_unblock;

    /* Fractional residue for ns -> osc-tick rounding, in units of
     * (1 / osc_per_us / 1000) of an OSC tick. Accumulates so 8681 ns
     * doesn't drift after many bits. */
    double tick_residue;
    double osc_per_ns;            /* osc_per_us / 1000.0 */

    /* TX bracket. When in_tx is set and unblock_at_osc has been
     * reached but no command is queued in rx, the run loop must
     * stall (don't advance OSC) until more bytes arrive. */
    int in_tx;
    /* Wall-clock time at which we first hit a stall, for the "too
     * far behind" warning. Reset when commands start flowing again. */
    /* (TODO: surface this if we see real-world hosts struggle.) */

    /* Cached CB2 level so we don't bother the VIA on no-op writes. */
    int last_cb2_level;
    int last_cb2_valid;
};

static void link_warn(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    fprintf(stderr, "serial-link: ");
    vfprintf(stderr, fmt, ap);
    fprintf(stderr, "\n");
    va_end(ap);
}

/* Set the socket non-blocking. Best-effort; warns on error. */
static int set_nonblocking(int fd) {
    int flags = fcntl(fd, F_GETFL, 0);
    if (flags < 0) return -1;
    return fcntl(fd, F_SETFL, flags | O_NONBLOCK);
}

struct serial_link *serial_link_start(const char *path, double osc_per_us) {
    if (!path || !*path) return NULL;
    if (osc_per_us <= 0.0) {
        link_warn("osc_per_us must be > 0 (got %g)", osc_per_us);
        return NULL;
    }

    struct serial_link *l = (struct serial_link *)calloc(1, sizeof(*l));
    if (!l) return NULL;
    l->listen_fd = -1;
    l->client_fd = -1;
    l->osc_per_ns = osc_per_us / 1000.0;
    snprintf(l->sock_path, sizeof(l->sock_path), "%s", path);

    /* Remove any stale socket from a previous crashed run. */
    unlink(path);

    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) { link_warn("socket: %s", strerror(errno)); free(l); return NULL; }

    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    if (strlen(path) >= sizeof(addr.sun_path)) {
        link_warn("socket path too long (max %zu): %s",
                  sizeof(addr.sun_path) - 1, path);
        close(fd); free(l); return NULL;
    }
    strncpy(addr.sun_path, path, sizeof(addr.sun_path) - 1);

    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        link_warn("bind %s: %s", path, strerror(errno));
        close(fd); free(l); return NULL;
    }
    if (listen(fd, 1) < 0) {
        link_warn("listen: %s", strerror(errno));
        close(fd); unlink(path); free(l); return NULL;
    }
    set_nonblocking(fd);
    l->listen_fd = fd;
    fprintf(stderr, "serial-link: listening on unix:%s\n", path);
    return l;
}

void serial_link_stop(struct serial_link *l) {
    if (!l) return;
    if (l->client_fd >= 0) close(l->client_fd);
    if (l->listen_fd >= 0) close(l->listen_fd);
    if (l->sock_path[0]) unlink(l->sock_path);
    free(l);
}

int serial_link_client_fd(const struct serial_link *l) {
    if (!l) return -1;
    return l->client_fd;
}

int serial_link_has_client(const struct serial_link *l) {
    return l && l->client_fd >= 0;
}

static void drop_client(struct serial_link *l) {
    if (l->client_fd >= 0) close(l->client_fd);
    l->client_fd = -1;
    l->rx_len = 0;
    /* If we were mid-TX, exit it so the run loop stops stalling. The
     * last CB2 level is preserved. */
    l->in_tx = 0;
    l->has_unblock = 0;
}

static void try_accept(struct serial_link *l) {
    if (l->client_fd >= 0) return;  /* already have one */
    int fd = accept(l->listen_fd, NULL, NULL);
    if (fd < 0) {
        if (errno != EAGAIN && errno != EWOULDBLOCK) {
            link_warn("accept: %s", strerror(errno));
        }
        return;
    }
    set_nonblocking(fd);
    l->client_fd = fd;
    l->rx_len = 0;
    l->has_unblock = 0;
    l->in_tx = 0;
    l->tick_residue = 0.0;
    l->last_cb2_valid = 0;
    fprintf(stderr, "serial-link: client connected\n");
}

/* Refill the rx buffer from the socket. Non-blocking; never partial-
 * reads more than rx has space for. */
static void try_recv(struct serial_link *l) {
    if (l->client_fd < 0) return;
    int room = RX_BUF_SIZE - l->rx_len;
    if (room <= 0) return;
    ssize_t n = recv(l->client_fd, l->rx + l->rx_len, (size_t)room, 0);
    if (n == 0) {
        fprintf(stderr, "serial-link: client disconnected\n");
        drop_client(l);
        return;
    }
    if (n < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) return;
        link_warn("recv: %s", strerror(errno));
        drop_client(l);
        return;
    }
    l->rx_len += (int)n;
}

/* Try to write `data` to the client. Drops the client on failure
 * (we use this so rarely -- only for ping pongs -- that we don't
 * bother with an outbuf). */
static void try_send(struct serial_link *l, const void *data, size_t n) {
    if (l->client_fd < 0) return;
    /* Best-effort blocking-ish send. On a full kernel buffer this
     * could spin; in practice the client is consuming pongs as fast
     * as we're sending them. */
    ssize_t w = send(l->client_fd, data, n, MSG_NOSIGNAL);
    if (w < 0) {
        if (errno != EAGAIN && errno != EWOULDBLOCK) drop_client(l);
    }
}

/* Convert ns to whole OSC ticks, accumulating the fractional residue
 * so over many bits the rounding doesn't drift. */
static uint64_t ns_to_osc(struct serial_link *l, uint64_t ns) {
    double exact = (double)ns * l->osc_per_ns + l->tick_residue;
    uint64_t whole = (uint64_t)exact;
    l->tick_residue = exact - (double)whole;
    return whole;
}

/* Apply a CB2 level change. The VIA handles edge-IFR via PCR; calling
 * the edge-aware version on every transition is correct, since the
 * boot ROM masks IER.CB2 mid-byte. */
static void apply_cb2(struct serial_link *l, int level,
                      struct bus *bus, struct via_6522_state *via) {
    if (l->last_cb2_valid && l->last_cb2_level == level) return;
    via_6522_set_cb2(via, bus, level ? 1 : 0);
    l->last_cb2_level = level;
    l->last_cb2_valid = 1;
}

/* Check if a full command (opcode + any args) is available in rx.
 * Returns the command length on yes (0 if no, -1 on unknown opcode). */
static int command_len(const struct serial_link *l) {
    if (l->rx_len == 0) return 0;
    uint8_t op = l->rx[0];
    switch (op) {
        case SERIAL_LINK_OP_LOW:
        case SERIAL_LINK_OP_HIGH:
        case SERIAL_LINK_OP_DELAY:
            return l->rx_len >= 9 ? 9 : 0;
        case SERIAL_LINK_OP_RESET_ON:
        case SERIAL_LINK_OP_RESET_OFF:
        case SERIAL_LINK_OP_PING:
        case SERIAL_LINK_OP_TX_START:
        case SERIAL_LINK_OP_TX_END:
            return 1;
        default:
            return -1;
    }
}

/* Read u64 little-endian from p. */
static uint64_t read_u64le(const uint8_t *p) {
    uint64_t v = 0;
    for (int i = 0; i < 8; i++) v |= (uint64_t)p[i] << (i * 8);
    return v;
}

/* Process exactly one queued command (caller has verified command_len
 * returned > 0). */
static void apply_one(struct serial_link *l, int len, uint64_t osc_now,
                      struct bus *bus, struct via_6522_state *via) {
    uint8_t op = l->rx[0];
    static int debug = -1;
    if (debug == -1) debug = getenv("SERIAL_LINK_DEBUG") != NULL;
    if (debug) {
        uint64_t ns = len == 9 ? read_u64le(l->rx + 1) : 0;
        fprintf(stderr, "serial-link: t=%llu op=0x%02X ns=%llu in_tx=%d\n",
                (unsigned long long)osc_now, op, (unsigned long long)ns, l->in_tx);
    }
    switch (op) {
        case SERIAL_LINK_OP_LOW: {
            apply_cb2(l, 0, bus, via);
            uint64_t ns = read_u64le(l->rx + 1);
            l->unblock_at_osc = osc_now + ns_to_osc(l, ns);
            l->has_unblock = 1;
            break;
        }
        case SERIAL_LINK_OP_HIGH: {
            apply_cb2(l, 1, bus, via);
            uint64_t ns = read_u64le(l->rx + 1);
            l->unblock_at_osc = osc_now + ns_to_osc(l, ns);
            l->has_unblock = 1;
            break;
        }
        case SERIAL_LINK_OP_DELAY: {
            uint64_t ns = read_u64le(l->rx + 1);
            l->unblock_at_osc = osc_now + ns_to_osc(l, ns);
            l->has_unblock = 1;
            break;
        }
        case SERIAL_LINK_OP_RESET_ON:
            bus->res = 1;
            break;
        case SERIAL_LINK_OP_RESET_OFF:
            bus->res = 0;
            break;
        case SERIAL_LINK_OP_PING: {
            uint8_t pong = SERIAL_LINK_OP_PING;
            try_send(l, &pong, 1);
            break;
        }
        case SERIAL_LINK_OP_TX_START:
            l->in_tx = 1;
            break;
        case SERIAL_LINK_OP_TX_END:
            l->in_tx = 0;
            break;
        default:
            /* Should never reach here; command_len() already filtered. */
            break;
    }
    /* Consume the command bytes. */
    memmove(l->rx, l->rx + len, (size_t)(l->rx_len - len));
    l->rx_len -= len;
}

void serial_link_poll(struct serial_link *l,
                     uint64_t osc_now,
                     struct bus *bus,
                     struct via_6522_state *via) {
    if (!l) return;
    try_accept(l);
    if (l->client_fd < 0) return;
    try_recv(l);

    /* Apply as many commands as we can: each command runs only once
     * unblock_at_osc has been reached. */
    while (l->rx_len > 0) {
        if (l->has_unblock && osc_now < l->unblock_at_osc) break;
        int len = command_len(l);
        if (len < 0) {
            link_warn("unknown opcode 0x%02X; dropping client", l->rx[0]);
            drop_client(l);
            return;
        }
        if (len == 0) break;   /* partial command; wait for more bytes */
        apply_one(l, len, osc_now, bus, via);
    }
}

int serial_link_should_stall(const struct serial_link *l, uint64_t osc_now) {
    if (!l || l->client_fd < 0 || !l->in_tx) return 0;
    /* Stall when:
     *  - The current command's duration has expired (or we never had
     *    one); AND
     *  - The buffer is empty (no follow-up command queued).
     * Otherwise, OSC may continue to advance up to unblock_at_osc. */
    if (l->has_unblock && osc_now < l->unblock_at_osc) return 0;
    return l->rx_len == 0;
}

int serial_link_needs_repoll(const struct serial_link *l, uint64_t osc_now) {
    /* Cheap branch -- safe to call every bus_step. Triggers a re-poll
     * when we've crossed the current commanded duration inside a TX,
     * so the next command's level/duration loads BEFORE OSC drifts
     * past it. Outside TX, no repoll is needed -- commands are
     * fire-and-forget. */
    if (!l || l->client_fd < 0 || !l->in_tx) return 0;
    return l->has_unblock && osc_now >= l->unblock_at_osc;
}
