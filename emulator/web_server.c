/* Embedded HTTP + WebSocket server for --web (see web_server.h); serves emulator/web/. */
#include "web_server.h"
#include "web_json.h"

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

/* ===== SHA1 (RFC 3174 reference; condensed, public-domain) ===== */
struct sha1_ctx { uint32_t h[5]; uint64_t len; uint8_t buf[64]; int nbuf; };

static uint32_t rol32(uint32_t v, int n) { return (v << n) | (v >> (32 - n)); }

static void sha1_block(struct sha1_ctx *c, const uint8_t *p) {
    uint32_t w[80];
    for (int i = 0; i < 16; i++) {
        w[i] = ((uint32_t)p[i*4] << 24) | ((uint32_t)p[i*4+1] << 16)
             | ((uint32_t)p[i*4+2] << 8) | (uint32_t)p[i*4+3];
    }
    for (int i = 16; i < 80; i++) w[i] = rol32(w[i-3] ^ w[i-8] ^ w[i-14] ^ w[i-16], 1);
    uint32_t a = c->h[0], b = c->h[1], cc = c->h[2], d = c->h[3], e = c->h[4];
    for (int i = 0; i < 80; i++) {
        uint32_t f, k;
        if (i < 20)      { f = (b & cc) | ((~b) & d);             k = 0x5A827999; }
        else if (i < 40) { f = b ^ cc ^ d;                         k = 0x6ED9EBA1; }
        else if (i < 60) { f = (b & cc) | (b & d) | (cc & d);      k = 0x8F1BBCDC; }
        else             { f = b ^ cc ^ d;                         k = 0xCA62C1D6; }
        uint32_t t = rol32(a, 5) + f + e + k + w[i];
        e = d; d = cc; cc = rol32(b, 30); b = a; a = t;
    }
    c->h[0] += a; c->h[1] += b; c->h[2] += cc; c->h[3] += d; c->h[4] += e;
}

static void sha1_init(struct sha1_ctx *c) {
    c->h[0]=0x67452301; c->h[1]=0xEFCDAB89; c->h[2]=0x98BADCFE;
    c->h[3]=0x10325476; c->h[4]=0xC3D2E1F0;
    c->len = 0; c->nbuf = 0;
}
static void sha1_update(struct sha1_ctx *c, const void *data, size_t len) {
    const uint8_t *p = (const uint8_t *)data;
    c->len += len;
    while (len) {
        int take = 64 - c->nbuf;
        if ((size_t)take > len) take = (int)len;
        memcpy(c->buf + c->nbuf, p, (size_t)take);
        c->nbuf += take; p += take; len -= (size_t)take;
        if (c->nbuf == 64) { sha1_block(c, c->buf); c->nbuf = 0; }
    }
}
static void sha1_final(struct sha1_ctx *c, uint8_t out[20]) {
    uint64_t bits = c->len * 8;
    uint8_t pad = 0x80;
    sha1_update(c, &pad, 1);
    uint8_t zero = 0;
    while (c->nbuf != 56) sha1_update(c, &zero, 1);
    uint8_t lenbuf[8];
    for (int i = 0; i < 8; i++) lenbuf[i] = (uint8_t)(bits >> (56 - 8*i));
    sha1_update(c, lenbuf, 8);
    for (int i = 0; i < 5; i++) {
        out[i*4]   = (uint8_t)(c->h[i] >> 24);
        out[i*4+1] = (uint8_t)(c->h[i] >> 16);
        out[i*4+2] = (uint8_t)(c->h[i] >> 8);
        out[i*4+3] = (uint8_t)(c->h[i]);
    }
}

/* ===== base64 ===== */
static void base64_encode(const uint8_t *in, size_t n, char *out) {
    static const char tbl[] =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    size_t i, j = 0;
    for (i = 0; i + 3 <= n; i += 3) {
        uint32_t v = ((uint32_t)in[i] << 16) | ((uint32_t)in[i+1] << 8) | in[i+2];
        out[j++] = tbl[(v >> 18) & 0x3F];
        out[j++] = tbl[(v >> 12) & 0x3F];
        out[j++] = tbl[(v >> 6) & 0x3F];
        out[j++] = tbl[v & 0x3F];
    }
    if (i < n) {
        uint32_t v = (uint32_t)in[i] << 16;
        if (i + 1 < n) v |= (uint32_t)in[i+1] << 8;
        out[j++] = tbl[(v >> 18) & 0x3F];
        out[j++] = tbl[(v >> 12) & 0x3F];
        out[j++] = (i + 1 < n) ? tbl[(v >> 6) & 0x3F] : '=';
        out[j++] = '=';
    }
    out[j] = '\0';
}

/* ===== Per-client state ===== */
enum client_state {
    CS_FREE = 0,
    CS_READING_HTTP,
    CS_WS_OPEN,
};

#define CLIENT_INBUF_SIZE  (8 * 1024)
#define CLIENT_OUTBUF_SIZE (64 * 1024)

struct client {
    int fd;
    enum client_state state;
    char inbuf[CLIENT_INBUF_SIZE];
    int  inlen;
    char outbuf[CLIENT_OUTBUF_SIZE];
    int  outlen;
    int  audio_init_sent;            /* 1 once we've sent the audio_init JSON */
};

#define EVENT_QUEUE_SIZE 32
#define AUDIO_RING_CAPACITY 8192  /* int16 samples; ~0.37s @ 22050 Hz */

struct web_server {
    int listen_fd;
    int port;
    char web_root[1024];
    char machine[32];               /* log prefix; the page at / is <machine>.html */
    struct client clients[WEB_MAX_CLIENTS];

    /* FIFO of pending client-originated events. */
    struct web_event events[EVENT_QUEUE_SIZE];
    int evt_head, evt_tail;

    /* Server-side audio ring: filled by web_server_audio_tap() from
     * the audio module's emit_sample(); drained by
     * web_server_flush_audio() into a single WS binary frame. */
    int16_t audio_ring[AUDIO_RING_CAPACITY];
    int audio_head, audio_tail;
    int audio_sample_rate;          /* announced to new clients via init msg */
};

/* ===== Logging ===== */
static void web_warn(const struct web_server *srv, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    fprintf(stderr, "%s-web: ", srv->machine);
    vfprintf(stderr, fmt, ap);
    fprintf(stderr, "\n");
    va_end(ap);
}

/* ===== Web root resolution ===== */
static int dir_exists(const char *p) {
    struct stat st;
    return stat(p, &st) == 0 && S_ISDIR(st.st_mode);
}

static void resolve_web_root(const char *requested, char *out, size_t n) {
    if (requested && *requested) {
        snprintf(out, n, "%s", requested);
        return;
    }
    /* Try <dir-of-argv0>/web (binary is .../emulator/emulator.out so
     * this lands on .../emulator/web). Falls through to CWD-relative
     * candidates below if missing. `cand` is sized 16 bytes larger
     * than `exe` so gcc's -Wformat-truncation check is satisfied even
     * when the readlink path fills exe to its boundary. */
    char exe[1024];
    char cand[1040];
    ssize_t r = readlink("/proc/self/exe", exe, sizeof(exe) - 1);
    if (r > 0) {
        exe[r] = '\0';
        char *slash = strrchr(exe, '/');
        if (slash) {
            *slash = '\0';
            snprintf(cand, sizeof(cand), "%s/web", exe);
            if (dir_exists(cand)) { snprintf(out, n, "%s", cand); return; }
        }
    }
    /* Fallback to CWD. */
    if (dir_exists("emulator/web")) { snprintf(out, n, "emulator/web"); return; }
    if (dir_exists("web"))          { snprintf(out, n, "web");          return; }
    snprintf(out, n, "emulator/web");  /* will fail at open time */
}

/* ===== Socket helpers ===== */
static int set_nonblocking(int fd) {
    int flags = fcntl(fd, F_GETFL, 0);
    if (flags < 0) return -1;
    return fcntl(fd, F_SETFL, flags | O_NONBLOCK);
}

static void close_client(struct client *c) {
    if (c->fd >= 0) close(c->fd);
    c->fd = -1;
    c->state = CS_FREE;
    c->inlen = 0;
    c->outlen = 0;
    c->audio_init_sent = 0;
}

/* Try to drain outbuf to the wire (best-effort, non-blocking). */
static void flush_outbuf(struct client *c) {
    while (c->outlen > 0) {
        ssize_t n = send(c->fd, c->outbuf, (size_t)c->outlen, MSG_NOSIGNAL);
        if (n <= 0) {
            if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return;
            close_client(c);
            return;
        }
        memmove(c->outbuf, c->outbuf + n, (size_t)(c->outlen - n));
        c->outlen -= (int)n;
    }
}

static void queue_bytes(struct client *c, const void *data, int n) {
    if (c->outlen + n > CLIENT_OUTBUF_SIZE) {
        /* Outbuf overflow -- drop the connection rather than truncate. */
        close_client(c);
        return;
    }
    memcpy(c->outbuf + c->outlen, data, (size_t)n);
    c->outlen += n;
}

/* ===== HTTP serving ===== */
static const char *mime_for(const char *path) {
    const char *dot = strrchr(path, '.');
    if (!dot) return "application/octet-stream";
    if (strcmp(dot, ".html") == 0) return "text/html; charset=utf-8";
    if (strcmp(dot, ".css")  == 0) return "text/css; charset=utf-8";
    if (strcmp(dot, ".js")   == 0) return "application/javascript; charset=utf-8";
    if (strcmp(dot, ".svg")  == 0) return "image/svg+xml";
    if (strcmp(dot, ".ico")  == 0) return "image/x-icon";
    return "application/octet-stream";
}

static void send_simple(struct client *c, int code, const char *status,
                        const char *body) {
    char hdr[256];
    int blen = body ? (int)strlen(body) : 0;
    int n = snprintf(hdr, sizeof(hdr),
        "HTTP/1.1 %d %s\r\n"
        "Content-Type: text/plain\r\n"
        "Content-Length: %d\r\n"
        "Connection: close\r\n\r\n",
        code, status, blen);
    queue_bytes(c, hdr, n);
    if (blen) queue_bytes(c, body, blen);
}

static void send_file(struct client *c, const struct web_server *srv, const char *path) {
    /* Sanitize. The only files we serve (<machine>.html, board.css and
     * the scripts) need none of: parent-dir navigation, double slashes,
     * or any URL-percent-encoding. Rejecting any '%' in the path
     * forecloses the "encode .. as %2e%2e" bypass class without us
     * having to write a URL decoder. If a future asset needs %20 etc.
     * in its name, add a proper decoder here AND keep the '..' /
     * '//' check on the decoded form. */
    if (path[0] != '/'
        || strstr(path, "..")
        || strstr(path, "//")
        || strchr(path, '%')) {
        send_simple(c, 400, "Bad Request", "bad path\n");
        return;
    }
    /* Default root -> the machine's page */
    char page[48];
    snprintf(page, sizeof(page), "/%s.html", srv->machine);
    const char *rel = (strcmp(path, "/") == 0) ? page : path;
    char full[2048];
    if (snprintf(full, sizeof(full), "%s%s", srv->web_root, rel) >= (int)sizeof(full)) {
        send_simple(c, 400, "Bad Request", "path too long\n");
        return;
    }
    FILE *f = fopen(full, "rb");
    if (!f) {
        send_simple(c, 404, "Not Found", "file not found\n");
        return;
    }
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (sz < 0 || sz > 1024 * 1024) {  /* 1 MiB cap on a single file */
        fclose(f);
        send_simple(c, 500, "Internal Server Error", "file too large\n");
        return;
    }
    char hdr[256];
    int n = snprintf(hdr, sizeof(hdr),
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: %s\r\n"
        "Content-Length: %ld\r\n"
        "Cache-Control: no-cache\r\n"
        "Connection: close\r\n\r\n",
        mime_for(rel), sz);
    queue_bytes(c, hdr, n);
    if (c->outlen + sz > CLIENT_OUTBUF_SIZE) {
        fclose(f);
        send_simple(c, 500, "Internal Server Error", "outbuf overflow\n");
        return;
    }
    if (fread(c->outbuf + c->outlen, 1, (size_t)sz, f) != (size_t)sz) {
        fclose(f);
        close_client(c);
        return;
    }
    c->outlen += (int)sz;
    fclose(f);
}

/* WebSocket handshake: compute Sec-WebSocket-Accept and emit 101. */
static void do_ws_handshake(struct client *c, const char *key) {
    static const char magic[] = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
    struct sha1_ctx h;
    sha1_init(&h);
    sha1_update(&h, key, strlen(key));
    sha1_update(&h, magic, sizeof(magic) - 1);
    uint8_t digest[20];
    sha1_final(&h, digest);
    char b64[64];
    base64_encode(digest, 20, b64);

    char resp[256];
    int n = snprintf(resp, sizeof(resp),
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Accept: %s\r\n\r\n",
        b64);
    queue_bytes(c, resp, n);
    c->state = CS_WS_OPEN;
}

/* Parse a Header: value out of an HTTP request that's been NUL-
 * terminated. Returns pointer to (whitespace-stripped) value, or NULL. */
static const char *find_header(const char *req, const char *name, char *tmp, size_t tmpsz) {
    /* Tokens are \r\n separated; case-insensitive name match. */
    const char *p = req;
    size_t nlen = strlen(name);
    while (*p) {
        const char *eol = strstr(p, "\r\n");
        if (!eol) break;
        if ((size_t)(eol - p) > nlen + 1
            && strncasecmp(p, name, nlen) == 0
            && p[nlen] == ':') {
            const char *v = p + nlen + 1;
            while (*v == ' ' || *v == '\t') v++;
            size_t vlen = (size_t)(eol - v);
            if (vlen >= tmpsz) vlen = tmpsz - 1;
            memcpy(tmp, v, vlen);
            tmp[vlen] = '\0';
            return tmp;
        }
        p = eol + 2;
    }
    return NULL;
}

/* Returns 1 if request fully read (terminated by \r\n\r\n). */
static int try_complete_request(struct client *c, const struct web_server *srv) {
    /* Look for end-of-headers. */
    char *end = NULL;
    if (c->inlen >= 4) {
        for (int i = 0; i <= c->inlen - 4; i++) {
            if (c->inbuf[i] == '\r' && c->inbuf[i+1] == '\n'
                && c->inbuf[i+2] == '\r' && c->inbuf[i+3] == '\n') {
                end = c->inbuf + i;
                break;
            }
        }
    }
    if (!end) {
        if (c->inlen >= CLIENT_INBUF_SIZE - 1) {
            send_simple(c, 400, "Bad Request", "header too long\n");
            close_client(c);
        }
        return 0;
    }
    *end = '\0';
    /* Parse request line: METHOD PATH HTTP/1.1 */
    char method[16] = {0}, path[1024] = {0};
    int parsed = sscanf(c->inbuf, "%15s %1023s", method, path);
    if (parsed != 2 || strcmp(method, "GET") != 0) {
        send_simple(c, 400, "Bad Request", "only GET supported\n");
        return 1;
    }
    /* WebSocket upgrade? */
    char tmp[256];
    const char *up = find_header(c->inbuf, "Upgrade", tmp, sizeof(tmp));
    if (up && strcasecmp(up, "websocket") == 0) {
        char keytmp[128];
        const char *key = find_header(c->inbuf, "Sec-WebSocket-Key", keytmp, sizeof(keytmp));
        if (!key) {
            send_simple(c, 400, "Bad Request", "missing WS key\n");
            return 1;
        }
        do_ws_handshake(c, key);
        c->inlen = 0;
        return 1;
    }
    send_file(c, srv, path);
    return 1;
}

/* ===== WebSocket framing ===== */
/* Send a text frame. Payload length must fit; we cap at 64 KiB. */
static void ws_send_text(struct client *c, const char *data, size_t n) {
    if (c->state != CS_WS_OPEN) return;
    uint8_t hdr[10];
    int hlen;
    if (n <= 125) {
        hdr[0] = 0x81;          /* FIN + text */
        hdr[1] = (uint8_t)n;
        hlen = 2;
    } else if (n <= 0xFFFF) {
        hdr[0] = 0x81;
        hdr[1] = 126;
        hdr[2] = (uint8_t)(n >> 8);
        hdr[3] = (uint8_t)n;
        hlen = 4;
    } else {
        /* Payload too large for our cap. */
        close_client(c);
        return;
    }
    queue_bytes(c, hdr, hlen);
    queue_bytes(c, data, (int)n);
}

/* Try to parse one frame from c->inbuf; returns >0 frame length consumed,
 * 0 if more data needed, -1 on protocol error. On a text frame fills
 * *out_text / *out_textlen pointing into c->inbuf (caller must consume
 * before the next read overwrites). */
static int ws_parse_frame(struct client *c, char **out_text, int *out_textlen) {
    if (c->inlen < 2) return 0;
    uint8_t b0 = (uint8_t)c->inbuf[0];
    uint8_t b1 = (uint8_t)c->inbuf[1];
    int opcode = b0 & 0x0F;
    int masked = (b1 & 0x80) != 0;
    uint64_t plen = b1 & 0x7F;
    int hdr_len = 2;
    if (plen == 126) {
        if (c->inlen < 4) return 0;
        plen = ((uint64_t)(uint8_t)c->inbuf[2] << 8) | (uint8_t)c->inbuf[3];
        hdr_len = 4;
    } else if (plen == 127) {
        /* Don't bother: our protocol uses short frames only. */
        return -1;
    }
    /* RFC 6455: client frames MUST be masked. */
    if (!masked) return -1;
    if (c->inlen < hdr_len + 4 + (int)plen) return 0;
    if (plen > 8192) return -1;  /* sanity cap on client frames */
    uint8_t mask[4];
    memcpy(mask, c->inbuf + hdr_len, 4);
    char *payload = c->inbuf + hdr_len + 4;
    for (uint64_t i = 0; i < plen; i++) payload[i] ^= mask[i & 3];

    int total = hdr_len + 4 + (int)plen;
    if (opcode == 0x8) return -1;          /* close */
    if (opcode == 0x9) {                   /* ping -> reply pong, drop body */
        uint8_t pong[2] = { 0x8A, 0 };
        queue_bytes(c, pong, 2);
        return total;
    }
    if (opcode == 0xA) return total;       /* pong (ignore) */
    if (opcode != 0x1) return -1;          /* only text supported */
    *out_text = payload;
    *out_textlen = (int)plen;
    return total;
}

/* ===== Event queue ===== */
static void queue_event(struct web_server *srv,
                         enum web_event_type t, int btn_down) {
    int next = (srv->evt_tail + 1) % EVENT_QUEUE_SIZE;
    if (next == srv->evt_head) {
        /* Queue full -- drop oldest. */
        srv->evt_head = (srv->evt_head + 1) % EVENT_QUEUE_SIZE;
    }
    srv->events[srv->evt_tail].type = t;
    srv->events[srv->evt_tail].button_down = btn_down;
    srv->evt_tail = next;
}

static void handle_text_msg(struct web_server *srv,
                             const char *txt, int len) {
    /* Single-pass structured parse; see web_json.h for the security
     * guarantees vs. the original "find substring" helpers. */
    struct web_json_msg msg;
    if (web_json_parse(txt, len, &msg) != 0) return;
    if (msg.has_type && strcmp(msg.type, "button") == 0 && msg.has_down) {
        queue_event(srv, WEB_EVT_BUTTON, msg.down ? 1 : 0);
    } else if (msg.has_type && strcmp(msg.type, "reset") == 0) {
        /* Reset is a one-shot (button_down field unused). */
        queue_event(srv, WEB_EVT_RESET, 0);
    }
}

/* ===== Server lifecycle ===== */
struct web_server *web_server_start(const char *machine, int port,
                                    const char *bind_addr, const char *web_root) {
    /* Ignore SIGPIPE; we handle write errors per-connection. */
    signal(SIGPIPE, SIG_IGN);

    struct web_server *srv = calloc(1, sizeof(*srv));
    if (!srv) return NULL;
    srv->listen_fd = -1;
    snprintf(srv->machine, sizeof(srv->machine), "%s", machine);
    for (int i = 0; i < WEB_MAX_CLIENTS; i++) srv->clients[i].fd = -1;
    resolve_web_root(web_root, srv->web_root, sizeof(srv->web_root));

    /* Default to loopback. inet_aton accepts "0.0.0.0" / "1.2.3.4". */
    struct in_addr ba;
    ba.s_addr = htonl(INADDR_LOOPBACK);
    int loopback_only = 1;
    if (bind_addr && *bind_addr) {
        if (inet_aton(bind_addr, &ba) == 0) {
            web_warn(srv, "bad --web-bind address '%s' (expected IPv4 dotted-quad)",
                     bind_addr);
            free(srv);
            return NULL;
        }
        loopback_only = (ba.s_addr == htonl(INADDR_LOOPBACK));
    }

    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) { web_warn(srv, "socket: %s", strerror(errno)); free(srv); return NULL; }
    int one = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr   = ba;
    addr.sin_port   = htons((uint16_t)port);
    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        web_warn(srv, "bind %s:%d: %s",
                 bind_addr && *bind_addr ? bind_addr : "127.0.0.1",
                 port, strerror(errno));
        close(fd); free(srv); return NULL;
    }
    if (listen(fd, 4) < 0) {
        web_warn(srv, "listen: %s", strerror(errno));
        close(fd); free(srv); return NULL;
    }
    socklen_t alen = sizeof(addr);
    getsockname(fd, (struct sockaddr *)&addr, &alen);
    srv->port = ntohs(addr.sin_port);
    set_nonblocking(fd);
    srv->listen_fd = fd;
    /* Display string for the listen banner: loopback shows
     * "127.0.0.1"; everything else (incl. 0.0.0.0) shows the actual
     * bind address so the user knows what's exposed. */
    char shown[INET_ADDRSTRLEN];
    if (loopback_only) {
        snprintf(shown, sizeof(shown), "127.0.0.1");
    } else {
        inet_ntop(AF_INET, &ba, shown, sizeof(shown));
    }
    fprintf(stderr, "%s-web: listening on http://%s:%d/ "
                    "(web_root=%s)\n",
            srv->machine, shown, srv->port, srv->web_root);
    if (!loopback_only) {
        web_warn(srv, "WARNING: bound to %s -- the board's controls "
                 "and audio stream are reachable from anyone who can "
                 "connect to this port. Use --web-bind 127.0.0.1 to "
                 "restrict to localhost.", shown);
    }
    return srv;
}

void web_server_stop(struct web_server *srv) {
    if (!srv) return;
    if (srv->listen_fd >= 0) close(srv->listen_fd);
    for (int i = 0; i < WEB_MAX_CLIENTS; i++) close_client(&srv->clients[i]);
    free(srv);
}

int web_server_client_count(const struct web_server *srv) {
    int n = 0;
    for (int i = 0; i < WEB_MAX_CLIENTS; i++) {
        if (srv->clients[i].state == CS_WS_OPEN) n++;
    }
    return n;
}

int web_server_port(const struct web_server *srv) {
    return srv ? srv->port : 0;
}

/* Accept any pending connections into a free client slot. */
static void try_accept(struct web_server *srv) {
    for (;;) {
        int fd = accept(srv->listen_fd, NULL, NULL);
        if (fd < 0) {
            if (errno != EAGAIN && errno != EWOULDBLOCK) {
                web_warn(srv, "accept: %s", strerror(errno));
            }
            return;
        }
        set_nonblocking(fd);
        /* TCP_NODELAY: state snapshots are small and frequent. */
        int one = 1;
        setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));
        int slot = -1;
        for (int i = 0; i < WEB_MAX_CLIENTS; i++) {
            if (srv->clients[i].state == CS_FREE) { slot = i; break; }
        }
        if (slot < 0) {
            /* Cap reached. */
            const char busy[] =
                "HTTP/1.1 503 Service Unavailable\r\n"
                "Content-Length: 0\r\n"
                "Connection: close\r\n\r\n";
            send(fd, busy, sizeof(busy) - 1, MSG_NOSIGNAL);
            close(fd);
            continue;
        }
        srv->clients[slot].fd = fd;
        srv->clients[slot].state = CS_READING_HTTP;
        srv->clients[slot].inlen = 0;
        srv->clients[slot].outlen = 0;
    }
}

static void read_from_client(struct web_server *srv, struct client *c) {
    if (c->state == CS_FREE) return;
    int room = CLIENT_INBUF_SIZE - c->inlen;
    if (room <= 0) { close_client(c); return; }
    ssize_t n = recv(c->fd, c->inbuf + c->inlen, (size_t)room, 0);
    if (n == 0) { close_client(c); return; }
    if (n < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) return;
        close_client(c);
        return;
    }
    c->inlen += (int)n;

    if (c->state == CS_READING_HTTP) {
        if (try_complete_request(c, srv)) {
            /* HTTP done: either upgraded to WS or queued response + will close. */
            flush_outbuf(c);
            if (c->state != CS_WS_OPEN) {
                /* Plain HTTP: close after the response drains. */
                if (c->outlen == 0) close_client(c);
            }
        }
        return;
    }

    /* WS_OPEN: parse one or more frames. */
    while (c->state == CS_WS_OPEN && c->inlen > 0) {
        char *txt = NULL;
        int txtlen = 0;
        int consumed = ws_parse_frame(c, &txt, &txtlen);
        if (consumed == 0) return;
        if (consumed < 0) { close_client(c); return; }
        if (txt) {
            handle_text_msg(srv, txt, txtlen);
            txt = NULL;
        }
        memmove(c->inbuf, c->inbuf + consumed, (size_t)(c->inlen - consumed));
        c->inlen -= consumed;
    }
}

int web_server_poll(struct web_server *srv,
                     struct web_event *out_event) {
    out_event->type = WEB_EVT_NONE;
    out_event->button_down = 0;
    if (!srv) return 0;

    fd_set rfds;
    FD_ZERO(&rfds);
    int maxfd = srv->listen_fd;
    FD_SET(srv->listen_fd, &rfds);
    for (int i = 0; i < WEB_MAX_CLIENTS; i++) {
        if (srv->clients[i].state != CS_FREE) {
            FD_SET(srv->clients[i].fd, &rfds);
            if (srv->clients[i].fd > maxfd) maxfd = srv->clients[i].fd;
        }
    }
    struct timeval tv = {0, 0};
    int rc = select(maxfd + 1, &rfds, NULL, NULL, &tv);
    if (rc > 0) {
        if (FD_ISSET(srv->listen_fd, &rfds)) try_accept(srv);
        for (int i = 0; i < WEB_MAX_CLIENTS; i++) {
            if (srv->clients[i].state != CS_FREE
                && FD_ISSET(srv->clients[i].fd, &rfds)) {
                read_from_client(srv, &srv->clients[i]);
            }
        }
    }
    /* Flush any pending outbufs (e.g. broadcast queued state). */
    for (int i = 0; i < WEB_MAX_CLIENTS; i++) {
        if (srv->clients[i].state != CS_FREE) flush_outbuf(&srv->clients[i]);
    }
    /* Drain one event from the queue. */
    if (srv->evt_head != srv->evt_tail) {
        *out_event = srv->events[srv->evt_head];
        srv->evt_head = (srv->evt_head + 1) % EVENT_QUEUE_SIZE;
    }
    return 0;
}

/* ===== Snapshot serialization ===== */
/* Append-format helper; bumps *pos. Returns 0 on success, -1 on overflow. */
static int sj_printf(char *buf, int cap, int *pos, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(buf + *pos, (size_t)(cap - *pos), fmt, ap);
    va_end(ap);
    if (n < 0 || *pos + n >= cap) return -1;
    *pos += n;
    return 0;
}

void web_server_broadcast(struct web_server *srv,
                           const struct web_snapshot *s) {
    if (!srv) return;
    int any = 0;
    for (int i = 0; i < WEB_MAX_CLIENTS; i++)
        if (srv->clients[i].state == CS_WS_OPEN) { any = 1; break; }
    if (!any) return;

    char json[8192];
    int pos = 0;
    int rows = s->lcd_rows, cols = s->lcd_cols;
    int ddram_n = rows * cols;
    if (ddram_n > (int)sizeof(s->ddram_visible)) ddram_n = (int)sizeof(s->ddram_visible);

    if (sj_printf(json, sizeof(json), &pos,
        "{\"lcd\":{\"rows\":%d,\"cols\":%d,\"ddram\":[", rows, cols)) return;
    for (int i = 0; i < ddram_n; i++) {
        if (sj_printf(json, sizeof(json), &pos, "%s%u",
                      i ? "," : "", (unsigned)s->ddram_visible[i])) return;
    }
    if (sj_printf(json, sizeof(json), &pos, "],\"cgram\":[")) return;
    for (int i = 0; i < 64; i++) {
        if (sj_printf(json, sizeof(json), &pos, "%s%u",
                      i ? "," : "", (unsigned)(s->cgram[i] & 0x1F))) return;
    }
    if (sj_printf(json, sizeof(json), &pos,
        "],\"cur\":[%d,%d],\"cur_on\":%d,\"blink_on\":%d,\"disp_on\":%d,"
        "\"f5x10\":%d,\"panel_rows\":%d,\"panel_5x10\":%d},"
        "\"btn\":%d,"
        "\"porta\":%u,\"portb\":%u,\"ddra\":%u,\"ddrb\":%u,"
        "\"osc\":%llu,\"cpu\":%llu,\"pc\":%u,\"irq\":%d,\"stp\":%d,\"leds\":[",
        s->cursor_row, s->cursor_col, s->cursor_on, s->blink_on, s->display_on,
        s->font_5x10, s->panel_rows, s->panel_5x10,
        s->button_pressed,
        (unsigned)s->porta, (unsigned)s->portb,
        (unsigned)s->ddra, (unsigned)s->ddrb,
        s->osc_ticks, s->cpu_cycles, (unsigned)s->pc, s->irq, s->stopped)) return;
    for (int i = 0; i < s->n_leds && i < WEB_MAX_LEDS; i++) {
        if (sj_printf(json, sizeof(json), &pos, "%s%d", i ? "," : "", s->leds[i] ? 1 : 0)) return;
    }
    if (sj_printf(json, sizeof(json), &pos, "]}")) return;

    char initmsg[64];
    int initlen = 0;
    if (srv->audio_sample_rate > 0) {
        initlen = snprintf(initmsg, sizeof(initmsg),
            "{\"type\":\"audio_init\",\"rate\":%d}",
            srv->audio_sample_rate);
    }

    for (int i = 0; i < WEB_MAX_CLIENTS; i++) {
        struct client *c = &srv->clients[i];
        if (c->state != CS_WS_OPEN) continue;
        if (initlen > 0 && !c->audio_init_sent) {
            ws_send_text(c, initmsg, (size_t)initlen);
            c->audio_init_sent = 1;
        }
        ws_send_text(c, json, (size_t)pos);
        flush_outbuf(c);
    }
}

/* ===== Audio ===== */

/* Send a binary frame (FIN+binary, no masking; we're the server). */
static void ws_send_binary(struct client *c, const uint8_t *data, size_t n) {
    if (c->state != CS_WS_OPEN) return;
    uint8_t hdr[10];
    int hlen;
    if (n <= 125) {
        hdr[0] = 0x82;          /* FIN + binary */
        hdr[1] = (uint8_t)n;
        hlen = 2;
    } else if (n <= 0xFFFF) {
        hdr[0] = 0x82;
        hdr[1] = 126;
        hdr[2] = (uint8_t)(n >> 8);
        hdr[3] = (uint8_t)n;
        hlen = 4;
    } else {
        close_client(c);
        return;
    }
    queue_bytes(c, hdr, hlen);
    queue_bytes(c, data, (int)n);
}

void web_server_audio_tap(void *user, int16_t sample) {
    struct web_server *srv = (struct web_server *)user;
    if (!srv) return;
    int next = (srv->audio_tail + 1) % AUDIO_RING_CAPACITY;
    if (next == srv->audio_head) {
        /* Overflow -- drop the oldest. The ring is sized for ~370 ms
         * which is far more than the snapshot interval, so this only
         * fires when there are no clients (and even then it's harmless). */
        srv->audio_head = (srv->audio_head + 1) % AUDIO_RING_CAPACITY;
    }
    srv->audio_ring[srv->audio_tail] = sample;
    srv->audio_tail = next;
}

void web_server_send_audio_rate(struct web_server *srv,
                                 int sample_rate) {
    if (!srv) return;
    srv->audio_sample_rate = sample_rate;
    /* Sent as a text frame so the client knows the rate before the
     * first binary audio frame arrives. */
    char msg[64];
    int n = snprintf(msg, sizeof(msg),
                     "{\"type\":\"audio_init\",\"rate\":%d}", sample_rate);
    for (int i = 0; i < WEB_MAX_CLIENTS; i++) {
        if (srv->clients[i].state == CS_WS_OPEN) {
            ws_send_text(&srv->clients[i], msg, (size_t)n);
            flush_outbuf(&srv->clients[i]);
        }
    }
}

void web_server_broadcast_audio(struct web_server *srv,
                                 const int16_t *samples, int count) {
    if (!srv || count <= 0) return;
    /* Frame format: [0x01 = audio tag][LE int16 samples...].
     * We cap a single frame at 4 KiB of samples (2000 int16) to stay
     * comfortably under our 64 KiB server send cap. */
    if (count > 2000) count = 2000;
    uint8_t buf[1 + 2 * 2000];
    buf[0] = 0x01;
    for (int i = 0; i < count; i++) {
        int16_t v = samples[i];
        buf[1 + i * 2]     = (uint8_t)(v & 0xFF);
        buf[1 + i * 2 + 1] = (uint8_t)((uint16_t)v >> 8);
    }
    size_t plen = 1 + 2 * (size_t)count;
    int any = 0;
    for (int i = 0; i < WEB_MAX_CLIENTS; i++)
        if (srv->clients[i].state == CS_WS_OPEN) { any = 1; break; }
    if (!any) return;
    for (int i = 0; i < WEB_MAX_CLIENTS; i++) {
        if (srv->clients[i].state == CS_WS_OPEN) {
            ws_send_binary(&srv->clients[i], buf, plen);
            flush_outbuf(&srv->clients[i]);
        }
    }
}

void web_server_flush_audio(struct web_server *srv) {
    if (!srv) return;
    /* No clients? Drop the queue so it doesn't fill up forever. */
    int any = 0;
    for (int i = 0; i < WEB_MAX_CLIENTS; i++)
        if (srv->clients[i].state == CS_WS_OPEN) { any = 1; break; }
    if (!any) { srv->audio_head = srv->audio_tail; return; }

    /* Drain the ring into one or more frames. ws_send_binary caps at
     * 2000 samples per frame; loop until empty. */
    while (srv->audio_head != srv->audio_tail) {
        int n = 0;
        int16_t batch[2000];
        while (srv->audio_head != srv->audio_tail && n < 2000) {
            batch[n++] = srv->audio_ring[srv->audio_head];
            srv->audio_head = (srv->audio_head + 1) % AUDIO_RING_CAPACITY;
        }
        web_server_broadcast_audio(srv, batch, n);
    }
}
