/* web_run: the --web run loop the board machines share (see web_run.h). */
#include "web_run.h"

#include <string.h>
#include <time.h>

#include "cpu_core.h"
#include "emu_run.h"
#include "pace.h"
#include "tty_alt_screen.h"

#define SNAP_NS (33 * 1000 * 1000L)     /* ~30 fps */

static void broadcast(struct web_server *srv, const struct web_machine *m) {
    struct web_snapshot snap;
    memset(&snap, 0, sizeof(snap));
    const struct lcd_hd44780_state *lcd = m->lcd;
    snap.lcd_rows = lcd->rows;
    snap.lcd_cols = lcd->cols;
    int n = lcd->rows * lcd->cols;
    if (n > (int)sizeof(snap.ddram_visible)) n = (int)sizeof(snap.ddram_visible);
    uint8_t visible[LCD_DDRAM_SIZE];
    lcd_hd44780_visible_bytes(lcd, visible);
    memcpy(snap.ddram_visible, visible, (size_t)n);
    memcpy(snap.cgram, lcd->cgram, sizeof(snap.cgram));
    lcd_hd44780_cursor(lcd, &snap.cursor_row, &snap.cursor_col);
    snap.cursor_on  = lcd->cursor_on;
    snap.blink_on   = lcd->blink_on;
    snap.display_on = lcd->display_on;
    snap.font_5x10  = lcd->font_5x10;
    snap.panel_rows = lcd->rows;

    snap.porta = via_6522_porta_pins(m->via);
    snap.portb = via_6522_portb_pins(m->via);
    snap.ddra  = m->via->ddra;
    snap.ddrb  = m->via->ddrb;

    snap.osc_ticks  = m->bus->osc_ticks;
    snap.cpu_cycles = clockticks6502;
    snap.pc         = pc;
    snap.irq        = m->bus->irq;
    snap.stopped    = cpu_stp_pending() ? 1 : 0;
    m->snapshot(m->ctx, &snap);

    web_server_broadcast(srv, &snap);
    /* Audio goes on the same cadence as state: at ~30 fps each binary
     * frame carries ~735 samples @ 22050 Hz. */
    web_server_flush_audio(srv);
}

int web_run(const struct web_machine *m, const struct emu_opts *opts) {
    install_tty_cleanup_handlers();  /* so Ctrl-C still cleans up */

    struct web_server *srv = web_server_start(m->name, opts->web_port, opts->web_bind,
                                              opts->web_root);
    if (!srv) return 1;

    /* The tap also forces audio->enabled on, so samples flow even when
     * --wav / --audio weren't given. */
    if (m->audio) {
        audio_set_tap(m->audio, web_server_audio_tap, srv);
        web_server_send_audio_rate(srv, m->audio->sample_rate);
    }

    struct timespec t0;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    uint64_t osc0 = m->bus->osc_ticks;
    long last_snap_ns = 0;

    while (!sigint_requested && !m->step(m->ctx)) {
        long wall_ns = emu_pace(&t0, osc0, m->bus->osc_ticks, m->osc_per_us);

        struct web_event evt;
        web_server_poll(srv, &evt);
        if (evt.type != WEB_EVT_NONE) m->event(m->ctx, &evt);

        if (wall_ns - last_snap_ns >= SNAP_NS) {
            broadcast(srv, m);
            last_snap_ns = wall_ns;
        }
    }

    /* Final snapshot so any connected client sees the end state. */
    broadcast(srv, m);

    if (m->audio) audio_set_tap(m->audio, NULL, NULL);  /* detach before audio_close */
    web_server_stop(srv);
    return 0;
}
