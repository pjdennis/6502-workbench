"""What passing arguments in registers would save in lathe/src/lextest.lth: for every function,
its call sites and the bytes each spends storing arguments into the callee's slots, and the
net saving of three conventions against today's (every argument stored in its slot).

    python3 lathe/tests/arg_report.py BUILD_DIR [--functions]

BUILD_DIR is a build that size_report.py made (its work/ directory has the objects and the
map). The conventions:
  a  the first parameter, if it is a byte, in A;
  b  the first three byte parameters (wherever they are in the list) in A, X and Y;
  c  the first parameter in A if it is a byte, in A and X if it is a word or pointer;
  d  b and c together: a first word or pointer in A and X, otherwise b.
A call site saves the stores of the arguments that go in registers (the loads stay). An
argument the caller computed (not a constant or a plain variable) must be computed last, so
only one computed argument can go in a register; a computed word in A and X costs TAY / TAX /
TYA (3 bytes) more than storing it, and is counted as saving the stores less 3. The callee
pays a store of each register into its slot on entry; "less" also credits the callee's first
instruction when it loads the parameter just stored, which it would no longer need."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'host', 'driver'))
import cpu6502  # noqa: E402
import lo  # noqa: E402

STORES = ('STA', 'STX', 'STY')
REG_OF = {'STA': 'A', 'STX': 'X', 'STY': 'Y'}


def slot_places(map_path):
    """{(function, slot number): address} from the S lines of the map."""
    places = {}
    with open(map_path) as f:
        for line in f:
            p = line.split()
            if p and p[0] == 'S':
                places[(p[3], int(p[4]))] = int(p[1], 16)
    return places


def instructions(func, cpu):
    """[(offset, mnemonic, mode, length, fix or None)] of a function's code."""
    fixes = {f.offset: f for f in func.fixes}
    out, at = [], 0
    while at < len(func.code):
        m, mode, n = cpu6502.decode(cpu, func.code, at)
        out.append((at, m, mode, n, fixes.get(at + 1)))
        at += n
    return out


def writes(reg, m, mode):
    if reg == 'A':
        return m in ('ADC', 'SBC', 'AND', 'ORA', 'EOR', 'TXA', 'TYA', 'PLA') or \
            (m in ('ASL', 'LSR', 'ROL', 'ROR') and mode == cpu6502.IMP)
    if reg == 'X':
        return m in ('TAX', 'INX', 'DEX', 'TSX')
    return m in ('TAY', 'INY', 'DEY')


def source_kind(ins, i, reg):
    """What register `reg` was last set from before instruction i: 'const', 'var' or 'computed'."""
    load = {'A': 'LDA', 'X': 'LDX', 'Y': 'LDY'}[reg]
    for j in range(i - 1, -1, -1):
        _, m, mode, _, fix = ins[j]
        if m == 'JSR' or mode == cpu6502.REL:
            return 'computed'
        if m == load:
            if mode == cpu6502.IMM:
                return 'const'
            if mode in (cpu6502.ABS, cpu6502.ZP):
                return 'var'
            return 'computed'
        if writes(reg, m, mode):
            return 'computed'
    return 'computed'


def main(argv):
    build = argv[0]
    show = '--functions' in argv
    work = os.path.join(build, 'work')
    mapname = [f for f in os.listdir(work) if f.endswith('.map')][0]
    places = slot_places(os.path.join(work, mapname))
    mods = [lo.load(os.path.join(work, f)) for f in sorted(os.listdir(work)) if f.endswith('.lo')]
    funcs = {}                          # name -> (module, Func)
    for m in mods:
        for f in m.functions():
            funcs[m.sym_name(f.sym)] = (m, f)
    kept = {name for name in funcs if any(k[0] == name for k in places)} | \
        {line.split()[3] for line in open(os.path.join(work, mapname)) if line.startswith('F ')}

    def params(name):
        m, f = funcs[name]
        return [(n, s) for n, s in enumerate(f.slots) if s.kind == lo.SK_PARAM]

    def store_size(name, slot):
        return 2 if places.get((name, slot), 0x100) < 0x100 else 3

    # Call sites: for each JSR or JMP to a function, the stores into its parameter slots
    # since the previous call to it in the same function.
    sites = []                          # (caller, callee, {param: [bytes stored, kind]})
    for m in mods:
        for f in m.functions():
            caller = m.sym_name(f.sym)
            if caller not in kept:
                continue
            ins = instructions(f, m.cpu)
            pending = {}
            for i, (at, mn, mode, n, fix) in enumerate(ins):
                if fix is None or fix.sym == f.sym and fix.slot == lo.NO_SLOT:
                    continue
                target = m.sym_name(fix.sym)
                if mn in STORES and fix.slot != lo.NO_SLOT and target in funcs and target != caller:
                    entry = pending.setdefault(target, {}).setdefault(fix.slot, [0, 'const'])
                    entry[0] += n if fix.kind != lo.FX_ZP else 2
                    if n == 3 and store_size(target, fix.slot) == 2:
                        entry[0] -= 1                       # the linker shrinks it
                    kind = source_kind(ins, i, REG_OF[mn])
                    if kind == 'computed' or entry[1] == 'computed':
                        entry[1] = 'computed'
                    elif kind == 'var':
                        entry[1] = 'var'
                if mn in ('JSR', 'JMP') and fix.slot == lo.NO_SLOT and target in funcs:
                    tm, tf = funcs[target]
                    if tf.flags & lo.F_REGISTERS:
                        continue
                    sites.append((caller, target, pending.pop(target, {})))

    per = {}
    for caller, callee, stored in sites:
        per.setdefault(callee, []).append(stored)

    totals = {'a': [0, 0, 0], 'b': [0, 0, 0], 'c': [0, 0, 0], 'd': [0, 0, 0]}    # call sites save, callee pays, credit
    rows = []
    for callee in sorted(per):
        ps = params(callee)
        if not ps:
            continue
        calls = per[callee]
        spent = sum(sum(v[0] for v in s.values()) for s in calls)
        m, f = funcs[callee]
        ins = instructions(f, m.cpu)
        first_loads = None
        if ins and ins[0][1] in ('LDA', 'LDX', 'LDY') and ins[0][4] is not None \
                and ins[0][4].sym == f.sym and ins[0][4].slot != lo.NO_SLOT:
            first_loads = ins[0][4].slot
        row = [callee, len(calls), spent]
        for conv in ('a', 'b', 'c', 'd'):
            if conv == 'd' and ps[0][1].size == 2:
                chosen = [ps[0]]
            elif conv == 'a':
                chosen = [ps[0]] if ps[0][1].size == 1 else []
            elif conv == 'b' or conv == 'd':
                chosen = [p for p in ps if p[1].size == 1][:3]
            else:
                chosen = [ps[0]] if ps[0][1].size <= 2 else []
            save = 0
            for s in calls:
                computed = 0
                for n, slot in chosen:
                    stored, kind = s.get(n, [0, 'const'])
                    if kind == 'computed':
                        computed += 1
                        if computed > 1:
                            continue
                        if slot.size == 2:
                            stored = max(stored - 3, 0)
                    save += stored
            pay = sum(store_size(callee, n) * slot.size for n, slot in chosen)
            credit = 0
            if first_loads is not None and any(n == first_loads for n, _ in chosen):
                credit = ins[0][3] if store_size(callee, first_loads) == 3 else 2
            totals[conv][0] += save
            totals[conv][1] += pay if chosen else 0
            totals[conv][2] += credit
            row.append((save, pay if chosen else 0, credit))
        rows.append(row)

    total_spent = sum(r[2] for r in rows)
    print('call sites %d, bytes spent storing arguments %d' % (sum(r[1] for r in rows), total_spent))
    for conv in ('a', 'b', 'c', 'd'):
        save, pay, credit = totals[conv]
        print('convention %s: call sites save %4d, callees pay %4d, net %+4d (%+4d with the first load '
              'credited)' % (conv, save, pay, save - pay, save - pay + credit))
    if show:
        print()
        print('%-28s %5s %6s   %-15s %-15s %-15s' % ('function', 'calls', 'stores', 'a save/pay/cr',
                                                     'b save/pay/cr', 'c save/pay/cr'))
        for r in sorted(rows, key=lambda r: -r[2]):
            print('%-28s %5d %6d   %-15s %-15s %-15s' % (r[0], r[1], r[2], '%d/%d/%d' % r[3],
                                                         '%d/%d/%d' % r[4], '%d/%d/%d' % r[5]))


if __name__ == '__main__':
    main(sys.argv[1:])
