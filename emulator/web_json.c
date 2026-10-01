/* Parser for the wendy2c web protocol's client messages (see web_json.h). */
#include "web_json.h"

#include <string.h>

/* Bounded recursive-descent parser. See web_json.h for the scope and
 * guarantees. The grammar we accept (a strict subset of JSON):
 *
 *   message = object
 *   object  = '{' (pair (',' pair)*)? '}'
 *   pair    = string ':' value
 *   value   = string | number | object | array | 'true' | 'false' | 'null'
 *   array   = '[' (value (',' value)*)? ']'
 *   string  = '"' char* '"'           -- no \uXXXX
 *   number  = '-'? digit+             -- no fractions / exponents
 *
 * We only EXTRACT the values of "type" (string) and "down" (number);
 * any other key's value is parsed-and-discarded.
 */

#define DEPTH_CAP        WEB_JSON_MAX_DEPTH
#define NUMBER_DIGITS_CAP 18            /* fits comfortably in a long */

struct parser {
    const char *p;
    const char *end;
};

static int is_ws(char c) {
    return c == ' ' || c == '\t' || c == '\n' || c == '\r';
}

static void skip_ws(struct parser *P) {
    while (P->p < P->end && is_ws(*P->p)) P->p++;
}

static int peek(struct parser *P) {
    return P->p < P->end ? (unsigned char)*P->p : -1;
}

/* Parse a quoted string. If out_buf is non-NULL, the unescaped bytes
 * (up to out_cap-1) are copied and the result is NUL-terminated; any
 * tail beyond out_cap-1 is silently dropped (no overflow, no error).
 * If out_buf is NULL, the string is parsed-and-discarded.
 *
 * Returns 0 on a well-formed string (with terminating `"` consumed),
 * -1 on EOF inside the string or on a \uXXXX sequence. */
static int parse_string(struct parser *P, char *out_buf, int out_cap) {
    if (peek(P) != '"') return -1;
    P->p++;
    int k = 0;
    while (P->p < P->end) {
        char c = *P->p;
        if (c == '"') {
            P->p++;
            if (out_buf && out_cap > 0) out_buf[k < out_cap ? k : out_cap - 1] = '\0';
            return 0;
        }
        if (c == '\\') {
            P->p++;
            if (P->p >= P->end) return -1;
            char e = *P->p;
            switch (e) {
                case '"':  c = '"';  break;
                case '\\': c = '\\'; break;
                case '/':  c = '/';  break;
                case 'n':  c = '\n'; break;
                case 'r':  c = '\r'; break;
                case 't':  c = '\t'; break;
                case 'b':  c = '\b'; break;
                case 'f':  c = '\f'; break;
                /* \uXXXX explicitly rejected -- we don't decode it
                 * and silently dropping would be lossy. */
                case 'u':  return -1;
                default:   return -1;
            }
        }
        if (out_buf && k < out_cap - 1) out_buf[k++] = c;
        else if (out_buf) k++;  /* still count so terminator goes at out_cap-1 */
        P->p++;
    }
    return -1;  /* unterminated */
}

/* Parse a signed integer with at most NUMBER_DIGITS_CAP digits. */
static int parse_int(struct parser *P, long *out) {
    int sign = 1;
    if (peek(P) == '-') { sign = -1; P->p++; }
    if (P->p >= P->end || *P->p < '0' || *P->p > '9') return -1;
    long v = 0;
    int n = 0;
    while (P->p < P->end && *P->p >= '0' && *P->p <= '9') {
        if (n++ >= NUMBER_DIGITS_CAP) return -1;
        v = v * 10 + (*P->p - '0');
        P->p++;
    }
    /* Reject floats (no '.' / 'e' / 'E'). If a fraction/exponent is
     * present, leaving these unconsumed will trip the caller's
     * "expected ',' or '}'" check; cleaner to refuse here. */
    if (P->p < P->end && (*P->p == '.' || *P->p == 'e' || *P->p == 'E')) return -1;
    *out = sign * v;
    return 0;
}

static int parse_value(struct parser *P, int depth);

/* Parse-and-discard an object body: zero or more "key":value pairs. */
static int parse_object_skip(struct parser *P, int depth) {
    if (peek(P) != '{') return -1;
    P->p++;
    if (depth >= DEPTH_CAP) return -1;
    skip_ws(P);
    if (peek(P) == '}') { P->p++; return 0; }
    for (;;) {
        skip_ws(P);
        if (parse_string(P, NULL, 0) != 0) return -1;
        skip_ws(P);
        if (peek(P) != ':') return -1;
        P->p++;
        skip_ws(P);
        if (parse_value(P, depth + 1) != 0) return -1;
        skip_ws(P);
        int c = peek(P);
        if (c == ',') { P->p++; continue; }
        if (c == '}') { P->p++; return 0; }
        return -1;
    }
}

static int parse_array_skip(struct parser *P, int depth) {
    if (peek(P) != '[') return -1;
    P->p++;
    if (depth >= DEPTH_CAP) return -1;
    skip_ws(P);
    if (peek(P) == ']') { P->p++; return 0; }
    for (;;) {
        skip_ws(P);
        if (parse_value(P, depth + 1) != 0) return -1;
        skip_ws(P);
        int c = peek(P);
        if (c == ',') { P->p++; continue; }
        if (c == ']') { P->p++; return 0; }
        return -1;
    }
}

/* Match a literal keyword (true / false / null) starting at P->p. */
static int match_keyword(struct parser *P, const char *kw) {
    int len = (int)strlen(kw);
    if (P->end - P->p < len) return -1;
    if (memcmp(P->p, kw, (size_t)len) != 0) return -1;
    P->p += len;
    return 0;
}

static int parse_value(struct parser *P, int depth) {
    if (depth > DEPTH_CAP) return -1;
    skip_ws(P);
    int c = peek(P);
    if (c == '"') return parse_string(P, NULL, 0);
    if (c == '{') return parse_object_skip(P, depth);
    if (c == '[') return parse_array_skip(P, depth);
    if (c == 't') return match_keyword(P, "true");
    if (c == 'f') return match_keyword(P, "false");
    if (c == 'n') return match_keyword(P, "null");
    if (c == '-' || (c >= '0' && c <= '9')) {
        long dummy;
        return parse_int(P, &dummy);
    }
    return -1;
}

int web_json_parse(const char *s, int slen, struct web_json_msg *msg) {
    memset(msg, 0, sizeof(*msg));
    struct parser P = { s, s + slen };

    skip_ws(&P);
    if (peek(&P) != '{') return -1;
    P.p++;
    skip_ws(&P);

    if (peek(&P) == '}') {
        P.p++;
        skip_ws(&P);
        return (P.p == P.end) ? 0 : -1;
    }

    for (;;) {
        skip_ws(&P);
        char key[24];  /* a tad smaller than WEB_JSON_TYPE_MAX so a
                        * 32-char value doesn't accidentally feel like
                        * a recognized key. */
        if (parse_string(&P, key, sizeof(key)) != 0) return -1;
        skip_ws(&P);
        if (peek(&P) != ':') return -1;
        P.p++;
        skip_ws(&P);

        if (strcmp(key, "type") == 0) {
            if (parse_string(&P, msg->type, sizeof(msg->type)) != 0) return -1;
            msg->has_type = 1;
        } else if (strcmp(key, "down") == 0) {
            long v;
            if (parse_int(&P, &v) != 0) return -1;
            msg->down = v;
            msg->has_down = 1;
        } else {
            /* Unknown key: parse-and-discard its value. */
            if (parse_value(&P, 1) != 0) return -1;
        }

        skip_ws(&P);
        int c = peek(&P);
        if (c == ',') { P.p++; continue; }
        if (c == '}') {
            P.p++;
            skip_ws(&P);
            return (P.p == P.end) ? 0 : -1;
        }
        return -1;
    }
}
