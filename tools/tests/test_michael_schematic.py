"""Michael's schematic (hardware/michael/schematics/michael_schematic.py) against the firmware and the FPGA
design: the VIA pins the firmware names reach the parts that use them, the 74HC00's chip selects give
Michael's memory map, the FPGA pin names are the design's ports, and the committed SVGs are current.

Run from the repo root:  python3 -m unittest discover -s tools/tests -v
"""
import itertools
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
SCHEMATICS = os.path.join(ROOT, 'hardware', 'michael', 'schematics')
sys.path.insert(0, SCHEMATICS)
import michael_schematic  # noqa: E402


def constants(path):
    """NAME = %bits definitions from a firmware include, as bit numbers."""
    found = {}
    with open(os.path.join(ROOT, path)) as f:
        for line in f:
            m = re.match(r'(\w+)\s*=\s*%([01]{8})\b', line)
            if m and m[2].count('1') == 1:
                found[m[1]] = 7 - m[2].index('1')
    return found


class MichaelSchematicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = michael_schematic.board()

    def joined(self, a, b):
        """True if pin a and pin b, each (ref, pin name or number), are on the same net."""
        return self.board.net(*a) is not None and self.board.net(*a) == self.board.net(*b)

    def assertJoined(self, a, b):
        self.assertTrue(self.joined(a, b), f'{a} (net {self.board.net(*a)}) and {b} (net {self.board.net(*b)})')

    def test_every_net_joins_two_pins_or_more(self):
        single = {net: pins for net, pins in self.board.nets().items() if len(pins) < 2}
        self.assertEqual(single, {})

    def test_port_a_reaches_what_the_firmware_drives(self):
        lcd_and_keyboard = constants('firmware/boards/michael/base_config_v2.inc')
        display = constants('firmware/lib/graphics/graphics_display.inc')
        uses = {'E': ('U3', 'E'), 'RW': ('U3', 'RW'), 'RS': ('U3', 'RS'),
                'SOLB': ('J1', 'KBD_CLK_OUT'), 'SOEB': ('J1', 'REG_OE'),
                'START': ('J1', 'DE'), 'ACK': ('J1', 'DE'), 'PARITY': ('J1', 'DP'), 'LED': ('R8', 1)}
        gd_uses = {'GD_E': 'B1', 'GD_CSB': 'B2', 'GD_RSTB': 'B3', 'GD_DC': 'B4'}
        for name, part_pin in uses.items():
            with self.subTest(name):
                self.assertJoined(('U5', f'PA{lcd_and_keyboard[name]}'), part_pin)
        for name, buffer_pin in gd_uses.items():
            with self.subTest(name):
                self.assertJoined(('U5', f'PA{display[name]}'), ('U8', buffer_pin))

    def test_port_b_is_the_lcd_keyboard_and_fpga_data_bus(self):
        for i in range(8):
            with self.subTest(bit=i):
                self.assertJoined(('U5', f'PB{i}'), ('U3', f'DB{i}'))
                self.assertJoined(('U5', f'PB{i}'), ('J1', f'D{i}'))
                self.assertJoined(('U5', f'PB{i}'), ('U7', f'B{i + 1}'))

    def test_interrupts_serial_and_reset(self):
        self.assertJoined(('U5', 'CA2'), ('J1', 'IRQ'))           # the keyboard's frame detector
        self.assertJoined(('U5', 'CB2'), ('J2', 'TXD'))           # serial in, through the shift register
        self.assertJoined(('U5', 'IRQB'), ('U1', 'IRQB'))
        self.assertJoined(('U1', 'RESB'), ('U5', 'RESB'))
        self.assertJoined(('U1', 'RESB'), ('SW1', 1))

    def test_chip_selects_give_the_memory_map(self):
        """Evaluates the 74HC00 (U4) for every combination of A15, A14, A13 and PHI2."""
        b = self.board
        gates = [((1, 2), 3), ((4, 5), 6), ((9, 10), 8), ((12, 13), 11)]
        for a15, a14, a13, phi2 in itertools.product((0, 1), repeat=4):
            levels = {b.net('U1', 'A15'): a15, b.net('U1', 'A14'): a14, b.net('U1', 'A13'): a13,
                      b.net('U1', 'PHI2'): phi2, 'GND': 0, '+5V': 1}
            for _ in gates:
                for (i1, i2), out in gates:
                    n1, n2 = b.net('U4', i1), b.net('U4', i2)
                    if n1 in levels and n2 in levels:
                        levels[b.net('U4', out)] = 1 - (levels[n1] & levels[n2])
            level = lambda ref, pin: levels[b.net(ref, pin)]  # noqa: E731
            addr = a15 << 15 | a14 << 14 | a13 << 13
            with self.subTest(addr=f'${addr:04X}', phi2=phi2):
                self.assertEqual(level('U2', '/CE') == 0, addr >= 0x8000, 'ROM')
                self.assertEqual(level('U6', '/CE') == 0, addr < 0x8000 and phi2 == 1, 'RAM')
                self.assertEqual(level('U6', '/OE'), a14, 'RAM reads only below $4000')
                self.assertEqual(level('U5', 'CS1') == 1 and level('U5', 'CS2B') == 0,
                                 0x6000 <= addr < 0x8000, 'VIA')

    def test_fpga_pins_are_the_designs_ports(self):
        ports = set()
        for xdc in ('spi-display/constr/cmod_a7.xdc', 'display-probe/constr/miso.xdc'):  # MISO: the probe's
            with open(os.path.join(ROOT, 'hardware/michael/fpga', xdc)) as f:
                ports |= set(re.findall(r'get_ports \{(\S+)\}', f.read()))
        nets = {self.board.net('U9', pin) for pin in range(1, 49)} - {None, 'GND', '+5V', '+3V3', 'VU'}
        self.assertEqual(nets - ports, set())
        for i in range(8):
            self.assertEqual(self.board.net('U9', i + 1), f'd[{i}]')
        for pin, net in ((9, 'e'), (10, 'csb'), (11, 'rstb'), (12, 'dc'), (13, 'bl'), (26, 'lcd_cs'),
                         (27, 'lcd_reset'), (28, 'lcd_dc'), (29, 'lcd_mosi'), (30, 'lcd_sck'), (31, 'lcd_led'),
                         (32, 'lcd_miso')):
            self.assertEqual(self.board.net('U9', pin), net)

    def test_committed_svgs_are_current(self):
        for name, svg in michael_schematic.sheets().items():
            with self.subTest(name), open(os.path.join(SCHEMATICS, name)) as f:
                self.assertEqual(f.read(), svg, f'run: python3 {os.path.relpath(SCHEMATICS, ROOT)}/michael_schematic.py')


if __name__ == '__main__':
    unittest.main()
