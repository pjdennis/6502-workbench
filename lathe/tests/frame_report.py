"""What saving calls (calls between `recursive` functions) cost in the tools as built for the
BBC.

    python3 lathe/tests/frame_report.py OUT_DIR

OUT_DIR as for lathe/tests/construct_report.py. A saving call pushes the caller's frame with
`JSR rt_frame.push` and the list after it (`LDA #n`, then an `ORA slot-i,Y` for each word and an
`LDA slot-i,Y` for each odd last byte of a slot) and pops it with `JSR rt_frame.pop` and a `JSR`
to the list (lathe/docs/code-model.md, "Recursion"). For each tool this counts the saving calls
that save something, their lists, entries and frame bytes, the bytes at the calls and in the
lists, as placed; what lists shared by the calls of one function that save the same slots would
save; and the functions with the most bytes of it.

A measuring tool (lathe/docs/spikes.md, "Size for a 128 KB ROM: the generated code, measured",
and "Built: saving calls through a list")."""
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import construct_report     # noqa: E402

OP_LIST_BYTE = 0xB9         # LDA abs,Y: an entry of one byte
OP_LIST_WORD = 0x19         # ORA abs,Y: an entry of two bytes


def is_call(i, name):
    return i.mnemonic == 'JSR' and i.target is not None and i.target[1] == name


def lists(f):
    """[(entries as (slot target, bytes), bytes of the list)] of the lists after f's JSRs to
    rt_frame.push, and the number of JSRs to rt_frame.pop (each followed by a JSR to a list)."""
    il = f.instructions
    found = []
    pops = 0
    for k, i in enumerate(il):
        if is_call(i, 'rt_frame.pop'):
            pops += 1
        if not is_call(i, 'rt_frame.push') or k + 1 >= len(il) or il[k + 1].mnemonic != 'LDA' \
                or il[k + 1].target is not None:
            continue
        entries, size = [], il[k + 1].placed
        j = k + 2
        while j < len(il) and il[j].opcode in (OP_LIST_BYTE, OP_LIST_WORD) and il[j].target:
            kind, name, slot, addend = il[j].target
            entries.append(((name, slot), 1 if il[j].opcode == OP_LIST_BYTE else 2))
            size += il[j].placed
            j += 1
        if not entries:
            raise SystemExit(f'{f.name}: a JSR rt_frame.push without a list after it')
        found.append((entries, size))
    return found, pops


def main(argv):
    out_dir = argv[0]
    if not os.path.isdir(os.path.join(out_dir, 'compiler', 'work')):
        construct_report.build(out_dir)
    for tool, main_name, env in construct_report.TOOLS:
        prog = construct_report.analyse(out_dir, tool, main_name)
        calls = entries = frame = at_calls = in_lists = shared = functions = 0
        hist = collections.Counter()
        biggest = []
        for f in prog.functions:
            found, pops = lists(f)
            if not found:
                continue
            functions += 1
            calls += pops
            cost = 9 * pops + sum(size for _, size in found)
            at_calls += 9 * pops
            in_lists += sum(size for _, size in found)
            seen = set()
            for e, size in found:
                entries += len(e)
                frame += sum(b for _, b in e)
                hist[sum(b for _, b in e)] += 1
                key = tuple(t for t, _ in e)
                if key in seen:
                    shared += size
                seen.add(key)
            biggest.append((cost, f.name, pops, len(found), len(seen)))
        print(f'== {tool}: {functions} functions with {calls} saving calls that save something')
        if not calls:
            continue
        print(f'   {sum(hist.values())} lists, {entries} entries, '
              f'{frame} bytes of frame; {at_calls} bytes of JSRs to push, pop and the lists, '
              f'{in_lists} bytes of lists: {at_calls + in_lists} in all (in line, 12 a byte: '
              f'{12 * frame})')
        print(f'   lists that repeat another of their function: {shared} bytes')
        print('   frame bytes a list: ' + ', '.join(f'{k}: {v}' for k, v in sorted(hist.items())))
        for cost, name, n, lst, sets in sorted(biggest, reverse=True)[:12]:
            print(f'   {cost:5d} {name}: {n} calls, {lst} lists, {sets} sets')


if __name__ == '__main__':
    main(sys.argv[1:])
