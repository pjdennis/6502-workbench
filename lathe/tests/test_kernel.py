"""kernel.py: text memory, streams, the name heap and the symbol table."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lathec_support as support  # noqa: E402
import env  # noqa: E402
import err  # noqa: E402
import kernel  # noqa: E402


def name(text):
    """Intern `text` the way the lexer does, one character at a time."""
    kernel.name_begin()
    for ch in text:
        kernel.name_add(ch)
    return kernel.name_end()


def spelling(n):
    return bytes(kernel.name_char(n, i) for i in range(kernel.name_length(n)))


class KernelTest(unittest.TestCase):
    def setUp(self):
        support.fresh()
        err.init()
        kernel.init()

    def assertFatal(self, number, call, *args):
        with self.assertRaises(SystemExit):
            call(*args)
        self.assertIn('error %d:' % number, support.error_text())


class NameHeapTest(KernelTest):
    def test_a_name_is_stored_once(self):
        first = name(b'count')
        top = kernel.name_top
        self.assertEqual(name(b'count'), first)
        self.assertEqual(kernel.name_top, top)

    def test_different_names_differ_and_keep_their_spelling(self):
        a, b = name(b'put_byte'), name(b'put_error')
        self.assertNotEqual(a, b)
        self.assertEqual(spelling(a), b'put_byte')
        self.assertEqual(spelling(b), b'put_error')

    def test_no_name_is_number_zero(self):
        self.assertNotEqual(name(b'a'), 0)

    def test_names_in_one_bucket_are_all_found(self):
        made = [name(b'n%d' % i) for i in range(300)]       # more names than buckets
        self.assertEqual(len(set(made)), 300)
        self.assertEqual([name(b'n%d' % i) for i in range(300)], made)

    def test_only_the_first_31_characters_count(self):
        long_one = name(b'a' * 31 + b'xyz')
        self.assertEqual(name(b'a' * 31 + b'q'), long_one)
        self.assertEqual(kernel.name_length(long_one), 31)
        self.assertNotEqual(name(b'a' * 30), long_one)

    def test_a_name_carries_a_token_number_that_starts_at_zero(self):
        n = name(b'while')
        self.assertEqual(kernel.name_token(n), 0)
        kernel.name_set_token(n, 77)
        self.assertEqual(kernel.name_token(name(b'while')), 77)

    def test_a_full_name_heap_is_error_70(self):
        def fill():
            for i in range(kernel.NAME_HEAP_SIZE):
                name(b'name%d' % i)
        self.assertFatal(err.E_NAMES_FULL, fill)


class SymbolTableTest(KernelTest):
    def test_a_symbol_is_found_by_scope_and_name(self):
        n = name(b'main')
        s = kernel.sym_add(kernel.SCOPE_MODULE, n, kernel.K_FUNC)
        self.assertEqual(kernel.sym_find(kernel.SCOPE_MODULE, n), (s, True))
        self.assertEqual(kernel.sym_name[s], n)
        self.assertEqual(kernel.sym_kind[s], kernel.K_FUNC)
        self.assertEqual(kernel.sym_obj[s], kernel.NO_OBJ)
        self.assertEqual(kernel.sym_flags[s], 0)

    def test_an_unknown_name_is_not_found(self):
        _, found = kernel.sym_find(kernel.SCOPE_MODULE, name(b'nothing'))
        self.assertFalse(found)
        _, found = kernel.sym_lookup(name(b'nothing'))
        self.assertFalse(found)

    def test_the_same_name_may_be_in_two_modules(self):
        n = name(b'put')
        own = kernel.sym_add(kernel.SCOPE_MODULE, n, kernel.K_FUNC)
        theirs = kernel.sym_add(1, n, kernel.K_FUNC)
        self.assertEqual(kernel.sym_find(1, n), (theirs, True))
        self.assertEqual(kernel.sym_find(kernel.SCOPE_MODULE, n), (own, True))
        _, found = kernel.sym_find(2, n)
        self.assertFalse(found)

    def test_a_plain_name_does_not_see_another_modules_symbols(self):
        n = name(b'put')
        kernel.sym_add(1, n, kernel.K_FUNC)
        _, found = kernel.sym_lookup(n)
        self.assertFalse(found)

    def test_declaring_a_name_twice_in_one_scope_is_error_41(self):
        n = name(b'twice')
        kernel.sym_add(kernel.SCOPE_MODULE, n, kernel.K_FUNC)
        self.assertFatal(err.E_DUPLICATE, kernel.sym_add, kernel.SCOPE_MODULE, n, kernel.K_CONST)

    def test_a_module_name_hides_a_predeclared_one(self):
        n = name(b'true')
        predeclared = kernel.sym_add(kernel.SCOPE_PREDECLARED, n, kernel.K_CONST)
        self.assertEqual(kernel.sym_lookup(n), (predeclared, True))
        own = kernel.sym_add(kernel.SCOPE_MODULE, n, kernel.K_CONST)
        self.assertEqual(kernel.sym_lookup(n), (own, True))

    def test_a_local_hides_a_module_name_until_the_function_ends(self):
        n = name(b'count')
        outer = kernel.sym_add(kernel.SCOPE_MODULE, n, kernel.K_CONST)
        kernel.scope_begin()
        inner = kernel.sym_add(kernel.SCOPE_LOCAL, n, kernel.K_CONST)
        self.assertEqual(kernel.sym_lookup(n), (inner, True))
        kernel.scope_end()
        self.assertEqual(kernel.sym_lookup(n), (outer, True))

    def test_the_end_of_a_function_releases_its_symbols_and_names(self):
        kernel.sym_add(kernel.SCOPE_MODULE, name(b'f'), kernel.K_FUNC)
        symbols, names = kernel.sym_count, kernel.name_top
        kernel.scope_begin()
        for i in range(20):
            kernel.sym_add(kernel.SCOPE_LOCAL, name(b'local%d' % i), kernel.K_CONST)
        kernel.scope_end()
        self.assertEqual((kernel.sym_count, kernel.name_top), (symbols, names))
        again = name(b'local7')
        self.assertEqual(spelling(again), b'local7')
        _, found = kernel.sym_lookup(again)
        self.assertFalse(found)

    def test_two_functions_may_use_the_same_local_name(self):
        for _ in range(2):
            kernel.scope_begin()
            kernel.sym_add(kernel.SCOPE_LOCAL, name(b'i'), kernel.K_CONST)
            kernel.scope_end()

    def test_a_full_symbol_table_is_error_71(self):
        def fill():
            for i in range(kernel.MAX_SYMS + 1):
                kernel.sym_add(kernel.SCOPE_MODULE, name(b's%d' % i), kernel.K_CONST)
        self.assertFatal(err.E_SYMS_FULL, fill)

    def test_members_are_numbered_in_order(self):
        first = kernel.member_add(3, 1)
        second = kernel.member_add(5, 7)
        self.assertEqual(second, first + 1)
        self.assertEqual((kernel.member_type[second], kernel.member_value[second]), (5, 7))

    def test_too_many_members_is_error_72(self):
        def fill():
            for i in range(kernel.MAX_MEMBERS + 1):
                kernel.member_add(1, 0)
        self.assertFatal(err.E_MEMBERS_FULL, fill)

    def test_modules_are_numbered_from_the_one_being_compiled(self):
        self.assertEqual(kernel.module_add(name(b'hello')), 0)
        self.assertEqual(kernel.module_add(name(b'host')), 1)
        self.assertEqual(spelling(kernel.module_name[1]), b'host')

    def test_too_many_modules_is_error_73(self):
        def fill():
            for i in range(kernel.MAX_MODULES + 1):
                kernel.module_add(name(b'm%d' % i))
        self.assertFatal(err.E_MODULES_FULL, fill)


class TextMemoryTest(KernelTest):
    def test_arguments_are_kept_as_zero_terminated_text(self):
        env.start(['hello.lth', 'out'])
        first = kernel.keep_argument(0)
        second = kernel.keep_argument(1)
        self.assertEqual(bytes(env.mem[first:first + 10]), b'hello.lth\0')
        self.assertEqual(bytes(env.mem[second:second + 4]), b'out\0')
        self.assertNotEqual(first, 0)

    def test_arguments_longer_than_the_text_area_are_error_82(self):
        env.start(['x' * (kernel.TEXT_END - kernel.TEXT_BASE)])
        self.assertFatal(err.E_TEXT_FULL, kernel.keep_argument, 0)

    def test_a_path_is_built_from_a_directory_a_name_and_an_ending(self):
        directory, _ = support.put_text(b'build/out')
        kernel.path_begin()
        kernel.path_add_text(directory)
        kernel.path_add(0x2F)
        kernel.path_add_name(name(b'hello'))
        path = kernel.path_end()
        self.assertEqual(bytes(env.mem[path:path + 16]), b'build/out/hello\0')

    def test_a_path_that_does_not_fit_is_error_83(self):
        def build():
            kernel.path_begin()
            for i in range(kernel.PATH_SIZE):
                kernel.path_add(0x41)
            kernel.path_end()
        self.assertFatal(err.E_PATH_LONG, build)


class StreamTest(KernelTest):
    def test_a_memory_stream_gives_its_bytes_and_then_the_end(self):
        start, end = support.put_text(b'ab')
        s = kernel.open_memory(start, end)
        self.assertEqual(kernel.get(s), (0x61, False))
        self.assertEqual(kernel.get(s), (0x62, False))
        self.assertEqual(kernel.get(s), (0, True))
        self.assertEqual(kernel.get(s), (0, True))

    def test_what_is_written_to_a_file_can_be_read_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _ = support.put_text(os.path.join(tmp, 'x.bin').encode())
            out, ok = kernel.open_out(path)
            self.assertTrue(ok)
            kernel.put(out, 0x12)
            kernel.put_word(out, 0xBEEF)
            kernel.put_name(out, name(b'hey'))
            kernel.close(out)
            source, ok = kernel.open_in(path)
            self.assertTrue(ok)
            read = [kernel.get(source)[0] for _ in range(7)]
            self.assertEqual(read, [0x12, 0xEF, 0xBE, 3, 0x68, 0x65, 0x79])
            self.assertEqual(kernel.get_word(source), 0)        # past the end reads as zero
            self.assertEqual(kernel.get(source), (0, True))
            kernel.close(source)

    def test_a_missing_file_does_not_open(self):
        path, _ = support.put_text(b'/nonexistent/dir/file')
        _, ok = kernel.open_in(path)
        self.assertFalse(ok)
        _, ok = kernel.open_out(path)
        self.assertFalse(ok)

    def test_a_closed_stream_can_be_used_again(self):
        start, end = support.put_text(b'')
        for _ in range(kernel.MAX_STREAMS * 2):
            kernel.close(kernel.open_memory(start, end))

    def test_too_many_streams_is_error_80(self):
        start, end = support.put_text(b'')

        def fill():
            for _ in range(kernel.MAX_STREAMS + 1):
                kernel.open_memory(start, end)
        self.assertFatal(err.E_STREAMS_FULL, fill)


if __name__ == '__main__':
    unittest.main()
