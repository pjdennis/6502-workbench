"""Michael's graphic display, as mounted on the FPGA interface (hardware/michael/fpga/spi-display), shows the
picture upside down unless the panel scans in reverse. graphics_display.inc's INIT_COMMANDS therefore sets
Display Function Control's GS (gate scan) and SS (source scan) bits. Rotating the panel's scan, rather than
the memory access order (MADCTL), keeps hardware scrolling (VSCRSADD) going the right way.

Run from the repo root:  python3 -m unittest discover -s tools/tests -v
Requires vasm6502_oldstyle on PATH (tests skip otherwise).
"""
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
PROGRAM = os.path.join(ROOT, 'firmware', 'programs', 'michael', 'michael_graphic_display_test.s')

DFUNCTR = 0xB6
REV, GS, SS = 0x80, 0x40, 0x20


def assemble(program):
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, 'a.bin')
        result = subprocess.run([os.path.join(ROOT, 'firmware', 'vasm'), '-quiet', '-wdc02', '-wfail', '-Fbin',
                                 '-dotdir', '-ignore-mult-inc', '-esc', '-o', out, program],
                                capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        with open(out, 'rb') as f:
            return f.read()


@unittest.skipUnless(shutil.which('vasm6502_oldstyle'), 'vasm6502_oldstyle not on PATH')
class DisplayOrientationTest(unittest.TestCase):
    def test_init_commands_reverse_the_panel_scan(self):
        image = assemble(PROGRAM)
        # The INIT_COMMANDS record: command, parameter count, then 3 parameters
        records = [image[i:i + 5] for i in range(len(image) - 4)
                   if image[i] == DFUNCTR and image[i + 1] == 3 and image[i + 2] == 0x08 and image[i + 4] == 0x27]
        self.assertEqual(len(records), 1, 'expected one Display Function Control record in INIT_COMMANDS')
        scan = records[0][3]
        self.assertEqual(scan & (GS | SS), GS | SS, f'GS and SS should both be set: got ${scan:02X}')
        self.assertEqual(scan & ~(GS | SS), REV | 0x02, f'the other bits are unchanged: got ${scan:02X}')


if __name__ == '__main__':
    unittest.main()
