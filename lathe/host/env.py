"""The outside world, as the host tools see it.

This is the one host file written in ordinary Python and not ported to Lathe: on the target the
same services are the machine's own (asm/17/environment.asm), declared `extern` in lathe/rt/host.lth
and wrapped by a few lines of Lathe. Everything else in lathe/host/ reaches files, arguments and
the console only through the functions here.

Pointers. Lathe code passes text to the system as a pointer. The host tools model that with `mem`,
64 KB of bytes: a pointer is an index into `mem`, and a string is zero-terminated bytes there.
Data that is only ever indexed (tables, the symbol columns) lives in ordinary module-level arrays
in the module that owns it and does not need to be in `mem`.
"""
import sys

MEM_SIZE = 0x10000
mem = bytearray(MEM_SIZE)

MAX_FILES = 16
_files = [None] * MAX_FILES          # handle -> open file; handle 0 means "could not open"
_args = []                           # program arguments, set by start()
_out = sys.stdout.buffer
_err = sys.stderr.buffer


def start(args):
    """Set the program arguments. is_program() calls this with sys.argv[1:]; tests call it directly."""
    global _args
    _args = [a.encode('latin-1') for a in args]


def is_program(name):
    """True if the module called `name` is the one Python was asked to run; the program
    arguments are then taken from the command line.

    A tool ends with `if env.is_program(__name__):` and a call of its main function. Those two
    lines are all the start-up code a tool has, and they hold no Python string, which the tools
    may not use (lathe/tests/test_shape.py).
    """
    if name != '__main__':
        return False
    start(sys.argv[1:])
    return True


def _name(ptr):
    end = mem.index(0, ptr)
    return bytes(mem[ptr:end]).decode('latin-1')


def argc():
    """Number of program arguments."""
    return len(_args)


def arg_copy(i, ptr):
    """Copy argument i to mem[ptr...] with a terminating zero; return its length."""
    a = _args[i]
    mem[ptr:ptr + len(a)] = a
    mem[ptr + len(a)] = 0
    return len(a)


def _open(ptr, mode):
    for h in range(1, MAX_FILES):
        if _files[h] is None:
            try:
                _files[h] = open(_name(ptr), mode)
            except OSError:
                return 0
            return h
    return 0


def open_in(ptr):
    """Open the file named at mem[ptr] for reading. Returns a handle, or 0 if it cannot be opened."""
    return _open(ptr, 'rb')


def open_out(ptr):
    """Create the file named at mem[ptr] for writing. Returns a handle, or 0."""
    return _open(ptr, 'wb')


def close(handle):
    _files[handle].close()
    _files[handle] = None


def read(handle):
    """Next byte of the file and False, or 0 and True at the end of the file."""
    b = _files[handle].read(1)
    if not b:
        return 0, True
    return b[0], False


def write(handle, byte):
    _files[handle].write(bytes((byte & 0xFF,)))


def put_byte(byte):
    """One byte to standard output."""
    _out.write(bytes((byte & 0xFF,)))


def put_error(byte):
    """One byte to the error output."""
    _err.write(bytes((byte & 0xFF,)))


def exit(code):
    """End the program. Does not return."""
    for h in range(1, MAX_FILES):
        if _files[h] is not None:
            _files[h].close()
    _out.flush()
    _err.flush()
    sys.exit(code)
