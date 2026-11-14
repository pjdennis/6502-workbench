"""The Lathe linker: object files in, a program image and a map file out.

    python3 lathe/host/link.py ENV MAINMODULE OUT.bin OUT.map OBJECT.lo...

Pass 1 reads everything but the code, and holds a few bytes for each function, slot, call and
symbol, never code:

    lk_envf     the environment file
    lk_scan     symbols, functions, slots, calls and classes into tables (lk_sym, lk_tab)
    lk_graph    what is reachable from main and from each interrupt function; recursion
    lk_alloc    zero page and main memory for every slot and variable
    lk_place    the size of each function after shrinking, and where its code goes

Pass 2 (lk_emit, with lk_fix, lk_boot, lk_out and lk_map) reads the code and the fix-ups and
writes the image and the map. A link error ends the program from wherever it is found
(lk_err), with exit status 1.
"""
import env
import lk_alloc
import lk_emit
import lk_envf
import lk_err
import lk_file
import lk_graph
import lk_place
import lk_scan
import lk_sym

MAIN_SUFFIX = b".main"


def find_main():
    """The function MAINMODULE.main, which some object file must define."""
    size = lk_file.arg_length(lk_file.ARG_MAIN)
    lk_sym.name_begin()
    for i in range(0, size):
        c = env.mem[lk_file.PATH + i]
        if c >= 65 and c <= 90:
            c += 32
        lk_sym.name_add(c)
    for i in range(0, len(MAIN_SUFFIX)):
        lk_sym.name_add(MAIN_SUFFIX[i])
    s, found = lk_sym.find()
    if not found or lk_sym.kind_of(s) != lk_sym.FUNCTION:
        lk_err.begin(lk_err.E_NO_MAIN)
        lk_err.colon()
        lk_sym.error_pending()
        lk_err.finish()
    return s


def main():
    if lk_file.arg_count() <= lk_file.ARG_OBJECT:
        lk_err.fail(lk_err.E_USAGE)
    lk_envf.read()
    lk_scan.scan_all()
    main_sym = find_main()
    lk_graph.build(main_sym)
    lk_alloc.allocate()
    lk_place.place()
    lk_emit.write(lk_sym.sym_a[main_sym])
    env.exit(0)


if env.is_program(__name__):
    main()
