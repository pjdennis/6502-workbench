"""The emulated boards a Lathe program can run on, and how to read what it showed.

Everything the driver knows about a board is in BOARDS (lathe/docs/boards.md has the recipe
behind each entry). A board program is linked with `output raw` and `exit stop`: the file is
the code from the start of the environment's `code` range, which is the load address and
where the emulator starts it, and the run ends at the STP the start-up code ends with. The
program's output is the text on the board's LCD, which the emulator's exit report prints.

A board with `disk` set (wendy2disk) is Wendy 2 run with `--disk DIR`: the emulator's file
ports at $F800-$F80F reach the files of the host directory DIR, and lathe/rt/disk.lth gives a
program the interface of lathe/rt/host.lth over them. Its output is in files of DIR, not on the
LCD: run_disk() runs the program on a directory the caller has filled with the input files (the
arguments in the file `args`, one a line) and returns what the program left in `out` and
`errors`, and the status written to `status` (0 if there is none: main returned). The caller
reads any other file the program wrote from DIR itself.

A board with `mos` set (bbc) is the BBC Model B+128 (`--machine bbcbplus`): the program is
loaded and entered by the MOS's *RUN, with its arguments in the command line, and
lathe/rt/bbc.lth gives it the interface of lathe/rt/host.lth over the MOS. run_mos() puts the
program file and its .inf file (load and execution addresses, which build.py writes) in a
directory of files, runs `RUN NAME ARGS` there with --bbc-strict, takes the program away again,
and returns its status, output and error output. The output is the emulator's standard output,
with the BBC's end of line, LF CR (OSNEWL), given back as LF; the BBC has no error stream, so the
error output is only a MOS error's message; the status is the N of the error "Exit N" that
bbc.exit raises, 1 for any other error, or 0 when the program returned to the MOS. A banked
program (an environment such as lathe/env/bbc-bank.env, whose code or regions are in the
window) runs with the module in its developer's form, RAM (module_options): the caller puts the
bank files in the directory beside the program (build.run_program does), and the program's
start-up code loads them into the module and the sideways RAM. run_module() runs a * command of
a module image (bbcrom.py), from ROM or, through the loader, from the module's RAM form.

The emulator's default machine is not here: build.run_image runs it, with host services.
"""
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mapenv  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
EMULATOR = os.path.join(ROOT, 'emulator', 'emulator.out')
# Every run starts with RAM that is not 0 (the emulator's --fill-ram), as on a real machine: a
# variable with no initial value is undefined until the program assigns it (language.md), and
# a program that relies on 0 fails here, not on the board. build.py's runs on the default
# machine pass it too.
FILL = ('--fill-ram',)


class RunError(Exception):
    pass


@dataclass(frozen=True)
class Board:
    machine: str            # the emulator's --machine
    options: tuple          # further options; {image} is the program file, {load} its address
    cycle_cap: int          # --cycle-cap: how long a run may take before it is an error
    cap_unit: str           # what the cap counts, for the message
    lcd_rows: int
    disk: bool = False      # run with --disk DIR ({disk}): the output is in files there
    mos: bool = False       # the BBC: run by *RUN through the MOS (run_mos)
    rt: tuple = ()          # directories of lathe/rt/ that build.py searches before lathe/rt/


# Environment name (lathe/env/NAME.env) -> board.
BOARDS = {
    'michael': Board('michael', ('--load', '{load}'), 2_000_000, 'CPU cycles', 4),
    # --wendy2-prog preloads the program into RAM and starts it, skipping the serial boot;
    # the positional file must be given but is not used, so it is the program too.
    'wendy2': Board('wendy2c', ('--wendy2-prog', '{image}', '--load', '{load}'), 4_000_000,
                    'oscillator ticks (2 per CPU cycle)', 2),
    # The same with the file ports, which reach the files of the directory {disk}.
    'wendy2disk': Board('wendy2c', ('--wendy2-prog', '{image}', '--load', '{load}',
                                    '--disk', '{disk}'), 200_000_000,
                        'oscillator ticks (2 per CPU cycle)', 2, disk=True),
    # The BBC Model B+128: *RUN NAME ARGS (--bbc-command) in the directory {disk}. Its module
    # `host` (lathe/rt/bbc/host.lth) is host.lth's interface over bbc.lth.
    'bbc': Board('bbcbplus', ('--disk', '{disk}', '--bbc-strict'), 400_000_000, 'CPU cycles', 0,
                 mos=True, rt=('bbc',)),
}

# The files of a disk board's directory that the driver writes or reads (lathe/rt/disk.lth).
ARGS_FILE, OUT_FILE, ERRORS_FILE, STATUS_FILE = 'args', 'out', 'errors', 'status'

EXIT_RE = re.compile(r'exit .*pc=\$([0-9A-Fa-f]{4})\s+\(([^)]*)\)')
ROW_RE = re.compile(r'^\s*\|(.*)\|\s*$')


def board_for(env_name):
    """The board for an environment name or .env path, or None (the default machine): the
    board of the same name, or else, for a file, the one its `define BOARD N` entry names
    (1 Michael, 2 Wendy 2; Wendy 2 with files if it also has `define DISK` not 0; 3 the BBC)."""
    name = os.path.splitext(os.path.basename(env_name))[0].lower()
    if name in BOARDS or not os.path.isfile(env_name):
        return BOARDS.get(name)
    defines = dict(mapenv.read_env(env_name).defines)
    board = defines.get('BOARD')
    if board == 1:
        return BOARDS['michael']
    if board == 2:
        return BOARDS['wendy2disk' if 'DISK' in defines and defines['DISK'] != 0 else 'wendy2']
    if board == 3:
        return BOARDS['bbc']
    return None


def command(board, image, load, disk=None):
    """The emulator's command line; disk is the directory of a disk board's files. Both paths
    are made absolute: with --disk the emulator changes to that directory before it opens the
    program file."""
    image = os.path.abspath(image)
    fill = {'image': image, 'load': f'{load:04X}', 'disk': os.path.abspath(disk or '.')}
    return ([EMULATOR, image, '--machine', board.machine] + list(FILL)
            + [o.format(**fill) for o in board.options]
            + ['--cycle-cap', str(board.cycle_cap), '--exit-report'])


def read_report(board, report):
    """The LCD rows from an exit report, trailing spaces removed. RunError unless the run
    ended at STP."""
    lines = report.splitlines()
    ends = [m for m in (EXIT_RE.search(line) for line in lines) if m]
    if not ends:
        raise RunError('the emulator printed no exit report:\n' + report)
    pc, why = ends[-1].group(1), ends[-1].group(2)
    if why != 'STP':
        raise RunError(f'the program did not stop (it ends with STP): the run ended by {why} '
                       f'at ${pc.upper()} after {board.cycle_cap} {board.cap_unit}')
    rows = None
    for line in lines:
        if rows is None:
            if line.rstrip().endswith('lcd:'):
                rows = []
            continue
        m = ROW_RE.match(line)
        if not m:
            break
        rows.append(m.group(1).rstrip())
    if rows is None or len(rows) != board.lcd_rows:
        raise RunError(f'no {board.lcd_rows}-row LCD in the exit report:\n' + report)
    return rows


def emulate(board, image, env, disk=None):
    """Runs a raw program file on a board. Returns the exit report."""
    if not os.path.isfile(EMULATOR):
        raise RunError('emulator/emulator.out is missing: run make at the repository root')
    if env.output != mapenv.OUTPUT_RAW or env.exit[0] != mapenv.EXIT_STOP:
        raise RunError(f'{env.path}: a board program needs `output raw` and `exit stop`')
    r = subprocess.run(command(board, image, env.code[0], disk), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
    report = r.stderr.decode('latin-1')
    if r.returncode != 0:
        raise RunError(f'the emulator failed (status {r.returncode}):\n' + report)
    return report


def run(board, image, env):
    """Runs a raw program file on a board. env is its mapenv.Env. Returns the LCD text, one
    line per row, with trailing spaces removed."""
    return ''.join(row + '\n' for row in read_report(board, emulate(board, image, env)))


def read_status(disk):
    """The exit status a program on a disk board left: the decimal number in the file `status`
    that disk.exit writes, or 0 if there is no such file (main returned to the start-up code,
    whose STP ended the run)."""
    path = os.path.join(disk, STATUS_FILE)
    if not os.path.isfile(path):
        return 0
    with open(path, 'rb') as fh:
        text = fh.read().decode('latin-1').strip()
    if not text.isdigit() or int(text) > 255:
        raise RunError(f'the file status holds {text!r}, not a status from 0 to 255')
    return int(text)


def read_file(disk, name):
    """The bytes of a file in a disk board's directory; empty if the program did not write it."""
    path = os.path.join(disk, name)
    if not os.path.isfile(path):
        return b''
    with open(path, 'rb') as fh:
        return fh.read()


def run_disk(board, image, env, disk):
    """Runs a raw program file on a disk board, on the files of the directory disk, which the
    caller has filled with the program's input files (its arguments in `args`, one a line).
    `out`, `errors` and `status` are removed first. Returns (status, the bytes of `out`, the
    bytes of `errors`). RunError unless the run ended at STP."""
    for name in (OUT_FILE, ERRORS_FILE, STATUS_FILE):
        path = os.path.join(disk, name)
        if os.path.isfile(path):
            os.unlink(path)
    read_report(board, emulate(board, image, env, disk))
    return read_status(disk), read_file(disk, OUT_FILE), read_file(disk, ERRORS_FILE)


# ---- The BBC: *RUN through the MOS ---------------------------------------------------------

BBC_LINE = 254          # the emulator's command buffer at $0700: 254 bytes and the CR
BBC_REPORT_RE = re.compile(r'^bbcbplus: exit\s+cpu_cycles=(\d+)\s+pc=\$([0-9A-Fa-f]{4})\s+\(([^)]*)\)', re.M)
BBC_EXIT_RE = re.compile(r'^Exit (\d{1,3})$')


def bbc_name(image):
    """The name a program file has on the BBC's disc: its own, without the extension."""
    return os.path.splitext(os.path.basename(image))[0]


def inf_text(name, load, length):
    """A .inf file (emulator/NOTES-bbcbplus.md): the name, the load and execution addresses
    (both the load address: $start is first) and the length, in hexadecimal."""
    return f'{name} {load:08X} {load:08X} {length:08X}\n'


def bbc_quote(arg):
    """An argument as bbc.lth reads it: as it is, or in quotes if it is empty or holds a space
    or a quote, a quote inside written twice."""
    if '\r' in arg:
        raise RunError(f'an argument on the BBC cannot hold a carriage return: {arg!r}')
    if arg and ' ' not in arg and '"' not in arg:
        return arg
    return '"' + arg.replace('"', '""') + '"'


def bbc_command(name, args, tail=None):
    """The * command that runs the program NAME with args: `RUN NAME ARGS` (or the tail as it
    is, if one is given). RunError if the MOS's line cannot hold it."""
    line = f'RUN {name}'
    rest = ' '.join(bbc_quote(a) for a in args) if tail is None else tail
    if rest:
        line += ' ' + rest
    if len(line) > BBC_LINE:
        raise RunError(f'the command line is {len(line)} bytes, more than the {BBC_LINE} the MOS takes')
    return line


def bbc_output(data):
    """The emulator's standard output with each LF CR, OSNEWL's end of line, as LF."""
    return data.replace(b'\n\r', b'\n')


def bbc_status(code, err):
    """(status, error output, cycles) from the emulator's status and error output (with the exit
    report). RunError unless the program returned or raised an error."""
    m = BBC_REPORT_RE.search(err)
    if not m:
        raise RunError('the emulator printed no exit report:\n' + err)
    cycles, pc, why = int(m.group(1)), m.group(2), m.group(3)
    said = ''.join(line for line in err.splitlines(True) if not line.startswith('bbcbplus: '))
    if why == 'returned' and code == 0:
        return 0, said.encode('latin-1'), cycles
    if why == 'error' and code == 1:
        lines = said.splitlines()
        e = BBC_EXIT_RE.match(lines[-1]) if lines else None
        if e and 0 < int(e.group(1)) <= 255:
            return int(e.group(1)), ''.join(l + '\n' for l in lines[:-1]).encode('latin-1'), cycles
        return 1, said.encode('latin-1'), cycles
    raise RunError(f'the program did not end well on the BBC: the run ended by {why} at ${pc.upper()}'
                   f' (status {code}):\n' + err)


def module_options(env):
    """The emulator's options for the module a banked program on the BBC uses (env is its
    mapenv.Env): the developer's form, RAM, with scheme direct16 (sixteen banks, latched by a
    read of $BFF0+n), in the slot of the environment's `define MODULE_SLOT N` (rt_bbc.SLOT).
    None for a program linked all in one."""
    if not env.banked():
        return None
    defines = dict((n.upper(), v) for n, v in env.defines)
    if defines.get('MODULE_SLOT') is None:
        raise RunError(f'{env.path}: a banked program on the BBC needs `define MODULE_SLOT N`')
    return ('--bbc-module-ram', '--bbc-module-scheme', 'direct16',
            '--bbc-module-slot', str(defines['MODULE_SLOT']))


ROM_TAIL = 239          # the most of a tail the module's bank 0 copies to $0700 (module.asm)


def module_command(command, args, tail=None):
    """The line of a * command of a module image with args (bbc_quote), or the tail as it is.
    RunError if the module cannot take it."""
    rest = ' '.join(bbc_quote(a) for a in args) if tail is None else tail
    if len(rest) > ROM_TAIL:
        raise RunError(f'the tail is {len(rest)} bytes, more than the {ROM_TAIL} the module copies')
    line = command + (' ' + rest if rest else '')
    if len(line) > BBC_LINE:
        raise RunError(f'the command line is {len(line)} bytes, more than the {BBC_LINE} the MOS takes')
    return line


MODULE_SCHEME = 'direct16'  # run_module's scheme when none is given: the sixteen-bank image's


def run_module(board, image, disk, command, args=(), slot=4, bank=0, ram=False, before=(),
               roms=(), stdin=None, tail=None, raw=False, cap=None, scheme=None):
    """Runs the * command `command` of a module image (lathe/host/driver/bbcrom.py) with args on
    the BBC, in the directory of files disk: the image in the module, scheme `scheme` (direct16,
    sixteen banks, or direct8, eight: bbcrom.SCHEMES; MODULE_SCHEME if not given), in `slot`,
    with the latch at `bank` at power on. With ram, the module is the developer's form, RAM, and
    empty: the commands `before` (such as `RUN LOADMOD IMAGE 4`, its loader) run first and fill
    it, and image is not given to the emulator. `roms` are (slot, file) pairs of further ROMs, a
    language among them. Returns what run_mos returns: (status, output, error output, cycles),
    or with raw the emulator's own status and output and its error output with the report."""
    if not os.path.isfile(EMULATOR):
        raise RunError('emulator/emulator.out is missing: run make at the repository root')
    fill = {'disk': os.path.abspath(disk)}
    cmd = ([EMULATOR, '--machine', board.machine] + list(FILL) + [o.format(**fill) for o in board.options]
           + ['--bbc-module-scheme', scheme or MODULE_SCHEME, '--bbc-module-slot', str(slot),
              '--bbc-module-bank', str(bank)]
           + (['--bbc-module-ram'] if ram else ['--bbc-module', os.path.abspath(image)]))
    for s, path in roms:
        cmd += ['--bbc-rom', f'{s}={os.path.abspath(path)}']
    for line in before:
        cmd += ['--bbc-command', line]
    cmd += ['--bbc-command', module_command(command, args, tail),
            '--cycle-cap', str(cap or board.cycle_cap), '--exit-report']
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       input=stdin if stdin is not None else b'')
    err = r.stderr.decode('latin-1')
    if raw:
        m = BBC_REPORT_RE.search(err)
        return r.returncode, r.stdout, err.encode('latin-1'), int(m.group(1)) if m else 0
    status, said, cycles = bbc_status(r.returncode, err)
    return status, bbc_output(r.stdout), said, cycles


def run_mos(board, image, disk, args=(), stdin=None, command_tail=None, raw=False, cap=None,
            module=None, report=False, before=()):
    """Runs a program file on the BBC: copies it, with the .inf file build.py wrote beside it
    (IMAGE.inf), into the directory disk under its BBC name, runs `RUN NAME ARGS` there and
    removes the two again. Returns (status, output, error output, CPU cycles), as bbc_status()
    and bbc_output() make them; with raw, the emulator's own status and standard output, and
    its error output without the exit report (with report, with it). `module` is the module's
    options (module_options), for a banked program, whose bank files the caller has put in
    disk. `before` are * commands run first, each when the one before returns.
    """
    if not os.path.isfile(EMULATOR):
        raise RunError('emulator/emulator.out is missing: run make at the repository root')
    name = bbc_name(image)
    program = os.path.join(disk, name)
    if os.path.exists(program) or os.path.exists(program + '.inf'):
        raise RunError(f'{disk} already holds a file {name}, the name of the program')
    with open(image + '.inf') as fh:
        load = int(fh.read().split()[1], 16)
    shutil.copyfile(image, program)
    with open(program + '.inf', 'w') as fh:
        fh.write(inf_text(name, load, os.path.getsize(image)))
    fill = {'disk': os.path.abspath(disk)}
    cmd = ([EMULATOR, '--machine', board.machine] + list(FILL) + [o.format(**fill) for o in board.options]
           + list(module or ()) + [w for line in before for w in ('--bbc-command', line)]
           + ['--bbc-command', bbc_command(name, args, command_tail),
              '--cycle-cap', str(cap or board.cycle_cap), '--exit-report'])
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           input=stdin if stdin is not None else b'')
    finally:
        os.unlink(program)
        os.unlink(program + '.inf')
    err = r.stderr.decode('latin-1')
    if raw:
        said = err if report else ''.join(line for line in err.splitlines(True)
                                          if not line.startswith('bbcbplus: '))
        m = BBC_REPORT_RE.search(err)
        return r.returncode, r.stdout, said.encode('latin-1'), int(m.group(1)) if m else 0
    status, said, cycles = bbc_status(r.returncode, err)
    return status, bbc_output(r.stdout), said, cycles
