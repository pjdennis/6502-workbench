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
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ansi_screen import AnsiScreen

ASM2 = Path(__file__).resolve().parents[2]
ROOT = ASM2.parents[1]
EMULATOR = ROOT / "emulator" / "emulator.out"
ASSEMBLER = ASM2 / "17" / "out" / "asm.out"
SERVICES = ROOT / "firmware" / "programs" / "michael" / "michael_editor_services.s"
LAYOUT = ROOT / "firmware" / "boards" / "michael" / "michael_editor_layout.inc"
LOAD = 0x0400
ROWS, COLS = 4, 20
STACK_FLOOR = 0x0154         # the buffers below the stack end here (editor.asm)
CYCLES_PER_KEY = 60000       # 30 ms at 2 MHz: more than the 20 ms between keys


def layout_address(name):
    return int(re.search(r'^%s\s*=\s*\$([0-9a-fA-F]+)' % name, LAYOUT.read_text(), re.M).group(1), 16)


class MichaelEditorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)
        cls.editor = cls.assemble_editor(tmp / "editor_michael.out", "define:direct_io", "define:michael")
        cls.console_editor = tmp / "editor.out"
        cls.assemble_editor(cls.console_editor)
        services_bin = tmp / "services.bin"
        subprocess.run([ROOT / "firmware" / "vasm", "-quiet", "-wdc02", "-wfail", "-Fbin", "-dotdir",
                        "-ignore-mult-inc", "-esc", "-o", services_bin, SERVICES],
                       check=True, capture_output=True, cwd=ROOT)
        cls.services = services_bin.read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def assemble_editor(cls, out, *defines):
        subprocess.run([EMULATOR, ASSEMBLER, "--no-dump", "editor/editor.asm", out, *defines],
                       check=True, capture_output=True, cwd=ASM2)
        return out.read_bytes()

    def image(self):
        """The editor and the services, as one RAM image from LOAD."""
        services_at = layout_address("MICHAEL_ENV_BASE") + 6
        editor = self.editor[:-2]        # the last 2 bytes are the entry point
        self.assertLessEqual(LOAD + len(editor), services_at)
        path = Path(self.tmp.name) / "image.bin"
        path.write_bytes(editor + bytes(services_at - LOAD - len(editor)) + self.services)
        return path

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
