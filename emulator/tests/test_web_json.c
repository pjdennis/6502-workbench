/* Tests for emulator/web_json.c.
 *
 * The most important test is `key_inside_value_does_not_match`: this
 * is the regression we're guarding against -- the old substring-based
 * helpers would match a `"button"` substring found inside a string
 * VALUE as if it were a key, which could let a hostile client steer
 * the parser. The other tests cover happy paths, malformed input,
 * and DoS-shape rejection.
 */

#include <stdio.h>
#include <string.h>
#include "greatest.h"
#include "../web_json.h"

static int parse(const char *s, struct web_json_msg *msg) {
    return web_json_parse(s, (int)strlen(s), msg);
}

/* ===== happy paths ===== */

TEST simple_button_press(void) {
    struct web_json_msg m;
    ASSERT_EQ(0, parse("{\"type\":\"button\",\"down\":1}", &m));
    ASSERT(m.has_type);
    ASSERT_STR_EQ("button", m.type);
    ASSERT(m.has_down);
    ASSERT_EQ(1, m.down);
    PASS();
}

TEST simple_button_release(void) {
    struct web_json_msg m;
    ASSERT_EQ(0, parse("{\"type\":\"button\",\"down\":0}", &m));
    ASSERT_EQ(0, m.down);
    PASS();
}

TEST reversed_key_order(void) {
    struct web_json_msg m;
    ASSERT_EQ(0, parse("{\"down\":1,\"type\":\"button\"}", &m));
    ASSERT(m.has_type);
    ASSERT_STR_EQ("button", m.type);
    ASSERT_EQ(1, m.down);
    PASS();
}

TEST whitespace_everywhere(void) {
    struct web_json_msg m;
    ASSERT_EQ(0, parse("  {  \"type\" : \"button\" , \"down\" : 1  }  ", &m));
    ASSERT_STR_EQ("button", m.type);
    ASSERT_EQ(1, m.down);
    PASS();
}

TEST whitespace_with_newlines_and_tabs(void) {
    struct web_json_msg m;
    ASSERT_EQ(0, parse("{\n\t\"type\":\t\"button\",\r\n\"down\":\t0\n}", &m));
    ASSERT_STR_EQ("button", m.type);
    ASSERT_EQ(0, m.down);
    PASS();
}

TEST empty_object(void) {
    struct web_json_msg m;
    ASSERT_EQ(0, parse("{}", &m));
    ASSERT(!m.has_type);
    ASSERT(!m.has_down);
    PASS();
}

TEST escape_sequences_in_string(void) {
    struct web_json_msg m;
    ASSERT_EQ(0, parse("{\"type\":\"a\\\"b\\nc\"}", &m));
    ASSERT(m.has_type);
    ASSERT_STR_EQ("a\"b\nc", m.type);
    PASS();
}

TEST unknown_keys_skipped(void) {
    struct web_json_msg m;
    ASSERT_EQ(0, parse("{\"foo\":42,\"type\":\"button\",\"bar\":\"hello\",\"down\":1}", &m));
    ASSERT_STR_EQ("button", m.type);
    ASSERT_EQ(1, m.down);
    PASS();
}

TEST unknown_nested_object_skipped(void) {
    struct web_json_msg m;
    ASSERT_EQ(0, parse("{\"meta\":{\"x\":1,\"y\":2},\"type\":\"button\",\"down\":0}", &m));
    ASSERT_STR_EQ("button", m.type);
    ASSERT_EQ(0, m.down);
    PASS();
}

TEST unknown_array_skipped(void) {
    struct web_json_msg m;
    ASSERT_EQ(0, parse("{\"v\":[1,2,3,\"a\\\"b\"],\"type\":\"button\"}", &m));
    ASSERT_STR_EQ("button", m.type);
    PASS();
}

TEST unknown_bool_and_null_skipped(void) {
    struct web_json_msg m;
    ASSERT_EQ(0, parse("{\"a\":true,\"b\":false,\"c\":null,\"type\":\"button\"}", &m));
    ASSERT_STR_EQ("button", m.type);
    PASS();
}

/* ===== SECURITY: key cannot match inside a string value ===== */

TEST key_inside_value_does_not_match(void) {
    /* The string value "button" looks like the literal `"button"` --
     * the old substring search would have flagged this as a key
     * match. The proper parser must NOT. */
    struct web_json_msg m;
    ASSERT_EQ(0, parse("{\"x\":\"button\"}", &m));
    ASSERT(!m.has_type);
    PASS();
}

TEST type_key_inside_value_does_not_match(void) {
    /* Same shape, this time impersonating the "type" key. */
    struct web_json_msg m;
    ASSERT_EQ(0, parse("{\"x\":\"\\\"type\\\":\\\"button\\\"\"}", &m));
    ASSERT(!m.has_type);
    ASSERT(!m.has_down);
    PASS();
}

TEST down_key_inside_value_does_not_match(void) {
    /* The literal text `"down":99` appears inside a string value;
     * must not register has_down. */
    struct web_json_msg m;
    ASSERT_EQ(0, parse("{\"note\":\"down:99\"}", &m));
    ASSERT(!m.has_down);
    PASS();
}

/* ===== malformed input is rejected ===== */

TEST not_an_object(void) {
    struct web_json_msg m;
    ASSERT_EQ(-1, parse("\"not an object\"", &m));
    PASS();
}

TEST top_level_array_rejected(void) {
    struct web_json_msg m;
    ASSERT_EQ(-1, parse("[1,2,3]", &m));
    PASS();
}

TEST unterminated_string(void) {
    struct web_json_msg m;
    ASSERT_EQ(-1, parse("{\"type\":\"button", &m));
    PASS();
}

TEST missing_colon(void) {
    struct web_json_msg m;
    ASSERT_EQ(-1, parse("{\"type\" \"button\"}", &m));
    PASS();
}

TEST missing_close_brace(void) {
    struct web_json_msg m;
    ASSERT_EQ(-1, parse("{\"type\":\"button\"", &m));
    PASS();
}

TEST trailing_comma_then_eof(void) {
    struct web_json_msg m;
    ASSERT_EQ(-1, parse("{\"type\":\"button\",", &m));
    PASS();
}

TEST garbage_after_object(void) {
    /* Extra trailing data after the closing brace is rejected. */
    struct web_json_msg m;
    ASSERT_EQ(-1, parse("{\"type\":\"button\"}xxx", &m));
    PASS();
}

TEST unicode_escape_rejected(void) {
    /* \uXXXX is explicitly NOT supported. */
    struct web_json_msg m;
    ASSERT_EQ(-1, parse("{\"type\":\"\\u0041\"}", &m));
    PASS();
}

TEST string_too_long_truncates(void) {
    /* A string value longer than WEB_JSON_TYPE_MAX-1 chars must not
     * overflow; parse succeeds, m.type is NUL-terminated, and the
     * tail is dropped. */
    struct web_json_msg m;
    ASSERT_EQ(0, parse("{\"type\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"}", &m));
    ASSERT(m.has_type);
    /* No buffer overflow -- the type field has a NUL within its size. */
    ASSERT(strlen(m.type) <= WEB_JSON_TYPE_MAX - 1);
    PASS();
}

/* ===== key bytes ===== */

TEST keys_bytes_parsed(void) {
    struct web_json_msg m;
    ASSERT_EQ(0, parse("{\"type\":\"keys\",\"bytes\":[27, 91,65]}", &m));
    ASSERT_STR_EQ("keys", m.type);
    ASSERT(m.has_bytes);
    ASSERT_EQ(3, m.n_bytes);
    ASSERT_EQ(27, m.bytes[0]);
    ASSERT_EQ(91, m.bytes[1]);
    ASSERT_EQ(65, m.bytes[2]);
    PASS();
}

TEST keys_bytes_empty(void) {
    struct web_json_msg m;
    ASSERT_EQ(0, parse("{\"bytes\":[]}", &m));
    ASSERT(m.has_bytes);
    ASSERT_EQ(0, m.n_bytes);
    PASS();
}

TEST keys_bytes_full(void) {
    char buf[1024];
    int n = snprintf(buf, sizeof(buf), "{\"bytes\":[");
    for (int i = 0; i < WEB_JSON_BYTES_MAX; i++) n += snprintf(buf + n, sizeof(buf) - n, "%s255", i ? "," : "");
    n += snprintf(buf + n, sizeof(buf) - n, "]}");
    struct web_json_msg m;
    ASSERT_EQ(0, web_json_parse(buf, n, &m));
    ASSERT_EQ(WEB_JSON_BYTES_MAX, m.n_bytes);
    ASSERT_EQ(255, m.bytes[WEB_JSON_BYTES_MAX - 1]);
    PASS();
}

TEST keys_too_many_bytes_rejected(void) {
    /* The client sends long text in pieces; one too many is malformed. */
    char buf[1024];
    int n = snprintf(buf, sizeof(buf), "{\"bytes\":[");
    for (int i = 0; i <= WEB_JSON_BYTES_MAX; i++) n += snprintf(buf + n, sizeof(buf) - n, "%s1", i ? "," : "");
    n += snprintf(buf + n, sizeof(buf) - n, "]}");
    struct web_json_msg m;
    ASSERT_EQ(-1, web_json_parse(buf, n, &m));
    PASS();
}

TEST keys_byte_out_of_range_rejected(void) {
    struct web_json_msg m;
    ASSERT_EQ(-1, parse("{\"bytes\":[256]}", &m));
    ASSERT_EQ(-1, parse("{\"bytes\":[-1]}", &m));
    PASS();
}

TEST keys_bytes_must_be_numbers(void) {
    struct web_json_msg m;
    ASSERT_EQ(-1, parse("{\"bytes\":[\"a\"]}", &m));
    ASSERT_EQ(-1, parse("{\"bytes\":[[1]]}", &m));
    ASSERT_EQ(-1, parse("{\"bytes\":\"ab\"}", &m));
    ASSERT_EQ(-1, parse("{\"bytes\":[1,]}", &m));
    PASS();
}

/* ===== DoS guards ===== */

TEST nesting_depth_capped(void) {
    /* A nested-object DoS shape '{"a":{"a":{"a":...}}}' deeper than
     * WEB_JSON_MAX_DEPTH must return -1, not crash. */
    char buf[1024];
    int n = 0;
    /* Build 10 levels of nesting (> MAX_DEPTH=8). */
    for (int i = 0; i < 10; i++) n += snprintf(buf + n, sizeof(buf) - n, "{\"a\":");
    n += snprintf(buf + n, sizeof(buf) - n, "1");
    for (int i = 0; i < 10; i++) n += snprintf(buf + n, sizeof(buf) - n, "}");
    struct web_json_msg m;
    int rc = web_json_parse(buf, n, &m);
    ASSERT_EQ(-1, rc);
    PASS();
}

TEST giant_number_rejected(void) {
    /* A huge run of digits in `"down"` must not overflow long; the
     * parser caps the value range. */
    struct web_json_msg m;
    ASSERT_EQ(-1, parse("{\"down\":99999999999999999999999999999999}", &m));
    PASS();
}

TEST negative_down_value(void) {
    struct web_json_msg m;
    ASSERT_EQ(0, parse("{\"down\":-1}", &m));
    ASSERT_EQ(-1, m.down);
    PASS();
}

SUITE(web_json_suite) {
    /* happy paths */
    RUN_TEST(simple_button_press);
    RUN_TEST(simple_button_release);
    RUN_TEST(reversed_key_order);
    RUN_TEST(whitespace_everywhere);
    RUN_TEST(whitespace_with_newlines_and_tabs);
    RUN_TEST(empty_object);
    RUN_TEST(escape_sequences_in_string);
    RUN_TEST(unknown_keys_skipped);
    RUN_TEST(unknown_nested_object_skipped);
    RUN_TEST(unknown_array_skipped);
    RUN_TEST(unknown_bool_and_null_skipped);
    /* SECURITY */
    RUN_TEST(key_inside_value_does_not_match);
    RUN_TEST(type_key_inside_value_does_not_match);
    RUN_TEST(down_key_inside_value_does_not_match);
    /* malformed */
    RUN_TEST(not_an_object);
    RUN_TEST(top_level_array_rejected);
    RUN_TEST(unterminated_string);
    RUN_TEST(missing_colon);
    RUN_TEST(missing_close_brace);
    RUN_TEST(trailing_comma_then_eof);
    RUN_TEST(garbage_after_object);
    RUN_TEST(unicode_escape_rejected);
    RUN_TEST(string_too_long_truncates);
    /* DoS */
    RUN_TEST(nesting_depth_capped);
    RUN_TEST(giant_number_rejected);
    RUN_TEST(negative_down_value);
    /* key bytes */
    RUN_TEST(keys_bytes_parsed);
    RUN_TEST(keys_bytes_empty);
    RUN_TEST(keys_bytes_full);
    RUN_TEST(keys_too_many_bytes_rejected);
    RUN_TEST(keys_byte_out_of_range_rejected);
    RUN_TEST(keys_bytes_must_be_numbers);
}

GREATEST_MAIN_DEFS();
int main(int argc, char **argv) {
    GREATEST_MAIN_BEGIN();
    RUN_SUITE(web_json_suite);
    GREATEST_MAIN_END();
}
