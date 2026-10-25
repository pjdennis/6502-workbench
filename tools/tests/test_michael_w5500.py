"""The W5500 Ethernet controller behind the GAL20RA10 SPI interface, on the emulator's Michael with the FPGA board
unplugged (--add gal-spi,w5500), with nothing driving port B against the VIA:
- firmware/programs/michael/michael_w5500_version.s reads VERSIONR ($04) in rounds of 4096 and shows each
  round's counts on the LCD;
- firmware/programs/michael/michael_w5500_ping.s gives the W5500 its network settings, so it answers ping, and
  shows them, the link and frames whose header count ($01 $02 $03) was wrong.

Run from the repo root:  python3 -m unittest discover -s tools/tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import michael_emulator  # noqa: E402

PROGRAMS = os.path.join(michael_emulator.ROOT, 'firmware', 'programs', 'michael')
PROGRAM = os.path.join(PROGRAMS, 'michael_w5500_version.s')
PING = os.path.join(PROGRAMS, 'michael_w5500_ping.s')


@unittest.skipUnless(michael_emulator.AVAILABLE, 'vasm6502_oldstyle, gcc and make are needed')
class W5500VersionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        michael_emulator.build_emulator()

    def run_program(self, hardware, program=PROGRAM):
        return michael_emulator.run(program=program, cycle_cap=3_000_000, options=['--add', hardware])[1]

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

    def test_ping_setup_gives_the_w5500_its_network(self):
        report = self.run_program('gal-spi,w5500', PING)
        self.assertIn('|W5500 192.168.8.50  |', report)
        self.assertIn('|CONFIG OK           |', report)
        self.assertIn('|LINK UP 100M FULL   |', report)
        self.assertIn('|BAD FRAMES 0000     |', report)
        self.assertIn('michael: w5500: ip 192.168.8.50 mask 255.255.255.0 gateway 192.168.8.1 '
                      'mac 02:65:02:00:00:01', report)
        self.assertIn('portb-contention=0', report)

    def test_ping_setup_without_the_w5500(self):
        report = self.run_program('gal-spi', PING)
        self.assertIn('|NO W5500            |', report)


if __name__ == '__main__':
    unittest.main()
