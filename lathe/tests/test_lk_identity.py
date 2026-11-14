"""The linker's image is the assembler's image.

Each program here is linked, then rendered from the same objects and the linker's own map as
asm17 text (lathe/host/driver/lo2asm.py) and assembled with asm/pyasm.py. The assembler picks
zero page forms and works out branches by itself, so equal bytes show that the linker's
shrinking, branch and label corrections, fix-ups and start-up code are right, whatever the
allocation happened to be.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lk_support import link  # noqa: E402
import lo  # noqa: E402  (test_lk_support puts the driver directory on the path)

MUST, EITHER, NEVER = 0, 1, 2
PARAM, LOCAL = lo.SK_PARAM, lo.SK_LOCAL


def env(zeropage='$00 $FF', stack='stack $FF\n', leave='call $F00F', code='$0200 $BFFF'):
    return ('cpu 6502\nzeropage %s\ncode %s\ndata $C000 $EFFF\n%sexit %s\n'
            % (zeropage, code, stack, leave))


def loop_program():
    """A loop over an "either" slot with a forward branch, a backward branch and a JMP to a
    label, all of which cross instructions that may shrink."""
    b = lo.Builder('t')
    b.var('t.held', 1, MUST)
    f = b.func('t.main')
    f.slot('i', 1, EITHER, 5)
    f.slot('big', 2, NEVER, 0)
    f.label('top').op('LDA', 'abs', ('t.main', 'i')).op('BEQ', 'rel', 'skip')
    f.op('INC', 'abs', ('t.main', 'i')).op('STA', 'abs', ('t.main', 'big'), 1)
    f.label('skip').op('LDA', 'abs', ('t.main', 'i')).op('BNE', 'rel', 'top')
    f.op('LDX', 'abs,y', ('t.main', 'i')).op('LDA', 'abs,y', ('t.main', 'i'))
    f.op('JMP', 'abs', 'skip')
    f.label('done').op('LDA', '#<', 'done').op('LDX', '#>', 'done').op('JSR', 'abs', 'done')
    f.op('STA', 'abs', 't.held').op('RTS')
    return b


def frames_program():
    """main -> a -> b and main -> c, with arguments stored into the callees' slots."""
    b = lo.Builder('t')
    b.var('t.count', 2, EITHER, 9)
    b.var('t.table', 40, NEVER)
    f = b.func('t.main')
    f.slot('m', 1, EITHER, 3)
    f.op('LDA', '#', 1).op('STA', 'abs', ('t.a', 0)).op('STA', 'abs', ('t.main', 'm'))
    f.call('t.a').op('JSR', 'abs', 't.a')
    f.op('LDA', 'abs', ('t.main', 'm')).op('STA', 'abs', ('t.c', 0)).op('LDA', '#', 0)
    f.op('STA', 'abs', ('t.c', 0), 1)
    f.call('t.c').op('JSR', 'abs', 't.c').op('RTS')
    f = b.func('t.a')
    f.slot('n', 1, EITHER, 4, PARAM)
    f.slot('p', 2, MUST, 0)
    f.op('LDA', 'abs', ('t.a', 'n')).op('STA', 'zp', ('t.a', 'p')).op('LDA', '#>', 't.table')
    f.op('STA', 'zp', ('t.a', 'p'), 1).op('LDY', '#', 0).op('STA', '(zp),y', ('t.a', 'p'))
    f.op('STA', 'abs', ('t.b', 0)).call('t.b').op('JMP', 'abs', 't.b')
    f = b.func('t.b')
    f.slot('x', 1, EITHER, 2, PARAM)
    f.slot('t', 3, NEVER, 0)
    f.label('again').op('DEC', 'abs', ('t.b', 'x')).op('BNE', 'rel', 'again')
    f.op('INC', 'abs', 't.count').op('BNE', 'rel', 'out').op('INC', 'abs', 't.count', 1)
    f.label('out').op('LDA', 'abs', ('t.b', 't'), 2).op('RTS')
    f = b.func('t.c')
    f.slot('w', 2, EITHER, 6, PARAM)
    f.slot('v', 2, EITHER, 1)
    f.op('LDX', '#', 0).op('LDA', 'abs,x', ('t.c', 'w')).op('STA', 'abs,x', ('t.c', 'v'))
    f.op('LDA', 'abs,x', 't.table', 39).op('ORA', 'abs', ('t.c', 'w'), 1).op('RTS')
    return b


class Identity(unittest.TestCase):
    def identical(self, objects, environment, main=None):
        r = link(objects, environment, main=main, asm=True)
        self.assertEqual((r.status, r.errors), (0, ''))
        if r.image != r.asm_image:
            where = next(i for i in range(len(r.image)) if r.image[i] != r.asm_image[i])
            self.fail('images differ first at $%04X\n%s\n%s' % (r.code_lo + where, r.map_text, r.asm_text))
        return r

    def test_shrinking_branches_and_labels_with_room_in_zero_page(self):
        r = self.identical([loop_program()], env('$10 $1F'))
        self.assertEqual(r.addr('S', 't.main', 0), 0x11)
        # as written the function is 36 bytes; five instructions shrink
        self.assertEqual(r.size('F', 't.main'), 31)

    def test_same_object_with_no_room_in_zero_page(self):
        r = self.identical([loop_program()], env('$10 $10'))
        self.assertEqual(r.addr('S', 't.main', 0), 0xC000)
        self.assertEqual(r.size('F', 't.main'), 35)       # only STA held shrinks

    def test_shared_frames_with_every_zero_page_size(self):
        sizes = set()
        for last in range(1, 14):
            r = self.identical([frames_program()], env('$80 $%02X' % (0x80 + last)))
            sizes.add(sum(int(m[2], 16) for m in r.map if m[0] == 'F'))
        # more zero page, smaller program: the allocation really changed between runs
        self.assertGreater(len(sizes), 3)

    def test_frames_are_shared_in_that_program(self):
        r = link([frames_program()], env())
        self.assertEqual(r.addr('S', 't.a', 0), r.addr('S', 't.c', 0))

    def test_start_up_variants(self):
        for stack in ('', 'stack $80\n'):
            for leave in ('call $F00F', 'loop', 'return'):
                self.identical([loop_program()], env(stack=stack, leave=leave))

    def test_init_functions(self):
        a = lo.Builder('a')
        a.var('a.x', 1, EITHER, 2)
        f = a.func('a.main')
        f.call('b.get').op('JSR', 'abs', 'b.get').op('STA', 'abs', 'a.x').op('RTS')
        f = a.func('a.$init')
        f.op('LDA', '#', 7).op('STA', 'abs', 'a.x').op('RTS')
        b = lo.Builder('b')
        b.var('b.y', 2, NEVER)
        f = b.func('b.get')
        f.op('LDA', 'abs', 'b.y').op('RTS')
        f = b.func('b.unused')
        f.op('RTS')
        f = b.func('b.$init')
        f.op('LDA', '#', 1).op('STA', 'abs', 'b.y').op('STA', 'abs', 'b.y', 1).op('RTS')
        r = self.identical([a, b], env())
        self.assertEqual(r.map_text.splitlines()[:2], ['F 0200 000F $start', 'F 020F 0007 $init'])
        self.assertFalse(r.has('F', 'b.unused'))

    def test_constant_data_with_fix_ups(self):
        b = lo.Builder('t')
        b.var('t.v', 2, EITHER, 1)
        f = b.func('t.main')
        f.op('LDA', '#<', 't.$1').op('LDX', '#>', 't.$1', 3).op('LDA', 'abs,x', 't.$2', 1).op('RTS')
        d = b.data('t.$1', b'ab\0\0cd\0\0\0')
        d.fix(2, lo.FX_WORD, 't.main').fix(6, lo.FX_LO, 't.$2', 1).fix(7, lo.FX_HI, 't.$2', 1)
        d = b.data('t.$2', bytes(6))
        d.fix(0, lo.FX_WORD, 't.v', 1).fix(2, lo.FX_WORD, 't.$1').fix(4, lo.FX_WORD, ('t.main', 0))
        b.module_.items[1].slots.append(lo.Slot(1, NEVER, 0, LOCAL, 's'))
        self.identical([b], env())

    def test_code_placed_high(self):
        self.identical([frames_program()], env(code='$E000 $FFF0').replace('$C000 $EFFF', '$0400 $04FF'))


if __name__ == '__main__':
    unittest.main()
