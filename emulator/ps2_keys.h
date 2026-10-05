#ifndef EMULATOR_PS2_KEYS_H
#define EMULATOR_PS2_KEYS_H

#include <stddef.h>
#include <stdint.h>

/* Most scan code bytes one key produces (Alt + Shift + a key). */
#define PS2_KEY_MAX_CODES 10

/* Encode the key at the start of `in` (len > 0) as PS/2 scan code set 2
 * bytes: press and release, with Shift or Ctrl held around it when
 * needed. Keys are the bytes a terminal sends:
 *   - printable ASCII, with Shift for capitals and shifted symbols;
 *   - CR or LF (Enter), BS or DEL (Backspace), Tab, and the other
 *     control codes as Ctrl + letter;
 *   - ESC [ or ESC O sequences for the arrows, Home, End, PgUp, PgDn,
 *     Insert and Delete, and ESC [1;5C / ESC [1;5D for Ctrl+Right/Left;
 *   - ESC [ <code> ; 3 u for a printable key with Alt held ("CSI u",
 *     modifier 3: Alt), with Shift too when the character needs it;
 *     any other ESC is the Esc key.
 * Sets *consumed to the bytes used and returns the number of codes
 * written to out (at most PS2_KEY_MAX_CODES); 0 for a byte no key
 * produces (>= $80). */
int ps2_encode_key(const uint8_t *in, size_t len, size_t *consumed, uint8_t *out);

#endif
