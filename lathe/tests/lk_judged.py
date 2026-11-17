#!/usr/bin/env python3
"""A stand-in linker for build.py (LATHE_LINKER) that measures what each bank holds: it runs the
host linker (lathe/host/link.py) in this process, with the same arguments and the same output,
and appends to the file named by $LK_JUDGED_OUT, for each bank, each module's bytes as the
linker judges them (as written, before zero page shrinks the code: lk_place, the fit check) and
as placed, and each module's bytes placed in fixed memory. rom_report.py uses it.

    LATHE_LINKER=lathe/tests/lk_judged.py LK_JUDGED_OUT=FILE python3 ... build.py ...

The lines it writes:

    == ENV MAIN
    bank N: judged J placed P  MODULE J/P, ...
    fixed MODULE P, ...
"""
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'host'))

import env  # noqa: E402
import lk_place  # noqa: E402


def main(args):
    objects = args[4:]
    env.start(args)
    current = [None]
    judged, placed = collections.Counter(), collections.Counter()
    place_object, take_bank, take = lk_place.place_object, lk_place.take_bank, lk_place.take

    def counting_place_object(obj):
        current[0] = os.path.splitext(os.path.basename(objects[obj]))[0]
        return place_object(obj)

    def counting_take_bank(b, size, written):
        judged[(current[0], b + 1)] += written
        placed[(current[0], b + 1)] += size
        return take_bank(b, size, written)

    def counting_take(size):
        placed[(current[0] or '$start', 0)] += size
        return take(size)

    lk_place.place_object = counting_place_object
    lk_place.take_bank = counting_take_bank
    lk_place.take = counting_take
    import link
    status = 0
    try:
        link.main()
    except SystemExit as e:
        status = e.code or 0
    banks = collections.defaultdict(list)
    for (m, b), w in judged.items():
        banks[b].append((m, w, placed[(m, b)]))
    with open(os.environ['LK_JUDGED_OUT'], 'a') as fh:
        fh.write(f'== {args[0]} {args[1]}\n')
        for b in sorted(banks):
            rows = sorted(banks[b], key=lambda r: -r[1])
            fh.write(f'bank {b}: judged {sum(r[1] for r in rows)} placed {sum(r[2] for r in rows)}  '
                     + ', '.join(f'{m} {w}/{p}' for m, w, p in rows) + '\n')
        fixed = sorted(((m, v) for (m, b), v in placed.items() if b == 0), key=lambda mv: -mv[1])
        fh.write('fixed ' + ', '.join(f'{m} {v}' for m, v in fixed) + '\n')
    return status


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
