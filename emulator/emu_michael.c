/* emu_run_michael: the Michael (v2) machine -- bus wiring, the plain, --live and --web run loops, LCD/keyboard/bus-check reporting (see emu_michael.h). */
#include "emu_michael.h"

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/select.h>

#include "bus.h"
#include "cpu_core.h"
#include "emu_run.h"
#include "lcd_report.h"
#include "pace.h"
#include "tty_alt_screen.h"
#include "web_run.h"
#include "chips/glue_michael.h"
#include "chips/rom_28c256.h"
#include "chips/ram_628128.h"
#include "chips/via_6522.h"
#include "chips/lcd_hd44780.h"
#include "chips/cpu_65c02.h"
#include "chips/ps2_keyboard_board.h"
#include "chips/serial_usb.h"
#include "ps2_keys.h"

/* The ROM's IRQ vector points here; programs copy their handler to it
 * (INTERRUPT_VECTOR_TARGET in base_config_v2.inc). */
#define MICHAEL_IRQ_TARGET 0x3F00

/* Michael's clock: the oscillator runs the CPU at 2 MHz. */
#define MICHAEL_TICKS_PER_US 2

static struct bus *active_bus = NULL;

/* The devices that drive PORTB when the VIA leaves its pins as inputs. */
struct portb_drivers {
    const struct lcd_hd44780_state *lcd;
    const struct ps2_keyboard_board_state *kbd;
};

/* Pins driven by more than one device read as the AND of their drives,
 * as a low driver wins. Undriven pins read 0. */
static uint8_t portb_input(void *ctx) {
    const struct portb_drivers *d = ctx;
    uint8_t lcd = 0xFF, kbd = 0xFF;
    int lcd_drives = lcd_hd44780_output(d->lcd, &lcd);
    int kbd_drives = ps2_board_output(d->kbd, &kbd);
    return (lcd_drives || kbd_drives) ? (uint8_t)(lcd & kbd) : 0x00;
}

/* Counts spells of more than one device driving the same PORTB pin:
 * the VIA (pins set as outputs), the LCD (a read cycle) and the
 * keyboard board (SOEB low). */
struct bus_check_state {
    const struct via_6522_state *via;
    struct portb_drivers drivers;
    uint32_t contention;
    uint8_t contending;
};

static void bus_check_tick(struct chip *self, struct bus *bus) {
    (void)bus;
    struct bus_check_state *s = self->state;
    uint8_t value;
    int drivers = (s->via->ddrb != 0) + lcd_hd44780_output(s->drivers.lcd, &value)
                + ps2_board_output(s->drivers.kbd, &value);
    if (drivers > 1) {
        if (!s->contending) s->contention++;
        s->contending = 1;
    } else {
        s->contending = 0;
    }
}

/* The VIA's IRQ output to the CPU; --kbd-fault noirq cuts it. Ticks
 * between the VIA and the CPU. */
static void irq_cut_tick(struct chip *self, struct bus *bus) {
    (void)self;
    bus->irq = 0;
}

/* --kbd-scancodes: the whole list is one key. */
static int queue_scancodes(struct ps2_keyboard_board_state *kbd, const char *list) {
    uint8_t codes[PS2_QUEUE_SIZE];
    int n = 0;
    const char *p = list;
    while (*p) {
        char *end;
        long byte = strtol(p, &end, 16);
        if (end == p || byte < 0 || byte > 0xFF || (*end && *end != ',') || n == PS2_QUEUE_SIZE) {
            fprintf(stderr, "michael: bad --kbd-scancodes list: %s\n", list);
            return -1;
        }
        codes[n++] = (uint8_t)byte;
        p = *end ? end + 1 : end;
    }
    return ps2_board_queue_key(kbd, codes, n);
}

/* Type the keys in text (as a terminal sends them, see ps2_keys.h) on
 * the keyboard, a key at a time. Returns -1 if the keyboard's queue
 * filled up. */
static int type_keys(struct ps2_keyboard_board_state *kbd, const uint8_t *text, size_t len) {
    for (size_t at = 0; at < len; ) {
        uint8_t codes[PS2_KEY_MAX_CODES];
        size_t used;
        int n = ps2_encode_key(text + at, len - at, &used, codes);
        at += used;
        if (n && ps2_board_queue_key(kbd, codes, n) < 0) return -1;
    }
    return 0;
}

/* --keys: type each key in the file. */
static int queue_keys_file(struct ps2_keyboard_board_state *kbd, const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) {
        fprintf(stderr, "michael: could not open --keys %s\n", path);
        return -1;
    }
    static uint8_t text[PS2_QUEUE_SIZE];
    size_t len = fread(text, 1, sizeof(text), f);
    fclose(f);
    if (type_keys(kbd, text, len) < 0) {
        fprintf(stderr, "michael: too many keys in %s\n", path);
        return -1;
    }
    return 0;
}

static enum ps2_fault board_fault(const char *name) {
    if (!name) return PS2_FAULT_NONE;
    if (!strcmp(name, "noedge")) return PS2_FAULT_NOEDGE;
    if (!strcmp(name, "noack"))  return PS2_FAULT_NOACK;
    if (!strcmp(name, "resend")) return PS2_FAULT_RESEND;
    return PS2_FAULT_NONE;     /* noirq is the machine's, not the board's */
}

static uint8_t michael_cpu_read(uint16_t addr) {
    active_bus->addr = addr;
    active_bus->rwb = 1;
    uint16_t chip_addr = glue_michael_decode(active_bus);
    uint8_t data = 0xFF;
    bus_read(active_bus, chip_addr, &data);
    return data;
}

/* A write goes to the chip the decode selects; with --ram eater, one to
 * $6000-$7FFF selects both the VIA and the RAM, and the bus hands a
 * write only to the first chip that takes it, so each gets it in turn. */
static void michael_bus_write(struct bus *b, uint8_t data) {
    uint16_t chip_addr = glue_michael_decode(b);
    if (b->viacs && b->ramcs) {
        b->ramcs = 0;
        bus_write(b, chip_addr, data);
        b->ramcs = 1;
        b->viacs = 0;
    }
    bus_write(b, chip_addr, data);
}

static void michael_cpu_write(uint16_t addr, uint8_t data) {
    active_bus->addr = addr;
    active_bus->rwb = 0;
    michael_bus_write(active_bus, data);
}

/* Hold RES for a few ticks: the CPU fetches its reset vector through
 * the ROM and the VIA clears its registers. */
static void pulse_reset(struct bus *b) {
    b->res = 1;
    for (int i = 0; i < 8; i++) bus_step(b);
    b->res = 0;
}

static void set_vector(struct rom_28c256_state *rom, uint16_t vector, uint16_t target) {
    rom->contents[vector & (ROM_28C256_SIZE - 1)] = (uint8_t)(target & 0xFF);
    rom->contents[(vector + 1) & (ROM_28C256_SIZE - 1)] = (uint8_t)(target >> 8);
}

/* Write the program into RAM through the bus, as the loader would. */
static int load_program(struct bus *b, const char *path, uint16_t load) {
    FILE *f = fopen(path, "rb");
    if (!f) {
        fprintf(stderr, "michael: could not open %s\n", path);
        return -1;
    }
    uint32_t off = 0;
    int byte;
    while ((byte = fgetc(f)) != EOF) {
        uint16_t a = (uint16_t)(load + off++);
        b->addr = a;
        b->rwb = 0;
        glue_michael_decode(b);
        if (!b->ramcs) {
            fprintf(stderr, "michael: %s does not fit in RAM at $%04X\n", path, load);
            fclose(f);
            return -1;
        }
        michael_bus_write(b, (uint8_t)byte);
    }
    fclose(f);
    b->rwb = 1;
    return 0;
}

/* Step up to n oscillator ticks, stopping at the cap or an STP; keep the
 * lowest stack pointer seen. */
static void step(struct bus *b, int n, uint64_t cap, uint8_t *lowest_sp) {
    for (int i = 0; i < n && b->osc_ticks < cap && !cpu_stp_pending(); i++) {
        bus_step(b);
        if (sp < *lowest_sp) *lowest_sp = sp;
    }
}

/* ---- --live: the LCD in the terminal, the terminal's keys on the keyboard ---- */

#define LIVE_QUIT_KEY   0x1D           /* Ctrl-] */
#define LIVE_KEY_GAP_NS (10 * 1000000L) /* keys go out once input pauses this long */
#define LIVE_FRAME_NS   (30 * 1000000L)

static void live_emit(const char *s, size_t n) {
    if (write(1, s, n) < 0) { /* best-effort */ }
}

/* The panel in a box, the cell under a showing cursor in reverse video */
static void live_render(const struct lcd_hd44780_state *lcd) {
    char buf[1024], text[LCD_DDRAM_SIZE + 8];
    (void)lcd_hd44780_render((struct lcd_hd44780_state *)lcd, text);
    int cursor_row = -1, cursor_col = -1;
    if (lcd->display_on && lcd->cursor_on) lcd_hd44780_cursor(lcd, &cursor_row, &cursor_col);
    int n = snprintf(buf, sizeof buf,
                     "\x1b[H\x1b[1mmichael live\x1b[0m  --  Ctrl-] quits\x1b[K\r\n\r\n  +");
    for (int c = 0; c < lcd->cols; c++) buf[n++] = '-';
    n += snprintf(buf + n, sizeof buf - n, "+\x1b[K\r\n");
    for (int r = 0; r < lcd->rows; r++) {
        n += snprintf(buf + n, sizeof buf - n, "  |");
        for (int c = 0; c < lcd->cols; c++) {
            char ch = lcd->display_on ? text[r * lcd->cols + c] : ' ';
            if (r == cursor_row && c == cursor_col)
                n += snprintf(buf + n, sizeof buf - n, "\x1b[7m%c\x1b[0m", ch);
            else
                buf[n++] = ch;
        }
        n += snprintf(buf + n, sizeof buf - n, "|\x1b[K\r\n");
    }
    n += snprintf(buf + n, sizeof buf - n, "  +");
    for (int c = 0; c < lcd->cols; c++) buf[n++] = '-';
    n += snprintf(buf + n, sizeof buf - n, "+\x1b[K\r\n");
    live_emit(buf, (size_t)n);
}

/* Read what the terminal has sent, without waiting. Returns the bytes read. */
static int live_read(uint8_t *buf, int room) {
    fd_set fds;
    struct timeval tv = {0, 0};
    FD_ZERO(&fds);
    FD_SET(0, &fds);
    if (room <= 0 || select(1, &fds, NULL, NULL, &tv) <= 0) return 0;
    ssize_t n = read(0, buf, (size_t)room);
    return n > 0 ? (int)n : 0;
}

static void run_live(struct bus *b, struct lcd_hd44780_state *lcd,
                     struct ps2_keyboard_board_state *kbd, uint64_t cap,
                     double osc_per_us, uint8_t *lowest_sp) {
    install_tty_cleanup_handlers();
    tty_alt_screen_enter();
    live_emit("\x1b[?25l\x1b[2J", 10);

    struct timespec t0;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    uint64_t osc0 = b->osc_ticks;
    long last_render_ns = -LIVE_FRAME_NS, last_input_ns = 0;
    uint8_t typed[256];
    int typed_len = 0, quit = 0;
    while (!quit && !sigint_requested && !cpu_stp_pending() && b->osc_ticks < cap) {
        step(b, 2000, cap, lowest_sp);
        long wall_ns = emu_pace(&t0, osc0, b->osc_ticks, osc_per_us);
        if (wall_ns - last_render_ns >= LIVE_FRAME_NS) {
            live_render(lcd);
            last_render_ns = wall_ns;
        }
        int got = live_read(typed + typed_len, (int)sizeof typed - typed_len);
        for (int i = 0; i < got; i++) if (typed[typed_len + i] == LIVE_QUIT_KEY) quit = 1;
        if (got) last_input_ns = wall_ns;
        typed_len += got;
        if (typed_len && wall_ns - last_input_ns >= LIVE_KEY_GAP_NS) {
            type_keys(kbd, typed, (size_t)typed_len);
            typed_len = 0;
        }
    }
    live_render(lcd);
    tty_alt_screen_leave();
}

/* ---- --web: the page's LCD, pins and LED; its keys typed on the keyboard ---- */

#define MICHAEL_LED 0x04    /* PA2: LED in base_config_v2.inc */

struct michael_web {
    struct bus *b;
    const struct via_6522_state *via;
    struct ps2_keyboard_board_state *kbd;
    uint64_t cap;
    uint8_t *lowest_sp;
};

static int web_step(void *ctx) {
    struct michael_web *w = ctx;
    step(w->b, 5000, w->cap, w->lowest_sp);
    return w->b->osc_ticks >= w->cap || cpu_stp_pending();
}

static void web_event(void *ctx, const struct web_event *evt) {
    struct michael_web *w = ctx;
    if (evt->type == WEB_EVT_RESET) pulse_reset(w->b);
    else if (evt->type == WEB_EVT_KEYS) type_keys(w->kbd, evt->bytes, (size_t)evt->n_bytes);
}

/* The page's LED 0 is PA2's. It is wired from +5V to the pin, so it
 * lights while PA2 is an output driven low (initialize_michael_ports
 * drives it high to turn it off). */
static void web_snapshot(void *ctx, struct web_snapshot *snap) {
    struct michael_web *w = ctx;
    snap->n_leds = 1;
    snap->leds[0] = (w->via->ddra & MICHAEL_LED) && !(via_6522_porta_pins(w->via) & MICHAEL_LED);
}

int emu_run_michael(const struct emu_opts *opts) {
    cpu_variant = opts->cpu_variant_opt;

    static struct glue_michael_state glue_state;
    static struct rom_28c256_state   rom_state;
    static struct ram_628128_state   ram_state;
    static struct via_6522_state     via_state;
    static struct lcd_hd44780_state  lcd_state;
    static struct cpu_65c02_state    cpu_state;
    static struct ps2_keyboard_board_state kbd_state;
    static struct serial_usb_state   ser_state;
    static struct bus_check_state    check_state;
    static const struct chip_ops check_ops = { .tick = bus_check_tick };
    static const struct chip_ops irq_cut_ops = { .tick = irq_cut_tick };
    struct chip glue_chip, rom_chip, ram_chip, via_chip, lcd_chip, kbd_chip, ser_chip, cpu_chip;
    struct chip check_chip = { &check_ops, "bus_check", &check_state };
    struct chip irq_cut_chip = { &irq_cut_ops, "irq_cut", NULL };

    glue_michael_init(&glue_chip, &glue_state);
    enum glue_michael_ram ram = GLUE_MICHAEL_RAM_16K;
    if (opts->ram_map) glue_michael_ram_by_name(opts->ram_map, &ram);   /* cli.c checked it */
    glue_michael_set_ram(ram);
    rom_28c256_init(&rom_chip, &rom_state);
    ram_628128_init(&ram_chip, &ram_state);
    via_6522_init(&via_chip, &via_state);
    lcd_hd44780_init(&lcd_chip, &lcd_state, &via_state);
    lcd_hd44780_set_wiring(&lcd_state, &LCD_WIRING_MICHAEL);
    lcd_hd44780_set_geometry(&lcd_state, 4, 20);
    ps2_keyboard_board_init(&kbd_chip, &kbd_state, &via_state, MICHAEL_TICKS_PER_US);
    kbd_state.fault = board_fault(opts->kbd_fault);
    if (opts->key_interval_ms) kbd_state.key_interval_us = (uint32_t)opts->key_interval_ms * 1000;
    if (opts->kbd_scancodes && queue_scancodes(&kbd_state, opts->kbd_scancodes) != 0) return 1;
    if (opts->keys_filename && queue_keys_file(&kbd_state, opts->keys_filename) != 0) return 1;
    /* The USB serial adapter on CB2, which the loaders receive through */
    serial_usb_init(&ser_chip, &ser_state, &via_state);
    if (opts->serial_input_filename &&
        serial_usb_queue_file(&ser_state, opts->serial_input_filename) != 0) {
        fprintf(stderr, "michael: could not open --serial-input %s\n", opts->serial_input_filename);
        return 1;
    }
    cpu_65c02_init(&cpu_chip, &cpu_state);

    memset(&check_state, 0, sizeof(check_state));
    check_state.via = &via_state;
    check_state.drivers.lcd = &lcd_state;
    check_state.drivers.kbd = &kbd_state;
    via_6522_set_portb_input(&via_state, portb_input, &check_state.drivers);

    /* With --load the code file goes into RAM, and the ROM is --rom's or
     * holds only the vectors; without it the code file is the ROM image
     * (unless --rom names one) and RAM starts empty. */
    int load_ram = opts->load_address >= 0;
    uint16_t load = load_ram ? (uint16_t)opts->load_address : 0;
    const char *rom_path = opts->rom_filename ? opts->rom_filename
                                              : (load_ram ? NULL : opts->code_filename);
    if (rom_path) {
        if (rom_28c256_load(&rom_state, rom_path) != 0) {
            fprintf(stderr, "michael: could not load ROM image: %s\n", rom_path);
            return 1;
        }
    } else {
        set_vector(&rom_state, 0xFFFC, load);
        set_vector(&rom_state, 0xFFFE, MICHAEL_IRQ_TARGET);
    }

    struct bus b;
    bus_init(&b);
    bus_add_chip(&b, &glue_chip);   /* first: decodes and clocks the CPU */
    bus_add_chip(&b, &rom_chip);
    bus_add_chip(&b, &ram_chip);
    bus_add_chip(&b, &via_chip);
    bus_add_chip(&b, &lcd_chip);
    bus_add_chip(&b, &kbd_chip);
    bus_add_chip(&b, &ser_chip);
    bus_add_chip(&b, &check_chip);
    if (opts->kbd_fault && !strcmp(opts->kbd_fault, "noirq")) bus_add_chip(&b, &irq_cut_chip);
    bus_add_chip(&b, &cpu_chip);

    if (load_ram && load_program(&b, opts->code_filename, load) != 0) return 1;

    active_bus = &b;
    cpu_external_read  = michael_cpu_read;
    cpu_external_write = michael_cpu_write;

    pulse_reset(&b);

    /* A program run without a ROM finds the LCD as the ROM leaves it
     * (michael_rom.s: reset_and_enable_display_no_cursor), as the
     * programs that run after the ROM's loader expect */
    if (!rom_path) {
        static const uint8_t rom_lcd_setup[] = {
            0x38,   /* 8-bit, 2 lines, 5x8 */
            0x08,   /* display off */
            0x01,   /* clear */
            0x06,   /* increment, no display shift */
            0x0C,   /* display on, no cursor */
        };
        for (size_t i = 0; i < sizeof rom_lcd_setup; i++)
            lcd_hd44780_instruction(&lcd_state, rom_lcd_setup[i]);
    }

    uint64_t cap = opts->cycle_cap;
    if ((opts->live || opts->web) && !opts->cycle_cap_set) cap = UINT64_MAX;
    double osc_per_us = opts->target_mhz > 0.0 ? opts->target_mhz : MICHAEL_TICKS_PER_US;
    uint8_t lowest_sp = 0xFF;
    int rc = 0;
    if (opts->web) {
        struct michael_web w = { &b, &via_state, &kbd_state, cap, &lowest_sp };
        struct web_machine m = {
            .name = "michael", .bus = &b, .lcd = &lcd_state, .via = &via_state,
            .osc_per_us = osc_per_us, .ctx = &w,
            .step = web_step, .event = web_event, .snapshot = web_snapshot,
        };
        rc = web_run(&m, opts);
    } else if (opts->live) {
        run_live(&b, &lcd_state, &kbd_state, cap, osc_per_us, &lowest_sp);
    } else {
        FILE *lcd_trace_fp = NULL;
        if (opts->lcd_trace_filename) {
            lcd_trace_fp = fopen(opts->lcd_trace_filename, "w");
            if (!lcd_trace_fp) {
                fprintf(stderr, "michael: could not open --lcd-trace %s\n", opts->lcd_trace_filename);
                return 1;
            }
        }
        while (b.osc_ticks < cap && !cpu_stp_pending()) {
            step(&b, 50000, cap, &lowest_sp);
            lcd_report_trace(lcd_trace_fp, &lcd_state, b.osc_ticks);
        }
        if (lcd_trace_fp) {
            lcd_report_trace(lcd_trace_fp, &lcd_state, b.osc_ticks);
            fclose(lcd_trace_fp);
        }
    }

    fprintf(stderr, "michael: exit  cpu_cycles=%llu  pc=$%04X  %s\n",
            (unsigned long long)clockticks6502, pc,
            cpu_stp_pending() ? "(STP)" : "(cycle cap)");
    lcd_report_final(stderr, "michael", &lcd_state);
    fprintf(stderr, "michael: bus: lcd-undriven=%u portb-contention=%u\n",
            (unsigned)lcd_state.undriven_strobes, (unsigned)check_state.contention);
    /* The lowest the stack pointer went: an address free below it is
     * room programs can use for data. */
    fprintf(stderr, "michael: stack: lowest $01%02X\n", lowest_sp);

    cpu_external_read  = NULL;
    cpu_external_write = NULL;
    active_bus = NULL;
    return rc;
}
