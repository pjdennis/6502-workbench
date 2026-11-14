"""The linker's image: start-up code, placement, fix-ups, shrinking and branch correction.

Every expectation here was worked out by hand from lathe/docs/object-format.md.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lk_support import (Obj, link, keep, HOST_ENV, MUST, EITHER, NEVER, PARAM, LOCAL, NOBODY)  # noqa: E402

START = bytes.fromhex('A2FF9AD8200C02A9004C0FF0')     # host.env, main at $020C


class SmallestProgram(unittest.TestCase):
    def setUp(self):
        o = Obj('t')
        o.func('main', b'\x60')
        self.r = link([o])

    def test_links(self):
        self.assertEqual((self.r.status, self.r.errors), (0, ''))

    def test_image_runs_from_code_start_to_ffff(self):
        self.assertEqual(len(self.r.image), 0x10000 - 0x0200)

    def test_start_code_is_first_and_calls_main(self):
        self.assertEqual(self.r.at(0x0200, 12), START)
        self.assertEqual(self.r.at(0x020C, 1), b'\x60')

    def test_reset_vector_points_at_start(self):
        self.assertEqual(self.r.at(0xFFFC, 2), b'\x00\x02')

    def test_everything_else_is_zero(self):
        self.assertEqual(self.r.at(0x020D, 0xFFFC - 0x020D), bytes(0xFFFC - 0x020D))
        self.assertEqual(self.r.at(0xFFFE, 2), b'\0\0')

    def test_map(self):
        self.assertEqual(self.r.map_text, 'F 0200 000C $start\nF 020C 0001 t.main\n')


class StartCode(unittest.TestCase):
    ENV = 'cpu 6502\nzeropage $00 $FF\ncode $1000 $1FFF\ndata $2000 $2FFF\n'

    def program(self):
        o = Obj('t')
        o.func('main', b'\x60')
        return [o]

    def test_without_stack_and_exit_loop(self):
        r = link(self.program(), self.ENV + 'exit loop\n')
        # CLD / JSR main / JMP to itself
        self.assertEqual(r.at(0x1000, 7), bytes.fromhex('D8 200710 4C0410'))
        self.assertEqual(r.map_text, 'F 1000 0007 $start\nF 1007 0001 t.main\n')
        self.assertEqual(r.at(0xFFFC, 2), b'\x00\x10')

    def test_exit_return(self):
        r = link(self.program(), self.ENV + 'stack $7F\nexit return\n')
        self.assertEqual(r.at(0x1000, 8), bytes.fromhex('A27F9A D8 200810 60'))

    def test_init_functions_are_called_in_object_order(self):
        a = Obj('a')
        a.func('main', b'\x60')
        a.func('$init', b'\xEA\x60')
        b = Obj('b')
        b.func('unused', b'\x60')
        b.func('$init', b'\x60')
        r = link([a, b], self.ENV + 'exit return\n')
        # $start: CLD / JSR $init / JSR main / RTS = 8 bytes; $init: two JSRs and RTS.
        self.assertEqual(r.at(0x1000, 8), bytes.fromhex('D8 200810 200F10 60'))
        self.assertEqual(r.at(0x1008, 7), bytes.fromhex('201010 201210 60'))
        self.assertEqual(r.map_text,
                         'F 1000 0008 $start\nF 1008 0007 $init\n'
                         'F 100F 0001 a.main\nF 1010 0002 a.$init\nF 1012 0001 b.$init\n')

    def test_main_module_name_is_folded_to_lower_case(self):
        r = link(self.program(), self.ENV + 'exit return\n', main='T')
        self.assertEqual(r.status, 0)


class Placement(unittest.TestCase):
    def test_functions_and_constants_in_object_then_record_order(self):
        a = Obj('a')
        f = a.f('b.f')
        c = a.code().abs(0x20, f).raw(0x60)
        a.func('main', c, calls=[(f, 0, NOBODY)])
        a.data('$1', b'hi')
        b = Obj('b')
        b.data('$1', b'\x01\x02\x03')
        b.func('f', b'\xEA\x60')
        keep(b, 'a.$1', '$1')
        r = link([a, b])
        self.assertEqual(r.map_text,
                         'F 0200 000C $start\nF 020C 0004 a.main\nF 0215 0002 b.f\nF 0217 0007 b.keep 1\n'
                         'D 0210 0002 a.$1\nD 0212 0003 b.$1\n')
        self.assertEqual(r.at(0x020C, 9), bytes.fromhex('201502 60') + b'hi\x01\x02\x03')
        self.assertEqual(r.at(0x0215, 2), b'\xEA\x60')

    def test_unreachable_functions_are_dropped(self):
        o = Obj('t')
        o.func('unused', b'\xEA\xEA\x60')
        o.func('main', b'\x60')
        o.func('alsounused', b'\x60')
        r = link([o])
        self.assertEqual(r.map_text, 'F 0200 000C $start\nF 020C 0001 t.main\n')

    def test_a_function_reached_only_through_another_is_kept(self):
        o = Obj('t')
        g = o.f('g')
        h = o.f('h')
        o.func('main', o.code().abs(0x20, g).raw(0x60), calls=[(g, 0, NOBODY)])
        o.func('g', o.code().abs(0x4C, h), calls=[(h, 0, NOBODY)])
        o.func('h', b'\x60')
        r = link([o])
        self.assertEqual(r.code('t.main'), bytes.fromhex('201002 60'))
        self.assertEqual(r.code('t.g'), bytes.fromhex('4C1302'))
        self.assertEqual(r.addr('F', 't.h'), 0x0213)


class FixUps(unittest.TestCase):
    def test_kinds_and_addends(self):
        o = Obj('t')
        v = o.var('big', 4, NEVER)
        z = o.var('ptr', 2, MUST)
        d = o.d('$1')
        c = o.code()
        c.byte(0xA9, 2, d, add=1)                   # LDA #<($1+1)
        c.byte(0xA2, 3, d, add=1)                   # LDX #>($1+1)
        c.abs(0x8D, v, add=3)                       # STA big+3
        c.byte(0x91, 4, z)                          # STA (ptr),Y
        c.byte(0x85, 4, z, add=1)                   # STA ptr+1
        c.raw(0x60)
        o.func('main', c)
        o.data('$1', b'abc')
        r = link([o])
        # main is 12 bytes at $020C, so $1 is at $0218; big at $C000, ptr at $00.
        self.assertEqual(r.code('t.main'), bytes.fromhex('A919 A202 8D03C0 9100 8501 60'))
        self.assertEqual(r.map_text.splitlines()[2:], ['D 0218 0003 t.$1', 'V C000 0004 t.big', 'V 0000 0002 t.ptr'])

    def test_fix_ups_in_constant_data(self):
        o = Obj('t')
        f = o.f('main')
        v = o.var('x', 2, NEVER)
        d = o.d('$2')
        o.func('main', b'\x60')
        o.data('$1', b'\xEE\0\0\xEE\0\0\0\0\xEE',
               fixes=[(1, 1, f, 0xFF, 0), (3, 2, v, 0xFF, 1), (4, 3, v, 0xFF, 1), (5, 1, d, 0xFF, 2)])
        o.data('$2', b'xyz')
        keep(o, '$1')
        r = link([o])
        # main at $020C; $1 at $020D (9 bytes); $2 at $0216; x at $C000.
        self.assertEqual(r.at(0x020D, 9), bytes.fromhex('EE 0C02 01 C0 1802 00 EE'))

    def test_slot_fix_ups_reach_the_callee_frame(self):
        o = Obj('t')
        g = o.f('g')
        c = o.code().raw(0xA9, 7).abs(0x8D, g, slot=0).abs(0x8D, g, slot=1, add=1).abs(0x20, g).raw(0x60)
        o.func('main', c, calls=[(g, 0, NOBODY)], slots=[(3, NEVER, 0, LOCAL, 'm')])
        o.func('g', b'\x60', slots=[(1, NEVER, 0, PARAM, 'a'), (2, NEVER, 0, PARAM, 'b')])
        r = link([o])
        # main's frame is $C000-$C002, g's starts at $C003: a at $C003, b at $C004.
        self.assertEqual(r.code('t.main'), bytes.fromhex('A907 8D03C0 8D05C0 201802 60'))


def loop_program():
    """main with one "either" byte slot i:

         0  LDA i        3  BEQ 8        5  INC i        8  LDA i
        11  BNE 0       13  JMP 8       16  RTS
    """
    o = Obj('t')
    m = o.f('main')
    c = o.code()
    c.abs(0xAD, m, slot=0)
    c.branch(0xF0, 8)
    c.abs(0xEE, m, slot=0)
    c.abs(0xAD, m, slot=0)
    c.branch(0xD0, 0)
    c.abs(0x4C, m, add=8)
    c.raw(0x60)
    o.func('main', c, slots=[(1, EITHER, 5, LOCAL, 'i')])
    o.var('held', 1, MUST)
    keep(o, 'held')
    return o


class Shrinking(unittest.TestCase):
    ENV = 'cpu 6502\ncode $0200 $BFFF\ndata $C000 $EFFF\nstack $FF\nexit call $F00F\n'

    def test_slot_in_zero_page_shrinks_and_moves_branches_and_labels(self):
        r = link([loop_program()], self.ENV + 'zeropage $10 $1F\n')
        self.assertEqual(r.addr('S', 't.main', 0), 0x11)        # $10 is the variable `held`
        self.assertEqual(r.code('t.main'),
                         bytes.fromhex('A511 F002 E611 A511 D0F6 4C1202 60'))

    def test_same_object_with_no_zero_page_left_keeps_the_written_layout(self):
        r = link([loop_program()], self.ENV + 'zeropage $10 $10\n')
        self.assertEqual(r.addr('S', 't.main', 0), 0xC000)
        self.assertEqual(r.code('t.main'),
                         bytes.fromhex('AD00C0 F003 EE00C0 AD00C0 D0F3 4C1402 60'))

    def test_sizes_in_the_map_follow(self):
        small = link([loop_program()], self.ENV + 'zeropage $10 $1F\n')
        large = link([loop_program()], self.ENV + 'zeropage $10 $10\n')
        self.assertEqual((small.size('F', 't.main'), large.size('F', 't.main')), (14, 17))

    def test_only_opcodes_with_a_zero_page_form_shrink(self):
        o = Obj('t')
        v = o.var('z', 2, MUST)
        c = o.code()
        c.abs(0xB9, v)              # LDA z,Y    no zero page,Y form
        c.abs(0xBE, v)              # LDX z,Y -> LDX zp,Y
        c.abs(0xBD, v, add=1)       # LDA z+1,X -> zp,X
        c.abs(0x6C, v)              # JMP (z)    never shrinks
        c.abs(0x2C, v)              # BIT z
        c.abs(0x20, v)              # JSR z      never shrinks
        c.abs(0x8C, v)              # STY z
        c.abs(0xFE, v)              # INC z,X
        o.func('main', c)
        r = link([o])
        self.assertEqual(r.code('t.main'),
                         bytes.fromhex('B90000 B600 B501 6C0000 2400 200000 8400 F600'))

    def test_addend_decides_with_the_address(self):
        o = Obj('t')
        v = o.var('z', 1, MUST)
        c = o.code().abs(0xAD, v, add=0xFF).abs(0xAD, v, add=0x100).abs(0xAD, v, add=-1).raw(0x60)
        o.func('main', c)
        r = link([o], self.ENV + 'zeropage $00 $FF\n')
        self.assertEqual(r.code('t.main'), bytes.fromhex('A5FF AD0001 ADFFFF 60'))

    def test_forward_and_backward_branches_across_several_sites(self):
        o = Obj('t')
        m = o.f('main')
        c = o.code()
        c.branch(0x90, 13)          #  0 BCC 13 (forward over three sites)
        c.abs(0xAD, m, slot=0)      #  2
        c.abs(0x8D, m, slot=1)      #  5 (stays absolute)
        c.abs(0xEE, m, slot=0)      #  8
        c.raw(0xE8)                 # 11 INX
        c.raw(0xEA)                 # 12 NOP
        c.abs(0xCE, m, slot=0)      # 13
        c.branch(0xD0, 2)           # 16 BNE 2 (back over three sites and one that stays)
        c.branch(0xF0, 12)          # 18 BEQ 12
        c.raw(0x60)                 # 20
        o.func('main', c, slots=[(1, MUST, 0, LOCAL, 'a'), (1, NEVER, 0, LOCAL, 'b')])
        r = link([o])
        self.assertEqual(r.code('t.main'),
                         bytes.fromhex('9009 A500 8D00C0 E600 E8 EA C600 D0F3 F0F9 60'))

    def test_a_function_without_fix_ups_shrinks_nothing(self):
        # Its FIX record may be left out; it does not take the shrinking of the function before.
        o = Obj('t')
        v = o.var('z', 1, MUST)
        o.func('main', o.code().abs(0xAD, v).abs(0x20, o.f('plain')).raw(0x60),
               calls=[(o.f('plain'), 0, NOBODY)])
        n = o.f('plain')
        o.raw(7, bytes((n, 0, 0)))
        o.raw(11, b'\xEA\x60')
        o.raw(12)
        r = link([o], self.ENV + 'zeropage $10 $1F\n')
        self.assertEqual(r.errors, '')
        self.assertEqual((r.size('F', 't.main'), r.size('F', 't.plain')), (6, 2))
        self.assertEqual(r.code('t.plain'), bytes.fromhex('EA60'))

    def test_65c02_opcodes_shrink_only_for_a_65c02(self):
        o = Obj('t', cpu=1)
        v = o.var('z', 1, MUST)
        c = o.code().abs(0x9C, v).abs(0x9E, v).abs(0x0C, v).branch(0x80, 0).raw(0x60)
        o.func('main', c)
        r = link([o], 'cpu 65c02\nzeropage $40 $4F\ncode $0200 $BFFF\ndata $C000 $EFFF\nexit return\n')
        self.assertEqual(r.code('t.main'), bytes.fromhex('6440 7440 0440 80F8 60'))


if __name__ == '__main__':
    unittest.main()
