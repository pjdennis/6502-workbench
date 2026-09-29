#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "greatest.h"
#include "../cli.h"

/* Redirect stderr to a captured pipe for assertions on diagnostic text. */
static int saved_stderr_fd = -1;
static int capture_pipe[2] = {-1, -1};

static void capture_stderr_begin(void) {
    saved_stderr_fd = dup(STDERR_FILENO);
    if (pipe(capture_pipe) != 0) abort();
    dup2(capture_pipe[1], STDERR_FILENO);
}

static void capture_stderr_end(char *buf, size_t buf_size) {
    fflush(stderr);
    close(capture_pipe[1]);
    capture_pipe[1] = -1;
    ssize_t n = read(capture_pipe[0], buf, buf_size - 1);
    if (n < 0) n = 0;
    buf[n] = '\0';
    close(capture_pipe[0]);
    capture_pipe[0] = -1;
    dup2(saved_stderr_fd, STDERR_FILENO);
    close(saved_stderr_fd);
    saved_stderr_fd = -1;
}

static int parse(char **argv, struct emu_opts *opts) {
    int argc = 0;
    while (argv[argc] != NULL) argc++;
    return parse_args(argc, argv, opts);
}

TEST cli_empty_argv_errors(void) {
    char *argv[] = {"emulator", NULL};
    struct emu_opts opts;
    char buf[1024] = {0};
    capture_stderr_begin();
    int rc = parse(argv, &opts);
    capture_stderr_end(buf, sizeof(buf));
    ASSERT_EQ_FMT(1, rc, "%d");
    ASSERT(strstr(buf, "usage:") != NULL);
    PASS();
}

TEST cli_server_first_arg_dispatches(void) {
    char *argv[] = {"emulator", "--server", NULL};
    struct emu_opts opts;
    int rc = parse(argv, &opts);
    ASSERT_EQ_FMT(0, rc, "%d");
    ASSERT_EQ_FMT(1, opts.server_main_dispatch, "%d");
    PASS();
}

TEST cli_code_file_only(void) {
    char *argv[] = {"emulator", "prog.bin", NULL};
    struct emu_opts opts;
    int rc = parse(argv, &opts);
    ASSERT_EQ_FMT(0, rc, "%d");
    ASSERT_STR_EQ("prog.bin", opts.code_filename);
    ASSERT_EQ_FMT((long)-1, opts.load_address, "%ld");
    ASSERT_STR_EQ("/dev/null", opts.input_filename);
    ASSERT_STR_EQ("/dev/null", opts.output_filename);
    ASSERT_EQ_FMT(2, opts.arg_base, "%d");
    PASS();
}

TEST cli_unknown_flag_errors(void) {
    char *argv[] = {"emulator", "prog.bin", "--bogus", NULL};
    struct emu_opts opts;
    char buf[1024] = {0};
    capture_stderr_begin();
    int rc = parse(argv, &opts);
    capture_stderr_end(buf, sizeof(buf));
    ASSERT_EQ_FMT(1, rc, "%d");
    ASSERT(strstr(buf, "unknown option --bogus") != NULL);
    PASS();
}

TEST cli_missing_value_errors(void) {
    char *argv[] = {"emulator", "prog.bin", "--mhz", NULL};
    struct emu_opts opts;
    char buf[1024] = {0};
    capture_stderr_begin();
    int rc = parse(argv, &opts);
    capture_stderr_end(buf, sizeof(buf));
    ASSERT_EQ_FMT(1, rc, "%d");
    ASSERT(strstr(buf, "--mhz requires a value") != NULL);
    PASS();
}

TEST cli_mhz_and_baud_combination(void) {
    char *argv[] = {"emulator", "prog.bin",
                    "--mhz", "1.5",
                    "--baud", "115200",
                    NULL};
    struct emu_opts opts;
    int rc = parse(argv, &opts);
    ASSERT_EQ_FMT(0, rc, "%d");
    ASSERT_EQ(1.5, opts.target_mhz);
    ASSERT_EQ_FMT(115200, opts.serial_baud, "%d");
    ASSERT_EQ_FMT(0, opts.cpu_mhz == 0.0 ? 0 : 1, "%d");
    PASS();
}

TEST cli_baud_without_mhz_errors(void) {
    char *argv[] = {"emulator", "prog.bin", "--baud", "9600", NULL};
    struct emu_opts opts;
    char buf[1024] = {0};
    capture_stderr_begin();
    int rc = parse(argv, &opts);
    capture_stderr_end(buf, sizeof(buf));
    ASSERT_EQ_FMT(1, rc, "%d");
    ASSERT(strstr(buf, "--baud requires --cpu-mhz or --mhz") != NULL);
    PASS();
}

TEST cli_console_and_terminal_exclusive(void) {
    char *argv[] = {"emulator", "prog.bin", "--console", "--terminal", NULL};
    struct emu_opts opts;
    char buf[1024] = {0};
    capture_stderr_begin();
    int rc = parse(argv, &opts);
    capture_stderr_end(buf, sizeof(buf));
    ASSERT_EQ_FMT(1, rc, "%d");
    ASSERT(strstr(buf, "mutually exclusive") != NULL);
    PASS();
}

TEST cli_load_hex_parsing(void) {
    char *argv[] = {"emulator", "prog.bin", "--load", "4000", NULL};
    struct emu_opts opts;
    int rc = parse(argv, &opts);
    ASSERT_EQ_FMT(0, rc, "%d");
    ASSERT_EQ_FMT((long)0x4000, opts.load_address, "%ld");
    PASS();
}

TEST cli_load_out_of_range_errors(void) {
    char *argv[] = {"emulator", "prog.bin", "--load", "10000", NULL};
    struct emu_opts opts;
    char buf[1024] = {0};
    capture_stderr_begin();
    int rc = parse(argv, &opts);
    capture_stderr_end(buf, sizeof(buf));
    ASSERT_EQ_FMT(1, rc, "%d");
    ASSERT(strstr(buf, "between 0 and ffff") != NULL);
    PASS();
}

TEST cli_positional_args_arg_base(void) {
    char *argv[] = {"emulator", "prog.bin",
                    "--input", "in.txt",
                    "--output", "out.txt",
                    "arg1", "arg2", NULL};
    struct emu_opts opts;
    int rc = parse(argv, &opts);
    ASSERT_EQ_FMT(0, rc, "%d");
    ASSERT_STR_EQ("in.txt", opts.input_filename);
    ASSERT_STR_EQ("out.txt", opts.output_filename);
    ASSERT_EQ_FMT(1, opts.input_specified, "%d");
    ASSERT_EQ_FMT(1, opts.output_specified, "%d");
    ASSERT_EQ_FMT(6, opts.arg_base, "%d");
    PASS();
}

TEST cli_rows_cols_show_repaints(void) {
    char *argv[] = {"emulator", "prog.bin",
                    "--rows", "40", "--cols", "120",
                    "--show-repaints", NULL};
    struct emu_opts opts;
    int rc = parse(argv, &opts);
    ASSERT_EQ_FMT(0, rc, "%d");
    ASSERT_EQ_FMT(40, opts.override_rows, "%d");
    ASSERT_EQ_FMT(120, opts.override_cols, "%d");
    ASSERT_EQ_FMT(1, opts.show_repaints, "%d");
    PASS();
}

TEST cli_machine_wendy2c_defaults_to_65c02(void) {
    char *argv[] = {"emulator", "prog.bin", "--machine", "wendy2c", NULL};
    struct emu_opts opts;
    int rc = parse(argv, &opts);
    ASSERT_EQ_FMT(0, rc, "%d");
    ASSERT_EQ_FMT(MACHINE_WENDY2C, opts.machine, "%d");
    /* CPU_65C02 is 1 in cpu_core.h */
    ASSERT_EQ_FMT(1, opts.cpu_variant_opt, "%d");
    PASS();
}

TEST cli_machine_default_is_nmos(void) {
    char *argv[] = {"emulator", "prog.bin", NULL};
    struct emu_opts opts;
    int rc = parse(argv, &opts);
    ASSERT_EQ_FMT(0, rc, "%d");
    ASSERT_EQ_FMT(MACHINE_NMOS_DEFAULT, opts.machine, "%d");
    ASSERT_EQ_FMT(0, opts.cpu_variant_opt, "%d");  /* CPU_NMOS */
    PASS();
}

TEST cli_wendy2c_plus_nmos_rejected(void) {
    char *argv[] = {"emulator", "prog.bin",
                    "--machine", "wendy2c",
                    "--cpu", "nmos", NULL};
    struct emu_opts opts;
    char buf[1024] = {0};
    capture_stderr_begin();
    int rc = parse(argv, &opts);
    capture_stderr_end(buf, sizeof(buf));
    ASSERT_EQ_FMT(1, rc, "%d");
    ASSERT(strstr(buf, "wendy2c requires --cpu 65c02") != NULL);
    PASS();
}

TEST cli_explicit_cpu_65c02_on_nmos_default(void) {
    char *argv[] = {"emulator", "prog.bin", "--cpu", "65c02", NULL};
    struct emu_opts opts;
    int rc = parse(argv, &opts);
    ASSERT_EQ_FMT(0, rc, "%d");
    ASSERT_EQ_FMT(MACHINE_NMOS_DEFAULT, opts.machine, "%d");
    ASSERT_EQ_FMT(1, opts.cpu_variant_opt, "%d");
    PASS();
}

TEST cli_unknown_machine_rejected(void) {
    char *argv[] = {"emulator", "prog.bin", "--machine", "atari2600", NULL};
    struct emu_opts opts;
    char buf[1024] = {0};
    capture_stderr_begin();
    int rc = parse(argv, &opts);
    capture_stderr_end(buf, sizeof(buf));
    ASSERT_EQ_FMT(1, rc, "%d");
    ASSERT(strstr(buf, "nmos-default") != NULL);
    PASS();
}

TEST cli_lcd_trace_path_parsed(void) {
    char *argv[] = {"emulator", "prog.bin",
                    "--machine", "wendy2c",
                    "--lcd-trace", "/tmp/lcd.trace", NULL};
    struct emu_opts opts;
    int rc = parse(argv, &opts);
    ASSERT_EQ_FMT(0, rc, "%d");
    ASSERT_STR_EQ("/tmp/lcd.trace", opts.lcd_trace_filename);
    PASS();
}

TEST cli_lcd_trace_default_null(void) {
    char *argv[] = {"emulator", "prog.bin", "--machine", "wendy2c", NULL};
    struct emu_opts opts;
    int rc = parse(argv, &opts);
    ASSERT_EQ_FMT(0, rc, "%d");
    ASSERT(opts.lcd_trace_filename == NULL);
    PASS();
}

TEST cli_lcd_trace_missing_value_errors(void) {
    char *argv[] = {"emulator", "prog.bin",
                    "--machine", "wendy2c",
                    "--lcd-trace", NULL};
    struct emu_opts opts;
    char buf[1024] = {0};
    capture_stderr_begin();
    int rc = parse(argv, &opts);
    capture_stderr_end(buf, sizeof(buf));
    ASSERT_EQ_FMT(1, rc, "%d");
    ASSERT(strstr(buf, "--lcd-trace requires a value") != NULL);
    PASS();
}

TEST cli_lcd_trace_requires_wendy2c(void) {
    char *argv[] = {"emulator", "prog.bin",
                    "--lcd-trace", "/tmp/lcd.trace", NULL};
    struct emu_opts opts;
    char buf[1024] = {0};
    capture_stderr_begin();
    int rc = parse(argv, &opts);
    capture_stderr_end(buf, sizeof(buf));
    ASSERT_EQ_FMT(1, rc, "%d");
    ASSERT(strstr(buf, "--lcd-trace") != NULL);
    ASSERT(strstr(buf, "wendy2c") != NULL);
    PASS();
}

TEST cli_live_accepted_for_michael(void) {
    char *argv[] = {"emulator", "prog.bin", "--machine", "michael", "--live", NULL};
    struct emu_opts opts;
    int rc = parse(argv, &opts);
    ASSERT_EQ_FMT(0, rc, "%d");
    ASSERT_EQ_FMT(1, opts.live, "%d");
    PASS();
}

TEST cli_direct_io_parsed(void) {
    char *argv[] = {"emulator", "prog.bin", "--direct-io", NULL};
    struct emu_opts opts;
    int rc = parse(argv, &opts);
    ASSERT_EQ_FMT(0, rc, "%d");
    ASSERT_EQ_FMT(1, opts.direct_io, "%d");
    PASS();
}

TEST cli_strict_api_parsed(void) {
    char *argv[] = {"emulator", "prog.bin", "--strict-api", NULL};
    struct emu_opts opts;
    int rc = parse(argv, &opts);
    ASSERT_EQ_FMT(0, rc, "%d");
    ASSERT_EQ_FMT(1, opts.strict_api, "%d");
    PASS();
}

TEST cli_direct_io_with_terminal_rejected(void) {
    char *argv[] = {"emulator", "prog.bin", "--direct-io", "--terminal", NULL};
    struct emu_opts opts;
    char buf[1024] = {0};
    capture_stderr_begin();
    int rc = parse(argv, &opts);
    capture_stderr_end(buf, sizeof(buf));
    ASSERT_EQ_FMT(1, rc, "%d");
    ASSERT(strstr(buf, "--direct-io requires") != NULL);
    PASS();
}

TEST cli_kbd_options_parsed_for_michael(void) {
    char *argv[] = {"emulator", "prog.bin", "--machine", "michael",
                    "--kbd-scancodes", "1c,f0,1c", "--kbd-fault", "noack", NULL};
    struct emu_opts opts;
    int rc = parse(argv, &opts);
    ASSERT_EQ_FMT(0, rc, "%d");
    ASSERT_STR_EQ("1c,f0,1c", opts.kbd_scancodes);
    ASSERT_STR_EQ("noack", opts.kbd_fault);
    PASS();
}

TEST cli_keys_and_interval_parsed_for_michael(void) {
    char *argv[] = {"emulator", "prog.bin", "--machine", "michael",
                    "--keys", "k.txt", "--key-interval", "50", NULL};
    struct emu_opts opts;
    int rc = parse(argv, &opts);
    ASSERT_EQ_FMT(0, rc, "%d");
    ASSERT_STR_EQ("k.txt", opts.keys_filename);
    ASSERT_EQ_FMT(50, opts.key_interval_ms, "%d");
    PASS();
}

TEST cli_ram_parsed_for_michael(void) {
    const char *maps[] = {"16k", "eater", "full", "mirror8k"};
    for (unsigned i = 0; i < sizeof maps / sizeof *maps; i++) {
        char *argv[] = {"emulator", "prog.bin", "--machine", "michael", "--ram", (char *)maps[i], NULL};
        struct emu_opts opts;
        ASSERT_EQ_FMT(0, parse(argv, &opts), "%d");
        ASSERT_STR_EQ(maps[i], opts.ram_map);
    }
    PASS();
}

TEST cli_unknown_ram_rejected(void) {
    char *argv[] = {"emulator", "prog.bin", "--machine", "michael", "--ram", "32k", NULL};
    struct emu_opts opts;
    char buf[1024] = {0};
    capture_stderr_begin();
    int rc = parse(argv, &opts);
    capture_stderr_end(buf, sizeof(buf));
    ASSERT_EQ_FMT(1, rc, "%d");
    ASSERT(strstr(buf, "--ram") != NULL);
    PASS();
}

TEST cli_ram_requires_michael(void) {
    char *argv[] = {"emulator", "prog.bin", "--machine", "wendy2c", "--ram", "full", NULL};
    struct emu_opts opts;
    char buf[1024] = {0};
    capture_stderr_begin();
    int rc = parse(argv, &opts);
    capture_stderr_end(buf, sizeof(buf));
    ASSERT_EQ_FMT(1, rc, "%d");
    ASSERT(strstr(buf, "--ram requires --machine michael") != NULL);
    PASS();
}

TEST cli_kbd_options_require_michael(void) {
    char *argv[] = {"emulator", "prog.bin", "--machine", "wendy2c",
                    "--kbd-scancodes", "1c", NULL};
    struct emu_opts opts;
    char buf[1024] = {0};
    capture_stderr_begin();
    int rc = parse(argv, &opts);
    capture_stderr_end(buf, sizeof(buf));
    ASSERT_EQ_FMT(1, rc, "%d");
    ASSERT(strstr(buf, "require --machine michael") != NULL);
    PASS();
}

TEST cli_unknown_kbd_fault_rejected(void) {
    char *argv[] = {"emulator", "prog.bin", "--machine", "michael",
                    "--kbd-fault", "smoke", NULL};
    struct emu_opts opts;
    char buf[1024] = {0};
    capture_stderr_begin();
    int rc = parse(argv, &opts);
    capture_stderr_end(buf, sizeof(buf));
    ASSERT_EQ_FMT(1, rc, "%d");
    ASSERT(strstr(buf, "--kbd-fault value must be") != NULL);
    PASS();
}

TEST cli_pace_options_parsed(void) {
    char *argv[] = {"emulator", "prog.bin",
                    "--pace-mask", "m.bin", "--pace-log", "log.txt",
                    "--pace-polls", "500", NULL};
    struct emu_opts opts;
    int rc = parse(argv, &opts);
    ASSERT_EQ_FMT(0, rc, "%d");
    ASSERT_STR_EQ("m.bin", opts.pace_mask_filename);
    ASSERT_STR_EQ("log.txt", opts.pace_log_filename);
    ASSERT_EQ_FMT(500, opts.pace_polls, "%d");
    PASS();
}

TEST cli_pace_defaults(void) {
    char *argv[] = {"emulator", "prog.bin", NULL};
    struct emu_opts opts;
    int rc = parse(argv, &opts);
    ASSERT_EQ_FMT(0, rc, "%d");
    ASSERT(opts.pace_mask_filename == NULL);
    ASSERT(opts.pace_log_filename == NULL);
    ASSERT_EQ_FMT(2000, opts.pace_polls, "%d");
    PASS();
}

TEST cli_pace_polls_must_be_positive(void) {
    char *argv[] = {"emulator", "prog.bin", "--pace-polls", "0", NULL};
    struct emu_opts opts;
    char buf[1024] = {0};
    capture_stderr_begin();
    int rc = parse(argv, &opts);
    capture_stderr_end(buf, sizeof(buf));
    ASSERT_EQ_FMT(1, rc, "%d");
    ASSERT(strstr(buf, "--pace-polls value must be positive") != NULL);
    PASS();
}

SUITE(cli_suite) {
    RUN_TEST(cli_pace_options_parsed);
    RUN_TEST(cli_pace_defaults);
    RUN_TEST(cli_pace_polls_must_be_positive);
    RUN_TEST(cli_empty_argv_errors);
    RUN_TEST(cli_server_first_arg_dispatches);
    RUN_TEST(cli_code_file_only);
    RUN_TEST(cli_unknown_flag_errors);
    RUN_TEST(cli_missing_value_errors);
    RUN_TEST(cli_mhz_and_baud_combination);
    RUN_TEST(cli_baud_without_mhz_errors);
    RUN_TEST(cli_console_and_terminal_exclusive);
    RUN_TEST(cli_load_hex_parsing);
    RUN_TEST(cli_load_out_of_range_errors);
    RUN_TEST(cli_positional_args_arg_base);
    RUN_TEST(cli_rows_cols_show_repaints);
    RUN_TEST(cli_machine_wendy2c_defaults_to_65c02);
    RUN_TEST(cli_machine_default_is_nmos);
    RUN_TEST(cli_wendy2c_plus_nmos_rejected);
    RUN_TEST(cli_explicit_cpu_65c02_on_nmos_default);
    RUN_TEST(cli_unknown_machine_rejected);
    RUN_TEST(cli_lcd_trace_path_parsed);
    RUN_TEST(cli_lcd_trace_default_null);
    RUN_TEST(cli_lcd_trace_missing_value_errors);
    RUN_TEST(cli_lcd_trace_requires_wendy2c);
    RUN_TEST(cli_live_accepted_for_michael);
    RUN_TEST(cli_direct_io_parsed);
    RUN_TEST(cli_direct_io_with_terminal_rejected);
    RUN_TEST(cli_strict_api_parsed);
    RUN_TEST(cli_kbd_options_parsed_for_michael);
    RUN_TEST(cli_keys_and_interval_parsed_for_michael);
    RUN_TEST(cli_kbd_options_require_michael);
    RUN_TEST(cli_unknown_kbd_fault_rejected);
    RUN_TEST(cli_ram_parsed_for_michael);
    RUN_TEST(cli_unknown_ram_rejected);
    RUN_TEST(cli_ram_requires_michael);
}

GREATEST_MAIN_DEFS();

int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(cli_suite);
    GREATEST_MAIN_END();
}
