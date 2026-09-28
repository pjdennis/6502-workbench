#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <errno.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <time.h>
#include <setjmp.h>

#include "file_io.h"
#include "console.h"
#include "cpu_core.h"
#include "trace.h"
#include "cli.h"
#include "emu_run.h"
#include "emu_wendy2c.h"
#include "emu_michael.h"
#include "stubs.h"
#include "direct_io.h"
#include "tty_alt_screen.h"

#define STDIN_FILENO  0
#define STDOUT_FILENO 1


uint8_t memory[0x10001];

FILE* input_file_ptr;
FILE* output_file_ptr;
int con_eof_flag = 0;

int arg_count;
uint16_t* arg_addresses;

int done = 0;
int exitcode_set = -1;
int error_output_started = 0;  // Track if emulated program wrote to stderr
int server_mode_active = 0;
jmp_buf server_abort_jmp;
int console_mode = 0;
int terminal_mode = 0;
int direct_io = 0;                // --direct-io (direct_io.h)
int strict_api = 0;               // --strict-api (stubs.h)
static uint8_t scr_a;             // the A argument of the pending screen call
int terminal_interactive = 0;
FILE* serial_input_file = NULL;
FILE* serial_output_file = NULL;
FILE* stderr_capture_file = NULL;
double target_mhz = 0.0;
double cpu_mhz = 0.0;
int serial_baud = 0;
/* --pace-mask/--pace-log/--pace-polls: unbatched key delivery for tests
 * (standard --input mode only; see cli.h) */
static unsigned char *pace_mask = NULL;
static long pace_mask_len = 0;
static long pace_in = 0;          /* input bytes read so far */
static int pace_polls = 2000;
static int pace_remaining = 0;    /* con_ready polls left in the current pause */
static FILE *pace_log = NULL;
static unsigned wait_ms = 0;      /* wait_ready's timeout, set through port_wait_lo/hi */
int override_rows = 0;
int override_cols = 0;
struct timespec start_time;
volatile sig_atomic_t sigint_requested = 0;
volatile sig_atomic_t sigtstp_requested = 0;
volatile sig_atomic_t sigcont_requested = 0;
int server_mode = 0;
struct timespec last_repaint_check;

void get_terminal_size(int *rows, int *cols);

void restore_terminal() {
    /* tty_alt_screen_leave is idempotent -- a no-op if we never entered
     * the alt screen -- so this is safe to register via atexit() from
     * any caller that puts the terminal into raw mode. */
    tty_alt_screen_leave();
}

void setup_raw_terminal() {
    tty_alt_screen_enter();
}

void enter_console() {
    int rows, cols;
    get_terminal_size(&rows, &cols);
    console_resize(rows, cols);
    setup_raw_terminal();
}

void handle_sigint(int sig) {
    (void)sig;
    sigint_requested = 1;
}

void handle_sigtstp(int sig) {
    (void)sig;
    sigtstp_requested = 1;
}

void handle_sigcont(int sig) {
    (void)sig;
    sigcont_requested = 1;
}

/* Install the minimum signal/atexit wiring that any mode putting the
 * terminal into raw mode + alt screen needs:
 *  - atexit(restore_terminal) so abnormal exits (exit(), main return)
 *    still leave the user's terminal in a usable state.
 *  - A SIGINT handler that sets sigint_requested, so Ctrl-C reaches
 *    the run loop and triggers a clean tty_alt_screen_leave() instead
 *    of the default action (which would kill the process with the
 *    cursor still hidden on the alt screen).
 *
 * Idempotent: safe to call from multiple setup paths. Used by
 * --console, --terminal (interactive), and wendy2c --live. */
void install_tty_cleanup_handlers(void) {
    static int atexit_registered = 0;
    if (!atexit_registered) {
        atexit(restore_terminal);
        atexit_registered = 1;
    }
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sigemptyset(&sa.sa_mask);
    sa.sa_handler = handle_sigint;
    sigaction(SIGINT, &sa, NULL);
}

/* Install SIGTSTP/SIGCONT handlers so Ctrl-Z / fg flow through
 * sigtstp_requested / sigcont_requested. The caller's run loop is
 * responsible for honouring those flags (restore terminal + raise
 * SIGTSTP with the default handler on stop; re-enter and redraw on
 * resume). Used by --console and --terminal interactive; --live does
 * not currently handle job control. */
void install_tty_jobcontrol_handlers(void) {
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sigemptyset(&sa.sa_mask);
    sa.sa_handler = handle_sigtstp;
    sigaction(SIGTSTP, &sa, NULL);
    sa.sa_handler = handle_sigcont;
    sigaction(SIGCONT, &sa, NULL);
}


void setup_console() {
    install_tty_cleanup_handlers();
    enter_console();
}

int con_byte_ready() {
    fd_set fds;
    struct timeval tv = {0, 0};
    FD_ZERO(&fds);
    FD_SET(STDIN_FILENO, &fds);
    return select(STDIN_FILENO + 1, &fds, NULL, NULL, &tv) > 0;
}

void get_terminal_size(int *rows, int *cols) {
    struct winsize ws;
    if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &ws) == 0 && ws.ws_row > 0) {
        *rows = ws.ws_row;
        *cols = ws.ws_col;
    } else {
        *rows = 24;
        *cols = 80;
    }
    if (override_rows > 0) *rows = override_rows;
    if (override_cols > 0) *cols = override_cols;
}

void emulation_exit(int code) {
    if (server_mode_active) {
        exitcode_set = code;
        longjmp(server_abort_jmp, 1);
    }
    exit(code);
}

// Time spent blocked waiting for input is not emulated time: shift the
// throttle's start time by it, so the CPU does not race to catch up afterwards.
static void exclude_wait_from_throttle(const struct timespec *before) {
    struct timespec after;
    clock_gettime(CLOCK_MONOTONIC, &after);
    start_time.tv_sec += after.tv_sec - before->tv_sec;
    start_time.tv_nsec += after.tv_nsec - before->tv_nsec;
    if (start_time.tv_nsec >= 1000000000L) {
        start_time.tv_sec++;
        start_time.tv_nsec -= 1000000000L;
    }
    if (start_time.tv_nsec < 0) {
        start_time.tv_sec--;
        start_time.tv_nsec += 1000000000L;
    }
}

// A --pace-mask pause ends: log "<input bytes read> <output bytes written>"
static void end_pace_pause(void) {
    pace_remaining = 0;
    if (pace_log) {
        fflush(output_file_ptr);
        fprintf(pace_log, "%ld %ld\n", pace_in, ftell(output_file_ptr));
        fflush(pace_log);
    }
}

// Block until stdin is readable or `us` microseconds of wall time pass;
// returns 1 if stdin became readable
static int select_stdin(double us) {
    if (us < 0) us = 0;
    fd_set fds;
    FD_ZERO(&fds);
    FD_SET(STDIN_FILENO, &fds);
    struct timeval tv;
    tv.tv_sec = (long)(us / 1e6);
    tv.tv_usec = (long)(us - tv.tv_sec * 1e6);
    return select(STDIN_FILENO + 1, &fds, NULL, NULL, &tv) > 0;
}

// Wait in wall time for stdin, keeping the time out of the throttle clock
static int wait_stdin(unsigned ms) {
    struct timespec before;
    clock_gettime(CLOCK_MONOTONIC, &before);
    int ready = select_stdin(ms * 1000.0);
    exclude_wait_from_throttle(&before);
    return ready;
}

static int file_has_byte(FILE *f) {
    int ch = fgetc(f);
    if (ch == EOF) return 0;
    ungetc(ch, f);
    return 1;
}

// wait_ready in terminal mode. With a baud rate the wait is in emulated time:
// the clock jumps to the next modelled arrival or to the deadline instead of
// spinning, and the throttle (if any) then keeps pace with the wall clock.
// Only live input with nothing on the way yet waits in wall time, and the
// emulated clock moves on with it.
static uint8_t serial_wait_ready(unsigned ms) {
    if (serial_baud == 0) {
        if (serial_inject_pos < serial_inject_len) return 0xFF;
        if (terminal_interactive) return wait_stdin(ms) ? 0xFF : 0x00;
        // file input is ready now or never
        return serial_input_file && file_has_byte(serial_input_file) ? 0xFF : 0x00;
    }
    double mhz = cpu_mhz > 0.0 ? cpu_mhz : target_mhz;
    uint64_t deadline = clockticks6502 + (uint64_t)(ms * mhz * 1000.0);
    for (;;) {
        serial_tx_drain();
        if (serial_inject_pos < serial_inject_len) return 0xFF;
        if (serial_rx_count() == 0 && serial_pace_wait_times_out()) {
            clockticks6502 = deadline;  // paced input: the key is not typed yet
            return 0x00;
        }
        serial_rx_fill();
        if (serial_rx_count() > 0) return 0xFF;
        if (clockticks6502 >= deadline || sigint_requested || sigtstp_requested)
            return 0x00;
        uint64_t next = serial_rx_next_arrival();
        if (next != UINT64_MAX) {
            clockticks6502 = next < deadline ? next : deadline;
        } else if (terminal_interactive) {
            struct timespec before, after;
            clock_gettime(CLOCK_MONOTONIC, &before);
            select_stdin((deadline - clockticks6502) / mhz);
            clock_gettime(CLOCK_MONOTONIC, &after);
            double waited_us = (after.tv_sec - before.tv_sec) * 1e6
                             + (after.tv_nsec - before.tv_nsec) / 1e3;
            uint64_t ticks = (uint64_t)(waited_us * mhz);
            clockticks6502 = deadline - clockticks6502 > ticks
                           ? clockticks6502 + ticks : deadline;
        } else {
            clockticks6502 = deadline;  // file input has ended: nothing more comes
        }
    }
}

// wait_ready: until an input byte is ready or `ms` milliseconds pass.
// Returns $FF (ready), $00 (timed out) or $01 (console input has ended).
static uint8_t wait_ready(unsigned ms) {
    if (terminal_mode) return serial_wait_ready(ms);
    if (con_eof_flag) return 0x01;
    if (console_mode) return wait_stdin(ms) ? 0xFF : 0x00;
    // --input: every byte is ready at once, except in a --pace-mask pause:
    // the paced key is not typed yet, so the first wait times out and the
    // program's next request for input ends the pause
    if (pace_remaining > 1) {
        pace_remaining = 1;
        return 0x00;
    }
    if (pace_remaining == 1) end_pace_pause();
    return 0xFF;
}

// One console input byte: 0 (and con_eof_flag set) at end of input.
static uint8_t con_read_byte(void) {
    if (console_mode) {
        struct timespec before;
        clock_gettime(CLOCK_MONOTONIC, &before);
        uint8_t ch;
        int got = read(STDIN_FILENO, &ch, 1);
        if (got < 0 && errno == EINTR && sigint_requested) {
            if (exitcode_set == -1) exitcode_set = 130;
            done = 1;
            return 0;
        }
        exclude_wait_from_throttle(&before);
        if (got == 1) return ch;
        if (got == 0) con_eof_flag = 1;
        return 0;
    }
    int b = fgetc(input_file_ptr);
    if (b == EOF) { con_eof_flag = 1; return 0; }
    if (pace_mask && pace_in < pace_mask_len && pace_mask[pace_in] != '0')
        pace_remaining = pace_polls;
    pace_in++;
    return b;
}

static uint8_t con_wait_ready(uint16_t ms) {
    return wait_ready(ms);
}

uint8_t read6502(uint16_t address) {
    if (address == port_read_b) {                    // read_b
        if (terminal_mode) {
            restore_terminal();
            fprintf(stderr, "Error: read_b not available in terminal mode, use serial_read\n");
            emulation_exit(1);
        }
        int b = fgetc(input_file_ptr);
        if (b == EOF) {
            b = 4;
            fseek(input_file_ptr, 0, SEEK_SET);
        }
        return b;
    } else if (address == port_open) {               // open
        uint16_t address = a | (x << 8);
        return file_open((const char*) (memory + address));
    } else if (address == port_openout) {            // openout
        uint16_t address = a | (x << 8);
        return file_open_for_write((const char*) (memory + address));
    } else if (address == port_read) {               // read
        if (a > 0 && dir_state[a - 1] != NULL) {
            DirState *ds = dir_state[a - 1];
            if (ds->buf_pos >= ds->buf_size) return 4;
            return (uint8_t)ds->buffer[ds->buf_pos++];
        }
        int b = file_read(a);
        if (b == EOF) {
            b = 4;
            fseek(file_handle(a), 0, SEEK_SET);
        }
        return b;
    } else if (address == port_eof_b) {              // eof_b
        if (terminal_mode) {
            restore_terminal();
            fprintf(stderr, "Error: eof_b not available in terminal mode, use serial_read\n");
            emulation_exit(1);
        }
        int b = fgetc(input_file_ptr);
        if (b == EOF) {
            fseek(input_file_ptr, 0, SEEK_SET);
            return 0x80;
        }
        ungetc(b, input_file_ptr);
        return 0;
    } else if (address == port_eof) {                // eof
        if (a > 0 && dir_state[a - 1] != NULL) {
            DirState *ds = dir_state[a - 1];
            return (ds->buf_pos >= ds->buf_size) ? 0x80 : 0x00;
        }
        FILE *f = file_handle(a);
        int b = fgetc(f);
        if (b == EOF) {
            fseek(f, 0, SEEK_SET);
            return 0x80;
        }
        ungetc(b, f);
        return 0;
    } else if (address == port_opendir) {            // opendir
        uint16_t addr = a | (x << 8);
        return dir_open((const char*)(memory + addr));
    } else if (address == port_argc) {               // argc
        return arg_count;
    } else if (address == port_argv_l) {             // argvl
        if (a >= arg_count) {
            restore_terminal();
            fprintf(stderr, "Argument %i does not exist\n", (int) a);
            emulation_exit(1);
        }
        return arg_addresses[a] & 0xff;
    } else if (address == port_argv_h) {             // argvh
        if (a >= arg_count) {
            restore_terminal();
            fprintf(stderr, "Argument %i does not exist\n", (int) a);
            emulation_exit(1);
        }
        return arg_addresses[a] >> 8;
    } else if (address == port_con_read) {             // con_read
        if (terminal_mode) {
            restore_terminal();
            fprintf(stderr, "Error: con_read not available in terminal mode, use serial_read\n");
            emulation_exit(1);
        }
        if (direct_io) {
            static const struct direct_io_input con_input = { con_read_byte, con_wait_ready };
            return direct_io_read_key(&con_input);
        }
        return con_read_byte();
    } else if (address == port_term_rows) {           // term_rows (a byte: capped at 255)
        int rows, cols;
        get_terminal_size(&rows, &cols);
        return rows > 255 ? 255 : (uint8_t)rows;
    } else if (address == port_term_cols) {           // term_cols (a byte: capped at 255)
        int rows, cols;
        get_terminal_size(&rows, &cols);
        return cols > 255 ? 255 : (uint8_t)cols;
    } else if (address == port_con_ready) {           // con_ready
        if (terminal_mode) {
            restore_terminal();
            fprintf(stderr, "Error: con_ready not available in terminal mode, use serial_read\n");
            emulation_exit(1);
        }
        // $FF = byte ready, $00 = none yet, $01 = end of input
        if (direct_io && direct_io_pending()) return 0xFF;
        if (con_eof_flag) return 0x01;
        if (console_mode) return con_byte_ready() ? 0xFF : 0x00;
        if (pace_remaining > 0) {
            if (--pace_remaining == 0) end_pace_pause();
            return 0x00;
        }
        return 0xFF;
    } else if (address == port_wait_ready) {          // wait_ready
        if (direct_io && direct_io_pending()) return 0xFF;
        return wait_ready(wait_ms);
    } else if (address == port_serial_ready) {        // serial_ready
        if (serial_baud > 0)
            serial_tx_drain();  // drain TX so DSR responses can be injected
        if (serial_inject_pos < serial_inject_len)
            return 0xFF;
        if (serial_baud > 0) {
            serial_rx_fill();
            return serial_rx_head != serial_rx_tail ? 0xFF : 0x00;
        }
        // No baud rate - direct polling
        if (terminal_interactive) {
            return con_byte_ready() ? 0xFF : 0x00;
        } else if (terminal_mode && serial_input_file) {
            int ch = fgetc(serial_input_file);
            if (ch == EOF) return 0x00;
            ungetc(ch, serial_input_file);
            return 0xFF;
        }
        return 0x00;
    } else if (address == port_serial_data) {         // serial_data
        if (serial_inject_pos < serial_inject_len) {
            uint8_t ch = (uint8_t)serial_inject_buf[serial_inject_pos++];
            if (serial_inject_pos >= serial_inject_len) {
                serial_inject_pos = 0;
                serial_inject_len = 0;
            }
            return ch;
        }
        if (serial_baud > 0) {
            serial_rx_fill();
            if (serial_rx_head != serial_rx_tail) {
                uint8_t ch = serial_rx_buf[serial_rx_tail];
                serial_rx_tail = (serial_rx_tail + 1) % SERIAL_BUF_SIZE;
                return ch;
            }
            return 0;
        }
        // No baud rate - direct read
        if (terminal_interactive) {
            struct timespec before;
            clock_gettime(CLOCK_MONOTONIC, &before);
            uint8_t ch;
            int got = read(STDIN_FILENO, &ch, 1);
            if (got < 0 && errno == EINTR && sigint_requested) {
                if (exitcode_set == -1) exitcode_set = 130;
                done = 1;
                return 0;
            }
            exclude_wait_from_throttle(&before);
            if (got == 1) return ch;
            return 0;
        } else if (terminal_mode && serial_input_file) {
            int b = fgetc(serial_input_file);
            if (b == EOF) return 0;
            return (uint8_t)b;
        }
        return 0x00;
    } else if (address == port_serial_write_ready) {  // serial_write_ready
        if (serial_baud > 0) {
            serial_tx_drain();
            return serial_tx_count() < SERIAL_BUF_SIZE - 1 ? 0xFF : 0x00;
        }
        return 0xFF;
    } else if (address == 0xfffe && memory[0xfffe] == 0 && memory[0xffff] == 0) {
        done = 1;
    }/* else if (address == 0xfe) {
        fprintf(stderr, "Accessed address %04x with PC=%04x\n", (int) address, (int) pc);

        FILE* dump_file_ptr = fopen("dump.out", "wb");
        if (!dump_file_ptr) {
            fprintf(stderr, "could not open output file: dump.out\n");
            return 1;
        }

        fwrite(memory, 1, 0x10000, dump_file_ptr);
        fclose(dump_file_ptr);

        exit(1);
    }*/
    return memory[address];
}

// One console output byte (write_b).
static void con_write_byte(uint8_t value) {
    if (console_mode) {
        unsigned char ch = value;
        console_handle_byte(ch);
        if (write(STDOUT_FILENO, &ch, 1) < 0) {
        }
    } else {
        fputc(value, output_file_ptr);
    }
}

void write6502(uint16_t address, uint8_t value) {
    if (address == port_write_b) {                   // write_b
        if (terminal_mode) {
            restore_terminal();
            fprintf(stderr, "Error: write_b not available in terminal mode, use serial_write\n");
            emulation_exit(1);
        }
        con_write_byte(value);
        return;
    } else if (address == port_scr_a) {              // direct-io screen call argument
        scr_a = value;
        return;
    } else if (address == port_scr_op) {             // direct-io screen call
        char seq[DIRECT_IO_SCREEN_MAX];
        int n = direct_io_screen(value, scr_a, y, seq);
        for (int i = 0; i < n; i++) con_write_byte((uint8_t)seq[i]);
        return;
    } else if (address == port_write_d) {            // write_d
        if (stderr_capture_file) {
            fputc(value, stderr_capture_file);
        } else {
            if (!error_output_started) {
                fputc('\n', stderr);  // End command line before first error output
                error_output_started = 1;
            }
            fputc(value, stderr);
        }
        return;
    } else if (address == port_close) {              // close
        file_close(value);
	return;
    } else if (address == port_exit) {               // exit
        exitcode_set = value;
        done = 1;
	return;
    } else if (address == port_write) {              // write
        file_write(x, value);
        return;
    } else if (address == port_wait_lo) {            // wait_ready timeout, low
        wait_ms = (wait_ms & 0xFF00) | value;
        return;
    } else if (address == port_wait_hi) {            // wait_ready timeout, high
        wait_ms = (wait_ms & 0x00FF) | (value << 8);
        return;
    } else if (address == port_con_flush) {          // con_flush
        if (terminal_mode) {
            restore_terminal();
            fprintf(stderr, "Error: con_flush not available in terminal mode, use serial_write\n");
            emulation_exit(1);
        }
        fflush(stdout);
        return;
    } else if (address == port_serial_write) {      // serial_write
        if (serial_baud > 0) {
            serial_tx_drain();
            serial_tx_buf[serial_tx_head] = value;
            serial_tx_head = (serial_tx_head + 1) % SERIAL_BUF_SIZE;
            return;
        }
        // No baud rate - direct write
        if (terminal_interactive) {
            unsigned char ch = value;
            if (write(STDOUT_FILENO, &ch, 1) < 0) {
            }
        } else if (terminal_mode && serial_output_file) {
            fputc(value, serial_output_file);
        }
        if (terminal_mode) {
            console_handle_byte(value);
        }
        return;
    }

    memory[address] = value;
    {
        static int watch_init = 0;
        static int watch_addr = -1;
        if (!watch_init) {
            watch_init = 1;
            const char *w = getenv("E6502_WATCH");
            if (w) watch_addr = (int)strtol(w, NULL, 16);
        }
        if (watch_addr >= 0 && address == (uint16_t)watch_addr)
            fprintf(stderr, "[WATCH] write $%02X to $%04X from pc=$%04X\n", value, address, pc);
    }
}

void show_commandline(int argc, char**argv) {
    for (int i = 1; i < argc; i++) {
        fprintf(stderr, "%s ", argv[i]);
    }
}

static int server_main(uint64_t cycle_cap);

int main(int argc, char **argv) {
    struct emu_opts opts;
    int rc = parse_args(argc, argv, &opts);
    if (rc != 0) {
        return rc;
    }
    if (opts.server_main_dispatch) {
        return server_main(opts.cycle_cap);
    }

    if (opts.machine == MACHINE_WENDY2C) {
        return emu_run_wendy2c(&opts);
    }
    if (opts.machine == MACHINE_MICHAEL) {
        return emu_run_michael(&opts);
    }

    /* Mirror parsed values into the existing globals/locals so the rest
     * of main() can stay untouched in this phase. */
    const char *code_filename = opts.code_filename;
    long load_address = opts.load_address;
    const char *input_filename = opts.input_filename;
    const char *output_filename = opts.output_filename;
    const char *error_output_filename = opts.error_output_filename;
    const char *dump_filename = opts.dump_filename;
    int no_dump = opts.no_dump;
    int input_specified = opts.input_specified;
    int output_specified = opts.output_specified;
    console_mode = opts.console_mode;
    terminal_mode = opts.terminal_mode;
    direct_io = opts.direct_io;
    strict_api = opts.strict_api;
    show_repaints = opts.show_repaints;
    server_mode = opts.server_mode;
    override_rows = opts.override_rows;
    override_cols = opts.override_cols;
    target_mhz = opts.target_mhz;
    cpu_mhz = opts.cpu_mhz;
    serial_baud = opts.serial_baud;
    pace_polls = opts.pace_polls;
    if (opts.pace_mask_filename) {
        FILE *f = fopen(opts.pace_mask_filename, "rb");
        if (!f) {
            fprintf(stderr, "could not open pace mask file: %s\n", opts.pace_mask_filename);
            return 1;
        }
        fseek(f, 0, SEEK_END);
        pace_mask_len = ftell(f);
        fseek(f, 0, SEEK_SET);
        pace_mask = malloc(pace_mask_len + 1);
        if (!pace_mask || fread(pace_mask, 1, pace_mask_len, f) != (size_t)pace_mask_len) {
            fprintf(stderr, "could not read pace mask file: %s\n", opts.pace_mask_filename);
            fclose(f);
            return 1;
        }
        fclose(f);
    }
    if (opts.pace_log_filename) {
        pace_log = fopen(opts.pace_log_filename, "w");
        if (!pace_log) {
            fprintf(stderr, "could not open pace log file: %s\n", opts.pace_log_filename);
            return 1;
        }
    }

    if (serial_baud > 0) {
        double effective_cpu_mhz = cpu_mhz > 0.0 ? cpu_mhz : target_mhz;
        serial_cycles_per_byte = (uint64_t)(effective_cpu_mhz * 10000000.0 / serial_baud);
    }
    // --pace-mask: in terminal mode the serial model holds input until the
    // program is idle (console.c); in --input mode read6502 paces con_ready
    if (terminal_mode && pace_mask) serial_pace_start(pace_mask, pace_mask_len);

    if (terminal_mode && !input_specified && !output_specified) {
        terminal_interactive = 1;
    }

    int arg_base = opts.arg_base;

    for (size_t x = 0; x != 0x10001; x++) {
        memory[x] = 0;
    }

    FILE* code_file_ptr = fopen(code_filename, "rb");
    if (!code_file_ptr) {
        fprintf(stderr, "could not open code file: %s\n", code_filename);
        return 1;
    }

    if (load_address < 0) {
        if (fseek(code_file_ptr, 0, SEEK_END) != 0) {
            fprintf(stderr, "could not determine code file size: %s\n", code_filename);
            fclose(code_file_ptr);
            return 1;
        }
        long code_size = ftell(code_file_ptr);
        if (code_size < 0) {
            fprintf(stderr, "could not determine code file size: %s\n", code_filename);
            fclose(code_file_ptr);
            return 1;
        }
        if (code_size > 0x10000) {
            fprintf(stderr, "Code file %s is too large to fit in memory\n", code_filename);
            fclose(code_file_ptr);
            return 1;
        }
        load_address = 0x10000 - code_size;
        if (fseek(code_file_ptr, 0, SEEK_SET) != 0) {
            fprintf(stderr, "could not rewind code file: %s\n", code_filename);
            fclose(code_file_ptr);
            return 1;
        }
    }

    long index = load_address;
    int b;
    while ((b = fgetc(code_file_ptr)) != EOF) {
        if (index > 0xffff) {
            fprintf(stderr,
                    "Code file %s will not fit in memory at the specified load address\n",
		    code_filename);
            fclose(code_file_ptr);
            return 1;
        }
        memory[index++] = b;
    }
    fclose(code_file_ptr);

    if (index < 0xfffe) {
      memory[0xfffd] = memory[index - 1];
      memory[0xfffc] = memory[index - 2];
    }

    size_t p = generate_stubs(memory, terminal_mode, direct_io, strict_api);

    if (console_mode) {
        input_file_ptr = stdin;
        setup_console();
        install_tty_jobcontrol_handlers();
    } else if (terminal_interactive) {
        input_file_ptr = fopen("/dev/null", "rb");
        install_tty_cleanup_handlers();
        setup_raw_terminal();
        install_tty_jobcontrol_handlers();
    } else if (terminal_mode) {
        // Terminal mode with file I/O
        input_file_ptr = fopen("/dev/null", "rb");
        if (input_specified) {
            serial_input_file = fopen(input_filename, "rb");
            if (!serial_input_file) {
                fprintf(stderr, "could not open input file: %s\n", input_filename);
                return 1;
            }
        }
        if (output_specified) {
            serial_output_file = fopen(output_filename, "wb");
            if (!serial_output_file) {
                fprintf(stderr, "could not open output file: %s\n", output_filename);
                if (serial_input_file) fclose(serial_input_file);
                return 1;
            }
        }
    } else {
        input_file_ptr = fopen(input_filename, "rb");
        if (!input_file_ptr) {
            fprintf(stderr, "could not open input file: %s\n", input_filename);
            return 1;
        }
    }

    if (terminal_mode) {
        int rows, cols;
        get_terminal_size(&rows, &cols);
        console_resize(rows, cols);
    }

    if (console_mode) {
        output_file_ptr = stdout;
    } else if (terminal_mode) {
        output_file_ptr = fopen("/dev/null", "wb");
    } else if (strcmp(output_filename, "-") == 0) {
        output_file_ptr = stdout;
    } else {
        output_file_ptr = fopen(output_filename, "wb");
        if (!output_file_ptr) {
            fprintf(stderr, "could not open output file: %s\n", output_filename);
            if (!console_mode) fclose(input_file_ptr);
            return 1;
        }
    }

    if (error_output_filename) {
        stderr_capture_file = fopen(error_output_filename, "wb");
        if (!stderr_capture_file) {
            fprintf(stderr, "could not open error output file: %s\n", error_output_filename);
            return 1;
        }
    }

    files_init(input_file_ptr);

    arg_count = argc - arg_base;
    arg_addresses = malloc(arg_count * sizeof(uint16_t));
    p = ARGV_BASE;   // argv strings live in their own window, not over the stubs
    for (int arg = 0; arg != arg_count; arg++) {
        arg_addresses[arg] = p;
        const char* s = argv[arg_base + arg];
        while (memory[p++] = *s++)
            ;
        if (p > ARGV_TOP) {
            fprintf(stderr,
                    "command-line args too long: argv strings overflow the "
                    "$%04X..$%04X window\n", ARGV_BASE, ARGV_TOP);
            return 1;
        }
    }

    if (!console_mode && !terminal_mode) {
        show_commandline(argc, argv);  // Print command line before emulation (no newline yet)
    }
    reset6502();

    clock_gettime(CLOCK_MONOTONIC, &start_time);
    last_repaint_check = start_time;

    trace_init_from_env();

    {
        int run_rc = emu_run_default(&opts);
        if (run_rc != 0) {
            return run_rc;
        }
    }

    free(arg_addresses);

    int unclosed_files = files_destroy();

    if (serial_baud > 0) serial_tx_flush();
    if (serial_input_file) fclose(serial_input_file);
    if (serial_output_file) fclose(serial_output_file);

    if (!console_mode && !terminal_mode && strcmp(output_filename, "-") != 0) {
        fclose(output_file_ptr);
    }
    if (terminal_mode) {
        fclose(output_file_ptr);
    }

    if (!console_mode) {
        fclose(input_file_ptr);
    }
    if (stderr_capture_file) {
        fclose(stderr_capture_file);
        stderr_capture_file = NULL;
    }

    uint8_t exitcode;
    if (exitcode_set != -1) {
        exitcode = exitcode_set;
    } else {
        uint16_t location = memory[0x100 + sp + 2] + (memory[0x100 + sp + 3] << 8) - 1;
        exitcode = memory[location];
        if (exitcode != 0) {
            if (!error_output_started) {
                fputc('\n', stderr);
                error_output_started = 1;
            }
            fprintf(stderr, "Error: ");
            for (int i = 0; i != 40; i++) {
                uint8_t c = memory[location + 1 + i];
                if (c == 0) break;
                fputc(c, stderr);
            }
            fputc('\n', stderr);
        }
    }

    // If files were left unclosed and no other error occurred, set error exit code
    if (unclosed_files > 0 && exitcode == 0) {
        exitcode = 1;
    }

    // Compute MHz for display
    double display_mhz = 0.0;
    if (target_mhz > 0) {
        display_mhz = target_mhz;
    } else {
        struct timespec end_time;
        clock_gettime(CLOCK_MONOTONIC, &end_time);
        double elapsed_us = (end_time.tv_sec - start_time.tv_sec) * 1e6
                          + (end_time.tv_nsec - start_time.tv_nsec) / 1e3;
        if (elapsed_us > 0) {
            display_mhz = (double)clockticks6502 / elapsed_us;
        }
    }

    // Print final status line (skip in console/terminal mode)
    if (!console_mode && !terminal_mode) {
        if (error_output_started || exitcode != 0) {
            fprintf(stderr, "Exit code %d; Executed %llu cycles at %.1f MHz\n", exitcode, (unsigned long long)clockticks6502, display_mhz);
        } else {
            fprintf(stderr, "executed %llu cycles at %.1f MHz\n", (unsigned long long)clockticks6502, display_mhz);
        }
    }

    if (dump_filename || (exitcode != 0 && !no_dump)) {
        char* auto_dump = NULL;
        if (!dump_filename) {
            // Auto-dump on error: derive filename from code file basename
            const char* base = strrchr(code_filename, '/');
            base = base ? base + 1 : code_filename;
            const char* suffix = ".dump.bin";
            auto_dump = malloc(strlen(base) + strlen(suffix) + 1);
            strcpy(auto_dump, base);
            strcat(auto_dump, suffix);
            dump_filename = auto_dump;
            fprintf(stderr, "Dumping memory to %s\n", dump_filename);
        }
        FILE* dump_file_ptr = fopen(dump_filename, "wb");
        if (!dump_file_ptr) {
            fprintf(stderr, "could not open dump file: %s\n", dump_filename);
            free(auto_dump);
            return 1;
        }
        fwrite(memory, 1, 0x10000, dump_file_ptr);
        fclose(dump_file_ptr);
        free(auto_dump);
    }

    return exitcode;
}

static uint8_t pristine_memory[0x10000];
static uint8_t *keys_buffer = NULL;
static size_t keys_buffer_len = 0;
static char *output_buffer = NULL;
static size_t output_buffer_len = 0;
static char *stderr_buffer = NULL;
static size_t stderr_buffer_len = 0;
static size_t stubs_end;  // address after stubs (where args go)

static int server_load_binary(const char *filename, long load_address) {
    memset(memory, 0, 0x10000);

    FILE *f = fopen(filename, "rb");
    if (!f) {
        fprintf(stderr, "server: could not open binary: %s\n", filename);
        return -1;
    }

    if (load_address < 0) {
        if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return -1; }
        long code_size = ftell(f);
        if (code_size < 0 || code_size > 0x10000) { fclose(f); return -1; }
        load_address = 0x10000 - code_size;
        if (fseek(f, 0, SEEK_SET) != 0) { fclose(f); return -1; }
    }

    long index = load_address;
    int b;
    while ((b = fgetc(f)) != EOF) {
        if (index > 0xffff) { fclose(f); return -1; }
        memory[index++] = b;
    }
    fclose(f);

    if (index < 0xfffe) {
        memory[0xfffd] = memory[index - 1];
        memory[0xfffc] = memory[index - 2];
    }

    stubs_end = generate_stubs(memory, terminal_mode, direct_io, strict_api);
    memcpy(pristine_memory, memory, 0x10000);
    return 0;
}

static int server_main(uint64_t cycle_cap) {
    char line[4096];
    long srv_load_address = -1;
    char srv_input[4096] = "";
    char srv_output[4096] = "";
    char srv_binary[4096] = "";
    int use_inline_keys = 0;
    int use_inline_output = 0;
    int use_inline_stderr = 0;
    char loaded_binary[4096] = "";
    int loaded_terminal_mode = -1;
    int loaded_direct_io = -1;
    int loaded_strict_api = -1;
    long loaded_address = -1;
    char *srv_args[256];
    int srv_arg_count = 0;
    int binary_loaded = 0;

    while (fgets(line, sizeof(line), stdin)) {
        size_t len = strlen(line);
        if (len > 0 && line[len - 1] == '\n') line[--len] = '\0';

        if (strcmp(line, "QUIT") == 0) {
            break;
        } else if (strncmp(line, "BINARY ", 7) == 0) {
            strncpy(srv_binary, line + 7, sizeof(srv_binary) - 1);
            srv_binary[sizeof(srv_binary) - 1] = '\0';
            // Skip reload if same binary, mode, stubs, and load address
            if (binary_loaded &&
                strcmp(srv_binary, loaded_binary) == 0 &&
                terminal_mode == loaded_terminal_mode &&
                direct_io == loaded_direct_io &&
                strict_api == loaded_strict_api &&
                srv_load_address == loaded_address) {
                // Already loaded - skip file I/O
            } else if (server_load_binary(srv_binary, srv_load_address) != 0) {
                fprintf(stderr, "server: failed to load binary\n");
                binary_loaded = 0;
                loaded_binary[0] = '\0';
            } else {
                binary_loaded = 1;
                strncpy(loaded_binary, srv_binary, sizeof(loaded_binary) - 1);
                loaded_binary[sizeof(loaded_binary) - 1] = '\0';
                loaded_terminal_mode = terminal_mode;
                loaded_direct_io = direct_io;
                loaded_strict_api = strict_api;
                loaded_address = srv_load_address;
            }
        } else if (strncmp(line, "LOAD ", 5) == 0) {
            if (strcmp(line + 5, "auto") == 0) {
                srv_load_address = -1;
            } else {
                srv_load_address = strtol(line + 5, NULL, 16);
            }
        } else if (strncmp(line, "ROWS ", 5) == 0) {
            override_rows = (int)strtol(line + 5, NULL, 10);
        } else if (strncmp(line, "COLS ", 5) == 0) {
            override_cols = (int)strtol(line + 5, NULL, 10);
        } else if (strncmp(line, "MODE ", 5) == 0) {
            terminal_mode = strcmp(line + 5, "terminal") == 0 ? 1 : 0;
            direct_io = strcmp(line + 5, "direct") == 0 ? 1 : 0;
        } else if (strncmp(line, "API ", 4) == 0) {
            strict_api = strcmp(line + 4, "strict") == 0 ? 1 : 0;
        } else if (strncmp(line, "INPUT ", 6) == 0) {
            strncpy(srv_input, line + 6, sizeof(srv_input) - 1);
            srv_input[sizeof(srv_input) - 1] = '\0';
        } else if (strncmp(line, "OUTPUT ", 7) == 0) {
            strncpy(srv_output, line + 7, sizeof(srv_output) - 1);
            srv_output[sizeof(srv_output) - 1] = '\0';
        } else if (strncmp(line, "KEYS ", 5) == 0) {
            size_t klen = (size_t)strtol(line + 5, NULL, 10);
            free(keys_buffer);
            keys_buffer = malloc(klen);
            keys_buffer_len = klen;
            // Read exactly klen raw bytes from stdin
            size_t read_so_far = 0;
            while (read_so_far < klen) {
                size_t n = fread(keys_buffer + read_so_far, 1,
                                 klen - read_so_far, stdin);
                if (n == 0) break;
                read_so_far += n;
            }
            use_inline_keys = 1;
            srv_input[0] = '\0';
        } else if (strcmp(line, "INLINE_OUTPUT") == 0) {
            use_inline_output = 1;
            srv_output[0] = '\0';
        } else if (strcmp(line, "INLINE_STDERR") == 0) {
            use_inline_stderr = 1;
        } else if (strncmp(line, "CWD ", 4) == 0) {
            if (chdir(line + 4) != 0) {
                fprintf(stderr, "server: chdir failed: %s\n", line + 4);
            }
        } else if (strncmp(line, "ARG ", 4) == 0) {
            if (srv_arg_count < 256) {
                srv_args[srv_arg_count++] = strdup(line + 4);
            }
        } else if (strcmp(line, "RUN") == 0) {
            if (!binary_loaded) {
                fprintf(stdout, "EXIT 1\n");
                fflush(stdout);
                goto run_cleanup;
            }

            // Restore pristine memory
            memcpy(memory, pristine_memory, 0x10000);

            // Write program arguments into their own RAM window (not over
            // the stubs), matching the one-shot load path above.
            size_t p = ARGV_BASE;
            arg_count = srv_arg_count;
            free(arg_addresses);
            arg_addresses = malloc(arg_count * sizeof(uint16_t));
            for (int arg = 0; arg < arg_count; arg++) {
                arg_addresses[arg] = p;
                const char *s = srv_args[arg];
                while ((memory[p++] = *s++))
                    ;
                if (p > ARGV_TOP) {
                    fprintf(stderr, "server: argv strings overflow the "
                            "$%04X..$%04X window\n", ARGV_BASE, ARGV_TOP);
                    fprintf(stdout, "EXIT 1\n");
                    fflush(stdout);
                    goto run_cleanup;
                }
            }

            // Open I/O
            if (terminal_mode) {
                input_file_ptr = fopen("/dev/null", "rb");
                output_file_ptr = fopen("/dev/null", "wb");
                if (use_inline_keys) {
                    serial_input_file = fmemopen(
                        keys_buffer, keys_buffer_len, "rb");
                } else if (srv_input[0]) {
                    serial_input_file = fopen(srv_input, "rb");
                }
                if (use_inline_output) {
                    free(output_buffer);
                    output_buffer = NULL;
                    output_buffer_len = 0;
                    serial_output_file = open_memstream(
                        &output_buffer, &output_buffer_len);
                } else if (srv_output[0]) {
                    serial_output_file = fopen(srv_output, "wb");
                }
                int rows, cols;
                get_terminal_size(&rows, &cols);
                console_resize(rows, cols);
            } else {
                if (use_inline_keys) {
                    input_file_ptr = fmemopen(
                        keys_buffer, keys_buffer_len, "rb");
                } else {
                    input_file_ptr = fopen(
                        srv_input[0] ? srv_input : "/dev/null", "rb");
                }
                if (use_inline_output) {
                    free(output_buffer);
                    output_buffer = NULL;
                    output_buffer_len = 0;
                    output_file_ptr = open_memstream(
                        &output_buffer, &output_buffer_len);
                } else if (srv_output[0]) {
                    output_file_ptr = fopen(srv_output, "wb");
                } else {
                    output_file_ptr = fopen("/dev/null", "wb");
                }
            }

            files_init(input_file_ptr);

            // Set up inline stderr capture
            if (use_inline_stderr) {
                free(stderr_buffer);
                stderr_buffer = NULL;
                stderr_buffer_len = 0;
                stderr_capture_file = open_memstream(
                    &stderr_buffer, &stderr_buffer_len);
            }

            // Reset CPU and emulation state
            done = 0;
            exitcode_set = -1;
            error_output_started = 0;
            clockticks6502 = 0;
            clockgoal6502 = 0;
            instructions = 0;
            con_eof_flag = 0;
            serial_reset();
            reset6502();

            // Run emulation (setjmp catches exit(1) from emulation errors)
            server_mode_active = 1;
            if (setjmp(server_abort_jmp) == 0) {
                const uint64_t max_cycles = cycle_cap;
                while (!done) {
                    step6502();
                    if (clockticks6502 > max_cycles) {
                        fprintf(stderr, "\nserver: did not terminate within %llu cycles\n",
                                (unsigned long long)max_cycles);
                        done = 1;
                        if (exitcode_set == -1) exitcode_set = 1;
                    }
                }
            } else {
                // Returned from longjmp - emulation aborted
                if (exitcode_set == -1) exitcode_set = 1;
            }
            server_mode_active = 0;

            // Clean up
            files_destroy();
            if (serial_baud > 0) serial_tx_flush();
            if (serial_input_file) { fclose(serial_input_file); serial_input_file = NULL; }
            if (serial_output_file) { fclose(serial_output_file); serial_output_file = NULL; }

            if (terminal_mode) {
                fclose(output_file_ptr);
                output_file_ptr = NULL;
            } else {
                if (output_file_ptr && output_file_ptr != stdout) {
                    fclose(output_file_ptr);
                    output_file_ptr = NULL;
                }
            }
            fclose(input_file_ptr);
            input_file_ptr = NULL;

            // Determine exit code
            uint8_t exitcode;
            if (exitcode_set != -1) {
                exitcode = exitcode_set;
            } else {
                uint16_t location = memory[0x100 + sp + 2]
                    + (memory[0x100 + sp + 3] << 8) - 1;
                exitcode = memory[location];
            }

            fprintf(stdout, "EXIT %d\n", exitcode);
            if (use_inline_output && output_buffer) {
                fprintf(stdout, "OUTPUT %zu\n", output_buffer_len);
                fwrite(output_buffer, 1, output_buffer_len, stdout);
            }
            if (use_inline_stderr) {
                if (stderr_capture_file) {
                    fclose(stderr_capture_file);
                    stderr_capture_file = NULL;
                }
                if (stderr_buffer) {
                    fprintf(stdout, "STDERR %zu\n", stderr_buffer_len);
                    fwrite(stderr_buffer, 1, stderr_buffer_len, stdout);
                } else {
                    fprintf(stdout, "STDERR 0\n");
                }
            }
            fflush(stdout);

run_cleanup:
            // Free args for next run
            for (int j = 0; j < srv_arg_count; j++) {
                free(srv_args[j]);
            }
            srv_arg_count = 0;
            srv_input[0] = '\0';
            srv_output[0] = '\0';
            use_inline_keys = 0;
            use_inline_output = 0;
            use_inline_stderr = 0;
            if (stderr_capture_file) {
                fclose(stderr_capture_file);
                stderr_capture_file = NULL;
            }
        } else {
            fprintf(stderr, "server: unknown command: %s\n", line);
        }
    }

    // Final cleanup
    for (int j = 0; j < srv_arg_count; j++) {
        free(srv_args[j]);
    }
    free(arg_addresses);
    arg_addresses = NULL;
    free(keys_buffer);
    keys_buffer = NULL;
    free(output_buffer);
    output_buffer = NULL;
    free(stderr_buffer);
    stderr_buffer = NULL;

    return 0;
}
