"""lathe/src/fold.lth against lathe/host/fold.py: lathe/src/foldtest.lth runs each section of
lathe/tests/scripts/fold.txt, and the sections made below, and prints what the constant
arithmetic gives; main() does the same with fold.py, command for command, and the outputs,
error reports and exit statuses must match.

The sections made here sweep exact() over a grid of numbers from -32768 to 65535 for every
operator: the results that are numbers in one section, and a sample of those that are errors
(out of range, division by zero) one to a section, since an error ends the program."""
import shutil
import tempfile
import unittest

import src_support as support
import script_host as script
import env
import err
import fold
import kernel
import typetab

EDGES = [0, 1, 2, 7, 15, 16, 0x7F, 0x80, 0xFF, 0x100, 0x7FFF, 0x8000, 0xFF80, 0xFFF9, 0xFFFE,
         0xFFFF]
GRID = [-32768, -32767, -256, -255, -129, -128, -16, -2, -1, 0, 1, 2, 7, 15, 16, 127, 128, 255,
        256, 4096, 32767, 32768, 65534, 65535]
ERRORS_PER_OPERATOR = 6


def sweep_typed(op, t):
    for x in EDGES:
        for y in EDGES:
            a = typetab.narrow(x, t)
            b = typetab.narrow(y, t)
            if b == 0 and (op == fold.DIV or op == fold.REM):
                env.put_byte(ord('-'))
            else:
                script.show_word(fold.typed(op, t, a, b))


def sweep_compare(op):
    for x in EDGES:
        for y in EDGES:
            for k in range(4):
                script.show_bool(fold.compare(op, x, k & 1 != 0, y, k & 2 != 0))


def main():
    err.init()
    kernel.init()
    typetab.init()
    script.open_script(env._args[0])
    while script.next_line():
        c = script.command(b"exact typed compare sweep_typed sweep_compare ")
        if c == 0:
            op = script.small()
            a = script.number()
            a_negative = script.flag()
            b = script.number()
            a, negative = fold.exact(op, a, a_negative, b, script.flag())
            script.show_word(a)
            script.show_bool(negative)
        elif c == 1:
            op = script.small()
            t = script.small()
            a = script.number()
            script.show_word(fold.typed(op, t, a, script.number()))
        elif c == 2:
            op = script.small()
            a = script.number()
            a_negative = script.flag()
            b = script.number()
            script.show_bool(fold.compare(op, a, a_negative, b, script.flag()))
        elif c == 3:
            op = script.small()
            sweep_typed(op, script.small())
        elif c == 4:
            sweep_compare(script.small())
        script.end_line()
    env.exit(0)


def exact_line(op, a, b):
    return b'exact %d %d %d %d %d' % (op, a & 0xFFFF, a < 0, b & 0xFFFF, b < 0)


def grid_sections():
    """The grid: one section of every exact() that gives a number, and some that do not."""
    good = []
    bad = []
    for op in range(fold.ADD, fold.REM + 1):
        errors = []
        for a in GRID:
            for b in GRID if op not in (fold.SHL, fold.SHR) else range(0, 18):
                line = exact_line(op, a, b)
                status, _, _ = script.host_run(lambda: run_line(line), [])
                if status == 0:
                    good.append(line)
                else:
                    errors.append(line)
        step = max(1, len(errors) // ERRORS_PER_OPERATOR)
        bad += errors[::step][:ERRORS_PER_OPERATOR]
    found = [(b'grid', b'\n'.join(good) + b'\n')]
    for line in bad:
        found.append((b'grid error: ' + line, line + b'\n'))
    return found


def run_line(line):
    """exact() of one script line on the host, to find out whether it is an error."""
    err.init()
    script._lines = [line]
    script.next_line()
    script.command(b"exact ")
    op = script.small()
    a = script.number()
    a_negative = script.flag()
    b = script.number()
    fold.exact(op, a, a_negative, b, script.flag())


class FoldTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-src-fold-')
        cls.image = support.build_program('foldtest', cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_every_script(self):
        self.assertGreater(script.check_script(self, self.image, main, 'fold', self.dir,
                                               extra=grid_sections()), 40)


if __name__ == '__main__':
    unittest.main()
