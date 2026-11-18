#!/usr/bin/env python3
"""The image of a Lathe module for the BBC Model B+128: one file of sixteen 16 KB banks (262,144
bytes, scheme direct16) or eight (131,072 bytes, one 128 KB EPROM, scheme direct8), which holds
one or more programs, each started by a * command (lathe/docs/bbc.md, "Step 3, as built: the ROM
form" and "The 128 KB module").

    python3 lathe/host/driver/bbcrom.py -o IMAGE [--listing FILE] [--loader FILE] [--short FILE]
                                        [--banks 16|8] COMMAND=PROGRAM,ENV[,MAP]...

Each program is linked on its own, by build.py, with an environment of its own (rom_env() makes
one from a program's *RUN environment): lathe/env/bbc-rom.env's machine, its banks of the module
`rom`, the window $8050-$BFDF. PROGRAM is its resident image (build.py's output: its fixed code
and constants, from its load address, the start of the environment's `code` range), and its bank
files are beside it (build.py copies them there). MAP is its map, for the listing.

What goes where (layout()):

- Every bank: the reserved bytes $8000-$804F of lathe/rt/bbc/module.asm (the sideways ROM header
  and the service code; $804F holds the bank's own number).
- The banks of the programs' code: each bank file of the module ($80 + n in its `bank` entry)
  in bank n, from $8050.
- The home bank: the module's own code and tables, after the code of the bank (bank 0, at
  $8050, in the sixteen-bank image; in the eight-bank one the bank with the most room after its
  code of those up to the last program's, or the first bank no program uses), and after them the
  texts of the Lathe tools' errors, packed by msgpack.py from the host's tables (3,673 bytes), in
  every image: the module writes one when a tool's ROM form asks with its service call $4C
  (lathe/docs/bbc.md, "The texts in the module").
- The programs' resident parts and the constants of their regions (a region bank's file), in
  pieces, which the home bank copies at the * command into main RAM and the sideways RAM slots.
  In the eight-bank image (or with --tails) in the rest of every bank, to $BFEF: first in the
  banks the image holds anyway, the one with the most room first, then in the banks after them,
  in order. In the sixteen-bank image, as it was before the eight-bank one, in bank 0 to $BFDF,
  then in the banks no program's code is in, in order.

Bank numbers. A program's bank of the module is bank n of the image where its environment says
`bank WIN N $8n FILE`; the environment chooses, and this tool checks: every such bank must be
`rom`, its number within the image (1 to 15 in the sixteen-bank image, where bank 0 is the
module's; 0 to 7 in the eight-bank one), used by one program only, and its file must fit
$8050-$BFDF. rom_env() numbers a program's banks of the module from a first bank given, in the
order of its `bank` lines, and returns the next: so a set of programs numbered one after the
other never collides. The resident parts are placed after the programs are linked, in the room
left over, so no number of a program's bank can collide with them.

--loader also writes the developer's loader (lathe/rt/bbc/loadmod.asm), which fills the module's
RAM form from the image: `*RUN LOADMOD IMAGE [SLOT]`. --short also writes the image's banks from 0
to the last one in use, and no more: the file for the loader on a disc, where the whole image
(256 KB) is more than a side holds (lathe/docs/bbc.md, "File names on the BBC"). The loader fills
each bank the file does not hold with the reserved bytes alone.

image(), layout() and loader() are the functions the tests call; ImageError says what does not
fit (with .over, the bytes over, where it is room that is short) or collides.
"""
import argparse
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'asm'))

import mapenv  # noqa: E402
import msgpack  # noqa: E402
import pyasm  # noqa: E402

MODULE_ASM = os.path.join(ROOT, 'lathe', 'rt', 'bbc', 'module.asm')
TEXTS_ASM = os.path.join(ROOT, 'lathe', 'rt', 'bbc', 'texts.asm')
MOST_PARTS = 4                          # the texts of the errors in at most this many parts
LOADER_ASM = os.path.join(ROOT, 'lathe', 'rt', 'bbc', 'loadmod.asm')
LOADER_LOAD = 0x1900                    # LOADMOD is loaded and entered at PAGE
BANKS = 16                              # the sixteen-bank image, scheme direct16
SCHEMES = {16: 'direct16', 8: 'direct8'}  # an image's banks, and the emulator's scheme for them
BANK_SIZE = 0x4000
IMAGE_SIZE = BANKS * BANK_SIZE
WINDOW = 0x8000
RESERVED = 0x50                         # $8000-$804F in every bank
NUMBER_AT = 0x4F                        # the bank's own number, the last reserved byte
FIRST = WINDOW + RESERVED               # $8050: the window of a program's banks starts here
LAST = 0xBFDF                           # ... and ends here, as the developer's form's
TOP = 0xBFEF                            # the pieces copied may run to here: the copier reads them
                                        # with LDA (zp),Y and Y = 0, which makes no dummy read
ROOM = LAST - FIRST + 1                 # a bank's room for code: 16,272 bytes
ENTRY = 8                               # the bytes of a copy list entry, in the home bank
FILL = 0xFF                             # an erased EPROM
SIDEWAYS_RAM = (0, 1, 12, 13)           # the B+128's
MAIN_RAM = 0xFF                         # a copy's destination in main RAM (module.asm, copier)
KEEP = 0x0400                           # exit return $0400 (lathe/rt/bbc.lth, KEEP)
TAIL = (0x0700, 0x07FF)                 # the tail and the stub, which last while a program runs
COMMAND_RE = re.compile(r'[A-Z][A-Z0-9]{0,9}$')


class ImageError(Exception):
    pass


@dataclass
class Bank:
    number: int                 # the environment's N
    value: int                  # $80 + n, or a sideways slot
    file: str = None
    rom: bool = False


@dataclass
class Program:
    command: str                # the * command, in capitals
    image: str                  # the resident image: build.py's output
    env: str                    # the environment it was linked with
    map: str = None             # its map, for the listing
    load: int = 0
    resident: bytes = b''
    banks: list = field(default_factory=list)
    top: int = 0                # the address after its memory below $8000 (check_himem)


def memory_top(path):
    """The address after the highest byte of main RAM an environment's program uses: the end of
    its `code`, `data` and `more data` ranges below $8000, + 1."""
    ends = []
    for n, words in mapenv.read_entries(path):
        key = [w.lower() for w in words[:2]]
        if key[0] in ('code', 'data') and len(words) == 3:
            ends.append(mapenv._number(words[2], f'{path}:{n}'))
        elif key == ['more', 'data'] and len(words) == 4:
            ends.append(mapenv._number(words[3], f'{path}:{n}'))
    return max(e for e in ends if e < 0x8000) + 1


def read_env_banks(path):
    """(window first, window last, [Bank]) of an environment file's `window`, `bank` and `rom`
    entries (the window named in its `bank` entries)."""
    windows, banks = {}, []
    lines = mapenv.read_entries(path)
    for n, words in lines:
        key = words[0].lower()
        if key == 'window' and len(words) == 4:
            windows[words[1].lower()] = (mapenv._number(words[2], f'{path}:{n}'),
                                         mapenv._number(words[3], f'{path}:{n}'))
        elif key == 'bank' and len(words) in (4, 5):
            banks.append(Bank(int(words[2]), mapenv._number(words[3], f'{path}:{n}'),
                              words[4] if len(words) == 5 else None))
    for n, words in lines:
        if words[0].lower() == 'rom' and len(words) == 3:
            for b in banks:
                if b.number == int(words[2]):
                    b.rom = True
    if len(windows) != 1:
        raise ImageError(f'{path}: a program of the module has one window (it has {len(windows)})')
    first, last = list(windows.values())[0]
    return first, last, banks


def load_program(p, size=BANKS):
    """Reads a program's environment, resident image and bank files, and checks them, for an
    image of `size` banks."""
    env = mapenv.read_env(p.env)
    where = f'{p.command} ({os.path.basename(p.env)})'
    if not COMMAND_RE.match(p.command):
        raise ImageError(f'{where}: a command is a capital letter and up to nine capitals or digits')
    if env.exit != (mapenv.EXIT_RETURN, KEEP) or env.output != mapenv.OUTPUT_RAW:
        raise ImageError(f'{where}: a program of the module needs `exit return $0400` and `output raw`')
    with open(p.image, 'rb') as fh:
        p.resident = fh.read()
    p.load = env.code[0]
    if not p.resident or p.load < 0x0800 or p.load + len(p.resident) > env.code[1] + 1:
        raise ImageError(f'{where}: the resident image must lie in the code range, from $0800')
    for name, (lo, hi) in (('code', env.code), ('data', env.data)):
        if lo <= TAIL[1] and hi >= TAIL[0]:
            raise ImageError(f'{where}: its {name} range ${lo:04X}-${hi:04X} takes $0700-$07FF, where '
                             f'the tail and the stub are while it runs')
    for n, words in mapenv.read_entries(p.env):
        if words[0].lower() == 'more' and len(words) == 4:
            lo, hi = mapenv._number(words[2], p.env), mapenv._number(words[3], p.env)
            if lo <= TAIL[1] and hi >= TAIL[0]:
                raise ImageError(f'{where}: its more data range ${lo:04X}-${hi:04X} takes '
                                 f'$0700-$07FF, where the tail and the stub are while it runs')
    if not env.banked():
        p.banks = []
        return p
    first, last, banks = read_env_banks(p.env)
    if (first, last) != (FIRST, LAST):
        raise ImageError(f'{where}: the window must be ${FIRST:04X}-${LAST:04X} (the reserved bytes of '
                         f'every bank are $8000-${FIRST - 1:04X}), not ${first:04X}-${last:04X}')
    beside = os.path.dirname(os.path.abspath(p.image))
    for b in banks:
        if b.value & 0x80:
            if b.value >= 0x80 + size:
                raise ImageError(f'{where}: bank {b.number} has the value ${b.value:02X}: a bank of the '
                                 f'module is $80 to ${0x7F + size:02X}')
            if b.value == 0x80 and size == BANKS:
                raise ImageError(f'{where}: bank {b.number} is bank 0 of the module ($80), which holds '
                                 f'the module\'s own code in the sixteen-bank image')
            if not b.rom:
                raise ImageError(f'{where}: bank {b.number} (${b.value:02X}) is not `rom`: in a ROM the '
                                 f'linker must keep its variables in main RAM')
            if b.file is None:
                raise ImageError(f'{where}: bank {b.number} (${b.value:02X}) has no file')
        elif b.value not in SIDEWAYS_RAM:
            raise ImageError(f'{where}: bank {b.number} is slot {b.value}, which is not sideways RAM '
                             f'(slots {", ".join(map(str, SIDEWAYS_RAM))})')
        if b.file is not None:
            path = os.path.join(beside, b.file)
            if not os.path.isfile(path):
                raise ImageError(f'{where}: its bank file {b.file} is not beside {p.image}')
            with open(path, 'rb') as fh:
                data = fh.read()
            if len(data) > LAST - FIRST + 1:
                raise ImageError(f'{where}: its bank file {b.file} is {len(data)} bytes, more than the '
                                 f'{LAST - FIRST + 1} of ${FIRST:04X}-${LAST:04X}')
            b.data = data
    p.banks = banks
    return p


# ---- The module's code ----------------------------------------------------------------------

def assemble(text, what='lathe/rt/bbc/module.asm'):
    """pyasm on text: (the bytes from its first address, the global labels)."""
    with tempfile.TemporaryDirectory(prefix='lathe-bbcrom-') as d:
        src, out = os.path.join(d, 'module.asm'), os.path.join(d, 'module.bin')
        with open(src, 'w') as fh:
            fh.write(text)
        a = pyasm.Assembler(src, out)
        try:
            a.run()
        except SystemExit as e:
            raise ImageError(f'{what} did not assemble ({e})') from None
        with open(out, 'rb') as fh:
            code = fh.read()
    return code, {k[1]: v for k, v in a.symbols.items() if k[0] == 'global'}


def tables(programs, lists, check_himem=False):
    """The asm text of the tables: the command table, the *HELP text and each command's copy
    list, [(source, destination, count, bank, unit)]. With check_himem each command's entry also
    has the top of its program's memory, which HIMEM must not be below."""
    out = ['commands:']
    for n, p in enumerate(programs):
        out += [f'  .byte "{p.command}", $00', f'  .word list_{n}', f'  .word ${p.load:04X}']
        if check_himem:
            out += [f'  .word ${p.top:04X}']
    out += ['  .byte $00', 'help_text:', '  .byte $0D', '  .byte "Lathe"', '  .byte $0D']
    for p in programs:
        out += [f'  .byte "  {p.command}"', '  .byte $0D']
    out += ['  .byte $00']
    for n, entries in enumerate(lists):
        out += [f'list_{n}:', f'  .byte {len(entries)}']
        for src, dst, count, bank, unit in entries:
            out += [f'  .word ${src:04X}', f'  .word ${dst:04X}', f'  .word ${count:04X}',
                    f'  .byte ${bank:02X}', f'  .byte ${unit:02X}']
    return '\n'.join(out) + '\n'


_tables = {}


def text_part(first, last, at, claim):
    """A part of the texts of the tools' errors, the texts first to last (lathe/rt/bbc/texts.asm
    with msgpack.py's tables of them), assembled to be at `at` in its bank, `claim` the module's
    return from a service call: its bytes."""
    if (first, last) not in _tables:
        _tables[(first, last)] = msgpack.tables(first, last)[0]
    with open(TEXTS_ASM) as fh:
        source = fh.read()
    code, labels = assemble(f'part_at: = ${at:04X}\nclaim: = ${claim:04X}\n' + source + _tables[(first, last)],
                            'lathe/rt/bbc/texts.asm')
    return code


def parts_table(parts):
    """The asm text of the table of the parts of the texts [(first text, bank, address)], in the
    order of their first texts, for module.asm's `text`."""
    out = [f'text_parts: = {len(parts)}', 'part_first:']
    out += [f'  .byte {first}' for first, bank, at in parts]
    out += ['part_bank:'] + [f'  .byte ${bank:02X}' for first, bank, at in parts]
    out += ['part_entry_low:'] + [f'  .byte ${(at - 1) & 0xFF:02X}' for first, bank, at in parts]
    out += ['part_entry_high:'] + [f'  .byte ${(at - 1) >> 8:02X}' for first, bank, at in parts]
    return '\n'.join(out) + '\n'


def module_code(programs, lists, home=0, at=FIRST, parts=((0, 0, FIRST),)):
    """The module's code assembled with its home bank `home` and its code and tables at `at` there,
    with the check of HIMEM if a program has a top (image(check_himem=True)), and the table of the
    parts of the texts of the errors, [(first text, bank, address)]: (the reserved bytes, the code
    and tables, the global labels)."""
    with open(MODULE_ASM) as fh:
        source = fh.read()
    check_himem = any(p.top for p in programs)
    head = f'home: = ${home:02X}\nhome_at: = ${at:04X}\n'
    head += 'check_himem: = $01\nentry_rest: = $07\n' if check_himem else 'entry_rest: = $05\n'
    at_home = len(parts) == 1 and parts[0][1] == home
    if at_home:
        head += f'part_at_home: = ${parts[0][2]:04X}\n'     # the one part is in the home bank: no table
    else:
        head += 'parts_away: = $01\n' + ('several_parts: = $01\n' if len(parts) > 1 else 'one_part_away: = $01\n')
    code, labels = assemble(head + source + tables(programs, lists, check_himem)
                            + ('' if at_home else parts_table(parts)))
    if labels['reserved_end'] != FIRST or len(code) > LAST - WINDOW + 1:
        raise ImageError(f'module.asm: the reserved bytes must end at ${FIRST:04X}, and its code fit a bank')
    return code[:RESERVED], code[at - WINDOW:], labels


# ---- The image ------------------------------------------------------------------------------

def over_error(text, over):
    e = ImageError(text)
    e.over = over
    return e


def place(blobs, areas, skip=True):
    """Lays the blobs [(what, bytes, unit, destination)] in the free areas [[bank, first, last]]
    in order, splitting one over areas where it must, in pieces (each an entry of 8 bytes in a
    copy list): with skip, an area with ENTRY bytes left or fewer is passed over unless the rest
    fits it, since a piece there would cost the home bank's table as much as it holds. Returns [(what,
    bank, address, bytes, unit, destination)]; ImageError if they do not fit, with .over the
    bytes over."""
    placed, i = [], 0
    for k, (what, data, unit, dest) in enumerate(blobs):
        done = 0
        while done < len(data):
            while i < len(areas) and (areas[i][2] < areas[i][1] or skip
                                      and areas[i][2] - areas[i][1] + 1 < len(data) - done
                                      and areas[i][2] - areas[i][1] + 1 <= ENTRY):
                i += 1
            if i == len(areas):
                need = sum(len(b[1]) for b in blobs)
                over = len(data) - done + sum(len(b[1]) for b in blobs[k + 1:])
                e = over_error(f'the resident parts and region constants ({need} bytes) do not fit in '
                               f'the banks the programs leave free: {over} bytes over', over)
                e.pieces = len(placed)          # the entries a fit would take, at least
                raise e
            bank, first, last = areas[i]
            n = min(len(data) - done, last - first + 1)
            placed.append((what, bank, first, data[done:done + n], unit, dest + done))
            areas[i][1] += n
            done += n
    return placed


@dataclass
class Layout:
    banks: int                  # 16 (direct16) or 8 (direct8)
    owner: dict                 # bank -> whose code it holds
    code_end: dict              # bank -> the first address after the program's code in it
    home: int = 0               # the home bank
    home_at: int = FIRST        # where the module's code and tables are in it
    parts: list = field(default_factory=list)   # the texts of the errors: [(first, last, bank, address, bytes)]
    reserved: bytes = b''       # $8000-$804F of every bank (its number at $804F apart)
    code: bytes = b''           # the module's code and tables
    placed: list = field(default_factory=list)
    areas: list = field(default_factory=list)   # what is left free, [[bank, first, last]]


def layout(programs, banks=BANKS, tails=None, parts=1):
    """Where everything goes (lathe/docs/bbc.md, "The 128 KB module"): each program's code in its
    banks from $8050; the module's code and tables in the home bank, after the code there (bank
    0, at $8050, in the sixteen-bank image, where no program may use bank 0; with tails the bank
    with the most room of those up to the last program's, or the first empty bank); then the programs'
    region constants and resident parts, in pieces.

    With tails (the eight-bank image's way, and the default there), the pieces go in the room
    left at the ends of the banks, to $BFEF: first in the banks the image holds anyway (the home
    bank and every bank up to the last program's), the one with the most room first, then in the
    banks after them in order, so that the image uses as few banks as it can. Without it (the
    sixteen-bank image's default, which it had before the eight-bank one), in the home bank to
    $BFDF and then in the banks no program's code is in, in order.

    The texts of the Lathe tools' errors (msgpack.py) go in `parts` parts or more, as few as fit
    (at most MOST_PARTS), each whole in one bank, before the pieces: one part in the home bank if
    it has room, else wherever there is (module.asm, "An error's text"; texts.asm).

    Returns a Layout; ImageError (with .over, the bytes over) if they do not fit."""
    if tails is None:
        tails = banks != BANKS
    owner, code_end = {}, {}
    for p in programs:
        for b in p.banks:
            if b.value & 0x80:
                n = b.value & 0x7F
                if n in owner:
                    raise ImageError(f'bank {n} of the module is {owner[n]}\'s and {p.command}\'s too: '
                                     f'number their banks apart (bbcrom.rom_env)')
                owner[n] = f'{p.command} (its bank {b.number}, {b.file})'
                code_end[n] = FIRST + len(b.data)
    blobs = []
    for p in programs:
        for b in p.banks:
            if not b.value & 0x80 and b.file is not None:
                blobs.append((f'{p.command} slot {b.value} ({b.file})', b.data, b.value, FIRST))
        blobs.append((f'{p.command} resident', p.resident, MAIN_RAM, p.load))
    lay = Layout(banks, owner, code_end)
    starts = {n: code_end.get(n, FIRST) for n in range(banks)}
    if not tails:
        lay.home = 0
    else:
        # The bank with the most room of those the image holds anyway (every bank up to the last
        # program's), if the code with no pieces fits it; else the first bank no program uses.
        smallest = len(module_code(programs, [[] for _ in programs])[1])
        held = range(max(owner) + 1 if owner else 1)
        lay.home = max(held, key=lambda n: (LAST - starts[n], -n))
        if LAST - starts[lay.home] + 1 < smallest + 4 * ENTRY:
            lay.home = min([n for n in range(banks) if n not in owner] or [lay.home])
    lay.home_at = starts[lay.home]
    last_held = max([lay.home] + list(owner))

    def areas_after(size):
        if not tails:
            return [[lay.home, lay.home_at + size, LAST]] + [[n, FIRST, LAST] for n in range(banks)
                                                              if n not in owner and n != lay.home]
        held = [[n, starts[n] + (size if n == lay.home else 0), TOP] for n in range(last_held + 1)]
        return in_order(held + [[n, FIRST, TOP] for n in range(last_held + 1, banks)])

    def in_order(areas):
        """With tails, the areas in the order the pieces take them: those of the banks the image
        holds anyway, the one with the most room left first, then the banks after them in order."""
        if tails:
            areas.sort(key=lambda a: (a[0] > last_held, a[0] if a[0] > last_held else a[1] - a[2], a[0]))
        return areas

    # The texts of the errors go in parts, each whole in one bank, wherever there is room: in as
    # few as fit (msgpack.split), each the code of texts.asm and its own tables.
    for count in range(parts, MOST_PARTS + 1):
        ranges = msgpack.split(count)
        try:
            size = settle(lay, programs, blobs, tails, ranges, areas_after, in_order)
            break
        except PartsError as e:
            if count == MOST_PARTS:
                raise over_error(f'the texts of the errors do not fit in {MOST_PARTS} parts in the room the '
                                 f'banks leave: a part of {e.size} bytes has no room', e.size) from None
    if len(lay.code) < size:                # a piece fewer than laid out for: a gap after the tables
        lay.code += bytes([FILL]) * (size - len(lay.code))
    return lay


class PartsError(Exception):
    def __init__(self, size):
        self.size = size


def place_parts(ranges, areas, claim, home):
    """Each part of the texts (ranges [(first, last)]), the largest first, whole at the start of
    an area: the home bank's if it holds it (a part there is entered with a JMP and needs no table),
    else the first area that holds it, in the order the pieces take the areas (so that the parts
    and the pieces fill the same areas first): [(first, last, bank, address, bytes)] in the order
    of the ranges. PartsError if one has no room."""
    sizes = [len(text_part(first, last, FIRST, claim)) for first, last in ranges]
    found = [None] * len(ranges)
    for k in sorted(range(len(ranges)), key=lambda k: -sizes[k]):
        fits = [a for a in areas if a[2] - a[1] + 1 >= sizes[k]]
        if not fits:
            raise PartsError(sizes[k])
        area = ([a for a in fits if a[0] == home] + fits)[0]
        first, last = ranges[k]
        found[k] = (first, last, area[0], area[1], text_part(first, last, area[1], claim))
        area[1] += sizes[k]
    return found


def settle(lay, programs, blobs, tails, ranges, areas_after, in_order):
    """The module's code, the parts of the texts (ranges) and the pieces laid out in lay until the
    code's size settles: returns that size. The code depends on the copy lists only through their
    length (the number of pieces) and on the parts only through their number; the pieces and the
    parts on the room the code leaves: lay it out with none, then again until it settles."""
    lists = [[] for _ in programs]
    parts = [(first, lay.home, lay.home_at) for first, last in ranges]    # one part: in the home bank, if it fits
    size = None
    for _ in range(8):
        lay.reserved, lay.code, labels = module_code(programs, lists, lay.home, lay.home_at, parts)
        if size is not None and len(lay.code) <= size:
            return size
        size = len(lay.code)
        if lay.home_at + size - 1 > LAST:
            over = lay.home_at + size - 1 - LAST
            raise over_error(f'the module\'s code and tables ({size} bytes) do not fit bank {lay.home} after '
                             f'its program\'s code: {over} bytes over', over)
        lay.areas = areas_after(size)
        lay.parts = place_parts(ranges, lay.areas, labels['claim'], lay.home)
        in_order(lay.areas)             # the parts took room: the pieces take what is left
        parts = [(first, bank, at) for first, last, bank, at, data in lay.parts]
        try:
            lay.placed = place(blobs, lay.areas, tails)
        except ImageError as e:
            # Over: each piece it would take has an entry in the tables, which take room too.
            e.over += ENTRY * max(0, e.pieces - sum(map(len, lists)))
            e.args = (re.sub(r'\d+ bytes over', f'{e.over} bytes over', e.args[0]),)
            raise
        lists = [[(addr, dest, len(data), bank, unit)
                  for what, bank, addr, data, unit, dest in lay.placed if what.startswith(p.command + ' ')]
                 for p in programs]
    raise ImageError('the home bank did not settle')


def image(specs, out, listing=None, short=None, banks=BANKS, tails=None, check_himem=True, parts=1):
    """Writes the module image `out` (banks of 16 KB: sixteen, 262,144 bytes, scheme direct16, or
    eight, 131,072 bytes, scheme direct8) for the programs specs, [(command, resident image,
    environment[, map])], and the listing (text) to `listing` if given; with `short`, also the
    image's banks from 0 to the last one in use (the home bank, a program's code or a piece), to
    that file; tails and parts as layout() has them. With check_himem (the default) a command is refused with the MOS error
    `Mode 7 needed` when HIMEM is below the top of its program's memory (the end of the highest
    of its `code`, `data` and `more` ranges, + 1): module.asm, step 0. Returns the listing."""
    if banks not in SCHEMES:
        raise ImageError(f'an image has 16 or 8 banks, not {banks}')
    programs = [load_program(Program(s[0].upper(), s[1], s[2], s[3] if len(s) > 3 else None), banks)
                for s in specs]
    if not programs:
        raise ImageError('no program')
    if check_himem:
        for p in programs:
            p.top = memory_top(p.env)
    for p in programs:
        if [q.command for q in programs].count(p.command) > 1:
            raise ImageError(f'the command {p.command} is given twice')
    lay = layout(programs, banks, tails, parts)
    data = [bytearray([FILL]) * BANK_SIZE for _ in range(banks)]
    for n in range(banks):
        data[n][:RESERVED] = lay.reserved
        data[n][NUMBER_AT] = n
    at = lay.home_at - WINDOW
    data[lay.home][at:at + len(lay.code)] = lay.code
    for first, last, bank, addr, part in lay.parts:
        data[bank][addr - WINDOW:addr - WINDOW + len(part)] = part
    for p in programs:
        for b in p.banks:
            if b.value & 0x80:
                data[b.value & 0x7F][RESERVED:RESERVED + len(b.data)] = b.data
    for what, bank, addr, piece, unit, dest in lay.placed:
        data[bank][addr - WINDOW:addr - WINDOW + len(piece)] = piece
    with open(out, 'wb') as fh:
        fh.write(b''.join(data))
    used = max([lay.home] + list(lay.owner) + [e[1] for e in lay.placed] + [e[2] for e in lay.parts])
    if short:
        with open(short, 'wb') as fh:
            fh.write(b''.join(data[:used + 1]))
    text = describe(out, programs, lay)
    text += f'banks in use: 0 to {used}, {(used + 1) * BANK_SIZE} bytes (--short)\n'
    if listing:
        with open(listing, 'w') as fh:
            fh.write(text)
    return text


def describe(out, programs, lay):
    """The listing: what is where, bank by bank, and what each command copies."""
    banks = lay.banks
    lines = [f'Lathe module image {os.path.basename(out)}: {banks} banks of 16 KB, scheme {SCHEMES[banks]}, '
             f'{banks * BANK_SIZE} bytes',
             f'every bank: $8000-${FIRST - 1:04X} the header and service code (module.asm), '
             f'${WINDOW + NUMBER_AT:04X} the bank\'s number', '']
    for n in range(banks):
        parts = []
        for p in programs:
            for b in p.banks:
                if b.value == 0x80 + n:
                    parts.append(f'${FIRST:04X}-${FIRST + len(b.data) - 1:04X} {p.command} bank {b.number} '
                                 f'code and constants ({b.file}, {len(b.data)} bytes)')
        if n == lay.home:
            parts.append(f'${lay.home_at:04X}-${lay.home_at + len(lay.code) - 1:04X} the module\'s code and '
                         f'tables ({len(lay.code)} bytes)')
        for first, last, bank, addr, part in lay.parts:
            if bank == n:
                parts.append(f'${addr:04X}-${addr + len(part) - 1:04X} the texts {first} to {last} of the errors '
                             f'({len(part)} bytes)')
        for what, bank, addr, data, unit, dest in sorted(lay.placed, key=lambda e: e[2]):
            if bank == n:
                parts.append(f'${addr:04X}-${addr + len(data) - 1:04X} {what}, to '
                             + (f'${dest:04X}' if unit == MAIN_RAM else f'slot {unit} ${dest:04X}')
                             + f' ({len(data)} bytes)')
        free = sum(a[2] - a[1] + 1 for a in lay.areas if a[0] == n)
        lines.append(f'bank {n:2d}: ' + ('; '.join(parts) if parts else 'empty')
                     + (f'; {free} bytes free' if free else ''))
    lines.append('')
    for p in programs:
        regions = [f'slot {b.value}' + (f' ({b.file})' if b.file else '') for b in p.banks
                   if not b.value & 0x80]
        pieces = sum(1 for e in lay.placed if e[0].startswith(p.command + ' '))
        lines.append(f'*{p.command}: {os.path.basename(p.image)}, {len(p.resident)} bytes resident at '
                     f'${p.load:04X}-${p.load + len(p.resident) - 1:04X}, entered at ${p.load:04X}; banks '
                     + (', '.join(str(b.value & 0x7F) for b in p.banks if b.value & 0x80) or 'none')
                     + '; regions in ' + (', '.join(regions) or 'none') + f'; {pieces} pieces copied')
        if p.map:
            entries = mapenv.read_map(p.map)
            fixed = [e for e in entries if e.kind == 'V' and e.bank is None and e.addr >= 0x0100]
            if fixed:
                lines.append(f'    variables in main RAM: {sum(e.size for e in fixed)} bytes, to '
                             f'${max(e.addr + e.size for e in fixed) - 1:04X}')
    total = sum(a[2] - a[1] + 1 for a in lay.areas)
    lines.append(f'free: {total} bytes')
    return '\n'.join(lines) + '\n'


# ---- The developer's loader -----------------------------------------------------------------

def loader(out, load=LOADER_LOAD):
    """Writes LOADMOD (lathe/rt/bbc/loadmod.asm) to `out`, and its .inf file beside it (load and
    execution address $1900), as *RUN reads them: `*RUN LOADMOD IMAGE [SLOT]` fills the module's
    developer form (RAM) from an image this tool wrote. Returns its length.

    With `load`, a page other than $1900 (ADFS's PAGE, $1F00: lathe/docs/bbc.md, "ADFS"), it is
    assembled to be loaded and entered there, and its buffer for a bank is the 16 KB from
    load + $0700 ($2000 for $1900, as the source says)."""
    with open(LOADER_ASM) as fh:
        text = fh.read()
    if load != LOADER_LOAD:
        if load & 0xFF or not 0x0E00 <= load <= 0x3F00:
            raise ImageError(f'LOADMOD is loaded at a page from $0E00 to $3F00, not ${load:04X}')
        for old, new in ((f'* = ${LOADER_LOAD:04X}\n', f'* = ${load:04X}\n'),
                         ('buffer: = $2000\n', f'buffer: = ${load + 0x0700:04X}\n')):
            assert text.count(old) == 1, old
            text = text.replace(old, new)
    code, labels = assemble(text, 'lathe/rt/bbc/loadmod.asm')
    with open(out, 'wb') as fh:
        fh.write(code)
    name = os.path.basename(out)
    with open(out + '.inf', 'w') as fh:
        fh.write(f'{name} {load:08X} {load:08X} {len(code):08X}\n')
    return len(code)


# ---- A program's environment for the ROM form ----------------------------------------------

def rom_env(source, out, first=1, banks=BANKS, settings=None):
    """Writes to `out` the ROM form of the environment `source` (a program's *RUN environment,
    such as lathe/env/bbc-bank.env with the program's lines): the window $8050-$BFDF, each bank
    of the module ($8n) renumbered, in the order of the `bank` lines, as banks first, first + 1,
    ... of an image of `banks` banks, and `rom` for each. Returns the next bank number free.

    The source defines ROMFORM as 0 and the result as 1, so that `when ROMFORM ENTRY` is an
    entry of the ROM form only and `unless ROMFORM ENTRY` of the developer's form only
    (configurations.md, "The environment file"). The tools use it for what the developer's form
    must keep fixed only because its start-up loads the banks, such as `bbcfs`, which `bbc.open`
    calls (lathe/docs/bbc.md, "File names on the BBC"). In the same way, for an image of eight
    banks (the 128 KB module, scheme direct8) a source's `define ROM128 0` becomes 1, so that
    `when ROM128` and `unless ROM128` entries give what differs there (a tool in fewer banks:
    lathe/docs/bbc.md, "The 128 KB module"). A `bank` entry of the module under `when` or
    `unless` is renumbered if it is an entry of the result, and left as it is if not.

    `settings` ({NAME: number}) sets the value of a source's `define NAME N` in the same way, for
    a variant the source describes under a define of its own: {'RAM32': 1} for the tools' 32K
    Model B form (lathe/docs/bbc.md, "The 32K Model B"). A name the source does not define is an
    error."""
    if banks not in SCHEMES:
        raise ImageError(f'an image has 16 or 8 banks, not {banks}')
    lines, roms, n = [], [], first
    defined = {}
    settings = {name.lower(): value for name, value in (settings or {}).items()}
    unset = set(settings)
    with open(source) as fh:
        for line in fh:
            words = line.split(';', 1)[0].split()
            if len(words) == 3 and words[0].lower() == 'define' and words[1].lower() in settings:
                line = re.sub(r'(?i)^(\s*define\s+\w+\s+)\S+', r'\g<1>%d' % settings[words[1].lower()], line,
                              count=1)
                unset.discard(words[1].lower())
            elif [w.lower() for w in words[:2]] == ['define', 'romform'] and len(words) == 3:
                line = re.sub(r'(?i)(romform\s+)\S+', r'\g<1>1', line, count=1)
            elif [w.lower() for w in words[:2]] == ['define', 'rom128'] and len(words) == 3:
                line = re.sub(r'(?i)(rom128\s+)\S+', r'\g<1>' + ('1' if banks == 8 else '0'), line, count=1)
            entry = _active(words, defined)
            if entry and entry[0].lower() == 'define' and len(entry) in (2, 3):
                value = line.split(';', 1)[0].split()[-1] if len(entry) == 3 else '1'
                defined[entry[1].lower()] = len(entry) == 2 or mapenv._number(value, source) != 0
            if entry and entry[0].lower() == 'window' and len(entry) == 4:
                line = f'window    {entry[1]} ${FIRST:04X} ${LAST:04X}\n'
            elif entry and entry[0].lower() == 'bank' and len(entry) in (4, 5) \
                    and mapenv._number(entry[3], source) & 0x80:
                if n >= banks:
                    raise ImageError(f'{source}: no bank of the module is left for its bank {entry[2]} '
                                     f'(an image has {banks})')
                line = (f'bank      {entry[1]} {entry[2]} ${0x80 + n:02X}'
                        + (f' {entry[4]}' if len(entry) == 5 else '') + '\n')
                roms.append(f'rom       {entry[1]} {entry[2]}\n')
                n += 1
            lines.append(line)
    if unset:
        raise ImageError(f'{source}: no define of {", ".join(sorted(unset)).upper()} to set')
    with open(out, 'w') as fh:
        fh.write(''.join(lines) + ''.join(roms))
    return n


def _active(words, defined):
    """The entry `words` is, its `when` and `unless` resolved with the defines so far (of the
    result: ROMFORM and ROM128 as rom_env writes them), or None if it is not an entry there."""
    while words and words[0].lower() in ('when', 'unless') and len(words) > 2:
        on = defined.get(words[1].lower())
        if on is None or on != (words[0].lower() == 'when'):
            return None
        words = words[2:]
    return words


def main(argv):
    ap = argparse.ArgumentParser(prog='bbcrom.py', description='Write a Lathe module image for the BBC.')
    ap.add_argument('-o', dest='out', required=True, help='the image file')
    ap.add_argument('--listing', help='where to write the listing (else standard output)')
    ap.add_argument('--loader', metavar='FILE', help='also write the developer\'s loader, LOADMOD, '
                    'to FILE (and FILE.inf)')
    ap.add_argument('--short', metavar='FILE', help='also write the banks in use alone to FILE, '
                    'for LOADMOD on a disc')
    ap.add_argument('--banks', type=int, choices=sorted(SCHEMES), default=BANKS,
                    help='16 (scheme direct16, the default) or 8 (direct8, a 128 KB EPROM)')
    ap.add_argument('--tails', action='store_true', help='put the resident parts and region constants in '
                    'the ends of the code banks too (the eight-bank image does so anyway)')
    ap.add_argument('--no-check-himem', action='store_true', help='do not refuse a command when HIMEM is '
                    'below its program\'s memory (by default the MOS error Mode 7 needed)')
    ap.add_argument('programs', nargs='+', metavar='COMMAND=PROGRAM,ENV[,MAP]')
    a = ap.parse_args(argv)
    specs = []
    for spec in a.programs:
        command, eq, rest = spec.partition('=')
        parts = rest.split(',')
        if not eq or len(parts) not in (2, 3):
            sys.stderr.write(f'bbcrom: {spec}: give COMMAND=PROGRAM,ENV[,MAP]\n')
            return 2
        specs.append([command] + parts)
    try:
        text = image(specs, a.out, a.listing, a.short, a.banks, a.tails or None, not a.no_check_himem)
        if a.loader:
            loader(a.loader)
    except (ImageError, mapenv.FormatError, OSError) as e:
        sys.stderr.write(f'bbcrom: {e}\n')
        return 1
    if not a.listing:
        sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
