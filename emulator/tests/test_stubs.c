/* Tests for the $F006 environment vector table and its stub routines. */

#include <stdint.h>
#include <string.h>

#include "greatest.h"
#include "../stubs.h"

static uint8_t memory[65536];

// Address of the stub routine a vector's JMP goes to
static uint16_t vector_target(uint16_t vec) {
    return memory[vec + 1] | (memory[vec + 2] << 8);
}

TEST every_vector_is_a_jmp(void) {
    memset(memory, 0, sizeof memory);
    generate_stubs(memory, 0);
    for (uint16_t vec = 0xF006; vec <= 0xF03F; vec += 3) {
        ASSERT_EQ_FMT(0x4C, memory[vec], "%02x");
    }
    PASS();
}

TEST stubs_end_below_string_pool(void) {
    // nmos binaries park a read-only string pool from $F0C0 up (stubs.h)
    memset(memory, 0, sizeof memory);
    ASSERT(generate_stubs(memory, 0) <= 0xF0C0);
    ASSERT(generate_stubs(memory, 1) <= 0xF0C0);
    PASS();
}

TEST wait_ready_stores_timeout_then_reads_result(void) {
    memset(memory, 0, sizeof memory);
    generate_stubs(memory, 0);
    uint16_t stub = vector_target(0xF03F);
    const uint8_t expect[] = {
        0x8D, port_wait_lo & 0xFF, port_wait_lo >> 8,        // STA port_wait_lo
        0x8E, port_wait_hi & 0xFF, port_wait_hi >> 8,        // STX port_wait_hi
        0xAD, port_wait_ready & 0xFF, port_wait_ready >> 8,  // LDA port_wait_ready
        0x60,                                                // RTS
    };
    ASSERT_MEM_EQ(expect, &memory[stub], sizeof expect);
    PASS();
}

SUITE(stubs_suite) {
    RUN_TEST(every_vector_is_a_jmp);
    RUN_TEST(stubs_end_below_string_pool);
    RUN_TEST(wait_ready_stores_timeout_then_reads_result);
}

GREATEST_MAIN_DEFS();

int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(stubs_suite);
    GREATEST_MAIN_END();
}
