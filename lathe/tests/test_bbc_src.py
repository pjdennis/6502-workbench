"""The compiler's smallest test programs on the emulated BBC Model B+128, in the small build:
lextest, errtest, kerneltest and srctest built with lathe/src/compiler-bbc.env and run with *RUN
through the MOS (bbc_support), against their Python twins at the small build's capacities, as
test_src_lex.py, test_src_err.py, test_src_kernel.py and test_src_src.py compare them on the
default machine. On the BBC the error output is the output, so a twin is run with the two joined;
the status of an exit other than 0 comes back from the MOS error "Exit N". lextest is run over
its corner cases and every source of the project, as test_src_lex.py runs it."""
import concurrent.futures
import os
import shutil
import tempfile
import unittest

import src_support as support
import bbc_support as bbc
import env
import err
import lathec_support
import lextest_host
import test_src_kernel
import test_src_lex
import test_src_src

HAVE_TOOLS = os.path.isfile(support.EMULATOR) and os.path.isfile(support.build.COMPILER)


def in_parallel(function, items):
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        return list(pool.map(function, items))


class OnTheBBC:
    """A test program built for the BBC in setUpClass (a mixin: the classes below are the tests)."""
    NAME = None

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-bbc-src-')
        cls.image = bbc.build_program(cls.NAME, cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_it_fits_page_to_himem(self):
        """The file from $1900, and the variables, below $7C00 (HIMEM in mode 7)."""
        self.assertLessEqual(0x1900 + os.path.getsize(self.image), 0x7C00)
        with open(os.path.join(self.dir, 'work', self.NAME + '.map')) as fh:
            for line in fh:
                p = line.split()
                if len(p) >= 4 and len(p[0]) == 1:
                    self.assertLessEqual(int(p[1], 16) + int(p[2], 16), 0x7C00, line)


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class ErrOnTheBBC(OnTheBBC, unittest.TestCase):
    NAME = 'errtest'

    def host_report(self, number, file=None, line=0, col=0):
        lathec_support.fresh()
        env._out = env._err
        err.init()
        if file is not None:
            start, _ = lathec_support.put_text(file.encode())
            err.set_file(start)
            err.position(line, col)
        try:
            err.fatal(number)
        except SystemExit as e:
            return e.code, env._err.getvalue()
        return None, env._err.getvalue()

    def check_all(self, cases):
        runs = in_parallel(lambda args: bbc.run(self.image, args), cases)
        for args, (status, out, said, _) in zip(cases, runs):
            with self.subTest(args=args):
                self.assertEqual((status, out), self.host_report(*args))
                self.assertEqual(said, b'')

    def test_every_error_number_in_a_file(self):
        self.check_all([(n, 'dir/some.lth', n * 7, n * 380) for n in range(0, 170)])

    def test_without_a_file_the_tool_is_named(self):
        self.check_all([(n,) for n in (1, 60, 99, 147, 150)])

    def test_the_largest_place_and_line_0(self):
        self.check_all([(20, 'x.lth', 65535, 65535), (62, 'missing.lth', 0, 5)])


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class KernelOnTheBBC(OnTheBBC, unittest.TestCase):
    NAME = 'kerneltest'
    MODES = 'nfsdpu'

    def test_every_mode(self):
        """The normal run, a full name heap, a full symbol table, a name declared twice, a path
        too long, a name frozen twice: each with its output file. Every mode ends with an error
        here, the normal run too: it declares more names than the small build's name heap
        holds (error 70), on the BBC and in the twin alike."""
        given = os.path.join(self.dir, 'input.txt')
        with open(given, 'wb') as fh:
            fh.write(bytes(range(256)) * 3 + b'tail')
        runs = in_parallel(lambda m: bbc.run(self.image, [given, os.path.join(self.dir, 'made-%sL' % m), m],
                                              paths=(0, 1)), self.MODES)
        for mode, (status, out, said, _) in zip(self.MODES, runs):
            with self.subTest(mode=mode):
                made = os.path.join(self.dir, 'made-%s' % mode)
                host = bbc.host_run(test_src_kernel.main, ['input.txt', 'made-%sP' % mode, mode], self.dir)
                self.assertEqual((status, out), host)
                self.assertEqual(said, b'')
                self.assertEqual(os.path.exists(made + 'L'), os.path.exists(made + 'P'))
                if os.path.exists(made + 'P'):
                    with open(made + 'L', 'rb') as a, open(made + 'P', 'rb') as b:
                        self.assertEqual(a.read(), b.read())
                self.assertEqual(status, 1)


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class SrcOnTheBBC(OnTheBBC, unittest.TestCase):
    NAME = 'srctest'
    CASES = [(b'line one\nline two\n\n\tthree\r\nfour', 'n', 0), (b'x\ny\n' * 100, 'n', 0),
             (b'ab', 'n', 0), (b'', 'n', 0), (b'0123456789', 'o', 1), (b'abc\ndefghijkl', 'e', 1),
             (None, 'n', 1)]

    def test_every_case(self):
        """As test_src_src.py's, a missing file (None) among them."""
        paths = []
        for n, (data, mode, _) in enumerate(self.CASES):
            path = os.path.join(self.dir, 'input%d.txt' % n)
            if data is not None:
                with open(path, 'wb') as fh:
                    fh.write(data)
            paths.append(path)
        runs = in_parallel(lambda c: bbc.run(self.image, [c[0], c[1][1]], paths=(0,)),
                           list(zip(paths, self.CASES)))
        for path, (data, mode, want), (status, out, said, _) in zip(paths, self.CASES, runs):
            with self.subTest(data=data, mode=mode):
                self.assertEqual((status, out), bbc.host_run(test_src_src.main,
                                                             [os.path.basename(path), mode], self.dir))
                self.assertEqual((status, said), (want, b''))


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class LexOnTheBBC(OnTheBBC, unittest.TestCase):
    NAME = 'lextest'

    def compare(self, paths):
        """lextest over each file on the BBC (by its base name, in a directory of its own) and
        the twin over the same; returns the number that ended with an error."""
        runs = in_parallel(lambda p: bbc.run(self.image, [p], paths=(0,)), paths)
        errors = 0
        for path, (status, out, said, _) in zip(paths, runs):
            with self.subTest(path=os.path.relpath(path, support.ROOT)):
                work = tempfile.mkdtemp(prefix='lathe-bbc-lex-')
                try:
                    shutil.copyfile(path, os.path.join(work, os.path.basename(path)))
                    host = bbc.host_run(lextest_host.main, [os.path.basename(path)], work)
                finally:
                    shutil.rmtree(work, ignore_errors=True)
                self.assertEqual(status, host[0])
                self.assertEqual(out, host[1])
                self.assertEqual(said, b'')
                errors += status != 0
        return errors

    def test_the_corners_of_the_lexical_rules(self):
        paths = []
        for name, text in sorted(test_src_lex.CORNERS.items()):
            path = os.path.join(self.dir, name + '.lth')
            with open(path, 'wb') as fh:
                fh.write(text)
            paths.append(path)
        self.assertGreater(self.compare(paths), 20)

    def test_sources_of_the_project(self):
        paths = [os.path.join(support.ROOT, p) for p in test_src_lex.lathe_sources()]
        self.assertGreater(len(paths), 300)
        self.compare(paths)

    def test_a_missing_file_and_no_argument(self):
        status, out, said, _ = bbc.run(self.image, [os.path.join(self.dir, 'none.lth')], paths=(0,))
        self.assertEqual((status, out), bbc.host_run(lextest_host.main, ['none.lth'], self.dir))
        self.assertEqual((status, said), (1, b''))
        status, out, said, _ = bbc.run(self.image, [])
        self.assertEqual((status, out), bbc.host_run(lextest_host.main, [], self.dir))


if __name__ == '__main__':
    unittest.main()
