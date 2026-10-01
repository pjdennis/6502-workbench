/* Michael's PS/2 keyboard board, modelled at frame level (see ps2_keyboard_board.h). */
#include "ps2_keyboard_board.h"

#include <string.h>

#define SOLB   0x08
#define SOEB   0x10
#define START  0x20

#define BIT_US            80     /* keyboard clock period */
#define HOST_FRAME_BITS   12     /* start, 8 data, parity, stop, line ack */
#define DEVICE_FRAME_BITS 11     /* start, 8 data, parity, stop */
#define DETECT_IDLE_US    150    /* frame detector's RC hold-over */
#define START_DELAY_US    1000   /* host releases the clock -> keyboard clocks */
#define REPLY_DELAY_US    1000   /* command received -> first reply frame */
#define BYTE_GAP_US       1000   /* between frames from the keyboard */
#define KEY_QUIET_US      200000 /* host quiet before key frames go out */
#define KEY_INTERVAL_US   20000  /* default gap between keys */

static int queue_put(struct ps2_byte_queue *q, uint16_t entry) {
    if (q->count == PS2_QUEUE_SIZE) return -1;
    q->entries[(q->head + q->count++) % PS2_QUEUE_SIZE] = entry;
    return 0;
}

static uint16_t queue_take(struct ps2_byte_queue *q) {
    uint16_t entry = q->entries[q->head];
    q->head = (q->head + 1) % PS2_QUEUE_SIZE;
    q->count--;
    return entry;
}

/* A pin reads low only when the VIA drives it low; an input floats high. */
static int driven_low(const struct via_6522_state *via, uint8_t bit) {
    return (via->ddra & bit) && !(via_6522_porta_pins(via) & bit);
}

static uint64_t us(const struct ps2_keyboard_board_state *s, uint32_t n) {
    return (uint64_t)n * s->ticks_per_us;
}

static void start_frame(struct ps2_keyboard_board_state *s, uint64_t start,
                        uint16_t entry, int from_host) {
    s->active = 1;
    s->from_host = (uint8_t)from_host;
    s->frame_byte = (uint8_t)entry;
    s->frame_last_of_key = (entry & PS2_LAST_OF_KEY) != 0;
    s->frame_start = start;
    s->frame_end = start + us(s, BIT_US * (from_host ? HOST_FRAME_BITS : DEVICE_FRAME_BITS));
}

static void reply(struct ps2_keyboard_board_state *s, uint8_t byte) {
    queue_put(&s->replies, byte);
}

static void receive_command(struct ps2_keyboard_board_state *s, uint8_t byte, uint64_t now) {
    s->commands++;
    s->next_send = now + us(s, REPLY_DELAY_US);
    s->keys_after = now + us(s, KEY_QUIET_US);
    if (s->fault == PS2_FAULT_NOACK) return;
    if (s->fault == PS2_FAULT_RESEND) { reply(s, 0xFE); return; }
    if (s->awaiting_argument) {
        s->awaiting_argument = 0;
        reply(s, 0xFA);
        return;
    }
    switch (byte) {
        case 0xEE: reply(s, 0xEE); break;
        case 0xFF: reply(s, 0xFA); reply(s, 0xAA); break;
        case 0xF2: reply(s, 0xFA); reply(s, 0xAB); reply(s, 0x83); break;
        case 0xED:
        case 0xF3: s->awaiting_argument = 1; reply(s, 0xFA); break;
        default:   reply(s, 0xFA); break;
    }
}

static void ps2_keyboard_board_tick(struct chip *self, struct bus *bus) {
    struct ps2_keyboard_board_state *s = (struct ps2_keyboard_board_state *)self->state;
    uint64_t now = bus->osc_ticks;

    /* The host holds the clock low with SOLB; releasing it with START
     * low starts a command frame from the 74HC165s' latched byte. */
    int solb_low = driven_low(s->via, SOLB);
    if (s->prev_solb_low && !solb_low) {
        s->detector_until = now + us(s, DETECT_IDLE_US);
        if (driven_low(s->via, START) && !s->active) {
            start_frame(s, now + us(s, START_DELAY_US), via_6522_portb_pins(s->via), 1);
        }
    }
    s->prev_solb_low = (uint8_t)solb_low;

    if (s->active && now >= s->frame_end) {
        s->active = 0;
        s->detector_until = now + us(s, DETECT_IDLE_US);
        s->shift_register = s->frame_byte;
        if (s->from_host) receive_command(s, s->frame_byte, now);
        else              s->next_send = now + us(s, s->frame_last_of_key ? s->key_interval_us : BYTE_GAP_US);
    }

    if (!s->active && !solb_low && now >= s->next_send) {
        if (s->replies.count) {
            start_frame(s, now, queue_take(&s->replies), 0);
        } else if (s->keys.count && s->commands && now >= s->keys_after) {
            start_frame(s, now, queue_take(&s->keys), 0);
        }
    }

    int clock_busy = solb_low || (s->active && now >= s->frame_start) || now < s->detector_until;
    uint8_t ca2 = (s->fault == PS2_FAULT_NOEDGE) ? 1 : !clock_busy;
    if (ca2 != s->ca2) {
        s->ca2 = ca2;
        via_6522_set_ca2(s->via, bus, ca2);
    }
}

int ps2_board_output(const struct ps2_keyboard_board_state *s, uint8_t *value) {
    if (!driven_low(s->via, SOEB)) return 0;
    *value = (uint8_t)~s->shift_register;
    return 1;
}

int ps2_board_queue_key(struct ps2_keyboard_board_state *s, const uint8_t *codes, int n) {
    if (s->keys.count + n > PS2_QUEUE_SIZE) return -1;
    for (int i = 0; i < n; i++) queue_put(&s->keys, (uint16_t)(codes[i] | (i == n - 1 ? PS2_LAST_OF_KEY : 0)));
    return 0;
}

void ps2_keyboard_board_init(struct chip *chip, struct ps2_keyboard_board_state *state,
                             struct via_6522_state *via, uint32_t ticks_per_us) {
    static const struct chip_ops ops = {
        .tick  = ps2_keyboard_board_tick,
        .read  = NULL,
        .write = NULL,
        .reset = NULL,
    };
    memset(state, 0, sizeof(*state));
    state->via = via;
    state->ticks_per_us = ticks_per_us;
    state->key_interval_us = KEY_INTERVAL_US;
    state->ca2 = 1;
    via->ca2_in = 1;
    chip->ops = &ops;
    chip->name = "ps2_keyboard_board";
    chip->state = state;
}
