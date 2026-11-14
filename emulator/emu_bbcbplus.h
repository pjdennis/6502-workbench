#ifndef EMULATOR_EMU_BBCBPLUS_H
#define EMULATOR_EMU_BBCBPLUS_H

#include "cli.h"

/* Run the BBC Model B+128 (--machine bbcbplus): the B+ memory map with
 * sideways RAM and ROM images, the banked module, and the emulator's own
 * MOS (bbc_mos.h). After reset it passes --bbc-command to OSCLI or enters
 * the code file loaded at --load. Returns the run's exit status: 0 when
 * the command or program returned, 1 on an error, a fault or a failed
 * --bbc-strict check, 2 at the cycle cap. */
int emu_run_bbcbplus(const struct emu_opts *opts);

#endif
