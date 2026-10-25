#ifndef EMULATOR_CHIPS_SPI_H
#define EMULATOR_CHIPS_SPI_H

#include <stdint.h>

/* A device on an SPI bus in mode 0 (SCLK idle low, MSB first), as a master's model drives it: one call per SCLK
 * pulse. The device shows a bit on MISO before the rising edge, samples MOSI on it, and moves to its next bit
 * as SCLK falls, so a pulse returns the MISO bit the rising edge saw. A device watches its own chip select; while
 * deselected it ignores the pulse and returns 1, as an undriven MISO reads at a GAL's input (its pull-up). */
struct spi_device {
    void *ctx;
    int (*pulse)(void *ctx, int mosi);
};

/* A pulse to the device, or 1 if there is none */
static inline int spi_pulse(const struct spi_device *d, int mosi) {
    return d->pulse ? d->pulse(d->ctx, mosi) : 1;
}

#endif
