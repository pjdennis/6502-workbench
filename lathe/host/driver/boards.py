"""The emulated boards a Lathe program can run on, and how to read what it showed.

Everything the driver knows about a board is in BOARDS (lathe/docs/boards.md has the recipe
behind each entry). A board program is linked with `output raw` and `exit stop`: the file is
the code from the start of the environment's `code` range, which is the load address and
where the emulator starts it, and the run ends at the STP the start-up code ends with. The
program's output is the text on the board's LCD, which the emulator's exit report prints.

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


# Environment name (lathe/env/NAME.env) -> board.
BOARDS = {
    'michael': Board('michael', ('--load', '{load}'), 2_000_000, 'CPU cycles', 4),
    # --wendy2-prog preloads the program into RAM and starts it, skipping the serial boot;
    # the positional file must be given but is not used, so it is the program too.
    'wendy2': Board('wendy2c', ('--wendy2-prog', '{image}', '--load', '{load}'), 4_000_000,
                    'oscillator ticks (2 per CPU cycle)', 2),
}

EXIT_RE = re.compile(r'exit .*pc=\$([0-9A-Fa-f]{4})\s+\(([^)]*)\)')
ROW_RE = re.compile(r'^\s*\|(.*)\|\s*$')


def board_for(env_name):
    """The board for an environment name or .env path, or None (the default machine)."""
    name = os.path.splitext(os.path.basename(env_name))[0].lower()
    return BOARDS.get(name)


def command(board, image, load):
    image = os.path.abspath(image)
    fill = {'image': image, 'load': f'{load:04X}'}
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


def run(board, image, env):
    """Runs a raw program file on a board. env is its mapenv.Env. Returns the LCD text, one
    line per row, with trailing spaces removed."""
    if not os.path.isfile(EMULATOR):
        raise RunError('emulator/emulator.out is missing: run make at the repository root')
    if env.output != mapenv.OUTPUT_RAW or env.exit[0] != mapenv.EXIT_STOP:
        raise RunError(f'{env.path}: a board program needs `output raw` and `exit stop`')
    r = subprocess.run(command(board, image, env.code[0]), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
    report = r.stderr.decode('latin-1')
    if r.returncode != 0:
        raise RunError(f'the emulator failed (status {r.returncode}):\n' + report)
    return ''.join(row + '\n' for row in read_report(board, report))
