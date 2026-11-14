"""decl.py: imports and import lists, and what an interface carries for them (lathe/docs/
language.md, "Modules"; lathe/host/README.md, "The interface file").

`import m` makes everything m exports usable; `import m (a, b)` only a and b, and only what the
list names, what the types of those need and what the bodies of the inline functions listed
name are read into the name heap. The object and interface files of a module must be the same
whether its imports have lists or not."""
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lathec_support as support  # noqa: E402
import decl  # noqa: E402
import env  # noqa: E402
import kernel  # noqa: E402

LIB = ('module lib\n'
       'pub enum Kind\n'
       '  K_A\n'
       '  K_B = 7\n'
       'end\n'
       'pub type Node = record\n'
       '  kind: Kind\n'
       '  next: ^Node\n'
       'end\n'
       'type Hidden = record\n'
       '  h: word\n'
       'end\n'
       'pub const LIMIT = 300\n'
       'pub const SMALL: byte = 7\n'
       'pub var count: byte\n'
       'pub var total: word\n'
       'pub var nodes: [4]Node\n'
       'pub var secret: ^Hidden\n'
       'pub func first(): ^Node\n'
       '  return nil\n'
       'end\n'
       'pub func take(n: byte, w: word): word, bool\n'
       '  return w, n == 0\n'
       'end\n')

USER = ('func f(): byte\n'
        '  var p: ^lib.Node\n'
        '  var w: word\n'
        '  var ok: bool\n'
        '  lib.count = lib.SMALL\n'
        '  lib.total = lib.LIMIT\n'
        '  p = lib.first()\n'
        '  p.next = nil\n'
        '  w, ok = lib.take(lib.count, lib.total)\n'
        '  return byte(lib.nodes[2].kind)\n'
        'end\n')


class Program(unittest.TestCase):
    """The compiler as a program, on files in a directory of the test's own."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name

    def write(self, module, text):
        path = os.path.join(self.dir, module + '.lth')
        with open(path, 'w') as f:
            f.write(text)
        return path

    def compile(self, module, text):
        status, errors = support.run_lathec(self.write(module, text), self.dir)
        self.assertEqual((status, errors), (0, ''))

    def fails(self, module, text, place, number):
        path = self.write(module, text)
        status, errors = support.run_lathec(path, self.dir)
        self.assertEqual(status, 1, errors)
        self.assertTrue(errors.startswith('%s:%s: error %d: ' % (path, place, number)), errors)

    def output(self, module):
        """The object and interface files of a module compiled last."""
        found = []
        for ending in ('.lo', '.li'):
            with open(os.path.join(self.dir, module + ending), 'rb') as f:
                found.append(f.read())
        return found

    def heap(self, module, text):
        """The name heap's use at the end of compiling a module, in this process."""
        import lathec
        path = self.write(module, text)
        support.fresh()
        env._out = io.BytesIO()
        env.start([path, self.dir])
        try:
            lathec.main()
            status = 0
        except SystemExit as e:
            status = e.code
        self.assertEqual((status, support.error_text()), (0, ''))
        support.fresh()
        return kernel.name_top


class ListTest(Program):
    def setUp(self):
        Program.setUp(self)
        self.compile('lib', LIB)

    def test_a_list_gives_the_same_files_as_no_list(self):
        self.compile('user', 'module user\nimport lib\n' + USER)
        whole = self.output('user')
        self.compile('user', 'module user\nimport lib (count, SMALL, total, LIMIT, first, take, nodes, Node)\n' + USER)
        self.assertEqual(self.output('user'), whole)
        self.compile('user', 'module user\nimport lib (Node, nodes, take, first, LIMIT, total, SMALL, count)\n' + USER)
        self.assertEqual(self.output('user'), whole)

    def test_a_list_goes_on_over_lines_while_it_is_open(self):
        self.compile('user', 'module user\nimport lib (count, SMALL,\n  total, LIMIT, first,\n'
                     '  take, nodes, Node)\nvar k: byte\n' + USER)

    def test_a_list_loads_less(self):
        whole = self.heap('user', 'module user\nimport lib\n' + USER)
        listed = self.heap('user', 'module user\nimport lib (count, SMALL, total, LIMIT, first, take, nodes, Node)\n'
                           + USER)
        self.assertLess(listed, whole)

    def test_a_name_not_listed_is_error_101(self):
        self.fails('user', 'module user\nimport lib (count)\nfunc f()\n  lib.count = lib.SMALL\nend\n',
                   '4:19', 101)
        self.fails('user', 'module user\nimport lib ()\nfunc f()\n  lib.count = 1\nend\n', '4:7', 101)
        self.fails('user', 'module user\nimport lib (first)\nvar n: lib.Node\n', '3:12', 101)

    def test_a_name_not_listed_is_error_101_also_in_asm(self):
        self.fails('user', 'module user\nimport lib (total)\nfunc f()\n  asm\n    LDA lib.count\n  end\nend\n',
                   '5:9', 101)

    def test_a_name_the_module_does_not_export_is_error_102_at_the_name(self):
        self.fails('user', 'module user\nimport lib (count,\n  nothing)\n', '3:3', 102)
        self.fails('user', 'module user\nimport lib (Hidden)\n', '2:13', 102)

    def test_a_name_listed_twice_is_error_103(self):
        self.fails('user', 'module user\nimport lib (count, take, count)\n', '2:26', 103)

    def test_the_types_a_listed_name_needs_work_without_being_listed(self):
        self.compile('user', 'module user\nimport lib (first, nodes)\nvar k: byte\nfunc f()\n'
                     '  lib.nodes[1].next = lib.first()\n  k = byte(lib.nodes[1].kind)\nend\n')
        self.fails('user', 'module user\nimport lib (nodes)\nvar k: byte\nfunc f()\n'
                   '  k = byte(lib.K_B)\nend\n', '5:16', 101)

    def test_a_listed_type_or_constant_of_an_enumeration_can_be_named(self):
        self.compile('user', 'module user\nimport lib (Kind, K_B)\nvar k: lib.Kind\nfunc f()\n'
                     '  k = lib.K_B\nend\n')

    def test_a_module_imported_twice_is_error_41_with_or_without_a_list(self):
        self.fails('user', 'module user\nimport lib (count)\nimport lib (total)\n', '3:8', 41)
        self.fails('user', 'module user\nimport lib\nimport lib ()\n', '3:8', 41)

    def test_more_names_than_a_list_can_hold_is_error_89(self):
        names = ', '.join('n%d' % i for i in range(decl.MAX_WANTS + 1))
        self.fails('user', 'module user\nimport lib (%s)\n' % names, '2:%d' % (14 + names.rindex(' ')), 89)

    def test_the_run_time_modules_the_compiler_calls_are_read_whole(self):
        """The operators call rt_math's routines whatever the list names: the same files."""
        status, errors = support.run_lathec(os.path.join(support.LATHE, 'rt', 'rt_math.lth'), self.dir)
        self.assertEqual((status, errors), (0, ''))
        body = 'var a: byte\nvar w: word\nfunc f()\n  a = a * a\n  w = w / w + rt_math.mul16(w, w)\nend\n'
        self.compile('user', 'module user\nimport rt_math\n' + body)
        whole = self.output('user')
        self.compile('user', 'module user\nimport rt_math (mul16)\n' + body)
        self.assertEqual(self.output('user'), whole)


class ReachedTwiceTest(Program):
    """A module an interface brings in for its inline functions, and imported by the importer."""

    def setUp(self):
        Program.setUp(self)
        self.compile('lib', LIB)
        self.compile('mid', 'module mid\nimport lib (count, total)\npub inline func bump()\n'
                     '  lib.count += 1\nend\npub func other()\nend\n')

    def test_either_order_gives_the_same_files(self):
        use = 'func f()\n  mid.bump()\n  lib.total = 1\nend\n'
        for whole, listed in (('import mid\nimport lib\n', 'import mid (bump)\nimport lib (total)\n'),
                              ('import lib\nimport mid\n', 'import lib (total)\nimport mid (bump)\n'),
                              ('import lib\nimport mid\n', 'import lib\nimport mid (bump)\n'),
                              ('import mid\nimport lib\n', 'import mid (bump)\nimport lib\n')):
            self.compile('user', 'module user\n' + whole + use)
            files = self.output('user')
            self.compile('user', 'module user\n' + listed + use)
            self.assertEqual(self.output('user'), files, listed)
        use = 'func f()\n  lib.total = 1\nend\n'
        self.compile('user', 'module user\nimport mid\nimport lib\n' + use)
        files = self.output('user')
        self.compile('user', 'module user\nimport mid ()\nimport lib (total)\n' + use)
        self.assertEqual(self.output('user'), files)

    def test_what_an_inline_body_names_cannot_be_named_unless_listed(self):
        self.fails('user', 'module user\nimport mid (bump)\nimport lib (total)\nfunc f()\n  mid.bump()\n'
                   '  lib.count = 1\nend\n', '6:7', 101)
        self.compile('user', 'module user\nimport mid (bump)\nimport lib (total, count)\nfunc f()\n'
                     '  mid.bump()\n  lib.count = 1\nend\n')
        self.compile('user', 'module user\nimport lib (total, count)\nimport mid (bump)\nfunc f()\n'
                     '  mid.bump()\n  lib.count = 1\nend\n')

    def test_a_module_of_an_interface_is_not_a_name_it_exports(self):
        self.fails('user', 'module user\nimport mid (lib)\n', '2:13', 102)


class InlineTest(Program):
    """What the bodies of exported inline functions name is found, listed or not."""

    def setUp(self):
        Program.setUp(self)
        self.compile('lib', LIB)
        self.compile('mid', 'module mid\nimport lib (count, total, take)\n'
                     'pub var hits: byte\npub const STEP = 2\npub var unused: word\n'
                     'pub inline func inner(n: byte)\n  hits += n\n  lib.total = lib.take(n, 1)\nend\n'
                     'pub inline func outer()\n  inner(STEP)\n  lib.count += 1\nend\n'
                     'pub func other()\nend\n')

    def test_an_inline_body_s_names_are_read_with_it(self):
        use = 'func f()\n  mid.outer()\nend\n'
        self.compile('user', 'module user\nimport mid\n' + use)
        whole = self.output('user')
        self.compile('user', 'module user\nimport mid (outer)\n' + use)
        self.assertEqual(self.output('user'), whole)

    def test_only_the_listed_inline_functions_are_read(self):
        whole = self.heap('user', 'module user\nimport mid\nfunc f()\n  mid.other()\nend\n')
        listed = self.heap('user', 'module user\nimport mid (other)\nfunc f()\n  mid.other()\nend\n')
        self.assertLess(listed, whole)

    def test_an_inline_body_s_names_cannot_be_named_by_the_importer_unless_listed(self):
        self.fails('user', 'module user\nimport mid (outer)\nfunc f()\n  mid.outer()\n  mid.hits = 0\nend\n',
                   '5:7', 101)

    def test_the_interface_lists_what_each_inline_body_names(self):
        with open(os.path.join(self.dir, 'mid.li'), 'rb') as f:
            li = f.read()
        self.assertTrue(li.startswith(b'LI\x02\x03mid'
                                      b'\x0a\x05outer\x03\x00\x05inner\x00\x04step\x03lib\x05count'
                                      b'\x0a\x05inner\x03\x00\x04hits\x03lib\x05total\x03lib\x04take'
                                      b'\x08\x03lib'), li)

    def test_a_body_that_names_what_its_own_list_leaves_out_is_error_101(self):
        self.fails('mid2', 'module mid2\nimport lib (count)\npub inline func g()\n  lib.total = 1\nend\n',
                   '4:7', 101)


if __name__ == '__main__':
    unittest.main()
