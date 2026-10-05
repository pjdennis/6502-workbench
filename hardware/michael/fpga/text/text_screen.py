"""The FPGA bus's text mode as a model: the character grid that the text commands ($2x, $3x in
docs/michael-fpga-bus-plan.md) change. It behaves as the ROM's screen on the LCD does
(firmware/lib/lcd/lcd_screen.inc), so the editor sees the same screen on either display, except that it
keeps reverse video, and rows and columns are 0-based. The RTL (../rtl/text_grid.v) is tested against it.

- Writing a character puts it at the cursor and moves right, to the start of the next row after the last
  column; on the bottom row the cursor stays past the last column, and characters written there are dropped,
  so writing never scrolls. BS moves left, CR to the first column, LF to the first column of the next row
  (staying on the bottom row); other control codes are dropped.
- Counts of 0 do nothing. Counts are limited to the cells or rows there are.
- The scroll region is two rows or more; a smaller one is ignored. Setting it homes the cursor.

It also keeps what the RTL does with the display's hardware scroll (offset, and memory_row), which doesn't
change what the screen shows, only where in the display's memory each row is drawn: scrolling the whole region
by fewer rows than it has moves its picture by offset rows; a new region, with the picture scrolled, starts
again at 0 (text_grid.v, text_render.v).
"""

BLANK = (' ', False)
BS, LF, CR = 0x08, 0x0A, 0x0D


class TextScreen:
    def __init__(self, rows=20, cols=20):
        self.rows, self.cols = rows, cols
        self.text_on()

    def text_on(self):
        """As the ROM's lcd_screen_initialize: cursor hidden, normal video, the whole screen the region,
        cleared, the cursor home."""
        self.cursor, self.reverse, self.offset = False, False, 0
        self.region_reset()
        self.clear()

    # The cells, as (character, reverse)
    def cell(self, row, col):
        return self.cells[row][col]

    def text(self, row):
        return ''.join(c for c, _ in self.cells[row])

    def clear(self):
        self.cells = [[BLANK] * self.cols for _ in range(self.rows)]
        self.goto(0, 0)

    def goto(self, row, col):
        """Rows past the last go to the last; columns past the last go just past it."""
        self.row, self.col = min(row, self.rows - 1), min(col, self.cols)

    def put(self, code):
        if code >= 0x20:
            if self.col < self.cols:
                self.cells[self.row][self.col] = (chr(code), self.reverse)
                self.col += 1
                if self.col == self.cols and self.row < self.rows - 1:
                    self.row, self.col = self.row + 1, 0
        elif code == BS:
            self.col = max(self.col - 1, 0)
        elif code == LF:
            self.row, self.col = min(self.row + 1, self.rows - 1), 0
        elif code == CR:
            self.col = 0

    def set_cursor(self, on):
        self.cursor = bool(on)

    def video(self, reverse):
        self.reverse = bool(reverse)

    # Within the cursor's row
    def _shift_row(self, n, insert):
        line, col = self.cells[self.row], self.col
        n = min(n, self.cols - col)
        if n:
            rest = line[col:]
            line[col:] = [BLANK] * n + rest[:-n] if insert else rest[n:] + [BLANK] * n

    def clear_eol(self):
        self._shift_row(self.cols, insert=False)

    def insert(self, n):
        self._shift_row(n, insert=True)

    def delete(self, n):
        self._shift_row(n, insert=False)

    # The scroll region
    def region(self, top, bottom):
        bottom = min(bottom, self.rows - 1)
        if top < bottom:
            if (top, bottom) != (getattr(self, 'top', None), getattr(self, 'bottom', None)):
                self.offset = 0
            self.top, self.bottom = top, bottom
            self.goto(0, 0)

    def region_reset(self):
        self.region(0, self.rows - 1)

    def _scroll(self, top, n, up):
        rows = self.cells[top:self.bottom + 1]
        if top == self.top and 0 < n < len(rows):    # the hardware scroll moves the picture
            self.offset = (self.offset + (-n if up else n)) % len(rows)
        n = min(n, len(rows))
        if n:
            blanks = [[BLANK] * self.cols for _ in range(n)]
            self.cells[top:self.bottom + 1] = rows[n:] + blanks if up else blanks + rows[:-n]

    def scroll_up(self, n):
        self._scroll(self.top, n, up=True)

    def scroll_down(self, n):
        self._scroll(self.top, n, up=False)

    def _lines(self, n, up):
        """From the cursor's row to the region's bottom, if the cursor is in the region; the cursor to the
        row's first column."""
        if self.top <= self.row <= self.bottom:
            self.col = 0
            self._scroll(self.row, n, up)

    def memory_row(self, row):
        """The display memory row where row is drawn, through the hardware scroll."""
        if not self.top <= row <= self.bottom:
            return row
        return self.bottom - (self.offset + self.bottom - row) % (self.bottom - self.top + 1)

    def insert_lines(self, n):
        self._lines(n, up=False)

    def delete_lines(self, n):
        self._lines(n, up=True)


class ScreenPort:
    """The model with the debug port's text methods (bus/debug.py's DebugPort), so a scenario written for the
    board, such as debug.text_demo, also runs on the model."""
    def __init__(self, rows=20, cols=20):
        self.screen = TextScreen(rows, cols)

    def put(self, text):
        for ch in text.encode('latin-1'):
            self.screen.put(ch)

    def cursor(self, on):
        self.screen.set_cursor(on)

    def text_off(self):
        pass

    def __getattr__(self, name):   # text_on, goto, clear, clear_eol, insert, delete, region, ... video
        return getattr(self.screen, name)
