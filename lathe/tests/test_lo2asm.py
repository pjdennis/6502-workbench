"""lathe/host/driver/lo2asm.py and naive.py: object files as asm17 text, assembled with asm/pyasm.py.

The images are checked three ways: by hand-written bytes, against `reference_image` below (the
rules of object-format.md applied directly, without an assembler), and by running on the emulator.
"""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'lathe', 'host', 'driver'))

import build  # noqa: E402
import cpu6502  # noqa: E402
import lo  # noqa: E402
import lo2asm  # noqa: E402
import mapenv  # noqa: E402
import naive  # noqa: E402

HOST_ENV = os.path.join(ROOT, 'lathe', 'env', 'host.env')
CODE = 0x0200


def host_module():
    return lo.Builder('host').module()


def hello_module():
    b = lo.Builder('hello')
    b.imp('host')
    f = b.func('hello.main')
    for ch in (0x48, 0x49, 0x0A):
        f.op('LDA', '#', ch)
        f.op('JSR', 'abs', 0xF009)
    f.op('RTS')
    return b.module()


def three_class_module():
    """Case (b) of the brief: every kind of operand the renderer must get right."""
    b = lo.Builder('t')
    b.data('t.tab', b'\x01\x02\x03\x04')
    callee = b.func('t.callee')
    callee.slot('arg', 1, cls=1, weight=2, kind=lo.SK_PARAM)
    callee.op('LDA', 'abs', ('t.callee', 'arg'))
    callee.op('RTS')
    w = b.func('t.work')
    w.slot('z', 2, cls=0, weight=9, kind=lo.SK_PARAM)
    w.slot('e', 1, cls=1, weight=4, kind=lo.SK_LOCAL)
    w.slot('n', 2, cls=2, weight=1, kind=lo.SK_TEMP)
    w.call('t.callee')
    w.label('top')
    w.op('LDA', 'abs', ('t.work', 'z'))
    w.op('STA', 'abs', ('t.work', 'e'))
    w.op('LDX', 'abs,y', ('t.work', 'e'))
    w.op('LDA', 'abs,y', ('t.work', 'e'))
    w.op('BEQ', 'rel', 'fwd')
    w.op('STA', 'abs', ('t.callee', 'arg'))
    w.op('JSR', 'abs', 't.callee')
    w.op('LDA', '#<', 't.tab')
    w.op('STA', 'zp', ('t.work', 'z'))
    w.op('LDA', '#>', 't.tab')
    w.op('LDY', '#', 0)
    w.op('LDA', '(zp),y', ('t.work', 'z'))
    w.op('JMP', 'abs', 'top')
    w.label('fwd')
    w.op('DEC', 'abs', ('t.work', 'n'))
    w.op('BNE', 'rel', 'top')
    w.op('RTS')
    m = b.func('t.main')
    m.call('t.work')
    m.op('JSR', 'abs', 't.work')
    m.op('RTS')
    return b.module()


def map_lines(text):
    return mapenv.parse_map(text)


# Two maps for three_class_module: A puts the class 1 slots in zero page, B in main memory.
MAP_A = """
F 0200 000C host_start.start
F 020C 0003 t.callee
F 020F 0023 t.work
F 0232 0004 t.main
D 0236 0004 t.tab
S 0012 0001 t.callee 0 arg
S 0010 0002 t.work 0 z
S 0013 0001 t.work 1 e
S C010 0002 t.work 2 n
"""
MAP_B = """
F 0200 000C host_start.start
F 020C 0004 t.callee
F 0210 0026 t.work
F 0236 0004 t.main
D 023A 0004 t.tab
S C000 0001 t.callee 0 arg
S 0010 0002 t.work 0 z
S C001 0001 t.work 1 e
S C010 0002 t.work 2 n
"""


def reference_image(modules, entries, env, main_module):
    """The image by the rules of object-format.md, with no assembler: shrink, then patch."""
    addr = lo2asm.Addresses(entries, lo2asm.Program(modules))
    image = bytearray(0x10000 - env.code[0])

    def put(a, data):
        image[a - env.code[0]:a - env.code[0] + len(data)] = data

    defs = lo2asm.Program(modules).defs
    for e in entries:
        if e.kind == mapenv.M_FUNC and e.name not in defs:
            main = addr.items[f'{main_module}.main']
            put(e.addr, bytes((0xA2, 0xFF, 0x9A, 0xD8, 0x20, main & 0xFF, main >> 8,
                               0xA9, 0x00, 0x4C, 0x0F, 0xF0)))
        elif e.kind == mapenv.M_FUNC:
            m, f = defs[e.name]
            ins, _ = lo2asm.decode_function(m, f)
            new_at, pos = {}, 0
            for x in ins:
                new_at[x.offset] = pos
                pos += x.length - (1 if lo2asm.shrinks(m, x, addr) else 0)
            new_at[len(f.code)] = pos
            out = bytearray()
            for x in ins:
                op = f.code[x.offset]
                operand = f.code[x.offset + 1:x.offset + x.length]
                if x.mode == cpu6502.REL:
                    disp = new_at[x.target] - (new_at[x.offset] + 2)
                    operand = bytes((disp & 0xFF,))
                elif x.fix is not None:
                    fx = x.fix
                    target = addr(m, fx)
                    addend = fx.addend
                    if fx.sym == f.sym and fx.slot == lo.NO_SLOT:
                        addend = new_at[addend]
                    v = (target + addend) & 0xFFFF
                    if lo2asm.shrinks(m, x, addr):
                        op = cpu6502.table(m.cpu)[x.mnemonic][cpu6502.shrinks(m.cpu, x.mnemonic, x.mode)]
                        operand = bytes((v,))
                    elif fx.kind == lo.FX_WORD:
                        operand = v.to_bytes(2, 'little')
                    elif fx.kind == lo.FX_HI:
                        operand = bytes((v >> 8,))
                    else:
                        operand = bytes((v & 0xFF,))
                out += bytes((op,)) + operand
            assert len(out) == e.size, (e.name, len(out), e.size)
            put(e.addr, out)
        elif e.kind in (mapenv.M_DATA, mapenv.M_VAR):
            m, x = defs[e.name]
            data = bytearray(x.data if e.kind == mapenv.M_DATA else (x.init or b''))
            if e.kind == mapenv.M_VAR and x.init is None:
                continue
            for fx in x.fixes:
                v = (addr(m, fx) + fx.addend) & 0xFFFF
                if fx.kind == lo.FX_WORD:
                    data[fx.offset:fx.offset + 2] = v.to_bytes(2, 'little')
                else:
                    data[fx.offset] = (v >> 8) if fx.kind == lo.FX_HI else v & 0xFF
            put(e.addr, data)
    start = addr.items[env.start]
    put(0xFFFC, start.to_bytes(2, 'little') + b'\x00\x00')
    return bytes(image)


class Work(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lathe-lo2asm-')
        self.env = mapenv.read_env(HOST_ENV)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def assemble(self, modules, entries, main_module=None, name='prog'):
        text = lo2asm.render_program(modules, entries, self.env, main_module)
        src = os.path.join(self.dir, name + '.asm')
        out = os.path.join(self.dir, name + '.bin')
        with open(src, 'w') as fh:
            fh.write(text)
        build.assemble(src, out)
        with open(out, 'rb') as fh:
            return text, fh.read()

    def at(self, image, a, n):
        return image[a - CODE:a - CODE + n]


class TestModuleMode(unittest.TestCase):
    def test_hello(self):
        self.assertEqual(lo2asm.render_module(hello_module()), '\n'.join([
            '; module hello, cpu 6502',
            '; imports: host',
            '',
            'abs_f009 = $F009',
            '',
            '; function hello.main',
            ';   no slots',
            'hello__main',
            '    LDA #$48',
            '    JSR abs_f009',
            '    LDA #$49',
            '    JSR abs_f009',
            '    LDA #$0A',
            '    JSR abs_f009',
            '    RTS',
            '']))

    def test_three_classes(self):
        text = lo2asm.render_module(three_class_module())
        work = text[text.index('; function t.work'):text.index('; function t.main')]
        self.assertEqual(work, '\n'.join([
            '; function t.work',
            ';   slot 0 z: size 2, class 0 (zp), param, weight 9',
            ';   slot 1 e: size 1, class 1 (either), local, weight 4',
            ';   slot 2 n: size 2, class 2 (not zp), temp, weight 1',
            ';   calls t.callee',
            't__work',
            '.L0000',
            '    LDA t__work__z',
            '    STA t__work__e',
            '    LDX t__work__e,Y',
            '    LDA t__work__e,Y',
            '    BEQ .L0021',
            '    STA t__callee__arg',
            '    JSR t__callee',
            '    LDA #<t__tab',
            '    STA t__work__z',
            '    LDA #>t__tab',
            '    LDY #$00',
            '    LDA (t__work__z),Y',
            '    JMP .L0000',
            '.L0021',
            '    DEC t__work__n',
            '    BNE .L0000',
            '    RTS',
            '', '']))
        self.assertIn('; data t.tab: 4 bytes\nt__tab\n    .byte $01, $02, $03, $04\n', text)

    def test_literal_absolute_below_100_is_bytes(self):
        b = lo.Builder('m')
        f = b.func('m.f')
        f.op('LDA', 'abs', 0x0012)
        f.op('LDA', 'zp,x', 0x34)
        f.op('JMP', '(abs)', 0x0300)
        text = lo2asm.render_module(b.module())
        self.assertIn('    .byte $AD, $12, $00         ; LDA $0012\n', text)
        self.assertIn('    LDA zp_34,X\n', text)
        self.assertIn('    JMP (abs_0300)\n', text)
        self.assertIn('abs_0300 = $0300\nzp_34 = $34\n', text)

    def test_addends_and_names(self):
        b = lo.Builder('m')
        b.extern('o.f', lo.K_FUNC)
        b.extern('o.c', lo.K_CLASS)
        b.data('m.$1', b'\x00\x00\x00')
        f = b.func('m.f')
        f.op('LDA', 'abs,x', 'm.$1', addend=2)
        f.op('LDA', 'abs,x', 'm.$1', addend=0xFFFF)
        f.op('STA', 'abs', ('o.f', 1))
        f.op('STA', 'abs', ('o.c', 0), addend=1)
        f.op('JSR', 'abs', 'o.f')
        text = lo2asm.render_module(b.module())
        self.assertIn('    LDA mS1+$02,X\n    LDA mS1-$01,X\n', text.replace('m__S1', 'mS1'))
        self.assertIn('    STA o__f__1\n    STA o__c__p0+$01\n    JSR o__f\n', text)

    def test_data_fixups(self):
        b = lo.Builder('m')
        f = b.func('m.f')
        f.op('RTS')
        d = b.data('m.d', bytes(range(20)) + b'\x00\x00\x00\x00')
        d.fix(20, lo.FX_WORD, 'm.f')
        d.fix(22, lo.FX_LO, 'm.f', addend=1)
        d.fix(23, lo.FX_HI, 'm.f')
        text = lo2asm.render_module(b.module())
        self.assertIn('m__d\n'
                      '    .byte $00, $01, $02, $03, $04, $05, $06, $07, $08, $09, $0A, $0B, $0C, $0D, $0E, $0F\n'
                      '    .byte $10, $11, $12, $13\n'
                      '    .word m__f\n'
                      '    .byte <m__f+$01\n'
                      '    .byte >m__f\n', text)

    def test_deterministic(self):
        self.assertEqual(lo2asm.render_module(three_class_module()),
                         lo2asm.render_module(lo.read(lo.write(three_class_module()))))


class TestDecodeErrors(unittest.TestCase):
    def render(self, f_setup, pattern):
        b = lo.Builder('m')
        f = b.func('m.f')
        f_setup(b, f)
        m = b.module()
        with self.assertRaisesRegex(lo2asm.RenderError, pattern):
            lo2asm.render_module(m)

    def test_unknown_opcode(self):
        self.render(lambda b, f: f.raw(0x02), r'unknown opcode \$02')

    def test_truncated(self):
        self.render(lambda b, f: f.raw(0xAD, 0x00), 'runs past the end')

    def test_fixup_not_on_operand(self):
        b = lo.Builder('m')
        f = b.func('m.f')
        f.op('JSR', 'abs', 'm.f')
        m = b.module()
        m.functions()[0].fixes[0].offset = 2
        with self.assertRaisesRegex(lo2asm.RenderError, 'not at the operand'):
            lo2asm.render_module(m)

    def test_fixup_kind_width(self):
        b = lo.Builder('m')
        f = b.func('m.f')
        f.op('JSR', 'abs', 'm.f')
        m = b.module()
        m.functions()[0].fixes[0].kind = lo.FX_ZP
        with self.assertRaisesRegex(lo2asm.RenderError, 'kind 4 on a 2-byte operand'):
            lo2asm.render_module(m)

    def test_branch_into_instruction(self):
        self.render(lambda b, f: f.raw(0xD0, 0x01, 0xAD, 0x00, 0x02), 'not at an instruction')


class TestProgramMode(Work):
    def test_hello_runs(self):
        modules = [host_module(), hello_module()]
        entries = naive.allocate(modules, self.env, 'hello')
        self.assertEqual([e.format() for e in entries],
                         ['F 0200 000C host_start.start', 'F 020C 0010 hello.main'])
        text, image = self.assemble(modules, entries, 'hello')
        self.assertIn('no object defines host_start.start', text)
        self.assertEqual(len(image), 0x10000 - CODE)
        self.assertEqual(image, reference_image(modules, entries, self.env, 'hello'))
        self.assertEqual(self.at(image, 0x0200, 12),
                         bytes((0xA2, 0xFF, 0x9A, 0xD8, 0x20, 0x0C, 0x02, 0xA9, 0x00, 0x4C, 0x0F, 0xF0)))
        self.assertEqual(self.at(image, 0xFFFC, 4), b'\x00\x02\x00\x00')
        if not os.path.isfile(build.EMULATOR):
            self.skipTest('emulator/emulator.out is not built (run make)')
        path = os.path.join(self.dir, 'hello.bin')
        with open(path, 'wb') as fh:
            fh.write(image)
        status, out, err = build.run_image(path)
        self.assertEqual((status, out, err), (0, b'HI\n', b''))

    def test_three_classes_zero_page(self):
        modules = [three_class_module()]
        entries = map_lines(MAP_A)
        _, image = self.assemble(modules, entries, 't')
        self.assertEqual(image, reference_image(modules, entries, self.env, 't'))
        self.assertEqual(self.at(image, 0x020C, 3), bytes((0xA5, 0x12, 0x60)))
        self.assertEqual(self.at(image, 0x020F, 0x23), bytes((
            0xA5, 0x10,                 # LDA z           zero page, class 0
            0x85, 0x13,                 # STA e           class 1 landed in zero page
            0xB6, 0x13,                 # LDX e,Y         zp,Y form
            0xB9, 0x13, 0x00,           # LDA e,Y         no zp,Y form: stays absolute
            0xF0, 0x12,                 # BEQ fwd         forward, across three shrunk operands
            0x85, 0x12,                 # STA callee.arg  argument into the callee's slot
            0x20, 0x0C, 0x02,           # JSR callee
            0xA9, 0x36,                 # LDA #<tab
            0x85, 0x10,                 # STA z           kind 4
            0xA9, 0x02,                 # LDA #>tab
            0xA0, 0x00,                 # LDY #0
            0xB1, 0x10,                 # LDA (z),Y       kind 4
            0x4C, 0x0F, 0x02,           # JMP top
            0xCE, 0x10, 0xC0,           # fwd: DEC n      class 2: never zero page
            0xD0, 0xDE,                 # BNE top         backward
            0x60)))
        self.assertEqual(self.at(image, 0x0236, 4), b'\x01\x02\x03\x04')

    def test_three_classes_main_memory(self):
        modules = [three_class_module()]
        entries = map_lines(MAP_B)
        _, image = self.assemble(modules, entries, 't')
        self.assertEqual(image, reference_image(modules, entries, self.env, 't'))
        self.assertEqual(self.at(image, 0x020C, 4), bytes((0xAD, 0x00, 0xC0, 0x60)))
        self.assertEqual(self.at(image, 0x0210, 0x26), bytes((
            0xA5, 0x10,
            0x8D, 0x01, 0xC0,
            0xBE, 0x01, 0xC0,
            0xB9, 0x01, 0xC0,
            0xF0, 0x13,
            0x8D, 0x00, 0xC0,
            0x20, 0x0C, 0x02,
            0xA9, 0x3A,
            0x85, 0x10,
            0xA9, 0x02,
            0xA0, 0x00,
            0xB1, 0x10,
            0x4C, 0x10, 0x02,
            0xCE, 0x10, 0xC0,
            0xD0, 0xDB,
            0x60)))

    def test_naive_matches_reference(self):
        modules = [host_module(), three_class_module()]
        entries = naive.allocate(modules, self.env, 't')
        _, image = self.assemble(modules, entries, 't')
        self.assertEqual(image, reference_image(modules, entries, self.env, 't'))
        kinds = [(e.kind, e.name, e.number) for e in entries if e.kind == 'S']
        self.assertEqual(kinds, [('S', 't.callee', 0), ('S', 't.work', 0), ('S', 't.work', 1),
                                 ('S', 't.work', 2)])
        addrs = {(e.name, e.number): e.addr for e in entries if e.kind == 'S'}
        self.assertEqual(addrs[('t.work', 0)], 0x00)                # class 0: zero page
        self.assertEqual(addrs[('t.work', 1)], 0xC001)              # class 1: data range

    def test_variables_and_data(self):
        b = lo.Builder('v')
        b.extern('v.p', lo.K_CLASS)
        b.clas('v.p', [2])
        b.var('v.zc', 1, cls=0)
        b.var('v.count', 2, cls=1, init=b'\x34\x12')
        v = b.var('v.ptr', 2, cls=2, init=b'\x00\x00')
        v.fix(0, lo.FX_WORD, 'v.msg', addend=1)
        d = b.data('v.msg', b'ok\x00\x00\x00')
        d.fix(3, lo.FX_WORD, 'v.main')
        f = b.func('v.main')
        f.op('LDA', 'abs', 'v.zc')
        f.op('STA', 'abs', ('v.p', 0))
        f.op('LDA', 'abs', 'v.count')
        f.op('RTS')
        modules = [b.module()]
        entries = naive.allocate(modules, self.env, 'v')
        self.assertEqual([e.format() for e in entries], [
            'F 0200 000C host_start.start', 'F 020C 0009 v.main', 'D 0215 0005 v.msg',
            'V 0000 0001 v.zc', 'V C000 0002 v.count', 'V C002 0002 v.ptr', 'C C004 0002 v.p 0 p0'])
        text, image = self.assemble(modules, entries, 'v')
        self.assertEqual(image, reference_image(modules, entries, self.env, 'v'))
        self.assertEqual(self.at(image, 0x020C, 9), bytes((0xA5, 0x00, 0x8D, 0x04, 0xC0, 0xAD, 0x00, 0xC0, 0x60)))
        self.assertEqual(self.at(image, 0x0215, 5), b'ok\x00\x0C\x02')
        self.assertEqual(self.at(image, 0xC000, 4), b'\x34\x12\x16\x02')
        self.assertIn('v__p__p0 = $C004\n', text)

    def test_size_mismatch(self):
        entries = map_lines(MAP_A.replace('F 020F 0023', 'F 020F 0026'))
        with self.assertRaisesRegex(lo2asm.RenderError, 'size \\$0026, the rule gives \\$0023'):
            lo2asm.render_program([three_class_module()], entries, self.env, 't')

    def test_missing_slot(self):
        entries = map_lines(MAP_A.replace('S 0013 0001 t.work 1 e\n', ''))
        with self.assertRaisesRegex(lo2asm.RenderError, 't.work slot 1 is not in the map'):
            lo2asm.render_program([three_class_module()], entries, self.env, 't')

    def test_zero_page_initialised_variable(self):
        b = lo.Builder('v')
        b.var('v.x', 1, cls=0, init=b'\x01')
        b.func('v.main').op('RTS')
        with self.assertRaisesRegex(naive.AllocError, 'initialised variable in zero page'):
            naive.allocate([b.module()], self.env, 'v')
        entries = map_lines('F 0200 000C host_start.start\nF 020C 0001 v.main\nV 0010 0001 v.x\n')
        with self.assertRaisesRegex(lo2asm.RenderError, 'below the image'):
            lo2asm.render_program([b.module()], entries, self.env, 'v')

    def test_cli(self):
        paths = []
        for m in (host_module(), hello_module()):
            paths.append(os.path.join(self.dir, m.name + '.lo'))
            with open(paths[-1], 'wb') as fh:
                fh.write(lo.write(m))
        mp = os.path.join(self.dir, 'hello.map')
        self.assertEqual(naive.main([HOST_ENV, 'hello', mp] + paths), 0)
        out = os.path.join(self.dir, 'hello.asm')
        self.assertEqual(lo2asm.main(['--map', mp, '--env', HOST_ENV, '-o', out] + paths), 0)
        with open(out) as fh:
            self.assertIn('    JSR hello__main\n', fh.read())


if __name__ == '__main__':
    unittest.main()
