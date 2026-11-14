/* The B+128 memory map (chips/bbc_memory.h): main RAM, ROMSEL and the
 * sideways window, sideways RAM, ROM images, empty slots, the private RAM,
 * the MOS ROM and I/O, and the module answering only in its slot. */

#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#include "greatest.h"
#include "../bus.h"
#include "../chips/bbc_memory.h"
#include "../chips/bbc_module.h"

static struct bbc_memory_state mem;
static struct bbc_module_state mod;
static struct chip mem_chip, mod_chip;
static struct bus b;

static void setup(int module_slot) {
    bbc_memory_init(&mem_chip, &mem);
    bus_init(&b);
    if (module_slot >= 0) {
        bbc_module_init(&mod_chip, &mod, BBC_MODULE_CC128, 1, 0);
        for (int k = 0; k < 8; k++) memset(mod.data + k * BBC_MODULE_BANK_SIZE, 0xA0 + k, BBC_MODULE_BANK_SIZE);
        mem.kind[module_slot] = BBC_SLOT_MODULE;
        bus_add_chip(&b, &mod_chip);
    }
    bus_add_chip(&b, &mem_chip);
}

/* An access as the machine makes it: decode, then the chips; an unclaimed
 * read finds the open bus, and every access leaves its byte there. */
static uint8_t rd(uint16_t a) {
    b.addr = a;
    b.rwb = 1;
    bbc_memory_decode(&b, &mem);
    uint8_t d = mem.open_bus;
    bus_read(&b, a, &d);
    mem.open_bus = d;
    return d;
}

static void wr(uint16_t a, uint8_t v) {
    b.addr = a;
    b.rwb = 0;
    bbc_memory_decode(&b, &mem);
    bus_write(&b, a, v);
    mem.open_bus = v;
}

TEST main_ram_reads_back(void) {
    setup(-1);
    wr(0x0000, 0x11);
    wr(0x7FFF, 0x22);
    ASSERT_EQ(0x11, rd(0x0000));
    ASSERT_EQ(0x22, rd(0x7FFF));
    PASS();
}

TEST romsel_selects_the_slot_in_the_window(void) {
    setup(-1);
    for (int s = 0; s < BBC_SLOTS; s++) {
        mem.kind[s] = BBC_SLOT_ROM;
        memset(mem.slot[s], 0x40 + s, BBC_SLOT_SIZE);
    }
    for (int s = 0; s < BBC_SLOTS; s++) {
        wr(BBC_ROMSEL, (uint8_t)s);
        ASSERT_EQ(s, mem.romsel);
        ASSERT_EQ(0x40 + s, rd(0x8000));
        ASSERT_EQ(0x40 + s, rd(0xBFFF));
    }
    wr(BBC_ROMSEL, 0x73);               /* bits 4-6 are not the slot */
    ASSERT_EQ(0x43, rd(0x8000));
    PASS();
}

TEST romsel_is_write_only_and_mirrored(void) {
    setup(-1);
    mem.kind[5] = BBC_SLOT_ROM;
    memset(mem.slot[5], 0x55, BBC_SLOT_SIZE);
    wr(0xFE38, 5);                      /* $FE30 and its mirror $FE38 */
    ASSERT_EQ(5, mem.romsel);
    ASSERT_EQ(0x55, rd(0x9000));
    uint16_t others[] = { 0xFE31, 0xFE33, 0xFE34, 0xFE37, 0xFE3C, 0xFE3F, 0xFE40, 0xFE2F };
    for (unsigned i = 0; i < sizeof others / sizeof others[0]; i++) {
        wr(others[i], 9);               /* not ROMSEL ($FE34 is the shadow select) */
        ASSERT_EQ(5, mem.romsel);
    }
    wr(0xFE30, 6);
    ASSERT_EQ(6, mem.romsel);
    rd(0x1234);                         /* a read of ROMSEL finds the open bus */
    mem.open_bus = 0x5A;
    ASSERT_EQ(0x5A, rd(BBC_ROMSEL));
    PASS();
}

TEST sideways_ram_is_written_through_the_window_only_when_selected(void) {
    setup(-1);
    mem.kind[0] = BBC_SLOT_RAM;
    mem.kind[1] = BBC_SLOT_RAM;
    wr(BBC_ROMSEL, 0);
    wr(0x8000, 0xAA);
    wr(0xBFFF, 0xBB);
    wr(BBC_ROMSEL, 1);
    wr(0x8000, 0xCC);
    ASSERT_EQ(0xCC, rd(0x8000));
    wr(BBC_ROMSEL, 0);
    ASSERT_EQ(0xAA, rd(0x8000));
    ASSERT_EQ(0xBB, rd(0xBFFF));
    ASSERT_EQ(0xAA, mem.slot[0][0]);
    ASSERT_EQ(0xCC, mem.slot[1][0]);
    PASS();
}

TEST rom_slots_ignore_writes(void) {
    setup(-1);
    mem.kind[7] = BBC_SLOT_ROM;
    mem.slot[7][0] = 0x12;
    wr(BBC_ROMSEL, 7);
    wr(0x8000, 0x99);
    ASSERT_EQ(0x12, rd(0x8000));
    PASS();
}

TEST empty_slots_read_the_open_bus(void) {
    setup(-1);
    wr(BBC_ROMSEL, 3);
    wr(0x0010, 0x80);                   /* the bus last carried $80 */
    ASSERT_EQ(0x80, rd(0x8123));
    mem.open_bus = 0x37;
    ASSERT_EQ(0x37, rd(0xA000));
    wr(0x8000, 0x99);                   /* dropped */
    mem.open_bus = 0x00;
    ASSERT_EQ(0x00, rd(0x8000));
    PASS();
}

TEST private_ram_covers_8000_to_afff_with_bit_7(void) {
    setup(-1);
    mem.kind[12] = BBC_SLOT_RAM;
    wr(BBC_ROMSEL, 12);
    wr(0x8000, 0x01);
    wr(0xB000, 0x02);
    wr(BBC_ROMSEL, 0x80 | 12);
    ASSERT_EQ(0x00, rd(0x8000));        /* private RAM, empty */
    wr(0x8000, 0x11);
    wr(0xAFFF, 0x22);
    ASSERT_EQ(0x02, rd(0xB000));        /* still the slot */
    wr(0xB000, 0x33);
    ASSERT_EQ(0x11, mem.private_ram[0]);
    ASSERT_EQ(0x22, mem.private_ram[0x2FFF]);
    wr(BBC_ROMSEL, 12);
    ASSERT_EQ(0x01, rd(0x8000));        /* the slot's RAM was not touched */
    ASSERT_EQ(0x33, rd(0xB000));
    PASS();
}

TEST mos_rom_and_io(void) {
    setup(-1);
    mem.mos[0x0000] = 0xC0;
    mem.mos[0x3FFF] = 0xFF;
    mem.mos[0x3C00] = 0x77;             /* $FC00: I/O, not the ROM */
    ASSERT_EQ(0xC0, rd(0xC000));
    ASSERT_EQ(0xFF, rd(0xFFFF));
    wr(0xC000, 0x00);
    ASSERT_EQ(0xC0, rd(0xC000));
    mem.open_bus = 0x42;
    ASSERT_EQ(0x42, rd(0xFC00));
    mem.open_bus = 0x43;
    ASSERT_EQ(0x43, rd(0xFEFF));
    PASS();
}

TEST module_answers_only_in_its_slot(void) {
    setup(4);
    mem.kind[5] = BBC_SLOT_RAM;
    wr(BBC_ROMSEL, 5);
    ASSERT_EQ(0x00, rd(0xBFC0));        /* slot 5: no switch */
    ASSERT_EQ(0, mod.bank);
    wr(BBC_ROMSEL, 4);
    ASSERT_EQ(0xA0, rd(0x8000));
    ASSERT_EQ(0xA1, rd(0xBFC0));        /* bank 1, through the bus */
    ASSERT_EQ(1, mod.bank);
    wr(0x8000, 0x5E);                   /* the RAM form */
    ASSERT_EQ(0x5E, mod.data[BBC_MODULE_BANK_SIZE]);
    wr(BBC_ROMSEL, 5);
    wr(0x8000, 0x66);
    ASSERT_EQ(0x5E, mod.data[BBC_MODULE_BANK_SIZE]);
    ASSERT_EQ(0x66, mem.slot[5][0]);
    PASS();
}

TEST private_ram_hides_the_module_below_b000(void) {
    setup(4);
    wr(BBC_ROMSEL, 0x84);
    wr(0x8000, 0x12);                   /* the private RAM, not the module */
    ASSERT_EQ(0x12, rd(0x8000));
    ASSERT_EQ(0xA0, mod.data[0]);
    ASSERT_EQ(0xA0, rd(0xB000));        /* the module still shows above */
    ASSERT_EQ(0xA2, rd(0xBFA0));        /* and still switches there */
    ASSERT_EQ(2, mod.bank);
    PASS();
}

TEST load_rom_image(void) {
    char path[] = "/tmp/bbc_rom_testXXXXXX";
    int fd = mkstemp(path);
    ASSERT(fd >= 0);
    FILE *f = fdopen(fd, "wb");
    fputs("ROM", f);
    fclose(f);
    setup(-1);
    ASSERT_EQ(0, bbc_memory_load_rom(&mem, 9, path));
    ASSERT_EQ(BBC_SLOT_ROM, mem.kind[9]);
    wr(BBC_ROMSEL, 9);
    ASSERT_EQ('R', rd(0x8000));
    ASSERT_EQ(0xFF, rd(0x8003));
    mem.kind[0] = BBC_SLOT_RAM;
    ASSERT_EQ(0, bbc_memory_load_rom(&mem, 0, path));
    ASSERT_EQ(BBC_SLOT_RAM, mem.kind[0]);
    f = fopen(path, "wb");
    for (int i = 0; i <= BBC_SLOT_SIZE; i++) fputc(0, f);
    fclose(f);
    ASSERT_EQ(-2, bbc_memory_load_rom(&mem, 9, path));
    ASSERT_EQ(-1, bbc_memory_load_rom(&mem, 9, "/nonexistent/rom"));
    remove(path);
    PASS();
}

SUITE(bbc_memory_suite) {
    RUN_TEST(main_ram_reads_back);
    RUN_TEST(romsel_selects_the_slot_in_the_window);
    RUN_TEST(romsel_is_write_only_and_mirrored);
    RUN_TEST(sideways_ram_is_written_through_the_window_only_when_selected);
    RUN_TEST(rom_slots_ignore_writes);
    RUN_TEST(empty_slots_read_the_open_bus);
    RUN_TEST(private_ram_covers_8000_to_afff_with_bit_7);
    RUN_TEST(mos_rom_and_io);
    RUN_TEST(module_answers_only_in_its_slot);
    RUN_TEST(private_ram_hides_the_module_below_b000);
    RUN_TEST(load_rom_image);
}

GREATEST_MAIN_DEFS();

int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(bbc_memory_suite);
    GREATEST_MAIN_END();
}
