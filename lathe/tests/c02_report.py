"""What the 65C02's instructions would save on the compiler and the linker as built for the BBC
(which has an NMOS 6502, so the build cannot use them there): an estimate from the NMOS code.

    python3 lathe/tests/c02_report.py OUT_DIR

OUT_DIR as for lathe/tests/construct_report.py. Counted, each a lower bound of what a code
generator that knew the instructions would do, and an upper bound of what a peephole pass on
this code would find (the register a pattern frees may be needed after it):

- BRA: a JMP to a place in the same function that a branch reaches (1 byte each);
- STZ: LDA #0 and one or more stores of A, with A loaded again before it is read (2 bytes);
- INC A, DEC A: CLC / ADC #1 and SEC / SBC #1 whose carry nothing reads (2 bytes);
- (zp): LDY #0 / LDA (p),Y or STA (p),Y with Y loaded again before it is read (2 bytes).

A measuring tool (lathe/docs/spikes.md, "Size for a 128 KB ROM: the generated code, measured")."""
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import construct_report     # noqa: E402

READS_A = ('STA', 'ADC', 'SBC', 'AND', 'ORA', 'EOR', 'CMP', 'TAX', 'TAY', 'PHA', 'ASL', 'LSR', 'ROL',
           'ROR', 'BIT', 'RTS', 'JMP', 'JSR', 'BEQ', 'BNE', 'BMI', 'BPL', 'BCC', 'BCS', 'BVC', 'BVS')
READS_C = ('ADC', 'SBC', 'ROL', 'ROR', 'BCC', 'BCS', 'RTS', 'JMP', 'JSR', 'PHP')


def dead_after(il, k, reg):
    """True if register reg ('A' or 'Y') is loaded again after il[k] before anything reads it,
    within the straight-line code that follows."""
    for i in il[k + 1:]:
        mn = i.mnemonic
        if reg == 'A':
            if mn in ('LDA', 'TXA', 'TYA', 'PLA'):
                return True
            if mn in READS_A or i.mode == 'imp' and mn in ('ASL', 'LSR', 'ROL', 'ROR'):
                return False
        else:
            if mn in ('LDY', 'TAY'):
                return True
            if mn in ('STY', 'CPY', 'INY', 'DEY', 'TYA', 'JSR', 'JMP', 'RTS') or ',y' in i.mode \
                    or mn.startswith('B'):
                return False
    return False


def carry_dead(il, k):
    for i in il[k + 1:]:
        if i.mnemonic in ('CLC', 'SEC', 'CMP', 'CPX', 'CPY') or (i.mnemonic in ('ASL', 'LSR')):
            return True
        if i.mnemonic in READS_C or i.mnemonic.startswith('B'):
            return False
    return False


def main(argv):
    out_dir = argv[0]
    if not os.path.isdir(os.path.join(out_dir, 'compiler', 'work')):
        construct_report.build(out_dir)
    for tool, main_name, env in construct_report.TOOLS:
        prog = construct_report.analyse(out_dir, tool, main_name)
        found = collections.Counter()
        for f in prog.functions:
            il = f.instructions
            for k, i in enumerate(il):
                mn = i.mnemonic
                if mn == 'JMP' and i.target and i.target[1] == f.name and i.target[2] is None:
                    if -128 <= i.target[3] - (i.offset + 2) <= 127:
                        found['BRA for a JMP'] += 1
                if mn == 'LDA' and i.mode == '#' and i.target is None and i.operand == 0:
                    j = k + 1
                    while j < len(il) and il[j].mnemonic == 'STA' and il[j].mode in ('abs', 'zp', 'abs,x', 'zp,x'):
                        j += 1
                    if j > k + 1 and dead_after(il, j - 1, 'A'):
                        found['STZ for LDA #0 / STA'] += 2
                if mn in ('CLC', 'SEC') and k + 1 < len(il) and il[k + 1].mode == '#' \
                        and il[k + 1].operand == 1 and il[k + 1].target is None \
                        and il[k + 1].mnemonic == ('ADC' if mn == 'CLC' else 'SBC') and carry_dead(il, k + 1):
                    found['INC A, DEC A for CLC / ADC #1'] += 2
                if mn == 'LDY' and i.mode == '#' and i.operand == 0 and k + 1 < len(il) \
                        and il[k + 1].mode == '(zp),y' and dead_after(il, k + 1, 'Y'):
                    found['(zp) for LDY #0 / LDA (p),Y'] += 2
        total = sum(f.size for f in prog.functions)
        print(f'== {tool}: {total} bytes; would save {sum(found.values())}')
        for k, v in found.most_common():
            print(f'{v:6d}  {k}')


if __name__ == '__main__':
    main(sys.argv[1:])
