"""No row of the linker's tables is read before something wrote it.

In Python a table starts as 0s; in the twin (lathe/src/lk_*.lth) a table has no initial value,
so it holds whatever memory held when the linker started: on the BBC, what the compiler or the
language left there (the BBC's tool chain, lathe/tests/test_bbc_toolchain.py, fills memory
first). So a row the host linker reads before writing it would be junk in the twin. This test
runs the host linker at the small capacities over the links made by hand (test_src_lk.py's,
test_src_link.py's) and lk_synthetic's program with every table wrapped, and lists every place
that reads a row nothing wrote.

The one exception is half of a word of the work area: lk_name.put_b writes one byte of a word
and keeps the other, which it reads to do so; the other byte is never used unless written.
"""
import io
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lathec_support  # noqa: E402
import lk_small  # noqa: E402
import test_src_lk as lk  # noqa: E402
import test_src_link as whole  # noqa: E402
import env  # noqa: E402

# (table, file, function) of reads that keep a byte they do not use.
BENIGN = {('lk_tab.work', 'lk_name.py', 'put_b')}


def tracked(base):
    class Tracked(base):
        """A table that notes the places that read a row nothing wrote."""
        def __init__(self, name, data, found):
            super().__init__(data)
            self.name, self.found, self.written = name, found, set()

        def __setitem__(self, i, v):
            self.written.add(i)
            super().__setitem__(i, v)

        def __getitem__(self, i):
            if i not in self.written:
                code = sys._getframe(1).f_code
                key = (self.name, os.path.basename(code.co_filename), code.co_name)
                if key not in BENIGN:
                    self.found.add(key)
            return super().__getitem__(i)
    return Tracked


TRACKED = {list: tracked(list), bytearray: tracked(bytearray)}


def run_tracked(case, d, found):
    """The host linker at the small capacities on the case in directory d, every table wrapped."""
    import importlib
    import link
    for name, data in case.files.items():
        os.makedirs(os.path.dirname(os.path.join(d, name)), exist_ok=True)
        with open(os.path.join(d, name), 'wb') as f:
            f.write(data)
    lathec_support.fresh()
    lk_small.load(True)
    for m in lk_small.MODULES:
        mod = importlib.import_module(m)
        for k, v in list(vars(mod).items()):
            if not k.startswith('__') and type(v) in TRACKED:
                setattr(mod, k, TRACKED[type(v)](m + '.' + k, v, found))
    env._out = io.BytesIO()
    env.start(case.args)
    here = os.getcwd()
    os.chdir(d)
    try:
        link.main()
    except SystemExit:
        pass
    finally:
        os.chdir(here)


class Unset(unittest.TestCase):
    def tearDown(self):
        lk_small.load(False)

    def test_no_row_is_read_before_it_is_written(self):
        from test_lk_support import HOST_ENV
        cases = [lk.link_case(t, HOST_ENV, o, m) for t, o, m in lk.hand_made_links()]
        cases += [lk.link_case(t, e, o, m) for t, e, o, m in lk.graph_links()]
        cases += [lk.link_case(t, e, o, m) for t, e, o, m in whole.edge_links()]
        cases.append(lk.synthetic_case(lk.SYNTHETIC_FITS))
        found = set()
        with tempfile.TemporaryDirectory() as work:
            for case in cases:
                run_tracked(case, tempfile.mkdtemp(dir=work), found)
        self.assertEqual(sorted(found), [])


if __name__ == '__main__':
    unittest.main()
