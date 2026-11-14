"""The first identity test between a host component and its Lathe counterpart: lathe/src/lex.lth
against lathe/host/lex.py. lathe/src/lextest.lth is built once and run on the emulator over
every source in lathe/tests/cases/, lathe/src/ and lathe/rt/, and over the corner cases below;
lathe/tests/lextest_host.py runs the host lexer over the same file in this process. The tokens
printed, the error output and the exit status must be identical.

LATHE_LEX_REPORT=1 prints the emulated cycles per source byte at the end."""
import concurrent.futures
import glob
import io
import os
import shutil
import tempfile
import unittest

import src_support as support
import lathec_support
import env
import lextest_host

ROOT = support.ROOT

# Sources written for this test: corners of the lexical rules, and every lexical error.
CORNERS = {
    'operators': b'( ) [ ] , : . @ ~ -> = += -= &= |= ^= <<= >>= + - * / & | ^ << >> == != < <= > >=\n',
    'numbers': b'0 65535 $FFFF $ffff %1111111111111111 \'a\' \'\\n\' \'\\x7E\' 007 $0 %0\n',
    'too_big': b'x = 65536\n',
    'too_big_hex': b'x = $10000\n',
    'too_big_binary': b'x = %10000000000000000\n',
    'no_digits': b'x = $\n',
    'no_binary_digits': b'x = %2\n',
    'case': b'MODULE Mixed\nPUB Func MaIn()\nWhile x_1 Do\nEND\n',
    'long_name': b'a' * 40 + b' ' + b'a' * 31 + b'b\n',
    'strings': b'"" "a" "\\n\\r\\t\\0\\\\\\"\\\'" "\\x00\\xff\\xAb"\n',
    'string_255': b'"' + b'x' * 255 + b'"\n',
    'string_256': b'"' + b'x' * 256 + b'"\n',
    'open_string': b'"abc\n',
    'string_at_end': b'"abc',
    'bad_escape': b'"\\q"\n',
    'bad_hex_escape': b'"\\x4g"\n',
    'char_open': b"'a\n",
    'char_empty': b"''\n",
    'char_at_end': b"'",
    'char_two': b"'ab'\n",
    'control_in_string': b'"a\tb"\n',
    'high_in_string': b'"a\x80"\n',
    'bad_char': b'x = 1 ? 2\n',
    'bang': b'x ! y\n',
    'crlf': b'a = 1\r\nb = 2\r\n\r\n',
    'no_final_newline': b'a = b +',
    'continuation': b'f(a,\n  b) + \n c\nx = [1,\n2]\ny = a and\nb or\nc mod\nd\n\n\n',
    'comments': b'; one\n  ; two\nx ; three\n;four',
    'tabs': b'\tx\t=\t1\n',
    'empty': b'',
    'only_newlines': b'\n\n\n',
    'if_else': b'#if a\nx\n#else\ny\n#end\n#if b\nz\n#else\nw\n#end\n#if c\n#if d\n#end\n#else\nq\n#end\n',
    'if_nested_skip': b'#if a\n  #if b\n  #else\n  #end\n#else ; c\nk\n#end ; e\n',
    'if_open': b'#if a\nx\n',
    'if_open_skipped': b'#if a\n#if b\n',
    'else_twice': b'#if a\n#else\n#else\n#end\n',
    'else_twice_taken': b'#if a\n#end\n#if b\nx\n#else\ny\n#else\n#end\n',
    'end_alone': b'#end\n',
    'else_alone': b'#else\n',
    'directive_unknown': b'#foo\n',
    'directive_mid_line': b'x #if\n',
    'directive_junk': b'#if a\n#end junk\n',
    'if_deep': b''.join(b'#if a%d\n' % i for i in range(20)),
    'asm_block': b'func f()\n  asm\n    LDA #$10 ; "\n  .x: STA $D020\n    end\n  x = 1\nend\n',
    'asm_func': b'asm func g(v: byte in a): byte in a\n  ASL A\n  #x\nend\nfunc h()\nend\n',
    'asm_open': b'asm\n  LDA #1\n',
    'many_lines': b'x\n' * 70000,
    'wide_line': b' ' * 70000 + b'x\n',
}


def lathe_sources():
    """Every .lth file under lathe/tests/cases, lathe/src and lathe/rt, relative to the root."""
    found = []
    for pattern in ('lathe/tests/cases/**/*.lth', 'lathe/src/*.lth', 'lathe/rt/*.lth'):
        found += glob.glob(os.path.join(ROOT, pattern), recursive=True)
    return sorted(os.path.relpath(p, ROOT) for p in found)


def host_run(path):
    """lextest_host over `path`: (status, output, error output)."""
    lathec_support.fresh()
    env._out = io.BytesIO()
    env.start([path])
    status = None
    try:
        lextest_host.main()
    except SystemExit as e:
        status = e.code
    return status, env._out.getvalue(), env._err.getvalue()


class LexIdentityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-src-lex-')
        cls.image = support.build_program('lextest', cls.dir)
        cls.cycles = 0
        cls.bytes = 0

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)
        if os.environ.get('LATHE_LEX_REPORT') and cls.bytes:
            print('\nlextest: %d bytes of source, %d cycles, %.1f cycles per byte'
                  % (cls.bytes, cls.cycles, cls.cycles / cls.bytes))

    def lathe_run(self, path):
        status, out, err, cycles = support.run(self.image, [path], timeout=120)
        return status, out, err, cycles

    def compare(self, paths, count=False):
        """Run both lexers over each of `paths` (relative to the root); the Lathe ones in
        parallel. Returns the number of files that ended with a lexical error."""
        cwd = os.getcwd()
        os.chdir(ROOT)
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
                lathe = list(pool.map(self.lathe_run, paths))
            errors = 0
            for path, (status, out, err, cycles) in zip(paths, lathe):
                with self.subTest(path=path):
                    expected = host_run(path)
                    self.assertEqual((status, err), expected[0::2])
                    self.assertEqual(out, expected[1])      # apart, so a difference is shown
                    errors += status != 0
                if count:
                    type(self).cycles += cycles
                    type(self).bytes += os.path.getsize(path)
            return errors
        finally:
            os.chdir(cwd)

    def test_every_source_of_the_project(self):
        paths = lathe_sources()
        self.assertGreater(len(paths), 300)
        self.compare(paths, count=True)
        print('\nlextest: %d files' % len(paths)) if os.environ.get('LATHE_LEX_REPORT') else None

    def test_the_corners_of_the_lexical_rules(self):
        paths = []
        for name, text in sorted(CORNERS.items()):
            path = os.path.join(self.dir, name + '.lth')
            with open(path, 'wb') as fh:
                fh.write(text)
            paths.append(os.path.relpath(path, ROOT))
        errors = self.compare(paths)
        self.assertGreater(errors, 20)          # the error cases do end in errors

    def test_a_missing_file_and_no_argument(self):
        os.chdir(ROOT)
        missing = os.path.join(self.dir, 'none.lth')
        status, out, err, _ = support.run(self.image, [missing])
        self.assertEqual((status, out, err), host_run(missing))
        self.assertEqual(status, 1)
        status, out, err, _ = support.run(self.image, [])
        lathec_support.fresh()
        env._out = io.BytesIO()
        env.start([])
        with self.assertRaises(SystemExit):
            lextest_host.main()
        self.assertEqual((out, err), (env._out.getvalue(), env._err.getvalue()))


if __name__ == '__main__':
    unittest.main()
