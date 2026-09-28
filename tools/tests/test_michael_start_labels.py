"""Every program uploaded to Michael's RAM (with compile_and_upload_michael.sh, whose S-records carry
the start address from vasm -exec) has a start label at its entry: its lowest address.

Run from the repo root:  python3 -m unittest discover -s tools/tests -v
Requires vasm6502_oldstyle on PATH (tests skip otherwise).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'upload'))
import upload_frame  # noqa: E402

UPLOADED = ('firmware/programs/michael/', 'firmware/boards/michael/upload_and_run_ram_v2.s', 'tools/tests/michael/')


def programs():
    """The uploaded programs that assemble (as firmware/manifest.txt records): Michael's in RAM, not
    the bring-up ROMs or BBC BASIC, which has its own loader."""
    with open(os.path.join(ROOT, 'firmware', 'manifest.txt')) as f:
        entries = [line.split() for line in f if not line.startswith('#')]
    return [os.path.join(ROOT, source) for source, esc, _ in entries
            if source.startswith(UPLOADED) and '/bringup/' not in source and '/bbc-basic/' not in source
            and esc != 'esc=FAIL']


@unittest.skipUnless(shutil.which('vasm6502_oldstyle'), 'vasm6502_oldstyle not on PATH')
class StartLabelTest(unittest.TestCase):
    def test_each_program_starts_at_its_lowest_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            for program in programs():
                with self.subTest(os.path.relpath(program, ROOT)):
                    out = os.path.join(tmp, 'a.s19')
                    result = subprocess.run([os.path.join(ROOT, 'firmware', 'vasm'), '-quiet', '-wdc02', '-wfail',
                                             '-Fsrec', '-s19', '-exec=start', '-dotdir', '-ignore-mult-inc', '-esc',
                                             '-I', os.path.join(HERE, 'michael'), '-o', out, program],
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    with open(out) as f:
                        segments, start = upload_frame.read_srec(f.read())
                    self.assertEqual(start, segments[0][0])


if __name__ == '__main__':
    unittest.main()
