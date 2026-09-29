/* Phase 4b smoke test: parse_args dispatches --machine wendy2c to
 * MACHINE_WENDY2C and defaults --cpu to 65c02. The end-to-end
 * "actually run a ROM through the bus" smoke test lives in
 * test_chip_cpu_65c02.c (added in phase 8). */

#include <stdint.h>
#include <stdio.h>

#include "greatest.h"
#include "../cli.h"
#include "../cpu_core.h"

static int parse(char **argv, struct emu_opts *opts) {
    int argc = 0;
    while (argv[argc] != NULL) argc++;
    return parse_args(argc, argv, opts);
}

TEST machine_wendy2c_default_cpu_65c02(void) {
    char *argv[] = {"emulator", "rom.bin", "--machine", "wendy2c", NULL};
    struct emu_opts opts;
    int rc = parse(argv, &opts);
    ASSERT_EQ_FMT(0, rc, "%d");
    ASSERT_EQ_FMT(MACHINE_WENDY2C, opts.machine, "%d");
    ASSERT_EQ_FMT(CPU_65C02, opts.cpu_variant_opt, "%d");
    PASS();
}

TEST machine_michael_default_cpu_65c02(void) {
    char *argv[] = {"emulator", "prog.bin", "--machine", "michael", NULL};
    struct emu_opts opts;
    int rc = parse(argv, &opts);
    ASSERT_EQ_FMT(0, rc, "%d");
    ASSERT_EQ_FMT(MACHINE_MICHAEL, opts.machine, "%d");
    ASSERT_EQ_FMT(CPU_65C02, opts.cpu_variant_opt, "%d");
    PASS();
}

TEST default_machine_keeps_nmos(void) {
    char *argv[] = {"emulator", "rom.bin", NULL};
    struct emu_opts opts;
    int rc = parse(argv, &opts);
    ASSERT_EQ_FMT(0, rc, "%d");
    ASSERT_EQ_FMT(MACHINE_NMOS_DEFAULT, opts.machine, "%d");
    ASSERT_EQ_FMT(CPU_NMOS, opts.cpu_variant_opt, "%d");
    PASS();
}

SUITE(machine_dispatch_suite) {
    RUN_TEST(machine_wendy2c_default_cpu_65c02);
    RUN_TEST(machine_michael_default_cpu_65c02);
    RUN_TEST(default_machine_keeps_nmos);
}

GREATEST_MAIN_DEFS();
int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(machine_dispatch_suite);
    GREATEST_MAIN_END();
}
