#!/usr/bin/env python3
"""The editor on Michael, in the emulator's Michael machine: the
define:direct_io define:michael build, uploaded through the Michael ROM's
loader (firmware/boards/michael/michael_rom.s) over the serial line and
running on its services, typed at on the PS/2 keyboard and shown on the 20x4
LCD.

Each test types keys and checks the LCD once they have been handled, that
the bus stayed clean, and that the stack stayed clear of the buffers below
it. The differential tests compare the LCD with the console build's ANSI
output at 20x4 (ansi_screen.AnsiScreen, its bottom row clipped like the
LCD's).

Run from toolchain/asm2 (verify.sh does); needs vasm6502_oldstyle on PATH
and the emulator and asm17 built.
"""
import os
import pty
import re
import select
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[1]))
from ansi_screen import AnsiScreen
import michael_image
from michael_image import EMULATOR

CONSOLE_LOAD = 0x0400

ROWS, COLS = 4, 20
STACK_FLOOR = 0x0154         # the buffers below the stack end here (editor.asm)
CYCLES_PER_KEY = 60000       # 30 ms at 2 MHz: more than the 20 ms between keys
UPLOAD_AND_START_CYCLES = 6000000  # 3 s: the upload (~1.2 s here, the loader drawing its progress
                                   # as it goes; ~2 s on the board's 57600 bps line), the keyboard's
                                   # start-up and its 200 ms before the first key


class MichaelEditorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)
        cls.editor = michael_image.build(tmp / "editor_michael.bin")
        cls.rom = michael_image.build_rom(tmp / "michael_rom.bin")
        cls.upload = michael_image.write_upload(cls.editor, tmp / "editor_michael.upload")
        cls.console_editor = tmp / "editor.out"
        michael_image.assemble_editor(cls.console_editor)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def michael(self, keys, *options):
        """Boot the ROM, upload the editor and type keys; the emulator's report."""
        keys_file = Path(self.tmp.name) / "keys.txt"
        keys_file.write_bytes(keys)
        cycles = UPLOAD_AND_START_CYCLES + CYCLES_PER_KEY * len(keys)
        report = subprocess.run([EMULATOR, self.rom, "--machine", "michael", "--serial-input", self.upload,
                                 "--keys", keys_file, "--cycle-cap", str(cycles), *options],
                                check=True, capture_output=True, text=True).stderr.splitlines()
        self.assertIn("michael: bus: lcd-undriven=0 portb-contention=0", report)
        stack = next(line for line in report if line.startswith("michael: stack: lowest $"))
        self.assertGreaterEqual(int(stack[-4:], 16), STACK_FLOOR, stack)
        return report

    def run_michael(self, keys):
        """Type keys at the editor on Michael; the LCD's rows once they are handled."""
        return self.lcd_rows(self.michael(keys))

    def lcd_rows(self, report):
        lcd = report.index("michael: lcd:")
        return [line.strip()[1:-1].rstrip() for line in report[lcd + 1:lcd + 1 + ROWS]]

    def run_console(self, keys):
        """The console build's screen at 20x4 after the same keys. It runs in
        an empty directory, so it too edits a new "[No Name]", and a $00 (no
        key) follows the keys: the console build exits once a key read hits
        the end of the input, before handling that key."""
        work = Path(self.tmp.name) / "console"
        work.mkdir(exist_ok=True)
        keys_file = work / "keys.bin"
        keys_file.write_bytes(keys + b"\x00")
        output = work / "output.bin"
        subprocess.run([EMULATOR, self.console_editor, "--no-dump", "--load", "%04x" % CONSOLE_LOAD,
                        "--rows", str(ROWS), "--cols", str(COLS), "--input", keys_file,
                        "--output", output],
                       capture_output=True, timeout=10, cwd=work)
        screen = AnsiScreen(ROWS, COLS, clip_bottom=True)
        screen.process(output.read_bytes().decode("latin-1"))
        return [screen.get_row_text(row) for row in range(ROWS)]

    def assert_same_as_console(self, keys):
        self.assertEqual(self.run_michael(keys), self.run_console(keys))

    def test_code_ends_below_the_text_buffers_end(self):
        """The text buffer starts on the page after the code and ends at TEXT_END (memory_map.asm)."""
        end = michael_image.LOAD + len(self.editor.read_bytes())
        self.assertLessEqual((end + 0xff) & ~0xff, michael_image.memory_map_address("TEXT_END") - 0x100)

    def test_quitting_goes_back_to_the_loader(self):
        self.assertEqual(self.run_michael(b":q\r")[:2], ["Michael ROM 4", "Ready"])

    def test_live(self):
        """--live draws the LCD in the terminal and types the terminal's keys;
        Ctrl-] quits and restores the terminal."""
        master, slave = pty.openpty()
        proc = subprocess.Popen([EMULATOR, self.rom, "--machine", "michael",
                                 "--serial-input", self.upload, "--live"],
                                stdin=slave, stdout=slave, stderr=subprocess.DEVNULL)
        os.close(slave)
        seen = b""

        def read_until(text, timeout=10):
            """Read until text shows, ignoring video attributes (the cursor)."""
            nonlocal seen
            deadline = time.monotonic() + timeout
            shown = lambda: text in re.sub(rb"\x1b\[[0-9]*m", b"", seen)
            while not shown() and time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        seen += os.read(master, 65536)
                    except OSError:
                        break
            return shown()

        try:
            self.assertTrue(read_until(b"[No Name] - NORMAL -"), seen[-500:])
            os.write(master, b"ihello")
            time.sleep(0.1)
            os.write(master, b"\x1b")
            self.assertTrue(read_until(b"|hello "), seen[-500:])
            os.write(master, b"\x1d")
            self.assertEqual(proc.wait(timeout=10), 0)
            read_until(b"\x1b[?1049l", timeout=1)
            self.assertIn(b"\x1b[?1049l", seen)
        finally:
            if proc.poll() is None:
                proc.kill()
            os.close(master)

    def test_starts_with_an_empty_unnamed_file(self):
        self.assertEqual(self.run_michael(b""), ["", "~", "~", "[No Name] - NORMAL -"])

    def test_typed_text_shows(self):
        self.assertEqual(self.run_michael(b"ihello\x1b")[0], "hello")

    def test_write_fails(self):
        self.assertEqual(self.run_michael(b"ihi\x1b:w\r")[ROWS - 1], ":Can't open file for")

    def test_same_as_console_typing_past_the_screen(self):
        self.assert_same_as_console(b"ione\rtwo\rthree\rfour\rfive\x1b")

    def test_same_as_console_moving_and_editing(self):
        self.assert_same_as_console(
            b"ialpha beta gamma\rdelta\repsilon\x1bggwdwjA!\x1b\x1b[A\x1b[Dx")

    def test_same_as_console_long_line(self):
        self.assert_same_as_console(b"i" + b"0123456789" * 5 + b"\x1b0")


if __name__ == "__main__":
    unittest.main()
