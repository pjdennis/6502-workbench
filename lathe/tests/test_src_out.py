"""lathe/src/out.lth against lathe/host/out.py: lathe/src/outtest.lth runs each section of
lathe/tests/scripts/out.txt, which write an object file record by record (with functions
finished by FBUF), and main() does the same with out.py, command for command. What they
print, their error reports and exit statuses, and the object files must be identical."""
import shutil
import tempfile
import unittest

import src_support as support
import script_host as script
import env
import err
import fbuf
import kernel
import out

COMMANDS = (b"init open module import sym sym3 var data bytes table tset tfix tend call class param "
            b"member func slot fend ksym end fbegin op fix finish ")


def main():
    err.init()
    kernel.init()
    out.init()
    fbuf.begin()
    script.open_script(env._args[0])
    obj = kernel.keep_argument(1)
    while script.next_line():
        c = script.command(COMMANDS)
        if c == 0:
            out.init()
        elif c == 1:
            script.show_bool(out.open(obj))
        elif c == 2:
            a = script.small()
            out.begin_module(a, script.name())
        elif c == 3:
            out.imported(script.name())
        elif c == 4:
            a = script.small()
            d = script.name()
            script.show_word(out.symbol(a, d, 0, script.name()))
        elif c == 5:
            a = script.small()
            d = script.name()
            e = script.name()
            script.show_word(out.symbol(a, d, e, script.name()))
        elif c == 6:
            d = script.number()
            e = script.number()
            a = script.small()
            out.variable(d, e, a, script.small())
        elif c == 7:
            d = script.number()
            out.data(d, script.number())
        elif c == 8:
            while script.more():
                out.data_byte(script.small())
        elif c == 9:
            out.table_begin(script.number())
        elif c == 10:
            d = script.number()
            out.table[d] = script.small()
        elif c == 11:
            d = script.number()
            a = script.small()
            e = script.number()
            b = script.small()
            out.table_fix(d, a, e, b, script.number())
        elif c == 12:
            d = script.number()
            out.table_end(d, script.number())
        elif c == 13:
            d = script.number()
            a = script.small()
            out.call(d, a, script.number())
        elif c == 14:
            d = script.number()
            a = script.small()
            out.pointer_class(d, a, script.small())
        elif c == 15:
            out.class_parameter(script.number())
        elif c == 16:
            d = script.number()
            out.member(d, script.number())
        elif c == 17:
            d = script.number()
            out.function_begin(d, script.small())
        elif c == 18:
            d = script.number()
            a = script.small()
            b = script.small()
            c = script.small()
            out.slot(d, a, b, c, script.name())
        elif c == 19:
            out.function_end()
        elif c == 20:
            a = script.small()
            b = script.small()
            d = script.name()
            s = kernel.sym_add(a, d, b)
            kernel.sym_obj[s] = script.number()
            kernel.sym_weight[s] = script.small()
            script.show_word(s)
        elif c == 21:
            out.end_module()
        elif c == 22:
            fbuf.begin()
        elif c == 23:
            fbuf.op(script.small())
        elif c == 24:
            a = script.small()
            b = script.small()
            d = script.number()
            c = script.small()
            fbuf.op_fix(a, b, d, c, script.number())
        elif c == 25:
            d = script.number()
            fbuf.finish(d, script.small())
        script.end_line()
    env.exit(0)


class OutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-src-out-')
        cls.image = support.build_program('outtest', cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_every_script(self):
        self.assertGreater(script.check_script(self, self.image, main, 'out', self.dir, outputs=1), 3)


if __name__ == '__main__':
    unittest.main()
