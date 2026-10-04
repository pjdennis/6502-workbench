"""Runs Michael programs on the emulator's Michael machine for the tests: assembled with firmware/vasm,
loaded at PROGRAM_LOAD_ADDRESS ($2000), with keys typed on its PS/2 keyboard, and the FPGA bus's transfers
logged (--fpga-log). Needs vasm6502_oldstyle on PATH, gcc and make (the tests skip without them)."""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
FW_VASM = os.path.join(ROOT, 'firmware', 'vasm')
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from firmware_manifest import BASE_FLAGS, FLAG_SETS  # noqa: E402
UPLOAD_FLAGS = BASE_FLAGS + dict(FLAG_SETS)['esc']   # as the upload scripts assemble
EMULATOR = os.path.join(ROOT, 'emulator', 'emulator.out')
AVAILABLE = bool(shutil.which('vasm6502_oldstyle') and shutil.which('gcc') and shutil.which('make'))


def build_emulator():
    subprocess.run(['make', '-s', 'emulator/emulator.out'], cwd=ROOT, check=True, capture_output=True)


def run(source=None, program=None, keys=None, cycle_cap=6_000_000, key_interval=None):
    """Assembles source (text) or program (a path) and runs it, typing keys (bytes) key_interval ms apart
    (the emulator's default if None). Returns (the FPGA bus log, the emulator's report: its exit line, the
    LCD and so on)."""
    with tempfile.TemporaryDirectory() as tmp:
        if source is not None:
            program = os.path.join(tmp, 'program.s')
            with open(program, 'w') as f:
                f.write(source)
        binary, log = os.path.join(tmp, 'program.bin'), os.path.join(tmp, 'fpga.log')
        subprocess.run([FW_VASM, *UPLOAD_FLAGS, '-o', binary, program], cwd=ROOT, check=True, capture_output=True)
        options = []
        if keys:
            keys_file = os.path.join(tmp, 'keys')
            with open(keys_file, 'wb') as f:
                f.write(keys)
            options = ['--keys', keys_file]
            if key_interval:
                options += ['--key-interval', str(key_interval)]
        report = subprocess.run([EMULATOR, binary, '--machine', 'michael', '--load', '2000', '--cycle-cap',
                                 str(cycle_cap), '--fpga-log', log, *options],
                                cwd=ROOT, check=True, capture_output=True, text=True).stderr
        with open(log) as f:
            return f.read(), report
