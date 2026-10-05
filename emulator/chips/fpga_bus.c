/* The Michael FPGA bus's transfers, logged, and the FPGA's side modelled (see fpga_bus.h). */
#include <string.h>
#include "fpga_bus.h"

#define BUS_E    0x04   /* PA2 (stage 4 of the plan moved it from PA0) */
#define BUS_SOEB 0x10
#define BUS_RS   0x20
#define BUS_RW   0x40

/* Commands are 9 bits, as in bus_control.v: a long form's operation is 0x100 | the operation (text mode's
   operations are fpga_text_op's codes) */
enum { NOP = 0x00, ID = 0x01, RESET = 0x03, ECHO = 0x04, DISP_RESET = 0x10, DISP_COMMAND = 0x11, DISP_DATA = 0x12,
       BACKLIGHT = 0x13, SERIAL_SEND = 0x50, TEXT = 0x80, LONG = 0x100,
       TEXT_ON = 0x100, TEXT_OFF = 0x101, GOTO = 0x102, PUT = 0x103, CLEAR = 0x104, CLEAR_EOL = 0x105,
       REGION = 0x108, REGION_RESET = 0x109, GEOMETRY = 0x110 };
#define VERSION 2
enum { ABANDONED = 0x01, UNKNOWN = 0x02, EXTRA = 0x04, UNDERFLOW = 0x08, OVERFLOW = 0x10 };

/* The commands, as bus_control.v has them: in text mode, DISP_COMMAND and DISP_DATA are refused, and
   DISP_RESET ends it */
static int display(const struct fpga_bus_state *s, int c) {
    return c == BACKLIGHT || c == DISP_RESET || (!s->text_mode && (c == DISP_COMMAND || c == DISP_DATA));
}
static int text(int c) { return c >= TEXT_ON && c < GEOMETRY; }
static int known(const struct fpga_bus_state *s, int c) {
    return c == NOP || c == ID || c == RESET || c == ECHO || c == SERIAL_SEND || c == TEXT || c == GEOMETRY ||
           display(s, c) || text(c);
}
static int streams(int c) {
    return c == ECHO || c == SERIAL_SEND || c == DISP_COMMAND || c == DISP_DATA || c == PUT;
}
static int arguments(const struct fpga_bus_state *s, int c) {
    if (display(s, c)) return c != DISP_DATA;
    if (c == TEXT) return 1;   /* the operation */
    if (!text(c) || c == PUT) return 0;
    if (c == GOTO || c == REGION) return 2;
    return c == TEXT_ON || c == TEXT_OFF || c == CLEAR || c == CLEAR_EOL || c == REGION_RESET ? 0 : 1;
}

static void push_reply(struct fpga_bus_state *s, uint8_t b) {
    if (s->reply_count == FPGA_REPLY_DEPTH) { s->sticky |= OVERFLOW; return; }
    s->reply[(s->reply_head + s->reply_count++) % FPGA_REPLY_DEPTH] = b;
}

/* A command, or a long form's operation (c | LONG) */
static void start(struct fpga_bus_state *s, int c) {
    if (!known(s, c)) s->sticky |= UNKNOWN;
    s->cmd = (uint16_t)c;
    s->args_left = (uint8_t)arguments(s, c);
    if (c == ID) { push_reply(s, 'M'); push_reply(s, 'B'); push_reply(s, VERSION); push_reply(s, 0x03); }
    if (c == GEOMETRY) { push_reply(s, FPGA_TEXT_ROWS); push_reply(s, FPGA_TEXT_COLS); }
    if (c == RESET) { s->reply_count = 0; s->sticky = 0; }
    if (c == TEXT_ON) s->text_mode = 1;
    if (c == TEXT_OFF || c == DISP_RESET) s->text_mode = 0;
    if (text(c) && s->args_left == 0 && c != PUT) fpga_text_op(&s->text, c & 0xFF, 0, 0);
}

static void write_command(struct fpga_bus_state *s, uint8_t c) {
    if (s->args_left) s->sticky |= ABANDONED;
    start(s, c);
}

static void write_data(struct fpga_bus_state *s, uint8_t d) {
    if (s->cmd == TEXT && s->args_left) {
        start(s, LONG | d);
    } else if (s->args_left) {
        if (s->args_left == 2) s->first_arg = d;
        if (--s->args_left == 0 && text(s->cmd))
            fpga_text_op(&s->text, s->cmd & 0xFF, arguments(s, s->cmd) == 2 ? s->first_arg : d, d);
    } else if (s->cmd == ECHO) {
        push_reply(s, d);
    } else if (s->cmd == PUT) {
        fpga_text_op(&s->text, PUT & 0xFF, d, 0);
    } else if (known(s, s->cmd) && !streams(s->cmd)) {
        s->sticky |= EXTRA;
    }
}

static void fpga_bus_tick(struct chip *self, struct bus *bus) {
    (void)bus;
    struct fpga_bus_state *s = self->state;
    uint8_t pins = via_6522_porta_pins(s->via);
    uint8_t e = (s->via->ddra & BUS_E) ? (pins & BUS_E) : 0;
    if (e && !s->e_was) {
        s->transfers++;
        int rs = (pins & BUS_RS) != 0;
        if (!(pins & BUS_RW)) {
            uint8_t b = via_6522_portb_pins(s->via);
            if (s->log) fprintf(s->log, "%c %02X\n", rs ? 'D' : 'C', b);
            if (!s->absent) {
                if (rs) write_data(s, b); else write_command(s, b);
            }
        } else if (s->log) {
            fputs(rs ? "R\n" : "S\n", s->log);
        }
        if ((pins & BUS_RW) && !s->absent) {
            s->reading = 1;
            s->read_rs = rs;
            if (!rs) {
                s->read_value = s->sticky;
                s->sticky = 0;
            } else if (s->reply_count) {
                s->read_value = s->reply[s->reply_head];
            } else {
                s->read_value = 0x00;
                s->sticky |= UNDERFLOW;
            }
        }
    } else if (!e && s->e_was && s->reading) {
        if (s->read_rs && s->reply_count) {
            s->reply_head = (s->reply_head + 1) % FPGA_REPLY_DEPTH;
            s->reply_count--;
        }
        s->reading = 0;
    }
    s->e_was = e;
}

int fpga_bus_output(const struct fpga_bus_state *s, uint8_t *value) {
    if (!s->reading || !(via_6522_porta_pins(s->via) & BUS_SOEB)) return 0;
    *value = s->read_value;
    return 1;
}

void fpga_bus_report(FILE *fp, const char *prefix, const struct fpga_bus_state *s) {
    const struct fpga_text *t = &s->text;
    if (!t->used) return;
    fprintf(fp, "%s: fpga text: %s, cursor %d,%d %s\n", prefix, s->text_mode ? "on" : "off", t->row, t->col,
            t->cursor ? "shown" : "hidden");
    char row[FPGA_TEXT_COLS + 1];
    for (int r = 0; r < FPGA_TEXT_ROWS; r++) {
        fpga_text_row(t, r, row);
        for (int c = 0; c < FPGA_TEXT_COLS; c++)
            if ((uint8_t)row[c] < 0x20 || (uint8_t)row[c] > 0x7E) row[c] = '?';
        fprintf(fp, "  |%s|\n", row);
    }
    int any = 0;
    for (int r = 0; r < FPGA_TEXT_ROWS; r++)
        for (int c = 0; c < FPGA_TEXT_COLS; c++) any |= t->reverse_cells[r][c];
    if (!any) return;
    fprintf(fp, "%s: fpga text-reverse:\n", prefix);
    for (int r = 0; r < FPGA_TEXT_ROWS; r++) {
        for (int c = 0; c < FPGA_TEXT_COLS; c++) row[c] = t->reverse_cells[r][c] ? '#' : ' ';
        fprintf(fp, "  |%s|\n", row);
    }
}

void fpga_bus_init(struct chip *chip, struct fpga_bus_state *state, const struct via_6522_state *via, FILE *log) {
    static const struct chip_ops ops = { .tick = fpga_bus_tick };
    memset(state, 0, sizeof(*state));
    state->via = via;
    state->log = log;
    fpga_text_init(&state->text);
    chip->ops = &ops;
    chip->name = "fpga_bus";
    chip->state = state;
}
