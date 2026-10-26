#ifndef EMULATOR_CHIPS_SPI_H
#define EMULATOR_CHIPS_SPI_H

#include <stdint.h>

/* A device on an SPI bus in mode 0 (SCLK idle low, MSB first), as a master's model drives it: one call per SCLK
 * pulse. The device shows a bit on MISO before the rising edge, samples MOSI on it, and moves to its next bit
 * as SCLK falls, so a pulse returns the MISO bit the rising edge saw. A device watches its own chip select; while
 * deselected it ignores the pulse and returns 1, as an undriven MISO reads at a GAL's input (its pull-up).
 * A master that drives the device's chip select and reset itself (the FPGA) uses select and reset; a device
 * whose chip select is a VIA pin (on the GAL interface) watches the pin and leaves them NULL. */
struct spi_device {
    void *ctx;
    int (*pulse)(void *ctx, int mosi);
    void (*select)(void *ctx, int selected);
    void (*reset)(void *ctx);
};

/* A pulse to the device, or 1 if there is none */
static inline int spi_pulse(const struct spi_device *d, int mosi) {
    return d->pulse ? d->pulse(d->ctx, mosi) : 1;
}

/* A byte each way, MSB first */
static inline uint8_t spi_byte(const struct spi_device *d, uint8_t out) {
    uint8_t in = 0;
    for (int i = 7; i >= 0; i--) in = (uint8_t)(in << 1 | spi_pulse(d, (out >> i) & 1));
    return in;
}

static inline void spi_select(const struct spi_device *d, int selected) {
    if (d->select) d->select(d->ctx, selected);
}

static inline void spi_reset(const struct spi_device *d) {
    if (d->reset) d->reset(d->ctx);
}

#endif
