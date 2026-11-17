"""Recurring patterns in the code of the Lathe-written compiler and linker that are larger than
they need be, counted over the whole build as the BBC has it.

    python3 lathe/tests/idiom_report.py OUT_DIR [--examples N]

OUT_DIR is a build made by lathe/tests/construct_report.py (the compiler in OUT_DIR/compiler,
the linker in OUT_DIR/linker); with none there it builds one. Every count is of placed bytes
(after zero page shrinking) in the functions the maps keep, the run-time modules included. Each
pattern is found by a scan of the instructions of one function (code_listing.py), with a
register memory of its own that forgets everything at a label (any branch or jump target) and
at a call, so what it calls redundant the compiler could have known; what it saves is what the
change would save at those places, before any knock-on effect.

A measuring tool (lathe/docs/spikes.md, "Size for a 128 KB ROM: the generated code, measured")."""
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import construct_report     # noqa: E402

BRANCHES = ('BCC', 'BCS', 'BEQ', 'BNE', 'BMI', 'BPL', 'BVC', 'BVS')
SETS_NZ_FROM_A = ('LDA', 'AND', 'ORA', 'EOR', 'ADC', 'SBC', 'TXA', 'TYA', 'PLA', 'ASL', 'LSR',
                  'ROL', 'ROR')
STORES = ('STA', 'STX', 'STY')


class Found:
    def __init__(self):
        self.count = collections.Counter()
        self.bytes = collections.Counter()
        self.examples = collections.defaultdict(list)

    def add(self, name, saved, f, ins, n=1):
        self.count[name] += n
        self.bytes[name] += saved
        if len(self.examples[name]) < 6:
            self.examples[name].append(f'{f.name}+{ins.offset}')


def targets_of(f):
    """Offsets in f that a branch or a jump inside f goes to."""
    at = set()
    offsets = {i.offset: i for i in f.instructions}
    for ins in f.instructions:
        if ins.mnemonic in BRANCHES or ins.mnemonic == 'BRA':
            d = ins.operand - 256 if ins.operand > 127 else ins.operand
            at.add(ins.offset + 2 + d)
        elif ins.mnemonic in ('JMP', 'JSR') and ins.target is not None and ins.target[1] == f.name \
                and ins.target[2] is None:
            at.add(ins.target[3])
    return at, offsets


def mem(ins):
    """The memory an instruction's operand names, as a key, or None (a literal address: it may
    be a device)."""
    if ins.target is None or ins.target[0] not in (1, 4, 5):
        return None
    kind, name, slot, addend = ins.target
    return (name, slot, addend, ins.mode)


def operand_key(ins):
    """What the instruction loads, as a value a register can be known to hold."""
    if ins.mode == '#':
        if ins.target is None:
            return ('#', ins.operand)
        return ('#', ins.target)
    m = mem(ins)
    if m is None or m[3] not in ('abs', 'zp'):
        return None
    return ('m',) + m[:3]


def same_memory(key, m):
    """Could memory m (name, slot, addend, mode) be what key holds?"""
    if key is None or key[0] != 'm':
        return False
    name, slot, addend = key[1:]
    if name != m[0] or slot != m[1]:
        return False
    if m[3] in ('abs', 'zp'):
        return abs(addend - m[2]) < 2
    return True


def scan(prog, found):
    for f in prog.functions:
        at, offsets = targets_of(f)
        regs = {'A': None, 'X': None, 'Y': None}
        carry = None
        nz_a = False                # N and Z are those of A
        ins_list = f.instructions
        for k, ins in enumerate(ins_list):
            mn = ins.mnemonic
            if ins.offset in at:
                regs = {'A': None, 'X': None, 'Y': None}
                carry = None
                nz_a = False
            nxt = ins_list[k + 1] if k + 1 < len(ins_list) else None
            prev = ins_list[k - 1] if k > 0 and ins.offset not in at else None
            # -- loads of what a register holds
            if mn in ('LDA', 'LDX', 'LDY'):
                r = mn[2]
                key = operand_key(ins)
                if key is not None and regs[r] == key and not (nxt and nxt.mnemonic in BRANCHES and r != 'A'):
                    found.add(f'{mn} of what {r} holds already', ins.placed, f, ins)
                elif key is not None and key[0] == '#' and ins.placed == 2:
                    for o in 'AXY':
                        if o != r and regs[o] == key and (o == 'A' or r == 'A'):
                            found.add(f'LD{r} #c where {o} holds c (T{o}{r} is 1 byte)', 1, f, ins)
                            break
            # -- CMP #0 after an instruction that set N and Z from A
            if mn == 'CMP' and ins.mode == '#' and ins.target is None and ins.operand == 0 and nxt is not None:
                if nxt.mnemonic in ('BEQ', 'BNE', 'BMI', 'BPL') and nz_a:
                    found.add('CMP #0 after A set Z (before BEQ/BNE)', ins.placed, f, ins)
                elif nxt.mnemonic in ('BEQ', 'BNE') and prev is not None and prev.mnemonic == 'JSR':
                    found.add('CMP #0 after JSR (a convention: Z of a byte result)', ins.placed, f, ins)
                elif nxt.mnemonic == 'LDA' and k + 2 < len(ins_list) and ins_list[k + 2].mnemonic == 'SBC':
                    found.add('word compare with low byte 0: LDA lo / CMP #0 dropped', ins.placed + prev.placed
                              if prev is not None and prev.mnemonic == 'LDA' else ins.placed, f, ins)
            # -- known carry
            if mn == 'CLC' and carry == 0:
                found.add('CLC with the carry known clear', 1, f, ins)
            if mn == 'SEC' and carry == 1:
                found.add('SEC with the carry known set', 1, f, ins)
            # -- JSR then RTS
            if mn == 'JSR' and nxt is not None and nxt.mnemonic == 'RTS':
                found.add('JSR then RTS (a JMP; the RTS stays for a label)' if nxt.offset in at
                          else 'JSR then RTS', 1 if nxt.offset not in at else 0, f, ins)
            # -- store then load of the same
            if mn in STORES and nxt is not None and nxt.mnemonic in ('LDA', 'LDX', 'LDY') \
                    and nxt.offset not in at and mem(ins) is not None and mem(ins) == mem(nxt) \
                    and nxt.mnemonic[2] != mn[2]:
                found.add('store then load of the same into another register (a transfer)',
                          nxt.placed - 1, f, nxt)
            # -- a word worked out in A and X, then stored to memory
            if mn == 'TAX' and nxt is not None and nxt.mnemonic == 'TYA' and k + 3 < len(ins_list):
                a, b = ins_list[k + 2], ins_list[k + 3]
                if a.mnemonic == 'STA' and b.mnemonic == 'STX' and mem(a) and mem(b) \
                        and mem(a)[:2] == mem(b)[:2]:
                    found.add('word in A and X (TAY ... TAX / TYA) then stored', 3, f, ins)
            # -- update the register memory
            m = mem(ins)
            if mn in ('LDA', 'LDX', 'LDY'):
                regs[mn[2]] = operand_key(ins)
            elif mn in STORES:
                r = mn[2]
                for o in 'AXY':
                    if m is not None and same_memory(regs[o], m):
                        regs[o] = None
                    if m is None and regs[o] and regs[o][0] == 'm':
                        regs[o] = None
                if ins.mode in ('abs', 'zp') and m is not None:
                    regs[r] = ('m',) + m[:3]
                if ins.mode == '(zp),y':
                    for o in 'AXY':
                        if regs[o] and regs[o][0] == 'm':
                            regs[o] = None
            elif mn in ('TAX', 'TAY'):
                regs[mn[2]] = regs['A']
            elif mn in ('TXA', 'TYA'):
                regs['A'] = regs[mn[1]]
            elif mn in ('INX', 'DEX'):
                regs['X'] = None
            elif mn in ('INY', 'DEY'):
                regs['Y'] = None
            elif mn in ('INC', 'DEC', 'ASL', 'LSR', 'ROL', 'ROR') and ins.mode != 'imp':
                for o in 'AXY':
                    if m is not None and same_memory(regs[o], m):
                        regs[o] = None
            elif mn in ('JSR', 'JMP', 'RTS', 'RTI', 'BRK', 'PLA', 'PLP') or mn in BRANCHES:
                if mn in ('JSR', 'PLA', 'PLP'):
                    regs = {'A': None, 'X': None, 'Y': None}
                if mn == 'PLA':
                    pass
            elif mn in ('ADC', 'SBC', 'AND', 'ORA', 'EOR', 'ASL', 'LSR', 'ROL', 'ROR'):
                regs['A'] = None
            # flags
            if mn in SETS_NZ_FROM_A or mn in ('TXA', 'TYA'):
                nz_a = True
            elif mn in ('LDX', 'LDY', 'INX', 'DEX', 'INY', 'DEY', 'CPX', 'CPY', 'CMP', 'BIT', 'INC', 'DEC',
                        'JSR', 'PLP', 'TAX', 'TAY') or (mn in ('ASL', 'LSR', 'ROL', 'ROR') and ins.mode != 'imp'):
                nz_a = mn in ('TAX', 'TAY')
            if mn == 'CLC':
                carry = 0
            elif mn == 'SEC':
                carry = 1
            elif mn == 'BCC':
                carry = 1           # falling through
            elif mn == 'BCS':
                carry = 0
            elif mn in ('ADC', 'SBC', 'CMP', 'CPX', 'CPY', 'ASL', 'LSR', 'ROL', 'ROR', 'JSR', 'PLP', 'RTI'):
                carry = None
                if mn == 'CMP' and ins.mode == '#' and ins.target is None and ins.operand == 0:
                    carry = 1


def long_branches(prog, found):
    """Bxx *+5 / JMP L: whether L is in reach of the branch now, or a JMP L (or an RTS where L
    holds one) is within reach to branch to instead."""
    for f in prog.functions:
        ins_list = f.instructions
        by_offset = {i.offset: i for i in ins_list}
        for k, ins in enumerate(ins_list):
            if ins.mnemonic in BRANCHES and ins.operand == 3 and k + 1 < len(ins_list):
                j = ins_list[k + 1]
                if j.mnemonic != 'JMP' or j.target is None or j.target[1] != f.name or j.target[2] is not None:
                    continue
                goal = j.target[3]
                found.count['long branches (Bxx over JMP)'] += 1
                found.bytes['long branches (Bxx over JMP)'] += 3
                here = ins.offset + 2
                if -128 <= goal - here <= 127:
                    found.add('long branch that would reach short now', 3, f, ins)
                    continue
                for other in ins_list:
                    if other is j:
                        continue
                    d = other.offset - here
                    if -128 <= d <= 127 and other.mnemonic == 'JMP' and other.target is not None \
                            and other.target[1] == f.name and other.target[3] == goal:
                        found.add('long branch that could branch to a JMP to the same place', 3, f, ins)
                        break


def tails(prog, found):
    """Cross-jumping: two copies of the same instructions ending in an RTS or a JMP within one
    function, where the second could be a JMP to the first (saves its length less 3)."""
    for f in prog.functions:
        at, offsets = targets_of(f)
        ins_list = f.instructions
        ends = [k for k, i in enumerate(ins_list) if i.mnemonic in ('RTS', 'JMP')]
        keyed = [(i.mnemonic, i.mode, i.operand if i.target is None else i.target) for i in ins_list]
        used = set()
        for a in range(len(ends)):
            for b in range(a + 1, len(ends)):
                ka, kb = ends[a], ends[b]
                if keyed[ka] != keyed[kb] or kb in used:
                    continue
                n = 0
                size = 0
                while ka - n >= 0 and kb - n > ka and keyed[ka - n] == keyed[kb - n]:
                    if n > 0 and ins_list[kb - n + 1].offset in at:
                        break
                    if ins_list[kb - n].mnemonic in BRANCHES:
                        break
                    size += ins_list[kb - n].placed
                    n += 1
                if size > 3 and n > 1:
                    found.add('same tail twice in a function (cross-jumping)', size - 3, f, ins_list[kb - n + 1])
                    used.add(kb)


def global_tails(prog, found, minimum=4):
    """The same instructions (with the same operands) ending a function in several functions:
    a shared epilogue would save all but one copy, less a JMP each."""
    seen = collections.defaultdict(list)
    for f in prog.functions:
        ins_list = f.instructions
        if not ins_list or ins_list[-1].mnemonic not in ('RTS', 'JMP'):
            continue
        key = []
        size = 0
        for i in reversed(ins_list[-4:]):
            if i.mnemonic in BRANCHES:
                break
            key.append((i.mnemonic, i.mode, i.operand if i.target is None else i.target))
            size += i.placed
        seen[tuple(key[:2])].append((f, size))
    # only exact: two last instructions alike, no slot operands of the function
    for key, fs in seen.items():
        if len(fs) > 1 and all(isinstance(t[2], (int, type(None))) or (isinstance(t[2], tuple) and
                                                                         t[2][2] is None) for t in key):
            size = sum(1 + (0 if t[1] in ('imp',) else 2) for t in key)
            if size > 3:
                found.add('the same last two instructions in several functions', (size - 3) * (len(fs) - 1),
                          fs[0][0], fs[0][0].instructions[-1], len(fs) - 1)


def big_index(prog, found):
    """CLC / LDA i+1 / ADC #>base / STA t+1 / LDA #<base / STA t (the address of an element of a
    big array, Y the low byte of the index), and those that repeat one already made in the
    function for the same index and array with no label, call or store to the index between."""
    for f in prog.functions:
        at, offsets = targets_of(f)
        il = f.instructions
        made = {}
        for k in range(len(il) - 5):
            if il[k].offset in at:
                made = {}
            if il[k].mnemonic == 'JSR':
                made = {}
            if il[k].mnemonic in STORES and mem(il[k]):
                m = mem(il[k])
                made = {key: v for key, v in made.items() if not (key[0][:2] == m[:2])}
            a = il[k:k + 6]
            if a[0].mnemonic == 'CLC' and a[1].mnemonic == 'LDA' and a[2].mnemonic == 'ADC' and a[2].mode == '#' \
                    and a[3].mnemonic == 'STA' and a[4].mnemonic == 'LDA' and a[4].mode == '#' \
                    and a[5].mnemonic == 'STA' and a[2].target is not None:
                size = sum(i.placed for i in a)
                found.add('big array: element pointer set up', size, f, a[0])
                key = (mem(a[1]), a[2].target)
                if key in made and mem(made[key]) == mem(a[5]):
                    found.add('big array: the same element pointer set up again', size, f, a[0])
                made[key] = a[5]


def inline_candidates(prog, found, rows):
    """Small functions called from several places: the bytes inlining would save, counted as
    (calls x (JSR + set-up)) - (calls x body) - body, for bodies of 6 bytes or less without
    their entry stores. Only an estimate."""
    sizes = {f.name: f for f in prog.functions}
    for name, r in rows.items():
        f = sizes.get(name)
        if f is None or r[0] < 2:
            continue
        body = [i for i in f.instructions if i.construct != 'function entry: register parameters stored']
        size = sum(i.placed for i in body) - 1     # no RTS
        if size <= 4 and not any(i.mnemonic == 'JSR' for i in body):
            saved = r[0] * 3 + r[4] - r[0] * size - f.size
            if saved > 0:
                found.add('small function called from several places (inline)', saved, f, f.instructions[0])


def entry_dead(prog, found):
    """A register parameter stored on entry that the function never reads (no other instruction
    names that slot). Asm functions are skipped."""
    for f in prog.functions:
        if any(i.construct == 'asm functions and blocks' for i in f.instructions):
            continue
        stores = [i for i in f.instructions if i.construct == 'function entry: register parameters stored']
        for s in stores:
            m = mem(s)
            if m is None:
                continue
            read = any(i is not s and mem(i) is not None and mem(i)[:2] == m[:2] and abs(mem(i)[2] - m[2]) < 2
                       for i in f.instructions)
            if not read:
                found.add('register parameter stored on entry and never read', s.placed, f, s)


def report(found, examples):
    for name in sorted(found.bytes, key=lambda n: -found.bytes[n]):
        ex = ', '.join(found.examples[name][:examples]) if examples else ''
        print(f'{found.bytes[name]:7d} bytes {found.count[name]:6d} times  {name}  {ex}')


def main(argv):
    out_dir = argv[0]
    examples = int(argv[argv.index('--examples') + 1]) if '--examples' in argv else 0
    if not os.path.isdir(os.path.join(out_dir, 'compiler', 'work')):
        construct_report.build(out_dir)
    for tool, main_name, env in construct_report.TOOLS:
        prog = construct_report.analyse(out_dir, tool, main_name)
        import io
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            rows = construct_report.calls_table(prog, 0)
        found = Found()
        scan(prog, found)
        long_branches(prog, found)
        tails(prog, found)
        global_tails(prog, found)
        big_index(prog, found)
        inline_candidates(prog, found, rows)
        entry_dead(prog, found)
        total = sum(f.size for f in prog.functions)
        print(f'== {tool}: {total} bytes of code')
        report(found, examples)


if __name__ == '__main__':
    main(sys.argv[1:])
