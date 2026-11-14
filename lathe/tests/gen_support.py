"""Shared by the tests of GEN's three files (reg.py, cond.py, gen.py): a module `m` being
written to a temporary object file, a function `m.f` being generated, and its code as text.

listing() ends the function and gives one string for each instruction:

    LDA #$05        an immediate
    STA s1          slot 1 of the function itself; its temporaries follow its locals
    ADC g2+1        the symbol with object-file number 2, plus 1
    STA f3.0        slot 0 of the function with object-file number 3
    LDA zp:s0       a zero page instruction with a fix-up
    LDA $D020       a fixed address
    BNE @12         a branch to offset 12; `JMP @12` likewise
    LDA g2,X        indexed; `LDA (zp:s0),Y` through a pointer
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lathec_support as support  # noqa: E402

sys.path.append(os.path.join(support.HOST, 'driver'))
import cpu6502  # noqa: E402

import err  # noqa: E402
import fbuf  # noqa: E402
import gen  # noqa: E402
import kernel  # noqa: E402
import out  # noqa: E402
import reg  # noqa: E402
import typetab  # noqa: E402

BYTE, SBYTE, WORD, INT, BOOL = (typetab.BYTE_TYPE, typetab.SBYTE_TYPE, typetab.WORD_TYPE,
                                typetab.INT_TYPE, typetab.BOOL_TYPE)
NUMBER, NEGATIVE = typetab.NUMBER_TYPE, typetab.NEGATIVE_TYPE


def name(text):
    kernel.name_begin()
    for ch in text:
        kernel.name_add(ch)
    return kernel.name_end()


def _target(fix, own):
    if fix[2] == own and fix[3] == 0xFF:
        text = '@%d' % fix[4]
        return text
    if fix[2] == own:
        text = 's%d' % fix[3]
    elif fix[3] != 0xFF:
        text = 'f%d.%d' % (fix[2], fix[3])
    else:
        text = 'g%d' % fix[2]
    return text + ('+%d' % fix[4] if fix[4] else '')


def decode(own):
    """The finished function in FBUF as a list of instruction texts."""
    code, fix_list = support.finished()
    fixes = {f[0]: f for f in fix_list}
    lines, at = [], 0
    while at < len(code):
        mnemonic, mode, size = cpu6502.decode(0, code, at)
        value = int.from_bytes(code[at + 1:at + size], 'little')
        fix = fixes.get(at + 1)
        if mode == cpu6502.IMP:
            text = mnemonic
        elif mode == cpu6502.REL:
            text = '%s @%d' % (mnemonic, at + 2 + (value - 256 if value > 127 else value))
        elif fix is not None:
            prefix = {1: '', 2: '#<', 3: '#>', 4: 'zp:', 5: ''}[fix[1]]
            text = '%s %s%s' % (mnemonic, prefix, _target(fix, own))
        elif mode == cpu6502.IMM:
            text = '%s #$%02X' % (mnemonic, value)
        else:
            text = '%s $%0*X' % (mnemonic, 2 * (size - 1), value)
        if mode in (cpu6502.ABSX, cpu6502.ZPX):
            text += ',X'
        elif mode in (cpu6502.ABSY, cpu6502.ZPY):
            text += ',Y'
        elif mode == cpu6502.INDY:
            text = '%s (%s),Y' % (mnemonic, text.split(' ', 1)[1])
        lines.append(text)
        at += size
    return lines


class GenTest(unittest.TestCase):
    """A module `m` (number 0) that imports `util` (number 1), and a function `m.f`, object
    symbol 0, being generated."""

    def setUp(self):
        support.fresh()
        err.init()
        kernel.init()
        typetab.init()
        out.init()
        gen.init()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'm.lo')
        pointer, _ = support.put_text(self.path.encode())
        out.open(pointer)
        kernel.module_add(name(b'm'))
        kernel.module_add(name(b'util'))
        self.own = out.symbol(out.SYM_FUNCTION, name(b'm'), 0, name(b'f'))
        gen.function_begin(self.own)

    def listing(self):
        """End the function and give its instructions."""
        gen.function_end(0)
        return decode(self.own)

    def records(self):
        out.end_module()
        return support.records(self.path)

    def assertFatal(self, number, call):
        with self.assertRaises(SystemExit):
            call()
        self.assertIn('error %d:' % number, support.error_text())

    # ---- things to push -----------------------------------------------------------------

    def slot(self, t, text=b'v', zp_class=1):
        """A new local of type t. Returns its slot number."""
        return reg.new_slot(typetab.size(t), zp_class, reg.SLOT_LOCAL, name(text))

    def local(self, t, text=b'v', zp_class=1):
        """Push a new local of type t. Returns its slot number."""
        n = self.slot(t, text, zp_class)
        gen.local(t, n)
        return n

    def variable(self, t, text, flags=0, address=0, scope=kernel.SCOPE_MODULE):
        """A variable that lives for the whole program. Returns its kernel symbol."""
        s = kernel.sym_add(scope, name(text), kernel.K_VAR)
        kernel.sym_type[s] = t
        kernel.sym_flags[s] = flags
        kernel.sym_value[s] = address
        return s

    def function(self, text, params=(), results=(), scope=kernel.SCOPE_MODULE, flags=0, address=0):
        """A function with (type, register) parameters and results. Returns its kernel symbol."""
        s = kernel.sym_add(scope, name(text), kernel.K_FUNC)
        kernel.sym_flags[s] = flags
        kernel.sym_value[s] = address
        for t, where in tuple(params) + tuple(results):
            kernel.member_add(t, where)
        kernel.sym_params[s] = len(params)
        kernel.sym_results[s] = len(results)
        return s
