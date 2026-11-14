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


@dataclass
class Env:
    cpu: int = 0
    zeropage: tuple = (0x00, 0xFF)
    code: tuple = (0x0200, 0xBFFF)
    data: tuple = (0xC000, 0xEFFF)
    start: str = ''
    path: str = ''


def read_env(path):
    """Parses an environment file. Unknown entries are ignored (the format grows)."""
    with open(path) as fh:
        text = fh.read()
    env = Env(path=path)
    seen = set()
    for n, words in _lines(text):
        key, args, where = words[0].lower(), words[1:], f'{path}:{n}'
        if key in seen and key in ('cpu', 'zeropage', 'code', 'data', 'start'):
            raise FormatError(f'{where}: second {key} entry')
        seen.add(key)
        if key == 'cpu':
            if len(args) != 1 or args[0].lower() not in ('6502', '65c02'):
                raise FormatError(f'{where}: cpu is 6502 or 65c02')
            env.cpu = 0 if args[0] == '6502' else 1
        elif key in ('zeropage', 'code', 'data'):
            if len(args) != 2:
                raise FormatError(f'{where}: {key} takes a first and a last address')
            lo, hi = _number(args[0], where), _number(args[1], where)
            if not 0 <= lo <= hi <= 0xFFFF or (key == 'zeropage' and hi > 0xFF):
                raise FormatError(f'{where}: bad {key} range')
            setattr(env, key, (lo, hi))
        elif key == 'start':
            if len(args) != 1 or '.' not in args[0]:
                raise FormatError(f'{where}: start takes a function name, module.name')
            env.start = args[0].lower()
    if not env.start:
        raise FormatError(f'{path}: no start entry')
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

    def format(self):
        s = f'{self.kind} {self.addr:04X} {self.size:04X} {self.name}'
        if self.number is not None:
            s += f' {self.number} {self.part}'
        return s


def parse_map(text, path='<map>'):
    out = []
    for n, words in _lines(text):
        where = f'{path}:{n}'
        kind = words[0]
        if kind not in (M_FUNC, M_DATA, M_VAR, M_SLOT, M_CLASS):
            raise FormatError(f'{where}: unknown map line kind {kind}')
        want = 6 if kind in (M_SLOT, M_CLASS) else 4
        if len(words) != want:
            raise FormatError(f'{where}: a {kind} line has {want} fields')
        try:
            addr, size = int(words[1], 16), int(words[2], 16)
            number = int(words[4]) if want == 6 else None
        except ValueError:
            raise FormatError(f'{where}: bad number') from None
        out.append(MapEntry(kind, addr, size, words[3], number, words[5] if want == 6 else None))
    return out


def read_map(path):
    with open(path) as fh:
        return parse_map(fh.read(), path)


def write_map(path, entries):
    with open(path, 'w') as fh:
        for e in entries:
            fh.write(e.format() + '\n')
