"""The linker's image is the assembler's image, for programs with interrupt contexts.

A function reachable from two contexts is linked once for each (code-model.md, "Interrupts");
lo2asm renders every copy the map lists as a function of its own, and each copy's calls and
slot references go to the copies of its own context, as the linker's do. The second half is the
address of a function that nothing calls: taking it keeps the function.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lk_support import link  # noqa: E402
import lo  # noqa: E402  (test_lk_support puts the driver directory on the path)

MUST, EITHER, NEVER = 0, 1, 2
PARAM, LOCAL = lo.SK_PARAM, lo.SK_LOCAL


def env(zeropage='$00 $FF'):
    return 'cpu 6502\nzeropage %s\ncode $0200 $BFFF\ndata $C000 $EFFF\nstack $FF\nexit call $F00F\n' % zeropage


def word(r, addr):
    """The two bytes at addr in the image, as a number."""
    return int.from_bytes(r.at(addr, 2), 'little')


def shared_program():
    """main and the interrupt function irq both call t.s; t.s calls t.s2, which both share.

    The allocator decides each slot once for all copies of its function, so what makes the two
    copies of t.s differ is its pointer class: irq calls through t.cb, so in t.s@1 parameter p
    is the class's block, which gets a zero page decision of its own."""
    b = lo.Builder('t')
    b.var('t.count', 1, EITHER, 3)
    b.var('t.big', 2, NEVER)
    b.var('t.vec', 2, NEVER)
    b.clas('t.cb', [1, 2])
    f = b.func('t.main')
    f.slot('m', 1, EITHER, 1)
    f.op('LDA', '#', 1).op('STA', 'abs', ('t.s', 'p')).op('STA', 'abs', ('t.main', 'm'))
    f.call('t.s').op('JSR', 'abs', 't.s').op('LDA', 'abs', ('t.main', 'm')).op('RTS')
    f = b.func('t.irq', lo.F_INTERRUPT)
    f.slot('i', 1, MUST, 2)
    f.op('PHA').op('LDA', '#', 2).op('STA', 'zp', ('t.irq', 'i')).op('STA', 'abs', ('t.cb', 0))
    f.call('t.cb', lo.C_POINTER).op('JSR', 'abs', 'call')
    f.op('STA', 'abs', ('t.s', 'p')).call('t.s').op('JSR', 'abs', 't.s').op('PLA').op('RTI')
    f.label('call').op('JMP', '(abs)', 't.vec')
    f = b.func('t.s')
    f.slot('p', 1, EITHER, 9, PARAM)
    f.slot('w', 2, EITHER, 2, PARAM)
    f.slot('z', 2, MUST, 0)
    f.slot('n', 2, NEVER, 0)
    f.slot('e', 1, EITHER, 5)
    f.label('top').op('LDA', 'abs', ('t.s', 'p')).op('BEQ', 'rel', 'out')
    f.op('STA', 'abs', ('t.s', 'e')).op('LDY', '#', 0).op('LDA', '(zp),y', ('t.s', 'z'))
    f.op('STA', 'abs', ('t.s', 'n')).op('STA', 'abs', ('t.s', 'n'), 1).op('INC', 'abs', 't.count')
    f.op('LDA', 'abs', ('t.s', 'w')).op('ADC', 'abs', ('t.s', 'w'), 1).op('STA', 'abs,y', ('t.s', 'w'))
    f.label('mid').op('LDA', 'abs,x', ('t.s', 'e')).op('STA', 'abs', ('t.s2', 'q'))
    f.call('t.s2').op('JSR', 'abs', 't.s2').op('DEC', 'abs', ('t.s', 'e')).op('BNE', 'rel', 'top')
    f.op('LDA', '#<', 't.s').op('LDX', '#>', 't.s').op('LDY', '#<', 'mid')
    f.op('LDA', 'abs', 't.big', 1).op('BMI', 'rel', 'mid').op('JMP', 'abs', 'out')
    f.label('out').op('RTS')
    f = b.func('t.s2')
    f.slot('q', 1, EITHER, 4, PARAM)
    f.slot('r', 1, EITHER, 2)
    f.label('again').op('LDA', 'abs', ('t.s2', 'q')).op('CLC').op('ADC', 'abs', ('t.s2', 'r'))
    f.op('STA', 'abs', ('t.s2', 'r')).op('DEC', 'abs', ('t.s2', 'q')).op('BNE', 'rel', 'again')
    f.op('RTS')
    d = b.data('t.$1', bytes(5))
    d.fix(0, lo.FX_WORD, 't.s').fix(2, lo.FX_WORD, ('t.s', 'e')).fix(4, lo.FX_LO, ('t.s2', 'r'))
    f = b.func('t.alt')
    f.slot('a', 1, EITHER, 20, PARAM)
    f.slot('b', 2, EITHER, 12, PARAM)
    f.op('LDA', 'abs', ('t.alt', 'a')).op('RTS')
    # The block weighs more than t.s's own p, so it is the first to get zero page.
    b.memb('t.cb', 't.s')
    b.memb('t.cb', 't.alt')
    return b


def three_program():
    """t.f is used by main, by irq and by nmi; nmi reaches it through t.h, which only nmi uses."""
    b = lo.Builder('t')
    f = b.func('t.main')
    f.slot('m', 2, EITHER, 2)
    f.op('LDA', 'abs', ('t.main', 'm')).op('STA', 'abs', ('t.f', 'a')).call('t.f').op('JSR', 'abs', 't.f')
    f.op('RTS')
    for name in ('t.irq', 't.nmi'):
        f = b.func(name, lo.F_INTERRUPT)
        f.slot('k', 1, EITHER, 3)
        f.op('INC', 'abs', (name, 'k'))
        callee = 't.f' if name == 't.irq' else 't.h'
        f.op('STA', 'abs', (callee, 0)).call(callee).op('JSR', 'abs', callee).op('RTI')
    f = b.func('t.h')
    f.slot('x', 1, EITHER, 1, PARAM)
    f.op('LDA', 'abs', ('t.h', 'x')).op('STA', 'abs', ('t.f', 'a')).call('t.f').op('JMP', 'abs', 't.f')
    f = b.func('t.f')
    f.slot('a', 1, EITHER, 6, PARAM)
    f.slot('w', 2, EITHER, 4)
    f.label('loop').op('LDA', 'abs', ('t.f', 'a')).op('STA', 'abs', ('t.g', 'v')).op('STA', 'abs', ('t.f', 'w'))
    f.call('t.g').op('JSR', 'abs', 't.g').op('DEC', 'abs', ('t.f', 'a')).op('BNE', 'rel', 'loop')
    f.op('LDA', 'abs', ('t.f', 'w'), 1).op('RTS')
    f = b.func('t.g')
    f.slot('v', 1, EITHER, 8, PARAM)
    f.slot('t', 1, NEVER, 0)
    f.op('LDA', 'abs', ('t.g', 'v')).op('BPL', 'rel', 'done').op('STA', 'abs', ('t.g', 't'))
    f.label('done').op('RTS')
    return b


def class_program():
    """Pointer calls through t.handler from irq; main calls beep directly and takes @beep."""
    b = lo.Builder('t')
    b.var('t.on_key', 2, EITHER, 4)
    b.clas('t.handler', [1, 2])
    f = b.func('t.main')
    f.slot('m', 1, EITHER, 1)
    f.op('LDA', '#<', 't.beep').op('STA', 'abs', 't.on_key')
    f.op('LDA', '#>', 't.beep').op('STA', 'abs', 't.on_key', 1)
    f.op('LDA', '#', 5).op('STA', 'abs', ('t.beep', 'code')).call('t.beep').op('JSR', 'abs', 't.beep')
    f.op('STA', 'abs', ('t.main', 'm')).op('RTS')
    f = b.func('t.irq', lo.F_INTERRUPT)
    f.slot('i', 1, EITHER, 2)
    f.op('LDA', '#', 3).op('STA', 'abs', ('t.handler', 0)).op('STA', 'abs', ('t.irq', 'i'))
    f.op('STA', 'abs', ('t.handler', 1)).op('STA', 'abs', ('t.handler', 1), 1)
    f.call('t.handler', lo.C_POINTER).op('JSR', 'abs', 'call').op('RTI')
    f.label('call').op('JMP', '(abs)', 't.on_key')
    f = b.func('t.beep')
    f.slot('code', 1, EITHER, 6, PARAM)
    f.slot('arg', 2, EITHER, 2, PARAM)
    f.slot('x', 1, EITHER, 1)
    f.op('LDA', 'abs', ('t.beep', 'code')).op('BEQ', 'rel', 'out').op('INC', 'abs', ('t.beep', 'arg'), 1)
    f.op('STA', 'abs', ('t.beep', 'x')).label('out').op('RTS')
    f = b.func('t.flash')
    f.slot('c', 1, EITHER, 3, PARAM)
    f.slot('a', 2, MUST, 0, PARAM)
    f.op('DEC', 'abs', ('t.flash', 'c')).op('LDA', '(zp),y', ('t.flash', 'a')).op('RTS')
    b.memb('t.handler', 't.beep')
    b.memb('t.handler', 't.flash')
    d = b.data('t.$table', bytes(4))
    d.fix(0, lo.FX_WORD, 't.beep').fix(2, lo.FX_WORD, ('t.beep', 'x'))
    return b


def dropped_program():
    """Addresses of functions nothing calls, taken from kept code, kept data and dropped code."""
    b = lo.Builder('t')
    b.var('t.vec', 2, EITHER, 2)
    f = b.func('t.main')
    f.op('LDA', '#<', 't.lonely').op('STA', 'abs', 't.vec').op('LDA', '#>', 't.lonely')
    f.op('STA', 'abs', 't.vec', 1).op('RTS')
    f = b.func('t.lonely')
    f.slot('l', 1, EITHER, 2)
    f.op('LDA', '#<', 't.deeper').op('STA', 'abs', ('t.lonely', 'l')).op('RTS')
    f = b.func('t.deeper')
    f.slot('d', 1, EITHER, 2)
    f.op('INC', 'abs', ('t.deeper', 'd')).op('RTS')
    f = b.func('t.unused')
    f.op('LDA', '#<', 't.never').op('RTS')
    f = b.func('t.never')
    f.op('RTS')
    f = b.func('t.orphan')
    f.slot('o', 2, EITHER, 1)
    f.op('LDA', 'abs', ('t.orphan', 'o')).op('RTS')
    f = b.func('t.tick', lo.F_INTERRUPT)
    f.op('LDA', '#>', 't.byirq').op('RTI')
    f = b.func('t.byirq')
    f.op('RTS')
    d = b.data('t.$tab', bytes(2))
    d.fix(0, lo.FX_WORD, 't.orphan')
    return b


class Identity(unittest.TestCase):
    def identical(self, objects, environment):
        r = link(objects, environment, asm=True)
        self.assertEqual((r.status, r.errors), (0, ''))
        if r.image != r.asm_image:
            where = next(i for i in range(len(r.image)) if r.image[i] != r.asm_image[i])
            self.fail('images differ first at $%04X\n%s\n%s' % (r.code_lo + where, r.map_text, r.asm_text))
        return r


class TwoContexts(Identity):
    def test_with_every_zero_page_size(self):
        differ = 0
        for last in range(0x84, 0x96):
            r = self.identical([shared_program()], env('$80 $%02X' % last))
            if r.size('F', 't.s') != r.size('F', 't.s@1'):
                differ += 1
        # The copies shrank differently in some of the runs: their frames really differed.
        self.assertGreater(differ, 2)

    def test_the_copies_by_hand(self):
        # Zero page $80-$87: z of both copies and irq.i must be there; then the heaviest, the
        # block (t.cb's p and w, which are t.s@1's), fits, and t.s's own p and w do not.
        r = self.identical([shared_program()], env('$80 $87'))
        self.assertEqual([r.addr('S', 't.s', i) for i in range(5)], [0xC006, 0xC007, 0x80, 0xC009, 0xC00B])
        self.assertEqual([r.addr('S', 't.s@1', i) for i in range(5)], [0x83, 0x84, 0x86, 0xC00E, 0xC010])
        self.assertEqual([r.addr('F', n) for n in ('t.main', 't.irq', 't.s', 't.s@1', 't.s2', 't.s2@1')],
                         [0x020C, 0x021B, 0x022F, 0x026A, 0x02A2, 0x02B2])
        # main stores t.s's p and calls t.s; irq stores the block and calls t.s@1.
        self.assertEqual(r.code('t.main'), bytes.fromhex('A901 8D06C0 8D05C0 202F02 AD05C0 60'))
        self.assertEqual(r.code('t.irq'), bytes.fromhex('48 A902 8582 8583 202C02 8583 206A02 68 40 6C03C0'))
        s, s1 = r.code('t.s'), r.code('t.s@1')
        self.assertEqual((len(s), len(s1)), (0x3B, 0x38))
        # LDA p / BEQ out: the branch is shorter in t.s@1, where p and w shrank.
        self.assertEqual((s[:5], s1[:4]), (bytes.fromhex('AD06C0 F035'), bytes.fromhex('A583 F033')))
        # Each copy calls its own context's t.s2.
        self.assertEqual((s[0x24:0x27], s1[0x21:0x24]), (bytes.fromhex('20A202'), bytes.fromhex('20B202')))
        # @t.s is the copy pointers reach (t.s@1, in t.cb's context) in both; a label is the
        # copy's own; so is a JMP to one.
        self.assertEqual(s[0x2C:0x32], bytes.fromhex('A96A A202 A04D'))
        self.assertEqual(s1[0x29:0x2F], bytes.fromhex('A96A A202 A085'))
        self.assertEqual((s[-4:], s1[-4:]), (bytes.fromhex('4C6902 60'), bytes.fromhex('4CA102 60')))
        # Constant data has no context: @t.s, a slot of t.s, and a slot of t.s2 (no class: the
        # first copy).
        self.assertEqual(r.at(r.addr('D', 't.$1'), 5), bytes.fromhex('6A02 10C0 0D'))

    def test_the_variables_are_shared(self):
        r = link([shared_program()], env('$80 $87'))
        self.assertTrue(r.has('V', 't.count'))
        self.assertFalse(r.has('V', 't.count@1'))


class ThreeContexts(Identity):
    def test_three_copies(self):
        for last in range(0x82, 0x92, 3):
            r = self.identical([three_program()], env('$80 $%02X' % last))
            names = [m[3] for m in r.map if m[0] == 'F']
            self.assertEqual(names, ['$start', 't.main', 't.irq', 't.nmi', 't.h', 't.f', 't.f@1', 't.f@2',
                                     't.g', 't.g@1', 't.g@2'])

    def test_a_first_copy_outside_context_0_is_marked_with_its_context(self):
        r = link([three_program()], env())
        self.assertEqual(r.line('F', 't.h')[4:], ['2'])
        self.assertEqual(r.line('F', 't.irq')[4:], ['1'])
        self.assertEqual(r.line('F', 't.f@2')[4:], [])
        self.assertEqual(r.line('F', 't.main')[4:], [])
        h = r.code('t.h')
        self.assertEqual(int.from_bytes(h[-2:], 'little'), r.addr('F', 't.f@2'))


class Classes(Identity):
    def test_a_class_called_from_an_interrupt(self):
        for last in (0x11, 0x13, 0x15, 0x18, 0x1F):
            r = self.identical([class_program()], env('$10 $%02X' % last))
            pointed = r.addr('F', 't.beep@1')
            self.assertEqual(word(r, r.addr('D', 't.$table')), pointed)
            self.assertEqual(word(r, r.addr('D', 't.$table') + 2), r.addr('S', 't.beep@1', 2))


class DroppedAddress(Identity):
    def test_a_function_whose_address_is_taken_is_kept(self):
        r = self.identical([dropped_program()], env())
        names = [m[3] for m in r.map if m[0] == 'F']
        self.assertEqual(names, ['$start', 't.main', 't.lonely', 't.deeper', 't.orphan', 't.tick', 't.byirq'])
        main = r.addr('F', 't.main')
        lonely = r.addr('F', 't.lonely')
        self.assertEqual((r.at(main + 1), r.at(main + 5)), (bytes((lonely & 0xFF,)), bytes((lonely >> 8,))))
        self.assertEqual(word(r, r.addr('D', 't.$tab')), r.addr('F', 't.orphan'))
        self.assertEqual(r.at(r.addr('F', 't.tick') + 1), bytes((r.addr('F', 't.byirq') >> 8,)))

    def test_a_kept_address_is_in_the_main_program(self):
        # Kept only for its address, a function is a root of context 0: its frame is shared
        # like any other there, and it has no copy elsewhere.
        r = link([dropped_program()], env())
        self.assertEqual(r.line('F', 't.byirq')[4:], [])


if __name__ == '__main__':
    unittest.main()
