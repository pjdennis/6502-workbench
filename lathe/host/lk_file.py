"""The linker's files, which are all named by program arguments.

The command line is `link ENV MAINMODULE OUT.bin OUT.map OBJECT.lo...` (README.md). A file is
opened by the number of its argument, so no file name is kept anywhere: an object file that is
read again is simply opened again.
"""
import env
import lk_err

ARG_ENV = 0
ARG_MAIN = 1
ARG_BIN = 2
ARG_MAP = 3
ARG_OBJECT = 4          # the first object file

PATH = 0                # where in env.mem an argument is copied to


def arg_count():
    """Number of program arguments."""
    return env.argc()


def arg_length(i):
    """Copy argument i to PATH and return its length."""
    return env.arg_copy(i, PATH)


def fail(n, i):
    """Report error n about the file named by argument i."""
    lk_err.begin(n)
    lk_err.colon()
    size = arg_length(i)
    for k in range(0, size):
        lk_err.put(env.mem[PATH + k])
    lk_err.finish()


def open_in(i):
    """Open the file named by argument i for reading."""
    arg_length(i)
    handle = env.open_in(PATH)
    if handle == 0:
        fail(lk_err.E_OPEN, i)
    return handle


def open_in_quiet(i):
    """Open the file named by argument i for reading, or return 0 if it cannot be opened."""
    arg_length(i)
    return env.open_in(PATH)


def open_out(i):
    """Create the file named by argument i."""
    arg_length(i)
    handle = env.open_out(PATH)
    if handle == 0:
        fail(lk_err.E_OPEN, i)
    return handle
