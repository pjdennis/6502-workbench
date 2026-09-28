#ifndef EMULATOR_CHIPS_SERIAL_USB_H
#define EMULATOR_CHIPS_SERIAL_USB_H

#include <stdint.h>
#include "../bus.h"
#include "via_6522.h"

/* USB serial chip on the wendy2c. RX path drives the VIA's CB2 + SR +
 * T2 the same way the real USB serial chip does -- pulses CB2 low to
 * mark a start bit, then feeds each bit on cb2_in as the VIA's T2
 * underflows shift them into SR.
 *
 * The driver here is timing-agnostic: it watches via_6522_sr_shift_total()
 * to detect each shift the VIA performs and advances cb2_in to the
 * next bit on the next tick. Tracking the monotonic shift counter (not
 * sr_bits_remaining directly) means we don't race the on-target's
 * `lda SR` that re-arms the counter to 8 in the same tick a shift
 * happens.
 *
 * Bits are shifted MSB-first into the LSB position of SR; so to send
 * the host byte X, the wire value the VIA captures is bit-reversed X.
 * The wendy2c's TRANSLATE table reverses on receive, so applications
 * see X. The chip queues bytes pre-translated by the host. */

/* RX queue capacity. Sized to hold a full uploaded program plus framing in a
 * single --serial-input pre-load: the wendy2c boot ROM streams a RAW program
 * (<= 64 KiB) + a 4-byte length/checksum frame, and the emulator pre-loads the
 * whole --serial-input file into this queue at once (dropping any overflow), so
 * a 4 KiB queue capped uploads at ~3.8 KB. 0x11000 (68 KiB) clears 64 KiB +
 * frame. The boot ROM reads at its own pace, so an oversized queue is harmless. */
#define SERIAL_USB_BUF_SIZE 0x11000

struct serial_usb_state {
    uint8_t buf[SERIAL_USB_BUF_SIZE];
    int head, tail;     /* circular RX queue head/tail */

    /* Driving state. */
    enum {
        SERIAL_IDLE,
        SERIAL_START,        /* CB2 just driven low; arming */
        SERIAL_SHIFTING,     /* shifting bits */
    } state;
    uint8_t current_byte;
    uint8_t bit_index;       /* 0..7; which bit we're driving on cb2 */
    uint32_t prev_shift_total;

    /* External hookup. */
    struct via_6522_state *via;  /* non-const because we drive cb2_in */
};

void serial_usb_init(struct chip *chip, struct serial_usb_state *state,
                     struct via_6522_state *via);

/* Queue one byte for delivery to the wendy2c CPU. The byte should
 * already be bit-reversed if the on-target code uses TRANSLATE. */
int serial_usb_queue_byte(struct serial_usb_state *state, uint8_t byte);

/* Number of bytes still queued (= length of the RX FIFO). */
int serial_usb_queue_count(const struct serial_usb_state *state);

/* Queue every byte of the file at path (as much as fits). Returns -1 if
 * it can't be opened. */
int serial_usb_queue_file(struct serial_usb_state *state, const char *path);

#endif
