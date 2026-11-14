"""Shared by the tests of the host compiler: finding the host modules, catching what they
write to the error output, running the compiler as a program, and reading object files."""
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LATHE = os.path.dirname(HERE)
HOST = os.path.join(LATHE, 'host')
LATHEC = os.path.join(HOST, 'lathec.py')
CASES = os.path.join(HERE, 'cases')

if HOST not in sys.path:
    sys.path.append(HOST)       # last, so nothing of Python's own can be hidden

import env  # noqa: E402

TEXT = 0x8000                   # where tests put text in env.mem; the kernel's area ends below


def put_text(text, address=TEXT):
    """Put zero-terminated `text` in env.mem. Returns (address, address of the zero)."""
    env.mem[address:address + len(text)] = text
    env.mem[address + len(text)] = 0
    return address, address + len(text)


def fresh():
    """Start a test with nothing left of the one before: no file open, no error output.
    What the tools write to the error output from now on is kept for error_text()."""
    for handle in range(1, env.MAX_FILES):
        if env._files[handle] is not None:
            env._files[handle].close()
            env._files[handle] = None
    env._err = io.BytesIO()


def error_text():
    return env._err.getvalue().decode('latin-1')


def run_lathec(*args):
    """Run the compiler as a program. Returns (exit status, error output as text)."""
    done = subprocess.run([sys.executable, LATHEC] + [str(a) for a in args],
                          capture_output=True, text=True)
    return done.returncode, done.stderr


def records(path):
    """The records of an object file, as a list of (type, body)."""
    with open(path, 'rb') as f:
        data = f.read()
    found, at = [], 0
    while at < len(data):
        size = data[at + 1] | data[at + 2] << 8
        found.append((data[at], data[at + 3:at + 3 + size]))
        at += 3 + size
    return found


def finished():
    """What FBUF finished, walked as OUT walks it: (code bytes, [fix-ups as (offset, kind, symbol,
    slot, addend)])."""
    import fbuf
    code, fixes = bytearray(), []
    fbuf.walk_begin()
    while fbuf.walk_next():
        if fbuf.piece_fixed:
            fixes.append((fbuf.fix_offset, fbuf.fix_kind, fbuf.fix_symbol, fbuf.fix_slot,
                          fbuf.fix_addend))
        code += bytes(fbuf.piece[i] for i in range(fbuf.piece_length))
    assert len(code) == fbuf.code_length and len(fixes) == fbuf.fix_count
    return bytes(code), fixes
