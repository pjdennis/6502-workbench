"""An ILI9341 panel, as far as the text mode uses it: the bytes it receives over SPI (each with its DC level)
become pixels, through CASET and PASET (the window) and RAMWR (pixels, two bytes each, columns first, then
pages, within the window). MADCTL is recorded; the orientation itself isn't modelled: column and page are the
panel's addresses as Michael's driver uses them (gd_prepare_vertical's MY, MV), so text row r is columns 16r
to 16r + 15 and text column c is pages 12c to 12c + 11.

What the glass shows (shown_cell) follows the hardware scroll, VSCRDEF (top fixed area, scroll area, bottom
fixed area, in lines) and VSCRSADD (the scroll area's first line). Those count the panel's frame memory lines,
which run the other way from columns: with MADCTL's MY, frame line 0 is column 319. And with the gate scan
reversed (GD_PANEL_SCAN), frame line 0 is shown at the bottom of the glass. So the top fixed area is shown at
the bottom, the scroll area above it, starting (at its bottom) with VSCRSADD's line, and the bottom fixed area
at the top. Michael's graphic driver scrolls the whole screen this way (gd_scroll_up: VSCRSADD = (20 - rows
scrolled) * 16), which test_ili9341.py checks.

The glass, as frames shows it, is scanned a line at a time, top to bottom, over each frame; the scroll's
registers take effect at the start of a frame (inferred: the board shows a new VSCRSADD a frame late).
"""
CASET, PASET, RAMWR, VSCRDEF, MADCTL, VSCRSADD = 0x2A, 0x2B, 0x2C, 0x33, 0x36, 0x37
COLUMNS, PAGES = 320, 240


class Panel:
    def __init__(self):
        self.pixels = [[None] * COLUMNS for _ in range(PAGES)]   # None: never written
        self.command, self.params = None, []
        self.registers = {}
        self.window = (0, COLUMNS - 1, 0, PAGES - 1)
        self.column = self.page = 0
        self.high = None

    def receive(self, dc, byte):
        if not dc:
            self.command, self.params, self.high = byte, [], None
            if byte == RAMWR:
                self.column, self.page = self.window[0], self.window[2]
            return
        self.params.append(byte)
        if self.command in (CASET, PASET) and len(self.params) == 4:
            start, end = self.params[0] << 8 | self.params[1], self.params[2] << 8 | self.params[3]
            c0, c1, p0, p1 = self.window
            self.window = (start, end, p0, p1) if self.command == CASET else (c0, c1, start, end)
        elif self.command == RAMWR:
            if self.high is None:
                self.high = byte
            else:
                self.pixels[self.page][self.column] = self.high << 8 | byte
                self.high = None
                c0, c1, p0, p1 = self.window
                self.column += 1
                if self.column > c1:
                    self.column, self.page = c0, self.page + 1 if self.page < p1 else p0
        else:
            self.registers[self.command] = list(self.params)

    def _words(self, value_pairs):
        return [value_pairs[i] << 8 | value_pairs[i + 1] for i in range(0, len(value_pairs), 2)]

    def shown_column(self, line, registers=None):
        """The memory column shown on the glass's line (0 at the top), through the hardware scroll (as the
        registers have it, by default the panel's)."""
        registers = self.registers if registers is None else registers
        tfa, vsa, bfa = self._words(registers.get(VSCRDEF, [0, 0, 1, 0x40, 0, 0]))
        ssa = self._words(registers.get(VSCRSADD, [0, 0]))[0]
        k = COLUMNS - 1 - line                          # from the bottom of the glass
        frame = k if k < tfa or k >= tfa + vsa else tfa + (ssa - tfa + k - tfa) % vsa
        return COLUMNS - 1 - frame

    def cell(self, row, col, shown=False):
        """The text cell's 12 columns of 16 pixels, each a 16-bit word (top pixel in bit 0) of lit pixels;
        None if any of its pixels is neither white nor black. In memory, or as shown on the glass."""
        words = []
        for x in range(12):
            word = 0
            for y in range(16):
                column = self.shown_column(row * 16 + y) if shown else row * 16 + y
                p = self.pixels[col * 12 + x][column]
                if p not in (0x0000, 0xFFFF):
                    return None
                word |= (p == 0xFFFF) << y
            words.append(word)
        return words


def frames(events, period, phase=0, lines=COLUMNS, pages=PAGES):
    """The glass, frame by frame, as the panel scans it, for bytes received at times (events: (time, dc, byte),
    in order): each frame starts at phase + k * period with the scroll's registers as they are then, and shows
    line l as the frame memory holds it l / 320 of the way through. Yields (start, glass), glass[line][page]
    being the pixel (None: never written) for the first lines and pages, until the frame after the last byte."""
    panel, i = Panel(), 0

    def until(t):
        nonlocal i
        while i < len(events) and events[i][0] < t:
            panel.receive(*events[i][1:])
            i += 1

    start = phase
    while True:
        until(start)
        settled = i == len(events)
        registers = {k: v for k, v in panel.registers.items() if k in (VSCRDEF, VSCRSADD)}
        glass = []
        for line in range(lines):
            until(start + line * period // COLUMNS)
            column = panel.shown_column(line, registers)
            glass.append([panel.pixels[page][column] for page in range(pages)])
        yield start, glass
        if settled:
            return
        start += period
