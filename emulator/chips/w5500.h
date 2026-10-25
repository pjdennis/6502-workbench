#ifndef EMULATOR_CHIPS_W5500_H
#define EMULATOR_CHIPS_W5500_H

#include <stdint.h>
#include <stdio.h>
#include "../bus.h"
#include "spi.h"
#include "via_6522.h"

/* The WIZnet W5500 Ethernet controller as an SPI device (chips/spi.h), its chip select (SCSn, active low) on a
 * VIA port A pin: on Michael, PA0, through the GAL SPI interface (gal_spi.h). The module pulls SCSn up, so it is
 * deselected while the pin is an input.
 *
 * A frame is two address bytes, a control byte -- the block (BSB, bits 7-3: 0 the common registers, 4n+1, 4n+2
 * and 4n+3 socket n's registers, TX buffer and RX buffer), read or write (bit 2: 1 writes) and the mode (bits 1-0:
 * 0 variable length, until SCSn rises; 1, 2 or 3 fixed at 1, 2 or 4 data bytes) -- then data, the address
 * counting up. While the address and control bytes go in, MISO counts them, $01, $02 and $03 (as the board shows):
 * a driver can check them to see the frame was taken whole. MISO is 0 during a write's data.
 *
 * Modelled: the register and buffer memory, with the reset values of the registers a driver reads first
 * (VERSIONR, read-only, is $04), and MR's software reset (RST, bit 7). PHYCFGR reads link up, as if
 * the cable were plugged into a 100 Mbps full duplex port. The network side isn't: commands, sockets and the PHY don't act. */

#define W5500_SOCKETS 8
#define W5500_BUFFER 0x800      /* each socket's TX and RX buffer at their reset size, 2 KB */

struct w5500_state {
    const struct via_6522_state *via;
    uint8_t cs_mask;            /* the port A pin of SCSn */
    int selected;
    uint8_t in, out, bits;      /* the byte arriving, the one leaving, and bits so far */
    uint8_t phase;              /* 0, 1: the address's bytes; 2: the control byte; 3: data */
    uint16_t addr;
    uint8_t control, data_left; /* fixed length mode: data bytes left in the frame */
    uint32_t frames;
    uint8_t common[0x40];
    uint8_t socket[W5500_SOCKETS][0x30];
    uint8_t tx[W5500_SOCKETS][W5500_BUFFER], rx[W5500_SOCKETS][W5500_BUFFER];
};

void w5500_init(struct chip *chip, struct w5500_state *state, const struct via_6522_state *via, uint8_t cs_mask);
/* One SCLK pulse (spi.h): the MISO bit the rising edge saw */
int w5500_pulse(void *state, int mosi);
/* The network settings: "<prefix>: w5500: ip a.b.c.d mask a.b.c.d gateway a.b.c.d mac xx:xx:xx:xx:xx:xx" */
void w5500_report(FILE *fp, const char *prefix, const struct w5500_state *state);
/* The W5500 as the GAL SPI interface's device */
struct spi_device w5500_spi(struct w5500_state *state);

#endif
