"""The linker's host modules at the capacities of the small build of its Lathe twins.

A twin gives a capacity that sizes a table twice, `#if LKSMALL` the small value and `#else` the
full one (lathe/host/README.md, "The linker in Lathe"). The host modules have only the full
value. load(True) runs each linker module of lathe/host again, in the order of its layers, with
every constant the twins give under LKSMALL set to that value, so that the tables it makes are
as small; load(False) runs them again as they are. Either way every module starts afresh: no
table, count or file of an earlier run is left.

Only this file knows the mechanism: the host modules and the twins hold no trace of it beyond the
`#if LKSMALL` blocks."""
import glob
import os
import re

import lathec_support  # noqa: F401  (puts lathe/host on the path)
import test_lk_shape

SRC = os.path.join(lathec_support.LATHE, 'src')
SMALL = re.compile(r'^#if LKSMALL\n(.*?)^#else\n', re.M | re.S)
CONST = re.compile(r'^(?:pub )?const (\w+) = (\$?[0-9A-Fa-f]+)', re.M)

# The linker's modules, lowest first.
MODULES = [m for m in test_lk_shape.LAYERS if m.startswith('lk_')]


def number(text):
    return int(text[1:], 16) if text.startswith('$') else int(text)


def capacities():
    """{module: {NAME: small value}} from the `#if LKSMALL` blocks of lathe/src/lk_*.lth."""
    found = {}
    for path in sorted(glob.glob(os.path.join(SRC, 'lk_*.lth'))):
        with open(path) as f:
            text = f.read()
        values = {}
        for block in SMALL.findall(text):
            for name, value in CONST.findall(block):
                values[name] = number(value)
        if values:
            found[os.path.basename(path)[:-4]] = values
    return found


def source(module, small):
    """The host module's source, with the small capacities if `small`."""
    with open(os.path.join(lathec_support.HOST, module + '.py')) as f:
        text = f.read()
    if small:
        for name, value in capacities().get(module, {}).items():
            text, n = re.subn(r'^%s = [^\n#]*' % name, '%s = %d ' % (name, value), text, flags=re.M)
            assert n == 1, (module, name)
    return text


_compiled = {}


def load(small):
    """Run every linker module of lathe/host again, at the small capacities or at full ones."""
    import importlib
    for module in MODULES:
        key = (module, small)
        if key not in _compiled:
            _compiled[key] = compile(source(module, small), os.path.join(lathec_support.HOST, module + '.py'),
                                     'exec')
        mod = importlib.import_module(module)
        exec(_compiled[key], mod.__dict__)
