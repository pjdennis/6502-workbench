"""Stage 11, step 9, the compiler's side: `in REGION` and `with REGION do ... end`
(provisional, 2026-11-14; lathe/docs/language.md, "Banked data"; lathe/docs/code-model.md,
"Data in windows"). What the compiler writes for them: the RGN records, the kind 6 fix-up of
`LDA #bank`, the calls of rt_with.map and rt_with.unmap with the bank kept in a temporary,
the CALL flag of the calls made inside a block, the interface entries that hold an importer to
the same rule; and that a module with neither writes what it wrote before."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lathec_support as support  # noqa: E402

sys.path.insert(0, os.path.join(support.HOST, 'driver'))
import lo  # noqa: E402
import lo2asm  # noqa: E402


class BankedDataTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = self.tmp.name

    def compile(self, name, text, ok=True, options=()):
        directory = os.path.join(self.out, 'src')
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, name + '.lth')
        with open(path, 'w') as f:
            f.write(text)
        status, errors = support.run_lathec(*options, path, self.out)
        if ok:
            self.assertEqual((status, errors), (0, ''))
            return lo.load(os.path.join(self.out, name + '.lo'))
        self.assertEqual(status, 1)
        return errors[len(path) + 1:]

    def text(self, m, function):
        """The lines of lo2asm's text for one function, without its comment."""
        lines = lo2asm.render_module(m).splitlines()
        first = lines.index(lo2asm.mangle(function))
        body = []
        for line in lines[first + 1:]:
            if not line.startswith(' ') and not line.startswith('.'):
                break
            body.append(line.split(';')[0].strip())
        return body

    def calls(self, m, function):
        f = m.definition(m.sym_index(function))
        return [(m.sym_name(c.callee), c.flags) for c in f.calls]

    def test_a_variable_and_a_table_in_a_region_follow_a_rgn_record(self):
        m = self.compile('regions', 'module regions\n'
                         'var t: [4]byte in names\n'
                         'pub var u: word in names\n'
                         'var plain: byte\n'
                         'const TT: [2]^byte in msgs = ["a", "b"]\n'
                         'pub const S in msgs = "text"\n')
        regions = {m.sym_name(x.sym): (x.region, getattr(x, 'cls', None)) for x in m.items
                   if isinstance(x, (lo.Var, lo.Data))}
        self.assertEqual(regions['regions.t'], ('names', 2))
        self.assertEqual(regions['regions.u'], ('names', 2))     # never in zero page
        self.assertEqual(regions['regions.plain'], ('', 1))
        self.assertEqual(regions['regions.s'][0], 'msgs')
        # a table's strings are not in the region; the table of their addresses is
        self.assertEqual([(m.sym_name(x.sym), x.region) for x in m.items if isinstance(x, lo.Data)],
                         [('regions.$1', ''), ('regions.$2', ''), ('regions.tt', 'msgs'),
                          ('regions.s', 'msgs')])

    def test_a_with_block_maps_the_bank_keeps_the_old_one_and_puts_it_back(self):
        m = self.compile('w', 'module w\n'
                         'var t: [4]byte in r\n'
                         'var n: byte\n'
                         'func f()\n'
                         '  with r do\n'
                         '    t[1] = n\n'
                         '  end\n'
                         '  n = 0\n'
                         'end\n')
        self.assertEqual(self.text(m, 'w.f'), [
            'LDA #$00', 'JSR rt_with__map', 'STA w__f__St1',
            'LDA w__n', 'STA w__t+$01',
            'LDY w__f__St1', 'JSR rt_with__unmap',
            'LDA #$00', 'STA w__n', 'RTS'])
        f = m.definition(m.sym_index('w.f'))
        bank = [x for x in f.fixes if x.kind == lo.FX_BANK]
        self.assertEqual([(m.sym_name(x.sym), x.slot, x.addend) for x in bank], [('w.t', 0xFF, 0)])
        self.assertEqual(m.imports, ['rt_with'])
        self.assertEqual(self.calls(m, 'w.f'), [('rt_with.map', 0), ('rt_with.unmap', 0)])

    def test_the_bank_is_named_by_the_first_thing_of_the_region_used(self):
        m = self.compile('w', 'module w\n'
                         'var t: byte in r\n'
                         'const K: [2]byte in r = [1, 2]\n'
                         'func f(): byte\n'
                         '  with r do\n'
                         '    return K[1] + t\n'
                         '  end\n'
                         'end\n')
        f = m.definition(m.sym_index('w.f'))
        self.assertEqual([m.sym_name(x.sym) for x in f.fixes if x.kind == lo.FX_BANK], ['w.k'])

    def test_a_block_that_uses_nothing_of_its_region_names_the_first_the_module_declares(self):
        """A fixed function given a pointer into the region reads it with `p[0]`: the bank is
        named by the module's first variable or table of the region (error 183 is retired)."""
        m = self.compile('w', 'module w\n'
                         'var plain: byte\n'
                         'var other: byte in q\n'
                         'var t: [4]byte in r\n'
                         'const K: [2]byte in r = [1, 2]\n'
                         'func get(p: ^byte): byte\n'
                         '  with r do\n'
                         '    return p[0]\n'
                         '  end\n'
                         'end\n'
                         'func put(p: ^byte, v: byte)\n'
                         '  with r do\n'
                         '    with r do\n'
                         '      p[0] = v\n'
                         '    end\n'
                         '  end\n'
                         'end\n')
        for function in ('w.get', 'w.put'):
            f = m.definition(m.sym_index(function))
            self.assertEqual([m.sym_name(x.sym) for x in f.fixes if x.kind == lo.FX_BANK], ['w.t'])
        self.assertEqual(self.text(m, 'w.get')[2:5], ['LDA #$00', 'JSR rt_with__map', 'STA w__get__St1'])

    def test_a_block_of_a_region_the_module_declares_nothing_in_must_use_something_of_it(self):
        """The object file names a bank by a variable or table of its region: an importer that
        uses nothing of an imported region in a block has none to name (error 184)."""
        self.compile('lib', 'module lib\n'
                     'pub var t: [4]byte in r\n')
        errors = self.compile('user', 'module user\n'
                              'import lib\n'
                              'func f(p: ^byte): byte\n'
                              '  with r do\n'
                              '    return p[0]\n'
                              '  end\n'
                              'end\n', ok=False)
        self.assertIn('4:3: error 184', errors)
        m = self.compile('user', 'module user\n'
                         'import lib\n'
                         'func f(p: ^byte): byte\n'
                         '  with r do\n'
                         '    return p[lib.t[0]]\n'
                         '  end\n'
                         'end\n')
        f = m.definition(m.sym_index('user.f'))
        self.assertEqual([m.sym_name(x.sym) for x in f.fixes if x.kind == lo.FX_BANK], ['lib.t'])

    def test_calls_inside_a_block_are_flagged(self):
        m = self.compile('w', 'module w\n'
                         'var t: byte in r\n'
                         'func g(): byte\n'
                         '  return 1\n'
                         'end\n'
                         'func h()\n'
                         'end\n'
                         'func f()\n'
                         '  h()\n'
                         '  with r do\n'
                         '    t = g()\n'
                         '  end\n'
                         '  h()\n'
                         'end\n')
        self.assertEqual(self.calls(m, 'w.f'), [('w.h', 0), ('rt_with.map', 0), ('w.g', lo.C_WITH),
                                                ('rt_with.unmap', 0)])

    def test_a_return_inside_a_block_puts_the_bank_back_keeping_a_x_and_the_carry(self):
        m = self.compile('w', 'module w\n'
                         'var t: [4]word in r\n'
                         'func f(i: byte): word\n'
                         '  with r do\n'
                         '    return t[i]\n'
                         '  end\n'
                         'end\n'
                         'func s(i: byte): byte, bool\n'
                         '  with r do\n'
                         '    if lo(t[i]) == 0 then\n'
                         '      return 0, false\n'
                         '    end\n'
                         '  end\n'
                         '  return 1, true\n'
                         'end\n')
        code = self.text(m, 'w.f')
        self.assertEqual(code[-2:], ['LDY w__f__St1', 'JMP rt_with__unmap'])
        self.assertTrue(any(line.startswith('LDA w__t') for line in code))
        s = self.text(m, 'w.s')
        i = s.index('CLC')
        self.assertEqual(s[i:i + 4], ['CLC', 'LDA #$00', 'LDY w__s__St1', 'JMP rt_with__unmap'])

    def test_break_and_continue_out_of_a_block_put_the_bank_back(self):
        m = self.compile('w', 'module w\n'
                         'var t: [8]byte in r\n'
                         'func f()\n'
                         '  var i: byte\n'
                         '  for i = 0 to 7 do\n'
                         '    with r do\n'
                         '      if t[i] == 0 then\n'
                         '        continue\n'
                         '      end\n'
                         '      if t[i] == 1 then\n'
                         '        break\n'
                         '      end\n'
                         '      t[i] = 2\n'
                         '    end\n'
                         '  end\n'
                         'end\n')
        code = self.text(m, 'w.f')
        self.assertEqual(code.count('JSR rt_with__map'), 1)
        self.assertEqual(code.count('LDY w__f__St1'), 3)     # continue, break and the end

    def test_a_break_inside_a_block_that_is_outside_the_loop_maps_nothing(self):
        m = self.compile('w', 'module w\n'
                         'var t: [8]byte in r\n'
                         'func f()\n'
                         '  var i: byte\n'
                         '  with r do\n'
                         '    for i = 0 to 7 do\n'
                         '      if t[i] == 0 then\n'
                         '        break\n'
                         '      end\n'
                         '    end\n'
                         '  end\n'
                         'end\n')
        self.assertEqual(self.text(m, 'w.f').count('LDY w__f__St1'), 1)

    def test_blocks_nest(self):
        m = self.compile('w', 'module w\n'
                         'var t: byte in r\n'
                         'var u: byte in s\n'
                         'var x: byte\n'
                         'func f(): byte\n'
                         '  with r do\n'
                         '    with r do\n'
                         '      t = 1\n'
                         '    end\n'
                         '    with s do\n'
                         '      x = u\n'
                         '      if x == 0 then\n'
                         '        return 1\n'
                         '      end\n'
                         '    end\n'
                         '    t = x\n'
                         '  end\n'
                         '  return 0\n'
                         'end\n')
        code = self.text(m, 'w.f')
        self.assertEqual(code.count('JSR rt_with__map'), 2)    # the inner block of r costs nothing
        f = m.definition(m.sym_index('w.f'))
        self.assertEqual([m.sym_name(x.sym) for x in f.fixes if x.kind == lo.FX_BANK], ['w.t', 'w.u'])
        # The return inside both blocks puts back what the outer one found: its temporary.
        i = code.index('LDY w__f__St1')
        self.assertEqual(code[i - 1:i + 2], ['LDA #$01', 'LDY w__f__St1', 'JMP rt_with__unmap'])
        self.assertIn('LDY w__f__St2', code)

    def test_an_inline_function_used_inside_a_block_can_use_the_region(self):
        m = self.compile('w', 'module w\n'
                         'var t: [4]byte in r\n'
                         'inline func get(i: byte): byte\n'
                         '  return t[i]\n'
                         'end\n'
                         'func f(): byte\n'
                         '  with r do\n'
                         '    return get(2)\n'
                         '  end\n'
                         'end\n')
        self.assertIn('LDA w__t+$02', self.text(m, 'w.f'))
        self.assertIn('118', self.compile('v', 'module v\n'
                                          'var t: [4]byte in r\n'
                                          'inline func get(i: byte): byte\n'
                                          '  return t[i]\n'
                                          'end\n'
                                          'func f(): byte\n'
                                          '  return get(2)\n'
                                          'end\n', ok=False))

    def test_a_static_variable_can_be_in_a_region(self):
        m = self.compile('w', 'module w\n'
                         'func f()\n'
                         '  static var seen: byte in r\n'
                         '  with r do\n'
                         '    seen += 1\n'
                         '  end\n'
                         'end\n')
        self.assertEqual([(m.sym_name(x.sym), x.region) for x in m.items if isinstance(x, lo.Var)],
                         [('w.f.seen', 'r')])

    def test_an_importer_is_held_to_the_same_rule(self):
        self.compile('lib', 'module lib\n'
                     'pub var t: [4]byte in r\n'
                     'pub const K: [3]byte in r = "abc"\n'
                     'pub var plain: byte\n')
        m = self.compile('user', 'module user\n'
                         'import lib\n'
                         'func f(): byte\n'
                         '  with r do\n'
                         '    lib.t[0] = lib.K[1]\n'
                         '    return lib.t[1]\n'
                         '  end\n'
                         'end\n')
        f = m.definition(m.sym_index('user.f'))
        self.assertEqual([m.sym_name(x.sym) for x in f.fixes if x.kind == lo.FX_BANK], ['lib.t'])
        for use in ('lib.t[0] = 1', 'lib.plain = lib.K[0]', 'lib.plain = byte(@lib.t)'):
            errors = self.compile('user', 'module user\nimport lib\nfunc f()\n  %s\nend\n' % use, ok=False)
            self.assertIn('error 118', errors)
        self.compile('user', 'module user\nimport lib\nfunc f()\n  lib.plain = 1\nend\n')

    def test_a_region_spelled_like_an_imported_variable_is_one_region(self):
        """Found by stage 11, step 10 (kernel.names in NAMES): the region's name is read from
        the interface before the variable's frozen entry of the same spelling is made, so once
        a function has thawed the variable the lexer gives the region's word as the thawed
        entry, another name entry than the one the variable holds. A region is its spelling."""
        self.compile('lib', 'module lib\n'
                     'pub var names: [4]byte in names\n')
        m = self.compile('user', 'module user\n'
                         'import lib\n'
                         'func f(): byte\n'
                         '  with names do\n'
                         '    return lib.names[0]\n'
                         '  end\n'
                         'end\n'
                         'func g()\n'
                         '  with names do\n'
                         '    lib.names[1] = 2\n'
                         '    with names do\n'
                         '      lib.names[2] = 3\n'
                         '    end\n'
                         '  end\n'
                         'end\n')
        g = m.definition(m.sym_index('user.g'))
        self.assertEqual([m.sym_name(x.sym) for x in g.fixes if x.kind == lo.FX_BANK], ['lib.names'])
        self.assertEqual([name for name, flags in self.calls(m, 'user.g')], ['rt_with.map', 'rt_with.unmap'])

    def kinds(self, m, function, name):
        f = m.definition(m.sym_index(function))
        return [x.kind for x in f.fixes if m.sym_name(x.sym) == name]

    def test_an_address_formed_only_to_reach_an_element_is_kind_7_and_8(self):
        """Indexing by a word, a row of a `rows` array, an element of a big array field: the
        address is formed in code only to reach a part of the variable in this function, which
        lets the linker put the variable in its module's bank (object-format.md, version 4)."""
        m = self.compile('w', 'module w\n'
                         'type Node = record\n'
                         '  x: word\n'
                         '  y: word\n'
                         'end\n'
                         'type Big = record\n'
                         '  n: byte\n'
                         '  a: [300]byte\n'
                         'end\n'
                         'var t: [2048]byte\n'
                         'var nodes: [300]Node rows\n'
                         'var b: Big\n'
                         'const K: [400]byte = [1]\n'
                         'func f(i: word): byte\n'
                         '  t[i] = K[i]\n'
                         '  nodes[i].y = 1\n'
                         '  return b.a[i]\n'
                         'end\n')
        for name in ('w.t', 'w.nodes', 'w.b', 'w.k'):
            self.assertEqual(sorted(set(self.kinds(m, 'w.f', name))), [lo.FX_REACH_LO, lo.FX_REACH_HI], name)

    def test_an_address_that_escapes_is_kind_2_and_3(self):
        m = self.compile('w', 'module w\n'
                         'var t: [2048]byte\n'
                         'var u: [2048]byte\n'
                         'var p: ^byte\n'
                         'func f(i: word)\n'
                         '  p = @t[i]\n'
                         'end\n'
                         'func g(i: word)\n'
                         '  p = @t[u[i]]\n'
                         'end\n'
                         'func h(): ^byte\n'
                         '  return @t\n'
                         'end\n')
        for function in ('w.f', 'w.g', 'w.h'):
            self.assertEqual(sorted(set(self.kinds(m, function, 'w.t'))), [lo.FX_LO, lo.FX_HI], function)
        # The index inside the designator after @ is reached, not taken.
        self.assertEqual(sorted(set(self.kinds(m, 'w.g', 'w.u'))), [lo.FX_REACH_LO, lo.FX_REACH_HI])

    # ---- A region in fixed memory, which the compiler is told of (-fREGION) -------------------

    FIXED = ('module w\n'
             'var t: [4]byte in r\n'
             'var n: byte\n'
             'func g(): byte\n'
             '  return 1\n'
             'end\n'
             'func f(i: byte): byte\n'
             '  with r do\n'
             '    t[i] = g()\n'
             '    if t[0] == 0 then\n'
             '      return t[1]\n'
             '    end\n'
             '  end\n'
             '  return n\n'
             'end\n')

    def test_a_block_of_a_region_in_fixed_memory_maps_nothing(self):
        """-fR: the region R is in fixed memory, so its blocks are their bodies alone: no call of
        rt_with.map or unmap, no temporary, no kind 6 fix-up, the calls inside not flagged, and
        no import of rt_with. The variables are still in the region (RGN), which the linker puts
        in fixed memory as the environment says."""
        m = self.compile('w', self.FIXED, options=('-fR',))
        self.assertEqual(self.calls(m, 'w.f'), [('w.g', 0)])
        f = m.definition(m.sym_index('w.f'))
        self.assertEqual([x for x in f.fixes if x.kind == lo.FX_BANK], [])
        self.assertFalse(any('St1' in line for line in self.text(m, 'w.f')))
        self.assertEqual(m.imports, [])
        regions = {m.sym_name(x.sym): x.region for x in m.items if isinstance(x, lo.Var)}
        self.assertEqual(regions['w.t'], 'r')
        banked = self.compile('w', self.FIXED)
        self.assertEqual(self.calls(banked, 'w.f'), [('rt_with.map', 0), ('w.g', lo.C_WITH),
                                                     ('rt_with.unmap', lo.C_WITH), ('rt_with.unmap', 0)])

    def test_another_region_is_still_mapped(self):
        """-f names only the regions given: a block of another maps its bank, and a block of a
        fixed region inside it runs with that bank mapped, so its calls are flagged; a block of
        a mapped region inside a fixed one maps it."""
        text = ('module w\n'
                'var t: byte in r\n'
                'var u: byte in s\n'
                'func g(): byte\n'
                '  return 1\n'
                'end\n'
                'func f()\n'
                '  with s do\n'
                '    u = g()\n'
                '    with r do\n'
                '      t = g()\n'
                '    end\n'
                '  end\n'
                '  with r do\n'
                '    t = g()\n'
                '    with s do\n'
                '      u = g()\n'
                '    end\n'
                '    t = g()\n'
                '  end\n'
                'end\n')
        m = self.compile('w', text, options=('-fr',))
        # (a module's calls are listed once for each callee and flags)
        self.assertEqual(self.calls(m, 'w.f'), [('rt_with.map', 0), ('w.g', lo.C_WITH), ('rt_with.unmap', 0),
                                                ('w.g', 0)])
        code = self.text(m, 'w.f')
        self.assertEqual((code.count('JSR rt_with__map'), code.count('JSR rt_with__unmap')), (2, 2))
        f = m.definition(m.sym_index('w.f'))
        self.assertEqual([m.sym_name(x.sym) for x in f.fixes if x.kind == lo.FX_BANK], ['w.u', 'w.u'])

    def test_a_region_in_fixed_memory_keeps_the_rules(self):
        """Its names are still used only inside its blocks (118), and a block must still name
        something of a region (184), so that the module compiles with the region in a bank too."""
        self.assertIn('error 118', self.compile('w', 'module w\nvar t: byte in r\nfunc f()\n  t = 1\nend\n',
                                                ok=False, options=('-fr',)))
        self.assertIn('error 184', self.compile('w', 'module w\nvar t: byte in r\nfunc f()\n  with q do\n'
                                                     '  end\nend\n', ok=False, options=('-fq',)))

    def test_the_option_takes_a_name(self):
        def usage(options):
            self.compile('w', 'module w\n')
            status, errors = support.run_lathec(*options, os.path.join(self.out, 'src', 'w.lth'), self.out)
            return status, errors.split(':')[:2]
        for bad in ('-f', '-f9', '-fa-b', '-fwith', '-fr=1'):
            with self.subTest(option=bad):
                self.assertEqual(usage((bad,)), (1, ['lathec', ' error 60']))
        many = tuple('-fr%d' % n for n in range(9))
        self.assertEqual(usage(many), (1, ['lathec', ' error 60']))
        self.compile('w', 'module w\n', options=many[:8] + ('-fr0',))   # a name given twice counts once

    def test_a_module_with_no_region_has_no_rt_with_import(self):
        m = self.compile('w', 'module w\nvar n: byte\nfunc f()\n  n = 1\nend\n')
        self.assertEqual(m.imports, [])


if __name__ == '__main__':
    unittest.main()
