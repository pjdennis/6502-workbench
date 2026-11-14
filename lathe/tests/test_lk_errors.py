"""Every link error: `link error N: text` with the names involved on the error output, exit
status 1. Capacities are part of this: exceeding one is a numbered error, not a crash.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lk_support import (Obj, link, record, word, string, HOST_ENV, MUST, EITHER, NEVER,  # noqa: E402
                             PARAM, LOCAL, NOBODY, INTERRUPT, POINTER)

ENV = 'cpu 6502\nzeropage $00 $FF\ncode $0200 $BFFF\ndata $C000 $EFFF\nexit return\n'


def simple(name='t'):
    o = Obj(name)
    o.func('main', b'\x60')
    return o


def caller(o, name, callees, slots=(), flags=0):
    c = o.code()
    calls = []
    for callee in callees:
        c.abs(0x20, o.f(callee))
        calls.append((o.f(callee), 0, NOBODY))
    c.raw(0x60)
    o.func(name, c, slots=slots, calls=calls, flags=flags)


class ErrorTest(unittest.TestCase):
    def assertError(self, r, number, text, *names):
        self.assertEqual(r.status, 1, r.errors)
        line = r.errors.strip()
        self.assertEqual(len(r.errors.strip().splitlines()), 1, r.errors)
        self.assertTrue(line.startswith('link error %d: %s' % (number, text)), line)
        for name in names:
            self.assertIn(name, line)
        return line


class CommandLineAndFiles(ErrorTest):
    def test_too_few_arguments(self):
        r = link([simple()], args=['a', 'b', 'c', 'd'])
        self.assertError(r, 1, 'usage: link ENV MAINMODULE OUT.bin OUT.map OBJECT.lo...')

    def test_missing_object_file(self):
        r = link([simple()], args=['/nonexistent/x.env', 't', '/tmp/x.bin', '/tmp/x.map', '/nonexistent/t.lo'])
        self.assertError(r, 2, 'cannot open file', '/nonexistent/x.env')

    def test_no_main(self):
        r = link([simple()], ENV, main='other')
        self.assertEqual(r.errors, 'link error 20: no main function: other.main\n')

    def test_main_must_be_a_function(self):
        o = simple()
        o.var('x.main', 1)
        r = link([o], ENV, main='x')
        self.assertError(r, 20, 'no main function', 'x.main')


class EnvironmentFile(ErrorTest):
    def test_bad_number(self):
        self.assertError(link([simple()], ENV.replace('$0200', '$02G0')), 3, 'environment file: bad entry')

    def test_number_too_large(self):
        self.assertError(link([simple()], ENV.replace('$BFFF', '$1BFFF')), 3, 'environment file: bad entry')

    def test_unknown_cpu(self):
        self.assertError(link([simple()], ENV.replace('6502', 'z80')), 3, 'environment file: bad entry')

    def test_unknown_exit(self):
        self.assertError(link([simple()], ENV.replace('return', 'never')), 3, 'environment file: bad entry')

    def test_entry_given_twice(self):
        for line in ('cpu 6502', 'zeropage $00 $10', 'code $0200 $0300', 'data $C000 $C001', 'stack $80',
                     'exit loop'):
            env = ENV + 'stack $FF\n' + line + '\n'
            self.assertError(link([simple()], env), 3, 'environment file: bad entry')

    def test_start_entry_of_the_earlier_format(self):
        self.assertError(link([simple()], ENV + 'start host_start.start\n'), 3, 'environment file: bad entry')

    def test_stack_must_be_a_byte(self):
        self.assertError(link([simple()], ENV + 'stack $100\n'), 3, 'environment file: bad entry')

    def test_missing_entry(self):
        for entry in ('zeropage', 'code', 'data', 'exit'):
            env = ''.join(line + '\n' for line in ENV.splitlines() if not line.startswith(entry))
            self.assertError(link([simple()], env), 4,
                             'environment file: zeropage, code, data and exit must all be given')

    def test_bad_ranges(self):
        for old, new in (('$00 $FF', '$80 $7F'), ('$00 $FF', '$00 $100'), ('$0200 $BFFF', '$0080 $BFFF'),
                         ('$C000 $EFFF', '$C000 $BFFF'), ('$C000 $EFFF', '$0000 $FFFF')):
            self.assertError(link([simple()], ENV.replace(old, new)), 34, 'environment file: bad address range')

    def test_comments_blank_lines_case_and_unknown_entries_are_accepted(self):
        env = ('; a machine\n\nCPU 65C02 ; comment\n  zeropage\t$10 $1f\ncode 512 $BFFF\n'
               'data $c000 $efff\ndefine HAS_LCD\ndefine SIZE $10\nregion LOW $0200-$7FFF ram fixed\nexit Return')
        r = link([simple()], env)
        self.assertEqual((r.status, r.errors), (0, ''))
        self.assertEqual(r.map_text, 'F 0200 0005 $start\nF 0205 0001 t.main\n')


class ObjectFiles(ErrorTest):
    def test_wrong_version(self):
        o = Obj('t', version=2)
        o.func('main', b'\x60')
        self.assertError(link([o], ENV), 5, 'unsupported object version', 'm0.lo')

    def test_not_an_object_file(self):
        self.assertError(link([b'hello, world'], ENV, main='t'), 5, 'unsupported object version')

    def test_initial_values_are_no_longer_supported(self):
        o = simple()
        o.var('x', 2, NEVER, flags=1, init=b'\x01\x02')
        self.assertError(link([o], ENV), 5, 'unsupported object version', 'm0.lo')

    def test_cut_short(self):
        data = simple().to_bytes()
        for cut in (len(data) - 3, len(data) - 1, 9):
            self.assertError(link([data[:cut]], ENV, main='t'), 6, 'object file is damaged', 'm0.lo')

    def test_unknown_record(self):
        o = simple()
        o.raw(0x55, b'??')
        self.assertError(link([o], ENV), 6, 'object file is damaged')

    def test_slot_outside_a_function(self):
        o = simple()
        o.raw(8, word(1) + bytes((1, 0, 1)) + string('x'))
        self.assertError(link([o], ENV), 6, 'object file is damaged')

    def test_symbol_number_out_of_range(self):
        o = simple()
        o.raw(4, word(99) + word(1) + bytes((1, 0, 0)))
        self.assertError(link([o], ENV), 6, 'object file is damaged')

    def test_definition_of_the_wrong_kind_of_symbol(self):
        o = simple()
        o.raw(4, word(o.f('main')) + word(1) + bytes((1, 0, 0)))
        self.assertError(link([o], ENV), 6, 'object file is damaged')

    def test_65c02_object_for_a_6502(self):
        o = Obj('t', cpu=1)
        o.func('main', b'\x60')
        self.assertError(link([o], ENV), 7, 'object file needs a 65C02', 'm0.lo')
        self.assertEqual(link([o], ENV.replace('6502', '65c02')).status, 0)


class Symbols(ErrorTest):
    def test_defined_twice(self):
        a = simple('a')
        a.func('b.f', b'\x60')
        b = Obj('b')
        b.func('f', b'\x60')
        self.assertEqual(link([a, b], ENV).errors, 'link error 17: symbol defined twice: b.f\n')

    def test_variable_defined_twice(self):
        o = simple()
        o.var('x', 1)
        o.var('x', 1)
        self.assertError(link([o], ENV), 17, 'symbol defined twice', 't.x')

    def test_undefined(self):
        o = Obj('t')
        caller(o, 'main', ['lib.missing'])
        self.assertEqual(link([o], ENV).errors, 'link error 18: undefined symbol: lib.missing\n')

    def test_two_kinds(self):
        a = simple('a')
        a.v('b.thing')
        b = Obj('b')
        b.func('thing', b'\x60')
        self.assertEqual(link([a, b], ENV).errors, 'link error 19: symbol used as two kinds of thing: b.thing\n')


class Storage(ErrorTest):
    def test_zero_page_full_names_the_chain_that_needs_most(self):
        o = Obj('t')
        caller(o, 'main', ['a', 'c'], [(1, MUST, 0, LOCAL, 'm')])
        caller(o, 'a', ['b'], [(2, MUST, 0, LOCAL, 'x')])
        caller(o, 'b', [], [(2, MUST, 0, LOCAL, 'y')])
        caller(o, 'c', [], [(3, MUST, 0, LOCAL, 'z')])
        r = link([o], ENV.replace('$00 $FF', '$00 $03'))
        self.assertEqual(r.errors, 'link error 25: zero page is full: t.main -> t.a -> t.b\n')
        self.assertEqual(link([o], ENV.replace('$00 $FF', '$00 $04')).status, 0)

    def test_zero_page_full_of_variables(self):
        o = simple()
        o.var('a', 2, MUST)
        o.var('b', 2, MUST)
        r = link([o], ENV.replace('$00 $FF', '$00 $02'))
        self.assertEqual(r.errors, 'link error 25: zero page is full\n')

    def test_one_item_larger_than_zero_page(self):
        o = simple()
        o.var('huge', 300, MUST)
        self.assertEqual(link([o], ENV).errors, 'link error 25: zero page is full: t.huge\n')

    def test_data_range_full(self):
        o = Obj('t')
        o.var('v', 6, NEVER)
        caller(o, 'main', ['f'], [(4, NEVER, 0, LOCAL, 'm')])
        caller(o, 'f', [], [(7, NEVER, 0, LOCAL, 'x')])
        r = link([o], ENV.replace('$C000 $EFFF', '$C000 $C00F'))
        self.assertEqual(r.errors, 'link error 26: variables do not fit in the data range: t.main -> t.f\n')
        self.assertEqual(link([o], ENV.replace('$C000 $EFFF', '$C000 $C010')).status, 0)

    def test_more_data_than_64k(self):
        o = Obj('t')
        caller(o, 'main', ['f'], [(40000, NEVER, 0, LOCAL, 'm')])
        caller(o, 'f', [], [(40000, NEVER, 0, LOCAL, 'x')])
        self.assertError(link([o], ENV), 26, 'variables do not fit in the data range')

    def test_code_range_full(self):
        o = Obj('t')
        o.func('main', bytes(11) + b'\x60')
        o.data('$1', bytes(5))
        # $start is 5 bytes here, main 12, the constant 5: 22 bytes.
        self.assertEqual(link([o], ENV.replace('$0200 $BFFF', '$0200 $0214')).errors,
                         'link error 27: code does not fit in the code range\n')
        self.assertEqual(link([o], ENV.replace('$0200 $BFFF', '$0200 $0215')).status, 0)


class FixUps(ErrorTest):
    def test_not_on_an_operand(self):
        o = Obj('t')
        v = o.var('x', 1, NEVER)
        c = o.code().raw(0xEA)
        c.fixes.append((1, 1, v, 0xFF, 0))         # points at an opcode
        c.raw(0xEA, 0xEA, 0x60)
        o.func('main', c)
        self.assertEqual(link([o], ENV).errors, 'link error 29: bad fix-up: t.main\n')

    def test_two_bytes_in_a_two_byte_instruction(self):
        o = Obj('t')
        v = o.var('x', 1, NEVER)
        c = o.code().raw(0xA9)
        c.fixes.append((1, 1, v, 0xFF, 0))
        c.raw(0x00, 0x60)
        o.func('main', c)
        self.assertError(link([o], ENV), 29, 'bad fix-up', 't.main')

    def test_out_of_order(self):
        o = Obj('t')
        v = o.var('x', 1, NEVER)
        c = o.code().abs(0xAD, v).abs(0xAD, v).raw(0x60)
        c.fixes.reverse()
        o.func('main', c)
        self.assertError(link([o], ENV), 29, 'bad fix-up', 't.main')

    def test_beyond_the_code(self):
        o = Obj('t')
        v = o.var('x', 1, NEVER)
        c = o.code().raw(0x60)
        c.fixes.append((7, 2, v, 0xFF, 0))
        o.func('main', c)
        self.assertError(link([o], ENV), 29, 'bad fix-up', 't.main')

    def test_unknown_kind(self):
        o = Obj('t')
        v = o.var('x', 1, NEVER)
        c = o.code().byte(0xA9, 5, v).raw(0x60)
        o.func('main', c)
        self.assertError(link([o], ENV), 29, 'bad fix-up', 't.main')

    def test_slot_that_the_function_does_not_have(self):
        o = Obj('t')
        m = o.f('main')
        o.func('main', o.code().abs(0xAD, m, slot=2).raw(0x60), slots=[(1, NEVER, 0, LOCAL, 'a')])
        self.assertError(link([o], ENV), 29, 'bad fix-up', 't.main')

    def test_in_constant_data(self):
        o = simple()
        v = o.var('x', 1, NEVER)
        o.data('$1', b'\0\0', fixes=[(1, 1, v, 0xFF, 0)])
        self.assertEqual(link([o], ENV).errors, 'link error 29: bad fix-up: t.$1\n')

    def test_instruction_cut_off(self):
        o = Obj('t')
        o.func('main', b'\x60\xAD\x00')
        self.assertError(link([o], ENV), 6, 'object file is damaged')

    def test_zero_page_fix_up_to_something_outside_zero_page(self):
        o = Obj('t')
        v = o.var('x', 2, NEVER)
        o.func('main', o.code().byte(0xB1, 4, v).raw(0x60))
        self.assertEqual(link([o], ENV).errors, 'link error 30: address must be in zero page: t.x, t.main\n')

    def test_call_without_a_call_record(self):
        o = Obj('t')
        o.func('main', o.code().abs(0x20, o.f('f')).raw(0x60))
        o.func('f', b'\x60')
        self.assertEqual(link([o], ENV).errors,
                         'link error 31: call of a function that was not linked: t.f, t.main\n')

    def test_the_address_of_a_function_keeps_it(self):
        # Nothing calls f, but main takes its address: f is kept, so the address is real.
        o = Obj('t')
        f = o.f('f')
        o.func('main', o.code().byte(0xA9, 2, f).byte(0xA2, 3, f).raw(0x60))
        o.func('f', b'\x60')
        o.data('$1', b'\0\0', fixes=[(0, 1, f, 0xFF, 0)])
        r = link([o], ENV)
        self.assertEqual(r.addr('F', 't.f'), 0x020A)
        self.assertEqual(r.code('t.main'), bytes.fromhex('A90A A202 60'))
        self.assertEqual(r.at(r.addr('D', 't.$1'), 2), b'\x0a\x02')

    def test_but_a_jsr_without_a_call_record_keeps_nothing_in_another_context(self):
        o = Obj('t')
        f = o.f('f')
        o.func('main', o.code().byte(0xA9, 2, f).raw(0x60))
        o.func('irq', o.code().abs(0x20, f).raw(0x40), flags=INTERRUPT)
        o.func('f', b'\x60')
        self.assertEqual(link([o], ENV).errors,
                         'link error 31: call of a function that was not linked: t.f, t.irq\n')

    def test_vector_overwritten_by_code(self):
        o = Obj('t')
        o.func('main', bytes(8) + b'\x60')
        r = link([o], ENV.replace('$0200 $BFFF', '$FFF0 $FFFF').replace('$C000 $EFFF', '$C000 $CFFF'))
        self.assertEqual(r.errors, 'link error 32: parts of the image overlap\n')


class Capacities(ErrorTest):
    def test_objects(self):
        objs = [simple()] + [Obj('m%d' % i) for i in range(64)]
        self.assertEqual(link(objs, ENV).errors, 'link error 8: too many object files\n')

    def test_symbols(self):
        o = simple()
        for i in range(2048):
            o.v('v%d' % i)
        self.assertEqual(link([o], ENV).errors, 'link error 9: too many symbols\n')

    def test_names(self):
        o = simple()
        for i in range(100):
            o.v('n%03d%s' % (i, 'x' * 200))
        self.assertEqual(link([o], ENV).errors, 'link error 10: too many or too long names\n')

    def test_functions(self):
        o = simple()
        for i in range(1024):
            o.func('f%d' % i, b'\x60')
        self.assertEqual(link([o], ENV).errors, 'link error 11: too many functions\n')

    def test_slots(self):
        o = simple()
        for i in range(33):
            o.func('f%d' % i, b'\x60', slots=[(1, NEVER, 0, LOCAL, 's')] * 250)
        self.assertEqual(link([o], ENV).errors, 'link error 12: too many slots\n')

    def test_more_slots_than_a_function_can_have(self):
        o = Obj('t')
        o.func('main', b'\x60', slots=[(1, NEVER, 0, LOCAL, 's')] * 256)
        self.assertError(link([o], ENV), 6, 'object file is damaged')

    def test_calls(self):
        o = Obj('t')
        names = ['f%d' % i for i in range(130)]
        caller(o, 'main', names)
        for i, name in enumerate(names):
            caller(o, name, names[i + 1:] + ['leaf%d' % i])
            o.func('leaf%d' % i, b'\x60')
        self.assertEqual(link([o], ENV).errors, 'link error 13: too many calls\n')

    def test_classes(self):
        o = simple()
        for i in range(65):
            o.clas('k%d' % i, [1])
        self.assertEqual(link([o], ENV).errors,
                         'link error 14: too many pointer classes or class parameters\n')

    def test_class_parameters(self):
        o = simple()
        for i in range(3):
            o.clas('k%d' % i, [1] * 100)
        self.assertError(link([o], ENV), 14, 'too many pointer classes or class parameters')

    def test_copies(self):
        o = Obj('t')
        names = ['f%d' % i for i in range(200)]
        caller(o, 'main', names)
        for name in names:
            o.func(name, b'\x60')
        for i in range(7):
            caller(o, 'irq%d' % i, names, flags=INTERRUPT)
        self.assertEqual(link([o], ENV).errors,
                         'link error 15: too many functions and copies of functions\n')

    def test_contexts(self):
        o = simple()
        for i in range(8):
            o.func('irq%d' % i, b'\x40', flags=INTERRUPT)
        self.assertEqual(link([o], ENV).errors, 'link error 16: too many interrupt functions\n')

    def test_sites(self):
        o = Obj('t')
        v = o.var('z', 1, MUST)
        c = o.code()
        for i in range(1025):
            c.abs(0xEE, v)
        c.raw(0x60)
        o.func('main', c)
        self.assertEqual(link([o], ENV).errors,
                         'link error 28: too many zero page operands in one function: t.main\n')

    def test_local_symbols(self):
        objs = [simple()]
        for m in range(3):
            o = Obj('m%d' % m)
            for i in range(1400):
                o.v('t.v%d' % i)
            objs.append(o)
        self.assertEqual(link(objs, ENV).errors, 'link error 33: too many symbols in the object files together\n')

    def test_members(self):
        o = simple()
        o.clas('k', [])
        for i in range(257):
            o.memb('k', 'main')
        self.assertEqual(link([o], ENV).errors, 'link error 35: too many functions whose address is taken\n')

    def test_definitions(self):
        o = simple()
        for i in range(1025):
            o.var('v%d' % i, 1)
        self.assertEqual(link([o], ENV).errors, 'link error 36: too many variables and constants\n')

    def test_addresses_taken(self):
        # Each record notes a function once; 35 records naming the same 30 is 1050 notes.
        o = simple()
        names = ['f%d' % i for i in range(30)]
        for name in names:
            o.func(name, b'\x60')
        fixes = [(2 * i, 1, o.f(name), 0xFF, 0) for i, name in enumerate(names)]
        for i in range(35):
            o.data('$%d' % i, bytes(60), fixes=fixes)
        self.assertEqual(link([o], ENV).errors,
                         'link error 38: too many functions whose address a fix-up takes\n')


if __name__ == '__main__':
    unittest.main()
