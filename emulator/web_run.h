#ifndef EMULATOR_WEB_RUN_H
#define EMULATOR_WEB_RUN_H

#include <stdint.h>

#include "audio.h"
#include "bus.h"
#include "cli.h"
#include "web_server.h"
#include "chips/lcd_hd44780.h"
#include "chips/via_6522.h"

/* The --web run loop the board machines share: it steps the machine in
 * batches paced to wall time, hands the browser's events to it and
 * pushes a snapshot of the LCD, the VIA pins and the clock (with its
 * measured rate against the target, so the page shows when the host
 * can't keep up) to the page about every 33 ms (with the audio stream,
 * when the machine has one). */
struct web_machine {
    const char *name;                   /* web_server_start's machine */
    struct bus *bus;
    const struct lcd_hd44780_state *lcd;
    const struct via_6522_state *via;
    struct audio_state *audio;          /* NULL: no audio stream */
    double osc_per_us;                  /* pacing rate */
    void *ctx;                          /* passed to the callbacks */
    /* Steps a batch; returns 1 when the run is over (cycle cap or STP). */
    int (*step)(void *ctx);
    void (*event)(void *ctx, const struct web_event *evt);
    /* Fills the machine's own snapshot fields: its LEDs and button,
     * the panel layout. */
    void (*snapshot)(void *ctx, struct web_snapshot *snap);
};

/* Serves the machine's page on --web-port / --web-bind / --web-root and
 * runs until the run is over or SIGINT. Returns 1 if the server could
 * not start, else 0. */
int web_run(const struct web_machine *m, const struct emu_opts *opts);

#endif
