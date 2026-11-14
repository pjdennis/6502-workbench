#!/usr/bin/env python3
"""Render Lathe object files as asm17 text (lathe/docs/object-format.md, "Rendering as assembler text").

    lo2asm.py FILE.lo [-o OUT.asm]
        Module mode: one module, no addresses. The text the snapshot tests compare.

    lo2asm.py --map OUT.map --env ENV --main MODULE -o OUT.asm A.lo B.lo ...
        Program mode: one asm17 source for the whole program. Assembled (asm/pyasm.py or asm17)
        it gives the file the linker gives: for `output image`, code start to $FFFF with the
        reset vector at $FFFC; for `output raw`, code start to the last byte placed and no
        vectors (pyasm's output runs from the lowest address written to the highest).
        $start and $init are written as the linker makes them (object-format.md, "Initial
        values and start-up"), labelled Sstart and Sinit. Each copy of a function that the
        map lists (mod.f, mod.f@1, ...) is rendered as a function of its own, label mod__fX401,
        whose references resolve to the copies of its own context (class Copies).

Names: symbol mod.name is label mod__name; slot s of mod.f is mod__f__s; parameter n of class
mod.c is mod__c__name, its name in the CLAS records, or mod__c__pN where they give it none; a
label inside a function is .L
and its written offset in four hex digits. Characters asm17 does not allow in a name ($ in
compiler-made names such as hello.$1) are written S, or X and two hex digits; names are lower
case, so these cannot collide with a user's name. Literal memory operands are written through
equates (abs_f009 = $F009, zp_12 = $12) because asm17 forces a literal to absolute after a
forward reference; an absolute instruction whose literal operand is below $100 (which asm17
would shrink) is written as .byte with the instruction in a comment.

asm17 has no 65C02 mnemonics, so an instruction the NMOS 6502 does not have (STP, WAI; and the
STP that `exit stop` puts at the end of $start) is written the same way: .byte and its opcode,
the mnemonic in a comment. Only one-byte instructions can be written so far: one with an operand
would need its fix-up or branch written as an expression, and lo2asm refuses it.
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
START = '$start'      # the start-up function the linker makes (object-format.md, "Initial values and start-up")
INIT = '$init'        # the function that calls every module.$init


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


def param_label(class_name, n, name=''):
    """The label of parameter n of a class, called `name` in its CLAS records, or nothing."""
    return f'{mangle(class_name)}__{name or f"p{n}"}'


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
    """True if the instruction takes its zero page form: its fix-up is of kind 5 (lo.read has
    checked that the instruction has such a form) and its address is in zero page."""
    if x.fix is None or x.fix.kind != lo.FX_SHRINK:
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
        self.param_names = {}      # class name -> the names of its parameters ('' if none)
        for m in modules:
            for x in m.items:
                if isinstance(x, (lo.Func, lo.Var, lo.Data)):
                    self.defs.setdefault(m.sym_name(x.sym), (m, x))
                elif isinstance(x, lo.Clas):
                    # The first name a CLAS record gives a parameter is its name (lk_scan).
                    names = self.param_names.setdefault(m.sym_name(x.sym), list(x.names))
                    for i, n in enumerate(x.names):
                        if i < len(names) and not names[i]:
                            names[i] = n

    def param_label(self, class_name, n):
        names = self.param_names.get(class_name, [])
        return param_label(class_name, n, names[n] if n < len(names) else '')

    def func(self, name):
        d = self.defs.get(name)
        return d[1] if d and isinstance(d[1], lo.Func) else None


class Copies:
    """The function copies a map lists, and which copy each reference means, by the linker's
    rules (code-model.md, "Interrupts"; lathe/host/lk_fix.py, target):

    - A call (JSR or JMP absolute) goes to the callee's copy in the caller's own context.
    - A slot of a function that has a copy in the referring copy's context is that copy's slot.
    - Any other reference to a function, and every reference from constant data, means the copy
      its address stands for: the one in the context that calls through the function's pointer
      class, or else its first copy (the lowest context that has it).
    - Variables, constant data and class parameters exist once and are never copied.
    """

    def __init__(self, funcs, program):
        self.names = {}            # function -> {context: name of its copy in the map}
        for e in funcs:
            self.names.setdefault(e.base(), {})[e.context] = e.name
        # Classes that share a member are one class; a class is live in the contexts whose
        # kept functions call through it.
        self.rep = {}
        self.member_of = {}
        for m in program.modules:
            for x in m.of_type(lo.Memb):
                k, f = self.find(m.sym_name(x.cls)), m.sym_name(x.func)
                if f in self.member_of:
                    other = self.find(self.member_of[f])
                    if other != k:
                        self.rep[other] = k
                else:
                    self.member_of[f] = k
        self.live = {}
        for base, copies in self.names.items():
            d = program.defs.get(base)
            if d is None or not isinstance(d[1], lo.Func):
                continue
            m, f = d
            for c in f.calls:
                if c.flags & lo.C_POINTER:
                    self.live.setdefault(self.find(m.sym_name(c.callee)), set()).update(copies)

    def find(self, k):
        while self.rep.get(k, k) != k:
            k = self.rep[k]
        return k

    def in_context(self, name, ctx):
        """The copy of function `name` for context ctx, or None."""
        return self.names.get(name, {}).get(ctx)

    def address_copy(self, name):
        """The copy that @name means, or None if the function was not kept."""
        copies = self.names.get(name)
        if not copies:
            return None
        k = self.member_of.get(name)
        ctxs = self.live.get(self.find(k)) if k is not None else None
        if ctxs and len(ctxs) == 1 and min(ctxs) in copies:
            return copies[min(ctxs)]
        return copies[min(copies)]


# Renderer.ref says what a fix-up stands for: ('label', offset), ('item', name),
# ('slot', function or copy, number, slot name or None) or ('param', class, number).

class Renderer:
    def __init__(self, program, copies=None):
        self.program = program
        self.copies = copies       # program mode: a Copies; module mode: None
        self.equates = {}          # name -> value, for literal operands

    def slot_name(self, m, fn, number):
        f = self.program.func(fn)
        if f is None:
            return None
        if number >= len(f.slots):
            raise RenderError(f'{m.name}: fix-up names slot {number} of {fn}, '
                              f'which has {len(f.slots)} slots')
        return f.slots[number].name

    def ref(self, m, fx, current, ctx=None, call=False):
        """What fix-up fx of module m stands for, seen from function `current` (None for
        constant data) in context ctx; `call` says the instruction is a JSR or JMP absolute."""
        s = m.symbols[fx.sym]
        if s.kind == lo.K_FUNC and fx.slot == lo.NO_SLOT:
            # A function's fix-up to itself is a label, except a one-byte part of its own
            # address, which like any @f may mean another context's copy.
            own = current is not None and fx.sym == current.sym
            if own and (self.copies is None or lo.FIX_WIDTH[fx.kind] == 2 or fx.addend != 0):
                return ('label', fx.addend)
            return ('item', self.copy_of(m, s.name, ctx, call))
        if s.kind == lo.K_FUNC:
            copy = s.name
            if self.copies is not None:
                copy = (self.copies.in_context(s.name, ctx) if ctx is not None else None) \
                    or self.copies.address_copy(s.name)
                if copy is None:
                    raise RenderError(f'{m.name}: {s.name} slot {fx.slot} is not in the map')
            return ('slot', copy, fx.slot, self.slot_name(m, s.name, fx.slot))
        if s.kind == lo.K_CLASS:
            return ('param', s.name, fx.slot)
        return ('item', s.name)

    def copy_of(self, m, name, ctx, call):
        """The copy of function `name` that a reference to its entry means."""
        if self.copies is None:
            return name
        if call and ctx is not None:
            copy = self.copies.in_context(name, ctx)
            if copy is None:
                raise RenderError(f'{m.name}: call of {name}, which has no copy for context {ctx}')
            return copy
        copy = self.copies.address_copy(name)
        if copy is None:
            raise RenderError(f'{m.name}: {name} is not in the map')
        return copy

    def target_text(self, m, fx, current, ctx=None, call=False):
        r = self.ref(m, fx, current, ctx, call)
        if r[0] == 'label':
            return local_label(r[1])
        if r[0] == 'slot':
            _, copy, number, name = r
            text = slot_label(copy, name) if name is not None else f'{mangle(copy)}__{number}'
            return with_addend(text, fx.addend)
        if r[0] == 'param':
            return with_addend(self.program.param_label(r[1], r[2]), fx.addend)
        return with_addend(mangle(r[1]), fx.addend)

    def literal(self, value, width):
        name = f'abs_{value:04x}' if width == 2 else f'zp_{value:02x}'
        self.equates[name] = value
        return name

    def instruction(self, m, x, current, ctx=None):
        mn, mode = x.mnemonic, x.mode
        if not asm17_has(mn, mode):
            if x.length != 1:
                raise RenderError(f'{m.name}: function {m.sym_name(current.sym)}: {mn} at '
                                  f'${x.offset:04X}: asm17 has no 65C02 instructions, and only '
                                  f'one-byte ones can be written as .byte')
            return byte_line(current.code[x.offset:x.offset + 1], mn)
        if mode == cpu6502.IMP:
            return f'{INDENT}{mn}'
        if mode == cpu6502.REL:
            return f'{INDENT}{mn} {local_label(x.target)}'
        width = x.length - 1
        if x.fix is not None:
            e = self.target_text(m, x.fix, current, ctx, is_call(x))
            if x.fix.kind == lo.FX_LO:
                e = '<' + e
            elif x.fix.kind == lo.FX_HI:
                e = '>' + e
        elif mode == cpu6502.IMM:
            return f'{INDENT}{mn} #${x.operand:02X}'
        elif width == 2 and x.operand < 0x100 and cpu6502.shrinks(m.cpu, mn, mode):
            return byte_line(current.code[x.offset:x.offset + 3],
                             f'{mn} {_mode_text(mode, f"${x.operand:04X}")}')
        else:
            e = self.literal(x.operand, width)
        if mode == cpu6502.IMM:
            return f'{INDENT}{mn} #{e}'
        return f'{INDENT}{mn} {_mode_text(mode, e)}'

    def function(self, m, f, comment=True, copy=None, ctx=None):
        """The text of function f; in program mode, of its copy named `copy`, for context ctx."""
        lines = []
        name = m.sym_name(f.sym)
        if comment:
            lines += function_comment(m, f)
            if copy is not None and ctx:
                lines.append(f';   this copy is for context {ctx}')
        ins, labels = decode_function(m, f)
        lines.append(mangle(copy or name))
        for x in ins:
            if x.offset in labels:
                lines.append(local_label(x.offset))
            lines.append(self.instruction(m, x, f, ctx))
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


def asm17_has(mnemonic, mode):
    """True if asm17 can write this instruction: the NMOS 6502 has it."""
    return mode in cpu6502.NMOS.get(mnemonic, {})


def byte_line(data, comment):
    """Bytes written as .byte, with what they are in a comment."""
    line = f'{INDENT}.byte ' + ', '.join(f'${b:02X}' for b in data)
    return f'{line:<31} ; {comment}'


def is_call(x):
    """A JSR or JMP absolute: the linker sends it to the callee's copy in the caller's context."""
    return x.mode == cpu6502.ABS and x.mnemonic in ('JSR', 'JMP')


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
    return (f'; variable {m.sym_name(v.sym)}: size {v.size}, class {v.cls} ({CLASS_NAMES[v.cls]}), '
            f'weight {v.weight}')


def render_module(m, others=()):
    """Module mode: the text for one module (others: objects to look up foreign slot names in)."""
    r = Renderer(Program([m] + list(others)))
    body = []
    for x in m.items:
        if isinstance(x, lo.Wgt):
            continue                # weights are for the linker's choice of zero page
        body.append('')
        if isinstance(x, lo.Func):
            body += r.function(m, x)
        elif isinstance(x, lo.Var):
            body.append(var_comment(m, x))
        elif isinstance(x, lo.Data):
            body.append(f'; data {m.sym_name(x.sym)}: {len(x.data)} bytes')
            body.append(mangle(m.sym_name(x.sym)))
            body += r.data_lines(m, x.data, x.fixes)
        elif isinstance(x, lo.Clas):
            rec = '; recursive' if x.flags & lo.CLAS_RECURSIVE else ''
            if any(x.names):
                params = ', '.join(f'{n or "p%d" % i} ({p})' for i, (p, n) in enumerate(zip(x.params, x.names)))
                body.append(f'; class {m.sym_name(x.sym)}: parameters {params}{rec}')
            else:
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

def init_functions(program, modules):
    """The module.$init functions, in object order."""
    return [f'{m.name}.{INIT}' for m in modules if program.func(f'{m.name}.{INIT}') is not None]


def start_function(env, has_init, main, r):
    """$start as object-format.md's table gives it for env: (lines, size)."""
    lines = [f'; {START}: start-up code for {os.path.basename(env.path) or "the environment"}',
             mangle(START)]
    size = 0

    def ins(text, n):
        nonlocal size
        lines.append(INDENT + text)
        size += n
    if env.stack is not None:
        ins(f'LDX #${env.stack:02X}', 2)
        ins('TXS', 1)
    ins('CLD', 1)
    if has_init:
        ins(f'JSR {mangle(INIT)}', 3)
    ins(f'JSR {mangle(main)}', 3)
    kind, addr = env.exit
    if kind == mapenv.EXIT_CALL:
        ins('LDA #$00', 2)
        ins(f'JMP {r.literal(addr, 2)}', 3)
    elif kind == mapenv.EXIT_LOOP:
        lines.append(local_label(size))
        ins(f'JMP {local_label(size)}', 3)
    elif kind == mapenv.EXIT_STOP:
        lines.append(byte_line(b'\xDB', 'STP'))
        size += 1
    else:
        ins('RTS', 1)
    return lines, size


def init_function(inits):
    """$init: a JSR to each module.$init, then RTS: (lines, size)."""
    lines = [f'; {INIT}: calls the initial-value code of each module', mangle(INIT)]
    lines += [f'{INDENT}JSR {mangle(f)}' for f in inits] + [f'{INDENT}RTS']
    return lines, 3 * len(inits) + 1


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

    def in_copy(self, renderer, ctx, current):
        """A resolver for final_size: addresses as the copy of `current` for context ctx sees
        them. Code is never in zero page, so a function's entry resolves to None."""
        def resolve(m, fx):
            r = renderer.ref(m, fx, current, ctx)
            if r[0] == 'label' or (r[0] == 'item' and m.symbols[fx.sym].kind == lo.K_FUNC):
                return None
            if r[0] == 'item':
                a, what = self.items.get(r[1]), r[1]
            else:
                a, what = self.parts.get((r[1], r[2])), f'{r[1]} slot {r[2]}'
            if a is None:
                raise RenderError(f'{m.name}: {what} is not in the map')
            return a
        return resolve

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


def render_program(modules, entries, env, main_module):
    """Program mode: one asm17 source. modules in link order; entries from the map."""
    program = Program(modules)
    funcs = [e for e in entries if e.kind == mapenv.M_FUNC]
    r = Renderer(program, Copies([e for e in funcs if e.name not in (START, INIT)], program))
    addr = Addresses(entries, program)
    main = f'{main_module}.main'
    code_start = env.code[0]
    if code_start < 0x100:
        raise RenderError('code must start at $0100 or above')
    if program.func(main) is None:
        raise RenderError(f'no object defines {main}')
    inits = init_functions(program, modules)

    equates = ['; slots and variables, from the map']
    for e in entries:
        if e.kind == mapenv.M_SLOT:
            f = program.func(e.base())
            if f is not None and e.number < len(f.slots):
                label = slot_label(e.name, f.slots[e.number].name)
            else:
                label = slot_label(e.name, e.part)
            equates.append(f'{label} = ${e.addr:04X}')
        elif e.kind == mapenv.M_CLASS:
            equates.append(f'{program.param_label(e.name, e.number)} = ${e.addr:04X}')
        elif e.kind == mapenv.M_VAR:
            equates.append(f'{mangle(e.name)} = ${e.addr:04X}')

    names = [e.name for e in funcs]
    if START not in names:
        raise RenderError(f'the map does not place {START}')
    start = funcs[names.index(START)]
    if start.addr != code_start:
        raise RenderError(f'{START} must be first in the code range (${code_start:04X}), '
                          f'the map has it at ${start.addr:04X}')
    if inits and INIT not in names:
        raise RenderError(f'{inits[0]} is defined, but the map has no {INIT}')
    if INIT in names and not inits:
        raise RenderError(f'map lists {INIT}, but no object defines a MODULE.{INIT}')
    for f in inits:
        if f not in names:
            raise RenderError(f'{f} is not in the map: every MODULE.{INIT} is kept')
    for a, b in zip(funcs, funcs[1:]):
        if b.addr < a.addr:
            raise RenderError(f'map: {b.name} is placed below {a.name}')

    placed = []                    # (address, size, lines)
    for e in funcs:
        if e.name == START:
            lines, size = start_function(env, bool(inits), main, r)
        elif e.name == INIT:
            if e.addr != start.addr + start.size:
                raise RenderError(f'{INIT} must follow {START} (at ${start.addr + start.size:04X}), '
                                  f'the map has it at ${e.addr:04X}')
            lines, size = init_function(inits)
        else:
            d = program.defs.get(e.base())
            if d is None or not isinstance(d[1], lo.Func):
                raise RenderError(f'map lists function {e.name}, which no object defines')
            m, f = d
            lines = r.function(m, f, copy=e.name, ctx=e.context)
            size = final_size(m, f, addr.in_copy(r, e.context, f))
        if size != e.size:
            raise RenderError(f'map gives {e.name} size ${e.size:04X}, the rule gives ${size:04X}')
        placed.append((e.addr, size, lines))
    for e in entries:
        if e.kind != mapenv.M_DATA:
            continue
        d = program.defs.get(e.name)
        if d is None or not isinstance(d[1], lo.Data):
            raise RenderError(f'map lists data {e.name}, which no object defines')
        m, x = d
        if len(x.data) != e.size:
            raise RenderError(f'map gives {e.name} size ${e.size:04X}, it has ${len(x.data):04X}')
        placed.append((e.addr, e.size, [f'; data {e.name}: {e.size} bytes', mangle(e.name)]
                       + r.data_lines(m, x.data, x.fixes)))

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
    if env.output == mapenv.OUTPUT_IMAGE:
        if pc > 0xFFFC:
            raise RenderError(f'the program reaches ${pc:04X}, over the reset vector')
        body += ['', f'; vectors: reset to {START}; no interrupt handler',
                 '* = $FFFC', f'{INDENT}.word {mangle(START)}', f'{INDENT}.word $0000']
    else:
        body += ['', '; output raw: the file ends here, with no vectors']
    eq = r.equate_lines()
    if eq:
        equates += ['', '; literal addresses'] + eq
    return '\n'.join(out + equates + body) + '\n'


def main(argv):
    ap = argparse.ArgumentParser(prog='lo2asm.py', description='Render Lathe objects as asm17 text.')
    ap.add_argument('objects', nargs='+')
    ap.add_argument('--map')
    ap.add_argument('--env')
    ap.add_argument('--main', help='program mode: the module whose main $start calls')
    ap.add_argument('-o', dest='out')
    a = ap.parse_args(argv)
    try:
        modules = [lo.load(p) for p in a.objects]
        if a.map or a.env:
            if not (a.map and a.env and a.main and a.out):
                ap.error('program mode needs --map, --env, --main and -o')
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
