"""Pointer classes: every function whose address is taken as one function type has its
parameters in the class's shared block (lathe/docs/code-model.md, "Functions called through a
pointer").
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lk_support import (Obj, link, keep, routine, NEVER, MUST, EITHER, LOCAL, PARAM,  # noqa: E402
                             INTERRUPT, RECURSIVE, SAVES, POINTER, NOBODY)
import lo  # noqa: E402

ENV = 'cpu 6502\nzeropage $00 $FF\ncode $0200 $BFFF\ndata $C000 $EFFF\nexit return\n'
CYCLE = 'link error 21: recursion through a call or function not marked recursive: '
MEMBER = ('link error 40: functions of one pointer class share their parameters: one that calls another '
          'must be recursive, as must the one it calls, or the function type it calls through: ')


def member(o, name, local, zp_class=NEVER, calls=(), flags=0, classes=(NEVER, NEVER), weights=(0, 0),
           names=('code', 'arg')):
    """A function with the parameters of class t.handler (a byte and a word) and one local."""
    slots = [(1, classes[0], weights[0], PARAM, names[0]), (2, classes[1], weights[1], PARAM, names[1]),
             (local, zp_class, 0, LOCAL, 'x')]
    routine(o, name, slots, calls, flags)


def dispatch(zp_class=NEVER):
    """main calls through t.handler, whose members are beep and flash."""
    o = Obj('t')
    o.clas('handler', [1, 2])
    routine(o, 'main', [(1, zp_class, 0, LOCAL, 'm')], [('handler', POINTER, None)])
    member(o, 'beep', 1, zp_class, classes=(zp_class, zp_class))
    member(o, 'flash', 3, zp_class, classes=(zp_class, zp_class), names=('c', 'a'))
    o.memb('handler', 'beep')
    o.memb('handler', 'flash')
    return o


class Block(unittest.TestCase):
    def test_the_block_is_above_the_caller_and_the_members_locals_above_the_block(self):
        r = link([dispatch()], ENV)
        self.assertEqual(r.addr('S', 't.main', 0), 0xC000)
        self.assertEqual([r.addr('C', 't.handler', i) for i in (0, 1)], [0xC001, 0xC002])
        self.assertEqual((r.addr('S', 't.beep', 2), r.addr('S', 't.flash', 2)), (0xC004, 0xC004))

    def test_a_members_parameters_are_the_block(self):
        r = link([dispatch()], ENV)
        for name in ('t.beep', 't.flash'):
            self.assertEqual([r.addr('S', name, i) for i in (0, 1)], [0xC001, 0xC002])

    def test_class_lines_name_the_parameters_after_the_first_member(self):
        r = link([dispatch()], ENV)
        self.assertEqual(r.map_text.splitlines()[-2:],
                         ['C C001 0001 t.handler 0 code', 'C C002 0002 t.handler 1 arg'])

    def test_in_zero_page(self):
        r = link([dispatch(MUST)], ENV.replace('$00 $FF', '$70 $7F'))
        self.assertEqual(r.addr('S', 't.main', 0), 0x70)
        self.assertEqual([r.addr('C', 't.handler', i) for i in (0, 1)], [0x71, 0x72])
        self.assertEqual((r.addr('S', 't.beep', 2), r.addr('S', 't.flash', 2)), (0x74, 0x74))

    def test_every_member_is_kept_once_the_class_is_called(self):
        r = link([dispatch()], ENV)
        self.assertEqual([m[3] for m in r.map if m[0] == 'F'], ['$start', 't.main', 't.beep', 't.flash'])

    def test_a_direct_caller_of_a_member_is_below_the_block(self):
        # main -> g (5 bytes) -> beep directly; main also calls through the class.
        o = Obj('t')
        o.clas('handler', [1, 2])
        routine(o, 'main', [(1, NEVER, 0, LOCAL, 'm')], ['g', ('handler', POINTER, None)])
        routine(o, 'g', [(5, NEVER, 0, LOCAL, 'q')], ['beep'])
        member(o, 'beep', 1)
        o.memb('handler', 'beep')
        r = link([o], ENV)
        self.assertEqual((r.addr('S', 't.g', 0), r.addr('C', 't.handler', 0), r.addr('S', 't.beep', 2)),
                         (0xC001, 0xC006, 0xC009))

    def test_arguments_and_addresses_in_code(self):
        o = Obj('t')
        k = o.clas('handler', [1, 2])
        beep = o.f('beep')
        m = o.f('main')
        c = o.code()
        c.raw(0xA9, 3).abs(0x8D, k, slot=0)             # LDA #3 / STA handler.code
        c.abs(0x8E, k, slot=1, add=1)                   # STX handler.arg+1
        c.byte(0xA9, 2, beep).byte(0xA2, 3, beep)       # LDA #<beep / LDX #>beep
        c.abs(0x20, m, add=c.here() + 4)                # JSR .call
        c.raw(0x60)
        c.raw(0x6C, 0x34, 0x12)                         # .call: JMP ($1234)
        o.func('main', c, calls=[(k, POINTER, NOBODY)])
        member(o, 'beep', 1)
        o.memb('handler', 'beep')
        r = link([o], ENV)
        self.assertEqual(r.addr('F', 't.beep'), 0x0218)
        self.assertEqual(r.code('t.main'), bytes.fromhex('A903 8D00C0 8E02C0 A918 A202 201502 60 6C3412'))

    def test_a_class_without_members_still_has_a_block(self):
        o = Obj('t')
        o.clas('handler', [1, 2])
        routine(o, 'main', [(1, NEVER, 0, LOCAL, 'm')], [('handler', POINTER, None)])
        r = link([o], ENV)
        self.assertEqual(r.map_text.splitlines()[-2:],
                         ['C C001 0001 t.handler 0 p0', 'C C002 0002 t.handler 1 p1'])

    def test_a_class_nobody_calls_through_has_no_block(self):
        o = Obj('t')
        o.clas('handler', [1, 2])
        routine(o, 'main', [(1, NEVER, 0, LOCAL, 'm')], ['beep'])
        member(o, 'beep', 1)
        member(o, 'flash', 3)
        o.memb('handler', 'beep')
        o.memb('handler', 'flash')
        r = link([o], ENV)
        self.assertFalse(any(m[0] == 'C' for m in r.map))
        self.assertFalse(r.has('F', 't.flash'))
        self.assertEqual([r.addr('S', 't.beep', i) for i in range(3)], [0xC001, 0xC002, 0xC004])


class BlockSlots(unittest.TestCase):
    def program(self, beep_classes, flash_classes, beep_weights=(0, 0), flash_weights=(0, 0), main_weight=0):
        o = Obj('t')
        o.clas('handler', [1, 2])
        routine(o, 'main', [(2, EITHER, main_weight, LOCAL, 'm')], [('handler', POINTER, None)])
        member(o, 'beep', 1, classes=beep_classes, weights=beep_weights)
        member(o, 'flash', 1, classes=flash_classes, weights=flash_weights)
        o.memb('handler', 'beep')
        o.memb('handler', 'flash')
        return o

    def test_must_in_one_member_puts_the_parameter_in_zero_page(self):
        r = link([self.program((EITHER, NEVER), (MUST, NEVER))], ENV)
        self.assertEqual([r.addr('C', 't.handler', i) for i in (0, 1)], [0x00, 0xC002])

    def test_never_in_one_member_keeps_an_either_parameter_out(self):
        r = link([self.program((EITHER, EITHER), (NEVER, EITHER), (9, 9), (9, 9))], ENV)
        self.assertEqual([r.addr('C', 't.handler', i) for i in (0, 1)], [0xC002, 0x00])

    def test_must_beats_never(self):
        r = link([self.program((NEVER, NEVER), (MUST, NEVER))], ENV)
        self.assertEqual(r.addr('C', 't.handler', 0), 0x00)

    def test_weights_of_the_members_are_added(self):
        # Two bytes of zero page: main's word weighs 120, the block's word 100 + 50.
        o = self.program((NEVER, EITHER), (NEVER, EITHER), (0, 100), (0, 50), main_weight=120)
        r = link([o], ENV.replace('$00 $FF', '$00 $01'))
        self.assertEqual((r.addr('S', 't.main', 0), r.addr('C', 't.handler', 1)), (0xC000, 0x00))
        o = self.program((NEVER, EITHER), (NEVER, EITHER), (0, 100), (0, 10), main_weight=120)
        r = link([o], ENV.replace('$00 $FF', '$00 $01'))
        self.assertEqual((r.addr('S', 't.main', 0), r.addr('C', 't.handler', 1)), (0x00, 0xC001))

    def test_the_sum_stops_at_255(self):
        o = self.program((NEVER, EITHER), (NEVER, EITHER), (0, 200), (0, 200), main_weight=255)
        r = link([o], ENV.replace('$00 $FF', '$00 $01'))
        # equal weights: a slot is tried before a class parameter
        self.assertEqual((r.addr('S', 't.main', 0), r.addr('C', 't.handler', 1)), (0x00, 0xC001))

    def test_a_member_whose_parameters_differ_from_the_class(self):
        o = Obj('t')
        o.clas('handler', [1, 2])
        routine(o, 'main', (), [('handler', POINTER, None)])
        routine(o, 'odd', [(1, NEVER, 0, PARAM, 'a'), (1, NEVER, 0, PARAM, 'b')])
        o.memb('handler', 'odd')
        self.assertEqual(link([o], ENV).errors,
                         'link error 24: function does not have the parameters of its pointer class: t.odd\n')
        o = Obj('t')
        o.clas('handler', [1, 2])
        routine(o, 'main', (), [('handler', POINTER, None)])
        routine(o, 'odd', [(1, NEVER, 0, PARAM, 'a')])
        o.memb('handler', 'odd')
        self.assertEqual(link([o], ENV).status, 1)

    def test_two_modules_must_describe_a_class_alike(self):
        a = Obj('a')
        a.clas('handler', [1, 2])
        routine(a, 'main')
        b = Obj('b')
        b.clas('a.handler', [1, 1])
        self.assertEqual(link([a, b], ENV).errors,
                         'link error 23: pointer class declared with different parameters: a.handler\n')
        b = Obj('b')
        b.clas('a.handler', [1, 2])
        self.assertEqual(link([a, b], ENV).status, 0)


class MergedClasses(unittest.TestCase):
    def program(self, other_sizes=(1, 2)):
        o = Obj('t')
        o.clas('handler', [1, 2])
        o.clas('callback', list(other_sizes))
        routine(o, 'main', [(1, NEVER, 0, LOCAL, 'm')], [('handler', POINTER, None), 'f'])
        routine(o, 'f', [(4, NEVER, 0, LOCAL, 'q')], [('callback', POINTER, None)])
        member(o, 'beep', 1)
        member(o, 'flash', 2)
        o.memb('handler', 'beep')
        o.memb('callback', 'beep')
        o.memb('callback', 'flash')
        return o

    def test_a_function_in_two_classes_makes_them_one_block(self):
        r = link([self.program()], ENV)
        # main C000, f C001-C004, the one block C005-C007, locals C008
        self.assertEqual([r.addr('C', 't.handler', i) for i in (0, 1)], [0xC005, 0xC006])
        self.assertEqual([r.addr('C', 't.callback', i) for i in (0, 1)], [0xC005, 0xC006])
        self.assertEqual((r.addr('S', 't.beep', 2), r.addr('S', 't.flash', 2)), (0xC008, 0xC008))

    def test_classes_with_different_parameters_cannot_merge(self):
        r = link([self.program((1, 1))], ENV)
        self.assertEqual(r.errors, 'link error 23: pointer class declared with different parameters: t.callback\n')


class ClassCycles(unittest.TestCase):
    def test_a_member_that_calls_a_member_overwrites_its_own_parameters(self):
        o = Obj('t')
        o.clas('handler', [1, 2])
        routine(o, 'main', (), [('handler', POINTER, None)])
        member(o, 'beep', 1, calls=['flash'])
        member(o, 'flash', 1)
        o.memb('handler', 'beep')
        o.memb('handler', 'flash')
        self.assertEqual(link([o], ENV).errors, MEMBER + 't.beep -> t.flash, both in the pointer class t.handler\n')

    def test_members_that_call_each_other_directly_are_a_plain_cycle_first(self):
        o = Obj('t')
        o.clas('handler', [1, 2])
        routine(o, 'main', (), [('handler', POINTER, None)])
        member(o, 'beep', 1, calls=[('flash', SAVES, None)], flags=RECURSIVE)
        member(o, 'flash', 1, calls=['beep'])
        o.memb('handler', 'beep')
        o.memb('handler', 'flash')
        self.assertEqual(link([o], ENV).errors, CYCLE + 't.beep -> t.flash -> t.beep\n')

    def test_a_member_that_calls_through_its_own_class(self):
        o = Obj('t')
        o.clas('handler', [1, 2])
        routine(o, 'main', (), [('handler', POINTER, None)])
        member(o, 'beep', 1, calls=[('handler', POINTER, None)])
        o.memb('handler', 'beep')
        self.assertEqual(link([o], ENV).errors, MEMBER + 't.beep -> t.handler, its own pointer class\n')

    def test_a_callback_that_calls_back_into_the_walker(self):
        o = Obj('t')
        o.clas('visit', [])
        routine(o, 'main', (), ['walk'])
        routine(o, 'walk', (), [('visit', POINTER, None)])
        routine(o, 'show', (), ['walk'])
        o.memb('visit', 'show')
        r = link([o], ENV)
        self.assertEqual(r.status, 1)
        self.assertTrue(r.errors.startswith(CYCLE), r.errors)
        for name in ('t.walk', 't.visit', 't.show'):
            self.assertIn(name, r.errors)

    def test_recursive_members_may_call_each_other_and_then_share_nothing(self):
        o = Obj('t')
        o.clas('visit', [1, 2], flags=1)
        routine(o, 'main', [(1, NEVER, 0, LOCAL, 'm')], [('visit', POINTER, None)])
        member(o, 'node', 1, calls=[('visit', POINTER | SAVES, None), ('leaf', SAVES, None)], flags=RECURSIVE)
        member(o, 'leaf', 2, calls=[('node', SAVES, None)], flags=RECURSIVE)
        o.memb('visit', 'node')
        o.memb('visit', 'leaf')
        r = link([o], ENV)
        self.assertEqual((r.status, r.errors), (0, ''))
        spans = sorted([(r.addr('C', 't.visit', 0), 3), (r.addr('S', 't.node', 2), 1), (r.addr('S', 't.leaf', 2), 2)])
        self.assertEqual(spans[0][0], 0xC001)
        self.assertEqual(spans[1][0], spans[0][0] + spans[0][1])
        self.assertEqual(spans[2][0], spans[1][0] + spans[1][1])

    def test_a_recursive_function_may_be_a_member_of_a_plain_class(self):
        # It saves its frame, parameters in the block included, around its own recursive call.
        o = Obj('t')
        o.clas('handler', [1, 2])
        routine(o, 'main', (), [('handler', POINTER, None)])
        member(o, 'walk', 1, calls=[('walk', SAVES, None)], flags=RECURSIVE)
        o.memb('handler', 'walk')
        self.assertEqual(link([o], ENV).status, 0)

    def test_but_not_if_it_recurses_through_the_plain_pointer(self):
        o = Obj('t')
        o.clas('handler', [1, 2])
        routine(o, 'main', (), [('handler', POINTER, None)])
        member(o, 'walk', 1, calls=[('handler', POINTER, None)], flags=RECURSIVE)
        o.memb('handler', 'walk')
        self.assertEqual(link([o], ENV).errors, MEMBER + 't.walk -> t.handler, its own pointer class\n')


class PendingWithClasses(unittest.TestCase):
    def test_a_call_inside_the_arguments_of_a_pointer_call_is_above_the_block(self):
        o = Obj('t')
        o.clas('handler', [1, 2])
        routine(o, 'main', [(1, NEVER, 0, LOCAL, 'm')], [('h', 0, '^handler'), ('handler', POINTER, None)])
        routine(o, 'h', [(2, NEVER, 0, LOCAL, 'q')])
        r = link([o], ENV)
        self.assertEqual((r.addr('C', 't.handler', 0), r.addr('S', 't.h', 0)), (0xC001, 0xC004))

    def test_a_call_inside_the_arguments_of_a_direct_call_of_a_member_too(self):
        o = Obj('t')
        o.clas('handler', [1, 2])
        routine(o, 'main', [(1, NEVER, 0, LOCAL, 'm')],
                [('h', 0, 'beep'), 'beep', ('handler', POINTER, None)])
        routine(o, 'h', [(2, NEVER, 0, LOCAL, 'q')])
        member(o, 'beep', 1)
        o.memb('handler', 'beep')
        r = link([o], ENV)
        # block C001-C003, beep's local C004; h above all of beep
        self.assertEqual((r.addr('C', 't.handler', 0), r.addr('S', 't.h', 0)), (0xC001, 0xC005))


class ClassesAndContexts(unittest.TestCase):
    def test_pointer_calls_from_two_contexts(self):
        o = dispatch()
        routine(o, 'irq', (), [('handler', POINTER, None)], flags=INTERRUPT)
        self.assertEqual(link([o], ENV).errors,
                         'link error 22: pointer class called through pointers from two contexts: '
                         't.handler, t.main, t.irq\n')

    def test_a_function_called_through_pointers_from_two_contexts(self):
        o = Obj('t')
        o.clas('handler', [1, 2])
        routine(o, 'main', (), ['poll'])
        routine(o, 'irq', (), ['poll'], flags=INTERRUPT)
        routine(o, 'poll', (), [('handler', POINTER, None)])
        self.assertEqual(link([o], ENV).errors,
                         'link error 22: pointer class called through pointers from two contexts: '
                         't.handler, t.poll, t.poll\n')

    def program(self):
        """The handler calls through t.handler; main calls beep directly and takes its address."""
        o = Obj('t')
        o.clas('handler', [1, 2])
        beep = o.f('beep')
        c = o.code().byte(0xA9, 2, beep).byte(0xA2, 3, beep).abs(0x8D, beep, slot=0).abs(0x20, beep).raw(0x60)
        o.func('main', c, calls=[(beep, 0, NOBODY)], slots=[(1, NEVER, 0, LOCAL, 'm')])
        routine(o, 'irq', [(1, MUST, 0, LOCAL, 'i')], [('handler', POINTER, None)], flags=INTERRUPT)
        c = o.code()
        c.abs(0xAD, beep, slot=0)           # 0 LDA code
        c.branch(0xF0, 8)                   # 3 BEQ 8
        c.abs(0xEE, beep, slot=2)           # 5 INC x
        c.raw(0x60)                         # 8 RTS
        o.func('beep', c, slots=[(1, EITHER, 0, PARAM, 'code'), (2, NEVER, 0, PARAM, 'arg'),
                                 (1, NEVER, 0, LOCAL, 'x')])
        member(o, 'flash', 1, classes=(MUST, NEVER))
        o.memb('handler', 'beep')
        o.memb('handler', 'flash')
        o.data('$table', b'\0\0', fixes=[(0, 1, beep, 0xFF, 0)])
        keep(o, '$table')
        return o

    def test_the_block_is_in_the_context_that_calls_through_the_class(self):
        r = link([self.program()], ENV)
        # zero page: irq.i at 0, then the block's parameter 0 (flash needs it there)
        self.assertEqual((r.addr('S', 't.irq', 0), r.addr('C', 't.handler', 0)), (0x00, 0x01))
        self.assertEqual(r.addr('S', 't.beep@1', 0), 0x01)

    def test_the_other_context_gets_a_copy_with_parameters_of_its_own(self):
        r = link([self.program()], ENV)
        # main memory: main.m C000; beep's own code C001, arg C002, x C004 | block arg, then x
        self.assertEqual([r.addr('S', 't.beep', i) for i in range(3)], [0xC001, 0xC002, 0xC004])
        self.assertEqual([r.addr('S', 't.beep@1', i) for i in range(3)], [0x01, 0xC005, 0xC007])

    def test_the_two_copies_differ_in_size(self):
        r = link([self.program()], ENV)
        self.assertEqual(r.code('t.beep'), bytes.fromhex('AD01C0 F003 EE04C0 60'))
        self.assertEqual(r.code('t.beep@1'), bytes.fromhex('A501 F003 EE07C0 60'))

    def test_the_address_of_a_member_is_the_copy_pointers_can_reach(self):
        r = link([self.program()], ENV)
        direct, pointed = r.addr('F', 't.beep'), r.addr('F', 't.beep@1')
        self.assertEqual(r.code('t.main'),
                         bytes((0xA9, pointed & 0xFF, 0xA2, pointed >> 8, 0x8D, 0x01, 0xC0,
                                0x20, direct & 0xFF, direct >> 8, 0x60)))
        self.assertEqual(r.at(r.addr('D', 't.$table'), 2), pointed.to_bytes(2, 'little'))


class ClassIdentity(unittest.TestCase):
    """The same check as test_lk_identity.py, for a program with a pointer class."""

    def test_dispatch_through_a_pointer(self):
        b = lo.Builder('t')
        b.var('t.on_key', 2, EITHER, 4)
        b.clas('t.handler', [1, 2])
        f = b.func('t.main')
        f.slot('m', 1, EITHER, 1)
        f.op('LDA', '#<', 't.beep').op('STA', 'abs', 't.on_key')
        f.op('LDA', '#>', 't.beep').op('STA', 'abs', 't.on_key', 1)
        f.op('LDA', '#', 3).op('STA', 'abs', ('t.handler', 0))
        f.op('STA', 'abs', ('t.handler', 1)).op('STA', 'abs', ('t.handler', 1), 1)
        f.call('t.handler', lo.C_POINTER).op('JSR', 'abs', 'call')
        f.op('STA', 'abs', ('t.flash', 'c')).call('t.flash').op('JSR', 'abs', 't.flash')
        f.op('STA', 'abs', ('t.main', 'm')).op('RTS')
        f.label('call').op('JMP', '(abs)', 't.on_key')
        f = b.func('t.beep')
        f.slot('code', 1, EITHER, 6, lo.SK_PARAM)
        f.slot('arg', 2, EITHER, 2, lo.SK_PARAM)
        f.slot('x', 1, EITHER, 1)
        f.op('LDA', 'abs', ('t.beep', 'code')).op('BEQ', 'rel', 'out').op('INC', 'abs', ('t.beep', 'arg'), 1)
        f.op('STA', 'abs', ('t.beep', 'x')).label('out').op('RTS')
        f = b.func('t.flash')
        f.slot('c', 1, EITHER, 3, lo.SK_PARAM)
        f.slot('a', 2, MUST, 0, lo.SK_PARAM)
        f.op('DEC', 'abs', ('t.flash', 'c')).op('LDA', '(zp),y', ('t.flash', 'a')).op('RTS')
        b.memb('t.handler', 't.beep')
        b.memb('t.handler', 't.flash')
        for last in (0x11, 0x12, 0x13, 0x14, 0x16, 0x1F):
            r = link([b], ENV.replace('$00 $FF', '$10 $%02X' % last), asm=True)
            self.assertEqual((r.status, r.errors), (0, ''))
            self.assertTrue(r.image == r.asm_image, 'zero page to $%02X\n%s\n%s' % (last, r.map_text, r.asm_text))


if __name__ == '__main__':
    unittest.main()
