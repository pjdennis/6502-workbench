"""The linker's files, which are all named by program arguments.

The command line is `link ENV MAINMODULE OUT.bin OUT.map OBJECT.lo...` (README.md), or `link
@FILE`: the arguments are then the words of FILE, separated by spaces, tabs or line ends, which a
machine whose command line is too short for a large link needs. A file is opened by the number of
its argument, so no file name is kept anywhere: an object file that is read again is simply
opened again.
"""
import env
import lk_err

ARG_ENV = 0
ARG_MAIN = 1
ARG_BIN = 2
ARG_MAP = 3
ARG_OBJECT = 4          # the first object file

PATH = 0                # where in env.mem an argument is copied to

# The arguments of a command file: each word followed by a 0 in arg_text. MAX_ARGS is the
# environment, the main module, the image, the map and 44 object files (lk_name.MAX_OBJECTS is 40).
ARGS_SIZE = 512
MAX_ARGS = 48
AT_SIGN = 64            # @
from_file = False
file_count = 0
arg_text = bytearray(ARGS_SIZE)


def arg_count():
    """Number of program arguments."""
    if from_file:
        return file_count
    return env.argc()


def arg_length(i):
    """Copy argument i to PATH and return its length."""
    if from_file:
        pos = 0
        for k in range(0, i):
            while arg_text[pos] != 0:
                pos += 1
            pos += 1
        size = 0
        while arg_text[pos + size] != 0:
            env.mem[PATH + size] = arg_text[pos + size]
            size += 1
        env.mem[PATH + size] = 0
        return size
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


def start():
    """If the command line is one argument @FILE, read the arguments from FILE."""
    global from_file, file_count
    if env.argc() != 1:
        return
    size = env.arg_copy(0, PATH)
    if size < 2 or env.mem[PATH] != AT_SIGN:
        return
    for i in range(0, size):
        env.mem[PATH + i] = env.mem[PATH + i + 1]
    handle = env.open_in(PATH)
    if handle == 0:
        fail(lk_err.E_OPEN, 0)
    count = 0
    pos = 0
    first = 0
    inside = False
    while True:
        c, at_end = env.read(handle)
        if at_end or c <= 32:
            if inside:
                if pos == ARGS_SIZE:
                    lk_err.fail(lk_err.E_COMMAND_FILE)
                arg_text[pos] = 0
                pos += 1
                inside = False
            if at_end:
                break
        else:
            if not inside:
                if count == MAX_ARGS:
                    lk_err.fail(lk_err.E_COMMAND_FILE)
                first = pos
                count += 1
                inside = True
            if pos == ARGS_SIZE or pos - first == 255:
                lk_err.fail(lk_err.E_COMMAND_FILE)
            arg_text[pos] = c
            pos += 1
    env.close(handle)
    file_count = count
    from_file = True
