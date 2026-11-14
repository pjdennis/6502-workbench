"""Helpers for the linker's tests: build object files byte by byte and run the linker on them.

No tests here. The object builder follows lathe/docs/object-format.md and nothing else, so
that the linker is checked against the document and not against another program's reading of it.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
LINK = os.path.join(ROOT, 'lathe', 'host', 'link.py')
sys.path.insert(0, os.path.join(ROOT, 'lathe', 'host', 'driver'))

HOST_ENV = (
    'cpu       6502\n'
    'zeropage  $00 $FF\n'
    'code      $0200 $BFFF\n'
    'data      $C000 $EFFF\n'
    'stack     $FF\n'
    'exit      call $F00F\n'
)

FUNCTION, VARIABLE, CONSTANT, CLASS = 1, 2, 3, 4
MUST, EITHER, NEVER = 0, 1, 2           # zero page classes
PARAM, LOCAL, TEMP = 0, 1, 2            # slot kinds
RECURSIVE, INTERRUPT = 1, 2             # FUNC flags
SAVES, POINTER = 1, 2                   # CALL flags
NOBODY = 0xFFFF

# The instructions with a two-byte address that have a zero page form (object-format.md, "The
# size of an instruction"): a fix-up of their address is of kind 5, any other two-byte one of kind 1.
SHRINKABLE = frozenset(
    [0x0D + 0x10 * h for h in range(16)] + [0x0E + 0x10 * h for h in range(16)]
    + [0x0C, 0x1C, 0x2C, 0x3C, 0x8C, 0x9C, 0xAC, 0xBC, 0xCC, 0xEC])


def word(n):
    return bytes((n & 0xFF, (n >> 8) & 0xFF))


def string(s):
    return bytes((len(s),)) + s.encode('latin-1')


def record(kind, body=b''):
    return bytes((kind,)) + word(len(body)) + body


class Code:
    """A function's code as written (three-byte absolute forms) and its fix-ups."""

    def __init__(self, obj):
        self.obj = obj
        self.bytes = bytearray()
        self.fixes = []

    def here(self):
        return len(self.bytes)

    def raw(self, *values):
        self.bytes += bytes(values)
        return self

    def _fix(self, kind, sym, slot, add):
        self.fixes.append((len(self.bytes), kind, sym, slot, add & 0xFFFF))

    def abs(self, op, sym, slot=0xFF, add=0, kind=None):
        """A three-byte instruction whose operand is a two-byte fix-up: of kind 5 if the
        instruction has a zero page form, else of kind 1, unless `kind` says otherwise."""
        self.bytes.append(op)
        if kind is None:
            kind = 5 if op in SHRINKABLE else 1
        self._fix(kind, sym, slot, add)
        self.bytes += b'\0\0'
        return self

    def byte(self, op, kind, sym, slot=0xFF, add=0):
        """A two-byte instruction whose operand is a one-byte fix-up of the given kind."""
        self.bytes.append(op)
        self._fix(kind, sym, slot, add)
        self.bytes.append(0)
        return self

    def branch(self, op, target):
        """A branch to a written offset."""
        self.bytes.append(op)
        self.bytes.append((target - (len(self.bytes) + 1)) & 0xFF)
        return self


class Obj:
    """One object file under construction."""

    def __init__(self, name, cpu=0, version=2):
        self.name = name
        self.records = [record(1, bytes((version, cpu)) + string(name))]
        self.numbers = {}

    def sym(self, kind, name):
        """The number of a symbol, writing its SYM record at first use."""
        if '.' not in name:
            name = self.name + '.' + name
        if name not in self.numbers:
            self.numbers[name] = len(self.numbers)
            self.records.append(record(3, bytes((kind,)) + string(name)))
        return self.numbers[name]

    def f(self, name):
        return self.sym(FUNCTION, name)

    def v(self, name):
        return self.sym(VARIABLE, name)

    def d(self, name):
        return self.sym(CONSTANT, name)

    def k(self, name):
        return self.sym(CLASS, name)

    def imp(self, name):
        self.records.append(record(2, string(name)))

    def var(self, name, size, zp_class=EITHER, weight=0, flags=0, init=b''):
        n = self.v(name)
        self.records.append(record(4, word(n) + word(size) + bytes((zp_class, weight, flags)) + init))
        return n

    @staticmethod
    def _fixes(fixes):
        return b''.join(word(off) + bytes((kind,)) + word(sym) + bytes((slot,)) + word(add)
                        for off, kind, sym, slot, add in fixes)

    def data(self, name, content, fixes=()):
        n = self.d(name)
        if fixes:
            self.records.append(record(6, self._fixes(fixes)))
        self.records.append(record(5, word(n) + bytes(content)))
        return n

    def code(self):
        return Code(self)

    def func(self, name, code=None, slots=(), calls=(), flags=0):
        """slots: (size, class, weight, kind, name); calls: (callee, flags, outer).

        code: a Code, or bytes with no fix-ups; the default is a lone RTS."""
        n = self.f(name)
        self.records.append(record(7, word(n) + bytes((flags,))))
        for size, zp_class, weight, kind, slot_name in slots:
            self.records.append(record(8, word(size) + bytes((zp_class, weight, kind)) + string(slot_name)))
        for callee, call_flags, outer in calls:
            self.records.append(record(9, word(callee) + bytes((call_flags,)) + word(outer)))
        if code is None:
            code = b'\x60'
        fixes = ()
        if isinstance(code, Code):
            fixes = code.fixes
            code = bytes(code.bytes)
        self.records.append(record(10, self._fixes(fixes)))
        self.records.append(record(11, bytes(code)))
        self.records.append(record(12))
        return n

    def clas(self, name, sizes, flags=0, names=None):
        """names: the parameters' names; empty, unknown, if not given."""
        n = self.k(name)
        if names is None:
            names = [''] * len(sizes)
        self.records.append(record(13, word(n) + bytes((flags, len(sizes)))
                                   + b''.join(word(s) + string(p) for s, p in zip(sizes, names))))
        return n

    def wgt(self, *entries):
        """A WGT record: entries (symbol number, slot or 0xFF, weight)."""
        self.records.append(record(15, b''.join(word(sym) + bytes((slot, weight)) for sym, slot, weight in entries)))

    def memb(self, class_name, func_name):
        self.records.append(record(14, word(self.k(class_name)) + word(self.f(func_name))))

    def raw(self, kind, body=b''):
        self.records.append(record(kind, body))

    def to_bytes(self):
        return b''.join(self.records) + record(0)


def routine(o, name, slots=(), calls=(), flags=0):
    """Add to Obj o a function that makes each call in turn and returns.

    A call is a callee name, or (callee, CALL flags, outer or None). An outer is a function
    name, or a class name after `^`. With the POINTER flag the callee is a class and the call
    is a JSR to a JMP (pointer) at the function's end."""
    c = o.code()
    records = []
    pointer_calls = []
    for call in calls:
        callee, call_flags, outer = call if isinstance(call, tuple) else (call, 0, None)
        if outer is None:
            outer_sym = NOBODY
        else:
            outer_sym = o.k(outer[1:]) if outer.startswith('^') else o.f(outer)
        if call_flags & POINTER:
            records.append((o.k(callee), call_flags, outer_sym))
            pointer_calls.append(c.here() + 1)
            c.raw(0x20, 0, 0)
        else:
            records.append((o.f(callee), call_flags, outer_sym))
            c.abs(0x20, o.f(callee))
    c.raw(0x60)
    for operand in pointer_calls:
        # JSR to the JMP (pointer) that follows the code; the pointer is a literal here.
        c.fixes.append((operand, 1, o.f(name), 0xFF, c.here()))
        c.raw(0x6C, 0x00, 0x03)
    c.fixes.sort()
    o.func(name, c, slots=slots, calls=records, flags=flags)


def keep(o, *names):
    """Add to Obj o an interrupt function `keep` that reads each variable or constant data
    named (a name whose last part starts with `$` is constant data), so that the linker keeps
    them. It is a root of a context of its own and has no slots, so it moves nothing that comes
    before it; give it last."""
    c = o.code()
    for name in names:
        c.abs(0xAD, o.d(name) if name.split('.')[-1].startswith('$') else o.v(name))
    c.raw(0x40)
    o.func('keep', c, flags=INTERRUPT)


class Result:
    """What a run of the linker left behind."""

    def __init__(self, status, errors, image, map_text, code_lo):
        self.asm_image = None       # the image by the assembler path, if asked for
        self.asm_text = ''
        self.status = status
        self.errors = errors
        self.image = image
        self.map_text = map_text
        self.code_lo = code_lo
        self.map = [line.split() for line in map_text.splitlines()]

    def at(self, addr, count=1):
        """`count` bytes of the image at an address."""
        return bytes(self.image[addr - self.code_lo:addr - self.code_lo + count])

    def line(self, letter, name, number=None):
        """The map line of this kind and name (and slot or parameter number)."""
        found = [m for m in self.map if m[0] == letter and m[3] == name
                 and (number is None or int(m[4]) == number)]
        if len(found) != 1:
            raise AssertionError('%d map lines for %s %s %s:\n%s' % (len(found), letter, name, number, self.map_text))
        return found[0]

    def addr(self, letter, name, number=None):
        return int(self.line(letter, name, number)[1], 16)

    def size(self, letter, name, number=None):
        return int(self.line(letter, name, number)[2], 16)

    def has(self, letter, name):
        return any(m[0] == letter and m[3] == name for m in self.map)

    def code(self, name):
        """The bytes of a function as linked."""
        return self.at(self.addr('F', name), self.size('F', name))


def _module_name(obj):
    return obj.name if isinstance(obj, Obj) else obj.module_.name


def link(objects, env=HOST_ENV, main=None, args=None, asm=False):
    """Link the objects (Obj, lo.Builder or bytes) and return a Result. main defaults to the
    first module. With asm, the program is also built by the assembler path: lo2asm renders
    the objects with the linker's map and asm/pyasm.py assembles the text."""
    with tempfile.TemporaryDirectory() as tmp:
        env_path = os.path.join(tmp, 'test.env')
        with open(env_path, 'w') as f:
            f.write(env)
        paths = []
        for i, obj in enumerate(objects):
            path = os.path.join(tmp, 'm%d.lo' % i)
            with open(path, 'wb') as f:
                if isinstance(obj, Obj):
                    f.write(obj.to_bytes())
                elif isinstance(obj, bytes):
                    f.write(obj)
                else:
                    f.write(obj.bytes())
            paths.append(path)
        if main is None:
            main = _module_name(objects[0])
        bin_path = os.path.join(tmp, 'out.bin')
        map_path = os.path.join(tmp, 'out.map')
        if args is None:
            args = [env_path, main, bin_path, map_path] + paths
        run = subprocess.run([sys.executable, LINK] + args, capture_output=True)
        image = b''
        map_text = ''
        if run.returncode == 0:
            with open(bin_path, 'rb') as f:
                image = f.read()
            with open(map_path) as f:
                map_text = f.read()
        code_lo = 0
        for line in env.splitlines():
            parts = line.split(';')[0].split()
            if len(parts) > 1 and parts[0].lower() == 'code' and run.returncode == 0:
                code_lo = int(parts[1][1:], 16) if parts[1][0] == '$' else int(parts[1])
        result = Result(run.returncode, run.stderr.decode('latin-1'), image, map_text, code_lo)
        if asm and run.returncode == 0:
            import build
            asm_bin = os.path.join(tmp, 'asm.bin')
            result.asm_text = build.assembler_image(paths, env_path, main, map_path,
                                                    os.path.join(tmp, 'out.asm'), asm_bin)
            with open(asm_bin, 'rb') as f:
                result.asm_image = f.read()
        return result
