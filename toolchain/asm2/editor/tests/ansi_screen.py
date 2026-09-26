"""
ANSI virtual terminal emulator for testing editor screen output.

Processes ANSI escape sequences into a virtual screen buffer with cursor
tracking. Only handles sequences the editor actually emits.

A missing or 0 numeric parameter takes its default (1, or the last row for
the bottom of a scroll region), as on real terminals.

Supported sequences:
    ESC[2J          - Clear screen
    ESC[{r};{c}H    - Cursor move (1-based)
    ESC[H           - Cursor home (1,1)
    ESC[K           - Clear to end of line
    ESC[7m / ESC[0m - Reverse/normal video (tracked per-cell in attrs buffer)
    ESC[?25l        - Cursor hide
    ESC[?25h        - Cursor show (triggers frame snapshot)
    ESC[{t};{b}r    - Set scroll region (1-based top;bottom) and home the
                      cursor; like a VT100 or xterm, ignore a region of
                      fewer than two rows
    ESC[r           - Reset scroll region to full screen and home the cursor
    ESC[{n}S        - Scroll up n lines (content moves up, blanks at bottom)
    ESC[{n}T        - Scroll down n lines (content moves down, blanks at top)
    ESC[{n}L        - Insert n blank lines at the cursor row (IL)
    ESC[{n}M        - Delete n lines at the cursor row (DL)
                      (IL and DL work down to the bottom margin, are ignored
                      outside the region and move the cursor to column 1)
    ESC[{n}@        - Insert n blank characters at cursor (ICH)
    ESC[{n}P        - Delete n characters at cursor (DCH)
    \b              - Backspace (one column left, stopping at column 1)

Deferred auto-wrap (the default; deferred_wrap=False wraps at once):
    Matches real VT100/xterm behavior where writing to the last column
    sets a pending-wrap flag instead of immediately advancing the cursor.
    ESC[K in this state clears from the last column, erasing the character.
    Cursor movement commands (ESC[r;cH) cancel the pending wrap.
    A character written with a wrap pending on the bottom margin of the
    scroll region scrolls the region up a line, as on a real terminal (so
    text that overflows the status row scrolls the whole screen).
"""


def _csi_args(params, *defaults):
    """The numeric parameters of a CSI sequence, one per default; a missing
    or 0 parameter takes its default."""
    parts = params.split(';')
    return [(int(parts[i]) if i < len(parts) and parts[i] else 0) or default
            for i, default in enumerate(defaults)]


class AnsiScreen:
    ATTR_REVERSE = 0x01

    def __init__(self, rows, cols, deferred_wrap=True):
        self.rows = rows
        self.cols = cols
        self.deferred_wrap = deferred_wrap
        self._pending_wrap = False
        self.buffer = [[' '] * cols for _ in range(rows)]
        self.attrs = [[0] * cols for _ in range(rows)]
        self.cursor_row = 0  # 0-based
        self.cursor_col = 0
        self.reverse_video = False
        self.cursor_visible = True
        # Snapshot of last rendered frame (captured at ESC[?25h)
        self.frame_buffer = None
        self.frame_attrs = None
        self.frame_cursor = (0, 0)
        # Scroll region (0-based, inclusive)
        self.scroll_top = 0
        self.scroll_bottom = rows - 1
        # Per-frame tracking for render optimization tests
        self.frames = []            # List of (buffer_copy, cursor_pos, content_touched, attrs_copy, min_content_col, max_content_col, frame_scrolled, scroll_touched)
        self.content_touched = set()  # Set of content row indices written this cycle
        self.min_content_col = {}     # row → min column index written this cycle
        self.max_content_col = {}     # row → max column index written this cycle
        self.frame_scrolled = False   # Whether any scroll happened this cycle
        self.scroll_touched = set()   # Content row indices moved by scroll operations

    def _clear_screen(self):
        self.buffer = [[' '] * self.cols for _ in range(self.rows)]
        self.attrs = [[0] * self.cols for _ in range(self.rows)]
        self.content_touched = set(range(self.rows - 1))
        self.min_content_col = {}
        self.max_content_col = {}
        self.frame_scrolled = False
        self.scroll_touched = set()
        self._pending_wrap = False

    def _clear_to_eol(self):
        row = self.cursor_row
        if 0 <= row < self.rows:
            if row < self.rows - 1:
                self.content_touched.add(row)
                col = self.cursor_col
                if col < self.cols:
                    if row not in self.min_content_col or col < self.min_content_col[row]:
                        self.min_content_col[row] = col
                    end_col = self.cols - 1
                    if row not in self.max_content_col or end_col > self.max_content_col[row]:
                        self.max_content_col[row] = end_col
            for c in range(self.cursor_col, self.cols):
                self.buffer[row][c] = ' '
                self.attrs[row][c] = 0

    def _move_cursor(self, row, col):
        self.cursor_row = row
        self.cursor_col = col
        self._pending_wrap = False

    def _put_char(self, ch):
        # Deferred wrap: resolve pending wrap before writing next character
        if self.deferred_wrap and self._pending_wrap:
            self.cursor_col = 0
            if self.cursor_row == self.scroll_bottom:
                self._scroll(self.scroll_top, 1, up=True)
            elif self.cursor_row < self.rows - 1:
                self.cursor_row += 1
            self._pending_wrap = False
        if self.cursor_row < 0 or self.cursor_row >= self.rows:
            return
        if self.cursor_col < 0 or self.cursor_col >= self.cols:
            return
        if self.cursor_row < self.rows - 1:
            self.content_touched.add(self.cursor_row)
            row = self.cursor_row
            col = self.cursor_col
            if row not in self.min_content_col or col < self.min_content_col[row]:
                self.min_content_col[row] = col
            if row not in self.max_content_col or col > self.max_content_col[row]:
                self.max_content_col[row] = col
        self.buffer[self.cursor_row][self.cursor_col] = ch
        self.attrs[self.cursor_row][self.cursor_col] = self.ATTR_REVERSE if self.reverse_video else 0
        self.cursor_col += 1
        # Deferred wrap: stay at last column with pending flag
        if self.deferred_wrap and self.cursor_col >= self.cols:
            self.cursor_col = self.cols - 1
            self._pending_wrap = True
        # Immediate wrap: cursor past last column wraps to next row
        if not self.deferred_wrap and self.cursor_col >= self.cols:
            self.cursor_col = 0
            self.cursor_row += 1
            if self.cursor_row >= self.rows:
                self.cursor_row = self.rows - 1

    def _set_scroll_region(self, top, bottom):
        """Set scroll region (0-based, inclusive) and home the cursor, as
        DECSTBM does; like a VT100 or xterm, ignore a region of fewer than
        two rows."""
        bottom = min(bottom, self.rows - 1)
        if top < bottom:
            self.scroll_top = top
            self.scroll_bottom = bottom
            self._move_cursor(0, 0)

    def _scroll(self, top, n, up):
        """Scroll rows top..scroll_bottom up by n (content moves up, blanks
        at the bottom) or down (blanks at the top). Does NOT mark rows as
        content_touched since the terminal hardware performs the scroll -
        only explicit character writes count. The content rows it moves
        (not the status row) go into scroll_touched."""
        bottom = self.scroll_bottom
        self.frame_scrolled = True
        self.scroll_touched.update(range(top, min(bottom, self.rows - 2) + 1))
        n = min(n, bottom + 1 - top)
        for grid, blank in ((self.buffer, ' '), (self.attrs, 0)):
            kept = grid[top + n:bottom + 1] if up else grid[top:bottom + 1 - n]
            blanks = [[blank] * self.cols for _ in range(n)]
            grid[top:bottom + 1] = kept + blanks if up else blanks + kept

    def _shift_chars(self, n, insert):
        """ICH/DCH: insert or delete n cells at the cursor within its row.
        Cells pushed past the right margin are lost; freed cells are blank
        with normal attributes. The cursor does not move. The row counts as
        touched (its content changed), but no cells count as written, so
        min/max column tracking measures only what was actually sent."""
        self._pending_wrap = False
        row, col = self.cursor_row, self.cursor_col
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            return
        if row < self.rows - 1:
            self.content_touched.add(row)
        n = min(n, self.cols - col)
        for line, blank in ((self.buffer[row], ' '), (self.attrs[row], 0)):
            if insert:
                line[col:] = [blank] * n + line[col:self.cols - n]
            else:
                line[col:] = line[col + n:] + [blank] * n

    def _snapshot(self):
        """Capture current buffer and cursor as a frame."""
        self.frame_buffer = [row[:] for row in self.buffer]
        self.frame_attrs = [row[:] for row in self.attrs]
        self.frame_cursor = (self.cursor_row, self.cursor_col)
        self.frames.append((self.frame_buffer, self.frame_cursor,
                            self.content_touched, self.frame_attrs,
                            self.min_content_col, self.max_content_col,
                            self.frame_scrolled, self.scroll_touched))
        self.content_touched = set()
        self.min_content_col = {}
        self.max_content_col = {}
        self.frame_scrolled = False
        self.scroll_touched = set()

    def process(self, data: str) -> 'AnsiScreen':
        """Process ANSI output data through the virtual terminal."""
        NORMAL = 0
        ESC = 1
        CSI = 2

        state = NORMAL
        params = ""
        i = 0

        while i < len(data):
            ch = data[i]
            i += 1

            if state == NORMAL:
                if ch == '\x1b':
                    state = ESC
                    params = ""
                elif ch == '\n':
                    self.cursor_row += 1
                    self.cursor_col = 0
                elif ch == '\r':
                    self.cursor_col = 0
                elif ch == '\b':
                    self._move_cursor(self.cursor_row,
                                      max(0, self.cursor_col - 1))
                elif ch >= ' ' and ch <= '~':
                    self._put_char(ch)
            elif state == ESC:
                if ch == '[':
                    state = CSI
                else:
                    state = NORMAL
            elif state == CSI:
                if ch.isdigit() or ch == ';' or ch == '?':
                    params += ch
                else:
                    # Dispatch CSI sequence
                    self._dispatch_csi(params, ch)
                    state = NORMAL

        return self

    def _dispatch_csi(self, params, final):
        if final == 'J':
            # Clear screen (only ESC[2J supported)
            if params == '2':
                self._clear_screen()
        elif final == 'H':
            # Cursor position
            row, col = _csi_args(params, 1, 1)
            self._move_cursor(row - 1, col - 1)
        elif final == 'K':
            # Clear to end of line
            self._clear_to_eol()
        elif final == 'm':
            # SGR - Select Graphic Rendition
            if params == '7':
                self.reverse_video = True
            elif params == '0' or params == '':
                self.reverse_video = False
        elif final == 'l':
            # Private mode reset
            if params == '?25':
                self.cursor_visible = False
        elif final == 'h':
            # Private mode set
            if params == '?25':
                self.cursor_visible = True
                self._snapshot()
        elif final == 'r':
            # Set/reset scroll region (no parameters: the whole screen)
            top, bottom = _csi_args(params, 1, self.rows)
            self._set_scroll_region(top - 1, bottom - 1)
        elif final in 'ST':
            # Scroll the region up (S) or down (T)
            n, = _csi_args(params, 1)
            self._scroll(self.scroll_top, n, up=final == 'S')
        elif final in 'LM':
            # IL / DL - Insert or delete lines at the cursor row
            n, = _csi_args(params, 1)
            if self.scroll_top <= self.cursor_row <= self.scroll_bottom:
                self._scroll(self.cursor_row, n, up=final == 'M')
                self._move_cursor(self.cursor_row, 0)
        elif final in '@P':
            # ICH / DCH - Insert or delete blank characters
            n, = _csi_args(params, 1)
            self._shift_chars(n, insert=final == '@')

    def get_frame_count(self) -> int:
        """Number of rendered frames (cursor-show events)."""
        return len(self.frames)

    def was_content_redrawn(self, frame_idx: int) -> bool:
        """True if content area was written during this frame's render cycle."""
        if frame_idx < 0 or frame_idx >= len(self.frames):
            return False
        return len(self.frames[frame_idx][2]) > 0

    def content_rows_touched(self, frame_idx: int) -> set:
        """Set of content row indices written during this frame."""
        if frame_idx < 0 or frame_idx >= len(self.frames):
            return set()
        return self.frames[frame_idx][2]

    def was_scrolled(self, frame_idx: int) -> bool:
        """True if a scroll operation was performed during this frame."""
        if frame_idx < 0 or frame_idx >= len(self.frames):
            return False
        return self.frames[frame_idx][6]

    def scroll_rows_touched(self, frame_idx: int) -> set:
        """Set of content row indices moved by scroll operations during this frame."""
        if frame_idx < 0 or frame_idx >= len(self.frames):
            return set()
        return self.frames[frame_idx][7]

    def get_min_col(self, frame_idx: int, row: int) -> int:
        """Minimum column index written to on a given row in a given frame.
        Returns -1 if the row was not written to in that frame."""
        if frame_idx < 0 or frame_idx >= len(self.frames):
            return -1
        min_cols = self.frames[frame_idx][4]
        return min_cols.get(row, -1)

    def get_max_col(self, frame_idx: int, row: int) -> int:
        """Maximum column index written to on a given row in a given frame.
        Returns -1 if the row was not written to in that frame."""
        if frame_idx < 0 or frame_idx >= len(self.frames):
            return -1
        max_cols = self.frames[frame_idx][5]
        return max_cols.get(row, -1)

    def get_row_text(self, row: int) -> str:
        """Row text from last rendered frame, rstripped."""
        if self.frame_buffer is None:
            return ""
        if row < 0 or row >= self.rows:
            return ""
        return ''.join(self.frame_buffer[row]).rstrip()

    def get_row_text_at_frame(self, frame_idx: int, row: int) -> str:
        """Row text from a specific frame, rstripped."""
        if frame_idx < 0 or frame_idx >= len(self.frames):
            return ""
        buf = self.frames[frame_idx][0]
        if row < 0 or row >= self.rows:
            return ""
        return ''.join(buf[row]).rstrip()

    def get_cursor(self) -> tuple:
        """Cursor (row, col) from last rendered frame, 0-based."""
        return self.frame_cursor

    def is_reverse_at(self, row: int, col: int) -> bool:
        """True if cell at (row, col) has reverse video in last rendered frame."""
        if self.frame_attrs is None:
            return False
        if row < 0 or row >= self.rows or col < 0 or col >= self.cols:
            return False
        return (self.frame_attrs[row][col] & self.ATTR_REVERSE) != 0

    def dump(self) -> str:
        """Return a string representation of the last rendered frame for debugging."""
        if self.frame_buffer is None:
            return "(no frame captured)"
        lines = []
        r, c = self.frame_cursor
        for i in range(self.rows):
            row_text = ''.join(self.frame_buffer[i]).rstrip()
            if i == r:
                lines.append(f"  {i:2d}: {row_text!r}  <- cursor at col {c}")
            else:
                lines.append(f"  {i:2d}: {row_text!r}")
        return '\n'.join(lines)


if __name__ == "__main__":
    # Self-test
    s = AnsiScreen(5, 20)

    # Test basic character output
    s.process("Hello")
    assert s.buffer[0][:5] == list("Hello"), f"got {s.buffer[0][:5]}"

    # Test cursor move and write
    s.process("\x1b[2;3HXY")
    assert s.buffer[1][2] == 'X'
    assert s.buffer[1][3] == 'Y'

    # Test clear screen
    s.process("\x1b[2J")
    assert s.buffer[0] == [' '] * 20
    assert s.buffer[1] == [' '] * 20

    # Test clear to end of line
    s.process("\x1b[1;1H")
    s.process("ABCDEF")
    s.process("\x1b[1;3H")  # col 3 (0-based: 2)
    s.process("\x1b[K")
    assert s.buffer[0][:6] == ['A', 'B', ' ', ' ', ' ', ' ']

    # Test frame snapshot on cursor show
    s2 = AnsiScreen(3, 10)
    s2.process("\x1b[2J\x1b[1;1HLine1\x1b[2;1HLine2\x1b[1;4H")
    s2.process("\x1b[?25h")  # cursor show -> snapshot
    assert s2.get_row_text(0) == "Line1"
    assert s2.get_row_text(1) == "Line2"
    assert s2.get_cursor() == (0, 3)

    # Test that cursor home works
    s3 = AnsiScreen(3, 10)
    s3.process("\x1b[5;5H")
    s3.process("\x1b[H")
    s3.process("\x1b[?25h")
    assert s3.get_cursor() == (0, 0)

    # Test frame tracking for content changes
    s4 = AnsiScreen(5, 20)
    # Frame 1: write to content area + show cursor
    s4.process("\x1b[1;1HHello\x1b[K\x1b[?25h")
    assert s4.get_frame_count() == 1
    assert s4.was_content_redrawn(0) == True

    # Frame 2: only write to status bar (last row) + show cursor
    s4.process("\x1b[5;1Hstatus\x1b[K\x1b[1;1H\x1b[?25h")
    assert s4.get_frame_count() == 2
    assert s4.was_content_redrawn(1) == False

    # Frame 3: write to content area again
    s4.process("\x1b[2;1HWorld\x1b[K\x1b[?25h")
    assert s4.get_frame_count() == 3
    assert s4.was_content_redrawn(2) == True

    # Test reverse video attribute tracking
    s5 = AnsiScreen(3, 10)
    s5.process("AB")
    s5.process("\x1b[7m")   # reverse video on
    s5.process("CD")
    s5.process("\x1b[0m")   # normal video
    s5.process("EF")
    s5.process("\x1b[?25h")  # snapshot
    assert s5.get_row_text(0) == "ABCDEF"
    assert s5.is_reverse_at(0, 0) == False, "A should be normal"
    assert s5.is_reverse_at(0, 1) == False, "B should be normal"
    assert s5.is_reverse_at(0, 2) == True, "C should be reverse"
    assert s5.is_reverse_at(0, 3) == True, "D should be reverse"
    assert s5.is_reverse_at(0, 4) == False, "E should be normal"
    assert s5.is_reverse_at(0, 5) == False, "F should be normal"

    # Immediate wrap (deferred_wrap=False): the cursor moves to the next
    # row as soon as the last column is written
    s5b = AnsiScreen(3, 5, deferred_wrap=False)
    s5b.process("ABCDEF\x1b[?25h")
    assert [s5b.get_row_text(r) for r in range(2)] == ["ABCDE", "F"]
    assert s5b.get_cursor() == (1, 1), s5b.get_cursor()

    # Test deferred wrap: writing to last column sets pending wrap
    s6 = AnsiScreen(3, 5, deferred_wrap=True)
    s6.process("ABCDE")  # 5 chars on 5-col screen
    # After writing 'E' at col 4, cursor stays at col 4 with pending wrap
    assert s6.cursor_col == 4, f"expected col 4, got {s6.cursor_col}"
    assert s6._pending_wrap == True, "pending wrap should be set"
    assert s6.buffer[0] == list("ABCDE"), f"got {s6.buffer[0]}"

    # ESC[K in pending wrap state clears from last column (the bug!)
    s7 = AnsiScreen(3, 5, deferred_wrap=True)
    s7.process("ABCDE")    # fill row, pending wrap at col 4
    s7.process("\x1b[K")    # clear to end of line
    # With deferred wrap, ESC[K clears col 4 (the 'E')
    assert s7.buffer[0] == list("ABCD "), f"expected 'ABCD ', got {''.join(s7.buffer[0])!r}"

    # Cursor move cancels pending wrap
    s8 = AnsiScreen(3, 5, deferred_wrap=True)
    s8.process("ABCDE")        # fill row, pending wrap
    s8.process("\x1b[1;1H")    # move to (0,0), cancels pending wrap
    s8.process("X")            # overwrites 'A' at (0,0)
    assert s8.buffer[0] == list("XBCDE"), f"got {''.join(s8.buffer[0])!r}"

    # Next char after pending wrap goes to next row
    s9 = AnsiScreen(3, 5, deferred_wrap=True)
    s9.process("ABCDE")    # fill row, pending wrap
    s9.process("F")         # resolves wrap: cursor to (1,0), writes 'F'
    assert s9.buffer[0] == list("ABCDE"), f"row 0: {''.join(s9.buffer[0])!r}"
    assert s9.buffer[1][0] == 'F', f"row 1 col 0: {s9.buffer[1][0]!r}"

    def rows_of(screen):
        return [screen.get_row_text(r) for r in range(screen.rows)]

    # A wrap pending on the bottom margin scrolls the region up a line; on
    # the last row below the region nothing scrolls and the cursor goes to
    # column 0 of the same row
    s9b = AnsiScreen(3, 5, deferred_wrap=True)
    s9b.process("\x1b[1;1HAAA\x1b[2;1HBBB\x1b[3;1HCCCCCD\x1b[?25h")
    assert rows_of(s9b) == ["BBB", "CCCCC", "D"], rows_of(s9b)
    s9c = AnsiScreen(3, 5, deferred_wrap=True)
    s9c.process("\x1b[1;2rAAA\x1b[3;1HCCCCCD\x1b[?25h")
    assert rows_of(s9c) == ["AAA", "", "DCCCC"], rows_of(s9c)

    # Test scroll region: set region and scroll up
    s10 = AnsiScreen(5, 10)
    # Fill rows: row0="AAA", row1="BBB", row2="CCC", row3="DDD", row4="EEE"
    s10.process("\x1b[1;1HAAA\x1b[2;1HBBB\x1b[3;1HCCC\x1b[4;1HDDD\x1b[5;1HEEE")
    # Set scroll region rows 2-4 (1-based), then scroll up 1
    s10.process("\x1b[2;4r")
    s10.process("\x1b[1S")
    s10.process("\x1b[r")  # reset scroll region
    s10.process("\x1b[?25h")
    # Row 0 unchanged (outside region), rows 1-3 shifted up within region
    assert s10.get_row_text(0) == "AAA", f"got {s10.get_row_text(0)!r}"
    assert s10.get_row_text(1) == "CCC", f"got {s10.get_row_text(1)!r}"
    assert s10.get_row_text(2) == "DDD", f"got {s10.get_row_text(2)!r}"
    assert s10.get_row_text(3) == "", f"got {s10.get_row_text(3)!r}"  # blank
    assert s10.get_row_text(4) == "EEE", f"got {s10.get_row_text(4)!r}"

    # Test scroll region: scroll down
    s11 = AnsiScreen(5, 10)
    s11.process("\x1b[1;1HAAA\x1b[2;1HBBB\x1b[3;1HCCC\x1b[4;1HDDD\x1b[5;1HEEE")
    # Set scroll region rows 2-4 (1-based), then scroll down 1
    s11.process("\x1b[2;4r")
    s11.process("\x1b[1T")
    s11.process("\x1b[r")
    s11.process("\x1b[?25h")
    assert s11.get_row_text(0) == "AAA", f"got {s11.get_row_text(0)!r}"
    assert s11.get_row_text(1) == "", f"got {s11.get_row_text(1)!r}"  # blank
    assert s11.get_row_text(2) == "BBB", f"got {s11.get_row_text(2)!r}"
    assert s11.get_row_text(3) == "CCC", f"got {s11.get_row_text(3)!r}"
    assert s11.get_row_text(4) == "EEE", f"got {s11.get_row_text(4)!r}"

    # Test scroll region: scroll up by 2
    s12 = AnsiScreen(6, 10)
    s12.process("\x1b[1;1HAAA\x1b[2;1HBBB\x1b[3;1HCCC\x1b[4;1HDDD\x1b[5;1HEEE\x1b[6;1HFFF")
    s12.process("\x1b[1;5r")  # region rows 1-5 (0-based 0-4)
    s12.process("\x1b[2S")    # scroll up 2
    s12.process("\x1b[r")
    s12.process("\x1b[?25h")
    assert s12.get_row_text(0) == "CCC", f"got {s12.get_row_text(0)!r}"
    assert s12.get_row_text(1) == "DDD", f"got {s12.get_row_text(1)!r}"
    assert s12.get_row_text(2) == "EEE", f"got {s12.get_row_text(2)!r}"
    assert s12.get_row_text(3) == "", f"got {s12.get_row_text(3)!r}"
    assert s12.get_row_text(4) == "", f"got {s12.get_row_text(4)!r}"
    assert s12.get_row_text(5) == "FFF", f"got {s12.get_row_text(5)!r}"

    # Test reset scroll region (ESC[r with no params)
    s13 = AnsiScreen(3, 10)
    s13.process("\x1b[2;3r")  # set narrow region
    assert s13.scroll_top == 1
    assert s13.scroll_bottom == 2
    s13.process("\x1b[r")     # reset
    assert s13.scroll_top == 0
    assert s13.scroll_bottom == 2

    # A region of fewer than two rows is ignored (it neither sets the region
    # nor homes the cursor), as on a VT100 or xterm
    s13b = AnsiScreen(4, 10)
    s13b.process("\x1b[2;4r\x1b[3;5H\x1b[3;3rA")
    assert (s13b.scroll_top, s13b.scroll_bottom) == (1, 3)
    assert s13b.buffer[2][4] == 'A'

    # Setting or resetting the scroll region homes the cursor
    s13c = AnsiScreen(4, 5)
    s13c.process("\x1b[3;4H\x1b[2;3rA")
    assert s13c.buffer[0][0] == 'A'
    s13c.process("\x1b[3;4H\x1b[rB")
    assert s13c.buffer[0][:2] == ['B', ' ']

    def row0(screen):
        return ''.join(screen.buffer[0])

    # ICH: insert blanks at cursor, shift the rest right, cursor stays
    s14 = AnsiScreen(3, 10)
    s14.process("ABCDEF\x1b[1;3H\x1b[2@")
    assert row0(s14) == "AB  CDEF  ", f"got {row0(s14)!r}"
    assert (s14.cursor_row, s14.cursor_col) == (0, 2)

    # ICH with no count inserts one blank
    s15 = AnsiScreen(3, 10)
    s15.process("ABC\x1b[1;2H\x1b[@")
    assert row0(s15) == "A BC      ", f"got {row0(s15)!r}"

    # ICH drops characters shifted past the right margin; count is clamped
    s16 = AnsiScreen(3, 5)
    s16.process("ABCDE\x1b[1;2H\x1b[2@")
    assert row0(s16) == "A  BC", f"got {row0(s16)!r}"
    s16.process("\x1b[99@")
    assert row0(s16) == "A    ", f"got {row0(s16)!r}"

    # ICH shifts attributes with characters; inserted blanks are normal
    s17 = AnsiScreen(3, 10)
    s17.process("A\x1b[7mB\x1b[1;1H\x1b[1@")
    assert s17.attrs[0][:3] == [0, 0, AnsiScreen.ATTR_REVERSE], f"got {s17.attrs[0][:3]}"

    # DCH: delete at cursor, shift the rest left, blanks at the right
    s18 = AnsiScreen(3, 10)
    s18.process("ABCDEF\x1b[1;2H\x1b[2P")
    assert row0(s18) == "ADEF      ", f"got {row0(s18)!r}"
    assert (s18.cursor_row, s18.cursor_col) == (0, 1)

    # DCH with no count deletes one; count is clamped to the row
    s19 = AnsiScreen(3, 10)
    s19.process("ABCDEF\x1b[1;1H\x1b[P")
    assert row0(s19) == "BCDEF     ", f"got {row0(s19)!r}"
    s19.process("\x1b[1;3H\x1b[99P")
    assert row0(s19) == "BC        ", f"got {row0(s19)!r}"

    # DCH shifts attributes with characters; blanks at the right are normal
    s20 = AnsiScreen(3, 5)
    s20.process("A\x1b[7mBCDE\x1b[0m\x1b[1;1H\x1b[1P")
    assert s20.attrs[0] == [AnsiScreen.ATTR_REVERSE] * 4 + [0], f"got {s20.attrs[0]}"

    # ICH and DCH cancel a pending deferred wrap
    s21 = AnsiScreen(3, 5, deferred_wrap=True)
    s21.process("ABCDE\x1b[1@X")
    assert row0(s21) == "ABCDX", f"got {row0(s21)!r}"
    s22 = AnsiScreen(3, 5, deferred_wrap=True)
    s22.process("ABCDE\x1b[1PX")
    assert row0(s22) == "ABCDX", f"got {row0(s22)!r}"

    # A shifted row counts as touched, but its cells are not counted as
    # written in frame tracking
    s23 = AnsiScreen(3, 10)
    s23.process("ABCDEF\x1b[?25h")
    s23.process("\x1b[1;2H\x1b[2@\x1b[1;4H\x1b[1P\x1b[?25h")
    assert s23.was_content_redrawn(1) == True
    assert s23.content_rows_touched(1) == {0}
    assert s23.get_min_col(1, 0) == -1

    # A 0 row or column in a cursor move means 1, as on real terminals
    s24 = AnsiScreen(3, 10)
    s24.process("\x1b[0;5HAB\x1b[2;0HCD\x1b[0;0HE\x1b[?25h")
    assert rows_of(s24) == ["E   AB", "CD", ""], rows_of(s24)

    # Backspace moves one column left, not past column 0, and from a
    # pending deferred wrap moves left of the last column
    s25 = AnsiScreen(3, 5)
    s25.process("AB\bX")
    assert row0(s25) == "AX   ", f"got {row0(s25)!r}"
    s25.process("\x1b[1;1H\bY")
    assert row0(s25) == "YX   ", f"got {row0(s25)!r}"
    s26 = AnsiScreen(3, 5, deferred_wrap=True)
    s26.process("ABCDE\bX")
    assert row0(s26) == "ABCXE", f"got {row0(s26)!r}"

    # IL inserts blank lines at the cursor row down to the bottom margin and
    # DL deletes lines there; both move the cursor to column 0 and are
    # ignored outside the margins
    def lettered(rows):
        s = AnsiScreen(rows, 5)
        for r in range(rows):
            s.process(f"\x1b[{r + 1};1H" + chr(ord('A') + r) * 3)
        return s
    s27 = lettered(5)
    s27.process("\x1b[1;4r\x1b[2;3H\x1b[2L\x1b[?25h")
    assert rows_of(s27) == ["AAA", "", "", "BBB", "EEE"], rows_of(s27)
    assert s27.get_cursor() == (1, 0)
    s28 = lettered(5)
    s28.process("\x1b[1;4r\x1b[2;3H\x1b[M\x1b[?25h")
    assert rows_of(s28) == ["AAA", "CCC", "DDD", "", "EEE"], rows_of(s28)
    assert s28.get_cursor() == (1, 0)
    s29 = lettered(5)
    s29.process("\x1b[2;4r\x1b[1;2H\x1b[L\x1b[5;1H\x1b[9M\x1b[?25h")
    assert rows_of(s29) == ["AAA", "BBB", "CCC", "DDD", "EEE"], rows_of(s29)
    assert s29.was_scrolled(0) == False

    # Scroll tracking counts content rows only: the status row (the last
    # row) is never among the rows a scroll moved
    s30 = lettered(4)
    s30.process("\x1b[?25h\x1b[S\x1b[?25h\x1b[2;4r\x1b[4;1H\x1b[M\x1b[?25h")
    assert s30.was_scrolled(1) and s30.scroll_rows_touched(1) == {0, 1, 2}
    assert s30.scroll_rows_touched(2) == set()
    s30.process("\x1b[2;4r\x1b[2;1H\x1b[2L\x1b[?25h")
    assert s30.scroll_rows_touched(3) == {1, 2}

    print("All self-tests passed.")
