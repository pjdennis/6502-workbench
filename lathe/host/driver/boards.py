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

The emulator's default machine is not here: build.run_image runs it, with host services.
"""
import os
import re
import subprocess
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mapenv  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
EMULATOR = os.path.join(ROOT, 'emulator', 'emulator.out')


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
}

# The files of a disk board's directory that the driver writes or reads (lathe/rt/disk.lth).
ARGS_FILE, OUT_FILE, ERRORS_FILE, STATUS_FILE = 'args', 'out', 'errors', 'status'

EXIT_RE = re.compile(r'exit .*pc=\$([0-9A-Fa-f]{4})\s+\(([^)]*)\)')
ROW_RE = re.compile(r'^\s*\|(.*)\|\s*$')


def board_for(env_name):
    """The board for an environment name or .env path, or None (the default machine): the
    board of the same name, or else, for a file, the one its `define BOARD N` entry names
    (1 Michael, 2 Wendy 2; Wendy 2 with files if it also has `define DISK` not 0)."""
    name = os.path.splitext(os.path.basename(env_name))[0].lower()
    if name in BOARDS or not os.path.isfile(env_name):
        return BOARDS.get(name)
    defines = dict(mapenv.read_env(env_name).defines)
    board = defines.get('BOARD')
    if board == 1:
        return BOARDS['michael']
    if board == 2:
        return BOARDS['wendy2disk' if 'DISK' in defines and defines['DISK'] != 0 else 'wendy2']
    return None


def command(board, image, load, disk=None):
    """The emulator's command line; disk is the directory of a disk board's files. Both paths
    are made absolute: with --disk the emulator changes to that directory before it opens the
    program file."""
    image = os.path.abspath(image)
    fill = {'image': image, 'load': f'{load:04X}', 'disk': os.path.abspath(disk or '.')}
    return ([EMULATOR, image, '--machine', board.machine]
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
