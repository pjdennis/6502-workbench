"""The linker's host modules at the capacities of the small build of its Lathe twins.

A twin gives a capacity that sizes a table twice, `#if LKSMALL` the small value and `#else` the
full one (lathe/host/README.md, "The linker in Lathe"), and some a third time, `#if LKSMALL == 2`
before the others, for the build of a 32K BBC (lathe/src/linker-bbc.env with RAM32 1). The host
modules have only the full value. load(True) runs each linker module of lathe/host again, in the
order of its layers, with every constant the twins give under LKSMALL set to that value, so that
the tables it makes are as small; load(2) with the 32K build's, which are the `#if LKSMALL == 2`
values and, where a twin has none, the small ones (`#if LKSMALL` is true there too); load(False)
runs them again as they are. Either way every module starts afresh: no table, count or file of an
earlier run is left.

Only this file knows the mechanism: the host modules and the twins hold no trace of it beyond the
`#if LKSMALL` blocks."""
import glob
import os
import re

import lathec_support  # noqa: F401  (puts lathe/host on the path)
import test_lk_shape

SRC = os.path.join(lathec_support.LATHE, 'src')
SMALL = re.compile(r'^#if LKSMALL\n(.*?)^#else\n', re.M | re.S)
RAM32 = re.compile(r'^#if LKSMALL == 2\n(.*?)^#else\n', re.M | re.S)     # the 32K BBC's build
CONST = re.compile(r'^(?:pub )?const (\w+) = (\$?[0-9A-Fa-f]+)', re.M)

# The linker's modules, lowest first.
MODULES = [m for m in test_lk_shape.LAYERS if m.startswith('lk_')]


def number(text):
    return int(text[1:], 16) if text.startswith('$') else int(text)


def capacities(level=True):
    """{module: {NAME: small value}} from the `#if LKSMALL` blocks of lathe/src/lk_*.lth; with
    level 2, the 32K build's: those of the `#if LKSMALL == 2` blocks over them."""
    found = {}
    for path in sorted(glob.glob(os.path.join(SRC, 'lk_*.lth'))):
        with open(path) as f:
            text = f.read()
        values = {}
        for pattern in (SMALL, RAM32) if level == 2 else (SMALL,):
            for block in pattern.findall(text):
                for name, value in CONST.findall(block):
                    values[name] = number(value)
        if values:
            found[os.path.basename(path)[:-4]] = values
    return found


def source(module, small):
    """The host module's source, with the small capacities if `small` (the 32K build's if 2)."""
    with open(os.path.join(lathec_support.HOST, module + '.py')) as f:
        text = f.read()
    if small:
        for name, value in capacities(small).get(module, {}).items():
            text, n = re.subn(r'^%s = [^\n#]*' % name, '%s = %d ' % (name, value), text, flags=re.M)
            assert n == 1, (module, name)
    return text


_compiled = {}


def load(small):
    """Run every linker module of lathe/host again, at the small capacities (the 32K build's, with
    2) or at full ones."""
    import importlib
    for module in MODULES:
        key = (module, small)
        if key not in _compiled:
            _compiled[key] = compile(source(module, small), os.path.join(lathec_support.HOST, module + '.py'),
                                     'exec')
        mod = importlib.import_module(module)
        exec(_compiled[key], mod.__dict__)
