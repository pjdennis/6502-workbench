"""lathec.py as a program: what it writes for whole modules, and how it answers a bad
command line. The object files are checked against docs/object-format.md record by record."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lathec_support as support  # noqa: E402

END, MOD, IMP, SYM, VAR, FUNC, SLOT, CALL, FIX, CODE, ENDF = 0, 1, 2, 3, 4, 7, 8, 9, 10, 11, 12
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
        pointer_in_ax = b'\x10\x01\x04'          # ^byte in ax
        self.assertEqual(self.interface('host'), b''.join([
            b'LI\x01', string(b'host'),
            b'\x01', string(b'read_byte'), b'\x01\x06\xf0', b'\x00', b'\x02', byte_in_a, bool_in_c,
            b'\x01', string(b'put_byte'), b'\x01\x09\xf0', b'\x01', byte_in_a, b'\x00',
            b'\x01', string(b'put_error'), b'\x01\x0c\xf0', b'\x01', byte_in_a, b'\x00',
            b'\x01', string(b'exit'), b'\x01\x0f\xf0', b'\x01', byte_in_a, b'\x00',
            b'\x01', string(b'open'), b'\x01\x12\xf0', b'\x01', pointer_in_ax, b'\x01', byte_in_a,
            b'\x01', string(b'close'), b'\x01\x15\xf0', b'\x01', byte_in_a, b'\x00',
            b'\x01', string(b'read'), b'\x01\x18\xf0', b'\x01', byte_in_a, b'\x02', byte_in_a,
            bool_in_c,
            b'\x01', string(b'open_out'), b'\x01\x21\xf0', b'\x01', pointer_in_ax, b'\x01',
            byte_in_a,
            b'\x01', string(b'write'), b'\x01\x24\xf0', b'\x02', byte_in_a, b'\x01\x02', b'\x00',
            b'\x01', string(b'argc'), b'\x01\x1b\xf0', b'\x00', b'\x01', byte_in_a,
            b'\x01', string(b'argv'), b'\x01\x1e\xf0', b'\x01', byte_in_a, b'\x01', pointer_in_ax,
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
                          0xA9, 0x0A, 0x4C, 0x09, 0xF0])),  # LDA #10 / JMP $F009: it returns for main
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
        jmp = b'\x4c\x00\x00'           # a call that a return follows
        self.assertEqual(self.records('app'), [
            (MOD, b'\x01\x00' + string(b'app')),
            (IMP, string(b'util')),
            (SYM, b'\x01' + string(b'app.local')),
            (SYM, b'\x01' + string(b'util.beep')),
            (FUNC, b'\x00\x00\x00'),
            (CALL, b'\x01\x00\x00\xff\xff'),
            (FIX, fixup(1, 1, 1, 0xFF, 0)),
            (CODE, jmp),
            (ENDF, b''),
            (SYM, b'\x01' + string(b'app.main')),
            (FUNC, b'\x02\x00\x04'),
            (CALL, b'\x00\x00\x00\xff\xff'),
            (CALL, b'\x01\x00\x00\xff\xff'),
            (FIX, fixup(1, 1, 0, 0xFF, 0) + fixup(4, 1, 1, 0xFF, 0) + fixup(7, 1, 0, 0xFF, 0)),
            (CODE, jsr * 2 + jmp),
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
            0x38, 0xA0, 0x07, 0xA2, 0xAB, 0xA9, 0xCD, 0x20, 0x34, 0x12,     # carry, then Y, X, A
            0x18, 0xA0, 0x02, 0xA2, 0x01, 0x20, 0x00, 0x20,
            0x18, 0xA0, 0x00, 0xA2, 0x00, 0x8A, 0x4C, 0x34, 0x12])])        # TXA: X holds the 0
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
        self.assertEqual(self.code('user'), [bytes([0xA0, 0x01, 0xA2, 0x02, 0xA9, 0x03, 0x4C, 0x00, 0x20])])

    def test_names_and_keywords_are_not_case_sensitive(self):
        self.compile(HOST_LTH)
        self.compile(self.source('Shout.LTH',
                                 'MODULE Shout\nIMPORT Host\nPUB FUNC Main()\n  HOST.Put_Byte(\'H\')\nEND\n'))
        self.assertEqual(self.records('shout')[2], (SYM, b'\x01' + string(b'shout.main')))
        self.assertEqual(self.code('shout'), [bytes([0xA9, 0x48, 0x4C, 0x09, 0xF0])])

    def test_layout_comments_and_line_ends_do_not_matter(self):
        self.compile(HOST_LTH)
        self.compile(self.source('loose.lth',
                                 '; a comment first\n\nmodule loose ; here too\n\nimport host\n\n'
                                 'pub func main()   ; main\n\n  host.put_byte(\n    72\n  )\n\n  return\nend',
                                 newline='\r\n'))
        self.assertEqual(self.code('loose'), [bytes([0xA9, 0x48, 0x4C, 0x09, 0xF0])])

    def test_a_function_can_be_empty_and_a_module_can_have_several(self):
        self.compile(self.source('several.lth',
                                 'module several\nfunc a()\nend\nfunc b()\n  a()\n  return\n  a()\nend\n'))
        # The first call returns for b; nothing can reach what follows the return.
        self.assertEqual(self.code('several'), [b'\x60', b'\x4c\x00\x00'])


class RecordsTest(CompileTest):
    """What stage 2a adds to the object file: slots, variables and the function of initial values."""

    def test_a_function_has_a_slot_for_each_parameter_local_and_temporary(self):
        self.compile(self.source('frame.lth',
                                 'module frame\n'
                                 'func f(a: byte, w: word): byte\n'
                                 '  var n: byte zp\n'
                                 '  var big: word nozp\n'
                                 '  n = a\n'
                                 '  while n != 0 do\n'
                                 '    n -= 1\n'
                                 '  end\n'
                                 '  return (a + n) & (a - n)\n'
                                 'end\n'))
        slots = [body for kind, body in self.records('frame') if kind == SLOT]
        self.assertEqual(slots, [
            b'\x01\x00\x01\x03\x00' + string(b'a'),        # size 1, either, weight 3, parameter
            b'\x02\x00\x01\x00\x00' + string(b'w'),
            b'\x01\x00\x00\x0b\x01' + string(b'n'),        # zp, weight 3 + 2 * 4 in the loop, local
            b'\x02\x00\x02\x00\x01' + string(b'big'),      # never in zero page
            b'\x01\x00\x01\x02\x02' + string(b'$t1'),      # a temporary
        ])

    def test_variables_get_a_symbol_when_declared_and_a_record_with_their_weight_at_the_end(self):
        self.compile(self.source('vars.lth',
                                 'module vars\n'
                                 'var count: byte\n'
                                 'var total: word zp\n'
                                 'var table: word nozp\n'
                                 'var port: byte at $D020\n'
                                 'func f()\n'
                                 '  static var seen: bool\n'
                                 '  count += 1\n'
                                 '  total = count\n'
                                 '  port = count\n'
                                 '  seen = true\n'
                                 'end\n'))
        records = self.records('vars')
        self.assertEqual([body for kind, body in records if kind == SYM], [
            b'\x02' + string(b'vars.count'), b'\x02' + string(b'vars.total'), b'\x02' + string(b'vars.table'),
            b'\x01' + string(b'vars.f'), b'\x02' + string(b'vars.f.seen')])
        self.assertEqual([body for kind, body in records if kind == VAR], [
            b'\x04\x00\x01\x00\x01\x01\x00',         # f.seen, after its function: size 1, weight 1
            b'\x00\x00\x01\x00\x01\x03\x00',         # count: weight 3 (the INC and two loads)
            b'\x01\x00\x02\x00\x00\x02\x00',         # total: zp
            b'\x02\x00\x02\x00\x02\x00\x00'])        # table: never in zero page, not used

    def test_initial_values_become_the_function_init_at_the_end_of_the_module(self):
        self.compile(self.source('start.lth',
                                 'module start\n'
                                 'var a: byte = 7\n'
                                 'var w: word = 7\n'
                                 'func f()\n'
                                 'end\n'))
        records = self.records('start')
        self.assertEqual(records[-6:], [
            (SYM, b'\x01' + string(b'start.$init')),
            (FUNC, b'\x03\x00\x00'),
            (FIX, fixup(3, 1, 0, 0xFF, 0) + fixup(6, 1, 1, 0xFF, 0) + fixup(11, 1, 1, 0xFF, 1)),
            (CODE, bytes([0xA9, 7, 0x8D, 0, 0, 0x8D, 0, 0, 0xA9, 0, 0x8D, 0, 0, 0x60])),
            (ENDF, b''),
            (END, b'')])

    def test_a_module_without_initial_values_has_no_init_function(self):
        self.compile(self.source('plain.lth', 'module plain\nvar a: byte\n'))
        self.assertEqual([kind for kind, _ in self.records('plain')], [MOD, SYM, VAR, END])

    def test_a_long_list_of_initial_values_is_written_out_in_parts_that_call_each_other(self):
        text = 'module many\n' + ''.join('var v%d: byte = %d\n' % (i, i) for i in range(70))
        self.compile(self.source('many.lth', text))
        records = self.records('many')
        names = [body[2:] for kind, body in records if kind == SYM and body[0] == 1]
        self.assertEqual(names, [b'many.$init1', b'many.$init2', b'many.$init'])
        code = self.code('many')
        self.assertEqual([len(c) for c in code], [32 * 5 + 1, 3 + 32 * 5 + 1, 3 + 6 * 5 + 1])
        self.assertEqual((code[1][0], code[2][0]), (0x20, 0x20))        # each part calls the one before
        self.assertEqual([body for kind, body in records if kind == CALL],
                         [b'\x20\x00\x00\xff\xff', b'\x41\x00\x00\xff\xff'])

    def test_too_many_initial_values_in_one_function_is_error_86(self):
        text = 'module full\nfunc f()\n' + ''.join('  static var v%d: byte = 1\n' % i for i in range(65)) + 'end\n'
        status, errors = support.run_lathec(self.source('full.lth', text), self.out)
        self.assertEqual(status, 1)
        self.assertRegex(errors, r'full\.lth:67:\d+: error 86: too many initial values\n$')

    def test_too_many_locals_is_error_85(self):
        text = 'module wide\nfunc f()\n' + ''.join('  var v%d: byte\n' % i for i in range(129)) + 'end\n'
        status, errors = support.run_lathec(self.source('wide.lth', text), self.out)
        self.assertEqual(status, 1)
        self.assertRegex(errors, r'wide\.lth:131:\d+: error 85: too many variables in one function\n$')

    def test_a_forward_function_is_called_before_its_body_and_keeps_its_symbol(self):
        self.compile(self.source('ahead.lth',
                                 'module ahead\n'
                                 'forward func later(n: byte): byte\n'
                                 'func first(): byte\n'
                                 '  return later(3)\n'
                                 'end\n'
                                 'pub func later(n: byte): byte\n'
                                 '  return n\n'
                                 'end\n'))
        records = self.records('ahead')
        self.assertEqual([body for kind, body in records if kind == SYM],
                         [b'\x01' + string(b'ahead.later'), b'\x01' + string(b'ahead.first')])
        self.assertEqual([body for kind, body in records if kind == FUNC], [b'\x01\x00\x00', b'\x00\x00\x04'])
        self.assertEqual(self.code('ahead')[0], bytes([0xA9, 3, 0x8D, 0, 0, 0x4C, 0, 0]))
        self.assertEqual(self.interface('ahead'), b'LI\x01' + string(b'ahead') + b'\x01' + string(b'later')
                         + b'\x00\x01\x01\x00\x01\x01\x01' + b'\x00')


class InterfaceTest(CompileTest):
    LIB = ('module lib\n'
           'pub const LIMIT = 300\n'
           'pub const SMALL: byte = 7\n'
           'pub const BELOW = -2\n'
           'pub const ON = true\n'
           'const SECRET = 1\n'
           'pub var count: byte\n'
           'pub var total: word zp\n'
           'pub var table: int nozp\n'
           'pub var port: byte at $D020\n'
           'var hidden: byte\n'
           'pub func take(n: byte, w: word): word, bool\n'
           '  return w, n == 0\n'
           'end\n'
           'pub func ready(): bool\n'
           '  return true\n'
           'end\n'
           'pub func plain(s: sbyte)\n'
           'end\n')

    def test_constants_variables_and_signatures_are_in_the_interface(self):
        self.compile(self.source('lib.lth', self.LIB))
        self.assertEqual(self.interface('lib'), b''.join([
            b'LI\x01', string(b'lib'),
            b'\x02', string(b'limit'), b'\x06\x2c\x01',           # a number without a type
            b'\x02', string(b'small'), b'\x01\x07\x00',           # a byte
            b'\x02', string(b'below'), b'\x07\xfe\xff',           # a number below zero
            b'\x02', string(b'on'), b'\x05\x01\x00',              # a bool
            b'\x03', string(b'count'), b'\x01\x00',
            b'\x03', string(b'total'), b'\x03\x02',               # zp
            b'\x03', string(b'table'), b'\x04\x04',               # nozp
            b'\x03', string(b'port'), b'\x01\x01\x20\xd0',        # at $D020
            b'\x01', string(b'take'), b'\x00', b'\x02\x01\x00\x03\x00', b'\x02\x03\x04\x05\x07',
            b'\x01', string(b'ready'), b'\x00', b'\x00', b'\x01\x05\x07',
            b'\x01', string(b'plain'), b'\x00', b'\x01\x02\x00', b'\x00',
            b'\x00']))

    def test_an_importer_uses_them_as_its_own(self):
        self.compile(self.source('lib.lth', self.LIB))
        self.compile(self.source('user.lth',
                                 'module user\n'
                                 'import lib\n'
                                 'var w: word\n'
                                 'var ok: bool\n'
                                 'func f()\n'
                                 '  lib.count = lib.SMALL\n'
                                 '  lib.total = lib.LIMIT\n'
                                 '  lib.port = lib.count\n'
                                 '  w, ok = lib.take(lib.count, lib.total)\n'
                                 'end\n'))
        records = self.records('user')
        self.assertEqual([body for kind, body in records if kind == SYM], [
            b'\x02' + string(b'user.w'), b'\x02' + string(b'user.ok'), b'\x01' + string(b'user.f'),
            b'\x02' + string(b'lib.count'), b'\x02' + string(b'lib.total'), b'\x01' + string(b'lib.take')])
        self.assertEqual([body for kind, body in records if kind == VAR],     # only its own
                         [b'\x00\x00\x02\x00\x01\x02\x00', b'\x01\x00\x01\x00\x01\x01\x00'])
        self.assertEqual(self.code('user')[0][:23], bytes([
            0xA9, 0x07, 0x8D, 0, 0,                         # LDA #7 / STA lib.count
            0xA9, 0x2C, 0x85, 0, 0xA9, 0x01, 0x85, 0,       # lib.total is zp: STA zero page, twice
            0xAD, 0, 0, 0x8D, 0x20, 0xD0,                   # LDA lib.count / STA $D020
            0x8D, 0, 0,                                     # A still holds lib.count: the argument
            0xA5]))
        fixes = [body for kind, body in records if kind == FIX][0]
        self.assertEqual(fixes[:32], fixup(3, 1, 3, 0xFF, 0) + fixup(8, 4, 4, 0xFF, 0) + fixup(12, 4, 4, 0xFF, 1)
                         + fixup(14, 1, 3, 0xFF, 0))
        self.assertEqual(fixes[32:40], fixup(20, 1, 5, 0, 0))               # slot 0 of lib.take

    def test_what_is_not_pub_is_not_there(self):
        self.compile(self.source('lib.lth', self.LIB))
        for name in ('SECRET', 'hidden'):
            user = self.source('user.lth', 'module user\nimport lib\nvar n: byte\nfunc f()\n  n = lib.%s\nend\n' % name)
            self.assertEqual(support.run_lathec(user, self.out), (1, user + ':5:11: error 40: undefined name\n'))

    def test_arrays_pointers_and_tables_are_in_the_interface(self):
        self.compile(self.source('lib.lth',
                                 'module lib\n'
                                 'pub const T: [2]word = [1, 2]\n'
                                 'pub var a: [3]byte\n'
                                 'pub var r: [4]word rows\n'
                                 'pub var p: ^^byte\n'
                                 'pub const NOTHING = nil\n'
                                 'pub func f(q: ^[2]byte): ^int\n'
                                 '  return nil\n'
                                 'end\n'))
        self.assertEqual(self.interface('lib'), b''.join([
            b'LI\x01', string(b'lib'),
            b'\x02', string(b't'), b'\x11\x02\x00\x03', b'\x00\x00',     # a table: [2]word
            b'\x03', string(b'a'), b'\x11\x03\x00\x01', b'\x04',         # an array is never in zero page
            b'\x03', string(b'r'), b'\x12\x04\x00\x03', b'\x04',         # stored by row
            b'\x03', string(b'p'), b'\x10\x10\x01', b'\x00',
            b'\x02', string(b'nothing'), b'\x08', b'\x00\x00',
            b'\x01', string(b'f'), b'\x00', b'\x01\x10\x11\x02\x00\x01\x00', b'\x01\x10\x04\x04',
            b'\x00']))
        self.compile(self.source('user.lth',
                                 'module user\n'
                                 'import lib\n'
                                 'var w: word\n'
                                 'func g(i: byte)\n'
                                 '  w = lib.T[i]\n'
                                 '  lib.a[i] = 1\n'
                                 '  lib.p = nil\n'
                                 '  w = word(lib.f(nil))\n'
                                 'end\n'))
        syms = [body for kind, body in self.records('user') if kind == SYM]
        self.assertIn(b'\x03' + string(b'lib.t'), syms)                  # constant data
        self.assertIn(b'\x02' + string(b'lib.a'), syms)

    def test_a_damaged_constant_or_variable_is_error_51(self):
        user = self.source('user.lth', 'module user\nimport lib\n')
        head = b'LI\x01' + string(b'lib')
        for damaged in (head + b'\x02' + string(b'c') + b'\x09\x00\x00\x00',      # unknown type of constant
                        head + b'\x02' + string(b'c') + b'\x00\x00\x00\x00',
                        head + b'\x03' + string(b'v') + b'\x09\x00\x00',          # unknown type of variable
                        head + b'\x03' + string(b'v') + b'\x01\x03\x00',          # unknown placement
                        head + b'\x09' + string(b'x') + b'\x00'):                 # unknown kind of entry
            with open(os.path.join(self.out, 'lib.li'), 'wb') as f:
                f.write(damaged)
            self.assertEqual(support.run_lathec(user, self.out),
                             (1, user + ':2:8: error 51: not an interface file of this version\n'))


    TYPES = ('module lib\n'
             'pub enum Kind\n'
             '  K_A\n'
             '  K_B = 7\n'
             'end\n'
             'pub type Node = record\n'
             '  kind: Kind\n'
             '  next: ^Node\n'
             'end\n'
             'pub type NodePtr = ^Node\n'
             'type Hidden = record\n'
             '  h: word\n'
             'end\n'
             'type Alias = byte\n'
             'pub var nodes: [4]Node\n'
             'pub var secret: ^Hidden\n'
             'pub func first(): NodePtr\n'
             '  return nil\n'
             'end\n')

    def test_types_are_in_the_interface_before_what_uses_them(self):
        self.compile(self.source('lib.lth', self.TYPES))
        node = b'\x13' + string(b'lib') + string(b'node')
        self.assertEqual(self.interface('lib'), b''.join([
            b'LI\x01', string(b'lib'),
            b'\x06', string(b'kind'), b'\x01',                              # an enumeration, pub
            b'\x02', string(b'k_a'), b'\x13' + string(b'lib') + string(b'kind'), b'\x00\x00',
            b'\x02', string(b'k_b'), b'\x13' + string(b'lib') + string(b'kind'), b'\x07\x00',
            b'\x05', string(b'node'), b'\x01', b'\x02',                      # a record of two fields
            string(b'kind'), b'\x13' + string(b'lib') + string(b'kind'),
            string(b'next'), b'\x10' + node,
            b'\x04', string(b'nodeptr'), b'\x01', b'\x10' + node,          # another name for ^Node
            b'\x05', string(b'hidden'), b'\x00', b'\x01', string(b'h'), b'\x03',   # not pub
            b'\x03', string(b'nodes'), b'\x11\x04\x00' + node, b'\x04',    # the alias is not there
            b'\x03', string(b'secret'), b'\x10\x13' + string(b'lib') + string(b'hidden'), b'\x00',
            b'\x01', string(b'first'), b'\x00', b'\x00', b'\x01\x10' + node + b'\x04',
            b'\x00']))

    def test_an_importer_uses_the_records_and_enumerations_of_another_module(self):
        self.compile(self.source('lib.lth', self.TYPES))
        self.compile(self.source('user.lth',
                                 'module user\n'
                                 'import lib\n'
                                 'var n: lib.Node\n'
                                 'var p: lib.NodePtr\n'
                                 'var k: lib.Kind\n'
                                 'func f()\n'
                                 '  n.kind = lib.K_B\n'
                                 '  p = lib.first()\n'
                                 '  p.next = @n\n'
                                 '  lib.nodes[1] = n\n'
                                 '  k = lib.nodes[2].kind\n'
                                 '  lo(lib.secret.h) = 0\n'
                                 'end\n'))
        self.assertIn((VAR, b'\x00\x00\x03\x00\x02\x04\x00'), self.records('user'))   # n: 3 bytes, never in zero page

    def test_a_type_a_module_does_not_export_cannot_be_named(self):
        self.compile(self.source('lib.lth', self.TYPES))
        for name in ('Hidden', 'Alias'):
            user = self.source('user.lth', 'module user\nimport lib\nvar h: lib.%s\n' % name)
            self.assertEqual(support.run_lathec(user, self.out), (1, user + ':3:12: error 40: undefined name\n'))

    def test_an_importer_must_import_the_modules_whose_types_an_interface_uses(self):
        self.compile(self.source('lib.lth', self.TYPES))
        self.compile(self.source('mid.lth', 'module mid\nimport lib\npub var p: ^lib.Node\n'))
        self.compile(self.source('ok.lth', 'module ok\nimport lib\nimport mid\nvar q: ^lib.Node\n'
                                 'func f()\n  q = mid.p\nend\n'))
        user = self.source('user.lth', 'module user\nimport mid\n')
        self.assertEqual(support.run_lathec(user, self.out),
                         (1, user + ':2:8: error 135: an imported module uses the types of a module '
                                    'not imported yet: import that one first\n'))

    def test_records_of_two_modules_are_different_types_even_with_the_same_fields(self):
        self.compile(self.source('one.lth', 'module one\npub type R = record\n  a: byte\nend\n'))
        self.compile(self.source('two.lth', 'module two\npub type R = record\n  a: byte\nend\n'))
        user = self.source('user.lth', 'module user\nimport one\nimport two\nvar x: one.R\nvar y: two.R\n'
                           'func f()\n  x = y\nend\n')
        self.assertEqual(support.run_lathec(user, self.out), (1, user + ':7:7: error 44: wrong type\n'))

    def test_a_damaged_type_entry_is_error_51(self):
        user = self.source('user.lth', 'module user\nimport lib\n')
        head = b'LI\x01' + string(b'lib')
        for damaged in (head + b'\x03' + string(b'v') + b'\x13' + string(b'lib') + string(b'none') + b'\x00\x00',
                        head + b'\x04' + string(b'x') + b'\x01\x09',          # an unknown type
                        head + b'\x07' + string(b'x') + b'\x00'):              # an unknown kind of entry
            with open(os.path.join(self.out, 'lib.li'), 'wb') as f:
                f.write(damaged)
            self.assertEqual(support.run_lathec(user, self.out),
                             (1, user + ':2:8: error 51: not an interface file of this version\n'))


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
        self.assertEqual(errors, 'lathec: error 60: usage: lathec [-c6502|-c65c02] [-dNAME[=NUMBER]]... '
                                 'SOURCE.lth OUTDIR [IMPORTDIR...]\n')

    def test_options_must_be_ones_it_knows(self):
        path = self.source('prog.lth', 'module prog\n')
        for option in ('-x', '-c', '-c6800', '-c65c02x', '-d', '-d9a', '-da-b', '-dx=', '-dx=1a',
                       '-dx=65536', '-dend', '-'):
            with self.subTest(option=option):
                status, errors = support.run_lathec(option, path, self.out)
                self.assertEqual(status, 1)
                self.assertTrue(errors.startswith('lathec: error 60: usage'), errors)
        self.assertEqual(support.run_lathec('-dx', '-dX', path, self.out),
                         (1, 'lathec: error 41: name already declared\n'))
        self.assertEqual(support.run_lathec('-c6502', path)[0], 1)

    def test_the_cpu_option_sets_the_cpu_of_the_module(self):
        path = self.source('prog.lth', 'module prog\n')
        for options, cpu in (((), 0), (('-c6502',), 0), (('-c65C02',), 1), (('-c65c02', '-c6502'), 0)):
            with self.subTest(options=options):
                self.assertEqual(support.run_lathec(*options, path, self.out), (0, ''))
                self.assertEqual(self.records('prog')[0], (MOD, bytes([1, cpu]) + string(b'prog')))

    def test_options_predeclare_constants(self):
        path = self.source('prog.lth', 'module prog\n'
                           '#if cpu_65c02 and LEVEL < 2\nconst A = 1\n#else\nconst A = 2\n#end\n'
                           'pub const B: word = SIZE + A\n')
        for options, b in ((('-dSIZE=1000', '-dlevel=1'), 1002), (('-c65c02', '-dSize=0', '-dLEVEL=1'), 1),
                           (('-dlevel=2', '-c65c02', '-dsize=65533'), 65535)):
            with self.subTest(options=options):
                self.assertEqual(support.run_lathec(*options, path, self.out), (0, ''))
                self.assertEqual(self.interface('prog'), b'LI\x01' + string(b'prog') + b'\x02'
                                 + string(b'b') + bytes([3, b & 0xFF, b >> 8, 0]))

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
