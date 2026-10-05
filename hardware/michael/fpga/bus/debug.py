#!/usr/bin/env python3
"""The Michael FPGA bus's debug port: the PC makes the same transactions as Michael, over the Cmod's USB
serial port (rtl/debug_port.v has the line format). With the bus design loaded:

  debug.py id         the ID reply: "MB", the protocol version and the capabilities
  debug.py status     the status byte
  debug.py pattern    resets and initialises the display as Michael's driver does (graphics_display.inc),
                      then draws coloured squares: the FPGA and the display, checked without Michael
  debug.py text       initialises the display, then shows text mode: a screen of text, reverse video, a
                      scroll region, and the cursor blinking where the last line ends
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "display-probe"))

LINE_BYTES = 32   # data bytes per line
TIMEOUT = 2.0     # seconds to wait for an answer


class NoAnswer(Exception):
    pass


class DebugPort:
    def __init__(self, ser):
        self.ser = ser

    def _lines(self, letter, values):
        values = list(values)
        for i in range(0, max(len(values), 1), LINE_BYTES):
            self.ser.write((letter + "".join(f"{v:02X}" for v in values[i:i + LINE_BYTES]) + "\n").encode())

    def command(self, *values):
        self._lines("C", values)

    def data(self, *values):
        if values:
            self._lines("D", values)

    def _answer(self, letter):
        """The next line starting with letter; other lines (Michael's SERIAL_SEND text) are skipped."""
        deadline = time.monotonic() + TIMEOUT
        while time.monotonic() < deadline:
            try:
                line = self.ser.readline(deadline).decode(errors="replace").strip()
            except TimeoutError:   # the kit's serial port, at the deadline
                break
            if line.startswith(letter):
                return line[1:]
            if not line:
                break
        raise NoAnswer(f"no '{letter}' answer from the debug port: is the bus design loaded?")

    def read(self, n=1):
        """n bytes of the reply queue."""
        self.ser.write(f"R{n:02X}\n".encode())
        text = self._answer("r")
        return [int(text[i:i + 2], 16) for i in range(0, 2 * n, 2)]

    def status(self):
        self.ser.write(b"S\n")
        return int(self._answer("s"), 16)

    def id(self):
        """("MB", version, capabilities): "MB" (Michael Bus) is the design's signature."""
        self.command(0x01)
        m, b, version, capabilities = self.read(4)
        return chr(m) + chr(b), version, capabilities

    # The display (the raw display commands, $1x)
    def disp_reset(self, level):
        self.command(0x10)
        self.data(level)

    def disp_command(self, cmd, *params):
        self.command(0x11)
        self.data(cmd, *params)

    def backlight(self, level):
        self.command(0x13)
        self.data(level)

    # Text mode, the long-form device $80: each operation is the device, then the operation and its
    # arguments as data. Rows and columns are 0-based
    TEXT = 0x80

    def _text(self, op, *arguments):
        self.command(self.TEXT)
        self.data(op, *arguments)

    def text_on(self): self._text(0x00)
    def text_off(self): self._text(0x01)
    def goto(self, row, col): self._text(0x02, row, col)
    def put(self, text): self._text(0x03, *text.encode('latin-1'))
    def clear(self): self._text(0x04)
    def clear_eol(self): self._text(0x05)
    def insert(self, n): self._text(0x06, n)
    def delete(self, n): self._text(0x07, n)
    def region(self, top, bottom): self._text(0x08, top, bottom)
    def region_reset(self): self._text(0x09)
    def scroll_up(self, n): self._text(0x0A, n)
    def scroll_down(self, n): self._text(0x0B, n)
    def insert_lines(self, n): self._text(0x0C, n)
    def delete_lines(self, n): self._text(0x0D, n)
    def cursor(self, on): self._text(0x0E, int(on))
    def video(self, reverse): self._text(0x0F, int(reverse))

    def geometry(self):
        """(rows, columns) of text mode's grid."""
        self._text(0x10)
        rows, cols = self.read(2)
        return rows, cols


def initialise_display(port):
    """As gd_prepare_vertical does: reset, INIT_COMMANDS, landscape MADCTL."""
    import probe
    names = probe.driver_constants()
    port.disp_reset(0)
    time.sleep(0.01)
    port.disp_reset(1)
    time.sleep(0.12)
    for cmd, params, delay in probe.michael_init_commands():
        port.disp_command(cmd, *params)
        if delay:
            time.sleep(0.15)
    port.disp_command(names["ILI9341_MADCTL"],
                      names["ILI9341_MADCTL_MY"] | names["ILI9341_MADCTL_MV"] | names["ILI9341_MADCTL_BGR"])


def fill(port, x, y, width, height, colour):
    """A rectangle of an RGB565 colour (landscape: x 0-319, y 0-239)."""
    port.disp_command(0x2A, x >> 8, x & 0xFF, (x + width - 1) >> 8, (x + width - 1) & 0xFF)
    port.disp_command(0x2B, y >> 8, y & 0xFF, (y + height - 1) >> 8, (y + height - 1) & 0xFF)
    port.disp_command(0x2C)
    port.data(*[colour >> 8, colour & 0xFF] * (width * height))


def text_demo(port):
    """A screen of text: a title in reverse video, a sentence that wraps over rows 2-4, a scroll region (rows
    6-18) scrolled up a line (so it starts at "row 7", and row 18 is blank), and the cursor blinking after
    "Ready" on the bottom row."""
    port.text_on()
    port.video(True)
    port.put(" MICHAEL TEXT MODE  ")
    port.video(False)
    port.goto(2, 0)
    port.put("The quick brown fox jumps over the lazy dog. 0123456789")
    port.region(6, 18)
    for row in range(6, 19):
        port.goto(row, 0)
        port.put(f"row {row}")
    port.scroll_up(1)
    port.region_reset()
    port.goto(19, 0)
    port.put("Ready")
    port.cursor(True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["id", "status", "pattern", "text"])
    ap.add_argument("--fpga-port", help="the Cmod's serial port (default: auto-detect)")
    args = ap.parse_args(argv)
    try:
        run(args)
    except NoAnswer as e:
        sys.exit(str(e))


def run(args):
    """The action, on the Cmod's serial port."""
    import board
    uart_check = board.serial_module()
    with uart_check.Serial(args.fpga_port or uart_check.find_port()) as ser:
        ser.flush_input()
        port = DebugPort(ser)
        if args.action == "id":
            name, version, capabilities = port.id()
            print(f"{name}, protocol version {version}, capabilities ${capabilities:02X}")
        elif args.action == "status":
            print(f"status ${port.status():02X}")
        elif args.action == "pattern":
            initialise_display(port)
            for i, colour in enumerate((0xF800, 0x07E0, 0x001F, 0xFFFF)):   # red, green, blue, white
                fill(port, 16 + i * 72, 88, 64, 64, colour)
            print(f"Drew four squares (red, green, blue, white); status ${port.status():02X}")
        else:
            initialise_display(port)
            text_demo(port)
            rows, cols = port.geometry()
            print(f"Text mode: {rows} rows of {cols}; status ${port.status():02X}")


if __name__ == "__main__":
    main()
