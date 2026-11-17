"""What saving calls (calls between `recursive` functions) cost in the compiler as built for the
BBC, and what other forms of the frame push and pop would cost.

    python3 lathe/tests/frame_report.py OUT_DIR

OUT_DIR as for lathe/tests/construct_report.py. A saving call's push is a run of
`LDA slot / JSR rt_frame.push` and its pop a run of `JSR rt_frame.pop_y / STY slot`. For each
function with saving calls this finds the runs, the bytes they take, how many distinct sets of
slots they push, and the size of three other forms:

- shared: one push routine and one pop routine of the function's own for each distinct set,
  `JSR` to them at each call (3 + 3 bytes a call, plus each routine once, with its RTS);
- whole frame: one push and one pop routine of the function's own that save every slot the
  function's calls save (the union), entered by every call;
- list: `LDA #<list / LDX #>list / JSR rt_frame.push_list` and `JSR rt_frame.pop_list` at each
  call (10 bytes) with the list of slot addresses as constant data (2 bytes a slot byte, 1 for
  its length), shared by the calls that push the same set; plus the two routines once.

A measuring tool (lathe/docs/spikes.md, "Size for a 128 KB ROM: the generated code, measured")."""
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import construct_report     # noqa: E402

LIST_ROUTINES = 70      # estimated: push_list and pop_list, a pointer in zero page, NMOS


def runs(f):
    """[(kind, [slot keys], bytes)] of the pushes and pops in f."""
    il = f.instructions
    out = []
    k = 0
    while k < len(il):
        i = il[k]
        if i.mnemonic == 'LDA' and k + 1 < len(il) and il[k + 1].mnemonic == 'JSR' \
                and il[k + 1].target and il[k + 1].target[1] == 'rt_frame.push':
            slots, size = [], 0
            while k + 1 < len(il) and il[k].mnemonic == 'LDA' and il[k + 1].mnemonic == 'JSR' \
                    and il[k + 1].target and il[k + 1].target[1] == 'rt_frame.push':
                slots.append((il[k].target, il[k].placed))
                size += il[k].placed + il[k + 1].placed
                k += 2
            out.append(('push', slots, size))
            continue
        if i.mnemonic == 'JSR' and i.target and i.target[1] == 'rt_frame.pop_y':
            slots, size = [], 0
            while k + 1 < len(il) and il[k].mnemonic == 'JSR' and il[k].target \
                    and il[k].target[1] == 'rt_frame.pop_y' and il[k + 1].mnemonic == 'STY':
                slots.append((il[k + 1].target, il[k + 1].placed))
                size += il[k].placed + il[k + 1].placed
                k += 2
            out.append(('pop', slots, size))
            continue
        k += 1
    return out


def main(argv):
    out_dir = argv[0]
    if not os.path.isdir(os.path.join(out_dir, 'compiler', 'work')):
        construct_report.build(out_dir)
    for tool, main_name, env in construct_report.TOOLS:
        prog = construct_report.analyse(out_dir, tool, main_name)
        now = shared = whole = listed = 0
        calls = 0
        functions = 0
        hist = collections.Counter()
        biggest = []
        for f in prog.functions:
            r = runs(f)
            pushes = [x for x in r if x[0] == 'push']
            pops = [x for x in r if x[0] == 'pop']
            if not pushes:
                continue
            functions += 1
            calls += len(pushes)
            cost = sum(x[2] for x in r)
            now += cost
            sets = collections.Counter(tuple(t for t, b in x[1]) for x in pushes)
            # shared: routine per distinct set: push routine = its run + RTS, pop routine = run + RTS
            routine = {}
            for x in pushes:
                routine[tuple(t for t, b in x[1])] = x[2] + 1
            for x in pops:
                key = tuple(reversed([t for t, b in x[1]]))
                routine[('pop',) + key] = x[2] + 1
            s = 6 * len(pushes) + sum(routine.values())
            shared += min(s, cost)
            union = {}
            for x in pushes:
                for t, b in x[1]:
                    union[t] = b
            w = 6 * len(pushes) + 2 * sum(b + 3 for b in union.values()) + 2
            whole += min(w, cost)
            lst = 10 * len(pushes) + sum(1 + 2 * len(k) for k in sets)
            listed += lst
            for x in pushes:
                hist[len(x[1])] += 1
            biggest.append((cost, f.name, len(pushes), len(sets), len(union)))
        print(f'== {tool}: {functions} functions with {calls} saving calls; push and pop {now} bytes')
        if not calls:
            continue
        print(f'   shared routines per set: {shared} ({now - shared} saved)')
        print(f'   one routine pair for the whole frame: {whole} ({now - whole} saved)')
        print(f'   lists in constant data: {listed} + routines {LIST_ROUTINES} '
              f'({now - listed - LIST_ROUTINES} saved)')
        print('   bytes saved a call: ' + ', '.join(f'{k}: {v}' for k, v in sorted(hist.items())))
        for cost, name, n, sets, u in sorted(biggest, reverse=True)[:12]:
            print(f'   {cost:5d} {name}: {n} calls, {sets} sets, {u} bytes in all')


if __name__ == '__main__':
    main(sys.argv[1:])
