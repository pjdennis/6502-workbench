"""The Lathe linker: object files in, a program image and a map file out.

    python3 lathe/host/link.py ENV MAINMODULE OUT.bin OUT.map OBJECT.lo...

Pass 1 never reads code, and holds a few bytes for each function, slot, call and symbol:

    lk_envf     the environment file
    lk_scan     symbols, functions, slots, calls, classes and weights into tables (lk_sym,
                lk_tab); fix-ups are only checked
    lk_graph    what is reachable from main and from each interrupt function, and what that
                keeps by naming it, which it finds by reading the fix-ups again, as often as
                that keeps something new (usually twice); recursion
    lk_alloc    zero page and main memory for every slot and variable
    lk_place    the size of each function after shrinking, from its fix-ups, and where its
                code goes

Pass 2 (lk_emit, with lk_fix, lk_boot, lk_out and lk_map) reads each file once more, in order,
holding one function's or one table's fix-ups at a time, and writes the image and the map. A
link error ends the program from wherever it is found (lk_err), with exit status 1.
"""
import env
import lk_alloc
import lk_emit
import lk_envf
import lk_err
import lk_file
import lk_graph
import lk_name
import lk_place
import lk_scan
import lk_sym
import lk_tab

def find_main():
    """The function MAINMODULE.main, which some object file must define. lk_name noted the
    symbol of that name while the files were read."""
    s = lk_name.main_sym
    if s == lk_tab.NONE or lk_sym.kind_of(s) != lk_sym.FUNCTION or not lk_sym.is_defined(s):
        lk_err.begin(lk_err.E_NO_MAIN)
        lk_err.colon()
        size = lk_file.arg_length(lk_file.ARG_MAIN)
        for i in range(0, size):
            c = env.mem[lk_file.PATH + i]
            if c >= 65 and c <= 90:
                c += 32
            lk_err.put(c)
        for i in range(0, len(lk_name.MAIN_SUFFIX)):
            lk_err.put(lk_name.MAIN_SUFFIX[i])
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
    lk_emit.write(lk_sym.row_of(main_sym))
    env.exit(0)


if env.is_program(__name__):
    main()
