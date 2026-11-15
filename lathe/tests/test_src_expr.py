"""lathe/src/expr.lth against lathe/host/expr.py: lathe/src/exprtest.lth runs each section of
lathe/tests/scripts/expr.txt. A section is a script, which declares the names its source uses
(variables, constants, tables, types, records, enumerations, functions of every kind, function
types, modules) by the commands of regcmd and exprtest, then a line `--`, then a piece of Lathe
source: bodies of functions, expressions, conditions, constants, types and declarations, which
the script's commands read through LEX and SRC as DECL does. It prints the token each command
hands back, the operands it leaves (regcmd's `show` and `state`), the code, fix-ups and weights
of the functions it ends, and the symbols it makes; the object file is compared too, and the
error output and status of a section that ends with an error. main() below does the same with
expr.py.

The program has EXPR, GEN and everything below them, about 50 KB of code: it is built banked on
Wendy 2 (lathe/host/README.md, "The banked build"), at the compiler's full capacities, as the
host is run. By default a representative part of the sections is run (every
third, the first and last included); LATHE_BANKED_ALL=1 runs all of them.

With LATHE_EXPR_COVERAGE=1 the test of the lines reached prints the statements of expr.py that
no section reaches."""
import os
import shutil
import sys
import tempfile
import unittest

import script_host as script
import regcmd_host
import env
import cond
import expr
import fbuf
import gen
import inline
import kernel
import lex
import reg
import src
import typetab

ALL = os.environ.get('LATHE_BANKED_ALL') == '1'

COMMANDS = (b"source first next sym record field enum fbegin param receive body fend expr cond econst "
            b"cnum type vtype decl save scope send gstore asvalue accept lresult gjump efunc initfn "
            b"cpu syms module einit setv dregion ")


def init():
    regcmd_host.init()
    gen.init()
    gen.function_begin(regcmd_host.own)
    gen.pend_type = 0               # as at the start: neither gen.init() nor function_begin() sets it
    cond.wanted_in_carry(False)
    src.init()
    lex.init()
    inline.init()
    expr.init()
    # What the Lathe program has when it starts, which a section before this one in the same
    # process may have left otherwise (one that ended with an error inside a block)
    expr.function = 0
    expr.asm_last = False
    expr.exit_label = reg.NONE
    expr.next_label = reg.NONE
    expr.placed_at = 0
    expr.critical_depth = 0
    expr.critical_inner = 0
    expr.case_count = 0
    expr.with_function = fbuf.NO_SLOT
    expr.with_loop = fbuf.NO_SLOT
    expr.with_entry = reg.NONE
    expr.placed_region = 0
    expr.data_region = 0
    expr.in_line = 0
    expr.in_col = 0


def show_token():
    script.show_byte(lex.tok)
    script.show_word(lex.line)
    script.show_word(lex.col)


def first_token():
    while True:
        lex.next()
        if lex.tok != lex.T_NL:
            return


def declared(form):
    s = kernel.sym_add(kernel.SCOPE_MODULE, script.name(), kernel.K_TYPE)
    t = typetab.declared(form, s)
    kernel.set_byte(s, kernel.C_TYPE, t)
    script.show_word(s)
    script.show_byte(t)


def add_field(s, name, t):
    r = kernel.byte_of(s, kernel.C_TYPE)
    f = kernel.sym_add(kernel.SCOPE_FIELDS + r, name, kernel.K_FIELD)
    kernel.set_byte(f, kernel.C_TYPE, t)
    kernel.set_word(f, kernel.C_VALUE, typetab.grow(r, typetab.size(t)))
    kernel.set_byte(s, kernel.C_PARAMS, kernel.byte_of(s, kernel.C_PARAMS) + 1)


def parameter(s, i):
    name = script.name()
    t = kernel.member_type_of(kernel.word_of(s, kernel.C_MEMBERS) + i)
    p = kernel.sym_add(kernel.SCOPE_LOCAL, name, kernel.K_LOCAL)
    kernel.set_byte(p, kernel.C_TYPE, t)
    kernel.set_word(p, kernel.C_VALUE, reg.new_slot(typetab.size(t), reg.CLASS_EITHER, reg.SLOT_PARAMETER, name))
    script.show_word(p)
    script.show_byte(kernel.word_of(p, kernel.C_VALUE) & 0xFF)


def show_symbols(first):
    for s in range(first, kernel.sym_count):
        script.show_word(kernel.word_of(s, kernel.C_NAME))
        script.show_byte(kernel.byte_of(s, kernel.C_SCOPE))
        script.show_byte(kernel.byte_of(s, kernel.C_KIND))
        script.show_byte(kernel.byte_of(s, kernel.C_FLAGS))
        script.show_byte(kernel.byte_of(s, kernel.C_TYPE))
        script.show_word(kernel.word_of(s, kernel.C_VALUE))
        script.show_word(kernel.word_of(s, kernel.C_OBJ))
        env.put_byte(ord(','))


def run(c):
    n_ = script.number
    s_ = script.small
    if c == 0:
        if not src.open_file(kernel.keep_argument(2)):
            env.exit(2)
    elif c == 1:
        first_token()
        show_token()
    elif c == 2:
        lex.next()
        show_token()
    elif c == 3:
        a = s_()
        b = s_()
        d = s_()
        e = s_()
        v = n_()
        s = kernel.sym_add(b, script.name(), a)
        kernel.set_byte(s, kernel.C_FLAGS, d)
        kernel.set_byte(s, kernel.C_TYPE, e)
        kernel.set_word(s, kernel.C_VALUE, v)
        script.show_word(s)
    elif c == 4:
        declared(typetab.FORM_RECORD)
    elif c == 5:
        s = n_()
        v = script.name()
        add_field(s, v, s_())
    elif c == 6:
        declared(typetab.FORM_ENUM)
    elif c == 7:
        s = n_()
        gen.function_begin(reg.object_symbol(s))
        gen.saves_frame = kernel.byte_of(s, kernel.C_FLAGS) & kernel.SF_RECURSIVE != 0
    elif c == 8:
        s = n_()
        i = 0
        while script.more():
            parameter(s, i)
            i += 1
    elif c == 9:
        gen.receive(n_())
    elif c == 10:
        expr.function_body(n_())
        show_token()
    elif c == 11:
        gen.function_end(s_())
        script.show_finished()
    elif c == 12:
        expr.expression()
        show_token()
    elif c == 13:
        script.show_word(expr.test())
        show_token()
    elif c == 14:
        expr.constant(s_())
        show_token()
    elif c == 15:
        script.show_word(expr.constant_number())
        show_token()
    elif c == 16:
        script.show_byte(expr.type_spec())
        show_token()
    elif c == 17:
        script.show_byte(expr.value_type())
        show_token()
    elif c == 18:
        a = s_()
        expr.variable(s_(), a)
        show_token()
    elif c == 19:
        s = n_()
        kernel.scope_begin()
        for i in range(kernel.byte_of(s, kernel.C_PARAMS)):
            v = kernel.sym_add(kernel.SCOPE_LOCAL, script.name(), kernel.K_LOCAL)
            kernel.set_byte(v, kernel.C_TYPE, kernel.member_type_of(kernel.word_of(s, kernel.C_MEMBERS) + i))
        inline.save(s)
        kernel.local_names = kernel.name_top
        kernel.scope_end()
        show_token()
    elif c == 20:
        kernel.scope_begin()
    elif c == 21:
        kernel.scope_end()
    elif c == 22:
        gen.store()
    elif c == 23:
        gen.as_value()
    elif c == 24:
        gen.accept(s_())
    elif c == 25:
        gen.load_result()
    elif c == 26:
        script.show_word(gen.jump_false())
    elif c == 27:
        script.show_word(expr.function)
    elif c == 28:
        s = n_()
        gen.init_function(s)
        script.show_finished()
    elif c == 29:
        gen.cpu = s_()
    elif c == 30:
        show_symbols(n_())
    elif c == 31:
        script.show_byte(kernel.module_add(script.name()))
    elif c == 32:
        expr.init()
    elif c == 33:
        s = n_()
        kernel.set_word(s, kernel.C_VALUE, n_())
    elif c == 34:
        expr.data_region = script.name()


def main():
    init()
    script.open_script(env._args[0])
    while script.next_line():
        c = script.find(COMMANDS)
        if c == script.NOT_FOUND:
            regcmd_host.run(script.command(regcmd_host.WORDS))
        else:
            run(c)
        script.end_line()
    env.exit(0)


# ---- Sections and lines reached ----------------------------------------------------------

def sections(work):
    """The sections of scripts/expr.txt written to files in `work`, each as its script and its
    source: [(title, script text, script path, source path)]."""
    found = []
    for n, (title, text) in enumerate(script.sections('expr')):
        commands, _, source = text.partition(b'\n--\n')
        base = os.path.join(work, 'expr-%d' % n)
        with open(base + '.txt', 'wb') as f:
            f.write(commands + b'\n')
        with open(base + '.lth', 'wb') as f:
            f.write(source)
        found.append((title, commands, base + '.txt', base + '.lth'))
    return found


def reached_lines(found):
    """Run every section with the host and note the lines of expr.py that run."""
    path = expr.__file__
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
        for title, commands, txt, lth in found:
            script.host_run(main, [txt, txt[:-4] + '.loP', lth])
    finally:
        sys.settrace(old)
    return hit


def executable_lines():
    """{line: (function, its text)} of the lines of expr.py that hold a statement inside a
    function."""
    import ast
    with open(expr.__file__) as f:
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


class ExprTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-src-expr-')
        cls.image = script.support.build_program('exprtest', cls.dir, banked=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_every_section(self):
        found = sections(self.dir)
        last = len(found) - 1
        chosen = [f for n, f in enumerate(found) if ALL or n % 3 == 0 or n == last]
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
            lathe = list(pool.map(lambda r: script.support.run_banked(
                self.image, [r[2], r[2][:-4] + '.loL', r[3]]), chosen))
        for (title, commands, txt, lth), (status, output, error, _) in zip(chosen, lathe):
            with self.subTest(section=title.decode()):
                here = os.getcwd()
                os.chdir(self.dir)
                try:
                    base = os.path.basename(txt)[:-4]
                    host = script.host_run(main, [base + '.txt', base + '.loP', base + '.lth'])
                finally:
                    os.chdir(here)
                if output != host[1]:
                    self.fail(script.first_difference(commands, output, host[1]))
                self.assertEqual((status, error), (host[0], host[2]))
                lathe_obj, host_obj = txt[:-4] + '.loL', txt[:-4] + '.loP'
                self.assertEqual(os.path.exists(lathe_obj), os.path.exists(host_obj))
                if os.path.exists(host_obj):
                    with open(lathe_obj, 'rb') as a, open(host_obj, 'rb') as b:
                        self.assertEqual(a.read(), b.read(), 'object file')
        self.assertGreater(len(found), 20)

    def test_the_sections_reach_every_line_of_expr_py(self):
        """Every statement of expr.py but those listed in UNREACHED runs in some section."""
        found = sections(self.dir)
        lines = executable_lines()
        here = os.getcwd()
        os.chdir(self.dir)
        try:
            reached = reached_lines([(t, c, os.path.basename(a), os.path.basename(b))
                                     for t, c, a, b in found])
        finally:
            os.chdir(here)
        missed = [lines[n] for n in sorted(set(lines) - reached)]
        if os.environ.get('LATHE_EXPR_COVERAGE') == '1':
            print('\n%d of %d statements of expr.py reached' % (len(lines) - len(missed), len(lines)))
            for m in missed:
                print('   ', m)
        self.assertEqual(missed, UNREACHED)


# The statements of expr.py that no section reaches, and why.
UNREACHED = [
    # Arguments wait in the frames of at most seven calls, each inside the arguments of the
    # one before, before the nesting limit (expr.MAX_NESTING) is reached: never sixteen.
    ('add_pending', 'err.fatal(err.E_OPERANDS_FULL)'),
    # 256 constants in the cases of one function: at the small build's capacities the function
    # buffer (1,024 bytes) is full first.
    ('case_constants', 'err.fatal(err.E_LABELS_FULL)'),
    # INLINE refuses `with` when it saves a body (inline.save()), so no expansion holds one.
    ('with_statement', 'err.fatal(err.E_INLINE_NOT_HERE)'),
]


if __name__ == '__main__':
    unittest.main()
