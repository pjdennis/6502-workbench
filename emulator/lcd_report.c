#include "lcd_report.h"

#include "cpu_core.h"

void lcd_report_trace(FILE *fp, struct lcd_hd44780_state *lcd, uint64_t osc_ticks) {
    if (!fp) return;
    char lcdbuf[LCD_DDRAM_SIZE + 8];
    int dirty = lcd_hd44780_render(lcd, lcdbuf);
    if (!dirty) return;
    fprintf(fp, "--- osc=%llu cpu=%llu pc=$%04X ---\n",
            (unsigned long long)osc_ticks,
            (unsigned long long)clockticks6502,
            pc);
    int cols = lcd->cols;
    for (int r = 0; r < lcd->rows; r++) {
        fprintf(fp, "|%.*s|\n", cols, lcdbuf + r * cols);
    }
    fflush(fp);
}

void lcd_report_final(FILE *fp, const char *prefix, struct lcd_hd44780_state *lcd) {
    char lcd_buf[LCD_DDRAM_SIZE + 8];
    (void)lcd_hd44780_render(lcd, lcd_buf);
    int cols = lcd->cols;
    fprintf(fp, "%s: lcd:\n", prefix);
    for (int r = 0; r < lcd->rows; r++) {
        fprintf(fp, "  |%.*s|\n", cols, lcd_buf + r * cols);
    }
    uint8_t lcd_bytes[LCD_DDRAM_SIZE];
    lcd_hd44780_visible_bytes(lcd, lcd_bytes);
    fprintf(fp, "%s: lcd-hex:\n", prefix);
    for (int r = 0; r < lcd->rows; r++) {
        fprintf(fp, "  |");
        for (int c = 0; c < cols; c++)
            fprintf(fp, c ? " %02x" : "%02x", lcd_bytes[r * cols + c]);
        fprintf(fp, "|\n");
    }
}
