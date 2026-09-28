#include "via_6522.h"

#include <stddef.h>
#include <string.h>

/* Recompute the bank-config bits PB0..PB4 drive to the PLD. PB pin
 * value = (orb & ddrb) | (input & ~ddrb); the input side is pulled
 * down on the wendy2c, so floats read as 0. */
static void update_bank_config(struct via_6522_state *s, struct bus *bus) {
    bus->bank_config = (uint8_t)((s->orb & s->ddrb) & 0x1F);
}

/* Update the IRQ output line based on (IFR & IER). IFR bit 7 is set
 * when any other (IFR & IER) bit is set. */
static void update_irq(struct via_6522_state *s, struct bus *bus) {
    uint8_t pending = s->ifr & s->ier & 0x7F;
    if (pending) s->ifr |= 0x80;
    else         s->ifr &= 0x7F;
    bus->irq = pending ? 1 : 0;
}

/* Set or clear an IFR bit and refresh IRQ. */
static void via_set_ifr(struct via_6522_state *s, struct bus *bus, uint8_t mask) {
    s->ifr |= mask;
    update_irq(s, bus);
}
static void via_clear_ifr(struct via_6522_state *s, struct bus *bus, uint8_t mask) {
    s->ifr &= (uint8_t)~mask;
    update_irq(s, bus);
}

/* PORTB pin value: bits driven by output (DDR=1) come from ORB; bits
 * with DDR=0 come from the external driver, else read as 0 (pull-downs
 * on PB0..4; PB6/7 are LED/T1 with no pull). PB7 is overridden by T1
 * squarewave when ACR_T1_OUT set. */
static uint8_t portb_pin_value(const struct via_6522_state *s) {
    uint8_t v = s->orb & s->ddrb;
    if (s->portb_input) v |= (uint8_t)(s->portb_input(s->portb_input_ctx) & ~s->ddrb);
    if (s->acr & VIA_ACR_T1_OUT) {
        v = (uint8_t)((v & 0x7F) | (s->pb7 ? 0x80 : 0));
    }
    return v;
}

/* PORTA pin value: same model, with externally driven input bits
 * (e.g. the control button) feeding through the DDR=0 channels. */
static uint8_t porta_pin_value(const struct via_6522_state *s) {
    return (uint8_t)((s->ora & s->ddra) | (s->porta_input & (uint8_t)~s->ddra));
}

/* An ORA access clears IFR.CA2 unless CA2 is an independent input. */
static void ora_access(struct via_6522_state *s, struct bus *bus) {
    if ((s->pcr & 0x0A) == 0x00) via_clear_ifr(s, bus, VIA_INT_CA2);
}

static bool via_6522_read(struct chip *self, struct bus *bus,
                          uint16_t addr, uint8_t *out) {
    if (!bus->viacs) return false;
    struct via_6522_state *s = (struct via_6522_state *)self->state;
    uint8_t reg = (uint8_t)(addr & 0xF);
    switch (reg) {
        case VIA_REG_ORB:
            *out = portb_pin_value(s);
            /* Reading ORB clears CB1/CB2 IFR (when in interrupt
             * input mode); for our wendy2c usage we leave them be -- the
             * upload-and-run code clears CB2 explicitly via IFR write. */
            return true;
        case VIA_REG_ORA:
            ora_access(s, bus);
            /* fall through */
        case VIA_REG_ORANH:
            *out = porta_pin_value(s);
            return true;
        case VIA_REG_DDRB: *out = s->ddrb; return true;
        case VIA_REG_DDRA: *out = s->ddra; return true;
        case VIA_REG_T1CL:
            *out = (uint8_t)(s->t1c & 0xFF);
            via_clear_ifr(s, bus, VIA_INT_T1);
            return true;
        case VIA_REG_T1CH:
            *out = (uint8_t)((s->t1c >> 8) & 0xFF);
            return true;
        case VIA_REG_T1LL: *out = (uint8_t)(s->t1l & 0xFF); return true;
        case VIA_REG_T1LH: *out = (uint8_t)((s->t1l >> 8) & 0xFF); return true;
        case VIA_REG_T2CL:
            *out = (uint8_t)(s->t2c & 0xFF);
            via_clear_ifr(s, bus, VIA_INT_T2);
            return true;
        case VIA_REG_T2CH:
            *out = (uint8_t)((s->t2c >> 8) & 0xFF);
            return true;
        case VIA_REG_SR:
            *out = s->sr;
            via_clear_ifr(s, bus, VIA_INT_SR);
            /* Reading SR while in shift-in-T2 mode primes the shift
             * register for the next 8 bits. The wendy2c ISR reads SR
             * right after enabling SR_IN_T2 to start each byte. */
            if ((s->acr & VIA_ACR_SR_MODE) == VIA_ACR_SR_IN_T2) {
                s->sr_bits_remaining = 8;
            }
            return true;
        case VIA_REG_ACR: *out = s->acr; return true;
        case VIA_REG_PCR: *out = s->pcr; return true;
        case VIA_REG_IFR: *out = s->ifr; return true;
        case VIA_REG_IER: *out = (uint8_t)(s->ier | 0x80); return true;
    }
    return true;
}

static bool via_6522_write(struct chip *self, struct bus *bus,
                           uint16_t addr, uint8_t data) {
    if (!bus->viacs) return false;
    struct via_6522_state *s = (struct via_6522_state *)self->state;
    uint8_t reg = (uint8_t)(addr & 0xF);
    switch (reg) {
        case VIA_REG_ORB:
            s->orb = data;
            update_bank_config(s, bus);
            return true;
        case VIA_REG_ORA:
            ora_access(s, bus);
            /* fall through */
        case VIA_REG_ORANH:
            s->ora = data;
            return true;
        case VIA_REG_DDRB:
            s->ddrb = data;
            update_bank_config(s, bus);
            return true;
        case VIA_REG_DDRA:
            s->ddra = data;
            return true;
        case VIA_REG_T1CL:
        case VIA_REG_T1LL:
            s->t1l = (uint16_t)((s->t1l & 0xFF00) | data);
            return true;
        case VIA_REG_T1CH:
            s->t1l = (uint16_t)((s->t1l & 0x00FF) | ((uint16_t)data << 8));
            s->t1c = s->t1l;
            s->t1_running = s->t1_loaded = s->t1_armed = 1;
            s->t1_reload = 0;
            via_clear_ifr(s, bus, VIA_INT_T1);
            if (s->acr & VIA_ACR_T1_OUT) s->pb7 = 0;  /* PB7 starts low */
            return true;
        case VIA_REG_T1LH:
            s->t1l = (uint16_t)((s->t1l & 0x00FF) | ((uint16_t)data << 8));
            via_clear_ifr(s, bus, VIA_INT_T1);
            return true;
        case VIA_REG_T2CL:
            s->t2l_lo = data;
            return true;
        case VIA_REG_T2CH:
            s->t2c = (uint16_t)(s->t2l_lo | ((uint16_t)data << 8));
            s->t2_running = s->t2_loaded = s->t2_armed = 1;
            via_clear_ifr(s, bus, VIA_INT_T2);
            return true;
        case VIA_REG_SR:
            s->sr = data;
            via_clear_ifr(s, bus, VIA_INT_SR);
            return true;
        case VIA_REG_ACR: s->acr = data; return true;
        case VIA_REG_PCR: s->pcr = data; return true;
        case VIA_REG_IFR:
            /* Writing 1 to a bit clears that IFR bit. */
            s->ifr &= (uint8_t)~(data & 0x7F);
            update_irq(s, bus);
            return true;
        case VIA_REG_IER:
            if (data & 0x80) s->ier |= (uint8_t)(data & 0x7F);
            else             s->ier &= (uint8_t)~(data & 0x7F);
            update_irq(s, bus);
            return true;
    }
    return true;
}

/* Apply a hardware reset to the VIA's internal registers, mirroring
 * the WDC W65C22S RES behavior: all registers (DDRA/B, ORA/B, T1/T2
 * counter+latch, SR, ACR, PCR, IFR, IER) clear; the IRQ output
 * deasserts; timers stop. External pin drives (porta_input) and the
 * CB2 input level are NOT touched -- they reflect what the outside
 * world is doing, not VIA state. */
static void via_6522_apply_reset(struct via_6522_state *s, struct bus *bus) {
    uint8_t saved_input = s->porta_input;
    uint8_t saved_cb2   = s->cb2_in;
    uint8_t saved_ca2   = s->ca2_in;
    uint8_t (*saved_portb_input)(void *) = s->portb_input;
    void *saved_portb_input_ctx = s->portb_input_ctx;
    memset(s, 0, sizeof(*s));
    s->porta_input = saved_input;
    s->cb2_in      = saved_cb2;
    s->ca2_in      = saved_ca2;
    s->portb_input = saved_portb_input;
    s->portb_input_ctx = saved_portb_input_ctx;
    if (bus) {
        bus->bank_config = 0;   /* (orb & ddrb) = 0 */
        bus->irq         = 0;   /* IFR/IER both cleared */
    }
}

static void via_6522_tick(struct chip *self, struct bus *bus) {
    struct via_6522_state *s = (struct via_6522_state *)self->state;

    /* RES rising-edge: apply hardware reset. Held-high keeps everything
     * cleared; the boot ROM doesn't poll while held. */
    if (bus->res && !s->prev_res) {
        via_6522_apply_reset(s, bus);
    }
    s->prev_res = bus->res;

    /* T1/T2 count on phi2 cycles, not OSC ticks. The clock_22v10
     * sets bus->cpu_cycle_due on each CK falling edge (= phi2 edge);
     * we gate the timer decrements on that signal so the on-target
     * bit-timing matches the real wendy2c boot ROM's T2 expectations.
     * (We do NOT clear cpu_cycle_due here -- the CPU chip ticks
     * after us and consumes it.) */
    if (!bus->cpu_cycle_due) return;

    /* The W65C22 datasheet's timing (figures 2-3, 2-4): a counter
     * written through T1CH/T2CH holds N for the next cycle, then counts
     * down; it times out as it rolls over from 0 to $FFFF, setting the
     * flag N+1.5 cycles after the write (seen on the cycle that reads
     * $FFFF). T1 then reloads from the latch, so free-run interrupts
     * come every N+2 cycles; one-shot mode counts on the same way but
     * sets the flag only once per write. */
    if (s->t1_running) {
        if (s->t1_loaded) {
            s->t1_loaded = 0;
        } else if (s->t1_reload) {
            s->t1c = s->t1l;
            s->t1_reload = 0;
        } else if (s->t1c == 0) {
            s->t1c = 0xFFFF;
            s->t1_reload = 1;
            if (s->acr & VIA_ACR_T1_CONT) {
                via_set_ifr(s, bus, VIA_INT_T1);
                if (s->acr & VIA_ACR_T1_OUT) s->pb7 ^= 1;
            } else if (s->t1_armed) {
                s->t1_armed = 0;
                via_set_ifr(s, bus, VIA_INT_T1);
                if (s->acr & VIA_ACR_T1_OUT) s->pb7 = 1;
            }
        } else {
            s->t1c--;
        }
    }

    /* T2 times out like T1 but keeps counting down from $FFFF, setting
     * the flag once per write to T2CH (datasheet 2.9). In SR-IN-T2 mode
     * each underflow instead shifts cb2_in into SR (when
     * sr_bits_remaining > 0) and reloads T2 from the low-byte latch for
     * the next bit-time -- a simplification of the real shift timing
     * (the serial drivers follow sr_shift_total, not the cycle count). */
    if (s->t2_running) {
        if (s->t2_loaded) {
            s->t2_loaded = 0;
        } else if ((s->acr & VIA_ACR_SR_MODE) == VIA_ACR_SR_IN_T2) {
            if (s->t2c == 0) {
                via_set_ifr(s, bus, VIA_INT_T2);
                /* T2 free-runs at t2l_lo cadence regardless of the
                 * shift counter -- the shift counter only gates
                 * whether each underflow actually shifts a bit and
                 * fires the SR IRQ. */
                if (s->sr_bits_remaining > 0) {
                    s->sr = (uint8_t)((s->sr << 1) | (s->cb2_in & 1));
                    s->sr_bits_remaining--;
                    s->sr_shift_total++;
                    if (s->sr_bits_remaining == 0) {
                        via_set_ifr(s, bus, VIA_INT_SR);
                    }
                }
                s->t2c = s->t2l_lo;
            } else {
                s->t2c--;
            }
        } else {
            if (s->t2c == 0 && s->t2_armed) {
                s->t2_armed = 0;
                via_set_ifr(s, bus, VIA_INT_T2);
            }
            s->t2c--;
        }
    }
}

static void via_6522_reset(struct chip *self) {
    struct via_6522_state *s = (struct via_6522_state *)self->state;
    via_6522_apply_reset(s, NULL);
}

void via_6522_init(struct chip *chip, struct via_6522_state *state) {
    static const struct chip_ops ops = {
        .tick  = via_6522_tick,
        .read  = via_6522_read,
        .write = via_6522_write,
        .reset = via_6522_reset,
    };
    memset(state, 0, sizeof(*state));
    chip->ops = &ops;
    chip->name = "via_6522";
    chip->state = state;
}

void via_6522_set_cb2(struct via_6522_state *s, struct bus *bus, uint8_t bit) {
    uint8_t prev = s->cb2_in;
    s->cb2_in = bit ? 1 : 0;

    /* CB2 edge detection per PCR bits 5-7. */
    uint8_t cb2_mode = s->pcr & VIA_PCR_CB2_MASK;
    if (cb2_mode == VIA_PCR_CB2_IND_NEG_E ||
        (s->pcr & 0xC0) == 0x00 /* CB2 input neg edge non-independent */) {
        if (prev && !s->cb2_in) {
            via_set_ifr(s, bus, VIA_INT_CB2);
            /* The W65C22 datasheet says the SR shift counter is reset
             * only by an SR read or write -- CB2 edges are purely
             * interrupt sources. The wendy2c boot ROM arms the counter
             * via `lda SR` in its CB2 ISR; external drivers like
             * serial_usb observe shifts via sr_shift_total deltas. */
        }
    }
    /* Positive edges, handshake/pulse modes -- not modeled (not used
     * by the wendy2c upload path). */
}

void via_6522_set_ca2(struct via_6522_state *s, struct bus *bus, uint8_t level) {
    uint8_t prev = s->ca2_in;
    s->ca2_in = level ? 1 : 0;
    uint8_t mode = s->pcr & VIA_PCR_CA2_MASK;
    if (mode & 0x08) return;                     /* output modes */
    int positive = (mode & VIA_PCR_CA2_POS_E) != 0;
    if (positive ? (!prev && s->ca2_in) : (prev && !s->ca2_in)) {
        via_set_ifr(s, bus, VIA_INT_CA2);
    }
}

void via_6522_set_portb_input(struct via_6522_state *s,
                              uint8_t (*input)(void *ctx), void *ctx) {
    s->portb_input = input;
    s->portb_input_ctx = ctx;
}

void via_6522_set_cb2_quiet(struct via_6522_state *s, uint8_t bit) {
    s->cb2_in = bit ? 1 : 0;
}

void via_6522_set_porta_input_bit(struct via_6522_state *s, uint8_t bit_mask, int level) {
    if (level) s->porta_input |= bit_mask;
    else       s->porta_input &= (uint8_t)~bit_mask;
}

uint8_t via_6522_get_pb7(const struct via_6522_state *s) { return s->pb7; }
uint16_t via_6522_get_t1c(const struct via_6522_state *s) { return s->t1c; }
uint8_t via_6522_porta_pins(const struct via_6522_state *s) { return porta_pin_value(s); }
uint8_t via_6522_portb_pins(const struct via_6522_state *s) { return portb_pin_value(s); }
uint8_t via_6522_sr_bits_remaining(const struct via_6522_state *s) { return s->sr_bits_remaining; }
uint32_t via_6522_sr_shift_total(const struct via_6522_state *s) { return s->sr_shift_total; }
uint8_t via_6522_ifr(const struct via_6522_state *s) { return s->ifr; }
uint8_t via_6522_ier(const struct via_6522_state *s) { return s->ier; }
