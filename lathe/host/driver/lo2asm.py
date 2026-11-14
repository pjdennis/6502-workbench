#!/usr/bin/env python3
"""Render Lathe object files as asm17 text (lathe/docs/object-format.md, "Rendering as assembler text").

    lo2asm.py FILE.lo [-o OUT.asm]
        Module mode: one module, no addresses. The text the snapshot tests compare.

    lo2asm.py --map OUT.map --env ENV [--main MODULE] -o OUT.asm A.lo B.lo ...
        Program mode: one asm17 source for the whole program. Assembled (asm/pyasm.py or asm17)
        it gives the image the linker gives: code start to $FFFF, reset vector at $FFFC.

Names: symbol mod.name is label mod__name; slot s of mod.f is mod__f__s; parameter n of class
mod.c is mod__c__pN (CLAS records carry no parameter names); a label inside a function is .L
and its written offset in four hex digits. Characters asm17 does not allow in a name ($ in
compiler-made names such as hello.$1) are written S, or X and two hex digits; names are lower
case, so these cannot collide with a user's name. Literal memory operands are written through
equates (abs_f009 = $F009, zp_12 = $12) because asm17 forces a literal to absolute after a
forward reference; an absolute instruction whose literal operand is below $100 (which asm17
would shrink) is written as .byte with the instruction in a comment.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cpu6502  # noqa: E402
import lo  # noqa: E402
import mapenv  # noqa: E402

INDENT = '    '
CLASS_NAMES = {0: 'zp', 1: 'either', 2: 'not zp'}
STARTUP_SIZE = 12
HOST_EXIT = 0xF00F


class RenderError(Exception):
    pass


# ---------------------------------------------------------------------------------------------
# Names

def mangle(name):
    out = []
    for ch in name:
        if ch == '.':
            out.append('__')
        elif ch.isascii() and (ch.isalnum() or ch == '_'):
            out.append(ch)
        elif ch == '$':
            out.append('S')
        else:
            out.append(f'X{ord(ch):02X}')
    return ''.join(out)


def slot_label(func_name, slot_name):
    return f'{mangle(func_name)}__{mangle(slot_name)}'


def param_label(class_name, n):
    return f'{mangle(class_name)}__p{n}'


def local_label(offset):
    return f'.L{offset:04X}'


def hex_value(v):
    return f'${v:02X}' if v < 0x100 else f'${v:04X}'


def with_addend(text, addend):
    addend &= 0xFFFF
    if addend == 0:
        return text
    if addend >= 0x8000:
        return f'{text}-{hex_value(0x10000 - addend)}'
    return f'{text}+{hex_value(addend)}'


# ---------------------------------------------------------------------------------------------
# Decoding a function

class Ins:
    __slots__ = ('offset', 'mnemonic', 'mode', 'length', 'operand', 'fix', 'target')

    def __init__(self, offset, mnemonic, mode, length, operand):
        self.offset, self.mnemonic, self.mode, self.length, self.operand = \
            offset, mnemonic, mode, length, operand
        self.fix = None
        self.target = None         # branch target (written offset)


def decode_function(m, f):
    """The instructions of f, with fix-ups attached, and the set of label offsets.
    Raises RenderError if the code and fix-ups do not fit together."""
    fname = m.sym_name(f.sym)
    code = f.code
    out = []
    starts = set()
    i = 0
    while i < len(code):
        try:
            mn, mode, n = cpu6502.decode(m.cpu, code, i)
        except ValueError as e:
            raise RenderError(f'{m.name}: function {fname}: {e}') from None
        out.append(Ins(i, mn, mode, n, int.from_bytes(code[i + 1:i + n], 'little')))
        starts.add(i)
        i += n
    by_operand = {x.offset + 1: x for x in out if x.length > 1}
    labels = set()
    for fx in f.fixes:
        ins = by_operand.get(fx.offset)
        where = f'{m.name}: function {fname}: fix-up at ${fx.offset:04X}'
        if ins is None:
            raise RenderError(f'{where} is not at the operand of an instruction')
        if ins.mode == cpu6502.REL:
            raise RenderError(f'{where} is on a branch')
        width = ins.length - 1
        if lo.FIX_WIDTH[fx.kind] != width:
            raise RenderError(f'{where}: kind {fx.kind} on a {width}-byte operand ({ins.mnemonic})')
        if ins.mode == cpu6502.IMM and fx.kind not in (lo.FX_LO, lo.FX_HI):
            raise RenderError(f'{where}: an immediate operand takes kind 2 or 3, not {fx.kind}')
        ins.fix = fx
        if fx.sym == f.sym and fx.slot == lo.NO_SLOT:
            labels.add(fx.addend)
    for ins in out:
        if ins.mode == cpu6502.REL:
            disp = ins.operand - 256 if ins.operand > 127 else ins.operand
            ins.target = ins.offset + 2 + disp
            labels.add(ins.target)
    for t in labels:
        if t not in starts and t != len(code):
            raise RenderError(f'{m.name}: function {fname}: label ${t:04X} is not at an instruction')
    return out, labels


def final_size(m, f, resolve):
    """Size of f once placed, by the rule of object-format.md ("The size of an instruction").
    resolve(module, fix) gives the target's address, or None if it is not known yet (code and data
    then, which lie in the code range and so not in zero page)."""
    ins, _ = decode_function(m, f)
    size = 0
    for x in ins:
        size += x.length
        if shrinks(m, x, resolve):
            size -= 1
    return size


def shrinks(m, x, resolve):
    if x.fix is None or x.fix.kind != lo.FX_WORD:
        return False
    if cpu6502.shrinks(m.cpu, x.mnemonic, x.mode) is None:
        return False
    addr = resolve(m, x.fix)
    return addr is not None and (addr + x.fix.addend) & 0xFFFF < 0x100


# ---------------------------------------------------------------------------------------------
# Rendering

class Program:
    """The objects being rendered together: finds definitions by name across modules."""

    def __init__(self, modules):
        self.modules = modules
        self.defs = {}             # name -> (module, item)
        for m in modules:
            for x in m.items:
                if isinstance(x, (lo.Func, lo.Var, lo.Data)):
                    self.defs.setdefault(m.sym_name(x.sym), (m, x))

    def func(self, name):
        d = self.defs.get(name)
        return d[1] if d and isinstance(d[1], lo.Func) else None


class Renderer:
    def __init__(self, program):
        self.program = program
        self.equates = {}          # name -> value, for literal operands

    def target_text(self, m, fx, current):
        s = m.symbols[fx.sym]
        if s.kind == lo.K_FUNC and fx.slot == lo.NO_SLOT:
            if current is not None and fx.sym == current.sym:
                return local_label(fx.addend)
            return with_addend(mangle(s.name), fx.addend)
        if s.kind == lo.K_FUNC:
            f = self.program.func(s.name)
            if f is not None:
                if fx.slot >= len(f.slots):
                    raise RenderError(f'{m.name}: fix-up names slot {fx.slot} of {s.name}, '
                                      f'which has {len(f.slots)} slots')
                text = slot_label(s.name, f.slots[fx.slot].name)
            else:
                text = f'{mangle(s.name)}__{fx.slot}'
            return with_addend(text, fx.addend)
        if s.kind == lo.K_CLASS:
            return with_addend(param_label(s.name, fx.slot), fx.addend)
        return with_addend(mangle(s.name), fx.addend)

    def literal(self, value, width):
        name = f'abs_{value:04x}' if width == 2 else f'zp_{value:02x}'
        self.equates[name] = value
        return name

    def instruction(self, m, x, current):
        mn, mode = x.mnemonic, x.mode
        if mode == cpu6502.IMP:
            return f'{INDENT}{mn}'
        if mode == cpu6502.REL:
            return f'{INDENT}{mn} {local_label(x.target)}'
        width = x.length - 1
        if x.fix is not None:
            e = self.target_text(m, x.fix, current)
            if x.fix.kind == lo.FX_LO:
                e = '<' + e
            elif x.fix.kind == lo.FX_HI:
                e = '>' + e
        elif mode == cpu6502.IMM:
            return f'{INDENT}{mn} #${x.operand:02X}'
        elif width == 2 and x.operand < 0x100 and cpu6502.shrinks(m.cpu, mn, mode):
            raw = ', '.join(f'${b:02X}' for b in current.code[x.offset:x.offset + 3])
            line = f'{INDENT}.byte {raw}'
            return f'{line:<31} ; {mn} {_mode_text(mode, f"${x.operand:04X}")}'
        else:
            e = self.literal(x.operand, width)
        if mode == cpu6502.IMM:
            return f'{INDENT}{mn} #{e}'
        return f'{INDENT}{mn} {_mode_text(mode, e)}'

    def function(self, m, f, comment=True):
        lines = []
        name = m.sym_name(f.sym)
        if comment:
            lines += function_comment(m, f)
        ins, labels = decode_function(m, f)
        lines.append(mangle(name))
        for x in ins:
            if x.offset in labels:
                lines.append(local_label(x.offset))
            lines.append(self.instruction(m, x, f))
        if len(f.code) in labels:
            lines.append(local_label(len(f.code)))
        return lines

    def data_lines(self, m, data, fixes):
        """.byte / .word lines for bytes with fix-ups."""
        lines = []
        by_offset = {fx.offset: fx for fx in fixes}
        run = []

        def flush():
            if run:
                lines.append(f'{INDENT}.byte ' + ', '.join(f'${b:02X}' for b in run))
                run.clear()
        i = 0
        while i < len(data):
            fx = by_offset.get(i)
            if fx is None:
                run.append(data[i])
                if len(run) == 16:
                    flush()
                i += 1
                continue
            flush()
            e = self.target_text(m, fx, None)
            if fx.kind == lo.FX_WORD:
                lines.append(f'{INDENT}.word {e}')
            else:
                lines.append(f'{INDENT}.byte {"<" if fx.kind == lo.FX_LO else ">" if fx.kind == lo.FX_HI else ""}{e}')
            i += lo.FIX_WIDTH[fx.kind]
        flush()
        return lines

    def equate_lines(self):
        return [f'{n} = ${v:02X}' if n.startswith('zp_') else f'{n} = ${v:04X}'
                for n, v in sorted(self.equates.items())]


def _mode_text(mode, e):
    return {cpu6502.ABS: e, cpu6502.ZP: e, cpu6502.ABSX: f'{e},X', cpu6502.ZPX: f'{e},X',
            cpu6502.ABSY: f'{e},Y', cpu6502.ZPY: f'{e},Y', cpu6502.INDX: f'({e},X)',
            cpu6502.INDY: f'({e}),Y', cpu6502.IND: f'({e})'}[mode]


def _flag_text(flags, names):
    return ', '.join(n for bit, n in names if flags & bit)


def function_comment(m, f):
    name = m.sym_name(f.sym)
    flags = _flag_text(f.flags, lo.FUNC_FLAG_NAMES)
    lines = [f'; function {name}' + (f': {flags}' if flags else '')]
    for i, s in enumerate(f.slots):
        lines.append(f';   slot {i} {s.name}: size {s.size}, class {s.cls} ({CLASS_NAMES[s.cls]}), '
                     f'{lo.SLOT_KIND_NAMES[s.kind]}, weight {s.weight}')
    if not f.slots:
        lines.append(';   no slots')
    for c in f.calls:
        bits = _flag_text(c.flags, ((lo.C_SAVES, 'saves frame'), (lo.C_POINTER, 'through pointer')))
        outer = '' if c.outer == lo.NO_OUTER else f'; outer {m.sym_name(c.outer)}'
        lines.append(f';   calls {m.sym_name(c.callee)}' + (f' ({bits})' if bits else '') + outer)
    return lines


def var_comment(m, v):
    init = ', initialised' if v.init is not None else ''
    return (f'; variable {m.sym_name(v.sym)}: size {v.size}, class {v.cls} ({CLASS_NAMES[v.cls]}), '
            f'weight {v.weight}{init}')


def render_module(m, others=()):
    """Module mode: the text for one module (others: objects to look up foreign slot names in)."""
    r = Renderer(Program([m] + list(others)))
    body = []
    for x in m.items:
        body.append('')
        if isinstance(x, lo.Func):
            body += r.function(m, x)
        elif isinstance(x, lo.Var):
            body.append(var_comment(m, x))
            if x.init is not None:
                body.append(mangle(m.sym_name(x.sym)))
                body += r.data_lines(m, x.init, x.fixes)
        elif isinstance(x, lo.Data):
            body.append(f'; data {m.sym_name(x.sym)}: {len(x.data)} bytes')
            body.append(mangle(m.sym_name(x.sym)))
            body += r.data_lines(m, x.data, x.fixes)
        elif isinstance(x, lo.Clas):
            rec = '; recursive' if x.flags & lo.CLAS_RECURSIVE else ''
            sizes = ', '.join(str(p) for p in x.params) or 'none'
            body.append(f'; class {m.sym_name(x.sym)}: parameter sizes {sizes}{rec}')
        elif isinstance(x, lo.Memb):
            body.append(f'; {m.sym_name(x.func)} is a member of class {m.sym_name(x.cls)}')
    head = [f'; module {m.name}, cpu {"65c02" if m.cpu else "6502"}']
    if m.imports:
        head.append('; imports: ' + ', '.join(m.imports))
    eq = r.equate_lines()
    if eq:
        head += [''] + eq
    return '\n'.join(head + body) + '\n'


# ---------------------------------------------------------------------------------------------
# Program mode

def startup_lines(start, main):
    return [f'; {start}: start-up code made by lo2asm, because no object defines {start}',
            ';   (stack, decimal mode off, call main, exit through the host call at $F00F)',
            mangle(start),
            f'{INDENT}LDX #$FF',
            f'{INDENT}TXS',
            f'{INDENT}CLD',
            f'{INDENT}JSR {mangle(main)}',
            f'{INDENT}LDA #$00',
            f'{INDENT}JMP abs_{HOST_EXIT:04x}']


class Addresses:
    """Addresses from a map: resolves fix-up targets."""

    def __init__(self, entries, program):
        self.items = {}            # name -> address (functions, data, variables)
        self.parts = {}            # (name, number) -> address (slots, class parameters)
        for e in entries:
            if e.kind in (mapenv.M_SLOT, mapenv.M_CLASS):
                self.parts[(e.name, e.number)] = e.addr
            else:
                self.items[e.name] = e.addr
        self.program = program

    def __call__(self, m, fx):
        s = m.symbols[fx.sym]
        if fx.slot == lo.NO_SLOT:
            a = self.items.get(s.name)
        else:
            a = self.parts.get((s.name, fx.slot))
        if a is None:
            what = s.name if fx.slot == lo.NO_SLOT else f'{s.name} slot {fx.slot}'
            raise RenderError(f'{m.name}: {what} is not in the map')
        return a


def render_program(modules, entries, env, main_module=None):
    """Program mode: one asm17 source. modules in link order; entries from the map."""
    program = Program(modules)
    r = Renderer(program)
    addr = Addresses(entries, program)
    if main_module is None:
        main_module = modules[-1].name if modules else 'main'
    main = f'{main_module}.main'
    code_start = env.code[0]
    if code_start < 0x100:
        raise RenderError('code must start at $0100 or above')

    equates = ['; slots, variables and class parameters, from the map']
    for e in entries:
        if e.kind == mapenv.M_SLOT:
            f = program.func(e.name)
            if f is not None and e.number < len(f.slots):
                label = slot_label(e.name, f.slots[e.number].name)
            else:
                label = slot_label(e.name, e.part)
            equates.append(f'{label} = ${e.addr:04X}')
        elif e.kind == mapenv.M_CLASS:
            equates.append(f'{param_label(e.name, e.number)} = ${e.addr:04X}')
        elif e.kind == mapenv.M_VAR:
            equates.append(f'{mangle(e.name)} = ${e.addr:04X}')

    placed = []                    # (address, size, lines)
    start_defined = program.func(env.start) is not None
    funcs = [e for e in entries if e.kind == mapenv.M_FUNC]
    for a, b in zip(funcs, funcs[1:]):
        if b.addr < a.addr:
            raise RenderError(f'map: {b.name} is placed below {a.name}')
    for e in funcs:
        d = program.defs.get(e.name)
        if d is None:
            if e.name == env.start and not start_defined:
                lines, size = startup_lines(env.start, main), STARTUP_SIZE
                r.equates[f'abs_{HOST_EXIT:04x}'] = HOST_EXIT
            else:
                raise RenderError(f'map lists function {e.name}, which no object defines')
        else:
            m, f = d
            lines = r.function(m, f)
            size = final_size(m, f, addr)
        if size != e.size:
            raise RenderError(f'map gives {e.name} size ${e.size:04X}, the rule gives ${size:04X}')
        placed.append((e.addr, size, lines))
    for e in entries:
        if e.kind not in (mapenv.M_DATA, mapenv.M_VAR):
            continue
        d = program.defs.get(e.name)
        if d is None:
            raise RenderError(f'map lists {e.name}, which no object defines')
        m, x = d
        if e.kind == mapenv.M_DATA:
            if len(x.data) != e.size:
                raise RenderError(f'map gives {e.name} size ${e.size:04X}, it has ${len(x.data):04X}')
            placed.append((e.addr, e.size, [f'; data {e.name}: {e.size} bytes', mangle(e.name)]
                           + r.data_lines(m, x.data, x.fixes)))
        elif x.init is not None:
            if e.addr < code_start:
                raise RenderError(f'initialised variable {e.name} is at ${e.addr:04X}, '
                                  f'below the image (code starts at ${code_start:04X})')
            placed.append((e.addr, e.size, [var_comment(m, x) + f', at ${e.addr:04X}']
                           + r.data_lines(m, x.init, x.fixes)))
    if not start_defined and not any(e.name == env.start for e in funcs):
        raise RenderError(f'no object defines {env.start} and the map does not place it')

    placed.sort(key=lambda p: p[0])
    out = [f'; program for {os.path.basename(env.path) or "environment"}: '
           + ', '.join(m.name for m in modules),
           f'* = ${code_start:04X}', '']
    body = []
    pc = code_start
    for a, size, lines in placed:
        if a < pc:
            raise RenderError(f'map: item at ${a:04X} overlaps the one before it (ends at ${pc:04X})')
        body.append('')
        if a != pc:
            body.append(f'* = ${a:04X}')
        body += lines
        pc = a + size
    if pc > 0xFFFC:
        raise RenderError(f'the program reaches ${pc:04X}, over the reset vector')
    body += ['', '; vectors: reset to the start function; no interrupt handler',
             '* = $FFFC', f'{INDENT}.word {mangle(env.start)}', f'{INDENT}.word $0000']
    eq = r.equate_lines()
    if eq:
        equates += ['', '; literal addresses'] + eq
    return '\n'.join(out + equates + body) + '\n'


def main(argv):
    ap = argparse.ArgumentParser(prog='lo2asm.py', description='Render Lathe objects as asm17 text.')
    ap.add_argument('objects', nargs='+')
    ap.add_argument('--map')
    ap.add_argument('--env')
    ap.add_argument('--main', help='module whose main the start-up code calls (default: the last object)')
    ap.add_argument('-o', dest='out')
    a = ap.parse_args(argv)
    try:
        modules = [lo.load(p) for p in a.objects]
        if a.map or a.env:
            if not (a.map and a.env and a.out):
                ap.error('program mode needs --map, --env and -o')
            text = render_program(modules, mapenv.read_map(a.map), mapenv.read_env(a.env), a.main)
        else:
            if len(modules) != 1:
                ap.error('module mode takes one object (program mode needs --map and --env)')
            text = render_module(modules[0])
    except (lo.LoError, RenderError, mapenv.FormatError, OSError) as e:
        sys.stderr.write(f'lo2asm: {e}\n')
        return 1
    if a.out:
        with open(a.out, 'w') as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
