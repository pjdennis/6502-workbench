"""The far-call stubs of the compiler and the linker as built for the BBC: how many, why each is
there, and what other stub forms would cost.

    python3 lathe/tests/stub_report.py OUT_DIR

OUT_DIR as for lathe/tests/construct_report.py. A stub (a T line of the map) is there for a
function in a bank that is called from fixed code, from another bank, or whose address is taken
(the start-up's calls of main and $init among them). The report counts, for each stub, where its
callers are, from the JSR and JMP instructions of the kept functions; and the bytes of:

- now: 6 bytes a stub (JSR FARCALL.call, the bank, the address less one);
- per bank: 5 bytes a stub (JSR to an entry of its bank, the address less one) and an entry of
  6 bytes for each bank (PHA / LDA #bank / JMP), the routine otherwise the same;
- the calls from code in fixed memory, and from each bank, that go through a stub.

A measuring tool (lathe/docs/spikes.md, "Size for a 128 KB ROM: the generated code, measured")."""
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import code_listing         # noqa: E402
import construct_report     # noqa: E402


def bank_of(rest):
    for r in rest:
        if r.startswith('b='):
            return int(r[2:])
    return 0


def main(argv):
    out_dir = argv[0]
    if not os.path.isdir(os.path.join(out_dir, 'compiler', 'work')):
        construct_report.build(out_dir)
    for tool, main_name, env in construct_report.TOOLS:
        work = os.path.join(out_dir, tool, 'work')
        prog = code_listing.Program(work, os.path.join(work, main_name + '.map'))
        bank = {name: bank_of(rest) for name, a, s, rest in prog.map_functions}
        stubs = {name for name, a, s in prog.stubs}
        reasons = collections.Counter()
        through = collections.Counter()
        callers = collections.defaultdict(set)
        for f in prog.functions:
            for i in f.instructions:
                if i.mnemonic in ('JSR', 'JMP') and i.target and i.target[2] is None \
                        and i.target[1] in stubs and i.target[1] != f.name:
                    callee = i.target[1]
                    if bank[f.name] != bank[callee]:
                        callers[callee].add(bank[f.name])
                        through['from fixed code' if bank[f.name] == 0 else 'from another bank'] += 1
        for s in stubs:
            c = callers.get(s, set())
            if not c:
                reasons['address taken or start-up only'] += 1
            elif c == {0}:
                reasons['called from fixed code only'] += 1
            elif 0 in c:
                reasons['called from fixed code and other banks'] += 1
            else:
                reasons['called from other banks only'] += 1
        banks = len({bank[s] for s in stubs})
        n = len(stubs)
        print(f'== {tool}: {n} stubs, {6 * n} bytes, for functions in {banks} banks')
        for k, v in reasons.most_common():
            print(f'   {v:4d}  {k}')
        for k, v in through.most_common():
            print(f'   {v:4d}  calls through a stub {k}')
        print(f'   per-bank entries: {5 * n + 6 * banks} bytes ({6 * n - 5 * n - 6 * banks} saved)')


if __name__ == '__main__':
    main(sys.argv[1:])
