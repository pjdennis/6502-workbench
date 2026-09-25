"""
ANSI virtual terminal emulator for testing editor screen output.

Processes ANSI escape sequences into a virtual screen buffer with cursor
tracking. Only handles sequences the editor actually emits.

Supported sequences:
    ESC[2J          - Clear screen
    ESC[{r};{c}H    - Cursor move (1-based)
    ESC[H           - Cursor home (1,1)
    ESC[K           - Clear to end of line
    ESC[7m / ESC[0m - Reverse/normal video (tracked per-cell in attrs buffer)
    ESC[?25l        - Cursor hide
    ESC[?25h        - Cursor show (triggers frame snapshot)
    ESC[{t};{b}r    - Set scroll region (1-based top;bottom)
    ESC[r           - Reset scroll region to full screen
    ESC[{n}S        - Scroll up n lines (content moves up, blanks at bottom)
    ESC[{n}T        - Scroll down n lines (content moves down, blanks at top)
    ESC[{n}@        - Insert n blank characters at cursor (ICH)
    ESC[{n}P        - Delete n characters at cursor (DCH)

Deferred auto-wrap (opt-in via deferred_wrap=True):
    Matches real VT100/xterm behavior where writing to the last column
    sets a pending-wrap flag instead of immediately advancing the cursor.
    ESC[K in this state clears from the last column, erasing the character.
    Cursor movement commands (ESC[r;cH) cancel the pending wrap.
"""


class AnsiScreen:
    ATTR_REVERSE = 0x01

    def __init__(self, rows, cols, deferred_wrap=False):
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
        self.scroll_touched = set()   # Set of row indices affected by scroll operations

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
            self.cursor_row += 1
            if self.cursor_row >= self.rows:
                self.cursor_row = self.rows - 1
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
        """Set scroll region (0-based, inclusive)."""
        self.scroll_top = max(0, min(top, self.rows - 1))
        self.scroll_bottom = max(0, min(bottom, self.rows - 1))

    def _reset_scroll_region(self):
        """Reset scroll region to full screen."""
        self.scroll_top = 0
        self.scroll_bottom = self.rows - 1

    def _scroll_region_up(self, n):
        """Scroll region up: remove n rows from top, insert blanks at bottom.
        Does NOT mark rows as content_touched since the terminal hardware
        performs the scroll - only explicit character writes count."""
        self.frame_scrolled = True
        self.scroll_touched.update(range(self.scroll_top, self.scroll_bottom + 1))
        for _ in range(n):
            if self.scroll_top > self.scroll_bottom:
                break
            del self.buffer[self.scroll_top]
            del self.attrs[self.scroll_top]
            self.buffer.insert(self.scroll_bottom, [' '] * self.cols)
            self.attrs.insert(self.scroll_bottom, [0] * self.cols)

    def _scroll_region_down(self, n):
        """Scroll region down: remove n rows from bottom, insert blanks at top.
        Does NOT mark rows as content_touched since the terminal hardware
        performs the scroll - only explicit character writes count."""
        self.frame_scrolled = True
        self.scroll_touched.update(range(self.scroll_top, self.scroll_bottom + 1))
        for _ in range(n):
            if self.scroll_top > self.scroll_bottom:
                break
            del self.buffer[self.scroll_bottom]
            del self.attrs[self.scroll_bottom]
            self.buffer.insert(self.scroll_top, [' '] * self.cols)
            self.attrs.insert(self.scroll_top, [0] * self.cols)

    def _shift_chars(self, n, insert):
        """ICH/DCH: insert or delete n cells at the cursor within its row.
        Cells pushed past the right margin are lost; freed cells are blank
        with normal attributes. The cursor does not move. Like scrolling,
        this is not counted as a content write in frame tracking."""
        self._pending_wrap = False
        row, col = self.cursor_row, self.cursor_col
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            return
        n = min(max(n, 1), self.cols - col)
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
            if params == '' or params == ';':
                self._move_cursor(0, 0)
            else:
                parts = params.split(';')
                row = int(parts[0]) - 1 if parts[0] else 0
                col = int(parts[1]) - 1 if len(parts) > 1 and parts[1] else 0
                self._move_cursor(row, col)
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
            # Set/reset scroll region
            if params == '' or params == ';':
                self._reset_scroll_region()
            else:
                parts = params.split(';')
                top = int(parts[0]) - 1 if parts[0] else 0
                bottom = int(parts[1]) - 1 if len(parts) > 1 and parts[1] else self.rows - 1
                self._set_scroll_region(top, bottom)
        elif final == 'S':
            # Scroll up
            n = int(params) if params else 1
            self._scroll_region_up(n)
        elif final == 'T':
            # Scroll down
            n = int(params) if params else 1
            self._scroll_region_down(n)
        elif final == '@':
            # ICH - Insert blank characters
            self._shift_chars(int(params) if params else 1, insert=True)
        elif final == 'P':
            # DCH - Delete characters
            self._shift_chars(int(params) if params else 1, insert=False)

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
        """Set of row indices affected by scroll operations during this frame."""
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
    s13.process("\x1b[2;2r")  # set narrow region
    assert s13.scroll_top == 1
    assert s13.scroll_bottom == 1
    s13.process("\x1b[r")     # reset
    assert s13.scroll_top == 0
    assert s13.scroll_bottom == 2

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

    # Shifted cells are not counted as written in frame tracking
    s23 = AnsiScreen(3, 10)
    s23.process("ABCDEF\x1b[?25h")
    s23.process("\x1b[1;2H\x1b[2@\x1b[1;4H\x1b[1P\x1b[?25h")
    assert s23.was_content_redrawn(1) == False
    assert s23.get_min_col(1, 0) == -1

    print("All self-tests passed.")
