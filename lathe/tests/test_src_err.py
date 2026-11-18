"""lathe/src/err.lth against lathe/host/err.py, through lathe/src/errtest.lth: every error
number, with and without a file and a place, must be reported in the same words."""
import io
import shutil
import tempfile
import unittest

import src_support as support
import lathec_support  # noqa: F401  (puts lathe/host on the path)
import env
import err


def host_report(number, file=None, line=0, col=0, place=False):
    """What err.py writes for error `number`, and the exit status; with `place`, the position is
    given as a place (err.position_at)."""
    env._err = io.BytesIO()
    err.init()
    if file is not None:
        start, _ = lathec_support.put_text(file.encode())
        err.set_file(start)
        if place:
            err.position(0, 0)
            err.position_at([line, col])
        else:
            err.position(line, col)
    try:
        err.fatal(number)
    except SystemExit as e:
        return e.code, env._err.getvalue()
    return None, env._err.getvalue()


class ErrTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-src-err-')
        cls.image = support.build_program('errtest', cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def check(self, number, file=None, line=0, col=0, place=False):
        args = [number]
        if file is not None:
            args += [file, line, col]
        if place:
            args += ['place']
        status, out, text, _ = support.run(self.image, args)
        self.assertEqual((status, text), host_report(number, file, line, col, place), args)
        self.assertEqual(out, b'')

    def test_every_error_number_in_a_file(self):
        for number in range(0, 170):
            self.check(number, 'dir/some.lth', number * 7, number * 380)

    def test_without_a_file_the_tool_is_named(self):
        for number in (1, 60, 99, 147, 150):
            self.check(number)

    def test_the_largest_place(self):
        self.check(20, 'x.lth', 65535, 65535)

    def test_a_place_kept_for_later(self):
        self.check(40, 'dir/some.lth', 1234, 56, place=True)
        self.check(40, 'x.lth', 65535, 65535, place=True)

    def test_line_0_is_nowhere(self):
        self.check(62, 'missing.lth', 0, 5)


if __name__ == '__main__':
    unittest.main()
