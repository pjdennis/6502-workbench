/* emu_run_wendy2c: the wendy2c machine -- chip wiring plus the plain, --live, --web and --serial-link run loops and the live ANSI renderer. */
#include "emu_wendy2c.h"

#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <signal.h>
#include <sys/select.h>

#include "audio.h"
#include "bus.h"
#include "cpu_core.h"
#include "emu_run.h"
#include "lcd_report.h"
#include "pace.h"
#include "serial_link.h"
#include "tty_alt_screen.h"
#include "web_run.h"
#include "chips/clock_22v10.h"
#include "chips/rom_28c256.h"
#include "chips/ram_628128.h"
#include "chips/via_6522.h"
#include "chips/lcd_hd44780.h"
#include "chips/serial_usb.h"
#include "chips/syscall_ports.h"
#include <unistd.h>
#include "chips/led_buttons.h"
#include "chips/cpu_65c02.h"

extern volatile sig_atomic_t sigint_requested;

/* Module-scope bus pointer used by the cpu_external_read/write hooks
 * the CPU dispatch reaches into. There's at most one wendy2c run
 * active per process. */
static struct bus *active_bus = NULL;

static uint8_t wendy2c_cpu_read(uint16_t addr) {
    if (!active_bus) return 0xFF;
    /* Reflect the address on the bus and refresh chip-select lines so
     * ROM/RAM/VIA see the right CS for THIS access. (CKS/CK are not
     * touched -- those advance on bus_step, not on per-access reads.) */
    active_bus->addr = addr;
    active_bus->rwb = 1;
    clock_22v10_refresh_combinational(active_bus);
    uint8_t data = 0xFF;
    bus_read(active_bus, addr, &data);
    return data;
}

static void wendy2c_cpu_write(uint16_t addr, uint8_t data) {
    if (!active_bus) return;
    active_bus->addr = addr;
    active_bus->rwb = 0;
    clock_22v10_refresh_combinational(active_bus);
    bus_write(active_bus, addr, data);
}

/* ---- live-mode renderer ---- */

/* PORTA / PORTB pin labels for the wendy2c. Reflects the post-GD-disable
 * wiring in base_config_wendy2c.inc + multitasking_test_wendy2c.s:
 * the graphic display is no longer wired up, freeing PA1/PA2 as the
 * CONTROL_BUTTON input and CONTROL_LED output, respectively. */
static const char *PORTA_LABELS[8] = {
    /* PA0 */ "RS",   /* LCD RS */
    /* PA1 */ "BTN",  /* CONTROL_BUTTON input */
    /* PA2 */ "LED",  /* CONTROL_LED output */
    /* PA3 */ "RW",   /* LCD RW */
    /* PA4 */ "D4",   /* LCD D4 */
    /* PA5 */ "D5",   /* LCD D5 */
    /* PA6 */ "D6",   /* LCD D6 */
    /* PA7 */ "D7",   /* LCD D7 */
};
static const char *PORTB_LABELS[8] = {
    /* PB0 */ "B0",   /* BANK bit 0 */
    /* PB1 */ "B1",
    /* PB2 */ "B2",
    /* PB3 */ "B3",
    /* PB4 */ "B4",
    /* PB5 */ "E",    /* LCD enable */
    /* PB6 */ "LED",  /* morse LED */
    /* PB7 */ "T1",   /* T1 squarewave */
};

static void live_emit(const char *s) {
    size_t n = strlen(s);
    if (write(1, s, n) < 0) { /* best-effort */ }
}

static void live_render(const struct bus *b,
                        const struct lcd_hd44780_state *lcd,
                        const struct via_6522_state *via,
                        const struct led_buttons_state *ledbtn,
                        int cap_hit) {
    char buf[2048];
    char lcdbuf[LCD_DDRAM_SIZE + 8];
    int cols = lcd->cols;
    (void)lcd_hd44780_render((struct lcd_hd44780_state *)lcd, lcdbuf);

    uint8_t porta = via_6522_porta_pins(via);
    uint8_t portb = via_6522_portb_pins(via);
    int led  = led_buttons_led(ledbtn);
    int led2 = led_buttons_control_led(ledbtn);
    int btn  = led_buttons_button(ledbtn);

    /* Cursor home, default colors. */
    int n = 0;
    n += snprintf(buf + n, sizeof(buf) - n, "\x1b[H\x1b[0m");
    n += snprintf(buf + n, sizeof(buf) - n,
        "\x1b[1mwendy2c live\x1b[0m  --  q/ESC/Ctrl-C quit, SPACE press button, R reset\x1b[K\r\n\r\n");

    /* LCD frame in a box. */
    n += snprintf(buf + n, sizeof(buf) - n, "  LCD:\x1b[K\r\n");
    n += snprintf(buf + n, sizeof(buf) - n, "  +");
    for (int i = 0; i < cols; i++) n += snprintf(buf + n, sizeof(buf) - n, "-");
    n += snprintf(buf + n, sizeof(buf) - n, "+\x1b[K\r\n");
    for (int r = 0; r < lcd->rows; r++) {
        n += snprintf(buf + n, sizeof(buf) - n, "  |%.*s|\x1b[K\r\n",
                      cols, lcdbuf + r * cols);
    }
    n += snprintf(buf + n, sizeof(buf) - n, "  +");
    for (int i = 0; i < cols; i++) n += snprintf(buf + n, sizeof(buf) - n, "-");
    n += snprintf(buf + n, sizeof(buf) - n, "+\x1b[K\r\n\r\n");

    /* LED + button indicators. The on-LEDs get a brighter color.
     *   morse LED on PB6 (toggled by the morse demo task)
     *   control LED on PA2 (toggled by the led_control task on each
     *     button press; see prg_led_control.inc)
     *   button on PA1 (SPACE toggles its level) */
    n += snprintf(buf + n, sizeof(buf) - n,
        "  LED PB6: %s%s\x1b[0m   LED PA2: %s%s\x1b[0m   BTN PA1: %s%s\x1b[0m   (SPACE)\x1b[K\r\n\r\n",
        led  ? "\x1b[1;33m" : "\x1b[2m", led  ? "[*]" : "[ ]",
        led2 ? "\x1b[1;33m" : "\x1b[2m", led2 ? "[*]" : "[ ]",
        btn  ? "\x1b[1;32m" : "\x1b[2m", btn  ? "[*]" : "[ ]");

    /* PORTA pins, MSB on the left. Each bit and each label gets a
     * 4-char column (longest label is 3 chars + 1 space of leading
     * pad) so the rows line up vertically. */
    n += snprintf(buf + n, sizeof(buf) - n, "  PORTA bits: ");
    for (int i = 7; i >= 0; i--) {
        n += snprintf(buf + n, sizeof(buf) - n, "   %s%d\x1b[0m",
                      (porta & (1u << i)) ? "\x1b[1m" : "\x1b[2m",
                      (porta >> i) & 1);
    }
    n += snprintf(buf + n, sizeof(buf) - n, "    DDRA=$%02X\x1b[K\r\n", via->ddra);
    n += snprintf(buf + n, sizeof(buf) - n, "              ");
    for (int i = 7; i >= 0; i--) {
        n += snprintf(buf + n, sizeof(buf) - n, "%4s", PORTA_LABELS[i]);
    }
    n += snprintf(buf + n, sizeof(buf) - n, "\x1b[K\r\n\r\n");

    n += snprintf(buf + n, sizeof(buf) - n, "  PORTB bits: ");
    for (int i = 7; i >= 0; i--) {
        n += snprintf(buf + n, sizeof(buf) - n, "   %s%d\x1b[0m",
                      (portb & (1u << i)) ? "\x1b[1m" : "\x1b[2m",
                      (portb >> i) & 1);
    }
    n += snprintf(buf + n, sizeof(buf) - n, "    DDRB=$%02X\x1b[K\r\n", via->ddrb);
    n += snprintf(buf + n, sizeof(buf) - n, "              ");
    for (int i = 7; i >= 0; i--) {
        n += snprintf(buf + n, sizeof(buf) - n, "%4s", PORTB_LABELS[i]);
    }
    n += snprintf(buf + n, sizeof(buf) - n, "\x1b[K\r\n\r\n");

    /* Status line: osc, cpu, pc, IRQ, halt reason. */
    n += snprintf(buf + n, sizeof(buf) - n,
        "  osc:%llu  cpu:%llu  pc:$%04X  irq:%d  %s\x1b[K\r\n",
        (unsigned long long)b->osc_ticks,
        (unsigned long long)clockticks6502,
        pc, b->irq,
        cpu_stp_pending() ? "[STP]" : (cap_hit ? "[CAP]" : ""));

    /* Clear from cursor to end of screen so a shrinking frame
     * doesn't leave garbage below. */
    n += snprintf(buf + n, sizeof(buf) - n, "\x1b[J");

    (void)n;
    live_emit(buf);
}

/* Returns 1 if user hit a quit key, 0 otherwise. Reads at most a few
 * bytes; SPACE toggles the button via led_buttons_press(). */
/* Pulse RES high on the bus for a few oscillator ticks then release.
 * Mirrors the init-time reset sequence: the CPU + VIA both sample RES
 * rising-edge in their tick() and clear their state, then resume from
 * the reset vector on the first cycle after RES drops. The 8-tick
 * width is plenty for the CPU to latch the new PC and is short enough
 * to be visually instantaneous. */
static void pulse_reset(struct bus *b, struct audio_state *audio) {
    b->res = 1;
    for (int i = 0; i < 8; i++) {
        bus_step(b);
        if (audio) audio_step(audio, b->osc_ticks, 0);
    }
    b->res = 0;
}

/* Bit-flag return values for live_poll_input so the loop can react to
 * multiple events from one keypress burst. */
#define LIVE_INPUT_QUIT   0x1
#define LIVE_INPUT_RESET  0x2

static int live_poll_input(struct led_buttons_state *ledbtn) {
    fd_set fds;
    struct timeval tv = {0, 0};
    FD_ZERO(&fds);
    FD_SET(0, &fds);
    if (select(1, &fds, NULL, NULL, &tv) <= 0) return 0;

    int flags = 0;
    unsigned char buf[16];
    ssize_t n = read(0, buf, sizeof(buf));
    for (ssize_t i = 0; i < n; i++) {
        unsigned char c = buf[i];
        if (c == 'q' || c == 'Q' || c == 0x03 /* Ctrl-C */ || c == 0x1B /* ESC */) {
            flags |= LIVE_INPUT_QUIT;
        } else if (c == ' ') {
            led_buttons_press(ledbtn, !ledbtn->button_pressed);
        } else if (c == 'r' || c == 'R') {
            flags |= LIVE_INPUT_RESET;
        }
    }
    return flags;
}

/* Poll the link if non-NULL; if it's stalled (TX active + current
 * duration expired + recv buffer empty), select-wait briefly on the
 * client fd so we don't busy-spin. Returns 1 if a stall happened (the
 * caller may want to re-check before starting the next batch).
 * Stall timeout is bounded so UIs (live render / web snapshots) stay
 * responsive. */
static int link_step(struct serial_link *link, uint64_t osc_now,
                      struct bus *b, struct via_6522_state *via,
                      int stall_timeout_ms) {
    if (!link) return 0;
    serial_link_poll(link, osc_now, b, via);
    if (!serial_link_should_stall(link, osc_now)) return 0;
    int fd = serial_link_client_fd(link);
    if (fd < 0) return 0;
    fd_set rfds; FD_ZERO(&rfds); FD_SET(fd, &rfds);
    struct timeval tv = { 0, stall_timeout_ms * 1000 };
    select(fd + 1, &rfds, NULL, NULL, &tv);
    return 1;
}

/* What the --live and --web loops work on. */
struct wendy2c_run {
    struct bus *b;
    struct lcd_hd44780_state *lcd;
    struct via_6522_state *via;
    struct led_buttons_state *ledbtn;
    struct audio_state *audio;
    struct serial_link *link;
    uint64_t cap;
    int panel_5x10;
};

/* Step up to n oscillator ticks, servicing the serial link (a stall
 * ends the batch early). Returns 1 when the run is over: the cycle cap.
 * An STP stops only the CPU: under --live and --web the board runs on,
 * and the reset button starts the CPU again. */
static int run_batch(struct wendy2c_run *r, int n) {
    struct bus *b = r->b;
    for (int i = 0; i < n; i++) {
        if (b->osc_ticks >= r->cap) return 1;
        bus_step(b);
        audio_step(r->audio, b->osc_ticks, via_6522_portb_pins(r->via));
        if (r->link && serial_link_needs_repoll(r->link, b->osc_ticks)) {
            serial_link_poll(r->link, b->osc_ticks, b, r->via);
            if (serial_link_should_stall(r->link, b->osc_ticks)) break;
        }
    }
    return 0;
}

static int emu_run_wendy2c_live(struct wendy2c_run *r, double osc_per_us) {
    struct bus *b = r->b;
    /* Install BEFORE entering the alt screen so that a Ctrl-C arriving
     * any time after the termios switch flows through sigint_requested
     * (caught by the loop below) instead of taking the default action,
     * which would kill the process with the cursor hidden and the alt
     * screen still active. The atexit registration covers exit paths
     * that don't go through the loop's quit checks. */
    install_tty_cleanup_handlers();
    tty_alt_screen_enter();
    /* Hide cursor; clear screen once so the home-and-overwrite render
     * pattern starts on a clean slate. */
    live_emit("\x1b[?25l\x1b[2J");

    const long FRAME_NS = 30 * 1000 * 1000; /* ~33 fps */

    struct timespec t0;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    uint64_t osc0 = b->osc_ticks;
    long last_render_ns = 0;

    int quit = 0, cap_hit = 0;
    /* Initial render so the user sees the panel immediately. */
    live_render(b, r->lcd, r->via, r->ledbtn, 0);

    while (!quit && !sigint_requested) {
        /* Drain pending link commands and stall briefly if the host
         * is mid-TX with an empty buffer. */
        if (link_step(r->link, b->osc_ticks, b, r->via, 5)) continue;
        /* Batch size tuned so the inner loop has minimal overhead
         * between renders. */
        if (run_batch(r, 2000)) {
            cap_hit = 1;
            break;
        }

        long wall_ns = emu_pace(&t0, osc0, b->osc_ticks, osc_per_us);

        if (wall_ns - last_render_ns >= FRAME_NS) {
            live_render(b, r->lcd, r->via, r->ledbtn, 0);
            last_render_ns = wall_ns;
        }

        int input_flags = live_poll_input(r->ledbtn);
        if (input_flags & LIVE_INPUT_QUIT)  quit = 1;
        if (input_flags & LIVE_INPUT_RESET) pulse_reset(b, r->audio);
    }

    /* Final render captures the last frame before tearing down the
     * alt screen. */
    live_render(b, r->lcd, r->via, r->ledbtn, cap_hit);
    /* Brief pause so the user sees the final state before we restore
     * the original terminal contents. */
    if (cap_hit) {
        struct timespec ts = { 0, 250 * 1000 * 1000 };
        nanosleep(&ts, NULL);
    }

    live_emit("\x1b[?25h"); /* show cursor */
    tty_alt_screen_leave();
    return 0; /* cap is normal exit for live mode */
}

/* ===== --web callbacks (see web_run.h) ===== */

static int web_step(void *ctx) {
    struct wendy2c_run *r = ctx;
    if (link_step(r->link, r->b->osc_ticks, r->b, r->via, 5)) return 0;
    return run_batch(r, 5000);
}

static void web_event(void *ctx, const struct web_event *evt) {
    struct wendy2c_run *r = ctx;
    if (evt->type == WEB_EVT_BUTTON) {
        led_buttons_press(r->ledbtn, evt->button_down);
    } else if (evt->type == WEB_EVT_RESET) {
        pulse_reset(r->b, r->audio);
    }
}

/* The page numbers the LEDs: 0 the morse LED (PB6), 1 the control LED (PA2). */
static void web_snapshot(void *ctx, struct web_snapshot *snap) {
    struct wendy2c_run *r = ctx;
    snap->panel_5x10     = r->panel_5x10;
    snap->n_leds         = 2;
    snap->leds[0]        = led_buttons_led(r->ledbtn);
    snap->leds[1]        = led_buttons_control_led(r->ledbtn);
    snap->button_pressed = led_buttons_button(r->ledbtn);
}

int emu_run_wendy2c(const struct emu_opts *opts) {
    cpu_variant = opts->cpu_variant_opt;

    static struct clock_22v10_state clk_state;
    static struct rom_28c256_state  rom_state;
    static struct ram_628128_state  ram_state;
    static struct via_6522_state    via_state;
    static struct lcd_hd44780_state lcd_state;
    static struct serial_usb_state  ser_state;
    static struct led_buttons_state ledbtn_state;
    static struct cpu_65c02_state   cpu_state;
    static struct syscall_ports_state sysc_state;
    struct chip clk_chip, rom_chip, ram_chip, via_chip, lcd_chip, ser_chip, ledbtn_chip, cpu_chip;
    struct chip sysc_chip;

    clock_22v10_init(&clk_chip, &clk_state);
    rom_28c256_init(&rom_chip, &rom_state);
    ram_628128_init(&ram_chip, &ram_state);
    via_6522_init  (&via_chip, &via_state);
    lcd_hd44780_init(&lcd_chip, &lcd_state, &via_state);
    /* Apply --lcd-panel: the 16x1-5x10 panel is physically a single-row
     * module, so we drop rows to 1; the rendering side picks up the
     * 5x10/cursor-gap layout from the snapshot's panel_5x10 flag. */
    if (opts->lcd_panel == LCD_PANEL_16X1_5X10) {
        lcd_hd44780_set_geometry(&lcd_state, 1, 16);
    }
    serial_usb_init(&ser_chip, &ser_state, &via_state);
    led_buttons_init(&ledbtn_chip, &ledbtn_state, &via_state);
    cpu_65c02_init (&cpu_chip, &cpu_state);

    /* Load ROM image. Falls back to code_filename if --rom is omitted. */
    const char *rom_path = opts->rom_filename ? opts->rom_filename
                                              : opts->code_filename;
    if (rom_path) {
        if (rom_28c256_load(&rom_state, rom_path) != 0) {
            fprintf(stderr, "wendy2c: could not load ROM image: %s\n", rom_path);
            return 1;
        }
    } else {
        fprintf(stderr, "wendy2c: no ROM image (use --rom PATH or positional argv)\n");
        return 1;
    }

    /* --disk: install the $F800+ OS-call port chip backed by a host directory
     * (the simulated SPI "disk"). Only when requested, so default runs are
     * byte-for-byte unchanged. The ROM + --serial-input were loaded above via
     * their own paths; chdir now so file_open()/dir_open() resolve in DIR. */
    int have_disk = (opts->disk_dir != NULL);
    if (have_disk) {
        if (chdir(opts->disk_dir) != 0) {
            fprintf(stderr, "wendy2c: could not chdir to --disk %s\n", opts->disk_dir);
            return 1;
        }
        syscall_ports_init(&sysc_chip, &sysc_state);
    }

    struct bus b;
    bus_init(&b);
    /* The clock must be the FIRST chip so wendy2c_cpu_read/write can
     * tick it before bus_read/bus_write fans out to ROM/RAM. */
    bus_add_chip(&b, &clk_chip);
    /* The OS-call ports must come before RAM/ROM so they intercept $F800-$F80F. */
    if (have_disk) bus_add_chip(&b, &sysc_chip);
    bus_add_chip(&b, &rom_chip);
    bus_add_chip(&b, &ram_chip);
    bus_add_chip(&b, &via_chip);
    bus_add_chip(&b, &lcd_chip);
    bus_add_chip(&b, &ser_chip);
    bus_add_chip(&b, &ledbtn_chip);
    bus_add_chip(&b, &cpu_chip);

    /* Pre-load any --serial-input bytes into the SERIAL_USB queue. */
    if (opts->serial_input_filename &&
        serial_usb_queue_file(&ser_state, opts->serial_input_filename) != 0) {
        fprintf(stderr, "wendy2c: could not open --serial-input %s\n",
                opts->serial_input_filename);
        return 1;
    }

    active_bus = &b;
    cpu_external_read  = wendy2c_cpu_read;
    cpu_external_write = wendy2c_cpu_write;

    /* Pulse RES so the CPU latches its reset vector through the bus
     * (i.e. through the ROM at $FFFC/$FFFD). */
    b.res = 1;
    for (int i = 0; i < 8; i++) bus_step(&b);
    b.res = 0;

    /* --wendy2-prog: preload a RAW program straight into RAM and start the
     * CPU there, bypassing the slow byte-at-a-time serial boot (impractical
     * for a ~38 KB program). The image is written with RAM bank $01 mapped,
     * so bytes >= $8000 land in the held upper-window bank just as the boot
     * ROM's loader would place them; the bank stays mapped for the run (the
     * program assumes the boot mapped it). */
    if (opts->wendy2_prog_filename) {
        FILE *pf = fopen(opts->wendy2_prog_filename, "rb");
        if (!pf) {
            fprintf(stderr, "wendy2c: could not open --wendy2-prog %s\n",
                    opts->wendy2_prog_filename);
            return 1;
        }
        uint16_t load = (opts->load_address >= 0)
                      ? (uint16_t)opts->load_address : 0x4000;
        b.bank_config = 0x01;        /* map RAM bank $01 into $8000-$EFFF */
        b.rwb = 0;                   /* drive write cycles */
        uint32_t off = 0;
        int byte;
        while ((byte = fgetc(pf)) != EOF) {
            uint16_t a = (uint16_t)(load + off);
            b.addr = a;
            clock_22v10_refresh_combinational(&b);   /* r_bits/ramcs for a + cfg $01 */
            bus_write(&b, a, (uint8_t)byte);
            off++;
        }
        fclose(pf);
        /* Hold bank $01 mapped and enter at the load address with a fresh
         * stack (the boot ROM would have done lda #$01/sta PORTB; ldx #$ff,
         * txs; jmp). bank_config only changes on a VIA PORTB write, which the
         * program won't do, so it stays $01 for the whole run. */
        via_state.orb = 0x01;
        via_state.ddrb = 0x1F;
        b.bank_config = 0x01;
        b.rwb = 1;
        pc = load;
        sp = 0xFF;
        fprintf(stderr, "wendy2c: --wendy2-prog preloaded %u bytes at $%04X "
                        "(bank $01), PC=$%04X\n", off, load, load);
    }

    /* Run until STP halts the CPU or we hit the cycle cap. The cap also
     * limits run-away tests; the wendy2c sample programs that use STP
     * (e.g. wendy2c_eeprom_show.s) terminate well within the default.
     *
     * Under --live the cap defaults to "unlimited" -- the user quits
     * interactively (q/ESC/Ctrl-C) -- mirroring how --console and
     * --terminal modes in emu_run.c bypass the cap entirely. An
     * explicit --cycle-cap still takes effect (useful for scripted
     * recordings). */
    uint64_t cap = opts->cycle_cap;
    if ((opts->live || opts->web) && !opts->cycle_cap_set) cap = UINT64_MAX;

    /* --mhz N pins the OSC (crystal) frequency. The 22V10 PLD halves
     * it for the CPU clock, so a --mhz 19.44 run matches the real
     * wendy2c board's CLOCK_FREQ_KHZ = 9720. 0 means "no throttle":
     * non-live runs uncapped; --live and --web pace to the board's
     * rate. */
    double osc_per_us = opts->target_mhz > 0.0 ? opts->target_mhz : 0.0;

    /* The board's OSC rate: base_config_wendy2c.inc has CLOCK_FREQ_KHZ
     * = 9720 (the CPU clock; delay_routines.inc and the T2-driven DELAY
     * constants in multitasking_test_wendy2c.s scale off it), so OSC =
     * 9.72 * 2 = 19.44 MHz, or --mhz if given. Audio uses it so the WAV
     * plays at the real-board pitch regardless of whether the emulation
     * is throttled (and a deliberately-overclocked run captures what
     * actually came out of PB7). audio_init is a near-no-op when
     * neither --wav nor --audio is given (enabled stays 0 and
     * audio_step short-circuits on the first branch). */
    double board_osc_per_us = osc_per_us > 0.0 ? osc_per_us : 19.44;
    struct audio_state audio;
    audio_init(&audio,
               AUDIO_DEFAULT_SAMPLE_RATE,
               opts->wav_filename,
               opts->audio_live,
               board_osc_per_us);

    /* Optional host-driven serial link. The link uses the same OSC
     * rate as the audio module (i.e. the assumed board frequency) so
     * ns -> osc-tick conversion stays consistent with whatever the
     * boot ROM expects, regardless of --mhz throttling. */
    struct serial_link *link = NULL;
    if (opts->serial_link_path) {
        link = serial_link_start(opts->serial_link_path, board_osc_per_us);
        if (!link) {
            audio_close(&audio);
            return 1;
        }
    }

    /* --lcd-trace: open the file once before entering the run loop. CLI
     * rejects this flag for --live / --web, so only the non-live paths
     * below need to check it. */
    FILE *lcd_trace_fp = NULL;
    if (opts->lcd_trace_filename) {
        lcd_trace_fp = fopen(opts->lcd_trace_filename, "w");
        if (!lcd_trace_fp) {
            fprintf(stderr, "wendy2c: could not open --lcd-trace %s\n",
                    opts->lcd_trace_filename);
            if (link) serial_link_stop(link);
            audio_close(&audio);
            return 1;
        }
    }

    struct wendy2c_run run = {
        .b = &b, .lcd = &lcd_state, .via = &via_state, .ledbtn = &ledbtn_state,
        .audio = &audio, .link = link, .cap = cap,
        .panel_5x10 = opts->lcd_panel == LCD_PANEL_16X1_5X10,
    };
    if (opts->web) {
        struct web_machine m = {
            .name = "wendy2c", .bus = &b, .lcd = &lcd_state, .via = &via_state,
            .audio = &audio, .osc_per_us = board_osc_per_us, .ctx = &run,
            .step = web_step, .event = web_event, .snapshot = web_snapshot,
        };
        web_run(&m, opts);
    } else if (opts->live) {
        emu_run_wendy2c_live(&run, board_osc_per_us);
    } else {
        /* Step in batches; when --mhz is given, sleep when ahead of the
         * wall clock so wall time tracks emulated osc time. */
        struct timespec t0;
        clock_gettime(CLOCK_MONOTONIC, &t0);
        uint64_t osc0 = b.osc_ticks;
        while (b.osc_ticks < cap) {
            if (link_step(link, b.osc_ticks, &b, &via_state, 10)) continue;
            const int BATCH = 50000;
            int stp = 0;
            for (int i = 0; i < BATCH && b.osc_ticks < cap; i++) {
                bus_step(&b);
                audio_step(&audio, b.osc_ticks, via_6522_portb_pins(&via_state));
                if (cpu_stp_pending() || sysc_state.poweroff) { stp = 1; break; }
                if (link && serial_link_needs_repoll(link, b.osc_ticks)) {
                    serial_link_poll(link, b.osc_ticks, &b, &via_state);
                    if (serial_link_should_stall(link, b.osc_ticks)) break;
                }
            }
            if (stp) break;
            lcd_report_trace(lcd_trace_fp, &lcd_state, b.osc_ticks);
            (void)emu_pace(&t0, osc0, b.osc_ticks, osc_per_us);
        }
    }

    /* Final LCD frame after STP/cap: ensure trace captures the end state. */
    if (lcd_trace_fp) {
        lcd_report_trace(lcd_trace_fp, &lcd_state, b.osc_ticks);
        fclose(lcd_trace_fp);
        lcd_trace_fp = NULL;
    }

    if (link) serial_link_stop(link);
    audio_close(&audio);

    int halted_on_stp = cpu_stp_pending();
    if (opts->exit_report) {
        fprintf(stderr,
            "wendy2c: exit  osc_ticks=%llu  cpu_cycles=%llu  pc=$%04X  %s\n",
            (unsigned long long)b.osc_ticks,
            (unsigned long long)clockticks6502,
            pc,
            halted_on_stp ? "(STP)" : "(cycle cap)");
        lcd_report_final(stderr, "wendy2c", &lcd_state);
    }

    /* Tear down the external hooks before returning so other code (e.g.
     * the test harness or a subsequent run) doesn't dangle on a dead
     * bus pointer. */
    cpu_external_read  = NULL;
    cpu_external_write = NULL;
    active_bus = NULL;

    /* Cycle-cap reached on a long-running program (e.g. one without
     * STP) is not necessarily a failure -- the LCD frame above shows
     * what landed. Reserve non-zero exit for clear setup errors. */
    (void)halted_on_stp;
    return 0;
}
