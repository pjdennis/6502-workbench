"""lathe/src/asmblock.lth against lathe/host/asmblock.py: lathe/src/asmtest.lth runs each
section of lathe/tests/scripts/asmblock.txt. A section is a script, which declares the names
its blocks use, then a line `--`, then a piece of Lathe source: `asm` blocks and the heads and
bodies of `asm` functions, which the script's `block` and `asmfunc` commands read through LEX
and SRC as EXPR and DECL do. It prints what FBUF finished (code, fix-ups, weights), the frame
and the symbols' weights and flags. main() below does the same with asmblock.py, and the
outputs, error reports, exit statuses and object files must be identical. Both are the small
build (lathe/host/README.md, "The small build")."""
import concurrent.futures
import os
import shutil
import sys
import tempfile
import unittest

import script_host as script
import env
import asmblock
import err
import fbuf
import kernel
import lex
import out
import reg
import src
import typetab

COMMANDS = (b"var func const table module local static type scope loops weight lconst source block "
            b"asmfunc finish symweight end begin ")

own = 0
module_m = 0
name_f = 0


def init():
    global own, module_m, name_f
    err.init()
    kernel.init()
    lex.init()
    src.init()
    typetab.init()
    out.init()
    if not out.open(kernel.keep_argument(1)):
        env.exit(2)
    module_m = script.name_of(b"m")
    kernel.module_add(module_m)
    kernel.module_add(script.name_of(b"util"))
    name_f = script.name_of(b"f")
    own = out.symbol(out.SYM_FUNCTION, module_m, 0, name_f)
    fbuf.begin()
    reg.begin(own)


def show_slot(n):
    script.show_byte(n)
    script.show_word(reg.slot_size[n])
    script.show_byte(reg.slot_class[n])
    script.show_byte(reg.slot_weight[n])
    script.show_byte(reg.slot_kind[n])
    script.show_word(reg.slot_name[n])
    script.show_bool(reg.slot_busy[n])
    env.put_byte(ord(','))


def symbol(scope, name, kind, t, value):
    s = kernel.sym_add(scope, name, kind)
    kernel.sym_type[s] = t
    kernel.sym_value[s] = value
    script.show_word(s)
    return s


def next_token():
    while True:
        lex.next()
        if lex.tok != lex.T_NL:
            return


def show_token():
    script.show_byte(lex.tok)
    script.show_word(lex.line)
    script.show_word(lex.col)


def run(c):
    n_ = script.number
    s_ = script.small
    if c == 0:
        a = s_()
        b = s_()
        d = s_()
        v = n_()
        s = symbol(d, script.name(), kernel.K_VAR, a, v)
        kernel.sym_flags[s] = b
    elif c == 1:
        n = script.name()
        a = s_()
        b = s_()
        s = symbol(a, n, kernel.K_FUNC, typetab.NO_TYPE, n_())
        kernel.sym_flags[s] = b
    elif c == 2:
        n = script.name()
        a = s_()
        symbol(kernel.SCOPE_MODULE, n, kernel.K_CONST, a, n_())
    elif c == 3:
        n = script.name()
        a = typetab.array_of(typetab.BYTE_TYPE, n_(), False)
        symbol(kernel.SCOPE_MODULE, n, kernel.K_CONST, a, 0)
    elif c == 4:
        n = script.name()
        symbol(kernel.SCOPE_MODULE, n, kernel.K_MODULE, typetab.NO_TYPE, n_())
    elif c == 5:
        n = script.name()
        v = n_()
        a = s_()
        b = s_()
        d = reg.new_slot(v, a, b, n)
        symbol(kernel.SCOPE_LOCAL, n, kernel.K_LOCAL, typetab.WORD_TYPE, d)
    elif c == 6:
        n = script.name()
        s = symbol(kernel.SCOPE_LOCAL, n, kernel.K_VAR, typetab.WORD_TYPE, 0)
        kernel.sym_obj[s] = out.symbol(out.SYM_VARIABLE, module_m, name_f, n)
    elif c == 7:
        symbol(kernel.SCOPE_MODULE, script.name(), kernel.K_TYPE, typetab.NO_TYPE, 0)
    elif c == 8:
        kernel.scope_begin()
    elif c == 9:
        reg.loop_depth = s_()
    elif c == 10:
        s = n_()
        kernel.sym_weight[s] = s_()
    elif c == 11:
        a = s_()
        reg.load_const(a, s_())
    elif c == 12:
        if not src.open_file(kernel.keep_argument(2)):
            env.exit(2)
    elif c == 13:
        next_token()
        if lex.tok != lex.T_ASM:
            env.exit(4)
        asmblock.block()
        show_token()
    elif c == 14:
        next_token()
        while lex.tok != lex.T_NL:
            lex.next()
        asmblock.function_body()
        show_token()
    elif c == 15:
        fbuf.finish(own, reg.local_count)
        script.show_finished()
        env.put_byte(ord('|'))
        for a in range(reg.local_count):
            show_slot(a)
    elif c == 16:
        s = n_()
        script.show_byte(kernel.sym_weight[s])
        script.show_byte(kernel.sym_flags[s])
    elif c == 17:
        out.end_module()
    elif c == 18:
        fbuf.begin()
        reg.begin(own)


def main():
    init()
    script.open_script(env._args[0])
    while script.next_line():
        run(script.command(COMMANDS))
        script.end_line()
    env.exit(0)


# ---- Lines reached -----------------------------------------------------------------------

def reached_lines(found):
    """Run every section with the host and note the lines of asmblock.py that run."""
    path = asmblock.__file__
    hit = set()

    def tracer(frame, event, arg):
        if frame.f_code.co_filename != path:
            return None
        if event in ('call', 'line'):
            hit.add(frame.f_lineno)
        return tracer

    old = sys.gettrace()
    sys.settrace(tracer)
    try:
        for args in found:
            script.host_run(main, args, True)
    finally:
        sys.settrace(old)
    return hit


def executable_lines():
    """{line: (function, its text)} of the lines of asmblock.py that hold a statement inside a
    function."""
    import ast
    with open(asmblock.__file__) as f:
        text = f.read()
    tree = ast.parse(text)
    source = text.split('\n')
    lines = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.stmt) and not isinstance(stmt, (ast.FunctionDef, ast.Global)) \
                        and not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)):
                    lines[stmt.lineno] = (node.name, source[stmt.lineno - 1].strip())
    return lines


class AsmblockTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-src-asmblock-')
        cls.image = script.support.build_program('asmtest', cls.dir, small=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def sections(self):
        """[(title, script, source)] of scripts/asmblock.txt, written to files: [(title, text,
        Lathe arguments, host arguments)]."""
        found = []
        for n, (title, text) in enumerate(script.sections('asmblock')):
            commands, _, source = text.partition(b'\n--\n')
            base = os.path.join(self.dir, 'asmblock-%d' % n)
            with open(base + '.txt', 'wb') as f:
                f.write(commands + b'\n')
            with open(base + '.lth', 'wb') as f:
                f.write(source)
            found.append((title, commands, [base + '.txt', base + '.loL', base + '.lth'],
                          [base + '.txt', base + '.loP', base + '.lth']))
        return found

    def test_every_section(self):
        found = self.sections()
        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
            lathe = list(pool.map(lambda r: script.support.run(self.image, r[2], timeout=600), found))
        for (title, commands, largs, hargs), (status, output, error, _) in zip(found, lathe):
            with self.subTest(section=title.decode()):
                host = script.host_run(main, hargs, True)
                if output != host[1]:
                    self.fail(script.first_difference(commands, output, host[1]))
                self.assertEqual((status, error), (host[0], host[2]))
                self.assertEqual(os.path.exists(largs[1]), os.path.exists(hargs[1]))
                if os.path.exists(hargs[1]):
                    with open(largs[1], 'rb') as a, open(hargs[1], 'rb') as b:
                        self.assertEqual(a.read(), b.read(), 'object file')
        self.assertGreater(len(found), 20)

    def test_the_sections_reach_every_line_of_asmblock_py(self):
        """Every statement of asmblock.py but those listed in UNREACHED runs in some section."""
        found = self.sections()
        lines = executable_lines()
        reached = reached_lines([f[3] for f in found])
        missed = [lines[n] for n in sorted(set(lines) - reached)]
        self.assertEqual(missed, UNREACHED)
        self.assertGreater(len(lines), 300)


# The statements of asmblock.py that no section reaches, and why.
UNREACHED = [
    ('number_term', 'return 0'),        # after err.fatal(), which does not return
    ('accumulator', 'fail_mode()'),     # instruction() calls it only for an instruction with the mode
]


if __name__ == '__main__':
    unittest.main()
