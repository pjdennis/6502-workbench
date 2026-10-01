#ifndef EMULATOR_WENDY2C_WEB_H
#define EMULATOR_WENDY2C_WEB_H

#include <stdint.h>

/* Tiny embedded HTTP + WebSocket server for the wendy2c live web UI.
 *
 * Design:
 *   - Single-threaded, driven by emu_run_wendy2c_web's batch loop.
 *   - Non-blocking listening socket + per-client fds.
 *   - HTTP: serves a few static files from web_root (index.html, css, js).
 *   - WebSocket: text frames only (JSON state snapshots + commands).
 *     Frames up to 64 KiB; longer payloads close the connection.
 *
 * State direction:
 *   server -> client: wendy2c_web_broadcast() pushes a JSON snapshot
 *   client -> server: wendy2c_web_poll() returns queued events
 *
 * Up to WENDY2C_WEB_MAX_CLIENTS concurrent WS clients. New connects
 * past the cap get HTTP 503. */

#define WENDY2C_WEB_MAX_CLIENTS 4

struct wendy2c_web_server;

/* Snapshot of everything the UI renders. Filled by the run loop and
 * passed to wendy2c_web_broadcast(). The DDRAM buffer is rows*cols
 * raw bytes (e.g. character codes 0x00..0x07 = CGRAM); the JS side
 * picks the glyph based on these. */
struct wendy2c_web_snapshot {
    int lcd_rows, lcd_cols;
    uint8_t ddram_visible[80];   /* rows*cols (16*4 max) raw bytes */
    uint8_t cgram[64];           /* 8 chars x 8 rows; low 5 bits = pixels */
    int cursor_row, cursor_col;
    int cursor_on, blink_on, display_on;
    int font_5x10;               /* 1 = HD44780 F-bit set; render glyphs as 5x10 */
    int panel_rows;              /* physical-panel row count (1 or 2) */
    int panel_5x10;              /* 1 = render glyphs as 5x10 cells with a 1-pixel
                                  *     cursor-row gap (16x1-5x10 module).
                                  * 0 = render as 5x8 cells with cursor row directly
                                  *     below (standard 16x2 module). */

    int morse_led;
    int control_led;
    int button_pressed;

    uint8_t porta, portb;
    uint8_t ddra, ddrb;

    unsigned long long osc_ticks;
    unsigned long long cpu_cycles;
    uint16_t pc;
    int irq;
    int stopped;                 /* 1 if CPU halted on STP */
};

/* Events the client sends back. WENDY2C_WEB_EVT_NONE if nothing queued. */
enum wendy2c_web_event_type {
    WENDY2C_WEB_EVT_NONE = 0,
    WENDY2C_WEB_EVT_BUTTON,
    WENDY2C_WEB_EVT_RESET,
};

struct wendy2c_web_event {
    enum wendy2c_web_event_type type;
    int button_down;             /* 0 or 1 when type == BUTTON */
};

/* Start listening on the given TCP port. Returns NULL on error
 * (diagnostic printed to stderr). `bind_addr` is the IPv4 address to
 * bind to (NULL or "127.0.0.1" = loopback only; "0.0.0.0" = all
 * interfaces, reachable from the LAN). `web_root` is the directory
 * holding index.html / wendy2c.css / wendy2c.js; pass NULL to fall
 * back to "<dirname(argv[0])>/web" via realpath. */
struct wendy2c_web_server *wendy2c_web_start(int port, const char *bind_addr,
                                              const char *web_root);

/* Service network I/O. Accepts any new connections, finishes any
 * pending HTTP requests / WS handshakes, and drains incoming WS
 * frames. Fills *out_event with at most one queued client event per
 * call (FIFO across all clients). Returns 0 on success. */
int wendy2c_web_poll(struct wendy2c_web_server *srv,
                     struct wendy2c_web_event *out_event);

/* Push the snapshot to every connected WS client as a single JSON
 * text frame. Silent on send errors (the connection is just dropped). */
void wendy2c_web_broadcast(struct wendy2c_web_server *srv,
                           const struct wendy2c_web_snapshot *snap);

/* Push a sample-rate header to clients (sent once after each new WS
 * upgrade so the JS audio decoder knows what rate to feed WebAudio). */
void wendy2c_web_send_audio_rate(struct wendy2c_web_server *srv,
                                 int sample_rate);

/* Push a chunk of int16 PCM samples to every connected WS client as a
 * binary frame (mono, little-endian, signed 16-bit). The first byte of
 * the payload is a frame-type tag (0x01 = audio); the remainder is raw
 * sample bytes. Silent on send errors. */
void wendy2c_web_broadcast_audio(struct wendy2c_web_server *srv,
                                 const int16_t *samples, int count);

/* Server-side audio-tap glue: queues a single sample into an internal
 * ring buffer. Pass as the audio_set_tap() callback (with srv as the
 * user pointer). The run loop drains the buffer into a single WS
 * binary frame at each snapshot tick. */
void wendy2c_web_audio_tap(void *user, int16_t sample);

/* Drain queued samples into a binary frame to all clients. Caller's
 * responsibility (the run loop calls this every ~33 ms). */
void wendy2c_web_flush_audio(struct wendy2c_web_server *srv);

/* Number of currently-connected WebSocket clients. */
int wendy2c_web_client_count(const struct wendy2c_web_server *srv);

/* The port we actually bound to (handy when 0 was requested for an
 * ephemeral port; we still return the kernel-assigned one). */
int wendy2c_web_port(const struct wendy2c_web_server *srv);

void wendy2c_web_stop(struct wendy2c_web_server *srv);

#endif
