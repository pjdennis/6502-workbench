#!/usr/bin/env python3
"""The image of a Lathe module for the BBC Model B+128: one file of sixteen 16 KB banks (262,144
bytes, scheme direct16), which holds one or more programs, each started by a * command
(lathe/docs/bbc.md, "Step 3, as built: the ROM form").

    python3 lathe/host/driver/bbcrom.py -o IMAGE [--listing FILE] [--loader FILE]
                                        COMMAND=PROGRAM,ENV[,MAP]...

Each program is linked on its own, by build.py, with an environment of its own (rom_env() makes
one from a program's *RUN environment): lathe/env/bbc-rom.env's machine, its banks of the module
`rom`, the window $8050-$BFDF. PROGRAM is its resident image (build.py's output: its fixed code
and constants, from its load address, the start of the environment's `code` range), and its bank
files are beside it (build.py copies them there). MAP is its map, for the listing.

What goes where:

- Every bank: the reserved bytes $8000-$804F of lathe/rt/bbc/module.asm (the sideways ROM header
  and the service code; $804F holds the bank's own number).
- Bank 0: the module's own code and tables after them, then resident parts as far as they fit.
- The banks of the programs' code: each bank file of the module ($80 + n in its `bank` entry)
  in bank n, from $8050.
- The banks no program's code is in, in order: the rest of the resident parts and the constants
  of the programs' regions (a region bank's file), which bank 0 copies at the * command into main
  RAM and the sideways RAM slots.

Bank numbers. A program's bank of the module is bank n of the image where its environment says
`bank WIN N $8n FILE`; the environment chooses, and this tool checks: every such bank must be
`rom`, its number 1 to 15 (bank 0 is the module's), used by one program only, and its file must
fit $8050-$BFDF. rom_env() numbers a program's banks of the module from a first bank given, in
the order of its `bank` lines, and returns the next: so a set of programs numbered one after the
other from 1 never collides. The resident parts are placed after the programs are linked, in the
banks left over, so no number of a program's bank can collide with them.

--loader also writes the developer's loader (lathe/rt/bbc/loadmod.asm), which fills the module's
RAM form from the image: `*RUN LOADMOD IMAGE [SLOT]`.

image() and loader() are the functions the tests call; ImageError says what does not fit or
collides.
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
import pyasm  # noqa: E402

MODULE_ASM = os.path.join(ROOT, 'lathe', 'rt', 'bbc', 'module.asm')
LOADER_ASM = os.path.join(ROOT, 'lathe', 'rt', 'bbc', 'loadmod.asm')
LOADER_LOAD = 0x1900                    # LOADMOD is loaded and entered at PAGE
BANKS = 16
BANK_SIZE = 0x4000
IMAGE_SIZE = BANKS * BANK_SIZE
WINDOW = 0x8000
RESERVED = 0x50                         # $8000-$804F in every bank
NUMBER_AT = 0x4F                        # the bank's own number, the last reserved byte
FIRST = WINDOW + RESERVED               # $8050: the window of a program's banks starts here
LAST = 0xBFDF                           # ... and ends here, as the developer's form's
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


def read_env_banks(path):
    """(window first, window last, [Bank]) of an environment file's `window`, `bank` and `rom`
    entries (the window named in its `bank` entries)."""
    windows, banks = {}, []
    with open(path) as fh:
        lines = list(mapenv._lines(fh.read()))
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


def load_program(p):
    """Reads a program's environment, resident image and bank files, and checks them."""
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
    with open(p.env) as fh:
        for n, words in mapenv._lines(fh.read()):
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
            if b.value > 0x8F:
                raise ImageError(f'{where}: bank {b.number} has the value ${b.value:02X}: a bank of the '
                                 f'module is $80 to $8F')
            if b.value == 0x80:
                raise ImageError(f'{where}: bank {b.number} is bank 0 of the module ($80), which holds '
                                 f'the module\'s own code')
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


def tables(programs, lists):
    """The asm text of the tables: the command table, the *HELP text and each command's copy
    list, [(source, destination, count, bank, unit)]."""
    out = ['commands:']
    for n, p in enumerate(programs):
        out += [f'  .byte "{p.command}", $00', f'  .word list_{n}', f'  .word ${p.load:04X}']
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


def module_code(programs, lists):
    with open(MODULE_ASM) as fh:
        source = fh.read()
    code, labels = assemble(source + tables(programs, lists))
    if labels['reserved_end'] != FIRST or len(code) > LAST - WINDOW + 1:
        raise ImageError(f'module.asm: the reserved bytes must end at ${FIRST:04X}, and bank 0 fit')
    return code, labels


# ---- The image ------------------------------------------------------------------------------

def place(blobs, areas):
    """Lays the blobs [(what, bytes, unit, destination)] in the free areas [[bank, first, last]]
    in order, splitting one over areas where it must. Returns [(what, bank, address, bytes, unit,
    destination)]; ImageError if they do not fit."""
    placed, i = [], 0
    for what, data, unit, dest in blobs:
        done = 0
        while done < len(data):
            while i < len(areas) and areas[i][1] > areas[i][2]:
                i += 1
            if i == len(areas):
                need = sum(len(b[1]) for b in blobs)
                raise ImageError(f'the resident parts and region constants ({need} bytes) do not fit in '
                                 f'the banks the programs leave free: {what} is '
                                 f'{len(data) - done} bytes over')
            bank, first, last = areas[i]
            n = min(len(data) - done, last - first + 1)
            placed.append((what, bank, first, data[done:done + n], unit, dest + done))
            areas[i][1] += n
            done += n
    return placed


def image(specs, out, listing=None):
    """Writes the module image `out` (262,144 bytes) for the programs specs, [(command, resident
    image, environment[, map])], and the listing (text) to `listing` if given. Returns the
    listing."""
    programs = [load_program(Program(s[0].upper(), s[1], s[2], s[3] if len(s) > 3 else None))
                for s in specs]
    if not programs:
        raise ImageError('no program')
    owner = {}
    for p in programs:
        if [q.command for q in programs].count(p.command) > 1:
            raise ImageError(f'the command {p.command} is given twice')
        for b in p.banks:
            if b.value & 0x80:
                n = b.value & 0x0F
                if n in owner:
                    raise ImageError(f'bank {n} of the module is {owner[n]}\'s and {p.command}\'s too: '
                                     f'number their banks apart (bbcrom.rom_env)')
                owner[n] = f'{p.command} (its bank {b.number}, {b.file})'
    blobs = []
    for p in programs:
        for b in p.banks:
            if not b.value & 0x80 and b.file is not None:
                blobs.append((f'{p.command} slot {b.value} ({b.file})', b.data, b.value, FIRST))
        blobs.append((f'{p.command} resident', p.resident, MAIN_RAM, p.load))
    # Bank 0's code depends on the copy lists only through their length: lay it out once with
    # empty lists of the right length, then for good.
    dummy = [[(0, 0, 1, 0, 0)] * 64 for _ in programs]
    code, labels = module_code(programs, dummy)
    lists = None
    for _ in range(4):
        areas = [[0, WINDOW + len(code), LAST]] + [[n, FIRST, LAST] for n in range(1, BANKS)
                                                   if n not in owner]
        placed = place(blobs, areas)
        lists = [[(addr, dest, len(data), bank, unit)
                  for what, bank, addr, data, unit, dest in placed if what.startswith(p.command + ' ')]
                 for p in programs]
        new_code, labels = module_code(programs, lists)
        if len(new_code) == len(code):
            code = new_code
            break
        code = new_code
    else:
        raise ImageError('bank 0 did not settle')
    banks = [bytearray([FILL]) * BANK_SIZE for _ in range(BANKS)]
    for n in range(BANKS):
        banks[n][:RESERVED] = code[:RESERVED]
        banks[n][NUMBER_AT] = n
    banks[0][:len(code)] = code
    banks[0][NUMBER_AT] = 0
    for p in programs:
        for b in p.banks:
            if b.value & 0x80:
                n = b.value & 0x0F
                banks[n][RESERVED:RESERVED + len(b.data)] = b.data
    for what, bank, addr, data, unit, dest in placed:
        banks[bank][addr - WINDOW:addr - WINDOW + len(data)] = data
    with open(out, 'wb') as fh:
        fh.write(b''.join(banks))
    text = describe(out, programs, code, owner, placed, areas)
    if listing:
        with open(listing, 'w') as fh:
            fh.write(text)
    return text


def describe(out, programs, code, owner, placed, areas):
    """The listing: what is where, bank by bank, and what each command copies."""
    lines = [f'Lathe module image {os.path.basename(out)}: {BANKS} banks of 16 KB, scheme direct16, '
             f'{IMAGE_SIZE} bytes',
             f'every bank: $8000-${FIRST - 1:04X} the header and service code (module.asm), '
             f'${WINDOW + NUMBER_AT:04X} the bank\'s number', '']
    for n in range(BANKS):
        parts = []
        if n == 0:
            parts.append(f'${FIRST:04X}-${WINDOW + len(code) - 1:04X} the module\'s code and tables '
                         f'({len(code) - RESERVED} bytes)')
        for p in programs:
            for b in p.banks:
                if b.value == 0x80 + n:
                    parts.append(f'${FIRST:04X}-${FIRST + len(b.data) - 1:04X} {p.command} bank {b.number} '
                                 f'code and constants ({b.file}, {len(b.data)} bytes)')
        for what, bank, addr, data, unit, dest in placed:
            if bank == n:
                parts.append(f'${addr:04X}-${addr + len(data) - 1:04X} {what}, to '
                             + (f'${dest:04X}' if unit == MAIN_RAM else f'slot {unit} ${dest:04X}')
                             + f' ({len(data)} bytes)')
        free = sum(a[2] - a[1] + 1 for a in areas if a[0] == n)
        lines.append(f'bank {n:2d}: ' + ('; '.join(parts) if parts else 'empty')
                     + (f'; {free} bytes free' if free else ''))
    lines.append('')
    for p in programs:
        regions = [f'slot {b.value}' + (f' ({b.file})' if b.file else '') for b in p.banks
                   if not b.value & 0x80]
        lines.append(f'*{p.command}: {os.path.basename(p.image)}, {len(p.resident)} bytes resident at '
                     f'${p.load:04X}-${p.load + len(p.resident) - 1:04X}, entered at ${p.load:04X}; banks '
                     + (', '.join(str(b.value & 0x0F) for b in p.banks if b.value & 0x80) or 'none')
                     + '; regions in ' + (', '.join(regions) or 'none'))
        if p.map:
            entries = mapenv.read_map(p.map)
            fixed = [e for e in entries if e.kind == 'V' and e.bank is None and e.addr >= 0x0100]
            if fixed:
                lines.append(f'    variables in main RAM: {sum(e.size for e in fixed)} bytes, to '
                             f'${max(e.addr + e.size for e in fixed) - 1:04X}')
    total = sum(a[2] - a[1] + 1 for a in areas)
    lines.append(f'free: {total} bytes')
    return '\n'.join(lines) + '\n'


# ---- The developer's loader -----------------------------------------------------------------

def loader(out):
    """Writes LOADMOD (lathe/rt/bbc/loadmod.asm) to `out`, and its .inf file beside it (load and
    execution address $1900), as *RUN reads them: `*RUN LOADMOD IMAGE [SLOT]` fills the module's
    developer form (RAM) from an image this tool wrote. Returns its length."""
    with open(LOADER_ASM) as fh:
        code, labels = assemble(fh.read(), 'lathe/rt/bbc/loadmod.asm')
    with open(out, 'wb') as fh:
        fh.write(code)
    name = os.path.basename(out)
    with open(out + '.inf', 'w') as fh:
        fh.write(f'{name} {LOADER_LOAD:08X} {LOADER_LOAD:08X} {len(code):08X}\n')
    return len(code)


# ---- A program's environment for the ROM form ----------------------------------------------

def rom_env(source, out, first=1):
    """Writes to `out` the ROM form of the environment `source` (a program's *RUN environment,
    such as lathe/env/bbc-bank.env with the program's lines): the window $8050-$BFDF, each bank
    of the module ($8n) renumbered, in the order of the `bank` lines, as banks first, first + 1,
    ... of the image, and `rom` for each. Returns the next bank number free."""
    lines, roms, n = [], [], first
    with open(source) as fh:
        for line in fh:
            words = line.split(';', 1)[0].split()
            if words and words[0].lower() == 'window' and len(words) == 4:
                line = f'window    {words[1]} ${FIRST:04X} ${LAST:04X}\n'
            elif words and words[0].lower() == 'bank' and len(words) in (4, 5) \
                    and mapenv._number(words[3], source) & 0x80:
                if n >= BANKS:
                    raise ImageError(f'{source}: no bank of the module is left for its bank {words[2]}')
                line = (f'bank      {words[1]} {words[2]} ${0x80 + n:02X}'
                        + (f' {words[4]}' if len(words) == 5 else '') + '\n')
                roms.append(f'rom       {words[1]} {words[2]}\n')
                n += 1
            lines.append(line)
    with open(out, 'w') as fh:
        fh.write(''.join(lines) + ''.join(roms))
    return n


def main(argv):
    ap = argparse.ArgumentParser(prog='bbcrom.py', description='Write a Lathe module image for the BBC.')
    ap.add_argument('-o', dest='out', required=True, help='the image file')
    ap.add_argument('--listing', help='where to write the listing (else standard output)')
    ap.add_argument('--loader', metavar='FILE', help='also write the developer\'s loader, LOADMOD, '
                    'to FILE (and FILE.inf)')
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
        text = image(specs, a.out, a.listing)
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
