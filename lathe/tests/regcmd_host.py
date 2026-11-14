"""The Python twin of lathe/src/regcmd.lth: the commands of the scripts that test REG and COND,
run on the host modules (lathe/tests/test_src_reg.py, test_src_cond.py)."""
import script_host as script
import env
import err
import fbuf
import kernel
import out
import reg
import typetab

WORDS = (b"begin slot temp var func ftype ptr const wraps mem pslot preg addr faddr index mode pop "
         b"swap squeeze dup keep become dtemp load lconst force store put pconst imm alu cmp cmpc acc "
         b"modify stepx test testb implied transfer spill take intomem apart unaliased zp deref "
         b"clobber claim release forget direct use loops label place looplabel branch jump join "
         b"accepts assignable fit unify fitf class show state same offset constb isdirect finish end "
         b"arr symweight slots inregs value retype ")

own = 0


def init():
    global own
    err.init()
    kernel.init()
    typetab.init()
    out.init()
    if not out.open(kernel.keep_argument(1)):
        env.exit(2)
    m = script.name_of(b"m")
    kernel.module_add(m)
    kernel.module_add(script.name_of(b"util"))
    own = out.symbol(out.SYM_FUNCTION, m, 0, script.name_of(b"f"))
    fbuf.begin()
    reg.begin(own)


def members(s):
    p = script.small()
    r = script.small()
    for _ in range(p + r):
        t = script.small()
        kernel.member_add(t, script.small())
    kernel.sym_params[s] = p
    kernel.sym_results[s] = r


def show_entry(i):
    script.show_byte(reg.op_kind[i])
    script.show_byte(reg.op_type[i])
    script.show_word(reg.op_size[i])
    script.show_word(reg.op_value[i])
    script.show_word(reg.op_symbol[i])
    script.show_byte(reg.op_slot[i])
    script.show_byte(reg.op_flags[i])
    script.show_word(reg.op_var[i])
    script.show_word(reg.op_true[i])
    script.show_word(reg.op_false[i])
    script.show_byte(reg.op_mode[i])
    script.show_word(reg.op_stride[i])


def show_slot(n):
    script.show_byte(n)
    script.show_word(reg.slot_size[n])
    script.show_byte(reg.slot_class[n])
    script.show_byte(reg.slot_weight[n])
    script.show_byte(reg.slot_kind[n])
    script.show_word(reg.slot_name[n])
    script.show_bool(reg.slot_busy[n])
    env.put_byte(ord(','))


def show_slots():
    for n in range(reg.local_count):
        show_slot(n)
    for n in range(fbuf.FIRST_TEMP, fbuf.FIRST_TEMP + reg.temp_count):
        show_slot(n)


def run(c):
    n_ = script.number
    s_ = script.small
    if c == 0:
        fbuf.begin()
        reg.begin(own)
    elif c == 1:
        v = n_()
        a = s_()
        b = s_()
        script.show_byte(reg.new_slot(v, a, b, script.name()))
    elif c == 2:
        script.show_byte(reg.temp(n_()))
    elif c == 3:
        a = s_()
        b = s_()
        d = s_()
        v = n_()
        s = kernel.sym_add(d, script.name(), kernel.K_VAR)
        kernel.sym_type[s] = a
        kernel.sym_flags[s] = b
        kernel.sym_value[s] = v
        script.show_word(s)
    elif c == 4:
        n = script.name()
        a = s_()
        b = s_()
        s = kernel.sym_add(a, n, kernel.K_FUNC)
        kernel.sym_flags[s] = b
        members(s)
        script.show_word(s)
    elif c == 5:
        n = script.name()
        b = s_()
        s = kernel.sym_add(kernel.SCOPE_MODULE, n, kernel.K_TYPE)
        members(s)
        a = typetab.declared(typetab.FORM_FUNC, s)
        kernel.sym_type[s] = a
        if b & 1 != 0:
            typetab.make_recursive(a)
        script.show_word(s)
        script.show_byte(a)
    elif c == 6:
        script.show_byte(typetab.pointer_to(s_()))
    elif c == 7:
        a = s_()
        reg.push(reg.O_CONST, a, n_())
    elif c == 8:
        reg.op_flags[reg.depth - 1] = reg.op_flags[reg.depth - 1] | reg.F_WRAPS
    elif c == 9:
        a = s_()
        v = n_()
        b = s_()
        w = n_()
        d = s_()
        reg.push_memory(a, v, b, w, d, n_())
    elif c == 10:
        a = s_()
        reg.push_slot(a, s_())
    elif c == 11:
        reg.push_register(s_())
    elif c == 12:
        a = s_()
        v = n_()
        b = s_()
        reg.push(reg.O_ADDR, a, n_())
        reg.op_symbol[reg.depth - 1] = v
        reg.op_slot[reg.depth - 1] = b
    elif c == 13:
        v = n_()
        reg.push(reg.O_ADDR, typetab.NO_TYPE, 0)
        reg.op_var[reg.depth - 1] = v
        reg.op_symbol[reg.depth - 1] = n_()
    elif c == 14:
        reg.take_index(s_())
    elif c == 15:
        a = s_()
        reg.op_mode[a] = s_()
        reg.op_stride[a] = n_()
    elif c == 16:
        reg.pop()
    elif c == 17:
        reg.swap()
    elif c == 18:
        reg.squeeze()
    elif c == 19:
        reg.duplicate(s_())
    elif c == 20:
        reg.keep(s_())
    elif c == 21:
        a = s_()
        b = s_()
        reg.become(a, b, s_())
    elif c == 22:
        a = s_()
        reg.describe_temp(a, s_())
    elif c == 23:
        a = s_()
        b = s_()
        reg.load(a, b, s_())
    elif c == 24:
        a = s_()
        reg.load_const(a, s_())
    elif c == 25:
        a = s_()
        reg.force(a, s_())
    elif c == 26:
        a = s_()
        b = s_()
        reg.store(a, b, s_())
    elif c == 27:
        a = s_()
        b = s_()
        d = s_()
        reg.put(a, b, d, s_())
    elif c == 28:
        a = s_()
        b = s_()
        reg.put_const(a, b, s_())
    elif c == 29:
        a = s_()
        reg.immediate(a, s_())
    elif c == 30:
        a = s_()
        b = s_()
        reg.alu(a, b, s_())
    elif c == 31:
        a = s_()
        reg.compare(a, s_())
    elif c == 32:
        reg.compare_const(s_())
    elif c == 33:
        reg.accumulator(s_())
    elif c == 34:
        a = s_()
        b = s_()
        reg.modify(a, b, s_())
    elif c == 35:
        reg.step_x(s_())
    elif c == 36:
        reg.test(s_())
    elif c == 37:
        a = s_()
        reg.test_byte(a, s_())
    elif c == 38:
        reg.implied(s_())
    elif c == 39:
        a = s_()
        reg.transfer(a, s_())
    elif c == 40:
        reg.spill(s_())
    elif c == 41:
        reg.take(s_())
    elif c == 42:
        reg.into_memory(s_())
    elif c == 43:
        a = s_()
        reg.apart(a, s_())
    elif c == 44:
        a = s_()
        b = s_()
        reg.unaliased(a, b, script.flag())
    elif c == 45:
        reg.zero_page(s_())
    elif c == 46:
        script.show_bool(reg.dereferenced(s_()))
    elif c == 47:
        reg.clobber()
    elif c == 48:
        reg.claim(s_())
    elif c == 49:
        reg.release(s_())
    elif c == 50:
        reg.forget()
    elif c == 51:
        a = s_()
        b = s_()
        reg.direct(a, b, s_())
    elif c == 52:
        reg.use(s_())
    elif c == 53:
        reg.loop_depth = s_()
    elif c == 54:
        script.show_byte(fbuf.new_label())
    elif c == 55:
        reg.label(s_())
    elif c == 56:
        reg.loop_label(s_())
    elif c == 57:
        a = s_()
        reg.branch(a, s_())
    elif c == 58:
        reg.jump(s_())
    elif c == 59:
        a = s_()
        reg.join(a, s_())
    elif c == 60:
        a = s_()
        script.show_bool(reg.accepts(a, s_()))
    elif c == 61:
        a = s_()
        reg.assignable(a, s_())
    elif c == 62:
        a = s_()
        reg.fit(a, s_())
    elif c == 63:
        a = s_()
        script.show_byte(reg.unify(a, s_()))
    elif c == 64:
        a = s_()
        reg.fit_function(a, s_())
    elif c == 65:
        script.show_word(reg.class_symbol(n_()))
    elif c == 66:
        a = s_()
        show_entry(a)
        if reg.op_kind[a + reg.INDEX] != 0:
            env.put_byte(ord('/'))
            show_entry(a + reg.INDEX)
    elif c == 67:
        script.show_byte(reg.depth)
        script.show_word(reg.owner)
        script.show_byte(reg.flags)
        script.show_byte(reg.local_count)
        script.show_byte(reg.temp_count)
        script.show_byte(reg.loop_depth)
    elif c == 68:
        a = s_()
        script.show_bool(reg.same_place(a, s_()))
    elif c == 69:
        a = s_()
        script.show_word(reg.offset(a, s_()))
    elif c == 70:
        a = s_()
        b = s_()
        script.show_bool(reg.is_const_byte(a, b))
        script.show_byte(reg.const_byte(a, b))
    elif c == 71:
        script.show_bool(reg.is_direct(s_()))
    elif c == 72:
        fbuf.finish(own, reg.local_count)
        script.show_finished()
        env.put_byte(ord('|'))
        show_slots()
    elif c == 73:
        out.end_module()
    elif c == 74:
        a = s_()
        v = n_()
        script.show_byte(typetab.array_of(a, v, script.flag()))
    elif c == 75:
        s = n_()
        script.show_byte(kernel.sym_weight[s])
        script.show_byte(kernel.sym_flags[s])
    elif c == 76:
        show_slots()
    elif c == 77:
        script.show_bool(reg.in_registers(s_()))
    elif c == 78:
        a = s_()
        reg.op_value[a] = n_()
    elif c == 79:
        a = s_()
        reg.op_type[a] = s_()


def main():
    """regtest's main()."""
    init()
    script.open_script(env._args[0])
    while script.next_line():
        run(script.command(WORDS))
        script.end_line()
    env.exit(0)
