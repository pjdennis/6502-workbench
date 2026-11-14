"""out.py: the records of an object file, as docs/object-format.md defines them."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lathec_support as support  # noqa: E402
import err  # noqa: E402
import fbuf  # noqa: E402
import kernel  # noqa: E402
import out  # noqa: E402

END, MOD, IMP, SYM, FUNC, SLOT, CALL, FIX, CODE, ENDF = 0, 1, 2, 3, 7, 8, 9, 10, 11, 12


def name(text):
    kernel.name_begin()
    for ch in text:
        kernel.name_add(ch)
    return kernel.name_end()


class OutTest(unittest.TestCase):
    def setUp(self):
        support.fresh()
        err.init()
        kernel.init()
        out.init()
        fbuf.begin()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'm.lo')
        pointer, _ = support.put_text(self.path.encode())
        self.assertTrue(out.open(pointer))

    def written(self):
        out.end_module()
        return support.records(self.path)

    def test_a_module_with_nothing_in_it(self):
        out.begin_module(0, name(b'host'))
        self.assertEqual(self.written(), [(MOD, b'\x01\x00\x04host'), (END, b'')])

    def test_the_cpu_is_in_the_module_record(self):
        out.begin_module(1, name(b'm'))
        self.assertEqual(self.written()[0], (MOD, b'\x01\x01\x01m'))

    def test_an_import_names_the_module(self):
        out.begin_module(0, name(b'hello'))
        out.imported(name(b'host'))
        self.assertEqual(self.written()[1], (IMP, b'\x04host'))

    def test_symbols_are_numbered_from_zero_and_named_module_dot_name(self):
        out.begin_module(0, name(b'hello'))
        first = out.symbol(out.SYM_FUNCTION, name(b'hello'), 0, name(b'main'))
        second = out.symbol(out.SYM_VARIABLE, name(b'util'), 0, name(b'count'))
        self.assertEqual((first, second), (0, 1))
        self.assertEqual(self.written()[1:3],
                         [(SYM, b'\x01\x0ahello.main'), (SYM, b'\x02\x0autil.count')])

    def test_a_static_variable_is_named_module_dot_function_dot_name(self):
        out.begin_module(0, name(b'm'))
        self.assertEqual(out.symbol(out.SYM_VARIABLE, name(b'm'), name(b'f'), name(b'seen')), 0)
        self.assertEqual(self.written()[1], (SYM, b'\x02\x08m.f.seen'))

    def test_a_variable_record_has_size_class_weight_and_no_flags(self):
        out.begin_module(0, name(b'm'))
        v = out.symbol(out.SYM_VARIABLE, name(b'm'), 0, name(b'count'))
        out.variable(v, 2, 0, 37)
        self.assertEqual(self.written()[2], (4, b'\x00\x00\x02\x00\x00\x25\x00'))

    def test_a_function_is_its_records_in_the_order_the_linker_reads_them(self):
        out.begin_module(0, name(b'm'))
        f = out.symbol(out.SYM_FUNCTION, name(b'm'), 0, name(b'f'))
        g = out.symbol(out.SYM_FUNCTION, name(b'm'), 0, name(b'g'))
        fbuf.op_fix(0x20, fbuf.FIX_ADDRESS, f, fbuf.NO_SLOT, 0)
        fbuf.op_fix(0x8D, fbuf.FIX_ADDRESS, g, 0, 1)
        fbuf.op(0x60)
        fbuf.finish(g, 0)
        out.call(f, 0, out.NO_OUTER)
        out.function_begin(g, out.FUNC_EXPORTED)
        out.slot(2, 1, 9, 0, name(b'p'))
        out.slot(1, 2, 0, 1, name(b'i'))
        out.function_end()
        self.assertEqual(self.written()[3:], [
            (FUNC, b'\x01\x00\x04'),
            (SLOT, b'\x02\x00\x01\x09\x00\x01p'),
            (SLOT, b'\x01\x00\x02\x00\x01\x01i'),
            (CALL, b'\x00\x00\x00\xff\xff'),
            (FIX, b'\x01\x00\x01\x00\x00\xff\x00\x00' b'\x04\x00\x01\x01\x00\x00\x01\x00'),
            (CODE, b'\x20\x00\x00\x8d\x00\x00\x60'),
            (ENDF, b''),
            (END, b''),
        ])

    def test_a_function_with_no_calls_or_fix_ups_still_has_fix_and_code_records(self):
        out.begin_module(0, name(b'm'))
        f = out.symbol(out.SYM_FUNCTION, name(b'm'), 0, name(b'f'))
        fbuf.op(0x60)
        fbuf.finish(f, 0)
        out.function_begin(f, 0)
        out.function_end()
        self.assertEqual(self.written()[2:],
                         [(FUNC, b'\x00\x00\x00'), (FIX, b''), (CODE, b'\x60'), (ENDF, b''), (END, b'')])

    def test_the_same_call_is_recorded_once_and_calls_do_not_leak_into_the_next_function(self):
        out.begin_module(0, name(b'm'))
        f = out.symbol(out.SYM_FUNCTION, name(b'm'), 0, name(b'f'))
        fbuf.finish(f, 0)
        out.call(5, 0, out.NO_OUTER)
        out.call(6, 0, out.NO_OUTER)
        out.call(5, 0, out.NO_OUTER)
        out.call(5, out.CALL_SAVES, out.NO_OUTER)
        out.call(5, 0, 6)
        out.function_begin(f, 0)
        out.function_end()
        out.function_begin(f, 0)
        out.function_end()
        calls = [body for kind, body in self.written() if kind == CALL]
        self.assertEqual(calls, [b'\x05\x00\x00\xff\xff', b'\x06\x00\x00\xff\xff',
                                 b'\x05\x00\x01\xff\xff', b'\x05\x00\x00\x06\x00'])

    def test_too_many_different_calls_in_one_function_is_error_78(self):
        with self.assertRaises(SystemExit):
            for callee in range(out.MAX_CALLS + 1):
                out.call(callee, 0, out.NO_OUTER)
        self.assertIn('error 78:', support.error_text())

    def test_a_file_that_cannot_be_created_does_not_open(self):
        pointer, _ = support.put_text(b'/nonexistent/dir/m.lo')
        self.assertFalse(out.open(pointer))


if __name__ == '__main__':
    unittest.main()
