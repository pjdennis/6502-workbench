"""lathe/host/driver/lo.py: reading, writing and building object files (docs/object-format.md)."""
import os
import struct
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'lathe', 'host', 'driver'))
sys.path.insert(0, os.path.join(ROOT, 'asm'))

import cpu6502  # noqa: E402
import lo  # noqa: E402


def rec(t, body=b''):
    return bytes((t,)) + struct.pack('<H', len(body)) + body


def string(s):
    return bytes((len(s),)) + s.encode('latin-1')


MOD = rec(lo.R_MOD, b'\x01\x00' + string('m'))
END = rec(lo.R_END)


def sym(kind, name):
    return rec(lo.R_SYM, bytes((kind,)) + string(name))


def fix_entry(offset, kind, symbol, slot, addend):
    return struct.pack('<HBHBH', offset, kind, symbol, slot, addend)


def func(symbol, *records, flags=0):
    return rec(lo.R_FUNC, struct.pack('<HB', symbol, flags)) + b''.join(records) + rec(lo.R_ENDF)


def hello():
    b = lo.Builder('hello')
    b.imp('host')
    f = b.func('hello.main')
    for ch in (0x48, 0x49, 0x0A):
        f.op('LDA', '#', ch)
        f.op('JSR', 'abs', 0xF009)
    f.op('RTS')
    return b


class TestOpcodeTable(unittest.TestCase):
    def test_matches_pyasm(self):
        import pyasm
        mode = {pyasm.MODE_NONE: cpu6502.IMP, pyasm.MODE_IMM: cpu6502.IMM, pyasm.MODE_ZP: cpu6502.ZP,
                pyasm.MODE_ZPX: cpu6502.ZPX, pyasm.MODE_ZPY: cpu6502.ZPY, pyasm.MODE_ABS: cpu6502.ABS,
                pyasm.MODE_ABSX: cpu6502.ABSX, pyasm.MODE_ABSY: cpu6502.ABSY,
                pyasm.MODE_INDX: cpu6502.INDX, pyasm.MODE_INDY: cpu6502.INDY,
                pyasm.MODE_REL: cpu6502.REL, pyasm.MODE_IND: cpu6502.IND}
        theirs = {m: {mode[md]: op for md, op in modes} for m, modes in pyasm.INSTRUCTIONS.items()}
        self.assertEqual(theirs, cpu6502.NMOS)

    def test_shrinks(self):
        self.assertEqual(cpu6502.shrinks(0, 'LDA', 'abs'), 'zp')
        self.assertEqual(cpu6502.shrinks(0, 'LDX', 'abs,y'), 'zp,y')
        self.assertIsNone(cpu6502.shrinks(0, 'LDA', 'abs,y'))
        self.assertIsNone(cpu6502.shrinks(0, 'JMP', 'abs'))
        self.assertIsNone(cpu6502.shrinks(0, 'JSR', 'abs'))


class TestWrite(unittest.TestCase):
    def test_hello_bytes(self):
        code = bytes((0xA9, 0x48, 0x20, 0x09, 0xF0, 0xA9, 0x49, 0x20, 0x09, 0xF0,
                      0xA9, 0x0A, 0x20, 0x09, 0xF0, 0x60))
        want = (rec(lo.R_MOD, b'\x01\x00' + string('hello')) + rec(lo.R_IMP, string('host'))
                + sym(1, 'hello.main')
                + func(0, rec(lo.R_FIX), rec(lo.R_CODE, code)) + END)
        self.assertEqual(hello().bytes(), want)

    def test_round_trip(self):
        b = hello()
        m = lo.read(b.bytes())
        self.assertEqual(m, b.module())
        self.assertEqual(lo.write(m), b.bytes())
        self.assertEqual(m.name, 'hello')
        self.assertEqual(m.imports, ['host'])
        self.assertEqual(m.functions()[0].sym, 0)
        self.assertEqual(m.sym_name(0), 'hello.main')

    def test_everything_round_trips(self):
        b = lo.Builder('demo', cpu=1)
        b.extern('util.f', lo.K_FUNC)
        b.extern('util.ptr', lo.K_CLASS)
        b.clas('util.ptr', [2, 1], flags=1)
        b.var('demo.count', 2, cls=1, weight=7)
        b.var('demo.big', 300, cls=2, weight=0)
        d = b.data('demo.msg', b'hi\x00\x00\x00')
        d.fix(3, lo.FX_WORD, 'demo.main')
        f = b.func('demo.main', flags=lo.F_EXPORTED)
        f.slot('a', 1, cls=0, weight=3, kind=lo.SK_PARAM)
        f.slot('t', 2, cls=2, weight=0, kind=lo.SK_TEMP)
        f.call('util.f', flags=1, outer='util.ptr')
        f.label('top')
        f.op('LDA', 'abs', ('demo.main', 'a'))
        f.op('STA', 'abs', ('util.f', 0), addend=1)
        f.op('BNE', 'rel', 'top')
        f.op('JMP', 'abs', 'top')
        f.op('RTS')
        b.memb('util.ptr', 'demo.main')
        m = lo.read(b.bytes())
        self.assertEqual(m, b.module())
        self.assertEqual(m.cpu, 1)
        fn = m.functions()[0]
        self.assertEqual([s.name for s in fn.slots], ['a', 't'])
        self.assertEqual(fn.calls, [lo.Call(m.sym_index('util.f'), 1, m.sym_index('util.ptr'))])
        self.assertEqual([(x.offset, x.kind, x.slot, x.addend) for x in fn.fixes],
                         [(1, 1, 0, 0), (4, 1, 0, 1), (9, 1, 0xFF, 0)])
        self.assertEqual(fn.code, bytes((0xAD, 0, 0, 0x8D, 0, 0, 0xD0, 0xF8, 0x4C, 0, 0, 0x60)))
        self.assertEqual(m.items[-1], lo.Memb(m.sym_index('util.ptr'), m.sym_index('demo.main')))


class TestBuilder(unittest.TestCase):
    def test_modes_and_fixups(self):
        b = lo.Builder('t')
        b.data('t.tab', b'\x00')
        f = b.func('t.f')
        f.slot('p', 2, cls=0, weight=1, kind=lo.SK_PARAM)
        f.op('LDA', '#<', 't.tab')
        f.op('LDX', '#>', 't.tab', addend=2)
        f.op('LDA', '(zp),y', ('t.f', 'p'))
        f.op('LDA', 'zp', 0x12)
        f.op('ASL')
        f.op('BEQ', 'rel', 'end')
        f.op('LDA', 'abs,x', 't.tab')
        f.label('end')
        f.op('RTS')
        b.module()
        fn = f.func
        self.assertEqual(fn.code, bytes((0xA9, 0, 0xA2, 0, 0xB1, 0, 0xA5, 0x12, 0x0A,
                                         0xF0, 0x03, 0xBD, 0, 0, 0x60)))
        self.assertEqual([(x.offset, x.kind, x.slot, x.addend) for x in fn.fixes],
                         [(1, 2, 0xFF, 0), (3, 3, 0xFF, 2), (5, 4, 0, 0), (12, 1, 0xFF, 0)])

    def test_branch_out_of_range(self):
        f = lo.Builder('t').func('t.f')
        f.op('BNE', 'rel', 'far')
        for _ in range(64):
            f.op('LDA', 'abs', 0x1234)
        f.label('far')
        with self.assertRaisesRegex(lo.LoError, 'out of range'):
            f.finish()

    def test_undeclared_symbol(self):
        b = lo.Builder('t')
        b.func('t.f').op('JSR', 'abs', 'x.y')
        with self.assertRaisesRegex(lo.LoError, 'x.y.*not declared'):
            b.bytes()

    def test_bad_mode(self):
        f = lo.Builder('t').func('t.f')
        with self.assertRaisesRegex(lo.LoError, 'no mode'):
            f.op('STA', '#', 1)


class TestReadErrors(unittest.TestCase):
    def bad(self, data, pattern):
        with self.assertRaisesRegex(lo.LoError, pattern):
            lo.read(data, 'x.lo')

    def test_message_names_file_and_offset(self):
        with self.assertRaisesRegex(lo.LoError, r'^x\.lo: offset \$0000: '):
            lo.read(rec(lo.R_IMP, string('a')) + END, 'x.lo')

    def test_first_record_must_be_mod(self):
        self.bad(rec(lo.R_IMP, string('a')) + END, 'first record must be MOD')

    def test_version(self):
        self.bad(rec(lo.R_MOD, b'\x02\x00' + string('m')) + END, 'version 2')

    def test_cpu(self):
        self.bad(rec(lo.R_MOD, b'\x01\x05' + string('m')) + END, 'CPU 5')

    def test_missing_end(self):
        self.bad(MOD, 'no END record')

    def test_after_end(self):
        self.bad(MOD + END + END, 'after the END')

    def test_truncated(self):
        self.bad(MOD + b'\x03\x10', 'truncated')
        self.bad(MOD + rec(lo.R_SYM, b'\x01\x05ab'), 'string runs past')

    def test_unknown_record(self):
        self.bad(MOD + rec(0x55) + END, r'unknown record type \$55')

    def test_symbol_kind(self):
        self.bad(MOD + sym(9, 'm.a') + END, 'symbol kind 9')

    def test_symbol_out_of_range(self):
        self.bad(MOD + sym(1, 'm.f') + func(1, rec(lo.R_CODE, b'\x60')) + END, 'symbol 1 .*not defined')

    def test_symbol_wrong_kind(self):
        self.bad(MOD + sym(2, 'm.v') + func(0, rec(lo.R_CODE, b'\x60')) + END, 'FUNC .*m.v.* is a variable')

    def test_defined_twice(self):
        f = func(0, rec(lo.R_CODE, b'\x60'))
        self.bad(MOD + sym(1, 'm.f') + f + f + END, 'defined twice')

    def test_duplicate_symbol_name(self):
        self.bad(MOD + sym(1, 'm.f') + sym(1, 'm.f') + END, 'second SYM')

    def test_function_record_order(self):
        slot = rec(lo.R_SLOT, struct.pack('<HBBB', 1, 1, 0, 1) + string('a'))
        call = rec(lo.R_CALL, struct.pack('<HBH', 0, 0, 0xFFFF))
        code = rec(lo.R_CODE, b'\x60')
        self.bad(MOD + sym(1, 'm.f') + func(0, call, slot, code) + END, 'SLOT .*after')
        self.bad(MOD + sym(1, 'm.f') + func(0, code, rec(lo.R_FIX)) + END, 'FIX .*after')
        self.bad(MOD + sym(1, 'm.f') + func(0, rec(lo.R_FIX)) + END, 'no CODE')
        self.bad(MOD + sym(1, 'm.f') + rec(lo.R_FUNC, b'\x00\x00\x00') + code + END, 'not closed by ENDF')
        self.bad(MOD + sym(1, 'm.f') + code + END, 'CODE record outside a function')

    def test_slot_kinds_params_first(self):
        local = rec(lo.R_SLOT, struct.pack('<HBBB', 1, 1, 0, 1) + string('a'))
        param = rec(lo.R_SLOT, struct.pack('<HBBB', 1, 1, 0, 0) + string('b'))
        self.bad(MOD + sym(1, 'm.f') + func(0, local, param, rec(lo.R_CODE, b'\x60')) + END,
                 'parameter .*after')

    def test_slot_class(self):
        s = rec(lo.R_SLOT, struct.pack('<HBBB', 1, 3, 0, 0) + string('a'))
        self.bad(MOD + sym(1, 'm.f') + func(0, s, rec(lo.R_CODE, b'\x60')) + END, 'class 3')

    def test_fixups_sorted(self):
        fx = rec(lo.R_FIX, fix_entry(4, 1, 0, 0xFF, 0) + fix_entry(1, 1, 0, 0xFF, 0))
        code = rec(lo.R_CODE, b'\x20\x00\x00\x20\x00\x00\x60')
        self.bad(MOD + sym(1, 'm.f') + func(0, fx, code) + END, 'not sorted')

    def test_fixup_length(self):
        self.bad(MOD + sym(1, 'm.f') + func(0, rec(lo.R_FIX, b'\x00'), rec(lo.R_CODE, b'\x60')) + END,
                 'multiple of 8')

    def test_fixup_past_code(self):
        fx = rec(lo.R_FIX, fix_entry(2, 1, 0, 0xFF, 0))
        self.bad(MOD + sym(1, 'm.f') + func(0, fx, rec(lo.R_CODE, b'\x20\x00\x00')) + END, 'past the end')

    def test_fixup_kind(self):
        fx = rec(lo.R_FIX, fix_entry(1, 7, 0, 0xFF, 0))
        self.bad(MOD + sym(1, 'm.f') + func(0, fx, rec(lo.R_CODE, b'\x20\x00\x00')) + END, 'fix-up kind 7')

    def test_fixup_target_slot(self):
        fx = rec(lo.R_FIX, fix_entry(1, 1, 1, 0, 0))
        self.bad(MOD + sym(1, 'm.f') + sym(2, 'm.v') + func(0, fx, rec(lo.R_CODE, b'\x20\x00\x00')) + END,
                 'slot 0 of .*m.v')
        fx = rec(lo.R_FIX, fix_entry(1, 1, 0, 3, 0))
        self.bad(MOD + sym(1, 'm.f') + func(0, fx, rec(lo.R_CODE, b'\xAD\x00\x00')) + END,
                 'slot 3 .*has 0 slots')
        fx = rec(lo.R_FIX, fix_entry(1, 1, 0, 0xFF, 0))
        self.bad(MOD + sym(4, 'm.c') + sym(1, 'm.f') + func(1, fx, rec(lo.R_CODE, b'\xAD\x00\x00')) + END,
                 'class .* needs a parameter')

    def test_dfix_placement(self):
        self.bad(MOD + rec(lo.R_DFIX) + END, 'DFIX record not just after a DATA record')
        v = rec(lo.R_VAR, struct.pack('<HHBBB', 0, 1, 1, 0, 0))
        self.bad(MOD + sym(2, 'm.v') + v + rec(lo.R_DFIX, fix_entry(0, 2, 0, 0xFF, 0)) + END,
                 'DFIX record not just after a DATA record')

    def test_var_has_no_initial_value(self):
        v = rec(lo.R_VAR, struct.pack('<HHBBB', 0, 2, 1, 0, 1) + b'\x01\x02')
        self.bad(MOD + sym(2, 'm.v') + v + END,
                 r'VAR m\.v: flag bit 0 \(initial value\) is not in format version 1: '
                 r'variables have no initial values; the compiler sets them in module\.\$init')
        v = rec(lo.R_VAR, struct.pack('<HHBBB', 0, 2, 1, 0, 0x80))
        self.bad(MOD + sym(2, 'm.v') + v + END, r'VAR m\.v: unknown flags \$80')
        v = rec(lo.R_VAR, struct.pack('<HHBBB', 0, 2, 1, 0, 0) + b'\x01')
        self.bad(MOD + sym(2, 'm.v') + v + END, 'VAR record has 1 unexpected bytes')

    def test_builder_var_takes_no_initial_value(self):
        with self.assertRaises(TypeError):
            lo.Builder('m').var('m.v', 1, 1, 0, b'\x01')

    def test_record_length(self):
        self.bad(MOD + sym(1, 'm.f') + rec(lo.R_FUNC, b'\x00\x00\x00') + rec(lo.R_CODE, b'\x60')
                 + rec(lo.R_ENDF, b'\x00') + END, 'ENDF .*length')
        self.bad(MOD + rec(lo.R_IMP, b'\x01') + END, 'string runs past')
        self.bad(MOD + rec(lo.R_IMP, string('a') + b'\x00') + END, 'unexpected bytes')


class TestLodump(unittest.TestCase):
    def run_dump(self, data):
        import subprocess
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.lo', delete=False) as fh:
            fh.write(data)
        try:
            return subprocess.run([sys.executable, os.path.join(ROOT, 'lathe', 'host', 'driver', 'lodump.py'),
                                   fh.name], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        finally:
            os.unlink(fh.name)

    def test_hello(self):
        r = self.run_dump(hello().bytes())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), [
            '0000  MOD   version 1, cpu 6502, module hello',
            '000B  IMP   host',
            '0013  SYM   #0 function hello.main',
            '0022  FUNC  hello.main  flags: -',
            '0028  FIX   0 entries',
            '002B  CODE  16 bytes',
            '            0000  A9 48     LDA #$48',
            '            0002  20 09 F0  JSR $F009',
            '            0005  A9 49     LDA #$49',
            '            0007  20 09 F0  JSR $F009',
            '            000A  A9 0A     LDA #$0A',
            '            000C  20 09 F0  JSR $F009',
            '            000F  60        RTS',
            '003E  ENDF',
            '0041  END'])

    def test_invalid_file(self):
        r = self.run_dump(MOD)
        self.assertEqual(r.returncode, 1)
        self.assertIn('MOD   version 1', r.stdout)
        self.assertIn('no END record', r.stderr)


if __name__ == '__main__':
    unittest.main()
