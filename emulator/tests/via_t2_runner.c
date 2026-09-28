/* Runs a program on the emulator's CPU and VIA chips, on a bus with 64K of RAM and the VIA at
 * $6000 (Michael's address), and prints the cycle of every T2 timeout and of every read of T2CL:
 *
 *   via_t2_runner <binary> <load address, hex> <cycles>
 *
 * The reset vector points at the load address and the IRQ vector at $3F00 (Michael's). Nothing
 * drives PORTB, so an LCD's busy flag reads clear. timer2_cycles_test.py uses it to time the
 * T2 ticks of michael_timer2_test2.s. */

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "../bus.h"
#include "../cpu_core.h"
#include "../chips/cpu_65c02.h"
#include "../chips/via_6522.h"

#define VIA_BASE   0x6000
#define IRQ_TARGET 0x3F00

static uint8_t memory[0x10000];
static struct bus b;
static uint64_t cycle;

/* Required by cpu_core.c; the CPU goes through the external hooks below instead. */
uint8_t read6502(uint16_t addr) { return memory[addr]; }
void write6502(uint16_t addr, uint8_t value) { memory[addr] = value; }

static int is_via(uint16_t addr) { return (addr & 0xFFF0) == VIA_BASE; }

static uint8_t cpu_read(uint16_t addr) {
    if (!is_via(addr)) return memory[addr];
    if ((addr & 0xF) == VIA_REG_T2CL) printf("t2cl-read %llu\n", (unsigned long long)cycle);
    uint8_t data = 0xFF;
    b.viacs = 1;
    bus_read(&b, addr, &data);
    b.viacs = 0;
    return data;
}

static void cpu_write(uint16_t addr, uint8_t data) {
    if (!is_via(addr)) { memory[addr] = data; return; }
    b.viacs = 1;
    bus_write(&b, addr, data);
    b.viacs = 0;
}

/* Every OSC tick is a CPU cycle: the VIA counts, then the CPU runs (as on the wendy2c bus). */
static void clock_tick(struct chip *self, struct bus *bus) {
    (void)self;
    bus->cpu_cycle_due = 1;
}

int main(int argc, char **argv) {
    if (argc != 4) {
        fprintf(stderr, "usage: %s <binary> <load address, hex> <cycles>\n", argv[0]);
        return 2;
    }
    uint16_t load = (uint16_t)strtoul(argv[2], NULL, 16);
    uint64_t cycles = strtoull(argv[3], NULL, 10);
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror(argv[1]); return 1; }
    size_t n = fread(memory + load, 1, sizeof(memory) - load, f);
    fclose(f);
    if (n == 0) { fprintf(stderr, "%s: empty\n", argv[1]); return 1; }
    memory[0xFFFC] = (uint8_t)load;
    memory[0xFFFD] = (uint8_t)(load >> 8);
    memory[0xFFFE] = (uint8_t)IRQ_TARGET;
    memory[0xFFFF] = (uint8_t)(IRQ_TARGET >> 8);

    static const struct chip_ops clock_ops = { .tick = clock_tick };
    struct chip clock_chip = { .ops = &clock_ops, .name = "clock" };
    struct via_6522_state via_state;
    struct chip via_chip;
    struct cpu_65c02_state cpu_state;
    struct chip cpu_chip;
    via_6522_init(&via_chip, &via_state);
    cpu_65c02_init(&cpu_chip, &cpu_state);
    bus_init(&b);
    bus_add_chip(&b, &clock_chip);
    bus_add_chip(&b, &via_chip);
    bus_add_chip(&b, &cpu_chip);

    cpu_variant = CPU_65C02;
    cpu_external_read = cpu_read;
    cpu_external_write = cpu_write;
    reset6502();

    for (cycle = 0; cycle < cycles; cycle++) {
        uint8_t before = via_6522_ifr(&via_state) & VIA_INT_T2;
        bus_step(&b);
        if (!before && (via_6522_ifr(&via_state) & VIA_INT_T2)) {
            printf("t2-timeout %llu\n", (unsigned long long)cycle);
        }
        if (cpu_stp_pending()) break;
    }
    return 0;
}
