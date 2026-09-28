#ifndef EMULATOR_PACE_H
#define EMULATOR_PACE_H

#include <stdint.h>
#include <time.h>

/* Wall-clock pacing for the bus-model machines: given a fixed-rate
 * reference (t0, osc0, osc_per_us), sleep enough that emulated osc ticks
 * track wall time. The caller has just stepped a batch; this checks
 * whether the emulator is ahead of the wall clock and sleeps if so.
 * osc_per_us <= 0 means no pacing. Returns the wall time since t0 in
 * nanoseconds (callers use it to schedule renders). */
long emu_pace(const struct timespec *t0, uint64_t osc0, uint64_t osc_now, double osc_per_us);

#endif
