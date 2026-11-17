"""The host compiler, lathe/host/lathec.py, recording which of its functions emitted each
instruction: a stand-in for it that build.py runs when LATHE_COMPILER names this file.

    LATHE_COMPILER=lathe/tests/construct_lathec.py python3 lathe/host/driver/build.py ...

It compiles exactly as lathec.py does (the same files are written) and also writes, beside each
object file, NAME.tags: for every function, its object symbol and, for every entry of the
function buffer that becomes code, its offset in the code, its bytes as written, its entry kind
(fbuf.I_*) and the chain of compiler functions on the Python stack when it was added, innermost
first. lathe/tests/construct_report.py reads them. A measuring tool (lathe/docs/spikes.md, "Size
for a 128 KB ROM: the generated code, measured")."""
import atexit
import json
import os
import sys

HOST = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'host')
sys.path.insert(0, HOST)
HOST = os.path.realpath(HOST)

import env      # noqa: E402
import fbuf     # noqa: E402

DEPTH = 30
keys = {}           # chain -> number
tags = {}           # buffer offset -> key number, for the function being compiled
functions = []      # [symbol, [[offset, size, kind, key]...]]
files = {}


def chain():
    f = sys._getframe(2)
    names = []
    while f is not None and len(names) < DEPTH:
        path = f.f_code.co_filename
        base = os.path.basename(path)
        if base.endswith('.py') and base != 'fbuf.py' and os.path.dirname(os.path.realpath(path)) == HOST:
            names.append(base[:-3] + '.' + f.f_code.co_name)
        f = f.f_back
    names = tuple(names)
    if names not in keys:
        keys[names] = len(keys)
    return keys[names]


original_end_entry = fbuf.end_entry
original_finish = fbuf.finish
original_begin = fbuf.begin


def end_entry():
    before = fbuf.used
    original_end_entry()
    if fbuf.used != before:
        tags[fbuf.newest] = chain()


def begin():
    tags.clear()
    original_begin()


def finish(symbol, base):
    original_finish(symbol, base)
    rows = []
    entry = 0
    offset = 0
    while entry < fbuf.used:
        size = fbuf.code_size(entry)
        kind = fbuf.buffer[entry]
        if size:
            rows.append([offset, size, kind, tags.get(entry, -1)])
        offset += size
        entry += fbuf.entry_size(kind)
    functions.append([symbol, rows])


fbuf.end_entry = end_entry
fbuf.begin = begin
fbuf.finish = finish


def write():
    if 'out' not in files:
        return
    with open(files['out'], 'w') as f:
        json.dump({'keys': [list(k) for k, v in sorted(keys.items(), key=lambda kv: kv[1])],
                   'functions': functions}, f)


def main():
    args = sys.argv[1:]
    names = [a for a in args if not a.startswith('-')]
    source, outdir = names[0], names[1]
    module = os.path.splitext(os.path.basename(source))[0].lower()
    files['out'] = os.path.join(outdir, module + '.tags')
    atexit.register(write)
    import lathec
    env.start(args)
    lathec.main()


main()
