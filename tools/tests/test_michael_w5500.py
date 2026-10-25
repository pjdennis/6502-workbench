"""The W5500 Ethernet controller behind the GAL20RA10 SPI interface, on the emulator's Michael with the FPGA board
unplugged (--add gal-spi,w5500): firmware/programs/michael/michael_w5500_version.s reads VERSIONR ($04) in
rounds of 4096 and shows each round's counts on the LCD, with nothing driving port B against the VIA.

Run from the repo root:  python3 -m unittest discover -s tools/tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import michael_emulator  # noqa: E402

PROGRAM = os.path.join(michael_emulator.ROOT, 'firmware', 'programs', 'michael', 'michael_w5500_version.s')


@unittest.skipUnless(michael_emulator.AVAILABLE, 'vasm6502_oldstyle, gcc and make are needed')
class W5500VersionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        michael_emulator.build_emulator()

    def run_program(self, hardware):
        return michael_emulator.run(program=PROGRAM, cycle_cap=3_000_000, options=['--add', hardware])[1]

    def test_every_read_finds_version_4(self):
        report = self.run_program('gal-spi,w5500')
        self.assertIn('LAST 04 FIRST BAD --', report)
        self.assertIn('GOOD 1000 BAD 0000', report)
        self.assertIn('portb-contention=0', report)

    def test_without_the_w5500_miso_reads_high(self):
        report = self.run_program('gal-spi')
        self.assertIn('LAST FF FIRST BAD FF', report)
        self.assertIn('GOOD 0000 BAD 1000', report)
        self.assertIn('portb-contention=0', report)


if __name__ == '__main__':
    unittest.main()
