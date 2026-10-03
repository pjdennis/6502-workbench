"""Michael's schematics (hardware/michael/schematics/michael_schematic.py), as built and as planned once the
FPGA bus plan (docs/michael-fpga-bus-plan.md) is complete, against the firmware and the FPGA design: the
VIA pins the firmware names reach the parts that use them, the 74HC00's chip selects give Michael's memory
map, the FPGA pin names are the design's ports, and the committed SVGs are current.

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

LCD_AND_KEYBOARD = 'firmware/boards/michael/base_config_v2.inc'


def constants(path):
    """NAME = %bits definitions from a firmware include, as bit numbers."""
    found = {}
    with open(os.path.join(ROOT, path)) as f:
        for line in f:
            m = re.match(r'(\w+)\s*=\s*%([01]{8})\b', line)
            if m and m[2].count('1') == 1:
                found[m[1]] = 7 - m[2].index('1')
    return found


class BoardChecks:
    """What holds in both states. Subclasses set PLANNED."""
    PLANNED = None

    @classmethod
    def setUpClass(cls):
        cls.board = michael_schematic.board(planned=cls.PLANNED)

    def joined(self, a, b):
        """True if pin a and pin b, each (ref, pin name or number), are on the same net."""
        return self.board.net(*a) is not None and self.board.net(*a) == self.board.net(*b)

    def assertJoined(self, a, b):
        self.assertTrue(self.joined(a, b), f'{a} (net {self.board.net(*a)}) and {b} (net {self.board.net(*b)})')

    def assertPinsOn(self, net, *pins):
        for pin in pins:
            self.assertEqual(self.board.net(*pin), net, pin)

    def test_every_part_has_a_value(self):
        """The sheets are build instructions: no part left as a question."""
        for ref in self.board.parts:
            with self.subTest(ref):
                self.assertTrue(self.board.values[ref])
                self.assertNotIn('?', self.board.values[ref])

    def test_the_fpga_supplies(self):
        """+3V3 from an LM1117 (IN pin 3, GND 1, OUT 2), the Cmod's VU through D2, and C7 on the 5 V rail."""
        self.assertIn('LM1117', self.board.values['U11'])
        self.assertPinsOn('+5V', ('U11', 3), ('D2', 'A'), ('C7', 1))
        self.assertPinsOn('+3V3', ('U11', 2))
        self.assertPinsOn('GND', ('U11', 1), ('C7', 2))
        self.assertPinsOn('VU', ('D2', 'K'), ('U9', 24))

    def test_the_regulator_has_the_capacitors_its_data_sheet_asks_for(self):
        """10 µF on U11's input (C8) and output (C9): not fitted yet, so marked to add."""
        for ref, rail in (('C8', '+5V'), ('C9', '+3V3')):
            with self.subTest(ref):
                self.assertPinsOn(rail, (ref, 1))
                self.assertPinsOn('GND', (ref, 2))
                self.assertIn('10 µF', self.board.values[ref])
                self.assertIn('to add', self.board.values[ref])

    def test_every_net_joins_two_pins_or_more(self):
        single = {net: pins for net, pins in self.board.nets().items() if len(pins) < 2}
        self.assertEqual(single, {})

    def test_port_a_reaches_the_lcd_and_keyboard(self):
        bits = constants(LCD_AND_KEYBOARD)
        uses = {'E': ('U3', 'E'), 'RW': ('U3', 'RW'), 'RS': ('U3', 'RS'),
                'SOLB': ('J1', 'KBD_CLK_OUT'), 'SOEB': ('J1', 'REG_OE'),
                'START': ('J1', 'DE'), 'ACK': ('J1', 'DE'), 'PARITY': ('J1', 'DP')}
        for name, part_pin in uses.items():
            with self.subTest(name):
                self.assertJoined(('U5', f'PA{bits[name]}'), part_pin)

    def test_port_b_is_the_lcd_keyboard_and_fpga_data_bus(self):
        for i in range(8):
            with self.subTest(bit=i):
                self.assertJoined(('U5', f'PB{i}'), ('U3', f'DB{i}'))
                self.assertJoined(('U5', f'PB{i}'), ('J1', f'D{i}'))
                self.assertJoined(('U5', f'PB{i}'), ('U7', f'B{i + 1}'))

    def test_interrupts_and_serial(self):
        self.assertJoined(('U5', 'CA2'), ('J1', 'IRQ'))           # the keyboard's frame detector
        self.assertJoined(('U5', 'CB2'), ('J2', 'TXD'))           # serial in, through the shift register
        self.assertJoined(('U5', 'IRQB'), ('U1', 'IRQB'))

    def test_reset_from_the_button_or_dtr(self):
        """SW1 and C1 on RESB with R1's pull-up; DTR pulls RESB low through R13 and D3, whose anode is on
        RESB so DTR high never fights the button."""
        self.assertPinsOn('RESB', ('U1', 'RESB'), ('U5', 'RESB'), ('SW1', 1), ('C1', 1), ('R1', 2), ('D3', 'A'))
        self.assertJoined(('D3', 'K'), ('R13', 2))
        self.assertJoined(('R13', 1), ('J2', 'DTR'))

    def test_power_comes_from_the_usb_serial_adapter(self):
        self.assertPinsOn('+5V', ('J2', '+5V'), ('U1', 'VDD'), ('U5', 'VDD'))
        self.assertPinsOn('GND', ('J2', 'GND'))
        self.assertIsNone(self.board.net('J2', '3V3'))

    def test_spare_nand_inputs_are_tied_high(self):
        self.assertPinsOn('+5V', ('U4', 1), ('U4', 2))

    def test_unused_buffer_inputs_are_tied_low(self):
        for pin in self.UNUSED_CONTROL_INPUTS:
            with self.subTest(pin):
                tie = self.board.net('U8', pin)
                ref = next(r for r, pins in self.board.parts.items()
                           if r.startswith('R') and any(net == tie for _, _, net in pins))
                self.assertEqual({self.board.net(ref, 1), self.board.net(ref, 2)}, {tie, 'GND'})

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

    def test_cmod_pins(self):
        for i in range(8):
            self.assertEqual(self.board.net('U9', i + 1), f'd[{i}]')
        for pin, net in self.CMOD_PINS.items():
            self.assertEqual(self.board.net('U9', pin), net, f'Cmod pin {pin}')


class AsBuiltTest(BoardChecks, unittest.TestCase):
    PLANNED = False
    UNUSED_CONTROL_INPUTS = ('B6', 'B7', 'B8')
    CMOD_PINS = {9: 'e', 10: 'csb', 11: 'rstb', 12: 'dc', 13: 'bl', 26: 'lcd_cs', 27: 'lcd_reset', 28: 'lcd_dc',
                 29: 'lcd_mosi', 30: 'lcd_sck', 31: 'lcd_led', 32: 'lcd_miso'}

    def test_port_a_reaches_the_display_interface(self):
        bits = constants('firmware/lib/graphics/graphics_display.inc')
        for name, buffer_pin in {'GD_E': 'B1', 'GD_CSB': 'B2', 'GD_RSTB': 'B3', 'GD_DC': 'B4'}.items():
            with self.subTest(name):
                self.assertJoined(('U5', f'PA{bits[name]}'), ('U8', buffer_pin))

    def test_the_led_lights_when_pa2_is_low(self):
        """Reversed, so the display's reset (active low, idle high) leaves it dark."""
        self.assertJoined(('U5', f'PA{constants(LCD_AND_KEYBOARD)["LED"]}'), ('D1', 'K'))
        self.assertJoined(('D1', 'A'), ('R8', 2))
        self.assertPinsOn('+5V', ('R8', 1))

    def test_fpga_pins_are_the_designs_ports(self):
        ports = set()
        for xdc in ('spi-display/constr/cmod_a7.xdc', 'display-probe/constr/miso.xdc'):  # MISO: the probe's
            with open(os.path.join(ROOT, 'hardware/michael/fpga', xdc)) as f:
                ports |= set(re.findall(r'get_ports \{(\S+)\}', f.read()))
        nets = {self.board.net('U9', pin) for pin in range(1, 49)} - {None, 'GND', '+5V', '+3V3', 'VU'}
        self.assertEqual(nets - ports, set())


class PlannedTest(BoardChecks, unittest.TestCase):
    """The FPGA bus plan's wiring changes: stage 1's, then stage 4's pin shuffle (E to PA2, the LED to PA1,
    PA0 free). The firmware moves the LED and E in stage 4, so their pins are written out here."""
    PLANNED = True
    E, LED = 2, 1
    UNUSED_CONTROL_INPUTS = ('B1', 'B2', 'B8')
    CMOD_PINS = {11: 'e', 12: 'rs', 14: 'd_oeb', 17: 'd_dir', 18: 'soeb', 19: 'rw', 26: 'lcd_cs', 27: 'lcd_reset',
                 28: 'lcd_dc', 29: 'lcd_mosi', 30: 'lcd_sck', 31: 'lcd_led', 32: 'lcd_miso'}

    def test_the_bus_signals_reach_the_fpga(self):
        bits = constants(LCD_AND_KEYBOARD)
        for pa, buffer_pin, cmod_pin in ((self.E, 'B3', 11), (bits['RS'], 'B4', 12), (bits['SOEB'], 'B6', 18),
                                         (bits['RW'], 'B7', 19)):
            with self.subTest(pa=pa):
                self.assertJoined(('U5', f'PA{pa}'), ('U8', buffer_pin))
                self.assertJoined(('U8', 'A' + buffer_pin[1:]), ('U9', cmod_pin))

    def test_pa0_is_free(self):
        self.assertIsNone(self.board.net('U5', 'PA0'))

    def test_e_is_pulled_down(self):
        self.assertTrue(any({self.board.net(r, 1), self.board.net(r, 2)} == {f'PA{self.E}', 'GND'}
                            for r in self.board.parts if r.startswith('R')))

    def test_the_fpga_controls_the_data_buffer_and_it_defaults_off_and_inward(self):
        self.assertJoined(('U7', '/OE'), ('U9', 14))
        self.assertJoined(('U7', 'DIR'), ('U9', 17))
        pulls = {frozenset((self.board.net(r, 1), self.board.net(r, 2))) for r in self.board.parts
                 if r.startswith('R')}
        self.assertIn(frozenset(('d_oeb', '+3V3')), pulls)   # off while the FPGA isn't configured
        self.assertIn(frozenset(('d_dir', 'GND')), pulls)    # B to A: Michael to the FPGA

    def test_the_led_is_on_pa1_and_lights_when_it_is_high(self):
        self.assertJoined(('U5', f'PA{self.LED}'), ('R8', 1))
        self.assertJoined(('R8', 2), ('D1', 'A'))
        self.assertPinsOn('GND', ('D1', 'K'))


class CommittedOutputTest(unittest.TestCase):
    def test_committed_sheets_and_parts_lists_are_current(self):
        outputs = michael_schematic.outputs()
        self.assertIn('parts.md', outputs)
        self.assertIn('planned/parts.md', outputs)
        for name, text in outputs.items():
            with self.subTest(name), open(os.path.join(SCHEMATICS, name)) as f:
                self.assertEqual(f.read(), text, f'run: python3 {os.path.relpath(SCHEMATICS, ROOT)}/michael_schematic.py')


if __name__ == '__main__':
    unittest.main()
