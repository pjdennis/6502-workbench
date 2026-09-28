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
    generate_stubs(memory, 0, 0, 0);
    for (uint16_t vec = 0xF006; vec <= 0xF03F; vec += 3) {
        ASSERT_EQ_FMT(0x4C, memory[vec], "%02x");
    }
    PASS();
}

TEST stubs_end_below_string_pool(void) {
    // nmos binaries park a read-only string pool from $F0C0 up (stubs.h)
    memset(memory, 0, sizeof memory);
    ASSERT(generate_stubs(memory, 0, 0, 0) <= 0xF0C0);
    ASSERT(generate_stubs(memory, 1, 0, 0) <= 0xF0C0);
    PASS();
}

TEST wait_ready_stores_timeout_then_reads_result(void) {
    memset(memory, 0, sizeof memory);
    generate_stubs(memory, 0, 0, 0);
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

/* --direct-io adds the editor's screen calls after wait_ready: ENV_BASE +
 * $42 on, 3 bytes apart, each storing A and then its op number. */
TEST direct_io_screen_vectors_store_a_then_op(void) {
    memset(memory, 0, sizeof memory);
    generate_stubs(memory, 0, 1, 0);
    for (uint8_t op = 0; op < 13; op++) {
        uint16_t vec = (uint16_t)(0xF042 + op * 3);
        ASSERT_EQ_FMT(0x4C, memory[vec], "%02x");
        uint16_t stub = vector_target(vec);
        const uint8_t expect[] = {
            0x8D, port_scr_a & 0xFF, port_scr_a >> 8,        // STA port_scr_a
            0xA9, op,                                        // LDA #op
            0x8D, port_scr_op & 0xFF, port_scr_op >> 8,      // STA port_scr_op
            0x60,                                            // RTS
        };
        ASSERT_MEM_EQ(expect, &memory[stub], sizeof expect);
    }
    /* The other vectors are unchanged. */
    uint16_t stub = vector_target(0xF03F);
    ASSERT_EQ_FMT(0x8D, memory[stub], "%02x");
    ASSERT_EQ_FMT(port_wait_lo & 0xFF, memory[stub + 1], "%02x");
    PASS();
}

TEST standard_stubs_have_no_screen_vectors(void) {
    memset(memory, 0, sizeof memory);
    generate_stubs(memory, 0, 0, 0);
    uint16_t read_b_stub = vector_target(0xF006);
    ASSERT_EQ_FMT(0xF042, read_b_stub, "%04x");   /* stubs follow wait_ready */
    PASS();
}

/* --strict-api stubs are longer: they still end below the argv strings. */
TEST strict_stubs_end_below_argv(void) {
    memset(memory, 0, sizeof memory);
    ASSERT(generate_stubs(memory, 0, 1, 1) <= ARGV_BASE);
    ASSERT(generate_stubs(memory, 1, 0, 1) <= ARGV_BASE);
    PASS();
}

SUITE(stubs_suite) {
    RUN_TEST(every_vector_is_a_jmp);
    RUN_TEST(stubs_end_below_string_pool);
    RUN_TEST(wait_ready_stores_timeout_then_reads_result);
    RUN_TEST(direct_io_screen_vectors_store_a_then_op);
    RUN_TEST(standard_stubs_have_no_screen_vectors);
    RUN_TEST(strict_stubs_end_below_argv);
}

GREATEST_MAIN_DEFS();

int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(stubs_suite);
    GREATEST_MAIN_END();
}
