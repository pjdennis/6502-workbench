"""Tests for tools/firmware_manifest.py.

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
TOOL = os.path.join(HERE, '..', 'firmware_manifest.py')

HAVE_VASM = shutil.which('vasm6502_oldstyle') is not None

GOOD = """  .org $8000
  .include "lib.inc"
start:
  lda #VALUE
  .byte "a\\n"
"""
LIB = "VALUE = $42\n"
BAD = "  .org $8000\n  lda #UNDEFINED_SYMBOL\n"


def run(*args, cwd=None):
    return subprocess.run([sys.executable, TOOL, *args], cwd=cwd,
                          capture_output=True, text=True)


@unittest.skipUnless(HAVE_VASM, 'vasm6502_oldstyle not on PATH')
class FirmwareManifestTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.write('good.s', GOOD)
        self.write('lib.inc', LIB)
        self.write('bad.s', BAD)
        self.write('sub/other.s', GOOD.replace('"lib.inc"', '"../lib.inc"'))
        self.write('excluded/skip.s', BAD)
        self.manifest = os.path.join(self.root, 'manifest.txt')

    def tearDown(self):
        shutil.rmtree(self.root)

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(text)

    def tool(self, command, *extra):
        return run(command, '--root', self.root, '--manifest', self.manifest,
                   '--exclude', 'excluded', *extra)

    def entries(self):
        with open(self.manifest) as f:
            lines = [l.split() for l in f if l.strip() and not l.startswith('#')]
        return {l[0]: l[1:] for l in lines}

    def test_update_records_hash_or_fail_per_flag_set(self):
        result = self.tool('update')
        self.assertEqual(result.returncode, 0, result.stderr)
        entries = self.entries()
        self.assertEqual(sorted(entries), ['bad.s', 'good.s', 'sub/other.s'])
        self.assertEqual(entries['bad.s'], ['esc=FAIL', 'noesc=FAIL'])
        esc, noesc = entries['good.s']
        self.assertRegex(esc, r'^esc=[0-9a-f]{64}$')
        self.assertRegex(noesc, r'^noesc=[0-9a-f]{64}$')
        # -esc turns "\n" into one byte, so the two builds differ
        self.assertNotEqual(esc[4:], noesc[6:])
        # same source, assembled from its own directory, gives the same bytes
        self.assertEqual(entries['sub/other.s'], entries['good.s'])

    def test_update_records_the_assembler_version(self):
        self.tool('update')
        with open(self.manifest) as f:
            header = [l for l in f if l.startswith('# assembler: ')]
        self.assertEqual(len(header), 1)
        self.assertRegex(header[0], r'^# assembler: vasm \d+\.\d+\w*')

    def test_check_passes_when_nothing_changed(self):
        self.tool('update')
        result = self.tool('check')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_check_fails_when_output_changes(self):
        self.tool('update')
        self.write('lib.inc', 'VALUE = $43\n')
        result = self.tool('check')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('good.s', result.stdout)
        self.assertIn('sub/other.s', result.stdout)

    def test_check_fails_when_a_program_is_added_or_removed(self):
        self.tool('update')
        os.remove(os.path.join(self.root, 'bad.s'))
        self.write('new.s', GOOD)
        result = self.tool('check')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('bad.s', result.stdout)
        self.assertIn('new.s', result.stdout)

    def test_check_fails_without_a_manifest(self):
        result = self.tool('check')
        self.assertNotEqual(result.returncode, 0)

    def record_other_assembler(self):
        with open(self.manifest) as f:
            text = f.read()
        with open(self.manifest, 'w') as f:
            f.write(text.replace('# assembler: vasm', '# assembler: OTHER vasm'))

    def test_check_passes_with_a_warning_when_only_the_assembler_differs(self):
        # Matching hashes are the real test: another vasm that produces the
        # same bytes passes, but the difference is still reported
        self.tool('update')
        self.record_other_assembler()
        result = self.tool('check')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('warning: assembler differs', result.stdout)
        self.assertIn('OTHER vasm', result.stdout)
        self.assertIn('0 differences', result.stdout)

    def test_check_blames_the_assembler_when_output_also_changes(self):
        self.tool('update')
        self.record_other_assembler()
        self.write('lib.inc', 'VALUE = $43\n')
        result = self.tool('check')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('good.s', result.stdout)
        self.assertIn('assembler differs', result.stdout)
        self.assertIn('may explain', result.stdout)

    def test_default_excludes_skip_non_firmware_dirs(self):
        for d in ('attic', 'emulator', 'toolchain'):
            self.write(f'{d}/parked.s', BAD)
        result = run('update', '--root', self.root, '--manifest', self.manifest)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(self.entries()),
                         ['bad.s', 'excluded/skip.s', 'good.s', 'sub/other.s'])

    def test_include_list_file_adds_each_listed_dir(self):
        for d in ('lib/a', 'lib/b'):
            os.makedirs(os.path.join(self.root, d))
        shutil.move(os.path.join(self.root, 'lib.inc'),
                    os.path.join(self.root, 'lib/b/lib.inc'))
        self.write('dirs.txt', '# comment\nlib/a\n\nlib/b\n')
        self.tool('update', '--include-list', os.path.join(self.root, 'dirs.txt'))
        self.assertNotIn('FAIL', self.entries()['good.s'][0])

    def test_include_dir_option_is_passed_to_vasm(self):
        os.makedirs(os.path.join(self.root, 'libdir'))
        shutil.move(os.path.join(self.root, 'lib.inc'),
                    os.path.join(self.root, 'libdir', 'lib.inc'))
        self.tool('update', '--include', 'libdir')
        entries = self.entries()
        self.assertNotIn('FAIL', entries['good.s'][0])


if __name__ == '__main__':
    unittest.main()
