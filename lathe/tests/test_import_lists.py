"""import_lists.py: the tool that writes import lists, and that the lists of the compiler's and
the linker's twins, their test programs and the run-time modules are what it writes."""
import glob
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import import_lists  # noqa: E402
import lathec_support as support  # noqa: E402

LIB = ('module lib\n'
       'pub const ONE = 1\n'
       'pub var count: byte\n'
       'pub var other: byte\n'
       'pub var spare: byte\n'
       'pub type T = record\n'
       '  a: byte\n'
       'end\n'
       'pub func f()\n'
       'end\n')
# Uses ONE and T everywhere, count only on the 65C02 (compiler-bank.env), f only in the body of
# an inline function it never expands, and other in an asm block.
USER = ('module user\n'
        '\n'
        'import lib   ; the library\n'
        '\n'
        'var t: lib.T\n'
        'var n: byte\n'
        'func g()\n'
        '#if cpu_65c02\n'
        '  lib.count = lib.ONE\n'
        '#else\n'
        '  n = lib.ONE\n'
        '#end\n'
        '  asm\n'
        '    LDA lib.other\n'
        '  end\n'
        'end\n'
        'pub inline func h()\n'
        '  lib.f()\n'
        'end\n')


class ToolBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name

    def write(self, name, text):
        path = os.path.join(self.dir, name + '.lth')
        with open(path, 'w') as f:
            f.write(text)
        return path

    def read(self, path):
        with open(path) as f:
            return f.read()

    def tool(self, *args):
        return subprocess.run([sys.executable, import_lists.__file__] + list(args), capture_output=True,
                              text=True)

    def files(self, path):
        out = os.path.join(self.dir, 'out')
        os.makedirs(out, exist_ok=True)
        lib = os.path.join(self.dir, 'lib.lth')
        self.assertEqual(support.run_lathec(lib, out), (0, ''))
        self.assertEqual(support.run_lathec('-c65c02', path, out), (0, ''))
        found = []
        for ending in ('.lo', '.li'):
            with open(os.path.join(out, 'user' + ending), 'rb') as f:
                found.append(f.read())
        return found

class ToolTest(ToolBase):
    def test_it_lists_what_every_configuration_uses_and_the_files_stay_the_same(self):
        self.write('lib', LIB)
        path = self.write('user', USER)
        before = self.files(path)
        self.assertEqual(self.tool('--check', path).returncode, 1)
        self.assertEqual(self.tool(path).returncode, 0)
        self.assertIn('\nimport lib (count, f, ONE, other, T)   ; the library\n', self.read(path))
        self.assertEqual(self.files(path), before)
        self.assertEqual(self.tool('--check', path).returncode, 0)

    def test_it_lists_nothing_where_everything_is_used_and_an_empty_list_where_nothing_is(self):
        self.write('lib', LIB)
        every = self.write('user', 'module user\nimport lib (ONE)\nvar t: lib.T\nfunc g()\n  lib.count = lib.ONE\n'
                           '  lib.other = 1\n  lib.spare = 1\n  lib.f()\nend\n')
        nothing = self.write('none', 'module none\nimport lib\n')
        self.assertEqual(self.tool(every, nothing).returncode, 0)
        self.assertTrue(self.read(every).startswith('module user\nimport lib\nvar t'))
        self.assertEqual(self.read(nothing), 'module none\nimport lib ()\n')

    def test_a_long_list_is_wrapped(self):
        names = ['name_number_%d' % i for i in range(12)]
        self.write('lib', 'module lib\n' + ''.join('pub var %s: byte\n' % n for n in names + ['spare']))
        path = self.write('user', 'module user\nimport lib\nfunc g()\n'
                          + ''.join('  lib.%s = 0\n' % n for n in names) + 'end\n')
        self.assertEqual(self.tool(path).returncode, 0)
        lines = self.read(path).split('\n')
        self.assertTrue(all(len(line) <= import_lists.WIDTH for line in lines))
        self.assertTrue(lines[1].startswith('import lib (name_number_0, name_number_1, name_number_10,'))
        self.assertTrue(lines[2].startswith(' ' * len('import lib (') + 'name_number_'))
        statement = ' '.join(lines[1:4]).split()
        self.assertEqual(statement[:3], ['import', 'lib', '(' + sorted(names)[0] + ','])
        self.assertEqual(' '.join(statement[2:]), '(' + ', '.join(sorted(names)) + ')')
        self.assertEqual(self.tool('--check', path).returncode, 0)


class LargeTest(ToolBase):
    """A module whose imports without lists do not fit the name heap of the build: the tool
    still finds what it uses, whatever its lists say now."""

    def big_lib(self):
        names = ['a_rather_long_exported_name_%03d' % i for i in range(400)]
        self.write('lib', 'module lib\n' + ''.join('pub var %s: byte\n' % n for n in names))
        return names

    def test_a_stale_list_is_found_and_written_anew_though_no_list_fits_the_heap(self):
        import kernel
        names = self.big_lib()
        self.assertGreater(400 * (8 + len(names[0])), kernel.NAME_HEAP_SIZE)
        body = 'func g()\n  lib.%s = 1\n  lib.%s = 2\nend\n' % (names[7], names[300])
        path = self.write('user', 'module user\nimport lib (%s)\n' % names[7] + body)
        done = self.tool('--check', path)
        self.assertEqual((done.returncode, done.stdout.strip()), (1, os.path.relpath(path)))
        self.assertEqual(self.tool(path).returncode, 0)
        self.assertEqual(self.read(path), 'module user\nimport lib (%s, %s)\n' % (names[7], names[300]) + body)
        self.assertEqual(self.tool('--check', path).returncode, 0)

    def test_a_file_that_does_not_compile_is_a_failure_in_both_modes(self):
        self.write('lib', LIB)
        path = self.write('user', 'module user\nimport lib\nfunc g()\n  lib.nothing = 1\nend\n')
        for args in (('--check', path), (path,)):
            done = self.tool(*args)
            self.assertEqual(done.returncode, 2, args)
            self.assertIn('user.lth', done.stderr)
            self.assertIn('error 40', done.stderr)
        broken = self.write('lib', 'module lib\npub var x\n')
        user = self.write('user', 'module user\nimport lib\n')
        done = self.tool('--check', user)
        self.assertEqual(done.returncode, 2)
        self.assertIn('lib.lth', done.stderr)


def listed_files():
    """The modules whose imports have the lists the tool writes."""
    src = os.path.join(support.LATHE, 'src')
    return sorted(glob.glob(os.path.join(src, '*.lth')) + glob.glob(os.path.join(support.LATHE, 'rt', '*.lth'))
                  + glob.glob(os.path.join(support.LATHE, 'rt', '*', '*.lth')))


class ListsTest(unittest.TestCase):
    def test_the_twins_test_programs_and_run_time_modules_have_the_lists_the_tool_writes(self):
        """`import_lists.py --check` on them: a list that is not what the compiler finds used is
        out of date (lathe/docs/language.md, "Modules")."""
        done = subprocess.run([sys.executable, import_lists.__file__, '--check'] + listed_files(),
                              capture_output=True, text=True)
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, '', ''))


if __name__ == '__main__':
    unittest.main()
