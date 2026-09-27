#include "lcd_hd44780.h"

#include <stddef.h>
#include <string.h>

/* HD44780 instructions (top-bit-first encoding). */
#define INST_CLEAR        0x01
#define INST_HOME         0x02
#define INST_ENTRY_MODE   0x04
#define INST_DISPLAY_CTL  0x08
#define INST_CURSOR_SHIFT 0x10
#define INST_FUNCTION_SET 0x20
#define INST_SET_CGRAM    0x40
#define INST_SET_DDRAM    0x80

const struct lcd_hd44780_wiring LCD_WIRING_WENDY2C = {
    .rs_port = LCD_PORT_A, .rs_bit = 0x01,
    .rw_port = LCD_PORT_A, .rw_bit = 0x08,
    .e_port  = LCD_PORT_B, .e_bit  = 0x20,
    .data_port = LCD_PORT_A, .data_mask = 0xF0,
};

const struct lcd_hd44780_wiring LCD_WIRING_MICHAEL = {
    .rs_port = LCD_PORT_A, .rs_bit = 0x20,
    .rw_port = LCD_PORT_A, .rw_bit = 0x40,
    .e_port  = LCD_PORT_A, .e_bit  = 0x80,
    .data_port = LCD_PORT_B, .data_mask = 0xFF,
};

static void execute_byte(struct lcd_hd44780_state *s, uint8_t rs, uint8_t byte);
static void advance_ac(struct lcd_hd44780_state *s);

static uint8_t port_pins(const struct lcd_hd44780_state *s, uint8_t port) {
    return port == LCD_PORT_A ? via_6522_porta_pins(s->via)
                              : via_6522_portb_pins(s->via);
}

static uint8_t pin(const struct lcd_hd44780_state *s, uint8_t port, uint8_t bit) {
    return (port_pins(s, port) & bit) ? 1 : 0;
}

static uint8_t port_ddr(const struct lcd_hd44780_state *s, uint8_t port) {
    return port == LCD_PORT_A ? s->via->ddra : s->via->ddrb;
}

static int driven(const struct lcd_hd44780_state *s, uint8_t port, uint8_t bits) {
    return (port_ddr(s, port) & bits) == bits;
}

static uint8_t read_value(const struct lcd_hd44780_state *s, uint8_t rs) {
    if (!rs) return (uint8_t)(s->ac & 0x7F);   /* busy flag (bit 7) never set */
    return s->cgram_mode ? s->cgram[s->ac & 0x3F] : s->ddram[s->ac % LCD_DDRAM_SIZE];
}

int lcd_hd44780_output(const struct lcd_hd44780_state *s, uint8_t *value) {
    const struct lcd_hd44780_wiring *w = &s->wiring;
    if (!s->via || !pin(s, w->e_port, w->e_bit) || !pin(s, w->rw_port, w->rw_bit)) return 0;
    *value = read_value(s, pin(s, w->rs_port, w->rs_bit)) & w->data_mask;
    return 1;
}

static void lcd_hd44780_tick(struct chip *self, struct bus *bus) {
    (void)bus;
    struct lcd_hd44780_state *s = (struct lcd_hd44780_state *)self->state;
    if (!s->via) return;

    const struct lcd_hd44780_wiring *w = &s->wiring;
    uint8_t e = pin(s, w->e_port, w->e_bit);

    int reading = e && pin(s, w->rw_port, w->rw_bit);
    if (reading && (port_ddr(s, w->data_port) & w->data_mask)) {
        if (!s->contending) s->contention++;
        s->contending = 1;
    } else {
        s->contending = 0;
    }

    /* Latch on E falling edge. */
    if (s->prev_e && !e) {
        uint8_t rs = pin(s, w->rs_port, w->rs_bit);
        uint8_t rw = pin(s, w->rw_port, w->rw_bit);
        if (!driven(s, w->rs_port, w->rs_bit) || !driven(s, w->rw_port, w->rw_bit) ||
            (!rw && !driven(s, w->data_port, w->data_mask))) {
            s->undriven_strobes++;
        }
        if (rw) {
            /* Read cycle: the data went out through lcd_hd44780_output
             * while E was high. A data read advances the address. */
            if (rs) advance_ac(s);
        } else {
            /* The value on D7..D0; unwired data lines read as 0. */
            uint8_t data = port_pins(s, w->data_port) & w->data_mask;
            if (s->four_bit_mode) {
                uint8_t nibble = data >> 4;
                if (!s->high_nibble_pending) {
                    s->high_nibble = nibble;
                    s->high_nibble_pending = 1;
                } else {
                    uint8_t byte = (uint8_t)((s->high_nibble << 4) | nibble);
                    s->high_nibble_pending = 0;
                    execute_byte(s, rs, byte);
                }
            } else {
                /* 8-bit mode. With 4-bit wiring only D4..D7 are on the
                 * bus, which is enough for the init dance: any
                 * function-set with DL=0 puts us in 4-bit mode. */
                execute_byte(s, rs, data);
            }
        }
    }
    s->prev_e = e;
}

static void advance_ac(struct lcd_hd44780_state *s) {
    if (s->entry_id) {
        s->ac++;
    } else {
        s->ac = (uint8_t)(s->ac - 1);
    }
}

static void execute_byte(struct lcd_hd44780_state *s, uint8_t rs, uint8_t byte) {
    if (rs) {
        /* Data write: store at AC, then advance. */
        if (s->cgram_mode) {
            s->cgram[s->ac & 0x3F] = byte;
        } else {
            s->ddram[s->ac % LCD_DDRAM_SIZE] = byte;
        }
        advance_ac(s);
        s->dirty = 1;
        return;
    }

    /* Command. Decode by leading 1-bit position (highest set bit). */
    if (byte & INST_SET_DDRAM) {
        s->ac = (uint8_t)(byte & 0x7F);
        s->cgram_mode = 0;
    } else if (byte & INST_SET_CGRAM) {
        s->ac = (uint8_t)(byte & 0x3F);
        s->cgram_mode = 1;
    } else if (byte & INST_FUNCTION_SET) {
        /* DL=bit4, N=bit3, F=bit2. DL=0 -> 4-bit mode.
         * Per datasheet, F (5x10 mode) is honored only when N=0; in
         * 2-line mode the controller ignores F and always uses 5x8. */
        s->four_bit_mode = (byte & 0x10) ? 0 : 1;
        s->two_line_mode = (byte & 0x08) ? 1 : 0;
        s->font_5x10 = (!s->two_line_mode && (byte & 0x04)) ? 1 : 0;
    } else if (byte & INST_CURSOR_SHIFT) {
        /* Not modeled. */
    } else if (byte & INST_DISPLAY_CTL) {
        s->display_on = (byte & 0x04) ? 1 : 0;
        s->cursor_on  = (byte & 0x02) ? 1 : 0;
        s->blink_on   = (byte & 0x01) ? 1 : 0;
    } else if (byte & INST_ENTRY_MODE) {
        s->entry_id = (byte & 0x02) ? 1 : 0;
        s->entry_s  = (byte & 0x01) ? 1 : 0;
    } else if (byte & INST_HOME) {
        s->ac = 0;
        s->cgram_mode = 0;
    } else if (byte & INST_CLEAR) {
        memset(s->ddram, 0x20, LCD_DDRAM_SIZE);
        s->ac = 0;
        s->cgram_mode = 0;
        s->dirty = 1;
    }
}

static void lcd_hd44780_reset(struct chip *self) {
    struct lcd_hd44780_state *s = (struct lcd_hd44780_state *)self->state;
    memset(s->ddram, 0x20, LCD_DDRAM_SIZE);  /* HD44780 starts cleared */
    memset(s->cgram, 0, LCD_CGRAM_SIZE);
    s->ac = 0;
    s->cgram_mode = 0;
    s->entry_id = 1;
    s->entry_s = 0;
    s->display_on = 0;
    s->cursor_on = 0;
    s->blink_on = 0;
    s->two_line_mode = 0;
    s->four_bit_mode = 0;  /* power-on default = 8-bit */
    s->font_5x10 = 0;
    s->high_nibble = 0;
    s->high_nibble_pending = 0;
    s->prev_e = 0;
    s->dirty = 1;
}

void lcd_hd44780_init(struct chip *chip, struct lcd_hd44780_state *state,
                      const struct via_6522_state *via) {
    static const struct chip_ops ops = {
        .tick  = lcd_hd44780_tick,
        .read  = NULL,
        .write = NULL,
        .reset = lcd_hd44780_reset,
    };
    memset(state, 0, sizeof(*state));
    state->rows = 2;
    state->cols = 16;
    state->wiring = LCD_WIRING_WENDY2C;
    state->via = via;
    /* HD44780 power-on defaults: entry-mode auto-increment, display
     * off, 8-bit interface, 1-line, 5x8. */
    state->entry_id = 1;
    state->four_bit_mode = 0;
    memset(state->ddram, 0x20, LCD_DDRAM_SIZE);
    chip->ops = &ops;
    chip->name = "lcd_hd44780";
    chip->state = state;
}

void lcd_hd44780_set_wiring(struct lcd_hd44780_state *state,
                            const struct lcd_hd44780_wiring *wiring) {
    state->wiring = *wiring;
}

void lcd_hd44780_set_geometry(struct lcd_hd44780_state *state,
                              uint8_t rows, uint8_t cols) {
    if (rows < 1) rows = 1;
    if (rows > 4) rows = 4;
    if (cols < 1) cols = 1;
    if (cols > 20) cols = 20;
    state->rows = rows;
    state->cols = cols;
}

/* DDRAM line addresses for 16x2 / 20x4 (per HD44780 datasheet). */
static uint8_t line_base(uint8_t row, uint8_t cols) {
    static const uint8_t bases_16x2[2] = {0x00, 0x40};
    static const uint8_t bases_20x4[4] = {0x00, 0x40, 0x14, 0x54};
    if (cols == 20) return bases_20x4[row & 3];
    return bases_16x2[row & 1];
}

void lcd_hd44780_visible_bytes(const struct lcd_hd44780_state *s,
                               uint8_t *out_buf) {
    int idx = 0;
    for (uint8_t r = 0; r < s->rows; r++) {
        uint8_t base = line_base(r, s->cols);
        for (uint8_t c = 0; c < s->cols; c++)
            out_buf[idx++] = s->ddram[(base + c) % LCD_DDRAM_SIZE];
    }
}

int lcd_hd44780_render(struct lcd_hd44780_state *s, char *out_buf) {
    int dirty = s->dirty;
    s->dirty = 0;
    int n = s->rows * s->cols;
    uint8_t bytes[LCD_DDRAM_SIZE];
    lcd_hd44780_visible_bytes(s, bytes);
    for (int i = 0; i < n; i++) {
        uint8_t b = bytes[i];
        char ch;
        if (b == 0x06) ch = '~';
        else if (b == 0x07) ch = '\\';
        else if (b >= 0x20 && b <= 0x7E) ch = (char)b;
        else if (b == 0) ch = ' ';
        else ch = '?';
        out_buf[i] = ch;
    }
    out_buf[n] = '\0';
    return dirty;
}
