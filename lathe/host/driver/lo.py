"""Read, write and build Lathe object files (lathe/docs/object-format.md, version 2).

    m = lo.load('hello.lo')          # -> Module; raises LoError with file and offset on bad input
    data = lo.write(m)               # -> bytes

    b = lo.Builder('hello')          # a convenient way to make a module, for tests and tools
    b.imp('host')
    f = b.func('hello.main')
    f.op('LDA', '#', 0x48)
    f.op('JSR', 'abs', 0xF009)       # literal operand: no fix-up
    f.op('RTS')
    b.save('hello.lo')

Operands for Builder ops: an int (a literal), a symbol name, (function name, slot name or
number), (class name, parameter number), or a label name of the function being built (for
branches, and for JMP/JSR/immediates, which then get a fix-up to the function itself with the
label's offset as the addend). Mode '#<' and '#>' are immediates with kind 2 / 3 fix-ups. A
two-byte operand gets kind 5 if the instruction has a zero page form and kind 1 if not.
"""
import struct
from dataclasses import dataclass, field
from typing import List

import cpu6502

VERSION = 2

R_END, R_MOD, R_IMP, R_SYM, R_VAR, R_DATA, R_DFIX, R_FUNC, R_SLOT, R_CALL, R_FIX, R_CODE, R_ENDF, \
    R_CLAS, R_MEMB, R_WGT = range(16)
RECORD_NAMES = {R_END: 'END', R_MOD: 'MOD', R_IMP: 'IMP', R_SYM: 'SYM', R_VAR: 'VAR', R_DATA: 'DATA',
                R_DFIX: 'DFIX', R_FUNC: 'FUNC', R_SLOT: 'SLOT', R_CALL: 'CALL', R_FIX: 'FIX',
                R_CODE: 'CODE', R_ENDF: 'ENDF', R_CLAS: 'CLAS', R_MEMB: 'MEMB', R_WGT: 'WGT'}

K_FUNC, K_VAR, K_DATA, K_CLASS = 1, 2, 3, 4
KIND_NAMES = {K_FUNC: 'function', K_VAR: 'variable', K_DATA: 'constant data', K_CLASS: 'pointer class'}

FX_WORD, FX_LO, FX_HI, FX_ZP, FX_SHRINK = 1, 2, 3, 4, 5
FIX_WIDTH = {FX_WORD: 2, FX_LO: 1, FX_HI: 1, FX_ZP: 1, FX_SHRINK: 2}

SK_PARAM, SK_LOCAL, SK_TEMP = 0, 1, 2
SLOT_KIND_NAMES = {SK_PARAM: 'param', SK_LOCAL: 'local', SK_TEMP: 'temp'}

F_RECURSIVE, F_INTERRUPT, F_EXPORTED, F_REGISTERS = 1, 2, 4, 8
FUNC_FLAG_NAMES = ((F_RECURSIVE, 'recursive'), (F_INTERRUPT, 'interrupt'), (F_EXPORTED, 'exported'),
                   (F_REGISTERS, 'registers'))
C_SAVES, C_POINTER = 1, 2
CLAS_RECURSIVE = 1
VAR_OLD_INIT = 1       # flag bit 0 meant "initial value follows" before initial values moved to code

NO_SLOT = 0xFF
NO_OUTER = 0xFFFF


class LoError(Exception):
    pass


@dataclass
class Symbol:
    kind: int
    name: str


@dataclass
class Fix:
    offset: int
    kind: int
    sym: int
    slot: int = NO_SLOT
    addend: int = 0


@dataclass
class Slot:
    size: int
    cls: int
    weight: int
    kind: int
    name: str


@dataclass
class Call:
    callee: int
    flags: int = 0
    outer: int = NO_OUTER


@dataclass
class Func:
    sym: int
    flags: int = 0
    slots: List[Slot] = field(default_factory=list)
    calls: List[Call] = field(default_factory=list)
    fixes: List[Fix] = field(default_factory=list)
    code: bytes = b''


@dataclass
class Var:
    """Storage only: a variable has no initial value in the object file (module.$init sets it)."""
    sym: int
    size: int
    cls: int = 1
    weight: int = 0
    flags: int = 0


@dataclass
class Data:
    sym: int
    data: bytes
    fixes: List[Fix] = field(default_factory=list)


@dataclass
class Clas:
    sym: int
    flags: int
    params: List[int]                       # the size of each parameter
    names: List[str] = None                 # the name of each ('' if not known); None: all ''

    def __post_init__(self):
        if self.names is None:
            self.names = [''] * len(self.params)
        if len(self.names) != len(self.params):
            raise LoError('a class needs one name for each parameter')


@dataclass
class Weight:
    """Weight a module adds to a variable it does not define (slot $FF), or to a slot of a
    function or a parameter of a class."""
    sym: int
    slot: int
    weight: int


@dataclass
class Wgt:
    entries: List[Weight] = field(default_factory=list)


@dataclass
class Memb:
    cls: int
    func: int


@dataclass
class Module:
    name: str
    cpu: int = 0
    version: int = VERSION
    imports: List[str] = field(default_factory=list)
    symbols: List[Symbol] = field(default_factory=list)
    items: list = field(default_factory=list)      # Func, Var, Data, Clas, Memb, Wgt in file order

    def sym_name(self, i):
        return self.symbols[i].name

    def sym_index(self, name):
        for i, s in enumerate(self.symbols):
            if s.name == name:
                return i
        raise KeyError(name)

    def of_type(self, t):
        return [x for x in self.items if isinstance(x, t)]

    def functions(self):
        return self.of_type(Func)

    def definition(self, i):
        """The Func, Var, Data or Clas that defines symbol i here, or None."""
        for x in self.items:
            if not isinstance(x, (Memb, Wgt)) and x.sym == i:
                return x
        return None


# ---------------------------------------------------------------------------------------------
# Reading

class _Reader:
    def __init__(self, data, filename):
        self.data = bytes(data)
        self.filename = filename
        self.pos = 0           # start of the record being decoded, for messages

    def fail(self, message):
        raise LoError(f'{self.filename}: offset ${self.pos:04X}: {message}')


class _Body:
    def __init__(self, reader, rtype, body):
        self.r = reader
        self.name = RECORD_NAMES[rtype]
        self.b = body
        self.i = 0

    def take(self, n):
        if self.i + n > len(self.b):
            self.r.fail(f'{self.name} record too short')
        v = self.b[self.i:self.i + n]
        self.i += n
        return v

    def u8(self):
        return self.take(1)[0]

    def u16(self):
        return struct.unpack('<H', self.take(2))[0]

    def string(self):
        n = self.u8()
        if self.i + n > len(self.b):
            self.r.fail(f'string runs past the end of the {self.name} record')
        return self.take(n).decode('latin-1')

    def rest(self):
        v = self.b[self.i:]
        self.i = len(self.b)
        return v

    def done(self):
        if self.i != len(self.b):
            self.r.fail(f'{self.name} record has {len(self.b) - self.i} unexpected bytes at its end')


def _fix_entries(body, r):
    raw = body.rest()
    if len(raw) % 8:
        r.fail(f'{body.name} body length {len(raw)} is not a multiple of 8')
    out = []
    for i in range(0, len(raw), 8):
        off, kind, sym, slot, addend = struct.unpack('<HBHBH', raw[i:i + 8])
        out.append(Fix(off, kind, sym, slot, addend))
    for a, b in zip(out, out[1:]):
        if b.offset <= a.offset:
            r.fail(f'{body.name}: fix-ups not sorted by offset (${b.offset:04X} after ${a.offset:04X})')
    return out


def read(data, filename='<object>'):
    """Decode and validate an object file. Returns a Module."""
    r = _Reader(data, filename)
    d = r.data
    m = None
    defined = {}                  # symbol -> description of where
    func = None                   # Func being read
    func_stage = 0                # 0 after FUNC, 1 SLOT, 2 CALL, 3 FIX, 4 CODE
    dfix = None                   # the fix-ups of a DFIX record, for the DATA record after it
    pending = []                  # (Fix, owner description, pos) checked at END
    ended = False

    def sym_ref(i, what, kinds=None):
        if i >= len(m.symbols):
            r.fail(f'{what}: symbol {i} has no SYM record (not defined yet)')
        s = m.symbols[i]
        if kinds is not None and s.kind not in kinds:
            r.fail(f'{what} names symbol {i} ({s.name}), which is a {KIND_NAMES[s.kind]}')
        return s

    def define(i, what, kind):
        sym_ref(i, what, (kind,))
        if i in defined:
            r.fail(f'symbol {i} ({m.symbols[i].name}) defined twice')
        defined[i] = what

    def check_fixes(fixes, size, what, code=None):
        """code: the function's code, to check kinds 1 and 5 against; None for constant data."""
        for x in fixes:
            if x.kind not in FIX_WIDTH:
                r.fail(f'{what}: unknown fix-up kind {x.kind}')
            if x.offset + FIX_WIDTH[x.kind] > size:
                r.fail(f'{what}: fix-up at offset ${x.offset:04X} runs past the end of the code or data')
            if x.kind == FX_SHRINK and code is None:
                r.fail(f'{what}: fix-up kind 5 at offset ${x.offset:04X} in constant data')
            if x.kind in (FX_WORD, FX_SHRINK) and code is not None and x.offset > 0:
                entry = cpu6502.decode_table(m.cpu).get(code[x.offset - 1])
                if entry is not None:
                    has_zp = cpu6502.shrinks(m.cpu, entry[0], entry[1]) is not None
                    if has_zp and x.kind == FX_WORD:
                        r.fail(f'{what}: fix-up kind 1 at offset ${x.offset:04X} on {entry[0]} {entry[1]}, '
                               f'which has a zero page form: it takes kind 5')
                    if not has_zp and x.kind == FX_SHRINK:
                        r.fail(f'{what}: fix-up kind 5 at offset ${x.offset:04X} on {entry[0]} {entry[1]}, '
                               f'which has no zero page form: it takes kind 1')
            s = sym_ref(x.sym, f'{what}: fix-up at ${x.offset:04X}')
            if s.kind in (K_VAR, K_DATA) and x.slot != NO_SLOT:
                r.fail(f'{what}: fix-up names slot {x.slot} of {s.name}, a {KIND_NAMES[s.kind]}')
            if s.kind == K_CLASS and x.slot == NO_SLOT:
                r.fail(f'{what}: fix-up names class {s.name} without a parameter (slot $FF): '
                       f'a class needs a parameter')
            pending.append((x, what, r.pos))

    while r.pos < len(d):
        if ended:
            r.fail('data after the END record')
        if r.pos + 3 > len(d):
            r.fail('record header truncated')
        rtype = d[r.pos]
        length = struct.unpack('<H', d[r.pos + 1:r.pos + 3])[0]
        if r.pos + 3 + length > len(d):
            r.fail(f'record body truncated ({length} bytes declared)')
        if rtype not in RECORD_NAMES:
            r.fail(f'unknown record type ${rtype:02X}')
        body = _Body(r, rtype, d[r.pos + 3:r.pos + 3 + length])
        name = RECORD_NAMES[rtype]

        if m is None:
            if rtype != R_MOD:
                r.fail(f'first record must be MOD, not {name}')
            version = body.u8()
            if version != VERSION:
                r.fail(f'unsupported object format version {version}: this reader takes version '
                       f'{VERSION} only; compile the module again')
            cpu = body.u8()
            if cpu not in (cpu6502.CPU_6502, cpu6502.CPU_65C02):
                r.fail(f'unknown CPU {cpu}')
            m = Module(body.string(), cpu, version)
            body.done()
            r.pos += 3 + length
            continue

        if dfix is not None and rtype != R_DATA:
            r.fail('DFIX record not just before a DATA record')
        if func is not None:
            order = {R_SLOT: 1, R_CALL: 2, R_FIX: 3, R_CODE: 4}
            if rtype in order:
                stage = order[rtype]
                if stage < func_stage or (stage == func_stage and stage >= 3):
                    after = {1: 'SLOT', 2: 'CALL', 3: 'FIX', 4: 'CODE'}[func_stage]
                    r.fail(f'{name} record after {after} in function {m.sym_name(func.sym)}')
                func_stage = stage
                if rtype == R_SLOT:
                    s = Slot(body.u16(), body.u8(), body.u8(), body.u8(), body.string())
                    n = len(func.slots)
                    if s.cls > 2:
                        r.fail(f'slot {n} ({s.name}) has class {s.cls}')
                    if s.kind not in SLOT_KIND_NAMES:
                        r.fail(f'slot {n} ({s.name}) has kind {s.kind}')
                    if s.kind == SK_PARAM and func.slots and func.slots[-1].kind != SK_PARAM:
                        r.fail(f'slot {n} ({s.name}) is a parameter after a local or temporary')
                    if n >= NO_SLOT:
                        r.fail('more than 255 slots')
                    func.slots.append(s)
                elif rtype == R_CALL:
                    c = Call(body.u16(), body.u8(), body.u16())
                    what = f'CALL in {m.sym_name(func.sym)}'
                    sym_ref(c.callee, what, (K_CLASS,) if c.flags & C_POINTER else (K_FUNC,))
                    if c.outer != NO_OUTER:
                        sym_ref(c.outer, what + ' (outer)', (K_FUNC, K_CLASS))
                    func.calls.append(c)
                elif rtype == R_FIX:
                    func.fixes = _fix_entries(body, r)
                else:
                    func.code = body.rest()
                    check_fixes(func.fixes, len(func.code), f'function {m.sym_name(func.sym)}', func.code)
                body.done()
            elif rtype == R_ENDF:
                if length:
                    r.fail(f'ENDF record has body length {length}, expected 0')
                if func_stage < 4:
                    r.fail(f'function {m.sym_name(func.sym)} has no CODE record')
                m.items.append(func)
                func = None
            else:
                r.fail(f'function {m.sym_name(func.sym)} not closed by ENDF (found {name})')
            r.pos += 3 + length
            continue

        if rtype == R_IMP:
            m.imports.append(body.string())
        elif rtype == R_SYM:
            kind = body.u8()
            sname = body.string()
            if kind not in KIND_NAMES:
                r.fail(f'unknown symbol kind {kind} for {sname}')
            if any(s.name == sname for s in m.symbols):
                r.fail(f'second SYM record for {sname}')
            m.symbols.append(Symbol(kind, sname))
        elif rtype == R_VAR:
            v = Var(body.u16(), body.u16(), body.u8(), body.u8(), body.u8())
            define(v.sym, 'VAR', K_VAR)
            vname = m.sym_name(v.sym)
            if v.cls > 2:
                r.fail(f'VAR {vname} has class {v.cls}')
            if v.flags & VAR_OLD_INIT:
                r.fail(f'VAR {vname}: flag bit 0 (initial value) is not in format version {VERSION}: '
                       f'variables have no initial values; the compiler sets them in module.$init')
            if v.flags:
                r.fail(f'VAR {vname}: unknown flags ${v.flags:02X}')
            m.items.append(v)
        elif rtype == R_DATA:
            x = Data(body.u16(), b'')
            define(x.sym, 'DATA', K_DATA)
            x.data = body.rest()
            if dfix is not None:
                x.fixes = dfix
                check_fixes(x.fixes, len(x.data), m.sym_name(x.sym))
                dfix = None
            m.items.append(x)
        elif rtype == R_DFIX:
            dfix = _fix_entries(body, r)
        elif rtype == R_FUNC:
            func = Func(body.u16(), body.u8())
            define(func.sym, 'FUNC', K_FUNC)
            func_stage = 0
        elif rtype == R_CLAS:
            c = Clas(body.u16(), body.u8(), [])
            define(c.sym, 'CLAS', K_CLASS)
            n = body.u8()
            c.params, c.names = [], []
            for _ in range(n):
                c.params.append(body.u16())
                c.names.append(body.string())
            m.items.append(c)
        elif rtype == R_MEMB:
            mb = Memb(body.u16(), body.u16())
            sym_ref(mb.cls, 'MEMB', (K_CLASS,))
            sym_ref(mb.func, 'MEMB', (K_FUNC,))
            m.items.append(mb)
        elif rtype == R_WGT:
            raw = body.rest()
            if len(raw) % 4:
                r.fail(f'WGT body length {len(raw)} is not a multiple of 4')
            w = Wgt()
            for i in range(0, len(raw), 4):
                e = Weight(*struct.unpack('<HBB', raw[i:i + 4]))
                s = sym_ref(e.sym, 'WGT', (K_FUNC, K_VAR, K_CLASS))
                if (s.kind == K_VAR) != (e.slot == NO_SLOT):
                    r.fail(f'WGT: {s.name} is a {KIND_NAMES[s.kind]}: '
                           + ('a weight for it names no slot' if s.kind == K_VAR else 'a weight names one of its slots'))
                pending.append((Fix(0, 0, e.sym, e.slot), 'WGT', r.pos))
                w.entries.append(e)
            m.items.append(w)
        elif rtype == R_END:
            if length:
                r.fail(f'END record has body length {length}, expected 0')
            ended = True
        else:
            r.fail(f'{name} record outside a function')
        body.done()
        r.pos += 3 + length

    if m is None:
        r.fail('empty file: first record must be MOD')
    if func is not None:
        r.fail(f'function {m.sym_name(func.sym)} not closed by ENDF (end of file)')
    if not ended:
        r.fail('no END record')
    if dfix is not None:
        r.fail('DFIX record not just before a DATA record')

    # Slot numbers can be checked once every local definition is known.
    for x, what, pos in pending:
        s = m.symbols[x.sym]
        target = m.definition(x.sym)
        if what == 'WGT' and isinstance(target, Var):
            r.pos = pos
            r.fail(f'WGT: {s.name} is defined here; its own VAR record has its weight')
        if x.slot == NO_SLOT:
            continue
        if s.kind == K_FUNC and isinstance(target, Func) and x.slot >= len(target.slots):
            r.pos = pos
            r.fail(f'{what}: fix-up names slot {x.slot} of {s.name}, which has {len(target.slots)} slots')
        if s.kind == K_CLASS and isinstance(target, Clas) and x.slot >= len(target.params):
            r.pos = pos
            r.fail(f'{what}: fix-up names parameter {x.slot} of {s.name}, '
                   f'which has {len(target.params)} parameters')
    return m


def load(path):
    with open(path, 'rb') as fh:
        return read(fh.read(), path)


# ---------------------------------------------------------------------------------------------
# Writing

def _rec(t, body=b''):
    if len(body) > 0xFFFF:
        raise LoError(f'{RECORD_NAMES[t]} record body is {len(body)} bytes, more than 65535')
    return bytes((t,)) + struct.pack('<H', len(body)) + bytes(body)


def _str(s):
    b = s.encode('latin-1')
    if len(b) > 255:
        raise LoError(f'name longer than 255 bytes: {s[:40]}...')
    return bytes((len(b),)) + b


def _fixes(fixes):
    return b''.join(struct.pack('<HBHBH', x.offset, x.kind, x.sym, x.slot, x.addend & 0xFFFF)
                    for x in sorted(fixes, key=lambda x: x.offset))


def write(m):
    """Encode a Module. Writes MOD, IMPs, every SYM, the definitions in order, END."""
    out = [_rec(R_MOD, bytes((m.version, m.cpu)) + _str(m.name))]
    out += [_rec(R_IMP, _str(i)) for i in m.imports]
    out += [_rec(R_SYM, bytes((s.kind,)) + _str(s.name)) for s in m.symbols]
    for x in m.items:
        if isinstance(x, Func):
            out.append(_rec(R_FUNC, struct.pack('<HB', x.sym, x.flags)))
            out += [_rec(R_SLOT, struct.pack('<HBBB', s.size, s.cls, s.weight, s.kind) + _str(s.name))
                    for s in x.slots]
            out += [_rec(R_CALL, struct.pack('<HBH', c.callee, c.flags, c.outer)) for c in x.calls]
            out.append(_rec(R_FIX, _fixes(x.fixes)))
            out.append(_rec(R_CODE, x.code))
            out.append(_rec(R_ENDF))
        elif isinstance(x, Var):
            out.append(_rec(R_VAR, struct.pack('<HHBBB', x.sym, x.size, x.cls, x.weight, x.flags)))
        elif isinstance(x, Data):
            if x.fixes:
                out.append(_rec(R_DFIX, _fixes(x.fixes)))
            out.append(_rec(R_DATA, struct.pack('<H', x.sym) + x.data))
        elif isinstance(x, Clas):
            out.append(_rec(R_CLAS, struct.pack('<HBB', x.sym, x.flags, len(x.params))
                            + b''.join(struct.pack('<H', p) + _str(n) for p, n in zip(x.params, x.names))))
        elif isinstance(x, Wgt):
            out.append(_rec(R_WGT, b''.join(struct.pack('<HBB', e.sym, e.slot, e.weight) for e in x.entries)))
        elif isinstance(x, Memb):
            out.append(_rec(R_MEMB, struct.pack('<HH', x.cls, x.func)))
        else:
            raise LoError(f'not an object item: {x!r}')
    out.append(_rec(R_END))
    return b''.join(out)


# ---------------------------------------------------------------------------------------------
# Building

class _Pending:
    """A fix-up whose target is still a name: (kind, name, slot, addend) at an offset."""

    def __init__(self, offset, kind, target, addend):
        self.offset, self.kind, self.target, self.addend = offset, kind, target, addend


class _Fixable:
    """Constant data being built: fix-ups by name, resolved when the module is finished."""

    def __init__(self, builder, item, size):
        self.b, self.item, self.size = builder, item, size
        self.pending = []

    def fix(self, offset, kind, target, addend=0):
        """A fix-up in the data. target: name, or (name, slot)."""
        if offset + FIX_WIDTH[kind] > self.size:
            raise LoError(f'fix-up at {offset} runs past the end of the data')
        self.pending.append(_Pending(offset, kind, target, addend))
        return self

    def finish(self):
        self.item.fixes = [self.b._resolve(p, None) for p in self.pending]


class FuncBuilder:
    def __init__(self, builder, func, name):
        self.b, self.func, self.name = builder, func, name
        self.code = bytearray()
        self.labels = {}
        self.branches = []         # (offset of the displacement byte, label)
        self.pending = []
        self.finished = False

    def slot(self, name, size, cls=1, weight=0, kind=SK_LOCAL):
        """Adds a slot; returns its number."""
        self.func.slots.append(Slot(size, cls, weight, kind, name))
        return len(self.func.slots) - 1

    def call(self, callee, flags=0, outer=None):
        kind = K_CLASS if flags & C_POINTER else K_FUNC
        c = Call(self.b.extern(callee, kind), flags, NO_OUTER)
        if outer is not None:
            c.outer = self.b._sym(outer)
        self.func.calls.append(c)
        return self

    def label(self, name):
        if name in self.labels:
            raise LoError(f'{self.name}: label {name} defined twice')
        self.labels[name] = len(self.code)
        return self

    def raw(self, *data):
        """Bytes copied into the code as they are."""
        self.code += bytes(data)
        return self

    def op(self, mnemonic, mode=cpu6502.IMP, operand=None, addend=0):
        part = None
        if mode in ('#<', '#>'):
            part, mode = (FX_LO if mode == '#<' else FX_HI), cpu6502.IMM
        modes = cpu6502.table(self.b.module_.cpu).get(mnemonic.upper())
        if modes is None:
            raise LoError(f'unknown mnemonic {mnemonic}')
        if mode not in modes:
            raise LoError(f'{mnemonic} has no mode {mode}')
        self.code.append(modes[mode])
        at = len(self.code)
        width = cpu6502.OPERAND_BYTES[mode]
        if width == 0:
            return self
        if mode == cpu6502.REL:
            if not isinstance(operand, str):
                raise LoError(f'{mnemonic}: a branch takes a label name')
            self.branches.append((at, operand))
            self.code.append(0)
            return self
        if isinstance(operand, int):
            if part is not None or operand > (0xFF if width == 1 else 0xFFFF):
                raise LoError(f'{mnemonic}: literal {operand} does not fit the operand')
            self.code += operand.to_bytes(width, 'little')
            return self
        if width == 2:
            kind = FX_SHRINK if cpu6502.shrinks(self.b.module_.cpu, mnemonic.upper(), mode) else FX_WORD
        elif part is not None:
            kind = part
        elif mode == cpu6502.IMM:
            raise LoError(f'{mnemonic} #: use mode "#<" or "#>" for a symbol')
        else:
            kind = FX_ZP
        self.pending.append(_Pending(at, kind, operand, addend))
        self.code += bytes(width)
        return self

    def finish(self):
        if self.finished:
            return
        for at, name in self.branches:
            if name not in self.labels:
                raise LoError(f'{self.name}: label {name} not defined')
            disp = self.labels[name] - (at + 1)
            if not -128 <= disp <= 127:
                raise LoError(f'{self.name}: branch at ${at - 1:04X} to {name} out of range ({disp})')
            self.code[at] = disp & 0xFF
        self.func.code = bytes(self.code)
        self.func.fixes = sorted((self.b._resolve(p, self) for p in self.pending), key=lambda x: x.offset)
        self.finished = True


class Builder:
    def __init__(self, name, cpu=cpu6502.CPU_6502):
        self.module_ = Module(name, cpu)
        self.parts = []

    def imp(self, name):
        self.module_.imports.append(name)
        return self

    def extern(self, name, kind):
        """Declares a symbol (SYM record) if it is not yet declared; returns its number."""
        m = self.module_
        for i, s in enumerate(m.symbols):
            if s.name == name:
                if s.kind != kind:
                    raise LoError(f'{name} is a {KIND_NAMES[s.kind]}, not a {KIND_NAMES[kind]}')
                return i
        m.symbols.append(Symbol(kind, name))
        return len(m.symbols) - 1

    def _sym(self, name):
        for i, s in enumerate(self.module_.symbols):
            if s.name == name:
                return i
        raise LoError(f'symbol {name} not declared (use Builder.extern)')

    def func(self, name, flags=0):
        f = Func(self.extern(name, K_FUNC), flags)
        self.module_.items.append(f)
        fb = FuncBuilder(self, f, name)
        self.parts.append(fb)
        return fb

    def var(self, name, size, cls=1, weight=0):
        """A variable: storage only. Initial values are code, in a function module.$init."""
        self.module_.items.append(Var(self.extern(name, K_VAR), size, cls, weight))
        return self

    def data(self, name, data):
        x = Data(self.extern(name, K_DATA), bytes(data))
        self.module_.items.append(x)
        p = _Fixable(self, x, len(x.data))
        self.parts.append(p)
        return p

    def clas(self, name, params, flags=0, names=None):
        names = None if names is None else list(names)
        self.module_.items.append(Clas(self.extern(name, K_CLASS), flags, list(params), names))
        return self

    def wgt(self, target, weight):
        """A WGT record of one entry: the target is a variable name or (function or class name,
        slot or parameter number)."""
        slot = NO_SLOT
        if isinstance(target, tuple):
            target, slot = target
        self.module_.items.append(Wgt([Weight(self._sym(target), slot, weight)]))
        return self

    def memb(self, cls, func):
        self.module_.items.append(Memb(self.extern(cls, K_CLASS), self.extern(func, K_FUNC)))
        return self

    def _resolve(self, p, fb):
        target, slot, addend = p.target, NO_SLOT, p.addend
        if isinstance(target, tuple):
            target, slot = target
        elif fb is not None and target in fb.labels:
            target, addend = fb.name, fb.labels[target] + addend
        i = self._sym(target)
        if isinstance(slot, str):
            d = self.module_.definition(i)
            names = [s.name for s in d.slots] if isinstance(d, Func) else []
            if slot not in names:
                raise LoError(f'{target} has no slot named {slot} here (give its number)')
            slot = names.index(slot)
        return Fix(p.offset, p.kind, i, slot, addend & 0xFFFF)

    def module(self):
        for p in self.parts:
            p.finish()
        return self.module_

    def bytes(self):
        return write(self.module())

    def save(self, path):
        data = self.bytes()
        with open(path, 'wb') as fh:
            fh.write(data)
        return path
