#ifndef EMULATOR_CHIPS_PS2_KEYBOARD_BOARD_H
#define EMULATOR_CHIPS_PS2_KEYBOARD_BOARD_H

#include <stdint.h>
#include "../bus.h"
#include "via_6522.h"

/* Michael's PS/2 keyboard board ("Bidirectional PS2 Keyboard Interface
 * Schematic v1.0",
 * docs/michael-bidirectional-PS2-keyboard-interface-schematic-v-1.0.pdf)
 * with a keyboard plugged in, modelled at frame level: the level of each
 * line over time, not every clock edge.
 *
 * VIA wiring (base_config_v2.inc):
 *   PA3 SOLB   low: the 74HC165s load PORTB plus START (PA5) and PARITY
 *              (PA6), and the keyboard clock is held low. Releasing it
 *              with START low sends that byte to the keyboard.
 *   PA4 SOEB   low: the 74HC595s drive the last frame's byte, inverted,
 *              onto PORTB (via_6522_set_portb_input + ps2_board_output).
 *   CA2        the frame detector: low while the keyboard clock is held
 *              low or clocking a frame, high again about 150 us after it
 *              goes idle.
 *
 * The keyboard clocks a command in about 1 ms after the host releases
 * the clock and answers about 1 ms after that: $FA (acknowledge), or
 * $EE to $EE (echo), $FA $AA to $FF (reset), $FA $AB $83 to $F2 (read
 * ID). $ED, $F0 and $F3 take an argument byte, also acknowledged;
 * $F0 $00 is answered $FA $FA $02 (scan code set 2). Queued
 * keys (groups of scan code bytes) go out once the host has sent a
 * command and then left the keyboard alone for 200 ms (start-up is
 * over): a key's bytes 1 ms apart, keys key_interval_us apart. */

enum ps2_fault {
    PS2_FAULT_NONE,
    PS2_FAULT_NOEDGE,   /* CA2 never moves: the clock can't be seen */
    PS2_FAULT_NOACK,    /* the keyboard never answers a command */
    PS2_FAULT_RESEND,   /* the keyboard answers every command with $FE */
};

#define PS2_QUEUE_SIZE 16384
#define PS2_LAST_OF_KEY 0x100    /* queue entry flag: the key's last byte */

struct ps2_byte_queue {
    uint16_t entries[PS2_QUEUE_SIZE];   /* byte | PS2_LAST_OF_KEY */
    int head, count;
};

struct ps2_keyboard_board_state {
    struct via_6522_state *via;
    uint32_t ticks_per_us;
    enum ps2_fault fault;

    uint8_t shift_register;     /* the 74HC595s: the last frame's byte */
    uint8_t prev_solb_low;
    uint8_t ca2;

    /* The frame on the wire, if any: clock active from start to end. */
    int active;
    uint8_t from_host;
    uint8_t frame_byte;
    uint8_t frame_last_of_key;
    uint64_t frame_start, frame_end;
    uint64_t detector_until;    /* the frame detector holds CA2 low until */

    struct ps2_byte_queue replies;  /* answers to commands, sent first */
    struct ps2_byte_queue keys;
    uint64_t next_send;             /* no frame from the keyboard before this */
    uint64_t keys_after;            /* no key frame before this */
    uint32_t key_interval_us;       /* from one key's last byte to the next key */
    uint8_t awaiting_argument_for;  /* the command whose argument comes next, or 0 */
    uint32_t commands;              /* command and argument bytes received */
};

void ps2_keyboard_board_init(struct chip *chip, struct ps2_keyboard_board_state *state,
                             struct via_6522_state *via, uint32_t ticks_per_us);

/* Queue a key for the keyboard to send: its n scan code bytes. Returns
 * -1 if the queue is full. */
int ps2_board_queue_key(struct ps2_keyboard_board_state *state, const uint8_t *codes, int n);

/* Returns 1 with *value = the byte on PORTB while SOEB is low, else 0. */
int ps2_board_output(const struct ps2_keyboard_board_state *state, uint8_t *value);

#endif
