"""codegen_report.py's counts on made-up functions."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import code_listing  # noqa: E402
import codegen_report as cr  # noqa: E402

SIZES = {'imp': 1, '#': 2, 'zp': 2, 'abs': 3, 'rel': 2, '(zp),y': 2}


def function(name, lines):
    """lines: (mnemonic, mode, operand, target) with target (kind, name, slot, addend) or None."""
    f = code_listing.Function(name, 0, 0, None, None)
    offset = 0
    for mn, mode, operand, target in lines:
        i = code_listing.Instruction()
        i.offset, i.mnemonic, i.mode, i.operand, i.target = offset, mn, mode, operand, target
        i.placed = i.written = SIZES[mode]
        i.temp = target is not None and target[1] == name and str(target[2]).startswith('$t')
        f.instructions.append(i)
        offset += i.placed
    f.size = offset
    return f


def slot(name, s, addend=0):
    return (5, name, s, addend)


class Counts(unittest.TestCase):
    def test_a_store_nothing_reads_is_counted_and_one_read_is_not(self):
        f = function('m.f', [('STA', 'abs', 0, slot('m.f', 'x')), ('STA', 'abs', 0, slot('m.f', 'y')),
                             ('LDA', 'abs', 0, slot('m.f', 'y')), ('RTS', 'imp', None, None)])
        self.assertEqual([(i.offset, b) for i, b in cr.never_read(f)], [(0, 3)])

    def test_a_run_twice_becomes_a_subroutine_when_shorter(self):
        run = [('LDA', 'abs', 0, slot('m.f', 'a')), ('CLC', 'imp', None, None),
               ('ADC', 'abs', 0, slot('m.f', 'b')), ('STA', 'abs', 0, slot('m.f', 'c'))]   # 10 bytes
        f = function('m.f', run + [('INX', 'imp', None, None)] + run + [('RTS', 'imp', None, None)])
        self.assertEqual(cr.repeats(f), [(4, 2, 10, 10 - 6 - 1)])
        short = run[:2]                                  # 4 bytes: two JSRs and an RTS are more
        f = function('m.f', short + [('INX', 'imp', None, None)] + short + [('RTS', 'imp', None, None)])
        self.assertEqual(cr.repeats(f), [])

    def test_a_run_does_not_end_in_a_jsr_or_hold_a_branch(self):
        run = [('LDA', 'abs', 0, slot('m.f', 'a')), ('STA', 'abs', 0, slot('m.f', 'c')),
               ('LDA', 'abs', 0, slot('m.f', 'b')), ('JSR', 'abs', 0, (1, 'm.g', None, 0))]
        f = function('m.f', run + [('INX', 'imp', None, None)] + run + [('RTS', 'imp', None, None)])
        self.assertEqual(cr.repeats(f), [(3, 2, 9, 9 - 6 - 1)])
        branchy = [('LDA', 'abs', 0, slot('m.f', 'a')), ('BNE', 'rel', 0, None),
                   ('STA', 'abs', 0, slot('m.f', 'c'))]
        f = function('m.f', branchy + branchy + [('RTS', 'imp', None, None)])
        self.assertEqual(cr.repeats(f), [])

    def test_jsr_rts_counts_only_an_rts_nothing_branches_to(self):
        f = function('m.f', [('JSR', 'abs', 0, (1, 'm.g', None, 0)), ('RTS', 'imp', None, None)])
        self.assertEqual(cr.jsr_rts(f), 1)
        f = function('m.f', [('BEQ', 'rel', 3, None), ('JSR', 'abs', 0, (1, 'm.g', None, 0)),
                             ('RTS', 'imp', None, None)])
        self.assertEqual(cr.jsr_rts(f), 0)

    def test_a_big_array_word_read(self):
        a = (8, 'm.big', None, 0)
        p = slot('m.f', '$t3')
        f = function('m.f', [('LDA', 'zp', 0, slot('m.f', 'i')), ('ASL', 'imp', None, None),
                             ('STA', 'zp', 0, slot('m.f', '$t2')), ('LDA', 'zp', 0, slot('m.f', 'i', 1)),
                             ('ROL', 'imp', None, None), ('STA', 'zp', 0, slot('m.f', '$t2', 1)),
                             ('CLC', 'imp', None, None), ('ADC', '#', 0, a),
                             ('STA', 'zp', 0, slot('m.f', '$t3', 1)), ('LDA', '#', 0, (7, 'm.big', None, 0)),
                             ('STA', 'zp', 0, p), ('LDY', 'zp', 0, slot('m.f', '$t2')), ('INY', 'imp', None, None),
                             ('LDA', '(zp),y', 0, p), ('TAX', 'imp', None, None),
                             ('LDY', 'zp', 0, slot('m.f', '$t2')), ('LDA', '(zp),y', 0, p),
                             ('RTS', 'imp', None, None)])
        [(shape, now, saved)] = cr.big_elements(f)
        self.assertEqual((shape, now, saved), ('word LDA,LDA', 29, 19))


if __name__ == '__main__':
    unittest.main()
