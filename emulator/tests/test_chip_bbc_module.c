/* The banked sideways ROM module (chips/bbc_module.h): the Computer Concepts
 * 128K carrier's switching zones and its bank-0-only rule, the direct16
 * scheme's sixteen addresses, the ROM and RAM forms, and the chip on the bus. */

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "greatest.h"
#include "../bus.h"
#include "../cpu_core.h"
#include "../chips/bbc_module.h"

/* cpu_core.c wants these from its host */
uint8_t read6502(uint16_t address) { (void)address; return 0; }
void write6502(uint16_t address, uint8_t value) { (void)address; (void)value; }

static struct bbc_module_state mod;
static struct chip mod_chip;

/* Every byte of bank b holds b, so a read tells which bank answered */
static void fill_banks(void) {
    for (int b = 0; b < BBC_MODULE_MAX_BANKS; b++)
        memset(mod.data + b * BBC_MODULE_BANK_SIZE, b, BBC_MODULE_BANK_SIZE);
}

static void cc128(int ram) {
    bbc_module_init(&mod_chip, &mod, BBC_MODULE_CC128, ram, 0);
    fill_banks();
}

static void direct16(int ram) {
    bbc_module_init(&mod_chip, &mod, BBC_MODULE_DIRECT16, ram, 0);
    fill_banks();
}

TEST cc128_has_eight_banks_and_direct16_sixteen(void) {
    ASSERT_EQ(8, bbc_module_banks(BBC_MODULE_CC128));
    ASSERT_EQ(16, bbc_module_banks(BBC_MODULE_DIRECT16));
    PASS();
}

TEST cc128_every_zone_selects_its_bank_from_bank_0(void) {
    for (int bank = 1; bank <= 7; bank++) {
        uint16_t first = (uint16_t)(0x3FE0 - bank * 0x20), last = (uint16_t)(first + 0x1F);
        uint16_t probes[] = { first, (uint16_t)(first + 0x10), last };
        for (int p = 0; p < 3; p++) {
            cc128(0);
            /* the byte returned is the new bank's */
            ASSERT_EQ_FMT(bank, bbc_module_read(&mod, probes[p]), "%d");
            ASSERT_EQ_FMT(bank, mod.bank, "%d");
            ASSERT_EQ_FMT(bank, bbc_module_read(&mod, 0x0000), "%d");
        }
    }
    PASS();
}

TEST cc128_zones_switch_only_from_bank_0(void) {
    cc128(0);
    bbc_module_read(&mod, 0x3F80);              /* bank 3 */
    ASSERT_EQ(3, mod.bank);
    ASSERT_EQ(3, bbc_module_read(&mod, 0x3FC0)); /* bank 1's zone: no switch from bank 3 */
    ASSERT_EQ(3, bbc_module_read(&mod, 0x3F00));
    ASSERT_EQ(3, mod.bank);
    ASSERT_EQ(0, bbc_module_read(&mod, 0x3FE0)); /* back to 0, from any bank */
    ASSERT_EQ(0, mod.bank);
    ASSERT_EQ(7, bbc_module_read(&mod, 0x3F1F));
    PASS();
}

TEST cc128_other_addresses_do_not_switch(void) {
    cc128(0);
    uint16_t quiet[] = { 0x0000, 0x2000, 0x3EFF, 0x3FE1, 0x3FEF, 0x3FF0, 0x3FFF };
    for (unsigned i = 0; i < sizeof quiet / sizeof quiet[0]; i++) {
        ASSERT_EQ(0, bbc_module_read(&mod, quiet[i]));
        ASSERT_EQ(0, mod.bank);
    }
    bbc_module_read(&mod, 0x3FA0);              /* bank 2 */
    for (unsigned i = 0; i < sizeof quiet / sizeof quiet[0]; i++) ASSERT_EQ(2, bbc_module_read(&mod, quiet[i]));
    PASS();
}

TEST cc128_counts_switches_that_change_the_bank(void) {
    cc128(0);
    bbc_module_read(&mod, 0x3FE0);              /* 0 -> 0: no change */
    ASSERT_EQ(0, (int)mod.switches);
    bbc_module_read(&mod, 0x3FC0);              /* 0 -> 1 */
    bbc_module_read(&mod, 0x3FE0);              /* 1 -> 0 */
    ASSERT_EQ(2, (int)mod.switches);
    PASS();
}

TEST direct16_every_address_selects_its_bank_from_any_bank(void) {
    for (int from = 0; from < 16; from++) {
        for (int n = 0; n < 16; n++) {
            direct16(0);
            bbc_module_read(&mod, (uint16_t)(0x3FF0 + from));
            ASSERT_EQ(from, mod.bank);
            ASSERT_EQ_FMT(n, bbc_module_read(&mod, (uint16_t)(0x3FF0 + n)), "%d");
            ASSERT_EQ(n, mod.bank);
        }
    }
    PASS();
}

TEST direct16_bfef_and_the_cc128_zones_do_not_switch(void) {
    direct16(0);
    bbc_module_read(&mod, 0x3FF5);
    uint16_t quiet[] = { 0x3FEF, 0x3FE0, 0x3FC0, 0x3F00, 0x0000 };
    for (unsigned i = 0; i < sizeof quiet / sizeof quiet[0]; i++) {
        ASSERT_EQ(5, bbc_module_read(&mod, quiet[i]));
        ASSERT_EQ(5, mod.bank);
    }
    PASS();
}

TEST rom_form_ignores_writes_and_writes_never_switch(void) {
    cc128(0);
    bbc_module_write(&mod, 0x0100, 0xAA);
    ASSERT_EQ(0, bbc_module_read(&mod, 0x0100));
    bbc_module_write(&mod, 0x3FC0, 0xAA);       /* a write in a zone */
    ASSERT_EQ(0, mod.bank);
    direct16(0);
    bbc_module_write(&mod, 0x3FF3, 0xAA);
    ASSERT_EQ(0, mod.bank);
    PASS();
}

TEST ram_form_writes_the_selected_bank(void) {
    cc128(1);
    bbc_module_read(&mod, 0x3F80);              /* bank 3 */
    bbc_module_write(&mod, 0x0100, 0xAA);
    bbc_module_write(&mod, 0x3FE0, 0xBB);       /* writes never switch, even at $3FE0 */
    ASSERT_EQ(3, mod.bank);
    ASSERT_EQ(0xAA, mod.data[3 * BBC_MODULE_BANK_SIZE + 0x100]);
    ASSERT_EQ(0xBB, mod.data[3 * BBC_MODULE_BANK_SIZE + 0x3FE0]);
    ASSERT_EQ(0, mod.data[0x100]);
    direct16(1);
    bbc_module_read(&mod, 0x3FFC);              /* bank 12 */
    bbc_module_write(&mod, 0x3FF1, 0xCC);
    ASSERT_EQ(12, mod.bank);
    ASSERT_EQ(0xCC, mod.data[12 * BBC_MODULE_BANK_SIZE + 0x3FF1]);
    PASS();
}

TEST init_selects_the_power_on_bank_and_empties_the_module(void) {
    bbc_module_init(&mod_chip, &mod, BBC_MODULE_CC128, 0, 5);
    ASSERT_EQ(5, mod.bank);
    ASSERT_EQ(0xFF, bbc_module_read(&mod, 0x0000));  /* an erased ROM */
    bbc_module_init(&mod_chip, &mod, BBC_MODULE_DIRECT16, 1, 15);
    ASSERT_EQ(15, mod.bank);
    ASSERT_EQ(0x00, bbc_module_read(&mod, 0x0000));  /* the RAM form starts empty */
    PASS();
}

TEST load_puts_bank_0_first_and_refuses_too_large(void) {
    char path[] = "/tmp/bbc_module_testXXXXXX";
    int fd = mkstemp(path);
    ASSERT(fd >= 0);
    FILE *f = fdopen(fd, "wb");
    for (int b = 0; b < 3; b++)
        for (int i = 0; i < BBC_MODULE_BANK_SIZE; i++) fputc(0x10 + b, f);
    fclose(f);
    bbc_module_init(&mod_chip, &mod, BBC_MODULE_CC128, 0, 0);
    ASSERT_EQ(3L * BBC_MODULE_BANK_SIZE, bbc_module_load(&mod, path));
    ASSERT_EQ(0x10, bbc_module_read(&mod, 0x0000));
    bbc_module_read(&mod, 0x3FA0);
    ASSERT_EQ(0x12, bbc_module_read(&mod, 0x0000));
    bbc_module_read(&mod, 0x3FE0);
    bbc_module_read(&mod, 0x3F80);
    ASSERT_EQ(0xFF, bbc_module_read(&mod, 0x0000));  /* past the image */

    f = fopen(path, "ab");                      /* 3 + 6 = 9 banks: too large for cc128 */
    for (int i = 0; i < 6 * BBC_MODULE_BANK_SIZE; i++) fputc(0, f);
    fclose(f);
    ASSERT_EQ(-2, bbc_module_load(&mod, path));
    bbc_module_init(&mod_chip, &mod, BBC_MODULE_DIRECT16, 0, 0);
    ASSERT_EQ(9L * BBC_MODULE_BANK_SIZE, bbc_module_load(&mod, path));
    ASSERT_EQ(-1, bbc_module_load(&mod, "/nonexistent/module"));
    remove(path);
    PASS();
}

TEST chip_claims_only_while_selected(void) {
    cc128(1);
    struct bus b;
    bus_init(&b);
    bus_add_chip(&b, &mod_chip);
    uint8_t d = 0x55;
    b.romcs = 0;
    ASSERT_EQ(0, bus_read(&b, 0xBFC0, &d));     /* not selected: no claim, no switch */
    ASSERT_EQ(0, mod.bank);
    ASSERT_EQ(0, bus_write(&b, 0x8000, 0x99));
    b.romcs = 1;
    ASSERT_EQ(1, bus_read(&b, 0xBFC0, &d));
    ASSERT_EQ(1, d);
    ASSERT_EQ(1, bus_write(&b, 0x8000, 0x99));
    ASSERT_EQ(0x99, mod.data[BBC_MODULE_BANK_SIZE]);
    ASSERT_EQ(0, bus_read(&b, 0xC000, &d));     /* outside the window */
    PASS();
}

/* ---- the reads the CPU core really makes, near the direct16 zone ---- */

static uint8_t mem[0x10000];

static uint8_t core_read(uint16_t a) {
    if (a >= 0x8000 && a < 0xC000) return bbc_module_read(&mod, (uint16_t)(a - 0x8000));
    return mem[a];
}

static void core_write(uint16_t a, uint8_t v) {
    if (a >= 0x8000 && a < 0xC000) bbc_module_write(&mod, (uint16_t)(a - 0x8000), v);
    else mem[a] = v;
}

/* An RTS as the last byte before $BFF0. A real NMOS 6502 reads the byte
 * after an RTS opcode (a dummy read of $BFF0, which would select bank 0);
 * the emulator's core makes no dummy reads, so the bank stays. */
TEST rts_before_the_zone_reads_what_the_core_reads(void) {
    direct16(0);
    bbc_module_read(&mod, 0x3FF4);              /* bank 4 */
    mod.data[4 * BBC_MODULE_BANK_SIZE + 0x3FEF] = 0x60;   /* RTS at $BFEF */
    memset(mem, 0, sizeof mem);
    mem[0x01FE] = 0x00;                          /* return to $1001 */
    mem[0x01FF] = 0x10;
    cpu_variant = CPU_NMOS;
    cpu_external_read = core_read;
    cpu_external_write = core_write;
    pc = 0xBFEF;
    sp = 0xFD;
    step6502();
    cpu_external_read = NULL;
    cpu_external_write = NULL;
    ASSERT_EQ_FMT(0x1001, pc, "%04X");
    ASSERT_EQ(4, mod.bank);
    PASS();
}

/* An indexed read: LDA $BFE8,X with X = 8 reads $BFF0 (bank 0) and only it */
TEST indexed_read_reaches_the_zone(void) {
    direct16(0);
    bbc_module_read(&mod, 0x3FF2);              /* bank 2 */
    memset(mem, 0, sizeof mem);
    mem[0x1000] = 0xBD; mem[0x1001] = 0xE8; mem[0x1002] = 0xBF;   /* LDA $BFE8,X */
    cpu_variant = CPU_NMOS;
    cpu_external_read = core_read;
    cpu_external_write = core_write;
    pc = 0x1000;
    x = 0x08;
    step6502();
    cpu_external_read = NULL;
    cpu_external_write = NULL;
    ASSERT_EQ(0, mod.bank);
    ASSERT_EQ(0, a);
    PASS();
}

SUITE(bbc_module_suite) {
    RUN_TEST(cc128_has_eight_banks_and_direct16_sixteen);
    RUN_TEST(cc128_every_zone_selects_its_bank_from_bank_0);
    RUN_TEST(cc128_zones_switch_only_from_bank_0);
    RUN_TEST(cc128_other_addresses_do_not_switch);
    RUN_TEST(cc128_counts_switches_that_change_the_bank);
    RUN_TEST(direct16_every_address_selects_its_bank_from_any_bank);
    RUN_TEST(direct16_bfef_and_the_cc128_zones_do_not_switch);
    RUN_TEST(rom_form_ignores_writes_and_writes_never_switch);
    RUN_TEST(ram_form_writes_the_selected_bank);
    RUN_TEST(init_selects_the_power_on_bank_and_empties_the_module);
    RUN_TEST(load_puts_bank_0_first_and_refuses_too_large);
    RUN_TEST(chip_claims_only_while_selected);
    RUN_TEST(rts_before_the_zone_reads_what_the_core_reads);
    RUN_TEST(indexed_read_reaches_the_zone);
}

GREATEST_MAIN_DEFS();

int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(bbc_module_suite);
    GREATEST_MAIN_END();
}
