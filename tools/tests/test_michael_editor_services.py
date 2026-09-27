"""The Michael editor services (firmware/programs/michael/michael_editor_services.s)
on the emulator's Michael machine: screen calls and keys, driven by small test
programs in tests/michael/ that call the services' vectors.

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
SERVICES = os.path.join(ROOT, 'firmware', 'programs', 'michael', 'michael_editor_services.s')
LAYOUT = os.path.join(ROOT, 'firmware', 'boards', 'michael', 'michael_editor_layout.inc')
TESTS = os.path.join(os.path.dirname(__file__), 'michael')
LOAD = 0x0400


def layout_address(name):
    with open(LAYOUT) as f:
        return int(re.search(r'^%s\s*=\s*\$([0-9a-fA-F]+)' % name, f.read(), re.M).group(1), 16)


@unittest.skipUnless(shutil.which('vasm6502_oldstyle') and shutil.which('gcc') and shutil.which('make'),
                     'vasm6502_oldstyle, gcc and make are needed')
class MichaelEditorServicesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        subprocess.run(['make', '-s', 'emulator/emulator.out'], cwd=ROOT, check=True, capture_output=True)
        cls.services = cls.assemble(SERVICES)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def assemble(cls, source):
        binary = os.path.join(cls.tmp.name, os.path.basename(source) + '.bin')
        subprocess.run([FW_VASM, '-quiet', '-wdc02', '-wfail', '-Fbin', '-dotdir', '-ignore-mult-inc',
                        '-esc', '-I', TESTS, '-o', binary, source], check=True, capture_output=True)
        with open(binary, 'rb') as f:
            return f.read()

    def run_program(self, name, typed=None):
        """The LCD's 4 lines after running tests/michael/<name>.s with the services."""
        program = self.assemble(os.path.join(TESTS, name + '.s'))
        services_at = layout_address('MICHAEL_ENV_BASE') + 6
        self.assertLessEqual(LOAD + len(program), services_at)
        image = program + bytes(services_at - LOAD - len(program)) + self.services
        image_file = os.path.join(self.tmp.name, name + '.image')
        with open(image_file, 'wb') as f:
            f.write(image)
        options = []
        if typed is not None:
            keys_file = os.path.join(self.tmp.name, name + '.keys')
            with open(keys_file, 'wb') as f:
                f.write(typed)
            options = ['--keys', keys_file]
        report = subprocess.run([EMULATOR, image_file, '--machine', 'michael', '--load', '%04x' % LOAD,
                                 '--cycle-cap', '20000000', *options],
                                check=True, capture_output=True, text=True).stderr.splitlines()
        self.assertTrue(report[0].endswith('(STP)'), report[0])
        self.assertIn('michael: bus: lcd-undriven=0 portb-contention=0', report)
        lcd = report.index('michael: lcd:')
        return [line.strip()[1:-1] for line in report[lcd + 1:lcd + 5]]

    def test_screen_calls(self):
        self.assertEqual(self.run_program('screen_calls'), [
            'HelloXY world       ',
            '  abcdefghijklmnopqr',
            '~\\uvwxyz            ',
            'status        abcdef'])

    def test_scrolling(self):
        self.assertEqual(self.run_program('screen_scroll'), [
            '                    ',
            'row1                ',
            'again               ',
            '                    '])

    def test_keys(self):
        typed = b'aA\x06\x1b[A\x1b[1;5C\x1b[3~\x1b\r\x08q'
        self.assertEqual(self.run_program('keys', typed)[0], '6141068089881B0D08  ')
