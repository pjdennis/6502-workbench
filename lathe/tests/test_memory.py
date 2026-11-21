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
CEILING = 43411             # the total of lathe/docs/architecture.md, "What stays in memory"
TWIN_ONLY = {('kernel', 'text'): 'the text memory, which the host keeps in env.mem',
             ('kernel', 'tokens'): 'the token memory, which the host keeps in env.mem'}


def without_rooms(lines):
    """The lines of a twin as every build but Image A's reads them: what is under `#if ROOMS`
    left out, what is under its `#else` kept (lathe/docs/bbc.md, "Capacities set at start-up")."""
    out = []
    stack = []                      # for each #if open: 'rooms' in ROOMS's own lines, 'else' in
    for line in lines:              # its #else, 'other' for any other #if
        words = line.split(';', 1)[0].split()
        if words[:1] == ['#if']:
            stack.append('rooms' if words[1:] == ['ROOMS'] else 'other')
            if stack[-1] == 'rooms':
                continue
        elif words[:1] == ['#else'] and stack[-1] != 'other':
            stack[-1] = 'else'
            continue
        elif words[:1] == ['#end'] and stack[-1] != 'other':
            stack.pop()
            continue
        elif words[:1] == ['#end']:
            stack.pop()
        if 'rooms' not in stack:
            out.append(line)
    return out


def twin_arrays(module):
    """{name: bytes per element} of the module-level arrays of lathe/src/MODULE.lth."""
    with open(os.path.join(report.LATHE, 'src', TWIN_FILE.get(module, module) + '.lth')) as f:
        text = '\n'.join(without_rooms(f.read().splitlines()))
    return {name: 1 if t in ('byte', 'sbyte', 'bool') else 2 for name, t in VAR.findall(text)}


CONST = re.compile(r'^(?:pub )?const (\w+) = (\d+)', re.M)


def twin_capacities(module):
    """{name: {'small': N, 'full': N, 'ram32': N, 'image_b': N}} of the constants lathe/src/MODULE.lth
    declares under `#if SMALL`, `#else` and, inside `#if SMALL`, `#if RAM32` (the 32K Model B's: its
    `#else` is the small build's) and, inside that, `#if ADAPT` (Image B's: its `#else` is the 32K
    Model B's). A constant of no `#if RAM32` has the small build's size there, and one of no `#if
    ADAPT` the 32K Model B's in Image B."""
    with open(os.path.join(report.LATHE, 'src', TWIN_FILE.get(module, module) + '.lth')) as f:
        lines = without_rooms(f.read().splitlines())
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
        elif len(stack) >= 2 and stack[1][0] == 'RAM32' and stack[1][1]:
            sizes['small'] = value
        elif len(stack) == 2 and stack[1][0] == 'RAM32':
            sizes['ram32'] = value
        elif len(stack) == 3 and stack[1][0] == 'RAM32' and stack[2][0] == 'ADAPT':
            sizes['ram32' if stack[2][1] else 'image_b'] = value
        else:
            sizes['small'] = value
    for sizes in found.values():
        sizes.setdefault('ram32', sizes['small'])
        sizes.setdefault('image_b', sizes['ram32'])
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

    def test_image_b_has_the_same_capacities_in_the_twins_and_the_host_test(self):
        """lathe/docs/bbc.md, "The image for machines with no sideways RAM": RAM32 1 with ADAPT 1,
        and each twin's `#if ADAPT` inside `#if RAM32` gives what script_host.IMAGE_B gives the host
        modules (lathec_image_b.py); every other capacity is the 32K Model B's."""
        import script_host
        wanted = {(m, name): size for m, name, size in script_host.image_b_capacities()}
        found = {}
        for module in TWINS:
            for name, sizes in twin_capacities(module).items():
                found[(module, name)] = sizes['image_b']
        self.assertEqual(found, wanted)
        ram32 = {(m, name): size for m, name, size in script_host.ram32_capacities()}
        differ = {key for key, size in found.items() if size != ram32[key]}
        self.assertEqual(differ, {(m, name) for m, name, size in script_host.IMAGE_B})

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
