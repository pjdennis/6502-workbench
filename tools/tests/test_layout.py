"""The repository layout: asm/, editor/ and prog8/ are top-level areas, asm1 is in the attic.

Guards the 2026-09 move out of toolchain/ (see docs/history.md): the new directories exist,
the old ones are gone, nothing live still names an old path, and the editor's includes and
launchers resolve from the repository root.
"""
import glob
import os
import re
import subprocess
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

# Files that describe the old paths on purpose, and the attic (never built or tested).
HISTORICAL = ('attic/', 'docs/history.md', 'docs/REORGANIZATION_PLAN.md', 'tools/reorg/',
              'tools/tests/test_layout.py')
OLD_PATH = re.compile(r'(?<!\w)toolchain/(?:asm|prog8|README)|(?<![\w-])asm2/(?:17|editor|Makefile|verify)')


def tracked_files():
    out = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout
    return [f for f in out.split('\0') if f and not f.startswith(HISTORICAL)]


def is_text(path):
    with open(os.path.join(ROOT, path), 'rb') as f:
        return b'\0' not in f.read(2048)


class LayoutTest(unittest.TestCase):
    def test_new_areas_exist(self):
        for d in ('asm/17', 'editor/tests', 'editor/bin', 'prog8/p8c', 'attic/asm1'):
            self.assertTrue(os.path.isdir(os.path.join(ROOT, d)), d)

    def test_old_areas_are_gone(self):
        # Tracked files only: an old checkout's untracked build output (toolchain/asm2/*/out/)
        # can linger after pulling.
        files = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True,
                               text=True, check=True).stdout.split('\n')
        for d in ('toolchain/', 'asm/editor', 'asm/legacy'):
            self.assertEqual([f for f in files if f.startswith(d)], [], d)

    def test_asm_is_only_the_assembler(self):
        self.assertEqual([f for f in tracked_files()
                          if f.startswith('asm/') and 'editor' in f], [])

    def test_no_live_file_names_an_old_path(self):
        found = []
        for path in tracked_files():
            if not is_text(path):
                continue
            with open(os.path.join(ROOT, path), errors='replace') as f:
                for n, line in enumerate(f, 1):
                    if OLD_PATH.search(line):
                        found.append(f'{path}:{n}: {line.strip()[:90]}')
        self.assertEqual(found, [])

    def test_includes_with_a_directory_resolve_from_the_root(self):
        # The assembler resolves .include against its working directory, which is the root for
        # the editor and the emulator's test programs (bare names go through include dirs).
        sources = glob.glob(os.path.join(ROOT, 'editor', '*.asm'))
        self.assertIn(os.path.join(ROOT, 'editor', 'editor.asm'), sources)
        sources += glob.glob(os.path.join(ROOT, 'emulator', 'tests', '*.asm'))
        missing = []
        for path in sources:
            with open(path) as f:
                for line in f:
                    m = re.match(r'\s*\.include\s+(\S+)', line)
                    if m and '/' in m.group(1) and not m.group(1).startswith('out/') \
                            and not os.path.exists(os.path.join(ROOT, m.group(1))):
                        missing.append(f'{os.path.relpath(path, ROOT)}: {m.group(1)}')
        self.assertEqual(missing, [])

    def test_editor_launchers_run_builds_the_tests_write(self):
        with open(os.path.join(ROOT, 'editor', 'tests', 'editor_tests.py')) as f:
            tests = f.read()
        launchers = glob.glob(os.path.join(ROOT, 'editor', 'bin', '*.sh'))
        self.assertGreaterEqual(len(launchers), 9)
        for path in launchers:
            with open(path) as f:
                text = f.read()
            name = os.path.basename(path)
            if 'michael' in name:  # these build the image themselves, from the root
                self.assertIn('cd "$(dirname "$0")/../.."', text, name)
                continue
            self.assertIn('ROOT="$(cd "$(dirname "$0")/../.." && pwd)"', text, name)
            self.assertIn('"$ROOT/emulator/emulator.out"', text, name)
            builds = re.findall(r'"\$ROOT/editor/out/(\w+\.out)"', text)
            self.assertEqual(len(builds), 1, name)
            self.assertTrue(f'"{builds[0]}"' in tests,
                            f'{name} runs {builds[0]}, which editor_tests.py does not write')

    def test_check_and_build_scripts_use_the_new_names(self):
        with open(os.path.join(ROOT, 'tools', 'check_all.sh')) as f:
            check = f.read()
        self.assertIn('suites=(firmware asm editor emulator prog8)', check)
        self.assertNotIn('asm1', check)
        with open(os.path.join(ROOT, 'tools', 'build_all.sh')) as f:
            self.assertIn('steps=(emulator asm editor)', f.read())


if __name__ == '__main__':
    unittest.main()
