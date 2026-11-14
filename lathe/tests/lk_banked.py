"""The whole Lathe-written linker (lathe/src/link.lth) built banked and run on emulated Wendy 2
with files (lathe/host/README.md, "The linker in Lathe").

build(out_dir) builds it with lathe/src/linker-bank.env: OUT_DIR/link.bin, its bank files
beside it, the environment as OUT_DIR/link.env and the work files (objects, map) in
OUT_DIR/work. run(image, files, args) links in a directory of its own: the case's files
(name -> bytes) are written there, with the linker's own bank files, and the arguments go in
the file `args`; the result is (status, error output, the files the run wrote, CPU cycles).

These are the linker's counterparts of src_support.build_banked and run_banked, which build and
run the compiler's test programs: the same board, but the arguments are already base names, and
what comes back is every file the linker wrote, not only those its arguments name, because a
bank or overlay file is named by the environment file being read.
"""
import dataclasses
import os
import re
import shutil
import tempfile

import src_support as support
import build
import boards
import mapenv

ENV = os.path.join(support.SRC, 'linker-bank.env')
CYCLE_CAP = 4000000000          # oscillator ticks, 2 a CPU cycle: 2,000 million cycles a run

# The files of the directory that are the board's, not the linker's output.
HARNESS = (boards.ARGS_FILE, boards.OUT_FILE, boards.ERRORS_FILE, boards.STATUS_FILE)


def build_linker(out_dir, env=ENV):
    """Build lathe/src/link.lth banked into OUT_DIR/link.bin. Returns the image's path."""
    image = os.path.join(out_dir, 'link.bin')
    shutil.copyfile(env, os.path.join(out_dir, 'link.env'))
    build.build(os.path.join(support.SRC, 'link.lth'), image, env=os.path.join(out_dir, 'link.env'),
                keep=os.path.join(out_dir, 'work'))
    return image


def linker_files(image):
    """The base names of the linker's own bank files."""
    env = mapenv.read_env(os.path.splitext(image)[0] + '.env')
    return env, set(name for name in bank_names(env))


def bank_names(env):
    with open(env.path) as f:
        for line in f:
            p = line.split(';')[0].split()
            if len(p) >= 5 and p[0].lower() == 'bank':
                yield p[4]


def files_of(d, skip=()):
    found = {}
    for top, dirs, names in os.walk(d):
        for name in names:
            rel = os.path.relpath(os.path.join(top, name), d)
            if rel in skip:
                continue
            with open(os.path.join(top, name), 'rb') as f:
                found[rel] = f.read()
    return found


def run(image, files, args, cycle_cap=CYCLE_CAP):
    """Run the banked linker on a case: (status, error output, {name: bytes} of the files it
    wrote or changed, CPU cycles). The arguments name the files by the names `files` gives."""
    env, own = linker_files(image)
    board = dataclasses.replace(boards.BOARDS['wendy2disk'], cycle_cap=cycle_cap)
    with tempfile.TemporaryDirectory(prefix='lathe-link-banked-') as disk:
        for name, data in files.items():
            path = os.path.join(disk, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                f.write(data)
        build.window_files(env, os.path.dirname(os.path.abspath(image)), disk)
        with open(os.path.join(disk, boards.ARGS_FILE), 'wb') as f:
            f.write(b''.join(str(a).encode('latin-1') + b'\n' for a in args))
        report = boards.emulate(board, image, env, disk)
        boards.read_report(board, report)
        written = {name: data for name, data in files_of(disk, set(HARNESS) | own).items()
                   if files.get(name) != data}
        m = re.search(r'cpu_cycles=(\d+)', report)
        return (boards.read_status(disk), boards.read_file(disk, boards.ERRORS_FILE), written,
                int(m.group(1)) if m else 0)
