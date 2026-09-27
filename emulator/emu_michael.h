#ifndef EMULATOR_EMU_MICHAEL_H
#define EMULATOR_EMU_MICHAEL_H

#include "cli.h"

/* Run the Michael (v2) board: 65C02, 16 KB RAM, VIA at $6000, 20x4
 * HD44780 in 8-bit mode (data on PORTB, E/RW/RS on PA7/PA6/PA5) and
 * ROM at $8000. With --load, <code file> is loaded into RAM there;
 * without it, <code file> is the ROM image. Returns 0 on normal exit,
 * non-zero on error. */
int emu_run_michael(const struct emu_opts *opts);

#endif
