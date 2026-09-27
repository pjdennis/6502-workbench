#include "emu_michael.h"

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "bus.h"
#include "cpu_core.h"
#include "lcd_report.h"
#include "chips/glue_michael.h"
#include "chips/rom_28c256.h"
#include "chips/ram_628128.h"
#include "chips/via_6522.h"
#include "chips/lcd_hd44780.h"
#include "chips/cpu_65c02.h"
#include "chips/ps2_keyboard_board.h"
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
    for (size_t at = 0; at < len; ) {
        uint8_t codes[PS2_KEY_MAX_CODES];
        size_t used;
        int n = ps2_encode_key(text + at, len - at, &used, codes);
        at += used;
        if (n && ps2_board_queue_key(kbd, codes, n) < 0) {
            fprintf(stderr, "michael: too many keys in %s\n", path);
            return -1;
        }
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
    glue_michael_decode(active_bus);
    uint8_t data = 0xFF;
    bus_read(active_bus, addr, &data);
    return data;
}

static void michael_cpu_write(uint16_t addr, uint8_t data) {
    active_bus->addr = addr;
    active_bus->rwb = 0;
    glue_michael_decode(active_bus);
    bus_write(active_bus, addr, data);
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
        bus_write(b, a, (uint8_t)byte);
    }
    fclose(f);
    b->rwb = 1;
    return 0;
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
    static struct bus_check_state    check_state;
    static const struct chip_ops check_ops = { .tick = bus_check_tick };
    static const struct chip_ops irq_cut_ops = { .tick = irq_cut_tick };
    struct chip glue_chip, rom_chip, ram_chip, via_chip, lcd_chip, kbd_chip, cpu_chip;
    struct chip check_chip = { &check_ops, "bus_check", &check_state };
    struct chip irq_cut_chip = { &irq_cut_ops, "irq_cut", NULL };

    glue_michael_init(&glue_chip, &glue_state);
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
    cpu_65c02_init(&cpu_chip, &cpu_state);

    memset(&check_state, 0, sizeof(check_state));
    check_state.via = &via_state;
    check_state.drivers.lcd = &lcd_state;
    check_state.drivers.kbd = &kbd_state;
    via_6522_set_portb_input(&via_state, portb_input, &check_state.drivers);

    uint16_t load = opts->load_address >= 0 ? (uint16_t)opts->load_address : 0x0900;
    if (opts->rom_filename) {
        if (rom_28c256_load(&rom_state, opts->rom_filename) != 0) {
            fprintf(stderr, "michael: could not load ROM image: %s\n", opts->rom_filename);
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
    bus_add_chip(&b, &check_chip);
    if (opts->kbd_fault && !strcmp(opts->kbd_fault, "noirq")) bus_add_chip(&b, &irq_cut_chip);
    bus_add_chip(&b, &cpu_chip);

    if (opts->code_filename && load_program(&b, opts->code_filename, load) != 0) return 1;

    active_bus = &b;
    cpu_external_read  = michael_cpu_read;
    cpu_external_write = michael_cpu_write;

    /* Pulse RES so the CPU fetches its reset vector through the ROM. */
    b.res = 1;
    for (int i = 0; i < 8; i++) bus_step(&b);
    b.res = 0;

    FILE *lcd_trace_fp = NULL;
    if (opts->lcd_trace_filename) {
        lcd_trace_fp = fopen(opts->lcd_trace_filename, "w");
        if (!lcd_trace_fp) {
            fprintf(stderr, "michael: could not open --lcd-trace %s\n", opts->lcd_trace_filename);
            return 1;
        }
    }

    uint64_t cap = opts->cycle_cap;
    uint8_t lowest_sp = 0xFF;
    while (b.osc_ticks < cap && !cpu_stp_pending()) {
        const int BATCH = 50000;
        for (int i = 0; i < BATCH && b.osc_ticks < cap && !cpu_stp_pending(); i++) {
            bus_step(&b);
            if (sp < lowest_sp) lowest_sp = sp;
        }
        lcd_report_trace(lcd_trace_fp, &lcd_state, b.osc_ticks);
    }
    if (lcd_trace_fp) {
        lcd_report_trace(lcd_trace_fp, &lcd_state, b.osc_ticks);
        fclose(lcd_trace_fp);
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
    return 0;
}
