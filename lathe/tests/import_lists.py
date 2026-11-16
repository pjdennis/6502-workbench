"""Write the import lists of Lathe modules (lathe/docs/language.md, "Modules").

    python3 lathe/tests/import_lists.py [--check] FILE.lth...

Rewrites each `import` line of each FILE with the list of exactly the names the module uses of
that import, sorted by their lower-case spelling, wrapped at WIDTH columns; an import of which
the module uses every exported name gets no list, and one it uses nothing of gets `()`. With
--check nothing is written: it prints the files whose imports are not what it would write,
and exits with status 1 if there are any.

What a module uses comes from the host compiler, not from the text: each file is compiled in
this process, with its lists taken out, and every `m.name` the compiler resolves through the
module's own `import m` is noted (kernel.module_find(), from expressions, `asm` blocks and the
bodies of the module's own inline functions, which are looked at as they are saved). A name
used only under `#if` is found by compiling the file in every configuration it is built in
(CONFIGS: the environments of lathe/src/ for the twins and their test programs, and of
lathe/env/ too for the run-time modules), and taking all of them together. The modules a file
imports are compiled first, in the same configuration, from their own sources (beside the file
or in lathe/rt/), with their lists taken out too, so that nothing depends on the lists the
files have now.

Without its lists a module may need more of the name heap than the build gives it (that is
what the lists are for), so these compiles have a heap of HEAP bytes, whatever
kernel.NAME_HEAP_SIZE is.

A file, or a module it imports, that does not compile in a configuration it is built in is an
error: the tool prints the compiler's message and exits with status 2, in both modes, and writes
nothing. The only configurations passed over are those configs() leaves out on purpose.
"""
import io
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LATHE = os.path.dirname(HERE)
HOST = os.path.join(LATHE, 'host')
for p in (HOST, os.path.join(HOST, 'driver')):
    if p not in sys.path:
        sys.path.append(p)

import build  # noqa: E402
import env  # noqa: E402
import mapenv  # noqa: E402

WIDTH = 100
HEAP = 0xF000           # the name heap of the tool's compiles: any module fits without lists
SRC = os.path.join(LATHE, 'src')
COMPILER_ENVS = [os.path.join(SRC, e + '.env')
                 for e in ('compiler', 'compiler-small', 'compiler-bank', 'compiler-bbc', 'compiler-bbc-bank')]
LINKER_ENVS = [os.path.join(SRC, e + '.env') for e in ('linker', 'linker-bank', 'linker-bbc')]
BOARD_ENVS = [os.path.join(LATHE, 'env', e + '.env')
              for e in ('host', 'michael', 'wendy2', 'wendy2disk', 'bbc', 'bbc-bank', 'bbc-rom', 'bbc-dfs')]
IMPORT = re.compile(r'^(\s*)import\s+([A-Za-z][A-Za-z0-9_]*)\s*(\(?)', re.I)


# Run-time modules built in only some of the environments: the board modules need `define
# BOARD` 1 or 2 (board.lth does not compile for any other value; 3, the BBC, has no LCD or VIA
# of theirs), disk.lth's file ports `define DISK`, and rt_bbc.lth the module's slot `define
# MODULE_SLOT` (lathe/env/bbc-bank.env).
BOARDS_WITH_LCD = (1, 2)
RT_NEEDS = {'board.lth': ('BOARD', BOARDS_WITH_LCD), 'via.lth': ('BOARD', BOARDS_WITH_LCD),
            'lcd.lth': ('BOARD', BOARDS_WITH_LCD), 'timer.lth': ('BOARD', BOARDS_WITH_LCD),
            'disk.lth': ('DISK', None), 'rt_bbc.lth': ('MODULE_SLOT', None)}


def built_in(name, env_path):
    """Whether run-time module file NAME is built in the environment ENV_PATH."""
    define, values = RT_NEEDS[name]
    value = dict(mapenv.read_env(env_path).defines).get(define, 0)
    return value in values if values else bool(value)


# The modules of lathe/rt/bbc/ are the BBC's own, which build.py finds before lathe/rt/'s only
# when the environment is the BBC's (boards.Board.rt): they are built in those alone (bbcfs.lth
# needs their `define BBCFS`; lathe/rt/bbcfs.lth is the module for the others).
RT_BBC = os.path.join(LATHE, 'rt', 'bbc')


def is_bbc(env_path):
    import boards
    return boards.board_for(env_path) is boards.BOARDS['bbc']


def module_order(path, env_path):
    """build.module_order() as build.build() finds the modules for the environment: the board's
    own directories first (lathe/rt/bbc/ for the BBC)."""
    import boards
    board = boards.board_for(env_path)
    build._building.dirs = [os.path.join(build.RT, d) for d in (board.rt if board else ())]
    try:
        return build.module_order(path)
    finally:
        build._building.dirs = []


def configs(path):
    """The environment files `path` is built with."""
    name = os.path.basename(path)
    if os.path.dirname(os.path.abspath(path)) == RT_BBC:
        return [e for e in BOARD_ENVS + COMPILER_ENVS + LINKER_ENVS if is_bbc(e)]
    if os.path.dirname(os.path.abspath(path)) == SRC:
        if name.startswith('lk') or name == 'link.lth':
            return LINKER_ENVS
        if name == 'sys.lth':
            return COMPILER_ENVS + LINKER_ENVS
        return COMPILER_ENVS
    every = BOARD_ENVS + COMPILER_ENVS + LINKER_ENVS
    if name in RT_NEEDS:
        return [e for e in every if built_in(name, e)]
    return every


def options(env_path):
    return build.compiler_options(mapenv.read_env(env_path), ())


# ---- Import statements in the text ---------------------------------------------------------

def statements(text):
    """[(first line, last line, indent, module, comment)] of the `import` statements of a
    source, lines counted from 1; the comment is what follows the last line's code, from the
    blanks before its `;` on, or ''."""
    lines = text.split('\n')
    found = []
    i = 0
    while i < len(lines):
        m = IMPORT.match(lines[i].split(';', 1)[0])
        if not m:
            i += 1
            continue
        first = i
        if m.group(3):
            while ')' not in lines[i].split(';', 1)[0]:
                i += 1
        code = lines[i].split(';', 1)[0]
        comment = lines[i][len(code.rstrip()):]
        found.append((first + 1, i + 1, m.group(1), m.group(2), comment))
        i += 1
    return found


def without_lists(text):
    """The source with its import lists blanked out, every line where it was."""
    lines = text.split('\n')
    for first, last, indent, module, comment in statements(text):
        for n in range(first - 1, last):
            code = lines[n].split(';', 1)[0]
            if n == first - 1:
                head = IMPORT.match(code)
                code = head.group(1) + 'import ' + head.group(2)
            else:
                code = ''
            lines[n] = code + (';' + lines[n].split(';', 1)[1] if ';' in lines[n] else '')
    return '\n'.join(lines)


def spellings(text, module):
    """{lower-case name: its spelling} of each `module.name` the text writes."""
    found = {}
    for m in re.finditer(r'\b%s\.([A-Za-z][A-Za-z0-9_]*)' % re.escape(module), text, re.I):
        found.setdefault(m.group(1).lower(), m.group(1))
    return found


def written(indent, module, names, comment):
    """The lines of an import statement with these names (None: no list)."""
    head = '%simport %s' % (indent, module)
    if names is None:
        lines = [head]
    else:
        lines = []
        line = head + ' ('
        pad = ' ' * len(line)
        for i, name in enumerate(names):
            piece = name + (',' if i < len(names) - 1 else ')')
            if line.endswith('(') or len(line) + 1 + len(piece) <= WIDTH:
                line += ('' if line.endswith('(') else ' ') + piece
            else:
                lines.append(line)
                line = pad + piece
        if not names:
            line += ')'
        lines.append(line)
    return lines[:-1] + [lines[-1] + comment]


# ---- What the compiler resolves ------------------------------------------------------------

class Recorder:
    """While a file is compiled: for each import line, the names resolved through it, and how
    many names the module imported exports."""

    def __init__(self):
        import kernel
        self.kernel = kernel
        self.line_of = {}           # module symbol -> line of its import
        self.used = {}              # line -> {lower-case name}
        self.exported = {}          # line -> number of names exported
        self.on = False

    def install(self):
        import decl
        import kernel
        import lex
        self.saved = [(kernel, 'sym_add', kernel.sym_add), (kernel, 'module_find', kernel.module_find),
                      (decl, 'unit', decl.unit)]
        self.saved += [(kernel, 'NAME_HEAP_SIZE', kernel.NAME_HEAP_SIZE), (kernel, 'names', kernel.names)]
        kernel.NAME_HEAP_SIZE = HEAP
        kernel.names = bytearray(HEAP)
        sym_add, module_find, unit = kernel.sym_add, kernel.module_find, decl.unit

        def recording_sym_add(scope, name, kind):
            s = sym_add(scope, name, kind)
            if self.on and scope == kernel.SCOPE_MODULE and kind == kernel.K_MODULE:
                kernel.set_byte(s, kernel.C_FLAGS, kernel.byte_of(s, kernel.C_FLAGS) | kernel.SF_LIST)     # so that saved bodies are looked at
                self.line_of[s] = lex.line
                self.used.setdefault(lex.line, set())
            return s

        def recording_module_find(m, name):
            # The imports are whole, so nothing is hidden: no list to check (SF_LIST is set
            # only so that saved bodies are looked at), and a name not there is error 40.
            if self.on and m in self.line_of:
                self.used[self.line_of[m]].add(spelling(name))
                return kernel.sym_find(kernel.word_of(m, kernel.C_VALUE), name)
            return module_find(m, name)

        def counting_unit():
            unit()
            if self.on:
                for s, line in self.line_of.items():
                    self.exported[line] = exported(kernel.word_of(s, kernel.C_VALUE))
        kernel.sym_add = recording_sym_add
        kernel.module_find = recording_module_find
        decl.unit = counting_unit

    def uninstall(self):
        for m, attr, value in self.saved:
            setattr(m, attr, value)


def spelling(n):
    import kernel
    return bytes(kernel.name_char(n, i) for i in range(kernel.name_length(n))).decode('latin-1')


def exported(scope):
    """How many names imported module `scope` exports, read whole: its symbols and frozen
    entries, but for the types not `pub` and the modules of its interface."""
    import kernel
    count = 0
    for s in list(range(0, kernel.sym_count)) + list(range(kernel.thaw_top, kernel.MAX_SYMS)):
        if kernel.byte_of(s, kernel.C_SCOPE) == scope and kernel.byte_of(s, kernel.C_KIND) != kernel.K_MODULE \
                and (kernel.byte_of(s, kernel.C_KIND) != kernel.K_TYPE or kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_PUB):
            count += 1
    f = kernel.module_frozen[scope]
    while f != 0:
        count += 1
        f = kernel.name_word(f + kernel.N_LINK)
    return count


def compile_one(path, out_dir, opts):
    """Compile one module with the host compiler, in this process. Returns its status."""
    import lathec
    for h in range(1, env.MAX_FILES):
        if env._files[h] is not None:
            env._files[h].close()
            env._files[h] = None
    env._err = io.BytesIO()
    env._out = io.BytesIO()
    env.start(list(opts) + [path, out_dir])
    try:
        lathec.main()
        return 0
    except SystemExit as e:
        return e.code


def uses(paths):
    """{path: {import line: (names used, names exported)}} over every configuration of each, and
    [message] of each compile that failed."""
    found = {p: {} for p in paths}
    failed = []
    recorder = Recorder()
    recorder.install()
    work = tempfile.mkdtemp(prefix='lathe-lists-')
    try:
        for env_path in sorted({e for p in paths for e in configs(p)}):
            opts = options(env_path)
            out_dir = os.path.join(work, os.path.basename(env_path))
            stripped = os.path.join(out_dir, 'src')
            os.makedirs(stripped)
            done = {}
            for path in paths:
                if env_path not in configs(path):
                    continue
                try:
                    order = module_order(path, env_path)
                except build.BuildError as e:
                    failed.append('%s: %s' % (os.path.relpath(path), e))
                    continue
                ok = True
                for name, dep in order:
                    dep = os.path.abspath(dep)
                    if dep in done:
                        ok = ok and done[dep]
                        continue
                    copy = os.path.join(stripped, os.path.basename(dep))
                    with open(dep, encoding='latin-1') as f:
                        text = f.read()
                    with open(copy, 'w', encoding='latin-1') as f:
                        f.write(without_lists(text))
                    recorder.line_of, recorder.used, recorder.exported = {}, {}, {}
                    recorder.on = dep in found
                    done[dep] = ok and compile_one(copy, out_dir, opts) == 0
                    recorder.on = False
                    if ok and not done[dep]:
                        message = env._err.getvalue().decode('latin-1').strip()
                        failed.append('%s (%s): %s' % (os.path.relpath(dep), os.path.basename(env_path),
                                                       message.replace(copy, os.path.relpath(dep))))
                    ok = done[dep]
                    if ok and dep in found:
                        for line, names in recorder.used.items():
                            before = found[dep].get(line, (set(), 0))
                            found[dep][line] = (before[0] | names, recorder.exported[line])
    finally:
        recorder.uninstall()
        shutil.rmtree(work, ignore_errors=True)
    return found, failed


def rewritten(text, lines_used):
    """The text with each import statement compiled in some configuration written anew."""
    lines = text.split('\n')
    for first, last, indent, module, comment in reversed(statements(text)):
        if first not in lines_used:
            continue                    # under an #if no configuration compiles
        names, count = lines_used[first]
        if len(names) == count:
            listed = None
        else:
            spelled = spellings(text, module)
            listed = [spelled.get(n, n) for n in sorted(names)]
        lines[first - 1:last] = written(indent, module, listed, comment)
    return '\n'.join(lines)


def main(argv):
    check = '--check' in argv
    paths = [os.path.abspath(a) for a in argv if a != '--check']
    found, failed = uses(paths)
    if failed:
        for message in failed:
            print(message, file=sys.stderr)
        return 2
    wrong = []
    for path in paths:
        with open(path, encoding='latin-1') as f:
            text = f.read()
        new = rewritten(text, found[path])
        if new != text:
            wrong.append(path)
            if not check:
                with open(path, 'w', encoding='latin-1') as f:
                    f.write(new)
    if check:
        for path in wrong:
            print(os.path.relpath(path))
        return 1 if wrong else 0
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
