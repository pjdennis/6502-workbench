"""The memory the compiler's tables take, laid out as Lathe lays them out, and how much of each
table the corpus uses.

    python3 lathe/tests/memory_report.py [--corpus] [--all]

Counts every module-level array of the compiler's host modules (lathe/host/ but env.py, the
linker and driver/): a list is 2 bytes an element, a bytearray or a list of bools 1, as a Lathe
`word`, `byte` and `bool` array are. A table that holds only bytes is a bytearray in the host, so that the count and
the Lathe twin agree (test_memory.py checks the twins). Then the text memory, kernel.TEXT_SIZE
bytes. Constant data (b"..." texts and tables) is code-side and not counted.

--corpus compiles every module of the corpus (each .lth under lathe/src/, lathe/rt/ and
lathe/tests/cases/, with the modules it imports first) with the host compiler, in this process,
and reports the peak use of each table. For the tables that keep a count of their use (the
name heap, the symbol table, the members, the text memory, the saved tokens, FBUF's buffer and
labels, LEX's string, OUT's table and its fix-ups) that is the highest count after any call
that can raise it (gauges()); for the others, the highest element any compile wrote a value
other than 0 to, plus one, counted only from the module's first line on. An error case of a
capacity (errors 70 to 98) is not counted: it fills its table on purpose. --all lists every array, not only those of
256 bytes or more.
"""
import glob
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LATHE = os.path.dirname(HERE)
HOST = os.path.join(LATHE, 'host')
for p in (HOST, os.path.join(HOST, 'driver')):
    if p not in sys.path:
        sys.path.append(p)

import env  # noqa: E402

BUDGET = 20 * 1024
CAPACITY = (156, 165, 166)    # errors outside 70 to 98 that are about a capacity of the compiler
MODULES = ('err', 'kernel', 'src', 'lex', 'typetab', 'fold', 'fbuf', 'out', 'reg', 'cond', 'gen',
           'asmblock', 'inline', 'expr', 'decl', 'lathec')


def module(name):
    import importlib
    return importlib.import_module(name)


def arrays(name):
    """[(array name, elements, bytes per element)] of host module NAME, in source order."""
    m = module(name)
    found = []
    for attr, value in vars(m).items():
        if isinstance(value, bytearray):
            found.append((attr, len(value), 1))
        elif isinstance(value, list) and attr != 'RECURSIVE':
            found.append((attr, len(value), 1 if value and isinstance(value[0], bool) else 2))
    return found


def text_size():
    import kernel
    return kernel.TEXT_SIZE


def table_bytes():
    """{module: bytes of its arrays}, and the text memory's bytes."""
    return {m: sum(n * w for _, n, w in arrays(m)) for m in MODULES}, text_size()


def total():
    per, text = table_bytes()
    return sum(per.values()) + text


# ---- Peak use over the corpus ------------------------------------------------------------

class Watched(list):
    """A list that notes the highest index it was given a value other than 0 at."""
    peak = 0
    on = False

    def __setitem__(self, i, v):
        list.__setitem__(self, i, v)
        if Watched.on and v != 0 and i + 1 > self.peak:
            self.peak = i + 1


class WatchedBytes(bytearray):
    peak = 0
    low = 0                 # for env.mem: only indexes from here count, as from 0

    def __setitem__(self, i, v):
        bytearray.__setitem__(self, i, v)
        if isinstance(i, slice):
            if i.stop is not None and i.stop - self.low > self.peak and any(v):
                self.peak = i.stop - self.low
        elif (Watched.on or self.low) and v != 0 and i + 1 - self.low > self.peak:
            self.peak = i + 1 - self.low


replaced = []          # (module, name, what it was) for each thing watch() replaced


def unwatch():
    """Put back what watch() and install_gauges() replaced, newest first."""
    while replaced:
        m, attr, value = replaced.pop()
        setattr(m, attr, value)


def watch():
    """Replace every array of the compiler's modules with a watched copy. Returns
    {(module, array): watched}, with ('kernel', 'text') for the text memory."""
    import kernel
    found = {}
    replaced.append((env, 'mem', env.mem))
    for name in MODULES:
        m = module(name)
        for attr, n, width in arrays(name):
            replaced.append((m, attr, getattr(m, attr)))
            if isinstance(getattr(m, attr), bytearray):
                w = WatchedBytes(n)
            else:
                w = Watched(getattr(m, attr)[:])
            setattr(m, attr, w)
            found[(name, attr)] = w
    mem = WatchedBytes(env.MEM_SIZE)
    mem.low = kernel.TEXT_BASE
    env.mem = mem
    found[('kernel', 'text')] = mem
    return found


SYM_COLUMNS = ('sym_name', 'sym_scope', 'sym_kind', 'sym_flags', 'sym_type', 'sym_value', 'sym_obj',
               'sym_weight', 'sym_members', 'sym_params', 'sym_results', 'sym_link')
LABEL_COLUMNS = ('label_offset', 'label_alias', 'label_uses', 'label_note')
TABLE_FIXES = ('table_fix_offset', 'table_fix_kind', 'table_fix_symbol', 'table_fix_slot',
               'table_fix_addend')


def gauges():
    """[(module, arrays, functions, use)]: the tables whose use is not the highest element
    written, but a count the module keeps, read after each call of the functions named."""
    import fbuf
    import inline
    import kernel
    import lex
    import out
    return [
        ('kernel', ('names',), ('name_end', 'freeze', 'freeze_member'), lambda: kernel.name_top),
        ('kernel', SYM_COLUMNS, ('sym_add', 'thaw'),
         lambda: kernel.sym_count + kernel.MAX_SYMS - kernel.thaw_top),
        ('kernel', ('member_type', 'member_value'), ('member_add',), lambda: kernel.member_count),
        ('kernel', ('text',), ('text_reserve', 'keep_argument'),
         lambda: kernel.text_top - kernel.TEXT_BASE),
        ('inline', ('saved tokens',), ('put',), lambda: inline.saved_top - inline.saved_start),
        ('fbuf', ('buffer',), ('add',), lambda: fbuf.used),
        ('fbuf', LABEL_COLUMNS, ('new_label',), lambda: fbuf.label_count),
        ('lex', ('string',), ('string_token', 'next'), lambda: lex.string_length),
        ('out', TABLE_FIXES, ('table_fix',), lambda: out.table_fix_count),
    ]


def install_gauges(peaks, where):
    """Wrap the functions of gauges() so that each call updates `peaks` (and `where`, from
    Gauge.path) for its arrays."""
    for name, attrs, functions, use in gauges():
        m = module(name)
        for f in functions:
            replaced.append((m, f, getattr(m, f)))

            def wrapped(*args, _f=getattr(m, f), _use=use, _attrs=attrs, _name=name):
                result = _f(*args)
                n = _use()
                for a in _attrs:
                    if n > peaks[(_name, a)]:
                        peaks[(_name, a)] = n
                        where[(_name, a)] = Gauge.path
                return result
            setattr(m, f, wrapped)
    out = module('out')
    begin = out.table_begin
    replaced.append((out, 'table_begin', begin))

    def table_begin(length):
        if length > peaks[('out', 'table')]:
            peaks[('out', 'table')] = length
            where[('out', 'table')] = Gauge.path
        begin(length)
    out.table_begin = table_begin
    return {(name, a) for name, attrs, functions, use in gauges() for a in attrs} | {('out', 'table')}


class Gauge:
    path = ''           # the module being compiled
    on = True           # False while an error case of a capacity is compiled


def compile_one(path, out_dir, options):
    """Compile one module with the host compiler, in this process. Returns its exit status."""
    import io
    import decl
    import lathec
    for h in range(1, env.MAX_FILES):
        if env._files[h] is not None:
            env._files[h].close()
            env._files[h] = None
    env._err = io.BytesIO()
    env._out = io.BytesIO()
    env.start(list(options) + [path, out_dir])
    unit = decl.unit

    def watched_unit():
        Watched.on = True
        try:
            unit()
        finally:
            Watched.on = False
    decl.unit = watched_unit
    try:
        lathec.main()
        status = 0
    except SystemExit as e:
        status = e.code
    finally:
        decl.unit = unit
        Watched.on = False
    return status


def corpus():
    """[(path, kind)] of every module of the corpus: kind is 'err' for an error case."""
    found = []
    for d in ('src', 'rt'):
        found += [(p, 'ok') for p in sorted(glob.glob(os.path.join(LATHE, d, '*.lth')))]
    for d in sorted(glob.glob(os.path.join(LATHE, 'tests', 'cases', '*'))):
        kind = 'err' if os.path.basename(d) == 'err' else 'ok'
        found += [(p, kind) for p in sorted(glob.glob(os.path.join(d, '*.lth')))]
    return found


def options_of(path, env_name=None):
    """The compiler options a case asks for, and those of the environment it is built for:
    the board's for a case of e2e-BOARD, the first `; config` environment's for one of
    e2e-config, lathe/src/compiler.env's for a module of lathe/src/ (which defines SMALL 0:
    the compiler's tables at full size), else host.env's."""
    import build
    import mapenv
    d = os.path.basename(os.path.dirname(path))
    if env_name is None:
        env_name = d[len('e2e-'):] if d.startswith('e2e-') else 'host'
        if os.path.dirname(os.path.abspath(path)) == os.path.join(LATHE, 'src'):
            env_name = os.path.join(LATHE, 'src', 'compiler.env')
        if d == 'src' and os.path.basename(path).startswith('lk'):
            # The linker's twins and their test programs test LKSMALL, which only the
            # linker's environment defines.
            env_name = os.path.join(LATHE, 'src', 'linker.env')
    words = []
    with open(path, encoding='latin-1') as f:
        for line in f:
            if line.startswith('module'):
                break
            if line.startswith('; config ') and d == 'e2e-config' and env_name == 'config':
                # The first configuration's environment, beside the case or in lathe/env/.
                env_name = line.split()[2]
                if os.path.isfile(os.path.join(os.path.dirname(path), env_name)):
                    env_name = os.path.join(os.path.dirname(path), env_name)
            if line.startswith('; options '):
                words += line[len('; options '):].split()
            if line.startswith('; defines '):
                words += ['-d' + w for w in line[len('; defines '):].split()]
    if d == 'err':
        return words
    if env_name == 'config':
        # A module e2e-config cases import: the environment of the first case it names.
        env_name = 'host'
        with open(path, encoding='latin-1') as f:
            first = f.readline().split()
        if first[1:3] == ['imported', 'by']:
            case = os.path.join(os.path.dirname(path), first[3].rstrip(',:'))
            with open(case, encoding='latin-1') as f:
                for line in f:
                    if line.startswith('; config '):
                        env_name = os.path.join(os.path.dirname(path), line.split()[2])
                        break
    return build.compiler_options(mapenv.read_env(build.env_path(env_name)), ()) + words


def capacity_error(path):
    """True if error case `path` is about a capacity of the compiler (errors 70 to 98, CAPACITY): its
    use of that table is not a need."""
    with open(path, encoding='latin-1') as f:
        words = f.readline().split()
    return len(words) > 2 and words[1] == "error" and (70 <= int(words[2]) <= 98 or int(words[2]) in CAPACITY)


def compile_program(path, kind, options, work, n, watched, peaks, where, done, gauged):
    """Compile `path` and the modules it imports into WORK/N. Returns [(path, message)] of the
    modules that failed, the error case itself apart."""
    import build
    try:
        order = build.module_order(path)
    except build.BuildError:
        order = [(build.module_name(path), path)]
    out_dir = os.path.join(work, str(n))
    os.makedirs(out_dir, exist_ok=True)
    host_li = os.path.join(work, 'host.li')
    failed = []
    for name, dep in order:
        key = (os.path.abspath(dep), options)
        if key in done and dep != path:
            li = os.path.join(done[key], name + '.li')
            if os.path.exists(li):
                shutil.copy(li, out_dir)
            continue
        if kind == 'err' and dep == path and os.path.exists(host_li) \
                and not os.path.exists(os.path.join(out_dir, 'host.li')):
            shutil.copy(host_li, out_dir)
        for w in watched.values():
            w.peak = 0
        Gauge.path = dep
        if kind == 'err' and dep == path and capacity_error(path):
            saved = dict(peaks), dict(where)
        status = compile_one(dep, out_dir, options)
        if kind == 'err' and dep == path and capacity_error(path):
            peaks.clear()
            peaks.update(saved[0])
            where.clear()
            where.update(saved[1])
        else:
            for k, w in watched.items():
                if k not in gauged and w.peak > peaks[k]:
                    peaks[k] = w.peak
                    where[k] = dep
        if status != 0 and not (kind == 'err' and dep == path):
            failed.append((dep, env._err.getvalue().decode('latin-1').strip()))
        else:
            done[key] = out_dir
        if name == 'host' and status == 0 and not os.path.exists(host_li):
            shutil.copy(os.path.join(out_dir, 'host.li'), host_li)
    return failed


def run_corpus(work):
    """Compile the corpus. Returns ({(module, array): peak}, {(module, array): the file that
    used the most}, [(path, message)] of the modules that failed but should not have)."""
    watched = watch()
    peaks = {key: 0 for key in watched}
    peaks[('inline', 'saved tokens')] = 0
    where = {key: '' for key in peaks}
    gauged = install_gauges(peaks, where)
    done = {}                       # (path, options) -> directory with its interface
    failed = []
    for n, (path, kind) in enumerate(corpus()):
        options = tuple(options_of(path))
        bad = compile_program(path, kind, options, work, n, watched, peaks, where, done, gauged)
        if bad and os.path.basename(os.path.dirname(path)) == 'rt':
            # A board module is built for a board only.
            bad = compile_program(path, kind, tuple(options_of(path, 'michael')), work, n, watched,
                                  peaks, where, done, gauged)
        failed += bad
    return peaks, where, failed


def main(argv):
    show_all = '--all' in argv
    peaks = None
    if '--corpus' in argv:
        work = tempfile.mkdtemp(prefix='lathe-memory-')
        try:
            peaks, where, failed = run_corpus(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)
            unwatch()
    print('%-9s %-22s %6s %3s %6s %6s' % ('module', 'array', 'elems', 'b/e', 'bytes',
                                            'peak' if peaks else ''))
    grand = 0
    for name in MODULES:
        rows = arrays(name)
        size = sum(n * w for _, n, w in rows)
        grand += size
        for attr, n, w in rows:
            if show_all or n * w >= 256:
                peak = '%6d' % peaks[(name, attr)] if peaks else ''
                print('%-9s %-22s %6d %3d %6d %s' % (name, attr, n, w, n * w, peak), end='')
                print('  ' + os.path.relpath(where[(name, attr)], LATHE) if peaks and peaks[(name, attr)] else '')
        print('%-9s %-22s %6s %3s %6d' % (name, '(all)', '', '', size))
    text = text_size()
    grand += text
    peak = '%6d' % peaks[('kernel', 'text')] if peaks else ''
    print('%-9s %-22s %6d %3d %6d %s' % ('kernel', 'text memory', text, 1, text, peak))
    if peaks:
        import inline
        print('%-9s %-22s %6d %3s %6s %6d  (in the text memory)' % (
            'inline', 'saved tokens', inline.SAVED_SIZE, '', '', peaks[('inline', 'saved tokens')]))
    print('%-9s %-22s %6s %3s %6d  (budget %d)' % ('total', '', '', '', grand, BUDGET))
    if peaks is not None:
        print()
        print('%d modules compiled' % len(corpus()))
        for path, said in failed:
            print('FAILED %s: %s' % (os.path.relpath(path, LATHE), said))


if __name__ == '__main__':
    main(sys.argv[1:])
