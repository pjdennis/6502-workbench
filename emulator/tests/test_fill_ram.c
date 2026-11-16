/* --fill-ram (fill_ram.h): RAM that is not 0 at power on. The pattern has
 * no zero byte, is not one repeated byte, and is the same on every run; it
 * fills each machine's RAM (banked RAM, sideways RAM, the private RAM and
 * the module's RAM form included) and leaves ROM, the MOS, I/O and empty
 * slots alone. */

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "greatest.h"
#include "../fill_ram.h"
#include "../stubs.h"
#include "../chips/bbc_memory.h"
#include "../chips/bbc_module.h"

TEST pattern_has_no_zero_byte(void) {
    for (uint32_t i = 0; i < 0x100000; i++)
        if (fill_ram_byte(i) == 0) FAILm("a zero byte in the pattern");
    PASS();
}

/* Every value but 0 occurs, so a count or a pointer read from it can be
 * anything; and neighbours differ, so two variables side by side rarely
 * hold the same value and a word is no repeated byte. */
TEST pattern_is_not_one_repeated_byte(void) {
    unsigned seen[256] = {0};
    unsigned same = 0;
    for (uint32_t i = 0; i < 0x10000; i++) {
        seen[fill_ram_byte(i)]++;
        if (fill_ram_byte(i) == fill_ram_byte(i + 1)) same++;
    }
    for (int v = 1; v < 256; v++) ASSERT(seen[v] > 0);
    ASSERT(same < 0x10000 / 64);
    PASS();
}

TEST pattern_is_the_same_every_time(void) {
    uint8_t a[256], b[256];
    fill_ram(a, sizeof a, 0x1234);
    fill_ram(b, sizeof b, 0x1234);
    ASSERT_MEM_EQ(a, b, sizeof a);
    for (int i = 0; i < 256; i++) ASSERT_EQ(fill_ram_byte(0x1234 + i), a[i]);
    PASS();
}

/* The default machine: all of memory but the I/O ports and the vectors
 * ($F000-$F005, $FFE0-$FFFF), which stay 0 as before; the stubs and the
 * program are written over it afterwards. */
TEST default_machine_keeps_its_ports(void) {
    static uint8_t memory[0x10001];
    memset(memory, 0, sizeof memory);
    fill_ram_default(memory);
    for (uint32_t a = 0; a < 0x10000; a++) {
        int io = (a >= 0xF000 && a <= 0xF005) || a >= ARGV_TOP;
        if (io) {
            if (memory[a] != 0) FAILm("a port or vector was filled");
        } else if (memory[a] == 0) {
            FAILm("a byte of RAM is 0");
        }
    }
    ASSERT_EQ(0, memory[0x10000]);
    PASS();
}

TEST bbc_fills_ram_and_leaves_rom(void) {
    static struct bbc_memory_state mem;
    struct chip chip;
    bbc_memory_init(&chip, &mem);
    mem.kind[0] = BBC_SLOT_RAM;
    mem.kind[13] = BBC_SLOT_RAM;
    mem.kind[5] = BBC_SLOT_ROM;
    memset(mem.slot[5], 0x42, BBC_SLOT_SIZE);
    memset(mem.mos, 0x37, sizeof mem.mos);
    fill_ram_bbc(&mem);
    for (int i = 0; i < 0x8000; i++) if (mem.ram[i] == 0) FAILm("main RAM");
    for (int i = 0; i < BBC_PRIVATE_RAM_SIZE; i++) if (mem.private_ram[i] == 0) FAILm("private RAM");
    for (int i = 0; i < BBC_SLOT_SIZE; i++) {
        if (mem.slot[0][i] == 0 || mem.slot[13][i] == 0) FAILm("sideways RAM");
        if (mem.slot[5][i] != 0x42) FAILm("a ROM slot was filled");
        if (mem.slot[7][i] != 0) FAILm("an empty slot was filled");
    }
    for (size_t i = 0; i < sizeof mem.mos; i++) if (mem.mos[i] != 0x37) FAILm("the MOS was filled");
    /* Each part has its own bytes, so a table copied from one to another is noticed */
    ASSERT(memcmp(mem.ram, mem.private_ram, 256) != 0);
    ASSERT(memcmp(mem.slot[0], mem.slot[13], 256) != 0);
    ASSERT(memcmp(mem.ram, mem.slot[0], 256) != 0);
    ASSERT_EQ(0, mem.romsel);
    PASS();
}

TEST bbc_module_fills_only_its_ram_form(void) {
    static struct bbc_module_state mod;
    struct chip chip;
    bbc_module_init(&chip, &mod, BBC_MODULE_DIRECT16, 1, 0);
    fill_ram_bbc_module(&mod);
    for (size_t i = 0; i < sizeof mod.data; i++) if (mod.data[i] == 0) FAILm("the RAM form");
    ASSERT(memcmp(mod.data, mod.data + BBC_MODULE_BANK_SIZE, 256) != 0);
    bbc_module_init(&chip, &mod, BBC_MODULE_DIRECT16, 0, 0);
    fill_ram_bbc_module(&mod);
    for (size_t i = 0; i < sizeof mod.data; i++) if (mod.data[i] != 0xFF) FAILm("the ROM form was filled");
    PASS();
}

SUITE(fill_ram_suite) {
    RUN_TEST(pattern_has_no_zero_byte);
    RUN_TEST(pattern_is_not_one_repeated_byte);
    RUN_TEST(pattern_is_the_same_every_time);
    RUN_TEST(default_machine_keeps_its_ports);
    RUN_TEST(bbc_fills_ram_and_leaves_rom);
    RUN_TEST(bbc_module_fills_only_its_ram_form);
}

GREATEST_MAIN_DEFS();

int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(fill_ram_suite);
    GREATEST_MAIN_END();
}
