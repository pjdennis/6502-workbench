#ifndef EMULATOR_WEB_JSON_H
#define EMULATOR_WEB_JSON_H

/* Purpose-built JSON parser for the wendy2c web protocol.
 *
 * Accepted shapes (anything else is rejected with -1 from
 * web_json_parse, except unknown keys in a valid object, which are
 * tolerated and skipped):
 *
 *     {"type":"button","down":0|1}
 *     {"type":"reset"}
 *     {"type":"keys","bytes":[27,91,65]}   -- key bytes, as a terminal
 *                                            sends them (ps2_keys.h)
 *
 * Why we don't just use a general parser:
 *   - We're embedded inside the emulator; no dep.
 *   - We only need a tiny vocabulary.
 *   - Hand-narrowing the grammar lets us cap nesting depth and
 *     numeric range to prevent DoS shapes.
 *
 * What this parser GUARANTEES (i.e. what the old substring helpers did
 * NOT guarantee):
 *   - Keys are only matched in KEY POSITIONS (immediately after `{` or
 *     `,` at top level), so a `"button"` substring sitting inside a
 *     string VALUE cannot be mistaken for a key.
 *   - Strings are properly terminated; an unterminated `"` returns
 *     -1 instead of running off the end of the buffer.
 *   - Object/array nesting is capped at WEB_JSON_MAX_DEPTH (8); a
 *     "{[{[{..." DoS shape returns -1 well before stack exhaustion.
 *   - Numeric values are bounded; a huge run of digits returns -1
 *     instead of overflowing.
 *   - "bytes" holds at most WEB_JSON_BYTES_MAX values, each 0..255;
 *     anything else there returns -1 (the client sends long text in
 *     pieces).
 *
 * What this parser does NOT do (deliberately):
 *   - Unicode escapes (\uXXXX) -- rejected, not interpreted.
 *   - Floating-point values -- rejected.
 *   - Top-level arrays / strings / numbers / nulls -- only objects.
 *   - Streaming / partial parse -- give it the whole frame at once.
 */

#include <stdint.h>

#define WEB_JSON_MAX_DEPTH 8
#define WEB_JSON_TYPE_MAX  32
#define WEB_JSON_BYTES_MAX 64

struct web_json_msg {
    int  has_type;
    char type[WEB_JSON_TYPE_MAX];
    int  has_down;
    long down;
    int     has_bytes;
    int     n_bytes;
    uint8_t bytes[WEB_JSON_BYTES_MAX];
};

/* Parse a top-level JSON object out of s[0..slen). Fills *msg with
 * any recognized fields (others left zeroed). Returns 0 on a valid
 * object (even if no recognized fields), -1 on malformed input or
 * cap-exceeded DoS shapes. */
int web_json_parse(const char *s, int slen, struct web_json_msg *msg);

#endif
