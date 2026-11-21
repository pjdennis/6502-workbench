"""The environment file and the map file (lathe/host/README.md)."""
import re
from dataclasses import dataclass, field
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


def entries(text, path='<env>'):
    """(line number, words) of each entry of an environment file, comments and blank lines
    left out. Every tool that reads an environment file reads its entries through this.

    `when NAME ENTRY` is ENTRY if NAME is defined by a `define` above it and not 0, and nothing
    otherwise; `unless NAME ENTRY` is the opposite; ENTRY may be another of them. An entry
    skipped is skipped completely: it is not checked. The latest `define` of a name counts."""
    defined = {}
    for n, words in _lines(text):
        where = f'{path}:{n}'
        while words and words[0].lower() in ('when', 'unless'):
            key = words[0].lower()
            if len(words) < 2:
                raise FormatError(f'{where}: {key} takes a define\'s name and an entry')
            if words[1].lower() not in defined:
                raise FormatError(f'{where}: {words[1]} is not defined above (by a define entry)')
            if len(words) < 3:
                raise FormatError(f'{where}: {key} takes a define\'s name and an entry')
            words = words[2:] if defined[words[1].lower()] == (key == 'when') else None
        if words is None:
            continue
        if words[0].lower() == 'define' and len(words) in (2, 3):
            defined[words[1].lower()] = len(words) == 2 or _number(words[2], where) != 0
        yield n, words


def read_entries(path):
    """entries() of the environment file at path."""
    with open(path) as fh:
        return list(entries(fh.read(), path))


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
    exit: tuple = (EXIT_RETURN, None)  # (EXIT_CALL, addr), (EXIT_RETURN, addr) for `exit return
                                       # addr`, or (EXIT_LOOP / EXIT_RETURN / EXIT_STOP, None)
    output: str = OUTPUT_IMAGE       # OUTPUT_IMAGE: code start to $FFFF and the reset vector;
                                     # OUTPUT_RAW: code start to the last byte placed
    defines: list = field(default_factory=list)  # `define NAME [VALUE]`: (NAME, VALUE or None)
    path: str = ''
    # Version 2 (configurations.md), as far as the driver needs it; the linker checks the rest.
    places: list = field(default_factory=list)   # `place MODULE WIN N`: the modules placed
    files: list = field(default_factory=list)    # the file of each `bank` or `overlay` that has one
    farcall: Optional[str] = None                # `farcall MODULE`
    regions: list = field(default_factory=list)  # `region NAME WIN N`: the regions in a bank
    fixed_regions: list = field(default_factory=list)  # `region NAME fixed [ADDR]`: the regions said to be
                                                       # in fixed memory (build.compiler_options)
    dynamic_regions: list = field(default_factory=list)  # `region NAME WIN N dynamic` (also in regions)
    main_regions: list = field(default_factory=list)  # `region NAME WIN N dynamic main` (also in
                                                      # dynamic_regions): in main RAM alone
    placer: Optional[str] = None                 # `placer MODULE` (lathe/host/lk_dyn.py)
    rooms: dict = field(default_factory=dict)    # `region NAME WIN N dynamic VARIABLE`: NAME's
                                                 # capacity variable

    def banked(self):
        """True if some module's code is in a window, or a region is in a bank: the link uses
        the far-call module, and the program cannot be built by the assembler path."""
        return bool(self.places) or bool(self.regions)


def read_env(path):
    with open(path) as fh:
        return parse_env(fh.read(), path)


def parse_env(text, path='<env>'):
    """Parses an environment file (lathe/host/README.md). Unknown entries are ignored, because the
    format grows; `start`, which an earlier version had, is an error."""
    env = Env(path=path)
    seen = set()
    for n, words in entries(text, path):
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
            elif len(form) == 2 and form[0] == EXIT_RETURN and 0 <= _number(args[1], where) <= 0xFFFF:
                env.exit = (EXIT_RETURN, _number(args[1], where))
            elif form in ([EXIT_LOOP], [EXIT_RETURN], [EXIT_STOP]):
                env.exit = (form[0], None)
            else:
                raise FormatError(f'{where}: exit takes call ADDR, loop, return [ADDR] or stop')
        elif key == 'output':
            form = [a.lower() for a in args]
            if form not in ([OUTPUT_IMAGE], [OUTPUT_RAW]):
                raise FormatError(f'{where}: output is image or raw')
            env.output = form[0]
        elif key == 'define':
            if not 1 <= len(args) <= 2 or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', args[0]):
                raise FormatError(f'{where}: define takes a name and, if it is not a bool, a number')
            value = _number(args[1], where) if len(args) == 2 else None
            if value is not None and not 0 <= value <= 0xFFFF:
                raise FormatError(f'{where}: a define\'s number is 0 to 65535')
            env.defines.append((args[0], value))
        elif key == 'place' and args:
            env.places.append(args[0].lower())
        elif key == 'bank' and len(args) == 4:
            env.files.append(args[3])
        elif key == 'overlay' and len(args) == 3:
            env.files.append(args[2])
        elif key == 'region' and len(args) == 3 and args[1].lower() != 'fixed':
            env.regions.append(args[0].lower())
        elif key == 'region' and len(args) >= 4 and args[3].lower() == 'dynamic':
            env.regions.append(args[0].lower())
            env.dynamic_regions.append(args[0].lower())
            room = args[4:]
            if room and room[0].lower() == 'main':
                env.main_regions.append(args[0].lower())
                room = room[1:]
            if room:
                env.rooms[args[0].lower()] = room[0]
        elif key == 'region' and len(args) in (2, 3) and args[1].lower() == 'fixed':
            env.fixed_regions.append(args[0].lower())
        elif key == 'farcall' and len(args) == 1:
            env.farcall = args[0].lower()
        elif key == 'placer' and len(args) == 1:
            env.placer = args[0].lower()
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
M_WINDOW, M_STUB = 'W', 'T'     # a bank's or overlay's contents (number, file); a stub


@dataclass
class MapEntry:
    kind: str
    addr: int
    size: int
    name: str
    number: Optional[int] = None      # slot or parameter number (S, C)
    part: Optional[str] = None        # slot or parameter name (S, C)
    context: int = 0                  # F: the context the function copy is for
    bank: Optional[int] = None        # F, D, V: the bank or overlay it is in (b=N)
    rom: bool = False                 # W: the bank is read-only (`rom WIN N`)
    kept: Optional[int] = None        # F: kept in fixed memory, its module in bank N (k=N)

    def format(self):
        if self.kind == M_WINDOW:
            return f'{self.kind} {self.addr:04X} {self.size:04X} {self.number} {self.name}' + (' rom' if self.rom else '')
        s = f'{self.kind} {self.addr:04X} {self.size:04X} {self.name}'
        if self.number is not None:
            s += f' {self.number} {self.part}'
        if self.kind == M_FUNC and self.context != 0 and '@' not in self.name:
            s += f' {self.context}'
        if self.bank is not None:
            s += f' b={self.bank}'
        if self.kept is not None:
            s += f' k={self.kept}'
        return s

    def base(self):
        """The function an F or S line belongs to: its name without the @N of a copy."""
        return self.name.split('@', 1)[0]


def parse_map(text, path='<map>'):
    out = []
    for n, words in _lines(text):
        where = f'{path}:{n}'
        kind = words[0]
        if kind == M_WINDOW or kind == M_STUB:
            want = 5 if kind == M_WINDOW else 4
            rom = kind == M_WINDOW and len(words) == 6 and words[5] == 'rom'
            if rom:
                words = words[:5]
            if len(words) != want:
                raise FormatError(f'{where}: a {kind} line has {want} fields')
            try:
                addr, size = int(words[1], 16), int(words[2], 16)
                number = int(words[3]) if kind == M_WINDOW else None
            except ValueError:
                raise FormatError(f'{where}: bad number') from None
            out.append(MapEntry(kind, addr, size, words[-1], number, rom=rom))
            continue
        bank = None
        kept = None
        if kind == M_FUNC and len(words) > 4 and words[-1].startswith('k='):
            try:
                kept = int(words[-1][2:])
            except ValueError:
                raise FormatError(f'{where}: bad number') from None
            words = words[:-1]
        elif kind in (M_FUNC, M_DATA, M_VAR) and len(words) > 4 and words[-1].startswith('b='):
            try:
                bank = int(words[-1][2:])
            except ValueError:
                raise FormatError(f'{where}: bad number') from None
            words = words[:-1]
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
        out.append(MapEntry(kind, addr, size, words[3], number, words[5] if want == 6 else None, context, bank,
                            kept=kept))
    return out


def read_map(path):
    with open(path) as fh:
        return parse_map(fh.read(), path)


def write_map(path, entries):
    with open(path, 'w') as fh:
        for e in entries:
            fh.write(e.format() + '\n')
