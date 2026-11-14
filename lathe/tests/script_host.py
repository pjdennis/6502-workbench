"""The Python twin of lathe/src/script.lth: reading a test script and writing what its
commands give, so that a test program of lathe/src/ and the host modules can be driven by one
script and their outputs compared (lathe/tests/test_src_typetab.py and the others).

Also run_section(): split a script into its sections and run one, either way."""
import concurrent.futures
import io
import os
import tempfile

import src_support as support
import lathec_support
import env
import kernel

HEX = b'0123456789ABCDEF'
SCRIPTS = os.path.join(support.HERE, 'scripts')

_lines = []
_line = b''
_at = 0


def open_script(path):
    global _lines
    with open(path, 'rb') as f:
        data = f.read()
    _lines = data.split(b'\n')
    _lines.reverse()


def next_line():
    """The next line that holds a command, made current. False at the end."""
    global _line, _at
    while _lines:
        line = _lines.pop()
        line = line.split(b';', 1)[0]
        _line = line[:250]
        _at = 0
        _skip()
        if _at < len(_line):
            return True
    return False


def _blank(c):
    return c in (0x20, 0x09, 0x0D)


def _skip():
    global _at
    while _at < len(_line) and _blank(_line[_at]):
        _at += 1


def more():
    _skip()
    return _at < len(_line)


def _word():
    global _at
    _skip()
    start = _at
    while _at < len(_line) and not _blank(_line[_at]):
        _at += 1
    return _line[start:_at]


NOT_FOUND = 0xFF


def find(words):
    """The number of the line's first word in `words`, a byte string of words each followed by
    a space, which it then reads; or NOT_FOUND, and it is left to be read."""
    global _at
    save = _at
    w = _word()
    table = words.split(b' ')[:-1]
    if w not in table:
        _at = save
        return NOT_FOUND
    return table.index(w)


def command(words):
    """As find(), but an unknown word ends the program with status 3."""
    n = find(words)
    if n == NOT_FOUND:
        env.exit(3)
    return n


def number():
    w = _word()
    negative = w.startswith(b'-')
    if negative:
        w = w[1:]
    value = 0
    if w.startswith(b'$'):
        for c in w[1:]:
            c = c - 0x61 + 10 if 0x61 <= c <= 0x66 else c - 0x41 + 10 if 0x41 <= c <= 0x46 else (c - 0x30) & 0xFF
            value = ((value << 4) | c) & 0xFFFF
    else:
        for c in w:
            value = (value * 10 + ((c - 0x30) & 0xFF)) & 0xFFFF
    if negative:
        value = (0 - value) & 0xFFFF
    return value


def small():
    return number() & 0xFF


def flag():
    return number() != 0


def name():
    w = _word()
    kernel.name_begin()
    for c in w:
        kernel.name_add(c)
    return kernel.name_end()


def name_of(text):
    kernel.name_begin()
    for c in text:
        kernel.name_add(c)
    return kernel.name_end()


def show_byte(b):
    env.put_byte(HEX[(b >> 4) & 15])
    env.put_byte(HEX[b & 15])
    env.put_byte(0x20)


def show_word(w):
    env.put_byte(HEX[(w >> 12) & 15])
    env.put_byte(HEX[(w >> 8) & 15])
    show_byte(w & 0xFF)


def show_bool(f):
    env.put_byte(ord('T') if f else ord('F'))


def end_line():
    env.put_byte(10)


def show_finished():
    """What FBUF finished, as lathe/src/listing.lth prints it."""
    import fbuf
    show_word(fbuf.code_length)
    env.put_byte(ord(':'))
    fbuf.walk_begin()
    while fbuf.walk_next():
        for i in range(fbuf.piece_length):
            show_byte(fbuf.piece[i])
    env.put_byte(ord('|'))
    fbuf.walk_begin()
    while fbuf.walk_next():
        if fbuf.piece_fixed:
            show_word(fbuf.fix_offset)
            show_byte(fbuf.fix_kind)
            show_word(fbuf.fix_symbol)
            show_byte(fbuf.fix_slot)
            show_word(fbuf.fix_addend)
            env.put_byte(ord(','))
    env.put_byte(ord('|'))
    for w in range(fbuf.weight_count):
        show_word(fbuf.weight_symbol[w])
        show_byte(fbuf.weight_slot[w])
        show_byte(fbuf.weight_value[w])
        env.put_byte(ord(','))


# ---- Running a script both ways ----------------------------------------------------------

def sections(name):
    """The sections of lathe/tests/scripts/NAME.txt, which lines that start with `==` divide:
    [(title, text)]. Each is run by itself, from a fresh start."""
    with open(os.path.join(SCRIPTS, name + '.txt'), 'rb') as f:
        data = f.read()
    found = []
    title, lines = b'start', []
    for line in data.split(b'\n'):
        if line.startswith(b'=='):
            if any(l.split(b';', 1)[0].strip() for l in lines):
                found.append((title, b'\n'.join(lines) + b'\n'))
            title, lines = line[2:].strip(), []
        else:
            lines.append(line)
    if any(l.split(b';', 1)[0].strip() for l in lines):
        found.append((title, b'\n'.join(lines) + b'\n'))
    return found


# The small build (lathe/host/README.md, "The small build"): the capacities the twins declare
# under `#if SMALL`, as (host module, name, size). host_run(small=True) gives the host modules
# the same; test_memory.py checks that the twins agree.
SMALL = (('kernel', 'NAME_HEAP_SIZE', 1024), ('kernel', 'MAX_SYMS', 264), ('kernel', 'MAX_MEMBERS', 264),
         ('fbuf', 'BUFFER_SIZE', 1024), ('out', 'MAX_TABLE', 264), ('out', 'MAX_TABLE_FIXES', 32),
         ('lex', 'MAX_STRING', 264))


def host_run(main, args, small=False):
    """main() of a Python twin, with program arguments: (status, output, error output). With
    `small`, the host modules have the capacities of the small build while it runs."""
    import importlib
    lathec_support.fresh()
    env._out = io.BytesIO()
    env.start(args)
    status = 0
    saved = []
    for module, const, size in SMALL if small else ():
        m = importlib.import_module(module)
        saved.append((m, const, getattr(m, const)))
        setattr(m, const, size)
    try:
        main()
    except SystemExit as e:
        status = e.code
    finally:
        for m, const, size in saved:
            setattr(m, const, size)
    return status, env._out.getvalue(), env._err.getvalue()


def check_script(test, image, main, name, work, outputs=0, extra=(), small=False):
    """Run every section of script NAME with the Lathe program `image` and with the twin
    `main`, and check that the status, the output and the error output are the same, and the
    files the two write: the program gets the script and then `outputs` names of files to
    write (ending in L for the Lathe, P for the host). `extra` adds sections, (title, text),
    that the test makes itself. `small`: the program is the small build, and the host is run
    with its capacities. The Lathe runs are made in parallel."""
    found = sections(name) + list(extra)
    runs = []
    for n, (title, text) in enumerate(found):
        path = os.path.join(work, '%s-%d.txt' % (name, n))
        with open(path, 'wb') as f:
            f.write(text)
        files = [os.path.join(work, '%s-%d-%d' % (name, n, k)) for k in range(outputs)]
        runs.append((title, text, path, files))
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        lathe = list(pool.map(lambda r: support.run(image, [r[2]] + [f + 'L' for f in r[3]],
                                                    timeout=600), runs))
    for (title, text, path, files), (status, out, err, _) in zip(runs, lathe):
        with test.subTest(section=title.decode()):
            host = host_run(main, [path] + [f + 'P' for f in files], small)
            if out != host[1]:
                test.fail(first_difference(text, out, host[1]))
            test.assertEqual((status, err), (host[0], host[2]))
            for f in files:
                test.assertEqual(os.path.exists(f + 'L'), os.path.exists(f + 'P'))
                if os.path.exists(f + 'P'):
                    with open(f + 'L', 'rb') as a, open(f + 'P', 'rb') as b:
                        test.assertEqual(a.read(), b.read(), 'file %s' % f)
    return len(found)


def first_difference(text, lathe_out, host_out):
    """A message naming the first command whose output line differs."""
    commands = [l.split(b';', 1)[0].strip() for l in text.split(b'\n')]
    commands = [c for c in commands if c]
    a = lathe_out.split(b'\n')
    b = host_out.split(b'\n')
    for n in range(max(len(a), len(b))):
        x = a[n] if n < len(a) else b'<none>'
        y = b[n] if n < len(b) else b'<none>'
        if x != y:
            c = commands[n] if n < len(commands) else b'?'
            return 'command %d (%s):\n  lathe %s\n  host  %s' % (n + 1, c.decode(), x.decode(), y.decode())
    return 'outputs differ'


