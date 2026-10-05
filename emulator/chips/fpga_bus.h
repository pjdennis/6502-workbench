#ifndef EMULATOR_CHIPS_FPGA_BUS_H
#define EMULATOR_CHIPS_FPGA_BUS_H

#include <stdint.h>
#include <stdio.h>
#include "../bus.h"
#include "via_6522.h"
#include "fpga_text.h"

/* The Michael FPGA bus (docs/michael-fpga-bus-plan.md), as the emulator sees it: each rising edge of E
 * (PA2, held low by the board's pull-down while it's an input) is a transfer, chosen by RS (PA5) and RW
 * (PA6). With a log, each is a line: "C hh" (a command), "D hh" (data), "R" (a reply read) or "S" (a status
 * read).
 *
 * The FPGA's side is modelled at the level of its commands (hardware/michael/fpga/rtl/bus_control.v): the
 * control commands (NOP, ID, RESET, ECHO), the reply queue and the status byte's sticky bits, GEOMETRY, and
 * text mode's grid (fpga_text.h); the raw display commands are accepted (and refused in text mode, as the
 * FPGA does) but not drawn. A read drives port B with its byte while E is high, unless SOEB (PA4) is low:
 * the keyboard board has port B then (the interlock). */

#define FPGA_REPLY_DEPTH 512

struct fpga_bus_state {
    const struct via_6522_state *via;
    FILE *log;              /* or NULL */
    uint8_t e_was;
    uint32_t transfers;
    /* The FPGA's side */
    uint8_t cmd, args_left, first_arg, sticky, text_mode;
    uint8_t reply[FPGA_REPLY_DEPTH];
    unsigned reply_head, reply_count;
    int absent;             /* unconfigured: transfers are logged, but nothing answers or acts on them */
    int reading, read_rs;   /* a read under way (E high), of the reply queue (read_rs) or the status */
    uint8_t read_value;
    struct fpga_text text;
};

void fpga_bus_init(struct chip *chip, struct fpga_bus_state *state, const struct via_6522_state *via, FILE *log);
/* What the FPGA drives onto port B: 1 and the byte while a read has it, else 0 */
int fpga_bus_output(const struct fpga_bus_state *state, uint8_t *value);
/* The text grid, cursor and reverse cells, if text mode was ever on: "<prefix>: fpga text: ..." lines */
void fpga_bus_report(FILE *fp, const char *prefix, const struct fpga_bus_state *state);

#endif
