"""Stage 11: the environment file's version 2 entries (window, switch, bank, overlay, place,
region, more, farcall) and what the linker does with them, on object files built by hand
(lathe/docs/configurations.md, section 5; lathe/host/README.md, "The environment file").
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lk_support import Obj, link, MUST, EITHER, NEVER, NOBODY, INTERRUPT  # noqa: E402
from test_lk_errors import ErrorTest  # noqa: E402

ENV = 'cpu 6502\nzeropage $00 $FF\ncode $0200 $7FFF\ndata $C000 $EFFF\nexit return\n'
WINDOW = 'window WIN $8000 $9FFF\nswitch WIN bank $F000 $1F\nbank WIN 1 $11 BANK1.BIN\n'


def simple(name='t'):
    o = Obj(name)
    o.func('main', b'\x60')
    return o


def farcall(name='fc'):
    """A far-call module with the three functions the linker needs."""
    o = Obj(name)
    o.func('call', b'\x60')
    o.func('back', b'\x60')
    o.func('start', b'\x60')
    return o


class EnvironmentEntries(ErrorTest):
    def test_windows_banks_regions_and_more_change_nothing_while_nothing_is_placed(self):
        env = (ENV + WINDOW + 'bank WIN 2 $12\nwindow OVL $A000 $AFFF\nswitch OVL overlay\n'
               'overlay OVL 1 Ov1.bin\nregion NAMES WIN 2\nregion MSGS fixed\nfarcall fc\n')
        plain = link([simple()], ENV)
        r = link([simple()], env)
        self.assertEqual((r.status, r.errors), (0, ''))
        self.assertEqual((r.image, r.map_text), (plain.image, plain.map_text))

    def test_a_window_must_not_overlap_code_data_more_or_another_window(self):
        for extra in ('window W $7F00 $80FF\n', 'window W $E000 $E0FF\n',
                      'more data $F000 $F7FF\nwindow W $F700 $F8FF\n',
                      'window V $9000 $9FFF\nwindow W $9800 $A7FF\n',
                      'window W $9000 $8FFF\n', 'window W $0080 $00FF\n'):
            self.assertError(link([simple()], ENV + extra), 34, 'environment file: bad address range')

    def test_more_must_not_overlap_code_or_data(self):
        for extra in ('more data $7000 $80FF\n', 'more data $E000 $F0FF\n', 'more data $F100 $F0FF\n',
                      'more data $00F0 $01FF\n'):
            self.assertError(link([simple()], ENV + extra), 34, 'environment file: bad address range')
        self.assertError(link([simple()], ENV + 'more data $F000 $F0FF\nmore data $F100 $F1FF\n'), 3,
                         'environment file: bad entry')
        self.assertError(link([simple()], ENV + 'more code $F000 $F0FF\n'), 3, 'environment file: bad entry')

    def test_an_unknown_window_or_bank(self):
        for extra, name in (('switch OTHER bank $F000 $1F\n', 'other'), ('bank OTHER 1 $11 X\n', 'other'),
                            ('place t OTHER 1\n', 'other'), ('place t WIN 2\n', 'win 2'),
                            ('region R WIN 3\n', 'win 3'), ('region R OTHER 1\n', 'other')):
            line = self.assertError(link([simple()], ENV + WINDOW + extra), 42,
                                    'environment file: no such window, bank or overlay')
            self.assertTrue(line.endswith(': ' + name), line)

    def test_a_name_given_twice(self):
        for extra, name in (('window WIN $A000 $AFFF\n', 'win'), ('bank WIN 1 $12 OTHER.BIN\n', 'win 1'),
                            ('switch WIN bank $F000 $1F\n', 'win'),
                            ('place t WIN 1\nplace t WIN 1\n', 't'), ('region R fixed\nregion R WIN 1\n', 'r')):
            line = self.assertError(link([simple()], ENV + WINDOW + extra + 'farcall fc\n'), 43,
                                    'environment file: named twice')
            self.assertTrue(line.endswith(': ' + name), line)

    def test_badly_formed_entries(self):
        for extra in ('bank WIN 0 $10 X\n', 'bank WIN 256 $10 X\n', 'bank WIN 2 $100 X\n',
                      'bank WIN 2 $12 X Y\n',
                      'window V $A000 $AFFF\nswitch V sideways\n', 'window V $A000 $AFFF\nswitch V bank $F000 0\n',
                      'window V $A000 $AFFF\nswitch V overlay\noverlay V 1\n',
                      'window V $A000 $AFFF\nswitch V overlay\nbank V 1 $11 X\n',
                      'overlay WIN 2 X\n', 'window V $A000 $AFFF\nbank V 1 $11 X\n',
                      'farcall a\nfarcall b\n', 'farcall\n', 'place t\n', 'place t WIN\n'):
            r = link([simple()], ENV + WINDOW + extra)
            self.assertError(r, 3, 'environment file: bad entry')

    def test_too_many_windows_or_banks(self):
        windows = ''.join('window W%d $%X00 $%XFF\n' % (i, 0xA0 + i, 0xA0 + i) for i in range(5))
        self.assertError(link([simple()], ENV + windows), 53, 'environment file: too many')
        banks = ''.join('bank WIN %d $%02X\n' % (i, i) for i in range(2, 18))
        self.assertError(link([simple()], ENV + WINDOW + banks), 53, 'environment file: too many')

    def test_a_module_placed_in_a_bank_without_a_file(self):
        line = self.assertError(link([simple()], ENV + WINDOW + 'bank WIN 2 $12\nplace t WIN 2\nfarcall fc\n'),
                                51, 'environment file: a module is placed in a bank that has no file')
        self.assertTrue(line.endswith(': win 2'), line)

    def test_place_of_a_module_that_is_not_linked(self):
        line = self.assertError(link([simple(), farcall()], ENV + WINDOW + 'place other WIN 1\nfarcall fc\n'),
                                44, 'a module the environment file places is not linked')
        self.assertTrue(line.endswith(': other'), line)

    def test_code_placed_without_a_farcall_entry(self):
        self.assertError(link([simple(), Obj('a')], ENV + WINDOW + 'place a WIN 1\n'), 54,
                         'environment file: code is placed in a window, and no farcall entry')

    def test_the_far_call_module_must_be_fixed(self):
        line = self.assertError(link([simple(), farcall()], ENV + WINDOW + 'place fc WIN 1\nfarcall fc\n'),
                                49, 'environment file: the far-call module must be in fixed memory')
        self.assertTrue(line.endswith(': fc'), line)

    def test_code_in_two_windows(self):
        env = ENV + WINDOW + 'window V $A000 $AFFF\nswitch V bank $F000 $1F\nbank V 1 $11 X\n'
        self.assertError(link([simple(), Obj('a'), Obj('b')], env + 'place a WIN 1\nplace b V 1\nfarcall fc\n'),
                         50, 'environment file: code is placed in two windows')

    def test_overlays_are_numbered_from_one(self):
        env = ENV + 'window OVL $8000 $8FFF\nswitch OVL overlay\noverlay OVL 1 A\noverlay OVL 3 C\n'
        line = self.assertError(link([simple()], env), 52,
                                'environment file: overlays must be numbered from 1 with none missing')
        self.assertTrue(line.endswith(': ovl'), line)

    def test_the_far_call_module_must_be_linked_with_call_and_start(self):
        a = Obj('a')
        a.func('f', b'\x60')
        env = ENV + WINDOW + 'place a WIN 1\nfarcall fc\n'
        line = self.assertError(link([simple(), a], env), 46,
                                'the far-call module is not linked, or does not define call and start')
        self.assertTrue(line.endswith(': fc'), line)
        half = Obj('fc')
        half.func('call', b'\x60')
        self.assertError(link([simple(), a, half], env), 46, 'the far-call module is not linked')


def banked():
    """Module a, for bank 1: f gives 1, g calls f."""
    a = Obj('a')
    a.func('f', b'\xa9\x01\x60')
    c = a.code()
    c.abs(0x20, a.f('f'))
    c.raw(0x60)
    a.func('g', c, calls=[(a.f('f'), 0, NOBODY)])
    return a


def caller():
    """Module t, fixed: main calls a.g."""
    t = Obj('t')
    c = t.code()
    c.abs(0x20, t.f('a.g'))
    c.raw(0x60)
    t.func('main', c, calls=[(t.f('a.g'), 0, NOBODY)])
    return t


PLACED = ENV + WINDOW + 'place a WIN 1\nfarcall fc\n'


class Placement(ErrorTest):
    def test_a_module_s_code_goes_in_its_bank(self):
        r = link([caller(), banked(), farcall()], PLACED)
        self.assertEqual((r.status, r.errors), (0, ''))
        self.assertIn('F 8000 0003 a.f b=1\n', r.map_text)
        self.assertIn('F 8003 0004 a.g b=1\n', r.map_text)
        self.assertIn('W 8000 0007 1 BANK1.BIN\n', r.map_text)
        self.assertEqual(r.files, {'BANK1.BIN': b'\xa9\x01\x60\x20\x00\x80\x60'})
        # Fixed code goes on as if the bank were not there.
        self.assertLess(r.addr('F', 'fc.call'), 0x8000)

    def test_a_bank_that_overflows(self):
        env = PLACED.replace('$8000 $9FFF', '$8000 $8005')
        line = self.assertError(link([caller(), banked(), farcall()], env), 45,
                                'code and data do not fit in a bank')
        self.assertTrue(line.endswith(': win 1, 1 byte over'), line)

    def test_a_bank_is_judged_by_its_size_before_shrinking(self):
        t = caller()
        t.var('v', 1, MUST)             # fixed: t's
        a = Obj('a')
        c = a.code()
        c.abs(0xAD, a.v('t.v'))         # LDA t.v: 3 bytes as written, 2 with t.v in zero page
        c.raw(0x60)
        a.func('g', c)
        env = PLACED.replace('$8000 $9FFF', '$8000 $8002')
        line = self.assertError(link([t, a, farcall()], env), 45, 'code and data do not fit in a bank')
        self.assertTrue(line.endswith(': win 1, 1 byte over'), line)
        r = link([t, a, farcall()], PLACED.replace('$8000 $9FFF', '$8000 $8003'))
        self.assertEqual((r.status, r.errors), (0, ''))
        self.assertIn('W 8000 0003 1 BANK1.BIN\n', r.map_text)
        self.assertEqual(r.files['BANK1.BIN'], b'\xa5\x00\x60')


OVERLAY = ENV + 'window OVL $8000 $8FFF\nswitch OVL overlay\noverlay OVL 1 OV1.BIN\n'


class Interrupts(ErrorTest):
    def test_an_interrupt_function_cannot_be_in_a_window(self):
        a = banked()
        a.func('tick', b'\x40', flags=INTERRUPT)
        line = self.assertError(link([caller(), a, farcall()], PLACED), 47,
                                'an interrupt function cannot be in a window')
        self.assertTrue(line.endswith(': a.tick'), line)

    def test_an_interrupt_function_must_not_reach_an_overlay(self):
        t = caller()
        c = t.code()
        c.abs(0x20, t.f('a.f'))
        c.raw(0x40)
        t.func('tick', c, calls=[(t.f('a.f'), 0, NOBODY)], flags=INTERRUPT)
        env = OVERLAY + 'place a OVL 1\nfarcall fc\n'
        line = self.assertError(link([t, banked(), farcall()], env), 48,
                                'an interrupt function reaches a function in an overlay')
        self.assertTrue(line.endswith(': t.tick, a.f'), line)

    def test_an_interrupt_function_may_reach_a_bank(self):
        t = caller()
        c = t.code()
        c.abs(0x20, t.f('a.f'))
        c.raw(0x40)
        t.func('tick', c, calls=[(t.f('a.f'), 0, NOBODY)], flags=INTERRUPT)
        r = link([t, banked(), farcall()], PLACED)
        self.assertEqual((r.status, r.errors), (0, ''))
        # The handler's copy of a.f is in the bank too, with a stub of its own, which calls the
        # handler's copy of fc.call; the handler calls that stub.
        self.assertIn('F 8003 0003 a.f@1 b=1\n', r.map_text)
        stub = r.addr('T', 'a.f@1')
        self.assertEqual(r.at(r.addr('F', 't.tick'), 3), b'\x20' + bytes((stub & 0xFF, stub >> 8)))
        call = r.addr('F', 'fc.call@1')
        self.assertEqual(r.at(stub, 6), bytes((0x20, call & 0xFF, call >> 8, 0x11, 0x02, 0x80)))


def with_data(v_class=NEVER):
    """Module a, for a window, with constants and variables that go in its bank and some that
    must not; t, fixed, names some of them."""
    a = Obj('a')
    a.data('$1', b'\x01\x02\x03')       # read only by a.f: in the bank
    a.data('$2', b'\x04')               # its address taken by a.f: fixed
    a.data('$3', b'\x05')               # read by t.main: fixed
    a.var('v', 1, v_class, weight=9)    # used only by a.f: in the bank, at its top
    a.var('w', 1, NEVER)                # used by t.main: fixed
    a.var('z', 1, MUST)                 # used only by a.f, but in zero page
    c = a.code()
    c.abs(0xBD, a.d('$1'))              # LDA a.$1,X
    c.byte(0xA9, 2, a.d('$2'))          # LDA #<a.$2
    c.abs(0x8D, a.v('v'))               # STA a.v
    c.abs(0x8D, a.v('z'))               # STA a.z
    c.raw(0x60)
    a.func('f', c)
    t = Obj('t')
    c = t.code()
    c.abs(0x20, t.f('a.f'))
    c.abs(0xAD, t.d('a.$3'))
    c.abs(0x8D, t.v('a.w'))
    c.raw(0x60)
    t.func('main', c, calls=[(t.f('a.f'), 0, NOBODY)])
    return t, a


class Data(ErrorTest):
    """A constant or variable of a module in a window goes in its bank only if every fix-up
    that names it is in that bank's code and none takes its address."""

    def test_what_goes_in_the_bank(self):
        t, a = with_data()
        r = link([t, a, farcall()], PLACED)
        self.assertEqual((r.status, r.errors), (0, ''))
        self.assertIn('D 8000 0003 a.$1 b=1\n', r.map_text)    # data first, in record order
        self.assertIn('F 8003 000B a.f b=1\n', r.map_text)
        self.assertLess(r.addr('D', 'a.$2'), 0x8000)
        self.assertLess(r.addr('D', 'a.$3'), 0x8000)
        self.assertIn('V 9FFF 0001 a.v b=1\n', r.map_text)
        self.assertGreaterEqual(r.addr('V', 'a.w'), 0xC000)
        self.assertLess(r.addr('V', 'a.z'), 0x100)
        code = r.files['BANK1.BIN']
        self.assertEqual(code[:6], b'\x01\x02\x03\xbd\x00\x80')     # a.$1, LDA a.$1,X
        self.assertEqual(code[8:], b'\x8d\xff\x9f\x85\x00\x60')     # STA a.v at the top, STA a.z
        self.assertIn('W 8000 000E 1 BANK1.BIN\n', r.map_text)     # the variable is not in the file

    def test_every_variable_that_may_go_in_the_bank_counts_for_its_size(self):
        # Code 12 bytes, a.$1 3, a.v 1 and a.z 1, though a.z is in zero page: 17.
        t, a = with_data()
        line = self.assertError(link([t, a, farcall()], PLACED.replace('$8000 $9FFF', '$8000 $800F')),
                                45, 'code and data do not fit in a bank')
        self.assertTrue(line.endswith(': win 1, 1 byte over'), line)
        t, a = with_data()
        r = link([t, a, farcall()], PLACED.replace('$8000 $9FFF', '$8000 $8010'))
        self.assertEqual((r.status, r.errors), (0, ''))
        self.assertIn('V 8010 0001 a.v b=1\n', r.map_text)

    def test_whether_a_bank_fits_does_not_depend_on_zero_page(self):
        # a.v may go in zero page: with two bytes of it, it does, and a.f shrinks; with one
        # byte only a.z is there. The bank's contents are judged the same either way.
        for zp, v_in_zp in (('$00 $01', True), ('$00 $00', False)):
            for last, fits in (('$800F', False), ('$8010', True)):
                t, a = with_data(EITHER)
                env = PLACED.replace('$8000 $9FFF', '$8000 ' + last).replace('$00 $FF', zp)
                r = link([t, a, farcall()], env)
                self.assertEqual(r.status == 0, fits, (zp, last, r.errors))
                if fits:
                    self.assertEqual(r.addr('V', 'a.v') < 0x100, v_in_zp, r.map_text)

    def test_constant_data_naming_it_keeps_it_fixed(self):
        _, a = with_data()
        a.data('$4', b'\0\0', fixes=[(0, 1, a.v('v'), 0xFF, 0)])     # .word a.v, in the bank
        c = a.code()
        c.abs(0xAD, a.d('$4'))
        c.raw(0x60)
        a.func('g', c)
        t = Obj('t')
        c = t.code()
        c.abs(0x20, t.f('a.f'))
        c.abs(0x20, t.f('a.g'))
        c.raw(0x60)
        t.func('main', c, calls=[(t.f('a.f'), 0, NOBODY), (t.f('a.g'), 0, NOBODY)])
        r = link([t, a, farcall()], PLACED)
        self.assertEqual((r.status, r.errors), (0, ''))
        self.assertIn('b=1', r.line('D', 'a.$4'))
        self.assertGreaterEqual(r.addr('V', 'a.v'), 0xC000)

    def test_in_an_overlay_constants_go_in_and_variables_stay_fixed(self):
        t, a = with_data()
        r = link([t, a, farcall()], OVERLAY + 'place a OVL 1\nfarcall fc\n')
        self.assertEqual((r.status, r.errors), (0, ''))
        self.assertIn('D 8000 0003 a.$1 b=1\n', r.map_text)
        self.assertGreaterEqual(r.addr('V', 'a.v'), 0xC000)


class More(ErrorTest):
    """`more data FIRST LAST`: the frames first in `data`, then the variables, in `data` while
    each fits and in `more` after that."""

    def program(self, sizes):
        o = Obj('t')
        c = o.code()
        for i, size in enumerate(sizes):
            o.var('v%d' % i, size, NEVER)
            c.abs(0xAD, o.v('v%d' % i))
        c.raw(0x60)
        o.func('main', c, slots=[(4, NEVER, 0, 1, 'l')])
        return o

    def test_variables_go_to_more_when_data_is_full(self):
        env = ENV.replace('$C000 $EFFF', '$C000 $C0FF') + 'more data $F800 $F9FF\n'
        r = link([self.program([100, 200, 50, 150])], env)
        self.assertEqual((r.status, r.errors), (0, ''))
        self.assertEqual(r.addr('S', 't.main', 0), 0xC000)        # the frames first
        self.assertEqual(r.addr('V', 't.v0'), 0xC004)
        self.assertEqual(r.addr('V', 't.v1'), 0xF800)             # 200 does not fit after 104
        self.assertEqual(r.addr('V', 't.v2'), 0xC068)             # 50 does
        self.assertEqual(r.addr('V', 't.v3'), 0xF8C8)

    def test_without_more_the_variables_come_first(self):
        r = link([self.program([1])], ENV)
        self.assertEqual(r.addr('V', 't.v0'), 0xC000)
        self.assertEqual(r.addr('S', 't.main', 0), 0xC001)

    def test_variables_that_fit_in_neither(self):
        env = ENV.replace('$C000 $EFFF', '$C000 $C0FF') + 'more data $F800 $F80F\n'
        self.assertError(link([self.program([250, 20, 3])], env), 26,
                         'variables do not fit in the data range, 20 bytes over')


if __name__ == '__main__':
    unittest.main()
