"""lathe/src/inlines.lth against lathe/host/inline.py: lathe/src/inlinetest.lth runs each section
of lathe/tests/scripts/inline.txt, which build a piece of Lathe source, save the bodies of
inline functions from it, write and read them as an interface does, and expand them: begin an
expansion, give its arguments as operands through GEN, replay its body, printing each token
and what its name means there, and end it. main() below does the same with inline.py, and the
outputs, error reports, exit statuses, object files and interface files must be identical.
Both are the small build (lathe/host/README.md, "The small build"), as gentest is.

The twin's module is `inlines`: `inline` is a keyword."""
import shutil
import tempfile
import unittest

import script_host as script
import regcmd_host
import env
import gen
import inline
import kernel
import lex
import reg
import src
import typetab

COMMANDS = (b"line text blank open next func params save record sym enter arg begin tokens leave "
            b"lookup lscope own slotname copy due leaves istate isyms gconst glocal gvar binary "
            b"asvalue accept preg slot fend write read iface ptr freeze module pop ")
SOURCE_SIZE = 512
SOURCE_AT = 0xA000          # where the source is in env.mem: above the text memory

source_length = 0
file = 0
iface = 0


def init():
    global file, iface, source_length
    regcmd_host.init()
    gen.init()
    gen.function_begin(regcmd_host.own)
    src.init()
    lex.init()
    file = kernel.keep_argument(0)
    iface = kernel.keep_argument(2)
    inline.init()
    source_length = 0


def add(c):
    global source_length
    if source_length == SOURCE_SIZE:
        env.exit(4)
    env.mem[SOURCE_AT + source_length] = c
    source_length += 1


def add_rest():
    if script.more():
        while True:
            ch, more = script.next_char()
            if not more:
                break
            add(ch)


def show_token():
    script.show_byte(lex.tok)
    script.show_word(lex.line)
    script.show_word(lex.col)
    if lex.tok == lex.T_NAME or lex.tok == lex.T_NUMBER:
        script.show_word(lex.value)
    elif lex.tok == lex.T_STRING:
        script.show_word(lex.string_length)
        for i in range(lex.string_length & 0xFF):
            script.show_byte(lex.string[i])


def show_record(f):
    r = kernel.sym_value[f]
    script.show_word(r - inline.saved_start)
    script.show_word(inline.word_at(r + inline.R_END) - inline.saved_start)
    script.show_word(inline.word_at(r + inline.R_LINE))
    script.show_bool(inline.word_at(r + inline.R_FILE) != 0)
    env.put_byte(0x20)
    script.show_byte(env.mem[r + inline.R_FLAGS])
    script.show_word(inline.word_at(r + inline.R_WRITTEN))
    for i in range(kernel.sym_params[f]):
        p = inline.param(f, i)
        script.show_word(inline.word_at(p))
        script.show_byte(env.mem[p + 2])
    env.put_byte(ord('|'))
    p = r + inline.R_PARAMS + kernel.sym_params[f] * inline.PARAM_SIZE
    while p < inline.word_at(r + inline.R_END):
        script.show_byte(env.mem[p])
        p += 1


def members(s):
    p = script.small()
    r = script.small()
    for n in range(p + r):
        t = script.small()
        kernel.member_add(t, script.small())
    kernel.sym_params[s] = p
    kernel.sym_results[s] = r


def show_found(s, found):
    script.show_word(s)
    script.show_bool(found)


def tokens():
    while True:
        lex.next()
        if lex.tok == lex.T_EOF:
            break
        show_token()
        if lex.tok == lex.T_NAME:
            s, found = inline.lookup(lex.value)
            show_found(s, found)
        env.put_byte(ord(','))
    src.close()


def show_state():
    script.show_byte(inline.level)
    script.show_byte(inline.depth)
    script.show_byte(inline.owned_count)
    script.show_byte(inline.alias_count)
    script.show_word(inline.saved_top - inline.saved_start)
    for d in range(1, inline.depth + 1):
        env.put_byte(ord('|'))
        script.show_word(inline.expanding[d])
        script.show_bool(inline.wanted[d])
        env.put_byte(0x20)
        script.show_byte(inline.done[d])
        script.show_bool(inline.lazy[d])
        env.put_byte(0x20)
        script.show_word(inline.sym_base[d])
        script.show_byte(inline.owned_base[d])
        script.show_byte(inline.alias_base[d])
        script.show_byte(inline.outer[d])
    env.put_byte(ord('|'))
    for n in range(inline.owned_count):
        script.show_byte(inline.owned[n])
    env.put_byte(ord('|'))
    for n in range(inline.alias_count):
        script.show_word(inline.alias[n])


def show_symbols(first):
    for s in range(first, kernel.sym_count):
        script.show_word(kernel.sym_name[s])
        script.show_byte(kernel.sym_scope[s])
        script.show_byte(kernel.sym_kind[s])
        script.show_byte(kernel.sym_type[s])
        script.show_word(kernel.sym_value[s])
        env.put_byte(ord(','))


def run(c):
    n_ = script.number
    s_ = script.small
    if c == 0:
        add_rest()
        add(0x0A)
    elif c == 1:
        add_rest()
    elif c == 2:
        for n in range(1, n_() + 1):
            add(0x0A)
    elif c == 3:
        lex.tok = lex.T_NL
        lex.open_brackets = 0
        src.push(kernel.open_memory(SOURCE_AT, SOURCE_AT + source_length), file)
        lex.next()
        show_token()
    elif c == 4:
        lex.next()
        show_token()
    elif c == 5:
        n = script.name()
        a = s_()
        b = s_()
        s = kernel.sym_add(a, n, kernel.K_FUNC)
        kernel.sym_flags[s] = b
        members(s)
        script.show_word(s)
    elif c == 6:
        s = n_()
        kernel.scope_begin()
        for a in range(kernel.sym_params[s]):
            v = kernel.sym_add(kernel.SCOPE_LOCAL, script.name(), kernel.K_LOCAL)
            kernel.sym_type[v] = kernel.member_type[kernel.sym_members[s] + a]
    elif c == 7:
        s = n_()
        inline.save(s)
        kernel.local_names = kernel.name_top
        kernel.scope_end()
        show_record(s)
    elif c == 8:
        show_record(n_())
    elif c == 9:
        a = s_()
        b = s_()
        d = s_()
        e = s_()
        v = n_()
        s = kernel.sym_add(b, script.name(), a)
        kernel.sym_flags[s] = d
        kernel.sym_type[s] = e
        kernel.sym_value[s] = v
        script.show_word(s)
    elif c == 10:
        s = n_()
        inline.enter(s, script.flag())
    elif c == 11:
        s = n_()
        inline.argument_symbol(s, s_())
    elif c == 12:
        inline.body_begin(n_())
    elif c == 13:
        tokens()
    elif c == 14:
        inline.leave()
    elif c == 15:
        s, found = inline.lookup(script.name())
        show_found(s, found)
    elif c == 16:
        script.show_byte(inline.local_scope())
    elif c == 17:
        script.show_byte(inline.own_slot(n_()))
    elif c == 18:
        n = script.name()
        script.show_word(inline.slot_name(n, s_()))
    elif c == 19:
        inline.copy_aliases()
    elif c == 20:
        script.show_bool(inline.copies_due())
    elif c == 21:
        script.show_bool(inline.leaves_operand())
    elif c == 22:
        show_state()
    elif c == 23:
        show_symbols(n_())
    elif c == 24:
        a = s_()
        gen.constant(a, n_())
    elif c == 25:
        a = s_()
        gen.local(a, s_())
    elif c == 26:
        gen.variable(n_())
    elif c == 27:
        gen.binary(s_())
    elif c == 28:
        gen.as_value()
    elif c == 29:
        gen.accept(s_())
    elif c == 30:
        reg.push_register(s_())
    elif c == 31:
        v = n_()
        a = s_()
        b = s_()
        script.show_byte(reg.new_slot(v, a, b, script.name()))
    elif c == 32:
        gen.function_end(s_())
        script.show_finished()
    elif c == 33:
        stream, ok = kernel.open_out(iface)
        inline.write(stream, n_())
        kernel.close(stream)
    elif c == 34:
        stream, ok = kernel.open_in(iface)
        p = kernel.text_top
        inline.read(stream, n_())
        kernel.close(stream)
        script.show_word(kernel.text_top - p)
    elif c == 35:
        stream, ok = kernel.open_out(iface)
        while script.more():
            kernel.put(stream, s_())
        kernel.close(stream)
    elif c == 36:
        script.show_byte(typetab.pointer_to(s_()))
    elif c == 37:
        a = s_()
        b = s_()
        d = s_()
        e = s_()
        v = n_()
        n = script.name()
        kernel.name_begin()
        for i in range(kernel.name_length(n)):
            kernel.name_add(kernel.name_char(n, i))
        kernel.freeze(a, b, d, e, v, 0, 0)
    elif c == 38:
        script.show_byte(kernel.module_add(script.name()))
    elif c == 39:
        reg.pop()


def main():
    init()
    script.open_script(env._args[0])
    while script.next_line():
        run(script.command(COMMANDS))
        script.end_line()
    env.exit(0)


class InlineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-src-inline-')
        cls.image = script.support.build_program('inlinetest', cls.dir, small=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_every_script(self):
        self.assertGreater(script.check_script(self, self.image, main, 'inline', self.dir,
                                               outputs=2, small=True), 5)


if __name__ == '__main__':
    unittest.main()
