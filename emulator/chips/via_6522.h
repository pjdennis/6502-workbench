#ifndef EMULATOR_CHIPS_VIA_6522_H
#define EMULATOR_CHIPS_VIA_6522_H

#include <stdint.h>
#include "../bus.h"

/* WDC 6522 VIA. Phase 9 = registers + T1/T2 + PB7 + IFR/IER + bank
 * config feedback to the clock + CB2-edge / SR-in-T2 path that
 * upload_and_run.inc uses for serial RX.
 *
 * The chip claims any access where bus->viacs is asserted; the low 4
 * bits of the address pick the register (the clock_22v10 already
 * decodes VIACS for $F000..$F7FF only).
 *
 * On the wendy2c, PB0..PB4 drive the C0..C4 bank-config bits to the
 * 22V10 PLD. On the real board these have pull-downs so that at reset
 * (DDRB = 0, no bits driven) the PLD sees %00000. We model that by
 * computing bus->bank_config = (orb & ddrb) & 0x1F whenever ORB or
 * DDRB changes.
 *
 * Serial RX: the SERIAL_USB chip (phase 13) drives via_set_cb2() to
 * pulse the CB2 pin low (start bit) and then to feed bits during
 * shift-in-T2 mode. */

#define VIA_REG_ORB     0x0
#define VIA_REG_ORA     0x1
#define VIA_REG_DDRB    0x2
#define VIA_REG_DDRA    0x3
#define VIA_REG_T1CL    0x4
#define VIA_REG_T1CH    0x5
#define VIA_REG_T1LL    0x6
#define VIA_REG_T1LH    0x7
#define VIA_REG_T2CL    0x8
#define VIA_REG_T2CH    0x9
#define VIA_REG_SR      0xA
#define VIA_REG_ACR     0xB
#define VIA_REG_PCR     0xC
#define VIA_REG_IFR     0xD
#define VIA_REG_IER     0xE
#define VIA_REG_ORANH   0xF

/* IFR / IER bit masks (positive logic). */
#define VIA_INT_CA2     0x01
#define VIA_INT_CA1     0x02
#define VIA_INT_SR      0x04
#define VIA_INT_CB2     0x08
#define VIA_INT_CB1     0x10
#define VIA_INT_T2      0x20
#define VIA_INT_T1      0x40

/* ACR bit masks. */
#define VIA_ACR_T1_CONT     0x40
#define VIA_ACR_T1_OUT      0x80  /* PB7 squarewave when set */
#define VIA_ACR_T2_PB6      0x20
#define VIA_ACR_SR_MODE     0x1C
#define VIA_ACR_SR_IN_T2    0x04
#define VIA_ACR_SR_OUT_T2   0x14

/* PCR (CB2 portion) modes for the wendy2c serial path. */
#define VIA_PCR_CB2_MASK         0xE0
#define VIA_PCR_CB2_IND_NEG_E    0x20

struct via_6522_state {
    /* Port latches and direction registers. */
    uint8_t orb, ora, ddrb, ddra;

    /* Timer 1 + Timer 2 (16-bit each). */
    uint16_t t1c, t1l;
    uint16_t t2c, t2l_lo;  /* T2 latch is only the low byte */

    uint8_t sr;
    uint8_t acr, pcr;
    uint8_t ifr, ier;

    /* Internal state. */
    uint8_t pb7;                /* T1 squarewave output state */
    uint8_t t1_running;         /* counting since the first write to T1CH */
    uint8_t t2_running;         /* counting since the first write to T2CH */
    uint8_t t1_loaded;          /* T1CH/T2CH written this cycle: the counter */
    uint8_t t2_loaded;          /*   holds for a cycle, then counts down */
    uint8_t t1_reload;          /* T1 timed out ($FFFF): the latch reloads next */
    uint8_t t1_armed;           /* a time-out sets the flag (one-shot: once */
    uint8_t t2_armed;           /*   per write to T1CH/T2CH) */
    uint8_t sr_bits_remaining;  /* shift-in-T2 byte progress */
    uint32_t sr_shift_total;    /* monotonic count of SR shifts so far;
                                 * external chips watch this to observe
                                 * each shift without racing the arm */
    uint8_t cb2_in;             /* current CB2 input level */
    uint8_t prev_cb2;           /* edge detect */
    uint8_t prev_res;           /* for bus->res rising-edge detect */

    /* External pin drive for PORTA input bits (bits with DDRA=0).
     * Read back through porta_pin_value() as
     *   (ora & ddra) | (porta_input & ~ddra).
     * Set/cleared by external chips, e.g. led_buttons.c for the
     * control button. PORTB inputs aren't modeled (PB0..4 are pulled
     * down to 0 on the wendy2c). */
    uint8_t porta_input;
};

void via_6522_init(struct chip *chip, struct via_6522_state *state);

/* External CB2 driver (used by the SERIAL_USB chip in phase 13). The
 * "edge" form runs the PCR-based IFR-edge logic; the "quiet" form
 * just updates the cb2_in level so the next T2 underflow shifts it,
 * without firing IFR (used to drive subsequent bits in a byte without
 * triggering a spurious "new start bit" interrupt). */
void via_6522_set_cb2(struct via_6522_state *state, struct bus *bus, uint8_t bit);
void via_6522_set_cb2_quiet(struct via_6522_state *state, uint8_t bit);

/* External pin-input drive for PORTA. `bit_mask` is the bit to drive
 * (e.g. 0x20 for PA5); `level` is 0 (clear) or 1 (set). Bits with
 * DDRA=1 are output-driven and the input drive has no effect at the
 * pin until the program flips DDRA. */
void via_6522_set_porta_input_bit(struct via_6522_state *state, uint8_t bit_mask, int level);

/* Inspectors -- handy for tests and for chips that latch port pins
 * (the LCD watches PORTA + the E line on PORTB bit 5, etc.). */
uint8_t via_6522_get_pb7(const struct via_6522_state *state);
uint16_t via_6522_get_t1c(const struct via_6522_state *state);
uint8_t via_6522_porta_pins(const struct via_6522_state *state);
uint8_t via_6522_portb_pins(const struct via_6522_state *state);

/* For the SERIAL_USB chip: peek the shift-register bits-remaining counter
 * so the external driver can synchronize CB2 transitions with T2 underflows
 * regardless of the timing model. */
uint8_t via_6522_sr_bits_remaining(const struct via_6522_state *state);

/* Monotonic count of bits shifted through the SR. Increments once per
 * T2 underflow that actually shifts (= sr_bits_remaining was positive).
 * External drivers track deltas to advance their byte stream one bit
 * per actual shift -- robust against the on-target arming the counter
 * in the same tick a shift happens. */
uint32_t via_6522_sr_shift_total(const struct via_6522_state *state);

/* IFR / IER inspectors -- used by the SERIAL_USB chip to know when the
 * on-target boot ROM has finished its init (= IER has CB2 enabled) and
 * to back-pressure between bytes (= IFR.CB2/SR cleared by the ISR). */
uint8_t via_6522_ifr(const struct via_6522_state *state);
uint8_t via_6522_ier(const struct via_6522_state *state);

#endif
