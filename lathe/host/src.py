"""SRC: the source stack.

Owns the stack of sources being read and gives LEX the top one, a character at a time, with
the line and column of that character. Today a source is a source file (or, for tests, text
in memory). The saved tokens of an `inline` function being replayed will be a third kind of
source, pushed on the same stack; an imported interface is not a source, because DECL reads
it straight into the symbol table.
"""
import err
import kernel

MAX_SOURCES = 4
LAST_POSITION = 0xFFFF      # lines and columns are counted this far and no further
C_LF = 0x0A

ch = 0              # the character being looked at; 0 at the end
eof = True          # True when the top source has no more characters
line = 0            # where `ch` is, both counted from 1
col = 0
depth = 0           # how many sources are open

stream = 0          # the top source's stream
name = 0            # pointer to its file name, 0 if it has none

# The sources below the top one, as they were when the one above was opened.
below_stream = [0] * MAX_SOURCES
below_name = [0] * MAX_SOURCES
below_ch = [0] * MAX_SOURCES
below_eof = [False] * MAX_SOURCES
below_line = [0] * MAX_SOURCES
below_col = [0] * MAX_SOURCES


def init():
    global depth, eof, ch
    depth = 0
    eof = True
    ch = 0


def push(new_stream, new_name):
    """Make a new top source and look at its first character."""
    global depth, stream, name, line, col, ch, eof
    if depth == MAX_SOURCES:
        err.fatal(err.E_SOURCES_FULL)
    below_stream[depth] = stream
    below_name[depth] = name
    below_ch[depth] = ch
    below_eof[depth] = eof
    below_line[depth] = line
    below_col[depth] = col
    depth += 1
    stream = new_stream
    name = new_name
    err.set_file(name)
    line = 1
    col = 0
    ch = 0
    eof = False
    advance()


def open_file(file_name):
    """Start reading the file whose name is at `file_name`. False if it cannot be opened."""
    new_stream, ok = kernel.open_in(file_name)
    if ok:
        push(new_stream, file_name)
    return ok


def open_memory(start, limit):
    """Start reading the text in env.mem from `start` up to but not including `limit`."""
    push(kernel.open_memory(start, limit), 0)


def advance():
    """Look at the next character."""
    global ch, eof, line, col
    if eof:
        return                  # the end has one position however often it is asked for
    if ch == C_LF:
        if line < LAST_POSITION:
            line += 1
        col = 1
    elif col < LAST_POSITION:
        col += 1
    ch, eof = kernel.get(stream)


def close():
    """Stop reading the top source and go back to the one below it."""
    global depth, stream, name, ch, eof, line, col
    kernel.close(stream)
    depth -= 1
    stream = below_stream[depth]
    name = below_name[depth]
    ch = below_ch[depth]
    eof = below_eof[depth]
    line = below_line[depth]
    col = below_col[depth]
    err.set_file(name)
