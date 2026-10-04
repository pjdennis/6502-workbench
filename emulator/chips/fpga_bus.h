#ifndef EMULATOR_CHIPS_FPGA_BUS_H
#define EMULATOR_CHIPS_FPGA_BUS_H

#include <stdint.h>
#include <stdio.h>
#include "../bus.h"
#include "via_6522.h"

/* The Michael FPGA bus (docs/michael-fpga-bus-plan.md), as the emulator sees it: each rising edge of E
 * (PA0, held low by the board's pull-down while it's an input) is a transfer, chosen by RS (PA5) and RW
 * (PA6). With a log, each is a line: "C hh" (a command), "D hh" (data), "R" (a reply read) or "S" (a status
 * read). The FPGA's commands aren't modelled yet: reads find port B undriven. */

struct fpga_bus_state {
    const struct via_6522_state *via;
    FILE *log;              /* or NULL */
    uint8_t e_was;
    uint32_t transfers;
};

void fpga_bus_init(struct chip *chip, struct fpga_bus_state *state, const struct via_6522_state *via, FILE *log);

#endif
