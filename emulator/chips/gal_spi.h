#ifndef EMULATOR_CHIPS_GAL_SPI_H
#define EMULATOR_CHIPS_GAL_SPI_H

#include <stdint.h>
#include "../bus.h"
#include "spi.h"
#include "via_6522.h"

/* The GAL20RA10 SPI interface (hardware/michael/spi-interface/gal/spi-control.pld) and its 74HC299, on Michael's
 * VIA in place of the FPGA board: port B to the '299's I/O pins, E on PA2, the GAL clocked by Phi2 and reset with
 * the board, the '299's /OE1 grounded. tick is one Phi2 cycle: the rising edge's register updates, then, while
 * the burst is on, the SCLK pulse in the low half that follows (SCLK = /CLK * BRST; the GAL's delayed BRST only
 * keeps a runt off that pulse).
 *
 * A rising edge with E high starts a burst (BRST) of 8 cycles, counted by C0-C2. While idle the '299 loads port B
 * on every edge, so the first edge with E high takes the byte to send; during the burst it shifts, Q7 to MOSI and
 * MISOr (MISO, sampled as SCLK rises) in at Q0. If E is still high at the burst's last edge, OUTPUT is set: the
 * '299 holds and drives the byte it received onto port B until an edge finds E low. A strobe that comes during a
 * burst is lost (it reads as "hold"); E as an input is low. */

struct gal_spi_state {
    const struct via_6522_state *via;
    struct spi_device spi;
    uint8_t brst, output, count, misor;   /* the GAL's registers */
    uint8_t sr;                           /* the 74HC299 */
    uint32_t bytes;                       /* bursts started */
};

void gal_spi_init(struct chip *chip, struct gal_spi_state *state, const struct via_6522_state *via,
                  struct spi_device spi);
/* What the '299 drives onto port B: 1 and the byte while OUTPUT is set, else 0 */
int gal_spi_output(const struct gal_spi_state *state, uint8_t *value);

#endif
