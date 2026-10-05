"""hardware/michael/Makefile's targets for Michael's ROM, by make's dry run (programming the EEPROM can't run
here): `rom` builds the image with tools/michael_rom.py; `program` builds it, backs up what's on the EEPROM,
then writes the image, in that order.

Run from the repo root:  python3 -m unittest discover -s tools/tests -v
"""
import os
import re
import shutil
import subprocess
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
MICHAEL = os.path.join(ROOT, 'hardware', 'michael')


def dry_run(*args):
    return subprocess.run(['make', '-n', '-C', MICHAEL, *args], check=True, capture_output=True,
                          text=True).stdout


@unittest.skipUnless(shutil.which('make'), 'make is needed')
class MichaelRomMakeTest(unittest.TestCase):
    def test_rom_builds_the_image(self):
        self.assertIn('tools/michael_rom.py', dry_run('rom'))

    def test_program_builds_backs_up_then_writes(self):
        out = dry_run('program')
        found = [re.search(pattern, out) for pattern in (r'michael_rom\.py', r'minipro -p AT28C256 .*-r \S*backups/',
                                                          r'minipro -p AT28C256 .*-w \S*michael_rom\.bin')]
        self.assertTrue(all(found), out)
        build, backup, write = (m.start() for m in found)
        self.assertTrue(build < backup < write, out)

    def test_minipro_flags_pass_through(self):
        self.assertIn('--no-write-protect', dry_run('program', 'MINIPRO_FLAGS=--no-write-protect'))


if __name__ == '__main__':
    unittest.main()
