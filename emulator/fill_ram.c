/* --fill-ram: RAM that is not 0 at power on (see fill_ram.h). */
#include "fill_ram.h"

#include "stubs.h"

uint8_t fill_ram_byte(uint32_t where) {
    /* A 32-bit mix (multiply, xor-shift): each place gets its own byte */
    uint32_t x = where * 0x9E3779B1u + 0x7F4A7C15u;
    x ^= x >> 16;
    x *= 0x85EBCA6Bu;
    x ^= x >> 13;
    x *= 0xC2B2AE35u;
    x ^= x >> 16;
    uint8_t b = (uint8_t)(x >> 24);
    return b ? b : (uint8_t)(0x80 | (x & 0x7F));
}

void fill_ram(uint8_t *ram, size_t size, uint32_t first) {
    for (size_t i = 0; i < size; i++) ram[i] = fill_ram_byte(first + (uint32_t)i);
}

void fill_ram_default(uint8_t *memory) {
    fill_ram(memory, 0xF000, 0);                                    /* $0000-$EFFF */
    fill_ram(memory + 0xF006, ARGV_TOP - 0xF006, 0xF006);            /* $F006-$FFDF */
}

void fill_ram_bbc(struct bbc_memory_state *mem) {
    fill_ram(mem->ram, sizeof mem->ram, 0);
    fill_ram(mem->private_ram, sizeof mem->private_ram, FILL_RAM_BBC_PRIVATE);
    for (int s = 0; s < BBC_SLOTS; s++)
        if (mem->kind[s] == BBC_SLOT_RAM)
            fill_ram(mem->slot[s], BBC_SLOT_SIZE, FILL_RAM_BBC_SLOTS + (uint32_t)s * BBC_SLOT_SIZE);
}

void fill_ram_bbc_module(struct bbc_module_state *module) {
    if (module->ram) fill_ram(module->data, sizeof module->data, FILL_RAM_BBC_MODULE);
}
