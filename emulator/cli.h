#ifndef EMULATOR_CLI_H
#define EMULATOR_CLI_H

#include <stdint.h>
#include <stdio.h>

/* Machine selection. nmos-default keeps the original direct-memory
 * Fake6502 path; wendy2c and michael route the CPU through the bus/chip
 * model. */
#define MACHINE_NMOS_DEFAULT  0
#define MACHINE_WENDY2C       1
#define MACHINE_MICHAEL       2

/* LCD panel selection for the wendy2c web/live render. Defaults to
 * the standard 16x2 5x8 module shipped on the breadboard; the 16x1
 * 5x10 selection asks the renderer to draw a single-line panel with
 * tall (5x10) cells and a 1-pixel gap between the glyph and the
 * underline cursor row -- the layout of common 16x1 LCD modules.
 * The firmware's chosen F bit (5x10 vs 5x8 font) is independent of
 * this and is reported in the snapshot for diagnostics. */
#define LCD_PANEL_16X2_5X8  0
#define LCD_PANEL_16X1_5X10 1

/* Parsed command-line options for the default (non-server-as-first-arg)
 * code path. Numeric defaults are 0 / -1; string defaults are documented
 * per field. */
struct emu_opts {
    const char *code_filename;          /* positional argv[1], NULL if missing */
    long load_address;                  /* --load HEX; -1 if not specified */
    const char *input_filename;         /* --input PATH; default "/dev/null" */
    const char *output_filename;        /* --output PATH; default "/dev/null" */
    const char *error_output_filename;  /* --error-output PATH; NULL default */
    const char *dump_filename;          /* --dump PATH; NULL default */
    int no_dump;                        /* --no-dump */
    int input_specified;                /* set when --input given */
    int output_specified;               /* set when --output given */
    int console_mode;                   /* --console */
    int terminal_mode;                  /* --terminal */
    int show_repaints;                  /* --show-repaints */
    int server_mode;                    /* --server seen after argv[1] */
    int override_rows;                  /* --rows N */
    int override_cols;                  /* --cols N */
    double target_mhz;                  /* --mhz N */
    double cpu_mhz;                     /* --cpu-mhz N */
    int serial_baud;                    /* --baud N */
    const char *pace_mask_filename;     /* --pace-mask PATH (standard --input mode): one byte per
                                         * input byte; after the program reads input byte i and
                                         * mask[i] != '0', con_ready reports "not ready" for
                                         * pace_polls polls, so the next byte arrives only after
                                         * the program has gone idle. NULL = no pacing. */
    const char *pace_log_filename;      /* --pace-log PATH: each time such a pause elapses, append
                                         * "<input bytes read> <output bytes written>\n". */
    int pace_polls;                     /* --pace-polls N; default 2000 */
    int arg_base;                       /* index in argv where positional args begin */
    int server_main_dispatch;           /* 1 if argv[1] == "--server" */
    int machine;                        /* --machine; MACHINE_NMOS_DEFAULT, MACHINE_WENDY2C or MACHINE_MICHAEL */
    int cpu_variant_opt;                /* --cpu; CPU_NMOS or CPU_65C02 (from cpu_core.h) */
    const char *rom_filename;           /* --rom PATH; wendy2c: NULL falls back to code_filename;
                                         * michael: NULL means a ROM holding only the vectors */
    const char *serial_input_filename;  /* --serial-input PATH; bytes queued into the SERIAL_USB chip */
    const char *wendy2_prog_filename;   /* --wendy2-prog PATH (wendy2c): RAW program preloaded directly
                                         * into RAM at --load (default $4000), bank $01 mapped, CPU
                                         * started there -- skips the slow serial boot for big programs */
    uint64_t cycle_cap;                 /* --cycle-cap N; max cycles before forced exit. Default 200000000.
                                         * For wendy2c this counts oscillator ticks (~2 per CPU cycle);
                                         * for nmos-default and --server it counts CPU cycles. */
    int cycle_cap_set;                  /* 1 iff --cycle-cap was given explicitly (vs. the default). */
    int live;                           /* --live (wendy2c only): live ANSI render of LCD + LED + VIA pins */
    const char *wav_filename;           /* --wav PATH (wendy2c only): write a WAV recording of the PB7 piezo line */
    int audio_live;                     /* --audio (wendy2c only): play piezo audio through the host's audio device */
    int web;                            /* --web (wendy2c only): embedded HTTP+WS server with browser UI */
    int web_port;                       /* --web-port N; default 8080 */
    const char *web_bind;               /* --web-bind ADDR; NULL = 127.0.0.1 (loopback only) */
    const char *web_root;               /* --web-root PATH; NULL = auto-discover next to argv[0] */
    const char *serial_link_path;       /* --serial-link PATH (wendy2c only): Unix socket for host-driven CB2 + reset */
    const char *lcd_trace_filename;     /* --lcd-trace PATH (wendy2c, michael; non-live, non-web): append a
                                         * timestamped LCD frame to PATH every time the LCD changes during
                                         * the run loop. Format: a "--- osc=N cpu=N pc=$NNNN ---" header
                                         * line followed by one "|...|"-bracketed row per LCD row. */
    int lcd_panel;                      /* --lcd-panel; LCD_PANEL_* constants. Default = 16x2 5x8. */
    const char *disk_dir;               /* --disk DIR (wendy2c only): host directory backing the
                                         * $F800+ file-I/O OS calls (the simulated SPI "disk").
                                         * NULL = the OS-call port chip is not installed. */
};

/* Initialize an emu_opts with the documented defaults. */
void emu_opts_init(struct emu_opts *opts);

/* Print the usage message to the given stream. */
void emu_opts_usage(FILE *fp);

/* Parse argv[1..argc-1] into *opts.
 *   - Returns  0 on success.
 *   - Returns >0 (= the exit code the caller should return) on error.
 *     Diagnostic messages are emitted to stderr.
 *   - When argv[1] == "--server", returns 0 with opts->server_main_dispatch=1
 *     and no other fields populated; the caller should dispatch into
 *     server_main and ignore the rest of the struct. */
int parse_args(int argc, char **argv, struct emu_opts *opts);

#endif
