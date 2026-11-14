"""The environment file and the map file (lathe/host/README.md)."""
from dataclasses import dataclass
from typing import Optional


class FormatError(Exception):
    pass


def _number(text, where):
    try:
        if text.startswith('$'):
            return int(text[1:], 16)
        return int(text, 10)
    except ValueError:
        raise FormatError(f'{where}: not a number: {text}') from None


def _lines(text):
    for n, line in enumerate(text.splitlines(), 1):
        line = line.split(';', 1)[0].strip()
        if line:
            yield n, line.split()


EXIT_CALL, EXIT_LOOP, EXIT_RETURN, EXIT_STOP = 'call', 'loop', 'return', 'stop'
OUTPUT_IMAGE, OUTPUT_RAW = 'image', 'raw'
KNOWN = ('cpu', 'zeropage', 'code', 'data', 'stack', 'exit', 'output')


@dataclass
class Env:
    cpu: int = 0
    zeropage: tuple = (0x00, 0xFF)
    code: tuple = (0x0200, 0xBFFF)
    data: tuple = (0xC000, 0xEFFF)
    stack: Optional[int] = None      # stack n: the start-up code sets S to n
    exit: tuple = (EXIT_RETURN, None)  # (EXIT_CALL, addr), or (EXIT_LOOP / EXIT_RETURN / EXIT_STOP, None)
    output: str = OUTPUT_IMAGE       # OUTPUT_IMAGE: code start to $FFFF and the reset vector;
                                     # OUTPUT_RAW: code start to the last byte placed
    path: str = ''


def read_env(path):
    with open(path) as fh:
        return parse_env(fh.read(), path)


def parse_env(text, path='<env>'):
    """Parses an environment file (lathe/host/README.md). Unknown entries are ignored, because the
    format grows; `start`, which an earlier version had, is an error."""
    env = Env(path=path)
    seen = set()
    for n, words in _lines(text):
        key, args, where = words[0].lower(), words[1:], f'{path}:{n}'
        if key in seen and key in KNOWN:
            raise FormatError(f'{where}: second {key} entry')
        seen.add(key)
        if key == 'cpu':
            if len(args) != 1 or args[0].lower() not in ('6502', '65c02'):
                raise FormatError(f'{where}: cpu is 6502 or 65c02')
            env.cpu = 0 if args[0].lower() == '6502' else 1
        elif key in ('zeropage', 'code', 'data'):
            if len(args) != 2:
                raise FormatError(f'{where}: {key} takes a first and a last address')
            lo, hi = _number(args[0], where), _number(args[1], where)
            if not 0 <= lo <= hi <= 0xFFFF or (key == 'zeropage' and hi > 0xFF):
                raise FormatError(f'{where}: bad {key} range')
            setattr(env, key, (lo, hi))
        elif key == 'stack':
            if len(args) != 1 or not 0 <= _number(args[0], where) <= 0xFF:
                raise FormatError(f'{where}: stack is one byte, the value for the stack pointer: stack $FF')
            env.stack = _number(args[0], where)
        elif key == 'exit':
            form = [a.lower() for a in args]
            if len(form) == 2 and form[0] == EXIT_CALL and 0 <= _number(args[1], where) <= 0xFFFF:
                env.exit = (EXIT_CALL, _number(args[1], where))
            elif form in ([EXIT_LOOP], [EXIT_RETURN], [EXIT_STOP]):
                env.exit = (form[0], None)
            else:
                raise FormatError(f'{where}: exit takes call ADDR, loop, return or stop')
        elif key == 'output':
            form = [a.lower() for a in args]
            if form not in ([OUTPUT_IMAGE], [OUTPUT_RAW]):
                raise FormatError(f'{where}: output is image or raw')
            env.output = form[0]
        elif key == 'start':
            raise FormatError(f'{where}: start is no longer an entry: the linker makes $start '
                              f'(lathe/docs/object-format.md, "Initial values and start-up")')
    if 'exit' not in seen:
        raise FormatError(f'{path}: no exit entry (exit call ADDR, exit loop, exit return or exit stop)')
    if env.exit[0] == EXIT_STOP and env.cpu != 1:
        raise FormatError(f'{path}: exit stop needs cpu 65c02 (STP is a 65C02 instruction)')
    return env


# Map file kinds.
M_FUNC, M_DATA, M_VAR, M_SLOT, M_CLASS = 'F', 'D', 'V', 'S', 'C'


@dataclass
class MapEntry:
    kind: str
    addr: int
    size: int
    name: str
    number: Optional[int] = None      # slot or parameter number (S, C)
    part: Optional[str] = None        # slot or parameter name (S, C)
    context: int = 0                  # F: the context the function copy is for

    def format(self):
        s = f'{self.kind} {self.addr:04X} {self.size:04X} {self.name}'
        if self.number is not None:
            s += f' {self.number} {self.part}'
        if self.kind == M_FUNC and self.context != 0 and '@' not in self.name:
            s += f' {self.context}'
        return s

    def base(self):
        """The function an F or S line belongs to: its name without the @N of a copy."""
        return self.name.split('@', 1)[0]


def parse_map(text, path='<map>'):
    out = []
    for n, words in _lines(text):
        where = f'{path}:{n}'
        kind = words[0]
        if kind not in (M_FUNC, M_DATA, M_VAR, M_SLOT, M_CLASS):
            raise FormatError(f'{where}: unknown map line kind {kind}')
        want = 6 if kind in (M_SLOT, M_CLASS) else 4
        copy = kind == M_FUNC and '@' in words[3] if len(words) > 3 else False
        if len(words) != want and not (kind == M_FUNC and not copy and len(words) == 5):
            raise FormatError(f'{where}: a {kind} line has {want} fields'
                              + (' (5 for a first copy outside context 0)' if kind == M_FUNC else ''))
        try:
            addr, size = int(words[1], 16), int(words[2], 16)
            number = int(words[4]) if want == 6 else None
            context = 0
            if copy:
                context = int(words[3].split('@', 1)[1])
            elif kind == M_FUNC and len(words) == 5:
                context = int(words[4])
        except ValueError:
            raise FormatError(f'{where}: bad number') from None
        if kind == M_FUNC and (copy or len(words) == 5) and context == 0:
            raise FormatError(f'{where}: context 0 is not written')
        out.append(MapEntry(kind, addr, size, words[3], number, words[5] if want == 6 else None, context))
    return out


def read_map(path):
    with open(path) as fh:
        return parse_map(fh.read(), path)


def write_map(path, entries):
    with open(path, 'w') as fh:
        for e in entries:
            fh.write(e.format() + '\n')
