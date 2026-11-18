"""The memory the compiler's tables take (lathe/tests/memory_report.py, lathe/docs/architecture.md,
"What stays in memory"): within the budget, counted the way the Lathe twins lay the tables out."""
import os
import re
import unittest

import memory_report as report

TWINS = ('err', 'kernel', 'src', 'lex', 'typetab', 'fold', 'fbuf', 'out', 'reg', 'cond', 'gen', 'asmblock',
         'inline', 'parts', 'expr', 'decl', 'lathec')
TWIN_FILE = {'inline': 'inlines'}     # a twin whose module has another name: `inline` is a keyword
VAR = re.compile(r'^(?:pub )?var (\w+): \[[^\]]+\](\^?\w+)', re.M)
# Arrays of a twin that are not arrays of its host module, and why.
CEILING = 43379             # the total of lathe/docs/architecture.md, "What stays in memory"
TWIN_ONLY = {('kernel', 'text'): 'the text memory, which the host keeps in env.mem',
             ('kernel', 'tokens'): 'the token memory, which the host keeps in env.mem'}


def twin_arrays(module):
    """{name: bytes per element} of the module-level arrays of lathe/src/MODULE.lth."""
    with open(os.path.join(report.LATHE, 'src', TWIN_FILE.get(module, module) + '.lth')) as f:
        text = f.read()
    return {name: 1 if t in ('byte', 'sbyte', 'bool') else 2 for name, t in VAR.findall(text)}


CONST = re.compile(r'^(?:pub )?const (\w+) = (\d+)', re.M)


def twin_capacities(module):
    """{name: {'small': N, 'full': N, 'ram32': N}} of the constants lathe/src/MODULE.lth declares
    under `#if SMALL`, `#else` and, inside `#if SMALL`, `#if RAM32` (the 32K Model B's: its
    `#else` is the small build's). A constant of no `#if RAM32` has the small build's size there."""
    with open(os.path.join(report.LATHE, 'src', TWIN_FILE.get(module, module) + '.lth')) as f:
        lines = f.read().splitlines()
    found = {}
    stack = []                      # the conditions of the #if lines open: [name, in the #else]
    for line in lines:
        words = line.split(';', 1)[0].split()
        if words[:1] == ['#if']:
            stack.append([' '.join(words[1:]), False])
            continue
        if words[:1] == ['#else']:
            stack[-1][1] = True
            continue
        if words[:1] == ['#end']:
            stack.pop()
            continue
        m = CONST.match(line)
        if not m or not stack or stack[0][0] != 'SMALL':
            continue
        name, value = m.group(1), int(m.group(2))
        sizes = found.setdefault(name, {})
        if stack[0][1]:
            sizes['full'] = value
        elif len(stack) == 2 and stack[1][0] == 'RAM32':
            sizes['small' if stack[1][1] else 'ram32'] = value
        else:
            sizes['small'] = value
    for sizes in found.values():
        sizes.setdefault('ram32', sizes['small'])
    return found


def twin_small(module):
    """{name: (small, full)} of the constants lathe/src/MODULE.lth declares under `#if SMALL`."""
    return {name: (sizes['small'], sizes['full']) for name, sizes in twin_capacities(module).items()}


class MemoryTest(unittest.TestCase):
    def test_the_small_build_has_the_same_capacities_in_the_twins_and_the_host_test(self):
        """lathe/host/README.md, "The small build": each twin's `#if SMALL` constants are those
        script_host.SMALL gives the host modules, and the others are the host's own."""
        import importlib
        import script_host
        wanted = {(m, name): size for m, name, size in script_host.SMALL}
        found = {}
        for module in TWINS:
            for name, (small, full) in twin_small(module).items():
                found[(module, name)] = small
                self.assertEqual(full, getattr(importlib.import_module(module), name), name)
        self.assertEqual(found, wanted)

    def test_the_32k_build_has_the_same_capacities_in_the_twins_and_the_host_test(self):
        """lathe/docs/bbc.md, "The 32K Model B": RAM32 1 makes SMALL 1 too, and each twin's
        `#if RAM32` inside `#if SMALL` gives what script_host.RAM32 gives the host modules."""
        import script_host
        wanted = {(m, name): size for m, name, size in script_host.ram32_capacities()}
        found = {}
        for module in TWINS:
            for name, sizes in twin_capacities(module).items():
                found[(module, name)] = sizes['ram32']
        self.assertEqual(found, wanted)
        small = {(m, name): size for m, name, size in script_host.SMALL}
        differ = {key for key, size in found.items() if size != small[key]}
        self.assertEqual(differ, {(m, name) for m, name, size in script_host.RAM32})

    def test_each_twin_lays_out_its_arrays_as_the_host_counts_them(self):
        for module in TWINS:
            host = {name: width for name, n, width in report.arrays(module)}
            twin = twin_arrays(module)
            for name, width in twin.items():
                with self.subTest(array=module + '.' + name):
                    if (module, name) in TWIN_ONLY:
                        continue
                    self.assertIn(name, host)
                    self.assertEqual(width, host[name])
            for name in host:
                with self.subTest(array=module + '.' + name):
                    self.assertIn(name, twin)

    @unittest.expectedFailure
    def test_the_tables_fit_the_budget(self):
        """Not yet: lathe/docs/architecture.md, "What stays in memory", says what is left."""
        self.assertLessEqual(report.total(), report.BUDGET)

    def test_the_tables_take_no_more_than_they_did(self):
        self.assertLessEqual(report.total(), CEILING)

    def test_every_module_of_the_corpus_compiles_at_these_capacities(self):
        import tempfile
        import shutil
        work = tempfile.mkdtemp(prefix='lathe-memory-')
        try:
            peaks, where, failed = report.run_corpus(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)
            report.unwatch()
        self.assertEqual(failed, [])


if __name__ == '__main__':
    unittest.main()
