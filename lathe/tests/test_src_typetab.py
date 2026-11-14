"""lathe/src/typetab.lth against lathe/host/typetab.py: lathe/src/typetest.lth runs each section
of lathe/tests/scripts/typetab.txt and prints what the type table gives; main() below does the
same with typetab.py, command for command, and the outputs, error reports and exit statuses
must match."""
import shutil
import tempfile
import unittest

import src_support as support
import script_host as script
import env
import err
import kernel
import typetab

EDGES = [0, 1, 0x7E, 0x7F, 0x80, 0xFF, 0x100, 0x7FFF, 0x8000, 0xFF7F, 0xFF80, 0xFFFE, 0xFFFF,
         0x1234]


def show(t):
    script.show_byte(t)
    script.show_word(typetab.size(t))
    script.show_byte(typetab.form[t])
    for f in (typetab.is_pointer, typetab.is_array, typetab.is_rows, typetab.is_record,
              typetab.is_enum, typetab.is_func, typetab.is_recursive, typetab.is_column,
              typetab.is_number, typetab.is_untyped, typetab.is_signed):
        script.show_bool(f(t))
    env.put_byte(0x20)
    script.show_word(typetab.base(t))
    script.show_word(typetab.length(t))
    script.show_byte(typetab.innermost(t))
    script.show_word(typetab.limit(t))


def sweep(t):
    for e in EDGES:
        script.show_bool(typetab.number_fits(e, False, t))
        script.show_bool(typetab.number_fits(e, True, t))
        script.show_word(typetab.narrow(e, t))


def main():
    err.init()
    kernel.init()
    typetab.init()
    script.open_script(env._args[0])
    while script.next_line():
        c = script.command(b"init ptr arr decl grow rec prefix build show fits narrow sweep count fill ")
        if c == 0:
            typetab.init()
        elif c == 1:
            show(typetab.pointer_to(script.small()))
        elif c == 2:
            t = script.small()
            n = script.number()
            show(typetab.array_of(t, n, script.flag()))
        elif c == 3:
            t = script.small()
            show(typetab.declared(t, script.number()))
        elif c == 4:
            t = script.small()
            script.show_word(typetab.grow(t, script.number()))
            show(t)
        elif c == 5:
            t = script.small()
            typetab.make_recursive(t)
            show(t)
        elif c == 6:
            t = script.small()
            script.show_byte(typetab.prefix(t, script.number()))
        elif c == 7:
            t = script.small()
            show(typetab.build(t, script.small()))
        elif c == 8:
            while script.more():
                show(script.small())
        elif c == 9:
            n = script.number()
            t = script.small()
            script.show_bool(typetab.number_fits(n, t != 0, script.small()))
        elif c == 10:
            n = script.number()
            script.show_word(typetab.narrow(n, script.small()))
        elif c == 11:
            sweep(script.small())
        elif c == 12:
            script.show_byte(typetab.count)
            script.show_byte(typetab.prefix_count)
        elif c == 13:
            t = script.small()
            while True:
                t = typetab.pointer_to(t)
        script.end_line()
    env.exit(0)


class TypetabTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-src-typetab-')
        cls.image = support.build_program('typetest', cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_every_script(self):
        self.assertGreater(script.check_script(self, self.image, main, 'typetab', self.dir), 5)


if __name__ == '__main__':
    unittest.main()
