/* emu_run_default: the nmos-default run loop (direct memory, Fake6502 dispatch, console/terminal/throttle). */
#include "emu_run.h"

#include <stdlib.h>
#include <string.h>

#include "cpu_core.h"
#include "console.h"
#include "trace.h"

int emu_run_default(const struct emu_opts *opts) {
    uint64_t next_throttle_check = 10000;
    uint64_t next_repaint_check = 10000;
    const uint64_t max_cycles = opts->cycle_cap;

    while (!done) {
        if (sigtstp_requested) {
            sigtstp_requested = 0;
            if (console_mode || terminal_mode) restore_terminal();
            struct sigaction sa;
            memset(&sa, 0, sizeof(sa));
            sa.sa_handler = SIG_DFL;
            sigemptyset(&sa.sa_mask);
            sigaction(SIGTSTP, &sa, NULL);
            raise(SIGTSTP);
            sa.sa_handler = handle_sigtstp;
            sigaction(SIGTSTP, &sa, NULL);
        }
        if (sigcont_requested) {
            sigcont_requested = 0;
            if (console_mode) enter_console();
            if (console_mode) console_redraw();
            if (terminal_mode) enter_console();
            if (terminal_mode) console_redraw();
        }
        if (sigint_requested) {
            if (exitcode_set == -1) exitcode_set = 130;
            if (console_mode || terminal_mode) restore_terminal();
            done = 1;
            break;
        }
        if (trace_mode) trace_record(pc);
        step6502();

        if (target_mhz > 0 && clockticks6502 >= next_throttle_check) {
            next_throttle_check = clockticks6502 + 10000;
            double emulated_us = (double)clockticks6502 / target_mhz;
            struct timespec now;
            clock_gettime(CLOCK_MONOTONIC, &now);
            double wall_us = (now.tv_sec - start_time.tv_sec) * 1e6
                           + (now.tv_nsec - start_time.tv_nsec) / 1e3;
            double ahead_us = emulated_us - wall_us;
            if (ahead_us > 100.0) {
                struct timespec delay;
                delay.tv_sec = 0;
                delay.tv_nsec = (long)(ahead_us * 1000.0);
                nanosleep(&delay, NULL);
            }
        }

        if (show_repaints && (console_mode || terminal_mode)
            && clockticks6502 >= next_repaint_check) {
            next_repaint_check = clockticks6502 + 10000;
            struct timespec now;
            clock_gettime(CLOCK_MONOTONIC, &now);
            double ms = (now.tv_sec - last_repaint_check.tv_sec) * 1e3
                      + (now.tv_nsec - last_repaint_check.tv_nsec) / 1e6;
            if (ms >= 16.0) {
                last_repaint_check = now;
                repaint_overlay_update(&now);
            }
        }

        if (!console_mode && !terminal_mode && clockticks6502 > max_cycles) {
            fprintf(stderr, "\ndid not terminate within %llu cycles\n",
                    (unsigned long long)max_cycles);
            if (trace_mode) trace_dump("timeout");
            free(arg_addresses);
            fclose(output_file_ptr);
            fclose(input_file_ptr);
            return 1;
        }
    }
    return 0;
}
