/* emu_pace: wall-clock throttle for the bus-model machines (see pace.h). */
#include "pace.h"

long emu_pace(const struct timespec *t0, uint64_t osc0, uint64_t osc_now, double osc_per_us) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    long wall_ns = (long)(now.tv_sec - t0->tv_sec) * 1000000000L
                  + (now.tv_nsec - t0->tv_nsec);
    if (osc_per_us <= 0.0) return wall_ns;
    double emu_us = (double)(osc_now - osc0) / osc_per_us;
    long emu_ns = (long)(emu_us * 1000.0);
    long ahead_ns = emu_ns - wall_ns;
    if (ahead_ns > 200000L /* 0.2 ms */) {
        struct timespec ts = { ahead_ns / 1000000000L, ahead_ns % 1000000000L };
        nanosleep(&ts, NULL);
        clock_gettime(CLOCK_MONOTONIC, &now);
        wall_ns = (long)(now.tv_sec - t0->tv_sec) * 1000000000L
                 + (now.tv_nsec - t0->tv_nsec);
    }
    return wall_ns;
}
