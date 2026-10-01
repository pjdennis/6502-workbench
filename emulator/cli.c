/* Command-line parsing and the usage text, printed when run with no arguments (see cli.h). */
#include "cli.h"
#include "cpu_core.h"  /* CPU_NMOS / CPU_65C02 */
#include "chips/glue_michael.h"  /* glue_michael_ram_by_name */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CPU_VARIANT_UNSET (-1)

void emu_opts_init(struct emu_opts *opts) {
    opts->code_filename = NULL;
    opts->load_address = -1;
    opts->input_filename = "/dev/null";
    opts->output_filename = "/dev/null";
    opts->error_output_filename = NULL;
    opts->dump_filename = NULL;
    opts->no_dump = 0;
    opts->input_specified = 0;
    opts->output_specified = 0;
    opts->console_mode = 0;
    opts->terminal_mode = 0;
    opts->direct_io = 0;
    opts->strict_api = 0;
    opts->show_repaints = 0;
    opts->server_mode = 0;
    opts->override_rows = 0;
    opts->override_cols = 0;
    opts->target_mhz = 0.0;
    opts->cpu_mhz = 0.0;
    opts->serial_baud = 0;
    opts->pace_mask_filename = NULL;
    opts->pace_log_filename = NULL;
    opts->pace_polls = 2000;
    opts->arg_base = 0;
    opts->server_main_dispatch = 0;
    opts->machine = MACHINE_NMOS_DEFAULT;
    opts->cpu_variant_opt = CPU_VARIANT_UNSET;
    opts->rom_filename = NULL;
    opts->serial_input_filename = NULL;
    opts->wendy2_prog_filename = NULL;
    opts->kbd_scancodes = NULL;
    opts->kbd_fault = NULL;
    opts->ram_map = NULL;
    opts->keys_filename = NULL;
    opts->key_interval_ms = 0;
    opts->disk_dir = NULL;
    opts->cycle_cap = 200000000ULL;
    opts->cycle_cap_set = 0;
    opts->live = 0;
    opts->wav_filename = NULL;
    opts->audio_live = 0;
    opts->web = 0;
    opts->web_port = 8080;
    opts->web_bind = NULL;
    opts->web_root = NULL;
    opts->serial_link_path = NULL;
    opts->lcd_trace_filename = NULL;
    opts->lcd_panel = LCD_PANEL_16X2_5X8;
}

void emu_opts_usage(FILE *fp) {
    fprintf(fp,
"usage: emulator <code file> [options] [<arguments>]\n"
"   or: emulator --server\n"
"\n"
"options:\n"
"  --load <hex addr>      load address for the code file (hexadecimal)\n"
"  --input <path>         file read from $F006 input port (default /dev/null)\n"
"  --output <path>        file written from $F009 output port (default /dev/null)\n"
"  --error-output <path>  file written from $F00C error port\n"
"  --dump <path>          memory dump path on exit\n"
"  --no-dump              skip the dump-on-exit\n"
"  --console              full-screen console UI\n"
"  --terminal             terminal-emulator UI (mutually exclusive with --console)\n"
"  --direct-io            the program calls the scr_* screen vectors instead of\n"
"                         writing ANSI, and con_read returns key codes instead of\n"
"                         escape sequences; the emulator converts both ways\n"
"  --strict-api           the environment calls keep only what their contracts\n"
"                         say: flags they do not return come back inverted, and\n"
"                         the screen calls change A and Y (tests)\n"
"  --show-repaints        flash on console/terminal repaints (debug)\n"
"  --server               long-running server: as argv[1] dispatches into\n"
"                         server_main; after argv[1] enables one-shot reuse loop\n"
"  --mhz <speed>          wall-clock throttle target; what it means depends on\n"
"                         the machine. nmos-default and michael: the CPU clock\n"
"                         in MHz (michael --live defaults to 2). wendy2c: the\n"
"                         OSC crystal frequency, which the 22V10 PLD halves for\n"
"                         the CPU clock, so --mhz 19.44 matches the real board\n"
"                         (9.72 MHz CPU). Paces --live and non-live runs, except\n"
"                         that michael is paced only with --live.\n"
"  --cpu-mhz <speed>      assumed CPU MHz for --baud timing\n"
"  --baud <rate>          serial-port baud rate (requires --mhz or --cpu-mhz)\n"
"  --pace-mask <path>     test hook: one byte per input byte; after a byte whose\n"
"                         mask byte is not '0' is read, con_ready reports\n"
"                         not-ready for --pace-polls polls (no type-ahead); a\n"
"                         wait_ready in the pause times out. In terminal mode the\n"
"                         input is held before the first byte and after each such\n"
"                         byte until the program is idle with all output sent\n"
"  --pace-log <path>      append \"<input read> <output written>\" as each pause ends\n"
"  --pace-polls N         polls per pause (default 2000)\n"
"  --rows N               override terminal rows\n"
"  --cols N               override terminal cols\n"
"  --machine <name>       'nmos-default' (default), 'wendy2c' or 'michael'\n"
"  --cpu <variant>        'nmos' or '65c02' (wendy2c and michael force '65c02')\n"
"  --rom <path>           wendy2c: ROM image (else falls back to <code file>)\n"
"                         michael: ROM image; with --load, <code file> goes into RAM\n"
"                         there (and without --rom the ROM holds only the vectors:\n"
"                         reset to --load, IRQ to $3F00); without --load, <code\n"
"                         file> is the ROM image\n"
"  --serial-input <path>  wendy2c, michael: bytes pre-queued into the SERIAL_USB chip\n"
"  --wendy2-prog <path>   wendy2c: preload a RAW program into RAM at --load\n"
"                         (default $4000), bank $01 mapped, start there --\n"
"                         skips the slow serial boot for big programs\n"
"  --disk <dir>           wendy2c: host dir backing the $F800+ file-I/O OS calls\n"
"  --kbd-scancodes <list> michael: comma-separated hex bytes the PS/2 keyboard sends\n"
"                         once the program has set it up (e.g. 1c,f0,1c types 'a')\n"
"  --keys <path>          michael: type these keys once the program has set up the\n"
"                         keyboard: text, control codes and ANSI key sequences\n"
"                         (arrows, Home, End, PgUp, PgDn, Insert, Delete)\n"
"  --key-interval MS      michael: milliseconds between typed keys (default 20)\n"
"  --kbd-fault <name>     michael: keyboard board fault -- noedge (CA2 never moves),\n"
"                         noirq (the VIA's IRQ doesn't reach the CPU), noack (no\n"
"                         answer to commands) or resend (every answer is $FE)\n"
"  --ram <decode>         michael: how RAM below the VIA is decoded -- 16k ($0000-$3FFF,\n"
"                         the default), eater (Ben Eater's: writes to $4000-$7FFF also\n"
"                         land in $0000-$3FFF), full (24K at $0000-$5FFF) or mirror8k\n"
"                         (8K at $0000-$1FFF, repeated up to $5FFF)\n"
"  --live                 wendy2c: live ANSI render of LCD, LED, button, VIA pin state\n"
"                         michael: the LCD, with the terminal's keys typed on the\n"
"                         PS/2 keyboard (Ctrl-] quits); paced to 2 MHz or --mhz\n"
"                         (saves the terminal; q/ESC/Ctrl-C to quit; space toggles button)\n"
"  --wav <path>           wendy2c: record the PB7 piezo line to a WAV file\n"
"                         (PCM mono int16 @22050 Hz, high-passed to mimic a small piezo)\n"
"  --audio                wendy2c: play the piezo line live through the host audio device\n"
"  --web                  wendy2c: embedded HTTP+WS server with a browser UI on\n"
"                         http://127.0.0.1:8080/ (override port with --web-port).\n"
"  --web-port N           wendy2c: TCP port for --web (default 8080).\n"
"  --web-bind ADDR        wendy2c: IPv4 bind address for --web (default\n"
"                         127.0.0.1, loopback only). Use 0.0.0.0 to also accept\n"
"                         connections from the LAN; the listen banner prints a\n"
"                         warning when bound non-loopback.\n"
"  --web-root PATH        wendy2c: directory containing index.html/wendy2c.css/.js.\n"
"                         Defaults to <dir-of-argv0>/web.\n"
"  --serial-link PATH     wendy2c: Unix-domain socket for host-driven CB2 line.\n"
"                         A Python client drives bit-level transitions and reset\n"
"                         pulses at emulated-time resolution; see wendy2c_emu_link.py.\n"
"                         Compatible with --web, --live, both, or neither.\n"
"  --cycle-cap N          max cycles before forced exit (decimal; default 200000000;\n"
"                         no cap under --live unless this is given explicitly).\n"
"                         For wendy2c this is oscillator ticks (~2 per CPU cycle);\n"
"                         for nmos-default and --server it is CPU cycles.\n"
"  --lcd-trace PATH       wendy2c, michael (non-live, non-web): append a timestamped LCD frame to\n"
"                         PATH every time the LCD changes during the run. Lets tests assert\n"
"                         on intermediate display states, not just the final frame.\n"
"  --lcd-panel TYPE       wendy2c: which LCD panel to model for the live/web render.\n"
"                         '16x2' (default) -- standard 16-col x 2-row 5x8 module, what\n"
"                         the breadboard ships with. '16x1-5x10' -- 16-col x 1-row module\n"
"                         with 5x10 cells and a 1-pixel gap between the glyph and the\n"
"                         underline cursor row (typical for tall-character 16x1 LCDs).\n"
"                         The firmware still picks its own F-bit; this controls how the\n"
"                         renderer lays out cells, not what the controller stores.\n");
}

/* Helper: --FLAG VALUE. Returns 0 on success, sets *value_out and
 * advances *idx by 2; returns 1 on missing value. */
static int take_str_value(int argc, char **argv, int *idx, const char *flag, const char **value_out) {
    if (*idx + 1 >= argc) {
        fprintf(stderr, "error: %s requires a value\n", flag);
        return 1;
    }
    *value_out = argv[*idx + 1];
    *idx += 2;
    return 0;
}

int parse_args(int argc, char **argv, struct emu_opts *opts) {
    emu_opts_init(opts);

    if (argc < 2) {
        emu_opts_usage(stderr);
        return 1;
    }

    /* --server as first argument: special path. Caller dispatches into
     * server_main and ignores the rest of the struct. */
    if (strcmp(argv[1], "--server") == 0) {
        opts->server_main_dispatch = 1;
        return 0;
    }

    opts->code_filename = argv[1];

    int i = 2;
    while (i < argc && strncmp(argv[i], "--", 2) == 0) {
        if (strcmp(argv[i], "--console") == 0) {
            opts->console_mode = 1;
            i++;
        } else if (strcmp(argv[i], "--direct-io") == 0) {
            opts->direct_io = 1;
            i++;
        } else if (strcmp(argv[i], "--strict-api") == 0) {
            opts->strict_api = 1;
            i++;
        } else if (strcmp(argv[i], "--terminal") == 0) {
            opts->terminal_mode = 1;
            i++;
        } else if (strcmp(argv[i], "--load") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "error: --load requires a value\n");
                return 1;
            }
            opts->load_address = strtol(argv[i + 1], NULL, 16);
            if (opts->load_address < 0 || opts->load_address > 0xffff) {
                fprintf(stderr, "error: --load value must be between 0 and ffff\n");
                return 1;
            }
            i += 2;
        } else if (strcmp(argv[i], "--pace-mask") == 0) {
            if (take_str_value(argc, argv, &i, "--pace-mask", &opts->pace_mask_filename)) return 1;
        } else if (strcmp(argv[i], "--pace-log") == 0) {
            if (take_str_value(argc, argv, &i, "--pace-log", &opts->pace_log_filename)) return 1;
        } else if (strcmp(argv[i], "--pace-polls") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "error: --pace-polls requires a value\n");
                return 1;
            }
            opts->pace_polls = (int)strtol(argv[i + 1], NULL, 10);
            if (opts->pace_polls <= 0) {
                fprintf(stderr, "error: --pace-polls value must be positive\n");
                return 1;
            }
            i += 2;
        } else if (strcmp(argv[i], "--input") == 0) {
            if (take_str_value(argc, argv, &i, "--input", &opts->input_filename)) return 1;
            opts->input_specified = 1;
        } else if (strcmp(argv[i], "--output") == 0) {
            if (take_str_value(argc, argv, &i, "--output", &opts->output_filename)) return 1;
            opts->output_specified = 1;
        } else if (strcmp(argv[i], "--error-output") == 0) {
            if (take_str_value(argc, argv, &i, "--error-output", &opts->error_output_filename)) return 1;
        } else if (strcmp(argv[i], "--dump") == 0) {
            if (take_str_value(argc, argv, &i, "--dump", &opts->dump_filename)) return 1;
        } else if (strcmp(argv[i], "--no-dump") == 0) {
            opts->no_dump = 1;
            i++;
        } else if (strcmp(argv[i], "--rows") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "error: --rows requires a value\n");
                return 1;
            }
            opts->override_rows = (int)strtol(argv[i + 1], NULL, 10);
            if (opts->override_rows <= 0) {
                fprintf(stderr, "error: --rows value must be positive\n");
                return 1;
            }
            i += 2;
        } else if (strcmp(argv[i], "--cols") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "error: --cols requires a value\n");
                return 1;
            }
            opts->override_cols = (int)strtol(argv[i + 1], NULL, 10);
            if (opts->override_cols <= 0) {
                fprintf(stderr, "error: --cols value must be positive\n");
                return 1;
            }
            i += 2;
        } else if (strcmp(argv[i], "--mhz") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "error: --mhz requires a value\n");
                return 1;
            }
            opts->target_mhz = strtod(argv[i + 1], NULL);
            if (opts->target_mhz <= 0.0) {
                fprintf(stderr, "error: --mhz value must be positive\n");
                return 1;
            }
            i += 2;
        } else if (strcmp(argv[i], "--cpu-mhz") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "error: --cpu-mhz requires a value\n");
                return 1;
            }
            opts->cpu_mhz = strtod(argv[i + 1], NULL);
            if (opts->cpu_mhz <= 0.0) {
                fprintf(stderr, "error: --cpu-mhz value must be positive\n");
                return 1;
            }
            i += 2;
        } else if (strcmp(argv[i], "--baud") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "error: --baud requires a value\n");
                return 1;
            }
            opts->serial_baud = (int)strtol(argv[i + 1], NULL, 10);
            if (opts->serial_baud <= 0) {
                fprintf(stderr, "error: --baud value must be positive\n");
                return 1;
            }
            i += 2;
        } else if (strcmp(argv[i], "--show-repaints") == 0) {
            opts->show_repaints = 1;
            i++;
        } else if (strcmp(argv[i], "--server") == 0) {
            opts->server_mode = 1;
            i++;
        } else if (strcmp(argv[i], "--machine") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "error: --machine requires a value\n");
                return 1;
            }
            const char *m = argv[i + 1];
            if (strcmp(m, "nmos-default") == 0) opts->machine = MACHINE_NMOS_DEFAULT;
            else if (strcmp(m, "wendy2c") == 0) opts->machine = MACHINE_WENDY2C;
            else if (strcmp(m, "michael") == 0) opts->machine = MACHINE_MICHAEL;
            else {
                fprintf(stderr, "error: --machine value must be 'nmos-default', 'wendy2c' or 'michael'\n");
                return 1;
            }
            i += 2;
        } else if (strcmp(argv[i], "--rom") == 0) {
            if (take_str_value(argc, argv, &i, "--rom", &opts->rom_filename)) return 1;
        } else if (strcmp(argv[i], "--serial-input") == 0) {
            if (take_str_value(argc, argv, &i, "--serial-input", &opts->serial_input_filename)) return 1;
        } else if (strcmp(argv[i], "--wendy2-prog") == 0) {
            if (take_str_value(argc, argv, &i, "--wendy2-prog", &opts->wendy2_prog_filename)) return 1;
        } else if (strcmp(argv[i], "--kbd-scancodes") == 0) {
            if (take_str_value(argc, argv, &i, "--kbd-scancodes", &opts->kbd_scancodes)) return 1;
        } else if (strcmp(argv[i], "--keys") == 0) {
            if (take_str_value(argc, argv, &i, "--keys", &opts->keys_filename)) return 1;
        } else if (strcmp(argv[i], "--key-interval") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "error: --key-interval requires a value\n");
                return 1;
            }
            opts->key_interval_ms = (int)strtol(argv[i + 1], NULL, 10);
            if (opts->key_interval_ms <= 0) {
                fprintf(stderr, "error: --key-interval value must be positive\n");
                return 1;
            }
            i += 2;
        } else if (strcmp(argv[i], "--kbd-fault") == 0) {
            if (take_str_value(argc, argv, &i, "--kbd-fault", &opts->kbd_fault)) return 1;
            const char *f = opts->kbd_fault;
            if (strcmp(f, "noedge") && strcmp(f, "noirq") && strcmp(f, "noack") && strcmp(f, "resend")) {
                fprintf(stderr, "error: --kbd-fault value must be 'noedge', 'noirq', 'noack' or 'resend'\n");
                return 1;
            }
        } else if (strcmp(argv[i], "--ram") == 0) {
            if (take_str_value(argc, argv, &i, "--ram", &opts->ram_map)) return 1;
            enum glue_michael_ram ram;
            if (glue_michael_ram_by_name(opts->ram_map, &ram) != 0) {
                fprintf(stderr, "error: --ram value must be '16k', 'eater', 'full' or 'mirror8k'\n");
                return 1;
            }
        } else if (strcmp(argv[i], "--disk") == 0) {
            if (take_str_value(argc, argv, &i, "--disk", &opts->disk_dir)) return 1;
        } else if (strcmp(argv[i], "--live") == 0) {
            opts->live = 1;
            i++;
        } else if (strcmp(argv[i], "--wav") == 0) {
            if (take_str_value(argc, argv, &i, "--wav", &opts->wav_filename)) return 1;
        } else if (strcmp(argv[i], "--audio") == 0) {
            opts->audio_live = 1;
            i++;
        } else if (strcmp(argv[i], "--web") == 0) {
            opts->web = 1;
            i++;
        } else if (strcmp(argv[i], "--web-port") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "error: --web-port requires a value\n");
                return 1;
            }
            opts->web_port = (int)strtol(argv[i + 1], NULL, 10);
            if (opts->web_port < 0 || opts->web_port > 65535) {
                fprintf(stderr, "error: --web-port must be 0..65535\n");
                return 1;
            }
            opts->web = 1;  /* setting a port implies --web */
            i += 2;
        } else if (strcmp(argv[i], "--web-bind") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "error: --web-bind requires a value\n");
                return 1;
            }
            opts->web_bind = argv[i + 1];
            opts->web = 1;  /* setting a bind implies --web */
            i += 2;
        } else if (strcmp(argv[i], "--web-root") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "error: --web-root requires a value\n");
                return 1;
            }
            opts->web_root = argv[i + 1];
            i += 2;
        } else if (strcmp(argv[i], "--serial-link") == 0) {
            if (take_str_value(argc, argv, &i, "--serial-link", &opts->serial_link_path)) return 1;
        } else if (strcmp(argv[i], "--lcd-trace") == 0) {
            if (take_str_value(argc, argv, &i, "--lcd-trace", &opts->lcd_trace_filename)) return 1;
        } else if (strcmp(argv[i], "--lcd-panel") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "error: --lcd-panel requires a value\n");
                return 1;
            }
            const char *t = argv[i + 1];
            if (strcmp(t, "16x2") == 0 || strcmp(t, "16x2-5x8") == 0) {
                opts->lcd_panel = LCD_PANEL_16X2_5X8;
            } else if (strcmp(t, "16x1") == 0 || strcmp(t, "16x1-5x10") == 0) {
                opts->lcd_panel = LCD_PANEL_16X1_5X10;
            } else {
                fprintf(stderr, "error: --lcd-panel value must be '16x2' or '16x1-5x10'\n");
                return 1;
            }
            i += 2;
        } else if (strcmp(argv[i], "--cycle-cap") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "error: --cycle-cap requires a value\n");
                return 1;
            }
            char *end;
            unsigned long long v = strtoull(argv[i + 1], &end, 10);
            if (*end != '\0' || v == 0) {
                fprintf(stderr, "error: --cycle-cap value must be a positive decimal integer\n");
                return 1;
            }
            opts->cycle_cap = (uint64_t)v;
            opts->cycle_cap_set = 1;
            i += 2;
        } else if (strcmp(argv[i], "--cpu") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "error: --cpu requires a value\n");
                return 1;
            }
            const char *c = argv[i + 1];
            if (strcmp(c, "nmos") == 0) opts->cpu_variant_opt = CPU_NMOS;
            else if (strcmp(c, "65c02") == 0) opts->cpu_variant_opt = CPU_65C02;
            else {
                fprintf(stderr, "error: --cpu value must be 'nmos' or '65c02'\n");
                return 1;
            }
            i += 2;
        } else {
            fprintf(stderr, "error: unknown option %s\n", argv[i]);
            return 1;
        }
    }

    if (opts->direct_io && (opts->terminal_mode || opts->machine != MACHINE_NMOS_DEFAULT)) {
        fprintf(stderr, "error: --direct-io requires the nmos-default machine, not --terminal\n");
        return 1;
    }
    if (opts->console_mode && opts->terminal_mode) {
        fprintf(stderr, "error: --console and --terminal are mutually exclusive\n");
        return 1;
    }

    if (opts->serial_baud > 0 && opts->cpu_mhz <= 0.0 && opts->target_mhz <= 0.0) {
        fprintf(stderr, "error: --baud requires --cpu-mhz or --mhz\n");
        return 1;
    }

    if (opts->live && opts->machine == MACHINE_NMOS_DEFAULT) {
        fprintf(stderr, "error: --live requires --machine wendy2c or michael\n");
        return 1;
    }
    if (opts->web && opts->machine != MACHINE_WENDY2C) {
        fprintf(stderr, "error: --web currently requires --machine wendy2c\n");
        return 1;
    }
    if (opts->web && opts->live) {
        fprintf(stderr, "error: --web and --live are mutually exclusive\n");
        return 1;
    }

    if ((opts->wav_filename || opts->audio_live)
        && opts->machine != MACHINE_WENDY2C) {
        fprintf(stderr, "error: --wav / --audio currently require --machine wendy2c\n");
        return 1;
    }

    if (opts->serial_link_path && opts->machine != MACHINE_WENDY2C) {
        fprintf(stderr, "error: --serial-link currently requires --machine wendy2c\n");
        return 1;
    }

    if (opts->lcd_trace_filename && opts->machine == MACHINE_NMOS_DEFAULT) {
        fprintf(stderr, "error: --lcd-trace requires --machine wendy2c or michael\n");
        return 1;
    }
    if (opts->lcd_trace_filename && (opts->live || opts->web)) {
        fprintf(stderr, "error: --lcd-trace is incompatible with --live and --web\n");
        return 1;
    }

    if ((opts->kbd_scancodes || opts->kbd_fault || opts->keys_filename || opts->key_interval_ms)
        && opts->machine != MACHINE_MICHAEL) {
        fprintf(stderr, "error: --kbd-scancodes / --kbd-fault / --keys / --key-interval require --machine michael\n");
        return 1;
    }

    if (opts->ram_map && opts->machine != MACHINE_MICHAEL) {
        fprintf(stderr, "error: --ram requires --machine michael\n");
        return 1;
    }

    if (opts->lcd_panel != LCD_PANEL_16X2_5X8 && opts->machine != MACHINE_WENDY2C) {
        fprintf(stderr, "error: --lcd-panel currently requires --machine wendy2c\n");
        return 1;
    }

    /* The bus-model machines are 65C02 boards: --cpu defaults to 65c02
     * and nmos is invalid. */
    if (opts->machine != MACHINE_NMOS_DEFAULT) {
        if (opts->cpu_variant_opt == CPU_VARIANT_UNSET) opts->cpu_variant_opt = CPU_65C02;
        if (opts->cpu_variant_opt == CPU_NMOS) {
            fprintf(stderr, "error: --machine %s requires --cpu 65c02\n",
                    opts->machine == MACHINE_WENDY2C ? "wendy2c" : "michael");
            return 1;
        }
    }
    /* For nmos-default, default --cpu to nmos. */
    if (opts->cpu_variant_opt == CPU_VARIANT_UNSET) {
        opts->cpu_variant_opt = CPU_NMOS;
    }

    opts->arg_base = i;
    return 0;
}
