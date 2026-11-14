"""Snapshot and end-to-end cases (lathe/host/README.md, "Tests").

    cases/snap/NAME.lth   lo2asm (module mode) of the compiled module equals NAME.expected.asm.
                          LATHE_UPDATE=1 rewrites the expected files instead; review the diff.
    cases/e2e/NAME.lth    The program's output on the emulator equals NAME.expected.out (and it
                          exits with status 0). Once lathe/host/link.py exists it is built both
                          ways, linker and assembler path, and the two images must be identical.
    cases/linkerr/NAME.lth
                          The first line is `; link error N`: the program compiles, and linking it
                          fails with that error, which build.py reports. Each later line before
                          `module` that starts with `; says ` gives text the message must hold.
    cases/e2e-michael/NAME.lth, cases/e2e-wendy2/NAME.lth
                          The same on a board (lathe/docs/boards.md): built with lathe/env/BOARD.env
                          both ways, run through build.run_program, and NAME.expected.out holds
                          the text the LCD shows at the STP, one line per row with trailing spaces
                          removed.
    cases/e2e-wendy2disk/NAME.lth
                          On Wendy 2 with --disk (lathe/env/wendy2disk.env): run on a directory
                          that holds a copy of NAME.disk/ (its input files; the arguments in
                          `args`, one a line). NAME.expected.out holds the file `out` it writes,
                          NAME.expected.err (if there is one; else nothing) the file `errors`; a
                          line `; status N` before `module` gives the status it must leave in the
                          file `status` (default 0), and each line `; same IN OUT` an output file
                          OUT that must hold exactly the bytes of the input IN.

A case can import modules that lie beside it; one called lib*.lth, or whose first line starts
with `; imported by`, is only that, and not a case. A comment line `; defines NAME NAME=NUMBER ...` before the `module` line gives the
compiler those defines (build.py --define), for `#if`. Each case is its own test method (test_snap_NAME, test_e2e_NAME, test_e2e_michael_NAME,
...). Everything is skipped while
lathe/host/lathec.py does not exist. Error cases (cases/err/) are tested with the compiler.
"""
import glob
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'lathe', 'host', 'driver'))

import build  # noqa: E402
import lo  # noqa: E402
import lo2asm  # noqa: E402

CASES = os.path.join(HERE, 'cases')
UPDATE = os.environ.get('LATHE_UPDATE') == '1'
NO_COMPILER = f'{os.path.relpath(build.COMPILER, ROOT)} does not exist yet: snapshot and end-to-end cases skipped'


def cases(kind):
    """The cases of a kind. A module whose name starts with `lib`, or whose first line starts
    with `; imported by`, is not one: it is there for cases to import."""
    return sorted(p for p in glob.glob(os.path.join(CASES, kind, '*.lth'))
                  if not os.path.basename(p).startswith('lib') and not _read(p).startswith('; imported by'))


def headers(path, word):
    """The words of each of a case's `; WORD ...` lines before `module`, one list per line."""
    found = []
    with open(path) as fh:
        for line in fh:
            if line.startswith('module'):
                break
            if line.startswith(f'; {word} '):
                found.append(line[len(f'; {word} '):].split())
    return found


def defines(path):
    """The defines a case asks for: the words of its `; defines` lines before `module`."""
    return [w for words in headers(path, 'defines') for w in words]


def _name(path):
    return os.path.splitext(os.path.basename(path))[0]


def _read(path, mode='r'):
    with open(path, mode) as fh:
        return fh.read()


@unittest.skipUnless(os.path.isfile(build.COMPILER), NO_COMPILER)
class TestCases(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lathe-case-')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def check_snap(self, source):
        expected = os.path.splitext(source)[0] + '.expected.asm'
        objects = build.compile_all(build.module_order(source), self.dir,
                                    build.compiler_options(None, defines(source)))
        text = lo2asm.render_module(lo.load(objects[-1]), [lo.load(p) for p in objects[:-1]])
        if UPDATE:
            with open(expected, 'w') as fh:
                fh.write(text)
            return
        if not os.path.isfile(expected):
            self.fail(f'{os.path.relpath(expected, ROOT)} is missing: record it with LATHE_UPDATE=1 '
                      f'and review it')
        self.assertEqual(text, _read(expected), f'{os.path.relpath(source, ROOT)}: lo2asm output '
                         'differs from the expected file (LATHE_UPDATE=1 rewrites it)')

    def check_e2e(self, source, env='host'):
        expected = os.path.splitext(source)[0] + '.expected.out'
        image = os.path.join(self.dir, 'default.bin')
        build.build(source, image, env, keep=os.path.join(self.dir, 'default'), defines=defines(source))
        if env in DISK:
            status, out, err = self.run_on_disk(source, image, env)
        else:
            status, out, err = build.run_program(image, env)
        self.assertEqual(out, _read(expected, 'rb'), f'{os.path.relpath(source, ROOT)}: output')
        want = int(headers(source, 'status')[0][0]) if headers(source, 'status') else 0
        self.assertEqual(status, want, f'exit status; error output: {err!r}')
        if os.path.isfile(build.LINKER):
            other = os.path.join(self.dir, 'asm.bin')
            build.build(source, other, env, use_asm=True, keep=os.path.join(self.dir, 'asm'),
                        defines=defines(source))
            self.assertTrue(_read(image, 'rb') == _read(other, 'rb'),
                            'the linker and the assembler path give different images '
                            f'(rebuild with build.py --keep DIR, with and without --asm, to compare)')


    def run_on_disk(self, source, image, env):
        """Runs a case on a disk board: NAME.disk/ holds its input files (its arguments in
        `args`), copied to the directory it runs on. Afterwards the error output (the file
        `errors`) must equal NAME.expected.err, or be empty if there is none, and for each line
        `; same IN OUT` the file OUT it wrote must hold exactly the bytes of the input IN."""
        base = os.path.splitext(source)[0]
        disk = os.path.join(self.dir, 'disk')
        inputs = base + '.disk'
        if os.path.isdir(inputs):
            shutil.copytree(inputs, disk)
        else:
            os.makedirs(disk)
        status, out, err = build.run_program(image, env, disk=disk)
        want_err = _read(base + '.expected.err', 'rb') if os.path.isfile(base + '.expected.err') else b''
        self.assertEqual(err, want_err, f'{os.path.relpath(source, ROOT)}: error output')
        for words in headers(source, 'same'):
            got = os.path.join(disk, words[1])
            self.assertTrue(os.path.isfile(got), f'{words[1]} was not written')
            self.assertTrue(_read(got, 'rb') == _read(os.path.join(inputs, words[0]), 'rb'),
                            f'{words[1]} differs from {words[0]}')
        return status, out, err

    def check_link_error(self, source):
        with open(source) as fh:
            head = fh.readline().split()
            says = []
            for line in fh:
                if line.startswith('module'):
                    break
                if line.startswith('; says '):
                    says.append(line[len('; says '):].rstrip('\n'))
        self.assertEqual(head[:3], [';', 'link', 'error'], f'{source}: the first line must be `; link error N`')
        with self.assertRaises(build.BuildError) as caught:
            build.build(source, os.path.join(self.dir, 'x.bin'), keep=os.path.join(self.dir, 'w'))
        message = str(caught.exception)
        self.assertTrue(message.startswith('linking failed'), message)
        self.assertIn(f'\nlink error {head[3]}: ', message)
        for text in says:
            self.assertIn(text, message)


# The end-to-end kinds: case directory -> environment (a board's, for e2e-BOARD).
E2E = {'e2e': 'host', 'e2e-michael': 'michael', 'e2e-wendy2': 'wendy2',
       'e2e-wendy2disk': 'wendy2disk'}
DISK = {'wendy2disk'}       # the boards whose output is in files (boards.py, `disk`)


def _add(kind, check):
    for path in cases(kind):
        def test(self, path=path):
            check(self, path)
        test.__doc__ = os.path.relpath(path, ROOT)
        setattr(TestCases, f'test_{kind.replace("-", "_")}_{_name(path)}', test)


_add('snap', TestCases.check_snap)
_add('linkerr', TestCases.check_link_error)
for _kind, _env in E2E.items():
    _add(_kind, lambda self, path, env=_env: TestCases.check_e2e(self, path, env))


@unittest.skipUnless(os.path.isfile(build.COMPILER), NO_COMPILER)
class TestDefines(unittest.TestCase):
    def test_other_defines_choose_other_parts(self):
        """cases/e2e/conditionals.lth built with defines other than those it names."""
        work = tempfile.mkdtemp(prefix='lathe-case-')
        self.addCleanup(shutil.rmtree, work, True)
        source = os.path.join(CASES, 'e2e', 'conditionals.lth')
        image = os.path.join(work, 'other.bin')
        build.build(source, image, keep=os.path.join(work, 'other'), defines=['FAST=0', 'LEVEL=1'])
        self.assertEqual(build.run_program(image), (0, b'LS6?\n', b''))


class TestHarness(unittest.TestCase):
    """Runs without the compiler: the cases are well formed."""

    def test_e2e_cases_have_expected_output(self):
        for kind in E2E:
            for path in cases(kind):
                self.assertTrue(os.path.isfile(os.path.splitext(path)[0] + '.expected.out'), path)

    def test_every_board_has_its_environment(self):
        for env in E2E.values():
            self.assertTrue(os.path.isfile(build.env_path(env)), env)

    def test_there_is_a_case(self):
        self.assertTrue(cases('e2e'), 'no end-to-end cases in lathe/tests/cases/e2e')


if __name__ == '__main__':
    unittest.main()
