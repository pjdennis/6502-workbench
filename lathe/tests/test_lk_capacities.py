"""The linker's capacities in every configuration it is built in: a function's first copy is node f
(lk_graph.make_nodes sets node_count to fn_count without a test of its own), so no build may hold
more functions than nodes, MAX_FUNCS <= MAX_NODES.

The twin's values are what the compiler makes of lathe/src/lk_tab.lth's capacities with each
environment's LKSMALL and LKROOMS: its block of capacities, compiled as a module of its own with
those defines, and its interface read back. The environments are every linker environment of
lathe/src/ and the ROM forms bbcrom.rom_env makes of linker-bbc.env: the B+128's, the 32K Model
B's (RAM32 1) and Image A's (ADFS 1, ADAPT 1). The host's are lathe/host/lk_tab.py's at the full,
the small and the 32K build's capacities (lk_small.load), and those lk_rooms.py gives the host
linker for Image A's machines, which change no capacity of the functions or the nodes.
"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lathec_support as support  # noqa: E402

SRC = os.path.join(support.LATHE, 'src')
LINKER_ENVS = ('linker', 'linker-bank', 'linker-full', 'linker-bbc')
ROM_FORMS = ({}, {'RAM32': 1}, {'ADFS': 1, 'ADAPT': 1})       # of linker-bbc.env
BLOCK_START = '#if LKSMALL == 2\n'                            # lk_tab.lth's capacities, from the
                                                              # first of these to the second


def capacity_block():
    """lk_tab.lth's block of capacities (MAX_FUNCS, MAX_NODES and the rest), with its #if lines."""
    with open(os.path.join(SRC, 'lk_tab.lth')) as f:
        text = f.read()
    first = text.index(BLOCK_START)
    return text[first:text.index(BLOCK_START, first + 1)]


def constant(interface, name):
    """The value of the number constant `name` (lower case) in an interface file's bytes: an entry
    is 2, the name as a string, the type and the value (test_compile.py)."""
    entry = b'\x02' + bytes((len(name),)) + name.encode('latin-1')
    at = interface.index(entry) + len(entry) + 1
    return interface[at] | interface[at + 1] << 8


def environments():
    """(name, path) of every environment the linker is built with."""
    import import_lists
    found = [(e, os.path.join(SRC, e + '.env')) for e in LINKER_ENVS]
    for settings in ROM_FORMS:
        found.append(('linker-bbc ROM form %r' % settings, import_lists.rom_form('linker-bbc', settings)))
    return found


class FunctionsAndNodes(unittest.TestCase):
    def test_the_twin_holds_no_more_functions_than_nodes_in_any_environment(self):
        import import_lists  # noqa: F401  (puts lathe/host/driver on the path)
        import mapenv
        with tempfile.TemporaryDirectory() as d:
            probe = os.path.join(d, 'probe.lth')
            with open(probe, 'w') as f:
                f.write('module probe\n' + capacity_block())
            seen = set()
            for name, path in environments():
                defines = dict(mapenv.read_env(path).defines)
                setting = (defines['LKSMALL'], defines['LKROOMS'])
                with self.subTest(environment=name, setting=setting):
                    self.assertEqual(support.run_lathec('-dLKSMALL=%d' % setting[0], '-dLKROOMS=%d' % setting[1],
                                                        probe, d), (0, ''))
                    with open(os.path.join(d, 'probe.li'), 'rb') as f:
                        interface = f.read()
                    functions, nodes = constant(interface, 'max_funcs'), constant(interface, 'max_nodes')
                    self.assertLessEqual(functions, nodes)
                seen.add(setting)
        # The full build, the small one, the 32K one and Image A's.
        self.assertEqual(seen, {(0, 0), (1, 0), (2, 0), (0, 1)})

    def test_the_host_holds_no_more_functions_than_nodes_at_any_capacities(self):
        import lk_rooms
        import lk_small
        import lk_tab
        try:
            for level in (False, True, 2):
                lk_small.load(level)
                with self.subTest(level=level):
                    self.assertLessEqual(lk_tab.MAX_FUNCS, lk_tab.MAX_NODES)
        finally:
            lk_small.load(False)
        named = {const for module, const in lk_rooms.TABLES.values()}
        self.assertFalse(named & {'MAX_FUNCS', 'MAX_NODES'})


if __name__ == '__main__':
    unittest.main()
