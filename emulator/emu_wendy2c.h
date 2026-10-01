#ifndef EMULATOR_EMU_WENDY2C_H
#define EMULATOR_EMU_WENDY2C_H

#include "cli.h"

/* Run the wendy2c machine model: builds the bus with the
 * 22V10 clock, ROM, RAM, VIA, LCD, serial-USB and LED/button chips and a
 * 65C02 on the bus, then steps it (plain, --live, --web or --serial-link
 * per opts). Returns 0 on normal exit, non-zero on error. */
int emu_run_wendy2c(const struct emu_opts *opts);

#endif
