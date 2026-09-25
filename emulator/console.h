#ifndef CONSOLE_H
#define CONSOLE_H

#include <stdint.h>
#include <time.h>

// Console screen state (non-static for testing)
extern int screen_rows, screen_cols;
extern char *screen_cells;
extern unsigned char *screen_attr;
extern int cursor_row, cursor_col;
extern unsigned char current_attr;
extern int scroll_top, scroll_bot;
extern int show_repaints;
extern struct timespec *repaint_time;     // --show-repaints: last paint time per cell
extern unsigned char *repaint_count;      // repaints within the highlight window
extern unsigned char *repaint_displayed;  // highlight level currently on screen

// Serial state (non-static for I/O port access)
#define SERIAL_BUF_SIZE 256
extern uint8_t serial_rx_buf[SERIAL_BUF_SIZE];
extern int serial_rx_head, serial_rx_tail;
extern uint8_t serial_tx_buf[SERIAL_BUF_SIZE];
extern int serial_tx_head, serial_tx_tail;
extern uint64_t serial_cycles_per_byte;
extern char serial_inject_buf[32];
extern int serial_inject_pos, serial_inject_len;

// Console rendering
void console_resize(int rows, int cols);
void console_clear_line(int mode);
void console_clear_screen(int mode);
void console_scroll_region_up(int top, int bot, int lines);
void console_scroll_region_down(int top, int bot, int lines);
void console_scroll_up(int lines);
void console_shift_chars(int n, int insert);
void console_put_char(unsigned char ch);
void console_handle_byte(unsigned char ch);
void console_handle_csi(unsigned char final);
void console_redraw(void);
void repaint_overlay_update(struct timespec *now);

// Serial buffering
void serial_reset(void);
void serial_inject_response(const char *str);
int serial_rx_count(void);
int serial_tx_count(void);
void serial_rx_fill(void);
void serial_tx_drain(void);
void serial_tx_flush(void);

#endif
