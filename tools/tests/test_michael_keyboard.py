"""Michael's keyboard programs, run on the emulator's Michael machine.

The emulator models the VIA, the LCD and the PS/2 keyboard board closely
enough for the keyboard driver (firmware/lib/keyboard/keyboard_driver.inc):
the start-up handshake, key frames, and whether the LCD and the keyboard
board share the bus without fighting over it. Programs are loaded at
PROGRAM_LOAD_ADDRESS from base_config_v2.inc; the emulator's ROM sends IRQs
to $3F00, INTERRUPT_VECTOR_TARGET.

Uses firmware/vasm with vasm6502_oldstyle from PATH, and builds the emulator
with make (tests skip if vasm, gcc or make is missing).
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
FW_VASM = os.path.join(ROOT, 'firmware', 'vasm')
EMULATOR = os.path.join(ROOT, 'emulator', 'emulator.out')
BASE_CONFIG = os.path.join(ROOT, 'firmware', 'boards', 'michael', 'base_config_v2.inc')
PROGRAMS = os.path.join(ROOT, 'firmware', 'programs', 'michael')

KEY_A = ['1c', 'f0', '1c']                                   # PS/2 set 2: 'a' down, up
KEY_PAUSE = ['e1', '14', '77', 'e1', 'f0', '14', 'f0', '77']  # Pause/Break: down only


def base_config_address(name):
    with open(BASE_CONFIG) as f:
        return re.search(r'^%s\s*=\s*\$([0-9a-fA-F]+)' % name, f.read(), re.M).group(1)


@unittest.skipUnless(shutil.which('vasm6502_oldstyle') and shutil.which('gcc') and shutil.which('make'),
                     'vasm6502_oldstyle, gcc and make are needed')
class MichaelKeyboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        subprocess.run(['make', '-s', 'emulator/emulator.out'], cwd=ROOT, check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_program(self, name, keys=(), fault=None, typed=None):
        """Returns the LCD's 4 lines once the keys have been typed: keys are raw scan code
        bytes, typed is text the emulator types on the keyboard."""
        binary = os.path.join(self.tmp.name, name + '.bin')
        subprocess.run([FW_VASM, '-quiet', '-wdc02', '-wfail', '-Fbin', '-dotdir',
                        '-ignore-mult-inc', '-esc', '-o', binary,
                        os.path.join(PROGRAMS, name + '.s')], check=True, capture_output=True)
        options = ['--kbd-scancodes', ','.join(keys)] if keys else []
        if fault:
            options += ['--kbd-fault', fault]
        if typed is not None:
            keys_file = os.path.join(self.tmp.name, name + '.keys')
            with open(keys_file, 'wb') as f:
                f.write(typed)
            options += ['--keys', keys_file]
        report = subprocess.run([EMULATOR, binary, '--machine', 'michael',
                                 '--load', base_config_address('PROGRAM_LOAD_ADDRESS'),
                                 '--cycle-cap', '2000000', *options],
                                check=True, capture_output=True, text=True).stderr.splitlines()
        self.assertIn('michael: bus: lcd-undriven=0 portb-contention=0', report)
        lcd = report.index('michael: lcd:')
        return [line.strip()[1:-1].rstrip() for line in report[lcd + 1:lcd + 5]]

    def diag_text(self, keys=(), fault=None):
        """The diagnostic's output as one string, without the IRQ vector it starts with."""
        text = ''.join(line.ljust(20) for line in self.run_program('michael_keyboard_diag', keys, fault))
        self.assertRegex(text, r'^IRQ [0-9A-F]{4} ')
        return text[9:].rstrip()

    def test_keyboard_new_echoes_a_key(self):
        self.assertEqual(self.run_program('michael_keyboard_new', KEY_A)[0], '>a')

    def test_keyboard_new_echoes_typed_text(self):
        self.assertEqual(self.run_program('michael_keyboard_new', typed=b'Hi there!')[0], '>Hi there!')

    def test_show_names_names_a_key(self):
        self.assertEqual(self.run_program('michael_keyboard_show_names', KEY_A)[:2], ['Ready?', 'A?'])

    def test_show_names_names_pause(self):
        self.assertEqual(self.run_program('michael_keyboard_show_names', KEY_PAUSE + KEY_A)[:3],
                         ['Ready?', 'PAUSE?', 'A?'])

    def test_diag_shows_start_up_then_raw_bytes(self):
        self.assertEqual(self.diag_text(KEY_A), 'F4bcd F3bcd 20bcd EDbcd 02bcd >1C F0 1C')

    def test_diag_stops_when_the_clock_cannot_be_pulled_low(self):
        self.assertEqual(self.diag_text(KEY_A, 'noedge'), 'F4')

    def test_diag_stops_when_no_interrupt_arrives(self):
        self.assertEqual(self.diag_text(KEY_A, 'noirq'), 'F4bc')

    def test_diag_shows_bytes_that_arrive_instead_of_an_ack(self):
        self.assertEqual(self.diag_text(KEY_A, 'noack'), 'F4bcd[1C][F0][1C]')

    def test_diag_shows_a_resend_request(self):
        self.assertEqual(self.diag_text(KEY_A, 'resend'), 'F4bcd[FE][1C][F0][1C]')


if __name__ == '__main__':
    unittest.main()
