"""The end-to-end corpus, lathe/tests/cases/e2e/, on the emulated BBC Model B+128.

Each case is built with lathe/env/bbc.env, both ways (the linker, and the assembler path, which
must give the same file), and run with *RUN through the MOS with --bbc-strict (boards.run_mos).
Its `import host` is lathe/rt/bbc/host.lth, host.lth's interface over lathe/rt/bbc.lth. The
output, with the BBC's line end LF CR given back as LF, must equal NAME.expected.out, and the
status must be 0, as on the default machine (test_cases.py).

The cases that do not fit the machine are listed in NOT_ON_THE_BBC with the reason, and the test
checks that the reason still holds."""
import concurrent.futures
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'host', 'driver'))

import build  # noqa: E402
import boards  # noqa: E402
from test_cases import cases, defines, _name, _read, ROOT  # noqa: E402

# Case -> why it cannot run on the BBC. Both store to fixed addresses that are the default
# machine's RAM: on the BBC they are the MOS's.
NOT_ON_THE_BBC = {
    'asm_pointer': 'stores at $C800 and $C801, which are the MOS ROM on the BBC (the stores are lost)',
    'state': 'has variables at $FA (MOS zero page: --bbc-strict stops it) and $EFF8 (the MOS ROM)',
}


def build_and_run(source, work):
    """Build source both ways and run the linker's image: (status, output, error output, the
    two images are the same). An exception is given back as it is, for the test to raise."""
    try:
        os.makedirs(work)
        image = os.path.join(work, 'case.bin')
        build.build(source, image, 'bbc', keep=os.path.join(work, 'link'), defines=defines(source))
        status, out, err = build.run_program(image, 'bbc')
        other = os.path.join(work, 'asm.bin')
        build.build(source, other, 'bbc', use_asm=True, keep=os.path.join(work, 'asm'),
                    defines=defines(source))
        return status, out, err, _read(image, 'rb') == _read(other, 'rb')
    except Exception as e:      # noqa: BLE001 -- raised again in the test of the case
        return e


@unittest.skipUnless(os.path.isfile(build.COMPILER) and os.path.isfile(boards.EMULATOR),
                     'compiler or emulator missing')
class BBCCases(unittest.TestCase):
    """The cases are built and run together, in parallel, before the tests look at them."""
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-case-')
        paths = [p for p in cases('e2e') if _name(p) not in NOT_ON_THE_BBC]
        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
            done = pool.map(lambda p: build_and_run(p, os.path.join(cls.dir, _name(p))), paths)
            cls.results = dict(zip(paths, done))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix='lathe-bbc-case-')
        self.addCleanup(shutil.rmtree, self.work, True)

    def check(self, source):
        result = self.results[source]
        if isinstance(result, Exception):
            raise result
        status, out, err, same = result
        expected = _read(os.path.splitext(source)[0] + '.expected.out', 'rb')
        self.assertEqual(out, expected, f'{os.path.relpath(source, ROOT)}: output on the BBC')
        self.assertEqual((status, err), (0, b''))
        self.assertTrue(same, 'the linker and the assembler path give different images')

    def test_the_cases_left_out_still_cannot_run(self):
        names = {_name(p): p for p in cases('e2e')}
        for name in NOT_ON_THE_BBC:
            with self.subTest(case=name):
                image = os.path.join(self.work, name + '.bin')
                build.build(names[name], image, 'bbc', keep=os.path.join(self.work, name))
                try:
                    status, out, _ = build.run_program(image, 'bbc')
                except boards.RunError as e:
                    self.assertIn('strict', str(e))
                    continue
                self.assertNotEqual(out, _read(os.path.splitext(names[name])[0] + '.expected.out', 'rb'))

    def test_most_cases_run(self):
        self.assertGreater(len(cases('e2e')) - len(NOT_ON_THE_BBC), 60)


for _path in cases('e2e'):
    if _name(_path) in NOT_ON_THE_BBC:
        continue

    def _test(self, path=_path):
        self.check(path)
    _test.__doc__ = os.path.relpath(_path, ROOT)
    setattr(BBCCases, f'test_bbc_{_name(_path)}', _test)


if __name__ == '__main__':
    unittest.main()
