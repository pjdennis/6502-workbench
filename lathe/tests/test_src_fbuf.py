"""lathe/src/fbuf.lth against lathe/host/fbuf.py: lathe/src/fbuftest.lth runs each section of
lathe/tests/scripts/fbuf.txt, which build functions from instructions, labels, branches and
fix-ups and finish them, and prints the code, fix-ups and weights; main() does the same with
fbuf.py, command for command, and the outputs, error reports and exit statuses must match."""
import shutil
import tempfile
import unittest

import src_support as support
import script_host as script
import env
import err
import fbuf
import kernel

OP_NOP = 0xEA
OP_LDA = 0xAD


COMMANDS = (b"begin op opb opw fix label labels place arrive branch jump call join same written "
            b"keep tail runs used finish nops fixes ")


def main():
    err.init()
    kernel.init()
    fbuf.begin()
    script.open_script(env._args[0])
    while script.next_line():
        c = script.command(COMMANDS)
        if c == 0:
            fbuf.begin()
        elif c == 1:
            fbuf.op(script.small())
        elif c == 2:
            a = script.small()
            fbuf.op_byte(a, script.small())
        elif c == 3:
            a = script.small()
            fbuf.op_word(a, script.number())
        elif c == 4:
            a = script.small()
            b = script.small()
            d = script.number()
            c = script.small()
            fbuf.op_fix(a, b, d, c, script.number())
        elif c == 5:
            script.show_byte(fbuf.new_label())
        elif c == 6:
            for _ in range(script.number()):
                a = fbuf.new_label()
            script.show_byte(a)
        elif c == 7:
            fbuf.place(script.small())
        elif c == 8:
            script.show_bool(fbuf.arrive(script.small()))
        elif c == 9:
            a = script.small()
            fbuf.branch(a, script.small())
        elif c == 10:
            fbuf.jump(script.small())
        elif c == 11:
            fbuf.call_label(script.small())
        elif c == 12:
            a = script.small()
            fbuf.join(a, script.small())
        elif c == 13:
            script.show_byte(fbuf.same(script.small()))
        elif c == 14:
            fbuf.as_written(script.flag())
        elif c == 15:
            fbuf.keep_as_written()
        elif c == 16:
            script.show_bool(fbuf.tail_call())
        elif c == 17:
            script.show_bool(fbuf.runs_on())
        elif c == 18:
            script.show_word(fbuf.used)
        elif c == 19:
            d = script.number()
            fbuf.finish(d, script.small())
            script.show_finished()
        elif c == 20:
            for _ in range(script.number()):
                fbuf.op(OP_NOP)
        elif c == 21:
            for n in range(script.number()):
                fbuf.op_fix(OP_LDA, fbuf.FIX_ADDRESS, 0, fbuf.NO_SLOT, n)
        script.end_line()
    env.exit(0)


class FbufTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-src-fbuf-')
        cls.image = support.build_program('fbuftest', cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_every_script(self):
        self.assertGreater(script.check_script(self, self.image, main, 'fbuf', self.dir), 5)


if __name__ == '__main__':
    unittest.main()
