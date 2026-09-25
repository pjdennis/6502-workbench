#include "console.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define STDIN_FILENO  0
#define STDOUT_FILENO 1

// External dependencies from emulator.c
extern uint64_t clockticks6502;
extern int terminal_interactive;
extern int terminal_mode;
extern FILE *serial_input_file;
extern FILE *serial_output_file;
extern int con_byte_ready(void);

// Console screen state
int screen_rows = 0;
int screen_cols = 0;
char *screen_cells = NULL;
unsigned char *screen_attr = NULL;
int cursor_row = 0;
int cursor_col = 0;
static int parser_state = 0;
static int csi_params[8];
static int csi_param_count = 0;
static int csi_param_value = -1;
static int csi_private = 0;
unsigned char current_attr = 0;
int scroll_top = 0;
int scroll_bot = -1;
int show_repaints = 0;
struct timespec *repaint_time = NULL;
unsigned char *repaint_count = NULL;
unsigned char *repaint_displayed = NULL;
static const unsigned char rainbow_colors[7] = {196, 208, 226, 46, 51, 21, 201};

// Serial state
uint64_t serial_cycles_per_byte = 0;
uint8_t serial_rx_buf[SERIAL_BUF_SIZE];
int serial_rx_head = 0;
int serial_rx_tail = 0;
static uint64_t serial_rx_next_fill_at = 0;
uint8_t serial_tx_buf[SERIAL_BUF_SIZE];
int serial_tx_head = 0;
int serial_tx_tail = 0;
static uint64_t serial_tx_next_drain_at = 0;
char serial_inject_buf[32];
int serial_inject_pos = 0;
int serial_inject_len = 0;

void console_resize(int rows, int cols) {
    if (rows <= 0 || cols <= 0) return;
    if (rows == screen_rows && cols == screen_cols && screen_cells != NULL) return;
    size_t sz = (size_t)rows * (size_t)cols;
    char *new_cells = malloc(sz);
    unsigned char *new_attr = malloc(sz);
    if (!new_cells) return;
    if (!new_attr) {
        free(new_cells);
        return;
    }
    memset(new_cells, ' ', sz);
    memset(new_attr, 0, sz);

    struct timespec *new_rtime = NULL;
    unsigned char *new_rcount = NULL;
    unsigned char *new_rdisp = NULL;
    if (show_repaints) {
        new_rtime = calloc(sz, sizeof(struct timespec));
        new_rcount = calloc(sz, 1);
        new_rdisp = calloc(sz, 1);
    }

    if (screen_cells) {
        int copy_rows = rows < screen_rows ? rows : screen_rows;
        int copy_cols = cols < screen_cols ? cols : screen_cols;
        for (int r = 0; r < copy_rows; r++) {
            memcpy(new_cells + r * cols, screen_cells + r * screen_cols, (size_t)copy_cols);
            memcpy(new_attr + r * cols, screen_attr + r * screen_cols, (size_t)copy_cols);
            if (show_repaints && repaint_time && new_rtime) {
                memcpy(new_rtime + r * cols, repaint_time + r * screen_cols, (size_t)copy_cols * sizeof(struct timespec));
                memcpy(new_rcount + r * cols, repaint_count + r * screen_cols, (size_t)copy_cols);
            }
        }
        free(screen_cells);
        free(screen_attr);
        free(repaint_time);
        free(repaint_count);
        free(repaint_displayed);
    }
    screen_cells = new_cells;
    screen_attr = new_attr;
    repaint_time = new_rtime;
    repaint_count = new_rcount;
    repaint_displayed = new_rdisp;
    screen_rows = rows;
    screen_cols = cols;
    scroll_top = 0;
    scroll_bot = screen_rows - 1;
    if (cursor_row >= screen_rows) cursor_row = screen_rows - 1;
    if (cursor_row < 0) cursor_row = 0;
    if (cursor_col >= screen_cols) cursor_col = screen_cols - 1;
    if (cursor_col < 0) cursor_col = 0;
}

void console_clear_line(int mode) {
    if (!screen_cells || screen_rows <= 0 || screen_cols <= 0) return;
    if (mode == 1) {
        int end = cursor_col + 1;
        if (end > screen_cols) end = screen_cols;
        memset(screen_cells + cursor_row * screen_cols, ' ', (size_t)end);
        memset(screen_attr + cursor_row * screen_cols, 0, (size_t)end);
        if (repaint_time) {
            memset(repaint_time + cursor_row * screen_cols, 0, (size_t)end * sizeof(struct timespec));
            memset(repaint_count + cursor_row * screen_cols, 0, (size_t)end);
        }
    } else if (mode == 2) {
        memset(screen_cells + cursor_row * screen_cols, ' ', (size_t)screen_cols);
        memset(screen_attr + cursor_row * screen_cols, 0, (size_t)screen_cols);
        if (repaint_time) {
            memset(repaint_time + cursor_row * screen_cols, 0, (size_t)screen_cols * sizeof(struct timespec));
            memset(repaint_count + cursor_row * screen_cols, 0, (size_t)screen_cols);
        }
    } else {
        int start = cursor_col;
        if (start < 0) start = 0;
        if (start < screen_cols) {
            memset(screen_cells + cursor_row * screen_cols + start, ' ', (size_t)(screen_cols - start));
            memset(screen_attr + cursor_row * screen_cols + start, 0, (size_t)(screen_cols - start));
            if (repaint_time) {
                memset(repaint_time + cursor_row * screen_cols + start, 0, (size_t)(screen_cols - start) * sizeof(struct timespec));
                memset(repaint_count + cursor_row * screen_cols + start, 0, (size_t)(screen_cols - start));
            }
        }
    }
}

void console_clear_screen(int mode) {
    if (!screen_cells || screen_rows <= 0 || screen_cols <= 0) return;
    size_t full = (size_t)screen_rows * (size_t)screen_cols;
    if (mode == 1) {
        for (int r = 0; r < cursor_row; r++) {
            memset(screen_cells + r * screen_cols, ' ', (size_t)screen_cols);
            memset(screen_attr + r * screen_cols, 0, (size_t)screen_cols);
            if (repaint_time) {
                memset(repaint_time + r * screen_cols, 0, (size_t)screen_cols * sizeof(struct timespec));
                memset(repaint_count + r * screen_cols, 0, (size_t)screen_cols);
            }
        }
        int end = cursor_col + 1;
        if (end > screen_cols) end = screen_cols;
        memset(screen_cells + cursor_row * screen_cols, ' ', (size_t)end);
        memset(screen_attr + cursor_row * screen_cols, 0, (size_t)end);
        if (repaint_time) {
            memset(repaint_time + cursor_row * screen_cols, 0, (size_t)end * sizeof(struct timespec));
            memset(repaint_count + cursor_row * screen_cols, 0, (size_t)end);
        }
    } else if (mode == 2 || mode == 3) {
        memset(screen_cells, ' ', full);
        memset(screen_attr, 0, full);
        if (repaint_time) {
            memset(repaint_time, 0, full * sizeof(struct timespec));
            memset(repaint_count, 0, full);
        }
    } else {
        int start = cursor_col;
        if (start < 0) start = 0;
        if (start < screen_cols) {
            memset(screen_cells + cursor_row * screen_cols + start, ' ', (size_t)(screen_cols - start));
            memset(screen_attr + cursor_row * screen_cols + start, 0, (size_t)(screen_cols - start));
            if (repaint_time) {
                memset(repaint_time + cursor_row * screen_cols + start, 0, (size_t)(screen_cols - start) * sizeof(struct timespec));
                memset(repaint_count + cursor_row * screen_cols + start, 0, (size_t)(screen_cols - start));
            }
        }
        for (int r = cursor_row + 1; r < screen_rows; r++) {
            memset(screen_cells + r * screen_cols, ' ', (size_t)screen_cols);
            memset(screen_attr + r * screen_cols, 0, (size_t)screen_cols);
            if (repaint_time) {
                memset(repaint_time + r * screen_cols, 0, (size_t)screen_cols * sizeof(struct timespec));
                memset(repaint_count + r * screen_cols, 0, (size_t)screen_cols);
            }
        }
    }
}

void console_scroll_region_up(int top, int bot, int lines) {
    if (!screen_cells || screen_rows <= 0 || screen_cols <= 0) return;
    if (lines <= 0 || top > bot) return;
    int region_rows = bot - top + 1;
    size_t row_bytes = (size_t)screen_cols;
    if (lines >= region_rows) {
        for (int r = top; r <= bot; r++) {
            memset(screen_cells + r * row_bytes, ' ', row_bytes);
            memset(screen_attr + r * row_bytes, 0, row_bytes);
        }
        if (repaint_time) {
            for (int r = top; r <= bot; r++) {
                memset(repaint_time + r * screen_cols, 0, row_bytes * sizeof(struct timespec));
                memset(repaint_count + r * screen_cols, 0, row_bytes);
                memset(repaint_displayed + r * screen_cols, 0, row_bytes);
            }
        }
        return;
    }
    size_t keep = (size_t)(region_rows - lines) * row_bytes;
    size_t clear = (size_t)lines * row_bytes;
    memmove(screen_cells + top * row_bytes, screen_cells + (top + lines) * row_bytes, keep);
    memmove(screen_attr + top * row_bytes, screen_attr + (top + lines) * row_bytes, keep);
    memset(screen_cells + (bot - lines + 1) * row_bytes, ' ', clear);
    memset(screen_attr + (bot - lines + 1) * row_bytes, 0, clear);
    if (repaint_time) {
        memmove(repaint_time + top * screen_cols, repaint_time + (top + lines) * screen_cols, keep * sizeof(struct timespec));
        memmove(repaint_count + top * screen_cols, repaint_count + (top + lines) * screen_cols, keep);
        memmove(repaint_displayed + top * screen_cols, repaint_displayed + (top + lines) * screen_cols, keep);
        memset(repaint_time + (bot - lines + 1) * screen_cols, 0, clear * sizeof(struct timespec));
        memset(repaint_count + (bot - lines + 1) * screen_cols, 0, clear);
        memset(repaint_displayed + (bot - lines + 1) * screen_cols, 0, clear);
    }
}

void console_scroll_region_down(int top, int bot, int lines) {
    if (!screen_cells || screen_rows <= 0 || screen_cols <= 0) return;
    if (lines <= 0 || top > bot) return;
    int region_rows = bot - top + 1;
    size_t row_bytes = (size_t)screen_cols;
    if (lines >= region_rows) {
        for (int r = top; r <= bot; r++) {
            memset(screen_cells + r * row_bytes, ' ', row_bytes);
            memset(screen_attr + r * row_bytes, 0, row_bytes);
        }
        if (repaint_time) {
            for (int r = top; r <= bot; r++) {
                memset(repaint_time + r * screen_cols, 0, row_bytes * sizeof(struct timespec));
                memset(repaint_count + r * screen_cols, 0, row_bytes);
                memset(repaint_displayed + r * screen_cols, 0, row_bytes);
            }
        }
        return;
    }
    size_t keep = (size_t)(region_rows - lines) * row_bytes;
    size_t clear = (size_t)lines * row_bytes;
    memmove(screen_cells + (top + lines) * row_bytes, screen_cells + top * row_bytes, keep);
    memmove(screen_attr + (top + lines) * row_bytes, screen_attr + top * row_bytes, keep);
    memset(screen_cells + top * row_bytes, ' ', clear);
    memset(screen_attr + top * row_bytes, 0, clear);
    if (repaint_time) {
        memmove(repaint_time + (top + lines) * screen_cols, repaint_time + top * screen_cols, keep * sizeof(struct timespec));
        memmove(repaint_count + (top + lines) * screen_cols, repaint_count + top * screen_cols, keep);
        memmove(repaint_displayed + (top + lines) * screen_cols, repaint_displayed + top * screen_cols, keep);
        memset(repaint_time + top * screen_cols, 0, clear * sizeof(struct timespec));
        memset(repaint_count + top * screen_cols, 0, clear);
        memset(repaint_displayed + top * screen_cols, 0, clear);
    }
}

// Shift one row's slice of a per-cell array for ICH/DCH: move the cells
// from col onward by n (right if insert, else left) and zero-fill the
// freed cells. elem = bytes per cell.
static void shift_row_cells(void *base, size_t elem, int row, int col, int n, int insert, int fill) {
    unsigned char *line = (unsigned char *)base + (size_t)row * screen_cols * elem;
    size_t keep = (size_t)(screen_cols - col - n) * elem;
    size_t gap = (size_t)n * elem;
    if (insert) {
        memmove(line + (col + n) * elem, line + col * elem, keep);
        memset(line + col * elem, fill, gap);
    } else {
        memmove(line + col * elem, line + (col + n) * elem, keep);
        memset(line + (screen_cols - n) * elem, fill, gap);
    }
}

// ICH (insert) / DCH (delete) n cells at the cursor within its row.
// Highlight state moves with the cells but is never stamped: shifting is
// not painting. Freed cells are blank, normal and unhighlighted.
void console_shift_chars(int n, int insert) {
    if (!screen_cells || cursor_row < 0 || cursor_row >= screen_rows) return;
    if (cursor_col < 0 || cursor_col >= screen_cols) return;
    if (n < 1) n = 1;
    if (n > screen_cols - cursor_col) n = screen_cols - cursor_col;
    shift_row_cells(screen_cells, 1, cursor_row, cursor_col, n, insert, ' ');
    shift_row_cells(screen_attr, 1, cursor_row, cursor_col, n, insert, 0);
    if (repaint_time) {
        shift_row_cells(repaint_time, sizeof(struct timespec), cursor_row, cursor_col, n, insert, 0);
        shift_row_cells(repaint_count, 1, cursor_row, cursor_col, n, insert, 0);
        shift_row_cells(repaint_displayed, 1, cursor_row, cursor_col, n, insert, 0);
    }
}

void console_scroll_up(int lines) {
    console_scroll_region_up(0, screen_rows - 1, lines);
}

void console_put_char(unsigned char ch) {
    if (!screen_cells || screen_rows <= 0 || screen_cols <= 0) return;
    int ebot = (scroll_bot >= 0 && scroll_bot < screen_rows) ? scroll_bot : screen_rows - 1;
    if (cursor_row < 0) cursor_row = 0;
    if (cursor_row >= screen_rows) {
        console_scroll_region_up(scroll_top, ebot, 1);
        cursor_row = screen_rows - 1;
    }
    if (cursor_col < 0) cursor_col = 0;
    if (cursor_col >= screen_cols) {
        cursor_col = 0;
        cursor_row++;
        if (cursor_row > ebot) {
            console_scroll_region_up(scroll_top, ebot, 1);
            cursor_row = ebot;
        } else if (cursor_row >= screen_rows) {
            cursor_row = screen_rows - 1;
        }
    }
    int idx = cursor_row * screen_cols + cursor_col;
    screen_cells[idx] = (char)ch;
    screen_attr[idx] = current_attr;
    if (repaint_time) {
        struct timespec now;
        clock_gettime(CLOCK_MONOTONIC, &now);
        double age = (now.tv_sec - repaint_time[idx].tv_sec)
                   + (now.tv_nsec - repaint_time[idx].tv_nsec) / 1e9;
        if (repaint_time[idx].tv_sec != 0 && age < 2.0) {
            if (repaint_count[idx] < 6)
                repaint_count[idx]++;
        } else
            repaint_count[idx] = 0;
        repaint_time[idx] = now;
        repaint_displayed[idx] = 0;
    }
    cursor_col++;
    if (cursor_col >= screen_cols) {
        cursor_col = 0;
        cursor_row++;
        if (cursor_row > ebot) {
            console_scroll_region_up(scroll_top, ebot, 1);
            cursor_row = ebot;
        } else if (cursor_row >= screen_rows) {
            cursor_row = screen_rows - 1;
        }
    }
}

void serial_reset() {
    serial_rx_head = 0;
    serial_rx_tail = 0;
    serial_rx_next_fill_at = 0;
    serial_tx_head = 0;
    serial_tx_tail = 0;
    serial_tx_next_drain_at = 0;
    serial_inject_pos = 0;
    serial_inject_len = 0;
}

int serial_rx_count() {
    return (serial_rx_head - serial_rx_tail + SERIAL_BUF_SIZE) % SERIAL_BUF_SIZE;
}

int serial_tx_count() {
    return (serial_tx_head - serial_tx_tail + SERIAL_BUF_SIZE) % SERIAL_BUF_SIZE;
}

// Fill RX buffer from input source at baud rate.
// Characters arrive from the "wire" at baud rate intervals and queue in the
// hardware FIFO. The CPU can then read them out as fast as it wants.
void serial_rx_fill() {
    int filled = 0;
    while (clockticks6502 >= serial_rx_next_fill_at &&
           serial_rx_count() < SERIAL_BUF_SIZE - 1) {
        int ch = -1;
        if (terminal_interactive) {
            if (!con_byte_ready()) break;
            uint8_t b;
            int got = read(STDIN_FILENO, &b, 1);
            if (got != 1) break;
            ch = b;
        } else if (serial_input_file) {
            ch = fgetc(serial_input_file);
            if (ch == EOF) break;
        } else {
            break;
        }
        serial_rx_buf[serial_rx_head] = (uint8_t)ch;
        serial_rx_head = (serial_rx_head + 1) % SERIAL_BUF_SIZE;
        serial_rx_next_fill_at += serial_cycles_per_byte;
        filled = 1;
    }
    // Prevent credit accumulation: when no input was available and the CPU
    // has been running (e.g. idle-polling), advance the fill timestamp so
    // future RX bytes arrive at baud rate from "now".
    if (!filled && serial_rx_next_fill_at < clockticks6502) {
        serial_rx_next_fill_at = clockticks6502;
    }
}

// Drain TX buffer to output at baud rate.
// Bytes leave the FIFO onto the "wire" at baud rate intervals.
// The CPU can fill the buffer as fast as it wants.
void serial_tx_drain() {
    while (clockticks6502 >= serial_tx_next_drain_at &&
           serial_tx_head != serial_tx_tail) {
        uint8_t b = serial_tx_buf[serial_tx_tail];
        serial_tx_tail = (serial_tx_tail + 1) % SERIAL_BUF_SIZE;
        if (terminal_interactive) {
            if (write(STDOUT_FILENO, &b, 1) < 0) {}
        } else if (serial_output_file) {
            fputc(b, serial_output_file);
        }
        if (terminal_mode) {
            console_handle_byte(b);
        }
        serial_tx_next_drain_at += serial_cycles_per_byte;
    }
    // Prevent credit accumulation: when the TX buffer is empty and the CPU
    // has been running (e.g. idle-polling for input), advance the drain
    // timestamp so future TX bytes drain at baud rate from "now", not from
    // the distant past.
    if (serial_tx_head == serial_tx_tail && serial_tx_next_drain_at < clockticks6502) {
        serial_tx_next_drain_at = clockticks6502;
    }
}

// Flush any remaining bytes in TX buffer (called at exit)
void serial_tx_flush() {
    while (serial_tx_head != serial_tx_tail) {
        uint8_t b = serial_tx_buf[serial_tx_tail];
        serial_tx_tail = (serial_tx_tail + 1) % SERIAL_BUF_SIZE;
        if (terminal_interactive) {
            if (write(STDOUT_FILENO, &b, 1) < 0) {}
        } else if (serial_output_file) {
            fputc(b, serial_output_file);
        }
        if (terminal_mode) {
            console_handle_byte(b);
        }
    }
}

void serial_inject_response(const char *str) {
    int len = (int)strlen(str);
    if (len > (int)sizeof(serial_inject_buf) - serial_inject_len) {
        len = (int)sizeof(serial_inject_buf) - serial_inject_len;
    }
    memcpy(serial_inject_buf + serial_inject_len, str, (size_t)len);
    serial_inject_len += len;
}

void console_handle_csi(unsigned char final) {
    if (csi_private) {
        csi_private = 0;
        return;
    }
    int params[8];
    int count = 0;
    for (int i = 0; i < csi_param_count && i < 8; i++) params[i] = csi_params[i];
    count = csi_param_count;
    if (count == 0) {
        params[0] = 0;
        count = 1;
    }
    switch (final) {
        case 'A': { // CUU
            int n = params[0] ? params[0] : 1;
            cursor_row -= n;
            if (cursor_row < 0) cursor_row = 0;
            break;
        }
        case 'B': { // CUD
            int n = params[0] ? params[0] : 1;
            cursor_row += n;
            if (cursor_row >= screen_rows) cursor_row = screen_rows - 1;
            break;
        }
        case 'C': { // CUF
            int n = params[0] ? params[0] : 1;
            cursor_col += n;
            if (cursor_col >= screen_cols) cursor_col = screen_cols - 1;
            break;
        }
        case 'D': { // CUB
            int n = params[0] ? params[0] : 1;
            cursor_col -= n;
            if (cursor_col < 0) cursor_col = 0;
            break;
        }
        case 'E': { // CNL
            int n = params[0] ? params[0] : 1;
            cursor_row += n;
            if (cursor_row >= screen_rows) cursor_row = screen_rows - 1;
            cursor_col = 0;
            break;
        }
        case 'F': { // CPL
            int n = params[0] ? params[0] : 1;
            cursor_row -= n;
            if (cursor_row < 0) cursor_row = 0;
            cursor_col = 0;
            break;
        }
        case 'G': { // CHA
            int n = params[0] ? params[0] : 1;
            cursor_col = n - 1;
            if (cursor_col < 0) cursor_col = 0;
            if (cursor_col >= screen_cols) cursor_col = screen_cols - 1;
            break;
        }
        case 'H':
        case 'f': { // CUP
            int r = (count > 0 && params[0] ? params[0] : 1) - 1;
            int c = (count > 1 && params[1] ? params[1] : 1) - 1;
            if (r < 0) r = 0;
            if (c < 0) c = 0;
            if (r >= screen_rows) r = screen_rows - 1;
            if (c >= screen_cols) c = screen_cols - 1;
            cursor_row = r;
            cursor_col = c;
            break;
        }
        case 'J': { // ED
            console_clear_screen(params[0]);
            break;
        }
        case 'K': { // EL
            console_clear_line(params[0]);
            break;
        }
        case 'n': { // DSR
            if (params[0] == 6) {
                char buf[32];
                snprintf(buf, sizeof(buf), "\x1b[%d;%dR", cursor_row + 1, cursor_col + 1);
                serial_inject_response(buf);
            }
            break;
        }
        case 'r': { // DECSTBM - Set Top and Bottom Margins
            if (count >= 2 && params[0] > 0 && params[1] > 0) {
                scroll_top = params[0] - 1;
                scroll_bot = params[1] - 1;
                if (scroll_top < 0) scroll_top = 0;
                if (scroll_bot >= screen_rows) scroll_bot = screen_rows - 1;
                if (scroll_top > scroll_bot) {
                    scroll_top = 0;
                    scroll_bot = screen_rows - 1;
                }
            } else {
                scroll_top = 0;
                scroll_bot = screen_rows - 1;
            }
            break;
        }
        case 'S': { // SU - Scroll Up
            int n = params[0] ? params[0] : 1;
            int ebot = (scroll_bot >= 0 && scroll_bot < screen_rows) ? scroll_bot : screen_rows - 1;
            console_scroll_region_up(scroll_top, ebot, n);
            break;
        }
        case 'T': { // SD - Scroll Down
            int n = params[0] ? params[0] : 1;
            int ebot = (scroll_bot >= 0 && scroll_bot < screen_rows) ? scroll_bot : screen_rows - 1;
            console_scroll_region_down(scroll_top, ebot, n);
            break;
        }
        case '@': { // ICH - Insert Characters
            console_shift_chars(params[0], 1);
            break;
        }
        case 'P': { // DCH - Delete Characters
            console_shift_chars(params[0], 0);
            break;
        }
        case 'm': { // SGR
            for (int i = 0; i < count; i++) {
                int p = params[i];
                if (p == 0) {
                    current_attr = 0;
                } else if (p == 7) {
                    current_attr = 1;
                } else if (p == 27) {
                    current_attr = 0;
                }
            }
            break;
        }
        default:
            break;
    }
}

void console_handle_byte(unsigned char ch) {
    if (parser_state == 0) {
        if (ch == 0x1b) {
            parser_state = 1;
            return;
        }
        if (ch == '\r') {
            cursor_col = 0;
            return;
        }
        if (ch == '\n') {
            int ebot = (scroll_bot >= 0 && scroll_bot < screen_rows) ? scroll_bot : screen_rows - 1;
            cursor_row++;
            if (cursor_row > ebot) {
                console_scroll_region_up(scroll_top, ebot, 1);
                cursor_row = ebot;
            } else if (cursor_row >= screen_rows) {
                cursor_row = screen_rows - 1;
            }
            return;
        }
        if (ch == '\b') {
            cursor_col--;
            if (cursor_col < 0) cursor_col = 0;
            return;
        }
        if (ch == '\t') {
            int next_tab = (cursor_col + 8) & ~7;
            if (next_tab >= screen_cols) next_tab = screen_cols - 1;
            cursor_col = next_tab;
            return;
        }
        if (ch >= 0x20) {
            console_put_char(ch);
        }
        return;
    }
    if (parser_state == 1) {
        if (ch == '[') {
            parser_state = 2;
            csi_param_count = 0;
            csi_param_value = -1;
            return;
        }
        parser_state = 0;
        return;
    }
    if (parser_state == 2) {
        if (ch == '?' && csi_param_count == 0 && csi_param_value < 0) {
            csi_private = 1;
            return;
        }
        if (ch >= '0' && ch <= '9') {
            if (csi_param_value < 0) csi_param_value = 0;
            csi_param_value = csi_param_value * 10 + (ch - '0');
            return;
        }
        if (ch == ';') {
            if (csi_param_count < 8) {
                csi_params[csi_param_count++] = (csi_param_value < 0) ? 0 : csi_param_value;
            }
            csi_param_value = -1;
            return;
        }
        if (csi_param_count < 8) {
            csi_params[csi_param_count++] = (csi_param_value < 0) ? 0 : csi_param_value;
        }
        console_handle_csi(ch);
        parser_state = 0;
        return;
    }
}

void repaint_overlay_update(struct timespec *now) {
    if (!repaint_time || !screen_cells) return;
    // Don't inject overlay if the 6502 is mid-ANSI-sequence
    if (parser_state != 0) return;

    // Buffer all output to emit atomically
    // Worst case per cell: cursor pos (12) + bg color (16) + reverse (4) + char (1) + unreverse (5) + bg reset (5) = ~43
    // Plus trailer: reset (4) + restore attr (4) + cursor pos (12) = ~20
    size_t buf_size = (size_t)screen_rows * (size_t)screen_cols * 48 + 64;
    char *buf = malloc(buf_size);
    if (!buf) return;
    size_t pos = 0;
    int any_changed = 0;

    for (int r = 0; r < screen_rows; r++) {
        int run_color = -1;   // current run's desired color (-1 = no active run)
        int run_attr = -1;    // current run's attr
        int last_col = -2;    // last column written (-2 = none)
        for (int c = 0; c < screen_cols; c++) {
            int idx = r * screen_cols + c;
            unsigned char desired = 0;  // 0 = no background
            if (repaint_time[idx].tv_sec != 0) {
                double age = (now->tv_sec - repaint_time[idx].tv_sec)
                           + (now->tv_nsec - repaint_time[idx].tv_nsec) / 1e9;
                if (age < 2.0) {
                    desired = repaint_count[idx] + 1;  // 1-7
                }
            }
            if (desired != repaint_displayed[idx]) {
                any_changed = 1;
                unsigned char attr = screen_attr[idx];
                // Continue current run if consecutive column with same color and attr
                if (c == last_col + 1 && (int)desired == run_color && (int)attr == run_attr) {
                    buf[pos++] = screen_cells[idx];
                } else {
                    // Start a new run: cursor pos + attributes + color
                    pos += (size_t)snprintf(buf + pos, buf_size - pos, "\x1b[%d;%dH", r + 1, c + 1);
                    memcpy(buf + pos, "\x1b[0m", 4); pos += 4;
                    if (attr) {
                        memcpy(buf + pos, "\x1b[7m", 4); pos += 4;
                    }
                    if (desired) {
                        if (attr) {
                            pos += (size_t)snprintf(buf + pos, buf_size - pos, "\x1b[38;5;%dm", rainbow_colors[desired - 1]);
                        } else {
                            pos += (size_t)snprintf(buf + pos, buf_size - pos, "\x1b[48;5;%dm", rainbow_colors[desired - 1]);
                        }
                    }
                    buf[pos++] = screen_cells[idx];
                    run_color = (int)desired;
                    run_attr = (int)attr;
                }
                last_col = c;
                repaint_displayed[idx] = desired;
            } else {
                // Cell doesn't need updating - break the run
                run_color = -1;
                last_col = -2;
            }
        }
    }

    if (any_changed) {
        // Reset all attributes to clean state, then restore 6502's current state
        memcpy(buf + pos, "\x1b[0m", 4); pos += 4;
        if (current_attr) {
            memcpy(buf + pos, "\x1b[7m", 4); pos += 4;
        }
        // Restore cursor to where the 6502 expects it
        pos += (size_t)snprintf(buf + pos, buf_size - pos, "\x1b[%d;%dH", cursor_row + 1, cursor_col + 1);
        if (write(STDOUT_FILENO, buf, pos) < 0) {}
    }
    free(buf);
}

void console_redraw() {
    if (!screen_cells || screen_rows <= 0 || screen_cols <= 0) return;
    unsigned char last_attr = 0;
    const char reset[] = "\x1b[0m";
    if (write(STDOUT_FILENO, reset, sizeof(reset) - 1) < 0) {
    }
    for (int r = 0; r < screen_rows; r++) {
        char pos[32];
        int pos_len = snprintf(pos, sizeof(pos), "\x1b[%d;1H", r + 1);
        if (pos_len > 0) {
            if (write(STDOUT_FILENO, pos, (size_t)pos_len) < 0) {
            }
        }
        for (int c = 0; c < screen_cols; c++) {
            unsigned char attr = screen_attr[r * screen_cols + c];
            if (attr != last_attr) {
                if (attr) {
                    const char rev[] = "\x1b[7m";
                    if (write(STDOUT_FILENO, rev, sizeof(rev) - 1) < 0) {
                    }
                } else {
                    const char norm[] = "\x1b[0m";
                    if (write(STDOUT_FILENO, norm, sizeof(norm) - 1) < 0) {
                    }
                }
                last_attr = attr;
            }
            if (write(STDOUT_FILENO, screen_cells + r * screen_cols + c, 1) < 0) {
            }
        }
    }
    if (current_attr) {
        const char rev[] = "\x1b[7m";
        if (write(STDOUT_FILENO, rev, sizeof(rev) - 1) < 0) {
        }
    } else {
        if (write(STDOUT_FILENO, reset, sizeof(reset) - 1) < 0) {
        }
    }
    char cur[32];
    int len = snprintf(cur, sizeof(cur), "\x1b[%d;%dH", cursor_row + 1, cursor_col + 1);
    if (len > 0) {
        if (write(STDOUT_FILENO, cur, (size_t)len) < 0) {
        }
    }
    if (repaint_displayed) {
        memset(repaint_displayed, 0, (size_t)screen_rows * (size_t)screen_cols);
    }
}
