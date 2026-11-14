"""inline.py, and inline and interrupt functions in the compiler: saving a body's tokens and
replaying them (src/lex), what save() finds out about a body, the scope names in an expansion
are looked up in, the substitution of arguments for parameters, interfaces, and that an inline
accessor gives exactly the code its body would give written in place.

The cases in cases/snap/inline_*.lth, cases/snap/interrupts.lth, cases/e2e/inline_*.lth and
cases/err/ show the rest; test_gate_map below reads the map of an end-to-end board case."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lathec_support as support  # noqa: E402

sys.path.append(os.path.join(support.HOST, 'driver'))
import build  # noqa: E402
import lo  # noqa: E402

import decl  # noqa: E402
import env  # noqa: E402
import err  # noqa: E402
import expr  # noqa: E402
import gen  # noqa: E402
import inline  # noqa: E402
import kernel  # noqa: E402
import lex  # noqa: E402
import out  # noqa: E402
import src  # noqa: E402
import typetab  # noqa: E402


def name(text):
    kernel.name_begin()
    for ch in text.encode():
        kernel.name_add(ch)
    return kernel.name_end()


class InProcess(unittest.TestCase):
    """Compile a module held in memory, in this process, and look at what is left."""

    def compile(self, text):
        support.fresh()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        err.init()
        kernel.init()
        inline.init()
        typetab.init()
        src.init()
        lex.init()
        out.init()
        gen.init()
        expr.init()
        decl.init()
        objects, _ = support.put_text((self.tmp.name + '/m.lo').encode(), 0x9000)
        self.assertTrue(out.open(objects))
        kernel.module_add(name('m'))
        begin, end = support.put_text(text.encode(), support.TEXT)
        self.text = begin
        src.open_memory(begin, end)
        decl.unit()
        out.end_module()

    def function(self, text):
        s, found = kernel.sym_find(kernel.SCOPE_MODULE, name(text))
        self.assertTrue(found)
        return s

    def flags(self, f):
        return env.mem[kernel.sym_value[f] + inline.R_FLAGS]

    def assigned(self, f):
        return [env.mem[inline.param(f, i) + 2] for i in range(kernel.sym_params[f])]

    def tokens_of(self, start, limit, line):
        """The tokens LEX gives from a source in memory, or a saved run, with their places."""
        found = []
        lex.tok = lex.T_NL
        lex.open_brackets = 0
        if line == 0:
            src.open_memory(start, limit)
        else:
            src.open_saved(start, limit, 0, line)
        lex.next()
        while lex.tok != lex.T_EOF:
            value = lex.value if lex.tok in (lex.T_NAME, lex.T_NUMBER) else 0
            if lex.tok == lex.T_STRING:
                value = bytes(lex.string[:lex.string_length])
            found.append((lex.tok, value, lex.line, lex.col))
            lex.next()
        src.close()
        return found


BODY = '''\
  var i: byte = 0            ; a comment
  while i < n do
    if s[i] == 'x' then
      return i, true
    end
    i += 1


  end
  return f(n +
           1, "a\\"b"), false
'''


class SaveTest(InProcess):
    def test_a_replayed_body_gives_the_tokens_it_was_read_as(self):
        source = 'module m\nfunc f(a: byte, b: ^byte): byte\nend\ninline func g(n: byte, s: ^byte): byte, bool\n' \
            + BODY + 'end\n'
        self.compile(source)
        g = self.function('g')
        r = kernel.sym_value[g]
        start = r + inline.R_PARAMS + 2 * inline.PARAM_SIZE
        replayed = self.tokens_of(start, inline.word_at(r + inline.R_END), inline.word_at(r + inline.R_LINE))
        begin, end = support.put_text(BODY.encode(), 0xA000)
        direct = self.tokens_of(begin, end, 0)
        self.assertEqual([t[:2] for t in replayed], [t[:2] for t in direct])
        self.assertEqual([(t[2] - 4, t[3]) for t in replayed], [t[2:] for t in direct])
        self.assertEqual(inline.word_at(r + inline.R_FILE), 0)      # read from memory: no file
        self.assertEqual([inline.word_at(inline.param(g, i)) for i in range(2)], [name('n'), name('s')])

    def test_flags_and_assigned_parameters(self):
        cases = [
            ('func get(i: byte): byte\n  return t[i]\n', inline.PURE | inline.LAST_RETURN, [0]),
            ('func put(i: byte, v: byte)\n  t[i] = v\n', inline.PURE, [0, 0]),
            ('func local(i: byte): byte\n  var k: byte = i\n  k += 1\n  for k = 0 to i do\n  end\n'
             '  return k\n', inline.PURE | inline.LAST_RETURN, [0]),
            ('func own(i: byte): byte\n  i += 1\n  return i\n', inline.PURE | inline.LAST_RETURN, [1]),
            ('func counts(i: byte)\n  for i = 0 to 3 do\n  end\n', inline.PURE, [1]),
            ('func arrow(i: byte, j: byte)\n  if h() -> i then\n  end\n', 0, [1, 0]),
            ('func pair(i: byte, j: bool)\n  i, j = h()\n', 0, [1, 1]),
            ('func address(i: byte)\n  var p: ^byte = @i\n', 0, [1]),
            ('func calls(i: byte)\n  g(i)\n', 0, [0]),
            ('func field(p: ^R)\n  p.v = 1\n', 0, [0]),
            ('func two(i: byte): byte\n  if i > 2 then\n    return 1\n  end\n  return 0\n', inline.PURE, [0]),
            ('func inner(i: byte): byte\n  if i > 2 then\n    return 1\n  end\n', inline.PURE, [0]),
            ('func global(i: byte)\n  n = i\n', inline.PURE, [0]),
            ('func globals(i: byte)\n  n = i\n  t[1] = i\n', 0, [0]),
            ('func pointer(p: ^byte)\n  p[1] = 0\n', 0, [0]),
            ('func downs(i: byte)\n  loop\n    i -= 1\n  until i == 0\n', inline.PURE, [1]),
        ]
        head = ('module m\ntype R = record\n  v: byte\nend\nvar t: [4]byte\nvar n: byte\n'
                'func g(a: byte)\nend\nfunc h(): byte, bool\n  return 0, true\nend\n')
        for text, flags, assigned in cases:
            with self.subTest(text.split('(')[0]):
                self.compile(head + 'inline ' + text + 'end\n')
                f = self.function(text.split()[1].split('(')[0])
                self.assertEqual(self.flags(f), flags)
                self.assertEqual(self.assigned(f), assigned)

    def test_names_made_by_the_declaration_stay(self):
        """The saved tokens hold places in the name heap: a name only the body uses is kept."""
        self.compile('module m\ninline func f(only_here: byte): byte\n  var also: byte = only_here\n'
                     '  return also\nend\n')
        top = kernel.name_top
        self.assertLess(name('only_here'), top)
        self.assertLess(name('also'), top)
        self.assertEqual(kernel.name_top, top)

    def test_the_buffer_has_a_named_capacity(self):
        line = '  x = x + 1\n'
        count = inline.SAVED_SIZE // 12 + 1
        with self.assertRaises(SystemExit):
            self.compile('module m\nvar x: byte\ninline func f()\n' + line * count + 'end\n')
        self.assertIn('error %d:' % err.E_INLINE_FULL, support.error_text())


class LookupTest(InProcess):
    def test_names_in_a_body_are_the_declaring_scope_s(self):
        """The caller's local hides nothing in the body; the body's parameter hides the module's."""
        self.compile('module m\nvar n: byte\nvar k: byte\ninline func f(k: byte): byte\n  return n + k\nend\n'
                     'func main()\n  var n: byte\nend\n')
        f = self.function('f')
        module_n, _ = kernel.sym_find(kernel.SCOPE_MODULE, name('n'))
        local_n = kernel.sym_add(kernel.SCOPE_LOCAL, name('n'), kernel.K_LOCAL)
        self.assertEqual(inline.lookup(name('n')), (local_n, True))
        inline.enter(f, True)
        param = kernel.sym_add(inline.SCOPE_INLINE + 1, name('k'), kernel.K_LOCAL)
        self.assertEqual(inline.lookup(name('k'))[0], kernel.sym_find(kernel.SCOPE_MODULE, name('k'))[0])
        inline.level = 1                    # what body_begin() does, without its source
        self.assertEqual(inline.lookup(name('n')), (module_n, True))
        self.assertEqual(inline.lookup(name('k')), (param, True))
        self.assertEqual(inline.lookup(name('true'))[1], True)
        inline.leave()
        self.assertEqual(inline.level, 0)
        self.assertEqual(kernel.sym_count, param)
        self.assertEqual(inline.lookup(name('n')), (local_n, True))


class ProgramTest(unittest.TestCase):
    """The compiler as a program, on files."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def compile(self, text, module='m'):
        path = os.path.join(self.tmp.name, module + '.lth')
        with open(path, 'w') as f:
            f.write(text)
        status, errors = support.run_lathec(path, self.tmp.name)
        self.assertEqual((status, errors), (0, ''))
        return lo.load(os.path.join(self.tmp.name, module + '.lo'))

    def code(self, m, function):
        """The code and fix-ups of a function, with references to its own symbol made the same."""
        own = m.sym_index('m.' + function)
        f = [x for x in m.functions() if x.sym == own][0]
        fixes = [(x.offset, x.kind, -1 if x.sym == own else x.sym, x.slot, x.addend) for x in f.fixes]
        return f.code, fixes, [(s.size, s.kind) for s in f.slots]

    def test_an_accessor_gives_the_code_of_its_body_written_in_place(self):
        m = self.compile('''module m
type P = record
  x: byte
  y: word
end
var table: [16]byte
var words: [16]word
var points: [8]P
var ptr: ^P
var g: byte
var w: word

inline func item(i: byte): byte
  return table[i]
end
inline func word_at(i: byte): word
  return words[i]
end
inline func px(q: ^P): byte
  return q.x
end
inline func set(i: byte, v: byte)
  table[i] = v
end
inline func sum(a: word, b: word): word
  return a + b
end
inline func less(a: byte, b: byte): bool
  return a < b
end

func inlined(k: byte)
  var v: byte
  v = item(k)
  v = item(3) + g
  w = word_at(k)
  w = sum(w, 1000)
  g = px(ptr)
  set(k, g)
  set(2, 7)
  if less(g, k) then
    g = 0
  end
  while less(k, 9) do
    k += 1
  end
end

func in_place(k: byte)
  var v: byte
  v = table[k]
  v = table[3] + g
  w = words[k]
  w = w + 1000
  g = ptr.x
  table[k] = g
  table[2] = 7
  if g < k then
    g = 0
  end
  while k < 9 do
    k += 1
  end
end
''')
        self.assertEqual(self.code(m, 'inlined'), self.code(m, 'in_place'))

    def test_interrupt_function_entry_exit_and_flag(self):
        source = 'module m\nvar n: byte\ninterrupt func h()\n  if n == 0 then\n    return\n  end\n  n -= 1\nend\n'
        for option, entry, leave in (('-c6502', b'\x48\x8A\x48\x98\x48\xD8', b'\x68\xA8\x68\xAA\x68\x40'),
                                     ('-c65c02', b'\x48\xDA\x5A', b'\x7A\xFA\x68\x40')):
            with self.subTest(option):
                path = os.path.join(self.tmp.name, 'm.lth')
                with open(path, 'w') as f:
                    f.write(source)
                self.assertEqual(support.run_lathec(option, path, self.tmp.name), (0, ''))
                m = lo.load(os.path.join(self.tmp.name, 'm.lo'))
                h = m.functions()[0]
                self.assertEqual(h.flags & 2, 2)                # FUNC flag bit 1: interrupt
                self.assertTrue(h.code.startswith(entry))
                self.assertTrue(h.code.endswith(leave))
                self.assertEqual(h.code.count(b'\x40'), 1)    # one RTI: the `return` goes there

    def test_an_exported_inline_function_is_expanded_by_an_importer(self):
        self.compile('module lib\nvar private: byte\npub var count: byte\n'
                     'pub inline func add(n: byte): byte\n  count += n\n  return count\nend\n', 'lib')
        m = self.compile('module m\nimport lib\nvar count: byte\nfunc f(k: byte): byte\n'
                         '  var count: byte = lib.add(k)\n  return count\nend\n')
        f = m.functions()[0]
        self.assertEqual({m.sym_name(x.sym) for x in f.fixes if x.sym != m.sym_index('m.f')}, {'lib.count'})
        self.assertEqual(f.calls, [])

    def test_errors_in_an_imported_expansion_name_the_inline_function_s_file(self):
        """The body's call of g is inside g's own arguments (error 100) only where it is expanded."""
        self.compile('module lib\npub func g(a: word, b: word, c: byte)\nend\npub inline func h(x: byte): byte\n'
                     '  g(x, 1, 2)\n  return x\nend\n', 'lib')
        path = os.path.join(self.tmp.name, 'm.lth')
        with open(path, 'w') as f:
            f.write('module m\nimport lib\nfunc f()\n  lib.g(1, 2, lib.h(3))\nend\n')
        status, errors = support.run_lathec(path, self.tmp.name)
        self.assertEqual(status, 1)
        self.assertTrue(errors.startswith('%s:5:3: error 100: ' % os.path.join(self.tmp.name, 'lib.lth')),
                        errors)

    def test_an_importer_need_not_import_what_an_inline_body_names(self):
        """lib's interface carries the modules it imports, for the expansions of its inline
        functions; the importer's own code still cannot name them."""
        self.assertEqual(support.run_lathec(os.path.join(support.LATHE, 'rt', 'host.lth'), self.tmp.name), (0, ''))
        self.compile('module lib\nimport host\npub inline func say(c: byte)\n  host.put_byte(c)\nend\n', 'lib')
        m = self.compile('module m\nimport lib\nfunc f()\n  lib.say(1)\nend\n')
        self.assertEqual([m.sym_name(x.sym) for x in m.functions()[0].fixes], [])
        path = os.path.join(self.tmp.name, 'm.lth')
        with open(path, 'w') as f:
            f.write('module m\nimport lib\nfunc f()\n  host.put_byte(1)\nend\n')
        self.assertEqual(support.run_lathec(path, self.tmp.name)[0], 1)


class SameWithoutInlineTest(unittest.TestCase):
    def test_the_mix_cases_differ_only_in_inline(self):
        """cases/e2e/inline_mix.lth and inline_mix_plain.lth: the same program with and without
        `inline` on its helpers, and the same expected output (each built and run by test_cases)."""
        def read(name):
            with open(os.path.join(support.CASES, 'e2e', name)) as f:
                return f.read()
        with_inline = read('inline_mix.lth').split('module inline_mix\n')[1]
        plain = read('inline_mix_plain.lth').split('module inline_mix_plain\n')[1]
        self.assertGreater(with_inline.count('inline func'), 4)
        self.assertEqual(with_inline.replace('inline func', 'func'), plain)
        self.assertEqual(read('inline_mix.expected.out'), read('inline_mix_plain.expected.out'))


@unittest.skipUnless(os.path.isfile(build.LINKER), 'no linker')
class GateMapTest(unittest.TestCase):
    def test_gate_map(self):
        """cases/e2e-michael/irq_shared.lth: the handler and main both call `saturate`, so the
        linker gives the handler a copy of its own, `saturate@N` for the handler's context N,
        with slots of its own."""
        work = tempfile.mkdtemp(prefix='lathe-gate-')
        self.addCleanup(__import__('shutil').rmtree, work, True)
        source = os.path.join(support.CASES, 'e2e-michael', 'irq_shared.lth')
        build.build(source, os.path.join(work, 'gate.bin'), 'michael', keep=work)
        with open(os.path.join(work, 'irq_shared.map')) as f:
            lines = [line.split() for line in f]
        copies = [line for line in lines if line[0] == 'F' and line[3].startswith('irq_shared.saturate')]
        self.assertEqual(len(copies), 2, copies)
        first, second = sorted(copies, key=lambda line: len(line[3]))
        self.assertEqual(first[3], 'irq_shared.saturate')                  # main's, context 0
        self.assertRegex(second[3], r'^irq_shared\.saturate@[1-9]$')      # the handler's
        self.assertNotEqual(first[1], second[1])
        slots = {}
        for line in lines:
            if line[0] == 'S' and line[3] in (first[3], second[3]):
                slots.setdefault(line[3], set()).add(line[1])
        self.assertEqual(len(slots[first[3]]), 3)                           # a, b and s
        self.assertEqual(len(slots[second[3]]), 3)
        self.assertFalse(slots[first[3]] & slots[second[3]])

if __name__ == '__main__':
    unittest.main()
