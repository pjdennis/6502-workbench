#!/usr/bin/env python3
"""The editor on Michael, in the emulator's Michael machine: the
define:direct_io define:michael build with the Michael services
(firmware/programs/michael/michael_editor_services.s), typed at on the PS/2
keyboard and shown on the 20x4 LCD.

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
from michael_image import EMULATOR, LOAD, ROOT

sys.path.insert(0, str(ROOT / "tools" / "upload"))
from upload_frame import build_frame

ROWS, COLS = 4, 20
STACK_FLOOR = 0x0154         # the buffers below the stack end here (editor.asm)
CYCLES_PER_KEY = 60000       # 30 ms at 2 MHz: more than the 20 ms between keys


class MichaelEditorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)
        cls.image_file = michael_image.build(tmp / "editor_michael.image")
        cls.console_editor = tmp / "editor.out"
        michael_image.assemble_editor(cls.console_editor)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def image(self):
        return self.image_file

    def run_michael(self, keys):
        """Type keys at the editor on Michael; the LCD's rows once they are handled."""
        keys_file = Path(self.tmp.name) / "keys.txt"
        keys_file.write_bytes(keys)
        cycles = 2000000 + CYCLES_PER_KEY * len(keys)
        report = subprocess.run([EMULATOR, self.image(), "--machine", "michael", "--load", "%04x" % LOAD,
                                 "--keys", keys_file, "--cycle-cap", str(cycles)],
                                check=True, capture_output=True, text=True).stderr.splitlines()
        self.assertIn("michael: bus: lcd-undriven=0 portb-contention=0", report)
        stack = next(line for line in report if line.startswith("michael: stack: lowest $"))
        self.assertGreaterEqual(int(stack[-4:], 16), STACK_FLOOR, stack)
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
        subprocess.run([EMULATOR, self.console_editor, "--no-dump", "--load", "%04x" % LOAD,
                        "--rows", str(ROWS), "--cols", str(COLS), "--input", keys_file,
                        "--output", output],
                       capture_output=True, timeout=10, cwd=work)
        screen = AnsiScreen(ROWS, COLS, clip_bottom=True)
        screen.process(output.read_bytes().decode("latin-1"))
        return [screen.get_row_text(row) for row in range(ROWS)]

    def assert_same_as_console(self, keys):
        self.assertEqual(self.run_michael(keys), self.run_console(keys))

    def test_environment_matches(self):
        """editor/michael_environment.asm has 17/environment.asm's vectors."""
        definition = re.compile(r"^([A-Za-z_]+) *= *(ENV_BASE \+ \$[0-9A-F]+|\$[0-9A-F]+)", re.M)
        asm2 = Path(michael_image.__file__).parents[1]
        environment = dict(definition.findall((asm2 / "17" / "environment.asm").read_text()))
        del environment["ENV_BASE"]
        michael = dict(definition.findall((asm2 / "editor" / "michael_environment.asm").read_text()))
        self.assertEqual({k: v for k, v in michael.items() if k != "ENV_BASE"}, environment)

    def upload_through_second_stage(self, frame_bytes):
        """Run the second-stage loader (as the ROM's loader would, from
        PROGRAM_LOAD_ADDRESS) with frame_bytes on the serial line; the report."""
        tmp = Path(self.tmp.name)
        loader = tmp / "second_stage_loader.bin"
        subprocess.run([ROOT / "firmware" / "vasm", "-quiet", "-wdc02", "-wfail", "-Fbin", "-dotdir",
                        "-ignore-mult-inc", "-esc", "-o", loader,
                        ROOT / "firmware" / "programs" / "michael" / "michael_second_stage_loader.s"],
                       check=True, capture_output=True, cwd=ROOT)
        frame = tmp / "image.frame"
        frame.write_bytes(frame_bytes)
        report = subprocess.run([EMULATOR, loader, "--machine", "michael", "--load", "0900",
                                 "--serial-input", frame, "--cycle-cap", "20000000"],
                                check=True, capture_output=True, text=True).stderr.splitlines()
        self.assertIn("michael: bus: lcd-undriven=0 portb-contention=0", report)
        return report

    def lcd_rows(self, report):
        lcd = report.index("michael: lcd:")
        return [line.strip()[1:-1].rstrip() for line in report[lcd + 1:lcd + 1 + ROWS]]

    def test_uploads_through_the_second_stage_loader(self):
        """On the board the image goes up in two uploads: the second-stage
        loader through the ROM's loader, then the image through it, straight
        to $0400."""
        report = self.upload_through_second_stage(build_frame(self.image().read_bytes()))
        self.assertEqual(self.lcd_rows(report), ["", "~", "~", "[No Name] - NORMAL -"])

    def test_second_stage_loader_stops_on_a_bad_checksum(self):
        frame = bytearray(build_frame(self.image().read_bytes()))
        frame[100] ^= 1
        report = self.upload_through_second_stage(bytes(frame))
        self.assertTrue(report[0].endswith("(STP)"), report[0])
        self.assertEqual(self.lcd_rows(report)[0], "Waiting for the")

    def test_second_stage_loader_stops_on_a_program_too_long(self):
        report = self.upload_through_second_stage(build_frame(bytes(0x3B00)))  # to $3F00
        self.assertTrue(report[0].endswith("(STP)"), report[0])

    def test_live(self):
        """--live draws the LCD in the terminal and types the terminal's keys;
        Ctrl-] quits and restores the terminal."""
        master, slave = pty.openpty()
        proc = subprocess.Popen([EMULATOR, self.image(), "--machine", "michael",
                                 "--load", "%04x" % LOAD, "--live"],
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
