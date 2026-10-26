#ifndef EMULATOR_CHIPS_FPGA_BUS_H
#define EMULATOR_CHIPS_FPGA_BUS_H

#include <stdint.h>
#include <stdio.h>
#include "../bus.h"
#include "via_6522.h"
#include "fpga_text.h"
#include "fpga_text_render.h"
#include "spi.h"

/* The Michael FPGA bus (docs/michael-fpga-bus-plan.md), as the emulator sees it: each rising edge of E
 * (PA2, held low by the board's pull-down while it's an input) is a transfer, chosen by RS (PA5) and RW
 * (PA6). With a log, each is a line: "C hh" (a command), "D hh" (data), "R" (a reply read) or "S" (a status
 * read).
 *
 * The FPGA's side is modelled at the level of its commands (hardware/michael/fpga/rtl/bus_control.v): the
 * control commands (NOP, ID, RESET, ECHO), the reply queue and the status byte's sticky bits, GEOMETRY, and
 * text mode's grid (fpga_text.h). The raw display commands drive the display (ili9341.h): its reset line,
 * its commands and their data, and its backlight; in text mode, as the FPGA does, DISP_COMMAND and DISP_DATA
 * are refused, and DISP_RESET ends it. In text mode the renderer (fpga_text_render.h) draws the grid on the
 * display when fpga_bus_render asks, and finishes the picture when text mode ends. A read drives port B with
 * its byte while E is high, unless SOEB (PA4) is low: the keyboard board has port B then (the interlock).
 *
 * The network, the long-form device $81 (rtl/net_spi.v, docs/michael-fpga-w5500-plan.md), makes W5500 frames on
 * the SPI device fpga_bus_attach_net gives it (none: MISO reads high), at once rather than in SPI time:
 * NET_READ's bytes join the reply queue, NET_WRITE's go out as they come, the next command ends the frame; a
 * header not answered $01 $02 $03 sets NET_ERROR; NET_RESET resets the device; NET_STATUS replies 0 (INTn
 * isn't modelled, and no frame is ever open when it's asked). */

#define FPGA_REPLY_DEPTH 512

struct fpga_bus_state {
    const struct via_6522_state *via;
    FILE *log;              /* or NULL */
    uint8_t e_was;
    uint32_t transfers;
    /* The FPGA's side */
    uint16_t cmd;            /* as bus_control.v: a one-byte command, or a long form's operation | 0x100 */
    uint8_t args_left, first_arg, sticky, text_mode;
    uint8_t reply[FPGA_REPLY_DEPTH];
    unsigned reply_head, reply_count;
    int absent;             /* unconfigured: transfers are logged, but nothing answers or acts on them */
    int reading, read_rs;   /* a read under way (E high), of the reply queue (read_rs) or the status */
    uint8_t read_value;
    struct fpga_text text;
    struct ili9341 panel;   /* the display the FPGA drives */
    struct fpga_text_render render;   /* text mode's, drawing the grid on it */
    uint64_t render_us;     /* when it last drew */
    struct spi_device net;  /* the network's device (the W5500), or none */
    int net_open;           /* a frame open: CS low */
    uint8_t net_header;     /* header bytes sent in it */
};

void fpga_bus_init(struct chip *chip, struct fpga_bus_state *state, const struct via_6522_state *via, FILE *log);
/* The W5500 (or another SPI device) on the network device's pins */
void fpga_bus_attach_net(struct fpga_bus_state *state, struct spi_device device);
/* What the FPGA drives onto port B: 1 and the byte while a read has it, else 0 */
int fpga_bus_output(const struct fpga_bus_state *state, uint8_t *value);
/* The text grid, cursor and reverse cells, if text mode was ever on: "<prefix>: fpga text: ..." lines */
void fpga_bus_report(FILE *fp, const char *prefix, const struct fpga_bus_state *state);
/* In text mode, the grid drawn on the display as the FPGA would have by now_us (fpga_text_render.h) */
void fpga_bus_render(struct fpga_bus_state *state, uint64_t now_us);

#endif
