#include "emu_michael.h"

#include <stdio.h>
#include <stdint.h>

#include "bus.h"
#include "cpu_core.h"
#include "lcd_report.h"
#include "chips/glue_michael.h"
#include "chips/rom_28c256.h"
#include "chips/ram_628128.h"
#include "chips/via_6522.h"
#include "chips/lcd_hd44780.h"
#include "chips/cpu_65c02.h"

/* The ROM's IRQ vector points here; programs copy their handler to it
 * (INTERRUPT_VECTOR_TARGET in base_config_v2.inc). */
#define MICHAEL_IRQ_TARGET 0x3F00

static const struct lcd_hd44780_wiring LCD_WIRING_MICHAEL = {
    .rs_port = LCD_PORT_A, .rs_bit = 0x20,
    .rw_port = LCD_PORT_A, .rw_bit = 0x40,
    .e_port  = LCD_PORT_A, .e_bit  = 0x80,
    .data_port = LCD_PORT_B, .data_mask = 0xFF,
};

static struct bus *active_bus = NULL;

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
    struct chip glue_chip, rom_chip, ram_chip, via_chip, lcd_chip, cpu_chip;

    glue_michael_init(&glue_chip, &glue_state);
    rom_28c256_init(&rom_chip, &rom_state);
    ram_628128_init(&ram_chip, &ram_state);
    via_6522_init(&via_chip, &via_state);
    lcd_hd44780_init(&lcd_chip, &lcd_state, &via_state);
    lcd_hd44780_set_wiring(&lcd_state, &LCD_WIRING_MICHAEL);
    lcd_hd44780_set_geometry(&lcd_state, 4, 20);
    cpu_65c02_init(&cpu_chip, &cpu_state);

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
    while (b.osc_ticks < cap && !cpu_stp_pending()) {
        const int BATCH = 50000;
        for (int i = 0; i < BATCH && b.osc_ticks < cap && !cpu_stp_pending(); i++) {
            bus_step(&b);
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

    cpu_external_read  = NULL;
    cpu_external_write = NULL;
    active_bus = NULL;
    return 0;
}
