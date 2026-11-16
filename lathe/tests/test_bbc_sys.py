"""lathe/src/sys.lth over lathe/rt/bbc.lth, the BBC's MOS (`define PORTS 2`, lathe/env/bbc.env).

- Choice: each `#if PORTS` of sys.lth is the `#else` of an `#if PORTS == 2` whose first part is
  the `#if PORTS` part with bbc for disk (but where the other machines use the table of open
  files, which the BBC has not: lathe/docs/bbc.md, "Step 4"), so that PORTS 0 and 1 compile what they did before the
  BBC was added (the object files are the same: checked once by hand when this was written, and
  here by the structure).
- Every environment with PORTS 2 is a BBC's, and the others keep 0 or 1.
- lathe/src/copytest.lth built with bbc.env and run on the BBC gives the cases of test_disk.py's
  SysOverDisk, with the error output in the output and the statuses as MOS errors.
"""
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'lathe', 'host', 'driver'))
sys.path.insert(0, HERE)

import boards  # noqa: E402
import build  # noqa: E402
from test_disk import calls, code_of, signatures  # noqa: E402

RT = os.path.join(ROOT, 'lathe', 'rt')
SRC = os.path.join(ROOT, 'lathe', 'src')
TABLE = re.compile(r'\b(files|MAX_FILES|keep)\b')
THREE = re.compile(r'^#if PORTS == 2\n(.*?)^#else\n^#if PORTS\n(.*?)^#else\n(.*?)^#end\n^#end\n', re.M | re.S)


def _read(path, mode='r'):
    with open(path, mode) as fh:
        return fh.read()


class Choice(unittest.TestCase):
    def test_bbc_has_what_sys_uses_of_disk(self):
        code = code_of(os.path.join(SRC, 'sys.lth'))
        bbc = signatures(os.path.join(RT, 'bbc.lth'))
        disk = signatures(os.path.join(RT, 'disk.lth'))
        used = sorted(set(calls(code, 'bbc')))
        self.assertEqual(used, sorted(set(calls(code, 'disk'))))
        for name in used:
            self.assertEqual(bbc[name], disk[name], name)

    def test_each_choice_has_three_parts(self):
        code = code_of(os.path.join(SRC, 'sys.lth'))
        # The import lists are what import_lists.py writes for each module: not the same text.
        code = re.sub(r'^(import \w+) \([^)]*\)', r'\1', code, flags=re.M)
        found = THREE.findall(code)
        self.assertEqual(len(found), len(re.findall(r'^#if PORTS\n', code, re.M)))
        self.assertGreater(len(found), 10)
        own = 0
        for bbc, disk, host in found:
            self.assertEqual(disk.replace('disk', 'host'), host)
            if TABLE.search(disk):
                # The table of open files: the BBC has none (the MOS keeps the handles and
                # bbc.exit closes every file), so its part is its own and names none of it.
                self.assertIsNone(TABLE.search(bbc), bbc)
                own += 1
            else:
                self.assertEqual(bbc, re.sub(r'\bdisk\b', 'bbc', disk))
        self.assertEqual(own, 6)    # the table, keep, open_in, open_out, close and exit
        outside = THREE.sub('', code)
        self.assertEqual(calls(outside, 'bbc') + calls(outside, 'disk') + calls(outside, 'host'), [])

    def test_bbc_has_no_initial_values(self):
        """sys.lth imports bbc in every build, and a module's $init is linked whether or not
        anything else of it is: bbc.lth must have none, so that other builds stay as they were."""
        work = tempfile.mkdtemp(prefix='lathe-bbc-init-')
        self.addCleanup(shutil.rmtree, work, True)
        objects = build.compile_all([('bbcfs', os.path.join(RT, 'bbcfs.lth')),
                                     ('bbc', os.path.join(RT, 'bbc.lth'))], work)
        self.assertNotIn(b'bbcfs.$init', _read(objects[0], 'rb'))     # which bbc.lth imports
        self.assertNotIn(b'bbc.$init', _read(objects[1], 'rb'))
        objects = build.compile_all([('disk', os.path.join(RT, 'disk.lth'))], work)
        self.assertIn(b'disk.$init', _read(objects[0], 'rb'))       # the test can see one

    def test_every_environment_says_which(self):
        envs = [os.path.join(ROOT, 'lathe', 'env', f) for f in os.listdir(os.path.join(ROOT, 'lathe', 'env'))]
        envs += [os.path.join(SRC, f) for f in os.listdir(SRC) if f.endswith('.env')]
        for path in envs:
            defines = dict(build.mapenv.read_env(path).defines)
            board = boards.board_for(path)
            if board is not None and board.mos:
                self.assertEqual(defines.get('PORTS'), 2, path)
            else:
                self.assertIn(defines.get('PORTS', 0), (0, 1), path)


@unittest.skipUnless(os.path.isfile(boards.EMULATOR) and os.path.isfile(build.COMPILER),
                     'emulator or compiler missing')
class SysOverBBC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.mkdtemp(prefix='lathe-bbc-sys-')
        cls.image = os.path.join(cls.work, 'copytest.bin')
        build.build(os.path.join(SRC, 'copytest.lth'), cls.image, 'bbc',
                    keep=os.path.join(cls.work, 'build'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def setUp(self):
        self.disk = tempfile.mkdtemp(prefix='lathe-bbc-run-')
        self.addCleanup(shutil.rmtree, self.disk, True)

    def run_with(self, args):
        return build.run_program(self.image, 'bbc', args, disk=self.disk)

    def test_the_build_uses_bbc(self):
        with open(os.path.join(self.work, 'build', 'copytest.map')) as fh:
            kept = [line.split()[3] for line in fh if line.startswith('F ')]
        self.assertIn('bbc.read', kept)
        self.assertNotIn('disk.read', kept)
        self.assertNotIn('bbc.$init', kept)

    def test_a_file_is_copied_byte_for_byte(self):
        data = bytes(range(256)) * 5 + b'end'
        with open(os.path.join(self.disk, 'in.bin'), 'wb') as fh:
            fh.write(data)
        self.assertEqual(self.run_with(['in.bin', 'out.bin']), (0, b'2 6 7\n!', b''))
        self.assertEqual(_read(os.path.join(self.disk, 'out.bin'), 'rb'), data)

    def test_an_empty_file_copies_to_an_empty_file(self):
        open(os.path.join(self.disk, 'e'), 'wb').close()
        self.assertEqual(self.run_with(['e', 'f'])[0], 0)
        self.assertEqual(os.path.getsize(os.path.join(self.disk, 'f')), 0)

    def test_arguments_are_counted_and_copied(self):
        self.assertEqual(self.run_with(['a', 'bcd', 'ef']), (2, b'3 1 3 2\n', b''))   # no file a

    def test_the_linkers_44_arguments_are_all_given(self):
        args = ['x%d' % i for i in range(44)]
        status, out, _ = self.run_with(args)
        self.assertEqual((status, out), (2, bytes([48 + 44]) + b' 2' * 10 + b' 3' * 34 + b'\n'))

    def test_an_output_that_cannot_be_created_is_status_3(self):
        open(os.path.join(self.disk, 'g'), 'wb').close()
        self.assertEqual(self.run_with(['g', 'no/such'])[0], 3)


if __name__ == '__main__':
    unittest.main()
