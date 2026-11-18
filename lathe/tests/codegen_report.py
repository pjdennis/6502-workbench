"""Code-generation changes counted on the code of a linked Lathe program, from its listing
(code_listing.py): what each would save where it applies, before any knock-on effect.

    python3 lathe/tests/codegen_report.py WORK_DIR MAP [WORK_DIR MAP ...]

1. never_read(): stores into a slot of the function itself (a parameter, a local or a
   temporary) that no instruction of the function reads: by any operand naming the slot that is
   not an STA, STX or STY on it. Those stores can go (a pass over the function buffer).
2. repeats(): runs of instructions that come twice or more in one function, with no label
   inside, no branch, jump, return or stack instruction, not ending in a JSR and not starting
   after one, and not in a function with an asm block or a saving call: k copies of L bytes
   as k JSRs to one copy with an RTS save (k - 1) L - 3k - 1. Greedy, the largest saving
   first, as the experiment LATHE_X_SUBS chose them.
3. big_elements(): the element pointers of arrays of more than 256 bytes (CLC ... ADC #>array /
   STA p+1 / LDA #<array / STA p) by what follows them, and the bytes a call of a run-time
   routine with the array's address in line (JSR, then an LDA array,Y that it skips: 6 bytes,
   with 4 more for the index in A and X) would save for a byte or word read into registers.
4. jsr_rts(): JSR then RTS where nothing branches to the RTS: a JMP, one byte less.

A measuring tool (lathe/docs/spikes.md, "Generated code, a second look")."""
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import code_listing     # noqa: E402

BRANCHES = ('BCC', 'BCS', 'BEQ', 'BNE', 'BMI', 'BPL', 'BVC', 'BVS', 'BRA')
STORES = ('STA', 'STX', 'STY')
UNMOVABLE = set(BRANCHES) | {'JMP', 'RTS', 'RTI', 'BRK', 'PHA', 'PLA', 'PHP', 'PLP', 'TSX', 'TXS',
                             'PHX', 'PHY', 'PLX', 'PLY'}


def targets(f):
    """Offsets in f that a branch, or a JMP or JSR to f itself, goes to."""
    at = set()
    for i in f.instructions:
        if i.mnemonic in BRANCHES:
            d = i.operand - 256 if i.operand > 127 else i.operand
            at.add(i.offset + 2 + d)
        elif i.mnemonic in ('JMP', 'JSR') and i.target is not None and i.target[1] == f.name \
                and i.target[2] is None:
            at.add(i.target[3])
    return at


def own_slot(f, i):
    """The slot of f that instruction i names, or None."""
    if i.target is None or i.target[1] != f.name or i.target[2] is None:
        return None
    return i.target[2]


def never_read(f):
    """[(instruction, bytes)] of the stores into slots of f that nothing in f reads."""
    read = set()
    stores = []
    for i in f.instructions:
        s = own_slot(f, i)
        if s is None:
            continue
        if i.mnemonic in STORES and i.mode in ('abs', 'zp'):
            stores.append((s, i))
        else:
            read.add(s)
    return [(i, i.placed) for s, i in stores if s not in read]


def key(i):
    return (i.mnemonic, i.mode, i.operand if i.target is None else i.target)


def repeats(f, minimum=1):
    """[(length in instructions, copies, bytes of one copy, saving)] chosen greedily."""
    il = f.instructions
    if any(i.mnemonic == 'JSR' and i.target is not None and i.target[1] == f.name for i in il):
        return []           # a saving call's list or a call through a pointer: left alone
    if any(i.mnemonic == 'JSR' and i.target is not None and i.target[1].startswith('rt_frame') for i in il):
        return []
    at = targets(f)
    n = len(il)
    ok = [i.mnemonic not in UNMOVABLE for i in il]
    jsr = [i.mnemonic == 'JSR' for i in il]
    keys = [key(i) for i in il]
    taken = [False] * n
    found = []
    while True:
        best = None
        first = collections.defaultdict(list)
        for k in range(n):
            if ok[k] and not taken[k] and not (k > 0 and jsr[k - 1]):
                first[keys[k]].append(k)
        for ks in first.values():
            for a in range(len(ks)):
                for b in range(a + 1, len(ks)):
                    i, j = ks[a], ks[b]
                    m = 0
                    while j + m < n and i + m < j and ok[i + m] and ok[j + m] and not taken[i + m] \
                            and not taken[j + m] and keys[i + m] == keys[j + m] \
                            and (m == 0 or (il[i + m].offset not in at and il[j + m].offset not in at)):
                        m += 1
                    while m > 0 and jsr[i + m - 1]:
                        m -= 1
                    if m < 2:
                        continue
                    size = sum(x.placed for x in il[i:i + m])
                    places = [i]
                    for c in ks:
                        if c >= places[-1] + m and keys[c:c + m] == keys[i:i + m] \
                                and not any(taken[c:c + m]) and all(ok[c:c + m]) \
                                and not any(il[t].offset in at for t in range(c + 1, c + m)):
                            places.append(c)
                    saving = (len(places) - 1) * size - 3 * len(places) - 1
                    if saving >= minimum and (best is None or saving > best[0]):
                        best = (saving, m, places, size)
        if best is None:
            return found
        saving, m, places, size = best
        for c in places:
            for t in range(c, c + m):
                taken[t] = True
        found.append((m, len(places), size, saving))


def big_elements(f):
    """[(shape, bytes now, bytes saved by a routine)] for each big-array element pointer."""
    il = f.instructions
    at = targets(f)
    out = []
    for k, i in enumerate(il):
        if not (i.mnemonic == 'ADC' and i.mode == '#' and i.target is not None and i.target[0] in (3, 8)):
            continue
        if k + 3 >= len(il) or il[k + 1].mnemonic != 'STA' or il[k + 3].mnemonic != 'STA':
            continue
        pointer = il[k + 3].target
        s = k
        while s > 0 and k - s < 7 and il[s].offset not in at \
                and il[s - 1].mnemonic in ('CLC', 'LDA', 'ASL', 'ROL', 'STA', 'TXA', 'TYA', 'STX'):
            s -= 1
            if il[s].mnemonic == 'LDA' and il[s - 1].mnemonic not in ('STA', 'ROL', 'ASL'):
                break
        now = sum(x.placed for x in il[s:k + 4])
        shifted = any(x.mnemonic == 'ROL' for x in il[s:k])
        uses = []
        j = k + 4
        while j < len(il) and il[j].offset not in at and il[j].mnemonic not in ('JSR', 'JMP', 'RTS') \
                and il[j].mnemonic not in BRANCHES:
            x = il[j]
            if x.mnemonic == 'ADC' and x.target and x.target[0] in (3, 8):
                break
            if x.mode.startswith('(') and x.target == pointer:
                uses.append(x.mnemonic)
                now += x.placed
            elif x.mnemonic in ('LDY', 'INY', 'DEY') or (x.mnemonic == 'TAX' and uses):
                now += x.placed
            j += 1
        shape = ('word' if shifted else 'byte') + ' ' + (','.join(uses) or '-')
        saved = now - 10 if shape in ('byte LDA', 'word LDA,LDA') else 0
        out.append((shape, now, max(0, saved)))
    return out


def jsr_rts(f):
    """JSR then an RTS that nothing branches to: each a byte."""
    at = targets(f)
    il = f.instructions
    return sum(1 for a, b in zip(il, il[1:]) if a.mnemonic == 'JSR' and b.mnemonic == 'RTS'
               and b.offset not in at)


def report(prog):
    rows = collections.Counter()
    shapes = collections.Counter()
    shape_saved = collections.Counter()
    for f in prog.functions:
        dead = never_read(f)
        rows['stores that nothing reads'] += sum(b for _, b in dead)
        rows['stores that nothing reads, of temporaries'] += sum(b for i, b in dead if i.temp)
        rows['repeated runs as subroutines'] += sum(r[3] for r in repeats(f))
        for shape, now, saved in big_elements(f):
            shapes[shape] += 1
            shape_saved[shape] += saved
            rows['big-array reads through a routine'] += saved
        rows['JSR then RTS: a JMP'] += jsr_rts(f)
    return rows, shapes, shape_saved


def main(argv):
    for w, m in zip(argv[0::2], argv[1::2]):
        prog = code_listing.Program(w, m)
        total = sum(f.size for f in prog.functions)
        rows, shapes, saved = report(prog)
        print(f'== {m}: {total} bytes of code')
        for name, n in rows.items():
            print(f'{n:7d}  {name}')
        for shape, n in shapes.most_common():
            print(f'         big-array element pointer, {shape}: {n} ({saved[shape]} saved)')


if __name__ == '__main__':
    main(sys.argv[1:])
