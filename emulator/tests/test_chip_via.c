/* Phase 9 VIA 6522 unit tests. */

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "greatest.h"
#include "../bus.h"
#include "../chips/via_6522.h"

static struct via_6522_state vs;
static struct chip vch;
static struct bus bus_;

static void setup(void) {
    via_6522_init(&vch, &vs);
    bus_init(&bus_);
    bus_add_chip(&bus_, &vch);
    bus_.viacs = 1;
}

static uint8_t r(uint8_t reg) {
    uint8_t v = 0;
    bus_read(&bus_, (uint16_t)(0xF000 | reg), &v);
    return v;
}

static void w(uint8_t reg, uint8_t val) {
    bus_write(&bus_, (uint16_t)(0xF000 | reg), val);
}

/* n CPU cycles: the timers count once per cycle. */
static void tick(int n) {
    for (int i = 0; i < n; i++) { bus_.cpu_cycle_due = 1; bus_step(&bus_); }
}

TEST init_state_is_zero(void) {
    setup();
    ASSERT_EQ_FMT((uint8_t)0, r(VIA_REG_ORB), "%02X");
    ASSERT_EQ_FMT((uint8_t)0, r(VIA_REG_ORA), "%02X");
    ASSERT_EQ_FMT((uint8_t)0, r(VIA_REG_DDRB), "%02X");
    ASSERT_EQ_FMT((uint8_t)0, r(VIA_REG_DDRA), "%02X");
    /* IFR/IER both 0; reading IER also forces bit 7 high. */
    ASSERT_EQ_FMT((uint8_t)0x80, r(VIA_REG_IER), "%02X");
    /* bus.bank_config reflects pull-down state (= 0). */
    ASSERT_EQ_FMT((uint8_t)0, bus_.bank_config, "%02X");
    /* No IRQ at reset. */
    ASSERT_EQ_FMT((uint8_t)0, bus_.irq, "%u");
    PASS();
}

TEST porta_input_output_direction(void) {
    setup();
    /* DDRA=$0F (low nibble out), ORA=$5A. PORTA reads back the
     * driven low nibble (= 0xA) with the high nibble at 0 (input,
     * floats 0 in our model since the wendy2c high-nibble pull is
     * off the LCD data side). */
    w(VIA_REG_DDRA, 0x0F);
    w(VIA_REG_ORA, 0x5A);
    ASSERT_EQ_FMT((uint8_t)0x0A, r(VIA_REG_ORA), "%02X");
    PASS();
}

/* PB0..PB4 drive bus.bank_config. */
TEST bank_config_follows_orb_and_ddrb(void) {
    setup();
    w(VIA_REG_DDRB, 0x1F);
    w(VIA_REG_ORB, 0x05);
    ASSERT_EQ_FMT((uint8_t)0x05, bus_.bank_config, "%02X");
    /* DDR=0 means pin floats (= 0 with pull-downs). */
    w(VIA_REG_DDRB, 0x10);  /* only PB4 driven */
    w(VIA_REG_ORB, 0x1F);
    ASSERT_EQ_FMT((uint8_t)0x10, bus_.bank_config, "%02X");
    PASS();
}

/* T1 timed (one-shot) IRQ count. */
TEST t1_timed_one_shot_fires_irq(void) {
    setup();
    w(VIA_REG_IER, 0x80 | VIA_INT_T1);  /* enable T1 */
    /* Latch low byte to 5, then writing high byte (=0) loads counter
     * with 0x0005 and starts T1. */
    w(VIA_REG_T1CL, 0x05);
    w(VIA_REG_T1CH, 0x00);
    ASSERT_EQ_FMT((uint8_t)0, bus_.irq, "%u");
    /* T1 fires N+2 = 7 cycles after the write: it holds 5 for a
     * cycle, counts down to 0 and rolls over to $FFFF. */
    tick(6);
    ASSERT_EQ_FMT((uint8_t)0, bus_.irq, "%u");
    tick(1);
    ASSERT_EQ_FMT((uint8_t)1, bus_.irq, "%u");
    /* IFR shows T1 set + bit 7 (any-IRQ). */
    uint8_t ifr = r(VIA_REG_IFR);
    ASSERT(ifr & VIA_INT_T1);
    ASSERT(ifr & 0x80);
    /* Reading T1CL clears T1 IFR. */
    (void)r(VIA_REG_T1CL);
    ASSERT_EQ_FMT((uint8_t)0, bus_.irq, "%u");
    /* T1 was one-shot, doesn't auto-rearm. Tick more, no new IRQ. */
    tick(100);
    ASSERT_EQ_FMT((uint8_t)0, bus_.irq, "%u");
    PASS();
}

/* T1 continuous + PB7 squarewave: PB7 should toggle each T1 underflow. */
TEST t1_continuous_toggles_pb7(void) {
    setup();
    w(VIA_REG_DDRB, 0x80);  /* PB7 output */
    /* ACR_T1_CONT=$40, ACR_T1_OUT=$80 -> $C0 */
    w(VIA_REG_ACR, 0xC0);
    w(VIA_REG_T1CL, 0x02);
    w(VIA_REG_T1CH, 0x00);  /* counter = 2, starts */
    /* PB7 starts low. */
    ASSERT_EQ_FMT((uint8_t)0, via_6522_get_pb7(&vs), "%u");
    /* N+2 = 4 cycles -> first time-out -> PB7 toggles to 1. */
    tick(4);
    ASSERT_EQ_FMT((uint8_t)1, via_6522_get_pb7(&vs), "%u");
    /* Another N+2 cycles -> toggles back to 0. */
    tick(4);
    ASSERT_EQ_FMT((uint8_t)0, via_6522_get_pb7(&vs), "%u");
    PASS();
}

/* IFR write semantics: writing 1 to a bit clears it. */
TEST ifr_write_clears_bits(void) {
    setup();
    w(VIA_REG_IER, 0x80 | VIA_INT_T1 | VIA_INT_T2);
    w(VIA_REG_T1CL, 1); w(VIA_REG_T1CH, 0);
    w(VIA_REG_T2CL, 1); w(VIA_REG_T2CH, 0);
    /* Tick enough to fire both. */
    tick(4);
    uint8_t ifr = r(VIA_REG_IFR);
    ASSERT(ifr & VIA_INT_T1);
    ASSERT(ifr & VIA_INT_T2);
    /* Clear T1 only. */
    w(VIA_REG_IFR, VIA_INT_T1);
    ifr = r(VIA_REG_IFR);
    ASSERT(!(ifr & VIA_INT_T1));
    ASSERT(ifr & VIA_INT_T2);
    PASS();
}

/* A timer's counter as the CPU reads it, and whether its IRQ was up
 * just before the read (reading T1CL or T2CL clears the flag). */
static uint16_t counter(uint8_t low_reg, uint8_t *irq) {
    *irq = bus_.irq;
    uint8_t low = r(low_reg);
    return (uint16_t)(low | (r((uint8_t)(low_reg + 1)) << 8));
}

/* W65C22 datasheet figure 2-3: the counter holds N on the cycle after
 * the write to T2C-H, counts down from the next, and interrupts N+1.5
 * cycles after the write, as it rolls over from 0 to $FFFF; then it
 * keeps counting down. */
TEST t2_one_shot_counts_as_in_the_datasheet(void) {
    setup();
    w(VIA_REG_IER, 0x80 | VIA_INT_T2);
    w(VIA_REG_T2CL, 3);
    w(VIA_REG_T2CH, 0);
    static const uint16_t expected[] = {3, 2, 1, 0, 0xFFFF, 0xFFFE};
    for (int i = 0; i < 6; i++) {
        tick(1);
        uint8_t irq;
        ASSERT_EQ_FMT(expected[i], counter(VIA_REG_T2CL, &irq), "%04X");
        ASSERT_EQ_FMT((uint8_t)(i == 4), irq, "%u");
    }
    PASS();
}

/* Datasheet 2.9: after the time-out the flag logic is off until the
 * next write to T2C-H, so the counter passing 0 again doesn't set it. */
TEST t2_interrupts_once_per_load(void) {
    setup();
    w(VIA_REG_IER, 0x80 | VIA_INT_T2);
    w(VIA_REG_T2CL, 3);
    w(VIA_REG_T2CH, 0);
    tick(5);
    ASSERT_EQ_FMT((uint8_t)1, bus_.irq, "%u");
    (void)r(VIA_REG_T2CL);
    tick(0x10000);
    ASSERT_EQ_FMT((uint8_t)0, bus_.irq, "%u");
    w(VIA_REG_T2CH, 0);
    tick(5);
    ASSERT_EQ_FMT((uint8_t)1, bus_.irq, "%u");
    PASS();
}

/* Figure 2-3 for T1: as T2 up to the time-out, then the latch reloads
 * the counter, which counts on without interrupting again. PB7, when
 * ACR7 enables it, goes low at the write and high at the time-out. */
TEST t1_one_shot_counts_as_in_the_datasheet(void) {
    setup();
    w(VIA_REG_IER, 0x80 | VIA_INT_T1);
    w(VIA_REG_ACR, VIA_ACR_T1_OUT);
    w(VIA_REG_DDRB, 0x80);
    w(VIA_REG_T1CL, 3);
    w(VIA_REG_T1CH, 0);
    static const uint16_t expected[] = {3, 2, 1, 0, 0xFFFF, 3, 2, 1, 0, 0xFFFF, 3};
    for (int i = 0; i < 11; i++) {
        tick(1);
        uint8_t irq;
        ASSERT_EQ_FMT((uint8_t)(i >= 4), via_6522_get_pb7(&vs), "%u");
        ASSERT_EQ_FMT(expected[i], counter(VIA_REG_T1CL, &irq), "%04X");
        ASSERT_EQ_FMT((uint8_t)(i == 4), irq, "%u");
    }
    PASS();
}

/* Figure 2-4: in free-run mode T1 interrupts N+1.5 cycles after the
 * write, then every N+2 cycles. */
TEST t1_free_run_interrupts_every_n_plus_2_cycles(void) {
    setup();
    w(VIA_REG_IER, 0x80 | VIA_INT_T1);
    w(VIA_REG_ACR, VIA_ACR_T1_CONT);
    w(VIA_REG_T1CL, 3);
    w(VIA_REG_T1CH, 0);
    tick(4);
    ASSERT_EQ_FMT((uint8_t)0, bus_.irq, "%u");
    for (int i = 0; i < 3; i++) {
        tick(1);
        ASSERT_EQ_FMT((uint8_t)1, bus_.irq, "%u");
        (void)r(VIA_REG_T1CL);
        tick(4);
        ASSERT_EQ_FMT((uint8_t)0, bus_.irq, "%u");
    }
    PASS();
}

/* Per the W65C22 datasheet, the SR shift counter is reset by an SR
 * read or write. The wendy2c boot ROM's CB2 ISR does an `lda SR` for
 * exactly that reason. Verify SR read arms 8 shifts and a byte clocks
 * in correctly. */
TEST sr_read_arms_shift_counter(void) {
    setup();
    w(VIA_REG_PCR, VIA_PCR_CB2_IND_NEG_E);
    w(VIA_REG_ACR, VIA_ACR_SR_IN_T2);
    w(VIA_REG_T2CL, 0x01);
    w(VIA_REG_T2CH, 0x00);
    tick(1);  /* The counter holds 1 for the cycle after the write */

    /* No CB2 edge yet -- reading SR primes the counter from zero. */
    ASSERT_EQ_FMT((uint8_t)0, via_6522_sr_bits_remaining(&vs), "%u");
    (void)r(VIA_REG_SR);
    ASSERT_EQ_FMT((uint8_t)8, via_6522_sr_bits_remaining(&vs), "%u");

    static const uint8_t bits[8] = {1,0,1,0,1,0,1,0};
    for (int i = 0; i < 8; i++) {
        via_6522_set_cb2(&vs, &bus_, bits[i]);
        tick(2);
    }
    ASSERT_EQ_FMT((uint8_t)0, via_6522_sr_bits_remaining(&vs), "%u");
    uint8_t sr = r(VIA_REG_SR);
    ASSERT_EQ_FMT((uint8_t)0xAA, sr, "%02X");
    PASS();
}

/* Datasheet: CB2 falling edges are pure interrupt sources -- they do
 * NOT touch the SR shift counter, even when the chip is in SR_IN_T2
 * mode with no shift in progress. The on-target boot ROM's CB2 ISR is
 * responsible for arming the counter (via `lda SR`). */
TEST cb2_falling_edge_does_not_arm_sr(void) {
    setup();
    w(VIA_REG_PCR, VIA_PCR_CB2_IND_NEG_E);
    w(VIA_REG_ACR, VIA_ACR_SR_IN_T2);
    via_6522_set_cb2(&vs, &bus_, 1);
    via_6522_set_cb2(&vs, &bus_, 0);
    ASSERT(vs.ifr & VIA_INT_CB2);
    ASSERT_EQ_FMT((uint8_t)0, via_6522_sr_bits_remaining(&vs), "%u");
    PASS();
}

/* sr_shift_total increments once per actual SR shift and is robust
 * against simultaneous arming. */
TEST sr_shift_total_counts_actual_shifts(void) {
    setup();
    w(VIA_REG_PCR, VIA_PCR_CB2_IND_NEG_E);
    w(VIA_REG_ACR, VIA_ACR_SR_IN_T2);
    w(VIA_REG_T2CL, 0x01);
    w(VIA_REG_T2CH, 0x00);
    tick(1);  /* The counter holds 1 for the cycle after the write */

    ASSERT_EQ_FMT((uint32_t)0, via_6522_sr_shift_total(&vs), "%u");
    /* Arm via SR read. */
    (void)r(VIA_REG_SR);
    /* No shift yet; counter is still 0. */
    ASSERT_EQ_FMT((uint32_t)0, via_6522_sr_shift_total(&vs), "%u");
    /* Two ticks: t2c 1->0 then 0->fire. */
    tick(2);
    ASSERT_EQ_FMT((uint32_t)1, via_6522_sr_shift_total(&vs), "%u");
    /* Another underflow -> another shift. */
    tick(2);
    ASSERT_EQ_FMT((uint32_t)2, via_6522_sr_shift_total(&vs), "%u");
    PASS();
}

/* Real wire-level traffic: a byte's bit pattern can contain multiple
 * 1->0 transitions on CB2 (the data bits themselves). Each falling
 * edge sets IFR.CB2 but must NOT reset the shift counter, or the SR
 * IRQ will fire on the wrong sample. This is a regression test for
 * the bug that surfaced once the host-driven serial link replaced
 * the byte-level serial_usb cheat chip. */
TEST cb2_falling_edge_mid_byte_does_not_rearm_sr(void) {
    setup();
    w(VIA_REG_PCR, VIA_PCR_CB2_IND_NEG_E);
    w(VIA_REG_ACR, VIA_ACR_SR_IN_T2);
    w(VIA_REG_T2CL, 0x01);
    w(VIA_REG_T2CH, 0x00);
    tick(1);  /* The counter holds 1 for the cycle after the write */

    via_6522_set_cb2(&vs, &bus_, 1);
    via_6522_set_cb2(&vs, &bus_, 0);
    /* Arm via SR read -- the real-hardware path. */
    (void)r(VIA_REG_SR);
    ASSERT_EQ_FMT((uint8_t)8, via_6522_sr_bits_remaining(&vs), "%u");

    /* Drive bit pattern 1,1,1,0,0,1,0,1 (LSB-first 0xA7 on the wire).
     * Three falling edges (1->0 at i=3 and i=6) and several rising
     * edges -- none should rearm the counter. */
    static const uint8_t bits[8] = {1, 1, 1, 0, 0, 1, 0, 1};
    for (int i = 0; i < 8; i++) {
        via_6522_set_cb2(&vs, &bus_, bits[i]);
        tick(2);
    }
    /* Check the count BEFORE reading SR (the read itself re-arms the
     * counter). After exactly 8 underflows the counter must be 0. */
    ASSERT_EQ_FMT((uint8_t)0, via_6522_sr_bits_remaining(&vs), "%u");
    uint8_t sr = r(VIA_REG_SR);
    ASSERT_EQ_FMT((uint8_t)0xE5, sr, "%02X");
    PASS();
}

TEST res_rising_edge_clears_registers_and_irq(void) {
    setup();
    /* Configure: DDRA = output, ORA = $5A, DDRB = $1F (banks driven),
     * ORB = $05 (banks=5), arm T1 continuous + IRQ-on-T1, set IER. */
    w(VIA_REG_DDRA, 0xFF);
    w(VIA_REG_ORA,  0x5A);
    w(VIA_REG_DDRB, 0x1F);
    w(VIA_REG_ORB,  0x05);
    w(VIA_REG_ACR,  VIA_ACR_T1_CONT);
    w(VIA_REG_T1LL, 0x10);
    w(VIA_REG_T1CH, 0x00);   /* arms T1 */
    w(VIA_REG_IER,  0x80 | VIA_INT_T1);  /* enable T1 IRQ */

    /* Inject an external pull-up on PA1 -- this is the wendy2c
     * control-button pin. RES must leave it intact. */
    via_6522_set_porta_input_bit(&vs, 0x02, 1);

    /* Run T1 down to underflow so IFR.T1 is set and the IRQ line goes
     * high. (T1 counts on cpu_cycle_due ticks.) */
    tick(200);
    ASSERT(bus_.irq);

    /* Pulse RES high. The VIA detects the rising edge on its next
     * tick and clears every register; the IRQ line drops; T1 stops. */
    bus_.res = 1;
    bus_step(&bus_);

    ASSERT_EQ_FMT((uint8_t)0, r(VIA_REG_DDRA), "%02X");
    ASSERT_EQ_FMT((uint8_t)0, r(VIA_REG_DDRB), "%02X");
    ASSERT_EQ_FMT((uint8_t)0, r(VIA_REG_ACR),  "%02X");
    ASSERT_EQ_FMT((uint8_t)0, r(VIA_REG_IER) & 0x7F, "%02X");
    ASSERT_EQ_FMT((uint8_t)0, r(VIA_REG_IFR) & 0x7F, "%02X");
    ASSERT_EQ_FMT((uint8_t)0, bus_.irq, "%02X");
    ASSERT_EQ_FMT((uint8_t)0, bus_.bank_config, "%02X");

    /* PORTA pin value after RES: (ora & ddra) | (porta_input & ~ddra).
     * ora and ddra are both 0; porta_input has PA1 high (pull-up), so
     * PORTA reads back as $02 -- proving the external drive survived
     * the reset. PORTB has no input drive modelled, so it reads 0. */
    ASSERT_EQ_FMT((uint8_t)0x02, r(VIA_REG_ORA), "%02X");
    ASSERT_EQ_FMT((uint8_t)0x00, r(VIA_REG_ORB), "%02X");

    /* Release RES. Holding it longer would have no further effect (no
     * re-edge); confirm the second tick doesn't disturb the cleared
     * state. */
    bus_.res = 0;
    bus_step(&bus_);
    ASSERT_EQ_FMT((uint8_t)0x02, r(VIA_REG_ORA), "%02X");
    PASS();
}

/* CA2 as an independent negative-edge interrupt input (PCR CA2 = %001),
 * the Michael keyboard board's frame-edge line. */
TEST ca2_independent_negative_edge_sets_ifr_and_irq(void) {
    setup();
    w(VIA_REG_PCR, VIA_PCR_CA2_IND_NEG_E);
    w(VIA_REG_IER, 0x80 | VIA_INT_CA2);
    via_6522_set_ca2(&vs, &bus_, 1);
    ASSERT_EQ_FMT((uint8_t)0, r(VIA_REG_IFR) & VIA_INT_CA2, "%02X");
    via_6522_set_ca2(&vs, &bus_, 0);
    ASSERT_EQ_FMT((uint8_t)VIA_INT_CA2, r(VIA_REG_IFR) & VIA_INT_CA2, "%02X");
    ASSERT_EQ_FMT((uint8_t)1, bus_.irq, "%u");
    /* Independent: reading or writing ORA leaves the flag alone. */
    (void)r(VIA_REG_ORA);
    w(VIA_REG_ORA, 0x00);
    ASSERT_EQ_FMT((uint8_t)VIA_INT_CA2, r(VIA_REG_IFR) & VIA_INT_CA2, "%02X");
    /* Writing the IFR bit clears it and drops IRQ. */
    w(VIA_REG_IFR, VIA_INT_CA2);
    ASSERT_EQ_FMT((uint8_t)0, r(VIA_REG_IFR) & VIA_INT_CA2, "%02X");
    ASSERT_EQ_FMT((uint8_t)0, bus_.irq, "%u");
    PASS();
}

TEST ca2_rising_edge_ignored_in_negative_edge_mode(void) {
    setup();
    w(VIA_REG_PCR, VIA_PCR_CA2_IND_NEG_E);
    via_6522_set_ca2(&vs, &bus_, 0);
    via_6522_set_ca2(&vs, &bus_, 1);
    ASSERT_EQ_FMT((uint8_t)0, r(VIA_REG_IFR) & VIA_INT_CA2, "%02X");
    PASS();
}

/* PCR CA2 = %000: negative-edge input whose flag an ORA access clears. */
TEST ca2_negative_edge_flag_cleared_by_ora_access(void) {
    setup();
    w(VIA_REG_PCR, 0x00);
    via_6522_set_ca2(&vs, &bus_, 1);
    via_6522_set_ca2(&vs, &bus_, 0);
    ASSERT_EQ_FMT((uint8_t)VIA_INT_CA2, r(VIA_REG_IFR) & VIA_INT_CA2, "%02X");
    (void)r(VIA_REG_ORA);
    ASSERT_EQ_FMT((uint8_t)0, r(VIA_REG_IFR) & VIA_INT_CA2, "%02X");
    PASS();
}

static uint8_t portb_driver_value;
static uint8_t portb_driver(void *ctx) {
    (void)ctx;
    return portb_driver_value;
}

/* An external device (the LCD during a read, the keyboard board's
 * shift registers) drives the PORTB pins with DDRB=0. */
TEST portb_input_pins_come_from_external_driver(void) {
    setup();
    via_6522_set_portb_input(&vs, portb_driver, NULL);
    portb_driver_value = 0xA5;
    ASSERT_EQ_FMT((uint8_t)0xA5, r(VIA_REG_ORB), "%02X");
    /* Output bits read back the latch; input bits the driver. */
    w(VIA_REG_DDRB, 0x0F);
    w(VIA_REG_ORB, 0x03);
    ASSERT_EQ_FMT((uint8_t)0xA3, r(VIA_REG_ORB), "%02X");
    ASSERT_EQ_FMT((uint8_t)0xA3, via_6522_portb_pins(&vs), "%02X");
    /* The driver survives a RES like the PORTA input drive does. */
    bus_.res = 1;
    bus_step(&bus_);
    ASSERT_EQ_FMT((uint8_t)0xA5, r(VIA_REG_ORB), "%02X");
    PASS();
}

SUITE(via_6522_suite) {
    RUN_TEST(init_state_is_zero);
    RUN_TEST(porta_input_output_direction);
    RUN_TEST(bank_config_follows_orb_and_ddrb);
    RUN_TEST(t1_timed_one_shot_fires_irq);
    RUN_TEST(t1_continuous_toggles_pb7);
    RUN_TEST(ifr_write_clears_bits);
    RUN_TEST(t2_one_shot_counts_as_in_the_datasheet);
    RUN_TEST(t2_interrupts_once_per_load);
    RUN_TEST(t1_one_shot_counts_as_in_the_datasheet);
    RUN_TEST(t1_free_run_interrupts_every_n_plus_2_cycles);
    RUN_TEST(sr_read_arms_shift_counter);
    RUN_TEST(cb2_falling_edge_does_not_arm_sr);
    RUN_TEST(sr_shift_total_counts_actual_shifts);
    RUN_TEST(cb2_falling_edge_mid_byte_does_not_rearm_sr);
    RUN_TEST(ca2_independent_negative_edge_sets_ifr_and_irq);
    RUN_TEST(ca2_rising_edge_ignored_in_negative_edge_mode);
    RUN_TEST(ca2_negative_edge_flag_cleared_by_ora_access);
    RUN_TEST(portb_input_pins_come_from_external_driver);
    RUN_TEST(res_rising_edge_clears_registers_and_irq);
}

GREATEST_MAIN_DEFS();
int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(via_6522_suite);
    GREATEST_MAIN_END();
}
