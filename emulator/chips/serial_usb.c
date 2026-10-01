/* USB serial chip: feeds queued bytes to the VIA's CB2/SR (see serial_usb.h). */
#include "serial_usb.h"

#include <stdio.h>

#include <stddef.h>
#include <string.h>

static int queue_empty(const struct serial_usb_state *s) {
    return s->head == s->tail;
}
static int queue_full(const struct serial_usb_state *s) {
    return ((s->head + 1) % SERIAL_USB_BUF_SIZE) == s->tail;
}
static uint8_t queue_pop(struct serial_usb_state *s) {
    uint8_t b = s->buf[s->tail];
    s->tail = (s->tail + 1) % SERIAL_USB_BUF_SIZE;
    return b;
}

/* Pick bit `bit_index` of `byte`, with bit_index=0 = LSB. Real UART
 * convention is LSB-first; with the VIA's left-shift-into-LSB SR, that
 * causes SR to capture the byte bit-reversed -- which the on-target
 * TRANSLATE table then reverses to recover the original byte value. */
static uint8_t byte_bit(uint8_t byte, uint8_t bit_index) {
    return (uint8_t)((byte >> bit_index) & 1);
}

static void serial_usb_tick(struct chip *self, struct bus *bus) {
    struct serial_usb_state *s = (struct serial_usb_state *)self->state;
    if (!s->via) return;

    switch (s->state) {
        case SERIAL_IDLE: {
            if (queue_empty(s)) return;
            /* Wait until the on-target boot ROM has finished its init
             * before sending the first byte: IER must have the CB2
             * interrupt enabled (set by the wendy2c init right before
             * cli) and any previously-pending IFR.CB2 / IFR.SR must be
             * cleared (= the ISR processed our previous byte). */
            uint8_t ier = via_6522_ier(s->via);
            if (!(ier & VIA_INT_CB2)) return;
            uint8_t ifr = via_6522_ifr(s->via);
            if (ifr & VIA_INT_CB2) return;
            if (ifr & VIA_INT_SR) return;

            s->current_byte = queue_pop(s);
            s->bit_index = 0;
            /* Snapshot the shift counter BEFORE the falling edge so
             * our first-shift detection is exact. */
            s->prev_shift_total = via_6522_sr_shift_total(s->via);
            /* Drop CB2 (start bit edge -- fires IFR.CB2). On real
             * hardware the SR shift counter is NOT armed by this edge;
             * the on-target ISR arms it via `lda SR`. */
            via_6522_set_cb2(s->via, bus, 0);
            /* Place bit 0 (LSB) on cb2_in immediately so the very
             * first T2 underflow after the on-target arms the counter
             * shifts bit 0 -- not the start bit -- into SR. */
            via_6522_set_cb2_quiet(s->via, byte_bit(s->current_byte, 0));
            s->state = SERIAL_SHIFTING;
            break;
        }
        case SERIAL_START:
            /* Unused in the new state machine. */
            s->state = SERIAL_IDLE;
            break;
        case SERIAL_SHIFTING: {
            uint32_t shifts = via_6522_sr_shift_total(s->via);
            /* Handle every shift that occurred since our last tick.
             * In practice this is 0 or 1 per tick, but a loop keeps
             * us correct under coarse-grained ticking too. */
            while (shifts > s->prev_shift_total) {
                s->prev_shift_total++;
                s->bit_index++;
                if (s->bit_index < 8) {
                    via_6522_set_cb2_quiet(s->via,
                        byte_bit(s->current_byte, s->bit_index));
                } else {
                    /* Byte fully shifted -- return CB2 to idle high
                     * so the next start edge will be detected. */
                    via_6522_set_cb2_quiet(s->via, 1);
                    s->state = SERIAL_IDLE;
                    break;
                }
            }
            break;
        }
    }
}

static void serial_usb_reset(struct chip *self) {
    struct serial_usb_state *s = (struct serial_usb_state *)self->state;
    s->head = 0;
    s->tail = 0;
    s->state = SERIAL_IDLE;
    s->current_byte = 0;
    s->bit_index = 0;
    s->prev_shift_total = 0;
    if (s->via) via_6522_set_cb2_quiet(s->via, 1);  /* idle high */
}

void serial_usb_init(struct chip *chip, struct serial_usb_state *state,
                     struct via_6522_state *via) {
    static const struct chip_ops ops = {
        .tick  = serial_usb_tick,
        .read  = NULL,
        .write = NULL,
        .reset = serial_usb_reset,
    };
    memset(state, 0, sizeof(*state));
    state->state = SERIAL_IDLE;
    state->via = via;
    if (via) via_6522_set_cb2_quiet(via, 1);  /* idle high at boot */
    chip->ops = &ops;
    chip->name = "serial_usb";
    chip->state = state;
}

int serial_usb_queue_byte(struct serial_usb_state *s, uint8_t byte) {
    if (queue_full(s)) return -1;
    s->buf[s->head] = byte;
    s->head = (s->head + 1) % SERIAL_USB_BUF_SIZE;
    return 0;
}

int serial_usb_queue_count(const struct serial_usb_state *s) {
    int n = s->head - s->tail;
    if (n < 0) n += SERIAL_USB_BUF_SIZE;
    return n;
}

int serial_usb_queue_file(struct serial_usb_state *s, const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    int byte;
    while ((byte = fgetc(f)) != EOF) {
        if (serial_usb_queue_byte(s, (uint8_t)byte) < 0) break;
    }
    fclose(f);
    return 0;
}
