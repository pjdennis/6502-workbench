"""lathec.py as a program: what it writes for whole modules, and how it answers a bad
command line. The object files are checked against docs/object-format.md record by record."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lathec_support as support  # noqa: E402

END, MOD, IMP, SYM, FUNC, SLOT, CALL, FIX, CODE, ENDF = 0, 1, 2, 3, 7, 8, 9, 10, 11, 12
HOST_LTH = os.path.join(support.LATHE, 'rt', 'host.lth')
HELLO_LTH = os.path.join(support.CASES, 'e2e', 'hello.lth')


def string(text):
    return bytes([len(text)]) + text


def fixup(offset, kind, symbol, slot, addend):
    return bytes([offset & 0xFF, offset >> 8, kind, symbol & 0xFF, symbol >> 8, slot,
                  addend & 0xFF, addend >> 8])


class CompileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = self.tmp.name

    def source(self, name, text, newline='\n'):
        """Write a source file in a directory of its own, away from the output."""
        directory = os.path.join(self.out, 'src')
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, name)
        with open(path, 'w', newline=newline) as f:
            f.write(text)
        return path

    def compile(self, path, *more):
        status, errors = support.run_lathec(path, self.out, *more)
        self.assertEqual((status, errors), (0, ''))

    def records(self, module):
        return support.records(os.path.join(self.out, module + '.lo'))

    def interface(self, module):
        with open(os.path.join(self.out, module + '.li'), 'rb') as f:
            return f.read()

    def code(self, module):
        return [body for kind, body in self.records(module) if kind == CODE]


class HelloTest(CompileTest):
    def test_a_module_of_extern_declarations_has_an_object_file_with_no_functions(self):
        self.compile(HOST_LTH)
        self.assertEqual(self.records('host'), [(MOD, b'\x01\x00' + string(b'host')), (END, b'')])

    def test_its_interface_lists_what_it_exports(self):
        self.compile(HOST_LTH)
        byte_in_a, bool_in_c = b'\x01\x01', b'\x05\x07'
        self.assertEqual(self.interface('host'), b''.join([
            b'LI\x01', string(b'host'),
            b'\x01', string(b'read_byte'), b'\x01\x06\xf0', b'\x00', b'\x02', byte_in_a, bool_in_c,
            b'\x01', string(b'put_byte'), b'\x01\x09\xf0', b'\x01', byte_in_a, b'\x00',
            b'\x01', string(b'put_error'), b'\x01\x0c\xf0', b'\x01', byte_in_a, b'\x00',
            b'\x01', string(b'exit'), b'\x01\x0f\xf0', b'\x01', byte_in_a, b'\x00',
            b'\x00']))

    def test_hello_compiles_to_the_records_the_object_format_requires(self):
        self.compile(HOST_LTH)
        self.compile(HELLO_LTH)
        self.assertEqual(self.records('hello'), [
            (MOD, b'\x01\x00' + string(b'hello')),
            (IMP, string(b'host')),
            (SYM, b'\x01' + string(b'hello.main')),
            (FUNC, b'\x00\x00\x04'),                      # symbol 0, exported
            (FIX, b''),                                   # calls of fixed addresses need none
            (CODE, bytes([0xA9, 0x48, 0x20, 0x09, 0xF0,   # LDA #'H' / JSR $F009
                          0xA9, 0x49, 0x20, 0x09, 0xF0,   # LDA #'I' / JSR $F009
                          0xA9, 0x0A, 0x20, 0x09, 0xF0,   # LDA #10  / JSR $F009
                          0x60])),                        # RTS
            (ENDF, b''),
            (END, b''),
        ])

    def test_hello_exports_main(self):
        self.compile(HOST_LTH)
        self.compile(HELLO_LTH)
        self.assertEqual(self.interface('hello'),
                         b'LI\x01' + string(b'hello') + b'\x01' + string(b'main') + b'\x00\x00\x00' + b'\x00')

    def test_an_interface_is_also_looked_for_in_the_import_directories(self):
        with tempfile.TemporaryDirectory() as elsewhere, tempfile.TemporaryDirectory() as empty:
            self.assertEqual(support.run_lathec(HOST_LTH, elsewhere), (0, ''))
            self.compile(HELLO_LTH, empty, elsewhere)
            self.assertEqual(len(self.code('hello')), 1)

    def test_the_output_directory_is_searched_before_the_import_directories(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            other = os.path.join(elsewhere, 'host.lth')
            with open(other, 'w') as f:
                f.write('module host\npub extern func put_byte(ch: byte in x) at $1234\n')
            self.assertEqual(support.run_lathec(other, elsewhere), (0, ''))
            self.compile(HOST_LTH)
            self.compile(HELLO_LTH, elsewhere)
            self.assertEqual(self.code('hello')[0][:5], bytes([0xA9, 0x48, 0x20, 0x09, 0xF0]))


class LanguageTest(CompileTest):
    def test_calls_of_lathe_functions_are_fix_ups_with_call_records(self):
        self.compile(HOST_LTH)
        self.compile(self.source('util.lth',
                                 'module util\n'
                                 'import host\n'
                                 'pub func beep()\n'
                                 '  host.put_byte(7)\n'
                                 'end\n'
                                 'func hidden()\n'
                                 'end\n'))
        self.compile(self.source('app.lth',
                                 'module app\n'
                                 'import util\n'
                                 'func local()\n'
                                 '  util.beep()\n'
                                 'end\n'
                                 'pub func main()\n'
                                 '  local()\n'
                                 '  util.beep()\n'
                                 '  local()\n'
                                 '  return\n'
                                 'end\n'))
        jsr = b'\x20\x00\x00'
        self.assertEqual(self.records('app'), [
            (MOD, b'\x01\x00' + string(b'app')),
            (IMP, string(b'util')),
            (SYM, b'\x01' + string(b'app.local')),
            (SYM, b'\x01' + string(b'util.beep')),
            (FUNC, b'\x00\x00\x00'),
            (CALL, b'\x01\x00\x00\xff\xff'),
            (FIX, fixup(1, 1, 1, 0xFF, 0)),
            (CODE, jsr + b'\x60'),
            (ENDF, b''),
            (SYM, b'\x01' + string(b'app.main')),
            (FUNC, b'\x02\x00\x04'),
            (CALL, b'\x00\x00\x00\xff\xff'),
            (CALL, b'\x01\x00\x00\xff\xff'),
            (FIX, fixup(1, 1, 0, 0xFF, 0) + fixup(4, 1, 1, 0xFF, 0) + fixup(7, 1, 0, 0xFF, 0)),
            (CODE, jsr * 3 + b'\x60'),
            (ENDF, b''),
            (END, b''),
        ])
        self.assertEqual(self.interface('util'),
                         b'LI\x01' + string(b'util') + b'\x01' + string(b'beep') + b'\x00\x00\x00' + b'\x00')

    def test_arguments_go_to_the_registers_an_extern_function_names(self):
        self.compile(self.source('regs.lth',
                                 'module regs\n'
                                 'extern func f(w: word in ax, n: byte in y, on: bool in c) at $1234\n'
                                 'extern func g(on: bool in c, w: int in xy): ^^byte in ay, bool in c at 8192\n'
                                 'pub func main()\n'
                                 '  f($ABCD, 7, true)\n'
                                 '  g(false, 513)\n'
                                 '  f(0, 0, false)\n'
                                 'end\n'))
        self.assertEqual(self.code('regs'), [bytes([
            0xA9, 0xCD, 0xA2, 0xAB, 0xA0, 0x07, 0x38, 0x20, 0x34, 0x12,     # carry last
            0xA2, 0x01, 0xA0, 0x02, 0x18, 0x20, 0x00, 0x20,
            0xA9, 0x00, 0xA2, 0x00, 0xA0, 0x00, 0x18, 0x20, 0x34, 0x12,
            0x60])])
        self.assertEqual(self.interface('regs'),          # only what is `pub`
                         b'LI\x01' + string(b'regs') + b'\x01' + string(b'main') + b'\x00\x00\x00' + b'\x00')

    def test_types_and_registers_of_an_extern_function_are_in_the_interface(self):
        self.compile(self.source('lib.lth',
                                 'module lib\n'
                                 'pub extern func g(w: int in xy, s: sbyte in a): ^^byte in ay, bool in c at $2000\n'))
        self.assertEqual(self.interface('lib'), b''.join([
            b'LI\x01', string(b'lib'), b'\x01', string(b'g'), b'\x01\x00\x20',
            b'\x02', b'\x04\x06', b'\x02\x01',
            b'\x02', b'\x10\x10\x01\x05', b'\x05\x07',
            b'\x00']))
        self.compile(self.source('user.lth',
                                 'module user\nimport lib\npub func main()\n  lib.g($0102, 3)\nend\n'))
        self.assertEqual(self.code('user'), [bytes([0xA2, 0x02, 0xA0, 0x01, 0xA9, 0x03, 0x20, 0x00, 0x20, 0x60])])

    def test_names_and_keywords_are_not_case_sensitive(self):
        self.compile(HOST_LTH)
        self.compile(self.source('Shout.LTH',
                                 'MODULE Shout\nIMPORT Host\nPUB FUNC Main()\n  HOST.Put_Byte(\'H\')\nEND\n'))
        self.assertEqual(self.records('shout')[2], (SYM, b'\x01' + string(b'shout.main')))
        self.assertEqual(self.code('shout'), [bytes([0xA9, 0x48, 0x20, 0x09, 0xF0, 0x60])])

    def test_layout_comments_and_line_ends_do_not_matter(self):
        self.compile(HOST_LTH)
        self.compile(self.source('loose.lth',
                                 '; a comment first\n\nmodule loose ; here too\n\nimport host\n\n'
                                 'pub func main()   ; main\n\n  host.put_byte(\n    72\n  )\n\n  return\nend',
                                 newline='\r\n'))
        self.assertEqual(self.code('loose'), [bytes([0xA9, 0x48, 0x20, 0x09, 0xF0, 0x60])])

    def test_a_function_can_be_empty_and_a_module_can_have_several(self):
        self.compile(self.source('several.lth',
                                 'module several\nfunc a()\nend\nfunc b()\n  a()\n  return\n  a()\nend\n'))
        self.assertEqual(self.code('several'), [b'\x60', b'\x20\x00\x00\x60\x20\x00\x00\x60'])


class ImportTest(CompileTest):
    def fails(self, path, expected):
        self.assertEqual(support.run_lathec(path, self.out), (1, path + expected))

    def test_what_a_module_does_not_export_cannot_be_used(self):
        self.compile(self.source('util.lth', 'module util\nfunc hidden()\nend\n'))
        app = self.source('app.lth', 'module app\nimport util\npub func main()\n  util.hidden()\nend\n')
        self.fails(app, ':4:8: error 40: undefined name\n')

    def test_an_import_brings_in_only_the_named_module(self):
        self.compile(HOST_LTH)
        self.compile(self.source('util.lth', 'module util\nimport host\npub func beep()\nend\n'))
        app = self.source('app.lth', 'module app\nimport util\npub func main()\n  host.put_byte(1)\nend\n')
        self.fails(app, ':4:3: error 40: undefined name\n')

    def test_a_damaged_interface_is_error_51(self):
        entry = b'\x01' + string(b'f')
        for damaged in (b'',
                        b'XX\x01' + string(b'host') + b'\x00',                      # not an interface
                        b'LI\x02' + string(b'host') + b'\x00',                      # another version
                        b'LI\x01' + string(b'other') + b'\x00',                     # another module's
                        b'LI\x01' + string(b'host'),                                # cut short
                        b'LI\x01' + string(b'host') + entry + b'\x00\x00',          # cut short in an entry
                        b'LI\x01' + string(b'host') + b'\x09' + string(b'f'),       # unknown kind of entry
                        b'LI\x01' + string(b'host') + entry + b'\x00\x01\x09\x01\x00\x00'):   # unknown type
            with open(os.path.join(self.out, 'host.li'), 'wb') as f:
                f.write(damaged)
            self.fails(HELLO_LTH, ':4:8: error 51: not an interface file of this version\n')

    def test_a_function_too_large_for_the_buffer_is_error_75(self):
        self.compile(HOST_LTH)
        big = self.source('big.lth', 'module big\nimport host\npub func main()\n'
                          + '  host.put_byte(1)\n' * 2000 + 'end\n')
        status, errors = support.run_lathec(big, self.out)
        self.assertEqual(status, 1)
        self.assertRegex(errors, r'big\.lth:\d+:\d+: error 75: function too large\n$')

    def test_many_functions_fit_because_each_is_written_when_it_ends(self):
        self.compile(HOST_LTH)
        text = 'module many\nimport host\n'
        for i in range(300):
            text += 'func f%d()\n' % i + '  host.put_byte(1)\n' * 100 + 'end\n'
        self.compile(self.source('many.lth', text))
        self.assertEqual(len(self.code('many')), 300)


class CommandLineTest(CompileTest):
    def test_too_few_arguments_is_error_60(self):
        status, errors = support.run_lathec(HOST_LTH)
        self.assertEqual(status, 1)
        self.assertEqual(errors, 'lathec: error 60: usage: lathec SOURCE.lth OUTDIR [IMPORTDIR...]\n')

    def test_a_source_file_not_called_lth_is_error_61(self):
        for name in ('prog.txt', 'prog', '.lth', '9lives.lth', 'my-prog.lth'):
            path = self.source(name, 'module prog\n')
            self.assertEqual(support.run_lathec(path, self.out),
                             (1, path + ': error 61: source file must be called NAME.lth\n'))

    def test_a_missing_source_file_is_error_62(self):
        path = os.path.join(self.out, 'nothing.lth')
        self.assertEqual(support.run_lathec(path, self.out),
                         (1, path + ': error 62: cannot open the source file\n'))

    def test_an_output_directory_that_does_not_exist_is_error_63(self):
        self.assertEqual(support.run_lathec(HOST_LTH, os.path.join(self.out, 'missing')),
                         (1, HOST_LTH + ': error 63: cannot create the output file\n'))

    def test_too_many_import_directories_is_error_84(self):
        status, errors = support.run_lathec(HOST_LTH, self.out, *['d'] * 20)
        self.assertEqual((status, errors), (1, HOST_LTH + ': error 84: too many directories\n'))

    def test_nothing_is_written_to_standard_output(self):
        import subprocess
        done = subprocess.run([sys.executable, support.LATHEC, HOST_LTH, self.out], capture_output=True)
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, b'', b''))


if __name__ == '__main__':
    unittest.main()
