"""lathe/src/gen.lth against lathe/host/gen.py: lathe/src/gentest.lth runs each section of
lathe/tests/scripts/gen.txt, which push operands through GEN and compute, store, convert,
index, call and return, and end functions and the list of initial values; it prints what
each gives and the code, fix-ups and weights of each function it ends. main() below does the
same with gen.py (and the commands of regcmd_host.py), and the outputs, error reports, exit
statuses and object files must be identical. Both are the small build (lathe/host/README.md,
"The small build"): with GEN in it the program does not fit the emulator's machine at the
compiler's full capacities."""
import shutil
import tempfile
import unittest

import script_host as script
import regcmd_host
import env
import cond
import err
import gen
import kernel
import out
import typetab

COMMANDS = (b"ginit gbegin settle resolve gconst gfunc gfaddr objsym gvar gtable glocal param argsend "
            b"binary negate compl gstore assign arrow pair convert part sizeof len gindex record field "
            b"address anon tbegin telem tend copyarr accept hold protect inreg receive result tptr "
            b"through call saving caddr mark gcompare asvalue tleft tright ginvert gjump cwanted gcarry "
            b"lresult ret ientry loopb loope fend initial initfn cpu saves gstate kconst module at gstep "
            b"rtype mustp symval ")


def init():
    regcmd_host.init()
    gen.init()
    gen.function_begin(regcmd_host.own)
    gen.pend_type = 0               # as at the start: neither gen.init() nor function_begin() sets it
    cond.wanted_in_carry(False)


def run(c):
    n_ = script.number
    s_ = script.small
    if c == 0:
        gen.init()
    elif c == 1:
        gen.function_begin(regcmd_host.own)
    elif c == 2:
        gen.settle()
    elif c == 3:
        gen.resolve(script.flag())
    elif c == 4:
        a = s_()
        gen.constant(a, n_())
    elif c == 5:
        gen.function(n_())
    elif c == 6:
        gen.function_address()
    elif c == 7:
        script.show_word(gen.object_symbol(n_()))
    elif c == 8:
        gen.variable(n_())
    elif c == 9:
        gen.table(n_())
    elif c == 10:
        a = s_()
        gen.local(a, s_())
    elif c == 11:
        s = n_()
        gen.parameter(s, s_())
    elif c == 12:
        gen.arguments_end(n_())
    elif c == 13:
        gen.binary(s_())
    elif c == 14:
        gen.negate()
    elif c == 15:
        gen.complement()
    elif c == 16:
        gen.store()
    elif c == 17:
        gen.assign(s_())
    elif c == 18:
        gen.store_arrow()
    elif c == 19:
        gen.store_pair()
    elif c == 20:
        gen.convert(s_())
    elif c == 21:
        gen.part(s_())
    elif c == 22:
        gen.size_of(s_())
    elif c == 23:
        gen.length()
    elif c == 24:
        gen.index()
    elif c == 25:
        script.show_byte(gen.record_of())
    elif c == 26:
        v = n_()
        gen.field(v, s_())
    elif c == 27:
        gen.address()
    elif c == 28:
        script.show_word(gen.anonymous())
    elif c == 29:
        out.table_begin(n_())
    elif c == 30:
        v = n_()
        gen.table_element(v, n_())
    elif c == 31:
        s = n_()
        out.table_end(s, n_())
    elif c == 32:
        s = n_()
        gen.copy_array(s, n_())
    elif c == 33:
        gen.accept(s_())
    elif c == 34:
        gen.hold()
    elif c == 35:
        gen.protect()
    elif c == 36:
        s = n_()
        script.show_bool(gen.in_register(s, s_()))
    elif c == 37:
        gen.receive(n_())
    elif c == 38:
        gen.result(n_())
    elif c == 39:
        gen.through_pointer()
    elif c == 40:
        script.show_bool(gen.through(n_()))
    elif c == 41:
        s = n_()
        a = s_()
        gen.call(s, a, script.flag())
    elif c == 42:
        script.show_bool(gen.saving(n_()))
    elif c == 43:
        gen.code_address(n_())
    elif c == 44:
        script.show_word(gen.mark())
    elif c == 45:
        gen.compare(s_())
    elif c == 46:
        gen.as_value()
    elif c == 47:
        gen.test_left(script.flag())
    elif c == 48:
        gen.test_right()
    elif c == 49:
        gen.invert()
    elif c == 50:
        script.show_word(gen.jump_false())
    elif c == 51:
        gen.carry_wanted()
    elif c == 52:
        gen.carry()
    elif c == 53:
        gen.load_result()
    elif c == 54:
        gen.ret()
    elif c == 55:
        gen.interrupt_entry()
    elif c == 56:
        gen.loop_begin()
    elif c == 57:
        gen.loop_end()
    elif c == 58:
        gen.function_end(s_())
        script.show_finished()
    elif c == 59:
        s = n_()
        v = n_()
        a = s_()
        gen.initial(s, v, a, n_())
    elif c == 60:
        gen.init_function(n_())
        script.show_finished()
    elif c == 61:
        gen.cpu = s_()
    elif c == 62:
        gen.saves_frame = script.flag()
    elif c == 63:
        script.show_byte(gen.pend_op)
        script.show_byte(gen.pend_type)
        script.show_word(gen.outer)
        script.show_byte(gen.init_count)
        script.show_bool(gen.saves_frame)
    elif c == 64:
        a = s_()
        s = kernel.sym_add(kernel.SCOPE_MODULE, script.name(), kernel.K_CONST)
        kernel.sym_type[s] = a
        script.show_word(s)
    elif c == 65:
        script.show_byte(kernel.module_add(script.name()))
    elif c == 66:
        v = n_()
        err.set_file(kernel.keep_argument(0))
        err.position(v, n_())
    elif c == 67:
        a = s_()
        b = s_()
        gen.step(a, b, s_())
    elif c == 68:
        s = kernel.sym_add(kernel.SCOPE_MODULE, script.name(), kernel.K_TYPE)
        a = typetab.declared(typetab.FORM_RECORD, s)
        kernel.sym_type[s] = a
        typetab.grow(a, n_())
        script.show_word(s)
        script.show_byte(a)
    elif c == 69:
        script.show_bool(gen.must_protect())
    elif c == 70:
        s = n_()
        kernel.sym_value[s] = n_()


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


class GenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-src-gen-')
        cls.image = script.support.build_program('gentest', cls.dir, small=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_every_script(self):
        self.assertGreater(script.check_script(self, self.image, main, 'gen', self.dir,
                                               outputs=1, small=True), 5)


if __name__ == '__main__':
    unittest.main()
