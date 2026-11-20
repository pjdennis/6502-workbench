"""The host linker, lathe/host/link.py, with the capacities that the image for every machine with
sideways RAM sets as its linker starts (lathe/docs/bbc.md, "The linker's tables on two banks"),
for test_bbc_rooms.py and test_gen_program.py:

    LATHE_LK_CAPACITIES=locals=1536,slots=2304,calls=1280 python3 lathe/tests/lk_rooms.py ARGS...

`locals` is lk_name.MAX_LOCALS (the rows of lk_name.local), `slots` lk_tab.MAX_SLOTS (of slot_sz
and slot_weight) and `calls` lk_tab.MAX_EDGES (of edge_word): what the twins call local_rows,
slot_rows and edge_rows. Every other capacity is the full build's, or with LATHE_LK_SMALL=2 the
32K build's (LKSMALL 2), as the image for machines with no sideways RAM has them (test_bbc_image_b.py).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'host'))

TABLES = {'locals': ('lk_name', 'MAX_LOCALS'), 'slots': ('lk_tab', 'MAX_SLOTS'), 'calls': ('lk_tab', 'MAX_EDGES')}


def values(text):
    """{module: {NAME: value}} for lk_small.load_values from `locals=N,slots=N,calls=N`."""
    found = {}
    for item in text.split(','):
        name, size = item.split('=')
        module, const = TABLES[name]
        found.setdefault(module, {})[const] = int(size)
    return found


def setting(capacities):
    """The LATHE_LK_CAPACITIES text of {table: rows}."""
    return ','.join('%s=%d' % (k, v) for k, v in sorted(capacities.items()))


if __name__ == '__main__':
    import lk_small
    given = values(os.environ['LATHE_LK_CAPACITIES'])
    if os.environ.get('LATHE_LK_SMALL') == '2':     # the 32K build's other capacities (Image B)
        base = lk_small.capacities(2)
        for module, names in given.items():
            base.setdefault(module, {}).update(names)
        given = base
    lk_small.load_values(given)
    import env
    env.start(sys.argv[1:])
    import link
    link.main()
