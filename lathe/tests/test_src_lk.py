"""The linker's lower layers written in Lathe (lathe/src/lk_*.lth) against their host originals.

Two test programs, built with lathe/src/linker.env (the small build, LKSMALL), each run beside its
twin here, which calls the host modules the same way at the same capacities (lk_small.py):

    lktest1 ENV MODE OUT.bin [FILE]     lk_err, lk_op, lk_file, lk_envf, lk_out: the opcode
                                        tables, the messages, every setting of an environment
                                        file, an image and bank files written
    lktest2 ENV MAIN OUT.bin OUT.map OBJECT.lo...
                                        lk_rec, lk_sym, lk_tab, lk_name, lk_scan: every table the
                                        first reading of the object files fills, the names an
                                        error message gives, nodes made as lk_graph makes them

The inputs are real: the environment files of lathe/env/ and lathe/src/, those of the
configuration cases, and every link the linker's own tests make (test_lk_*.py, run again here
with their links recorded), good and bad; the object files of some end-to-end programs and of
lextest; and lk_synthetic's program at the size the small build can take, and a little larger,
which both must refuse alike. What the two print, their error output, their exit status and the
files they write must be identical.

With LATHE_LK_COVERAGE=1 in the environment, the test also prints which lines of the host
modules the runs reached (the Lathe runs reach the same lines).
"""
import concurrent.futures
import glob
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import src_support as support
import lathec_support
import lk_small
import env
import link
import lk_alloc
import lk_boot
import lk_envf
import lk_err
import lk_file
import lk_graph
import lk_map
import lk_name
import lk_op
import lk_out
import lk_rec
import lk_scan
import lk_sym
import lk_tab
import lk_win

ENV = os.path.join(support.SRC, 'linker.env')

# ---- lkshow.lth --------------------------------------------------------------------------

HEX = b'0123456789ABCDEF'


def show_byte(b):
    env.put_byte(HEX[(b >> 4) & 15])
    env.put_byte(HEX[b & 15])
    env.put_byte(32)


def show_word(w):
    env.put_byte(HEX[(w >> 12) & 15])
    env.put_byte(HEX[(w >> 8) & 15])
    show_byte(w & 0xFF)


def show_bool(f):
    env.put_byte(ord('T') if f else ord('F'))
    env.put_byte(32)


def label(c):
    env.put_byte(ord(c))
    env.put_byte(32)


def end_line():
    env.put_byte(10)


# ---- lktest1.lth -------------------------------------------------------------------------

ARG_FILE = 4
MODE_AT = 0x8000                # where the mode is copied to in env.mem


def show_args():
    label('a')
    show_byte(lk_file.arg_count())
    for i in range(0, lk_file.arg_count()):
        show_byte(lk_file.arg_length(i))
    end_line()


def show_ops():
    for op in range(0, 256):
        show_byte(lk_op.length(op))
        if lk_op.can_shrink(op):
            show_byte(lk_op.zp_opcode(op))
        else:
            label('-')
        show_bool(lk_op.is_branch(op, lk_op.CPU_6502))
        show_bool(lk_op.is_branch(op, lk_op.CPU_65C02))
        end_line()


NUMBERS = (0, 9, 10, 99, 100, 199, 255)
WORDS = (0, 1, 9, 10, 99, 100, 999, 1000, 9999, 10000, 12345, 65535)


def show_numbers():
    for n in NUMBERS:
        lk_err.put_number(n)
        lk_err.comma()
    for n in WORDS:
        lk_err.put_word(n)
        lk_err.arrow()
    lk_err.over(0, False)
    lk_err.over(1, False)
    lk_err.over(2, False)
    lk_err.over(65535, False)
    lk_err.over(5, True)
    lk_err.colon()
    lk_err.put(10)
    for n in range(1, lk_err.E_FARCALL_MISSING + 1):
        lk_err.begin(n)
        lk_err.put(10)


def show_text(name):
    show_word(name)
    if name != 0:
        for i in range(0, lk_envf.text[name - 1]):
            env.put_byte(lk_envf.text[name + i])
        env.put_byte(32)


def show_env():
    lk_envf.read()
    label('e')
    show_byte(lk_envf.cpu)
    for v in (lk_envf.zp_lo, lk_envf.zp_hi, lk_envf.code_lo, lk_envf.code_hi, lk_envf.data_lo,
              lk_envf.data_hi, lk_envf.have):
        show_word(v)
    show_bool(lk_envf.has_stack)
    show_word(lk_envf.stack)
    show_byte(lk_envf.exit_kind)
    show_word(lk_envf.exit_addr)
    show_bool(lk_envf.exit_keeps)
    show_bool(lk_envf.raw)
    show_bool(lk_envf.has_more)
    show_word(lk_envf.more_lo)
    show_word(lk_envf.more_hi)
    end_line()
    label('t')
    show_word(lk_envf.text_top)
    for i in range(0, lk_envf.text_top):
        show_byte(lk_envf.text[i])
    end_line()
    label('c')
    show_text(lk_envf.farcall)
    end_line()
    for b in range(0, lk_envf.win_count):
        label('w')
        show_text(lk_envf.win_name[b])
        show_word(lk_envf.win_lo[b])
        show_word(lk_envf.win_hi[b])
        show_byte(lk_envf.win_switch[b])
        show_word(lk_envf.win_reg[b])
        show_byte(lk_envf.win_mask[b])
        end_line()
    for b in range(0, lk_envf.bank_count):
        label('b')
        show_byte(lk_envf.bank_win[b])
        show_byte(lk_envf.bank_n[b])
        show_byte(lk_envf.bank_value[b])
        show_text(lk_envf.bank_file[b])
        end_line()
    for b in range(0, lk_envf.place_count):
        label('p')
        show_text(lk_envf.place_name[b])
        show_byte(lk_envf.place_bank[b])
        end_line()
    for b in range(0, lk_envf.region_count):
        label('r')
        show_text(lk_envf.region_name[b])
        show_byte(lk_envf.region_bank[b])
        end_line()
    label('x')
    show_bool(lk_envf.placed())
    if lk_envf.placed():
        b = lk_envf.window()
        show_byte(b)
        show_bool(lk_envf.is_overlay())
        show_bool(lk_envf.in_window((lk_envf.win_lo[b] - 1) & 0xFFFF))
        show_bool(lk_envf.in_window(lk_envf.win_lo[b]))
        show_bool(lk_envf.in_window(lk_envf.win_hi[b]))
        show_bool(lk_envf.in_window((lk_envf.win_hi[b] + 1) & 0xFFFF))
    end_line()


def write_image():
    lk_out.open_image()
    lk_out.seek((lk_envf.code_lo + 2) & 0xFFFF)
    lk_out.put(1)
    lk_out.put_word(0x1234)
    lk_out.seek((lk_envf.code_lo + 300) & 0xFFFF)
    lk_out.put(0xAA)
    lk_out.close_image(lk_envf.code_lo)


def write_banks():
    for b in range(0, lk_envf.bank_count):
        if lk_envf.bank_file[b] != 0:
            lk_out.open_bank(b)
            lk_out.put(b)
            lk_out.seek((lk_envf.win_lo[lk_envf.bank_win[b]] + 3) & 0xFFFF)
            lk_out.put_word(lk_envf.win_lo[lk_envf.bank_win[b]])
            lk_out.close_image(0)


def write_behind():
    lk_out.open_image()
    lk_out.put(1)
    lk_out.seek(lk_envf.code_lo)


def lktest1():
    size = env.arg_copy(lk_file.ARG_MAIN, MODE_AT)
    for i in range(0, size):
        c = env.mem[MODE_AT + i]
        if c == ord('a'):
            show_args()
        elif c == ord('o'):
            show_ops()
        elif c == ord('n'):
            show_numbers()
        elif c == ord('e'):
            show_env()
        elif c == ord('i'):
            write_image()
        elif c == ord('b'):
            write_banks()
        elif c == ord('s'):
            write_behind()
        elif c == ord('q'):
            label('q')
            show_bool(lk_file.open_in_quiet(ARG_FILE) != 0)
            end_line()
        elif c == ord('f'):
            env.close(lk_file.open_in(ARG_FILE))
        elif c == ord('u'):
            lk_err.fail(lk_err.E_USAGE)
    env.exit(0)


# ---- lktest2.lth -------------------------------------------------------------------------

def show_objects():
    label('o')
    show_byte(lk_name.object_count)
    show_word(lk_sym.count)
    show_word(lk_name.local_count)
    show_word(lk_name.heap_top)
    show_word(lk_name.main_sym)
    show_word(lk_name.fc_call)
    show_word(lk_name.fc_start)
    show_byte(lk_scan.pend_count)
    end_line()
    for obj in range(0, lk_name.object_count):
        label('j')
        show_word(lk_name.obj_first[obj])
        show_word(lk_name.obj_fn[obj])
        show_word(lk_name.obj_def[obj])
        show_byte(lk_scan.obj_cpu[obj])
        show_byte(lk_scan.cpu_of(obj))
        show_byte(lk_scan.obj_bank[obj])
        end_line()
    for obj in range(0, lk_envf.place_count):
        label('p')
        show_byte(lk_envf.place_bank[obj])
        end_line()


def show_locals():
    label('l')
    for i in range(0, lk_name.local_count):
        show_word(lk_name.local_at(i))
    end_line()


def show_functions():
    for f in range(0, lk_tab.fn_count):
        r = lk_tab.fn_ref(f)
        label('f')
        show_word(r)
        show_byte(lk_tab.fn_flags[f])
        show_word(lk_tab.fn_slot[f])
        show_word(lk_tab.fn_nslots(f))
        show_byte(lk_tab.fn_class[f])
        show_word(lk_tab.fn_edge[f])
        show_byte(lk_scan.object_of(f))
        show_byte(lk_scan.fn_bank(f))
        k, live = lk_tab.member_class(f)
        show_byte(k)
        show_bool(live)
        label(':')
        e = lk_tab.first_call(r)
        while e != 0:
            show_word(lk_tab.edge_sym(e - 1))
            show_byte(lk_tab.edge_flag(e - 1))
            show_bool(lk_scan.crosses(f, lk_tab.edge_sym(e - 1), lk_tab.edge_flag(e - 1)))
            e = lk_tab.next_call(r, e)
        end_line()
        lk_name.error_name(r)
        lk_err.put(10)


def show_slots():
    for s in range(0, lk_tab.slot_count):
        label('s')
        show_byte(lk_tab.slot_sz[s])
        show_byte(lk_tab.slot_weight_of(s))
        show_word(lk_tab.slot_bytes(s))
        show_byte(lk_tab.slot_class(s))
        show_bool(lk_tab.slot_in_zp(s))
        show_bool(lk_tab.slot_is_param(s))
        end_line()
    label('g')
    for b in range(0, lk_tab.big_count):
        show_word(lk_tab.big_slot[b])
        show_word(lk_tab.big_size[b])
    end_line()


def show_classes():
    for k in range(0, lk_tab.cls_count):
        r = lk_tab.cls_ref(k)
        label('k')
        show_byte(lk_tab.cls_rep[k])
        show_byte(lk_tab.class_of(k))
        show_byte(lk_tab.cls_np[k])
        show_word(lk_tab.cls_par[k])
        show_word(lk_tab.cls_namer[k])
        show_word(lk_tab.cls_edge[k])
        label(':')
        e = lk_tab.first_call(r)
        while e != 0:
            show_word(lk_tab.edge_sym(e - 1))
            show_byte(lk_tab.edge_flag(e - 1))
            e = lk_tab.next_call(r, e)
        end_line()
        lk_name.error_name(r)
        lk_err.put(10)
    for p in range(0, lk_tab.cp_count):
        label('c')
        show_word(lk_tab.cp_size[p])
        show_byte(lk_tab.cp_info[p])
        show_byte(lk_tab.cp_weight[p])
        end_line()
    for m in range(0, lk_tab.memb_count):
        label('m')
        show_word(lk_tab.memb_class[m])
        show_word(lk_tab.memb_func[m])
        end_line()


def show_calls():
    label('e')
    show_word(lk_tab.edge_count)
    show_word(lk_tab.waiting)
    for e in range(0, lk_tab.edge_count):
        show_word(lk_tab.edge_at(e))
    end_line()


def show_defs():
    for d in range(0, lk_tab.def_count):
        r = lk_tab.def_ref(d)
        label('d')
        show_word(r)
        show_word(lk_tab.def_a[d])
        show_word(lk_tab.def_w(d))
        show_word(lk_tab.def_b[d])
        show_byte(lk_tab.def_f[d])
        show_bool(lk_tab.is_kept_def(d))
        show_bool(lk_tab.is_kept_var(d))
        show_byte(lk_scan.def_bank(d))
        end_line()
        lk_name.error_name(r)
        lk_err.put(10)


def show_goto():
    for obj in range(0, lk_name.object_count):
        label('r')
        show_byte(lk_rec.goto(obj, 1))
        show_byte(lk_rec.goto(obj, 2))
        show_word(lk_rec.recno())
        show_word(lk_rec.left())
        show_byte(lk_rec.goto(obj, 2))
        show_byte(lk_rec.goto(obj, 1))
        show_word(lk_rec.left())
        end_line()
    lk_rec.close()


CONTEXTS = (1, 1, 1, 0, 1, 3, 2, 1, 1, 4, 1, 1, 1, 7, 1, 1)


def make_nodes():
    lk_tab.ctx_count = 3
    for f in range(0, lk_tab.fn_count):
        lk_tab.fn_ctx[f] = CONTEXTS[f & 15]
    for k in range(0, lk_tab.cls_count):
        lk_tab.cls_reach[k] = 1 if k % 3 != 2 else 0
        lk_tab.cls_ctx[k] = k % 3
    lk_tab.node_count = lk_tab.fn_count
    for f in range(0, lk_tab.fn_count):
        for ctx in range(lk_tab.ctx_count - 1, -1, -1):
            if lk_tab.has_copy(f, ctx):
                lk_tab.work[lk_tab.W_CTXZ + f] = ctx << 8
    for f in range(0, lk_tab.fn_count):
        first = True
        for ctx in range(0, lk_tab.ctx_count):
            if lk_tab.has_copy(f, ctx):
                if not first:
                    lk_tab.new_node(f, ctx)
                first = False
    lk_tab.extra_end = lk_tab.node_count
    for k in range(0, lk_tab.cls_count):
        if lk_tab.cls_reach[k] != 0:
            lk_tab.cls_node[k] = lk_tab.node_count
            lk_tab.new_node(lk_tab.CLASS_NODE + k, lk_tab.cls_ctx[k])


def show_nodes():
    make_nodes()
    label('n')
    show_word(lk_tab.node_count)
    show_word(lk_tab.extra_end)
    end_line()
    n = lk_tab.first_in_order()
    while n != lk_tab.NONE:
        lk_tab.set_zbase(n, (n * 3) & 0xFF)
        lk_tab.work[lk_tab.W_MBASE + n] = (n * 5) & 0xFFFF
        label('v')
        show_word(n)
        show_word(lk_tab.own_of(n))
        show_byte(lk_tab.ctx_of(n))
        show_byte(lk_tab.zbase_of(n))
        show_word(lk_tab.mbase_of(n))
        show_bool(lk_tab.is_node(n))
        show_bool(lk_tab.is_extra_copy(n))
        show_bool(lk_tab.node_is_class(n))
        show_word(lk_tab.node_sym(n))
        if lk_tab.node_is_class(n):
            show_byte(lk_tab.node_class(n))
        end_line()
        lk_name.error_node(n)
        lk_err.put(10)
        n = lk_tab.next_in_order(n)
    for f in range(0, lk_tab.fn_count):
        label('y')
        show_word(lk_tab.first_node(f))
        show_word(lk_tab.first_extra(f))
        for ctx in range(0, lk_tab.ctx_count):
            show_bool(lk_tab.has_copy(f, ctx))
            if lk_tab.has_copy(f, ctx):
                show_word(lk_tab.copy_node(f, ctx))
                show_bool(lk_tab.in_block(f, ctx))
        if lk_tab.fn_nslots(f) != 0:
            show_bool(lk_tab.in_frame(f, 0, False))
            show_bool(lk_tab.in_frame(f, 0, True))
        end_line()
    label('z')
    show_word(lk_tab.add16(1, 2))
    show_bool(lk_tab.overflow)
    show_word(lk_tab.add16(0xFFFF, 0))
    show_bool(lk_tab.overflow)
    show_word(lk_tab.add16(0x8000, 0x8000))
    show_bool(lk_tab.overflow)
    end_line()


def show_held():
    handle = lk_file.open_out(lk_file.ARG_MAP)
    for obj in range(0, lk_name.object_count):
        lk_name.buf_begin(0, 2 * lk_tab.W_SCC)
        lk_rec.open_object(obj)
        kind = lk_rec.advance()
        while kind != lk_rec.R_END:
            if kind == lk_rec.R_MOD:
                lk_rec.get_byte()
                lk_rec.get_byte()
                lk_name.keep_at(2 * lk_tab.W_SCC)
                lk_name.write_held(handle, 2 * lk_tab.W_SCC)
                env.write(handle, 10)
            elif kind == lk_rec.R_SYM:
                lk_rec.get_byte()
                pos = lk_name.buf_keep()
                lk_name.write_held(handle, pos)
                env.write(handle, 32)
            kind = lk_rec.advance()
        env.write(handle, 10)
        label('h')
        show_word(lk_name.buf_top)
        end_line()
    lk_rec.close()
    env.close(handle)


def lktest2():
    if lk_file.arg_count() <= lk_file.ARG_OBJECT:
        lk_err.fail(lk_err.E_USAGE)
    lk_envf.read()
    lk_scan.scan_all()
    show_objects()
    show_locals()
    show_functions()
    show_slots()
    show_classes()
    show_calls()
    show_defs()
    show_goto()
    show_nodes()
    show_held()
    if lk_tab.fn_count != 0 and lk_tab.def_count != 0:
        lk_name.fail_in(lk_err.E_UNDEFINED, lk_tab.def_ref(0), lk_tab.fn_ref(0))
    env.exit(0)


# ---- lktest3.lth and lktest4.lth ---------------------------------------------------------

def find_main():
    """lktest3.lth's find_main is a copy of link.find_main."""
    return link.find_main()


def show_graph():
    label('g')
    show_byte(lk_tab.ctx_count)
    show_word(lk_tab.node_count)
    show_word(lk_tab.extra_end)
    show_word(lk_graph.order_count)
    show_word(lk_graph.scc_count)
    end_line()
    label('f')
    for f in range(0, lk_tab.fn_count):
        show_byte(lk_tab.fn_ctx[f])
        show_byte(lk_tab.fn_flags[f])
    end_line()
    for k in range(0, lk_tab.cls_count):
        label('k')
        show_byte(lk_tab.cls_reach[k])
        if lk_tab.cls_reach[k] != 0:
            show_byte(lk_tab.cls_ctx[k])
            show_word(lk_tab.cls_node[k])
        end_line()
    label('c')
    for p in range(0, lk_tab.cp_count):
        show_byte(lk_tab.cp_info[p])
        show_byte(lk_tab.cp_weight[p])
    end_line()
    label('d')
    for d in range(0, lk_tab.def_count):
        show_byte(lk_tab.def_f[d])
    end_line()
    for n in range(0, lk_tab.node_count):
        if lk_tab.is_node(n):
            label('n')
            show_word(n)
            show_word(lk_tab.own_of(n))
            show_byte(lk_tab.ctx_of(n))
            show_word(lk_tab.work[lk_tab.W_SCC + n])
            label(':')
            e = lk_graph.first_edge(n)
            while e != 0:
                target, applies = lk_graph.edge_node(n, e)
                if applies:
                    show_word(target)
                else:
                    label('-')
                e = lk_graph.next_edge(n, e)
            end_line()
    label('o')
    for n in range(0, lk_graph.order_count):
        show_word(lk_tab.work[lk_tab.W_ORDER + n])
    end_line()


def show_stubs():
    label('s')
    show_word(lk_win.stub_count)
    for obj in range(0, lk_name.object_count + 1):
        show_word(lk_win.obj_stub[obj])
    label(':')
    for f in range(0, lk_tab.fn_count):
        if lk_win.has_stub(f):
            show_word(f)
            show_byte(lk_win.copies(f))
    end_line()


def show_boot(main_fn):
    for n in range(0, lk_tab.node_count):
        lk_tab.work[lk_tab.W_ADDR + n] = (lk_envf.code_lo + 0x100 + 7 * n) & 0xFFFF
    label('b')
    show_word(lk_boot.plan())
    show_word(lk_boot.start_addr)
    show_word(lk_boot.start_len)
    show_word(lk_boot.init_addr)
    show_word(lk_boot.init_len)
    show_word(lk_boot.table_addr)
    show_word(lk_boot.table_len)
    show_word(lk_win.stub_base)
    show_byte(lk_win.table_count)
    for i in range(0, lk_win.table_count):
        show_byte(lk_win.table_bank(i))
    label(':')
    for n in range(0, lk_tab.node_count):
        if lk_tab.is_node(n) and not lk_tab.node_is_class(n) and lk_win.has_stub(lk_tab.own_of(n)):
            show_word(lk_win.stub_addr(n))
    end_line()
    lk_out.open_image()
    lk_boot.write(main_fn)
    lk_out.close_image(lk_boot.start_addr)


def lktest3():
    if lk_file.arg_count() <= lk_file.ARG_OBJECT:
        lk_err.fail(lk_err.E_USAGE)
    lk_envf.read()
    lk_scan.scan_all()
    main_sym = find_main()
    lk_graph.build(main_sym)
    show_graph()
    lk_win.check_interrupts()
    lk_win.mark_stubs(lk_sym.row_of(main_sym))
    show_stubs()
    show_boot(lk_sym.row_of(main_sym))
    env.exit(0)


def show_storage():
    label('z')
    show_word(lk_alloc.zp_cap)
    show_word(lk_alloc.zp_vars)
    show_word(lk_alloc.zp_used)
    show_word(lk_alloc.layouts)
    for ctx in range(0, lk_tab.ctx_count):
        show_word(lk_alloc.ctx_bottom[ctx])
        show_word(lk_alloc.ctx_depth[ctx])
    end_line()
    for n in range(0, lk_tab.node_count):
        if lk_tab.is_node(n):
            label('v')
            show_byte(lk_tab.zbase_of(n))
            show_word(lk_tab.mbase_of(n))
            show_word(lk_tab.work[lk_tab.W_ZSIZE + n])
            show_word(lk_tab.work[lk_alloc.LAY_BASE + n])
            show_word(lk_tab.work[lk_alloc.LAY_END + n])
            show_word(lk_tab.work[lk_alloc.LAY_SIZE + n])
            show_word(lk_tab.work[lk_alloc.LAY_DOWN + n])
            show_word(lk_alloc.zp_size(n))
            if not lk_tab.node_is_class(n):
                label(':')
                f = lk_tab.own_of(n)
                for i in range(0, lk_tab.fn_nslots(f) & 0xFF):
                    show_word(lk_alloc.slot_addr(n, i))
            end_line()
    label('t')
    for s in range(0, lk_tab.slot_count):
        show_byte(lk_tab.slot_sz[s])
    end_line()
    label('p')
    for p in range(0, lk_tab.cp_count):
        show_byte(lk_tab.cp_info[p])
        show_word(lk_tab.cp_addr[p])
    end_line()
    label('a')
    for d in range(0, lk_tab.def_count):
        show_byte(lk_tab.def_f[d])
        if lk_tab.is_kept_var(d):
            show_word(lk_tab.def_a[d])
            show_byte(lk_win.bank_def(d))
            show_byte(lk_win.def_dest(d))
    end_line()


def lktest4():
    if lk_file.arg_count() <= lk_file.ARG_OBJECT:
        lk_err.fail(lk_err.E_USAGE)
    lk_envf.read()
    lk_scan.scan_all()
    main_sym = find_main()
    lk_graph.build(main_sym)
    lk_win.check_interrupts()
    lk_win.mark_stubs(lk_sym.row_of(main_sym))
    lk_alloc.allocate()
    show_storage()
    env.exit(0)


# ---- running both ------------------------------------------------------------------------

def host_run(main, args, cwd):
    """main() over the host modules at the small capacities, in directory cwd: (status, output,
    error output)."""
    lathec_support.fresh()
    lk_small.load(True)
    env._out = io.BytesIO()
    env.start(args)
    status = 0
    here = os.getcwd()
    os.chdir(cwd)
    try:
        main()
    except SystemExit as e:
        status = e.code
    finally:
        os.chdir(here)
    return status, env._out.getvalue(), env._err.getvalue()


def files_of(d):
    found = {}
    for top, dirs, names in os.walk(d):
        for name in names:
            with open(os.path.join(top, name), 'rb') as f:
                found[os.path.relpath(os.path.join(top, name), d)] = f.read()
    return found


class Case:
    """One run of a test program: the files it starts with, its arguments, and a title."""

    def __init__(self, title, files, args):
        self.title = title
        self.files = files          # {name: bytes}
        self.args = args


def lathe_and_host(test, image, main, cases, work):
    """Run every case with the Lathe program (in parallel) and with its twin, each in a
    directory of its own holding the case's files, and compare all they give. Returns the
    number of cases."""
    dirs = []
    for n, case in enumerate(cases):
        pair = []
        for side in 'LP':
            d = os.path.join(work, '%d%s' % (n, side))
            os.makedirs(d)
            for name, data in case.files.items():
                os.makedirs(os.path.dirname(os.path.join(d, name)), exist_ok=True)
                with open(os.path.join(d, name), 'wb') as f:
                    f.write(data)
            pair.append(d)
        dirs.append(pair)
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        lathe = list(pool.map(lambda c: support.run(image, c[0].args, timeout=600, cwd=c[1][0]),
                              zip(cases, dirs)))
    for case, (dl, dp), (status, out, err, _) in zip(cases, dirs, lathe):
        host = host_run(main, case.args, dp)
        with test.subTest(case=case.title):
            if out != host[1]:
                test.fail(first_difference(out, host[1]))
            test.assertEqual(err.decode('latin-1'), host[2].decode('latin-1'))
            test.assertEqual(status, host[0])
            test.assertEqual(files_of(dl), files_of(dp))
    return len(cases)


def first_difference(a, b):
    la, lb = a.split(b'\n'), b.split(b'\n')
    for n in range(max(len(la), len(lb))):
        x = la[n] if n < len(la) else b'<none>'
        y = lb[n] if n < len(lb) else b'<none>'
        if x != y:
            return 'line %d:\n  lathe %s\n  host  %s' % (n + 1, x[:300].decode('latin-1'), y[:300].decode('latin-1'))
    return 'outputs differ'


# ---- the inputs --------------------------------------------------------------------------

LINK_TESTS = ('test_lk_errors', 'test_lk_windows', 'test_lk_classes', 'test_lk_calls',
              'test_lk_contexts', 'test_lk_storage', 'test_lk_image', 'test_lk_output')


def recorded_links():
    """Every link the linker's own tests make, as [(env text, [object bytes], main, args)]:
    their tests are run again here, with link() recording what it is given."""
    import importlib
    import test_lk_support
    found = []
    seen = set()
    real = test_lk_support.link

    def recording(objects, env=test_lk_support.HOST_ENV, main=None, args=None, asm=False,
                  command_file=None):
        if command_file is not None:        # the whole linker's (test_src_link.command_files)
            return real(objects, env, main, args, asm, command_file)
        data = [o.to_bytes() if isinstance(o, test_lk_support.Obj) else o if isinstance(o, bytes)
                else o.bytes() for o in objects]
        if main is None:
            main = test_lk_support._module_name(objects[0])
        key = (env, tuple(data), main, tuple(args) if args else None)
        if key not in seen:
            seen.add(key)
            found.append((env, data, main, args))
        return real(objects, env, main, args, asm)

    modules = [importlib.import_module(m) for m in LINK_TESTS]
    saved = [(m, m.link) for m in modules if hasattr(m, 'link')]
    for m, _ in saved:
        m.link = recording
    try:
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(m) for m in modules)
        unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    finally:
        for m, f in saved:
            m.link = f
    return found


def link_case(title, env_text, objects, main, args=None):
    files = {'e.env': env_text.encode('latin-1')}
    names = []
    for i, data in enumerate(objects):
        files['m%d.lo' % i] = data
        names.append('m%d.lo' % i)
    if args is None:
        args = ['e.env', main, 'out.bin', 'out.map'] + names
    return Case(title, files, args)


def hand_made_links():
    """Links the linker's tests do not make, for what they do not reach: [(title, objects, main)]
    in HOST_ENV. Object files built record by record (test_lk_support)."""
    from test_lk_support import Obj, record, routine, string, word, POINTER
    found = []

    def case(title, *objects, main=None):
        found.append((title, [o.to_bytes() for o in objects], main or objects[0].name))

    def one(title, build):
        o = Obj('t')
        build(o)
        case(title, o)

    one('a SYM record of kind 0', lambda o: o.raw(3, bytes((0,)) + string('t.x')))
    one('a variable of zero page class 3', lambda o: o.var('x', 1, zp_class=3))
    one('a FUNC record inside a function', lambda o: (o.raw(7, word(o.f('a')) + b'\0'), o.func('main')))
    one('a SLOT record outside a function', lambda o: o.raw(8, word(1) + bytes((1, 0, 1)) + string('s')))
    one('a slot of zero page class 3', lambda o: o.func('main', slots=[(1, 3, 0, 1, 's')]))
    one('a slot of kind 3', lambda o: o.func('main', slots=[(1, 1, 0, 3, 's')]))
    one('a CALL record outside a function', lambda o: o.raw(9, word(o.f('main')) + b'\0' + word(0xFFFF)))
    one('a call made while a variable waits', lambda o: o.func('main', calls=[(o.f('g'), 0, o.v('x'))]))
    one('a call through a pointer of a function', lambda o: o.func('main', calls=[(o.f('g'), POINTER, 0xFFFF)]))
    one('a WGT record inside a function', lambda o: (o.raw(7, word(o.f('main')) + b'\0'),
                                                     o.wgt((o.v('x'), 0xFF, 1)), o.raw(12)))
    one('a WGT record of 3 bytes', lambda o: o.raw(15, b'\0\0\0'))
    one('a WGT entry for a slot of a variable', lambda o: (o.var('y', 1), o.wgt((o.v('y'), 0, 1))))
    one('a FIX record outside a function', lambda o: o.raw(10, b''))
    one('a FIX record of 7 bytes', lambda o: (o.raw(7, word(o.f('main')) + b'\0'), o.raw(10, b'\0' * 7)))
    one('a DFIX record inside a function', lambda o: (o.raw(7, word(o.f('main')) + b'\0'), o.raw(6, b''),
                                                      o.raw(12)))
    one('a DFIX record before a function', lambda o: (o.raw(6, b''), o.func('main')))
    one('a record of an unknown type', lambda o: o.raw(0x20, b''))
    one('a name longer than its record', lambda o: o.raw(3, bytes((1, 5))))
    one('a module name of 65 characters', lambda o: (o.func('main'), setattr(o, 'records', [record(1, bytes((2, 0)) + string('t' * 65))] + o.records[1:])))
    one('a class with the names of its parameters', lambda o: (o.clas('k', [1, 2], names=['a', 'bc']), o.func('main')))
    one('a weight for a slot a defined function lacks',
        lambda o: (o.func('main', slots=[(1, 1, 0, 1, 's')]), o.wgt((o.f('main'), 3, 1))))
    one('a weight for a parameter a class lacks', lambda o: (o.clas('k', [1]), o.wgt((o.k('k'), 1, 1))))
    one('weights for parameters of a class', lambda o: (o.clas('k', [1, 2]), o.wgt((o.k('k'), 1, 9)),
                                                         o.wgt((o.k('k'), 1, 250)), o.func('main')))
    one('more than 64 slots of 15 bytes or more', lambda o: o.func('main', slots=[(16, 2, 0, 1, 's%d' % i)
                                                                                for i in range(65)]))
    one('2001 SYM records of one name', lambda o: [o.raw(3, bytes((2,)) + string('t.x')) for _ in range(2001)])
    one('calls made while the arguments of two others wait',
        lambda o: (o.func('h'), o.func('main', calls=[(o.f('g'), 0, o.f('h')), (o.f('g'), 0, o.f('h')),
                                                      (o.f('g2'), 0, o.f('later')), (o.f('h'), 0, o.k('k'))]),
                   o.func('g'), o.func('g2'), o.func('later'), o.clas('k', [1])))

    a, b = Obj('a'), Obj('b')
    a.wgt((a.v('b.x'), 0xFF, 200), (a.v('b.y'), 0xFF, 3))
    a.func('main')
    b.var('x', 1, weight=100)
    b.var('y', 2, weight=9)
    case('weights for variables defined later and earlier', a, b, Obj('c'))
    c = Obj('c')
    c.var('z', 1, weight=250)
    d = Obj('d')
    d.wgt((d.v('c.z'), 0xFF, 10), (d.f('c.f'), 0, 7))
    d.func('main')
    c.func('f', slots=[(1, 1, 3, 0, 'p')])
    case('a weight that stops at 255, and one for a function read later', c, d, main='d')
    e = Obj('e')
    e.wgt((e.f('e.later'), 4, 7))
    e.func('main')
    e.func('later', slots=[(1, 1, 3, 0, 'p')])
    case('a waiting weight for a slot the function lacks', e)

    k1, k2 = Obj('k1'), Obj('k2')
    k1.clas('k', [1, 2])
    k1.func('main')
    k2.clas('k1.k', [1])
    case('a class described with two numbers of parameters', k1, k2)
    m = Obj('m')
    m.clas('k0', [1])
    m.clas('k1', [1])
    m.clas('k2', [2])
    routine(m, 'f', slots=[(1, 1, 0, 0, 'p')])
    routine(m, 'g', slots=[(1, 1, 0, 0, 'p')])
    m.func('main', calls=[(m.f('g'), 0, m.k('k1')), (m.f('f'), 0, m.k('k1')), (m.f('g'), 0, m.k('k0'))])
    m.memb('k1', 'f')
    m.memb('k0', 'f')
    m.memb('k1', 'g')
    case('a function of two classes, the later one first', m)
    n = Obj('n')
    n.clas('k0', [1])
    n.clas('k2', [2])
    routine(n, 'f', slots=[(1, 1, 0, 0, 'p')])
    n.func('main')
    n.memb('k0', 'f')
    n.memb('k2', 'f')
    case('a function of two classes of different parameters', n)
    n = Obj('n')
    n.clas('k0', [1])
    n.clas('k3', [2])
    routine(n, 'f', slots=[(1, 1, 0, 0, 'p')])
    n.func('main')
    n.memb('k3', 'f')
    n.memb('k0', 'f')
    case('a function of two classes of different sizes', n)
    n = Obj('n')
    n.clas('k0', [1])
    n.clas('k4', [1, 1])
    routine(n, 'f', slots=[(1, 1, 0, 0, 'p')])
    n.func('main')
    n.memb('k4', 'f')
    n.memb('k0', 'f')
    case('a function of two classes of different numbers of parameters', n)
    n = Obj('n')
    n.clas('k0', [1])
    routine(n, 'f', slots=[(1, 1, 0, 0, 'p')])
    n.func('main')
    n.memb('k0', 'f')
    n.memb('k0', 'f')
    case('a function of one class twice', n)
    u = Obj('u')
    u.clas('k', [1])
    u.func('main')
    u.memb('k', 'nothing')
    case('a member nothing defines', u)
    u = Obj('u')
    u.func('main')
    u.memb('k', 'main')
    case('a class nothing describes', u)
    return found


def graph_links():
    """Links for what the graph and storage reach that the linker's tests do not: [(title, env,
    objects, main)]."""
    from test_lk_support import (HOST_ENV, Obj, routine, EITHER, NEVER, PARAM, INTERRUPT,
                                 POINTER)
    found = []

    def case(title, env_text, *objects):
        found.append((title, env_text, [o.to_bytes() for o in objects], objects[0].name))

    o = Obj('t')
    c = o.code()
    c.byte(0xA9, 2, o.f('main'))            # LDA #<main, inside main: its address is taken
    c.raw(0x60)
    o.func('main', c)
    case('a function that takes its own address', HOST_ENV, o)

    o = Obj('t')
    o.clas('k', [1])
    routine(o, 'g', slots=[(1, EITHER, 0, PARAM, 'p')])
    routine(o, 'irq', calls=['g'], flags=INTERRUPT)
    routine(o, 'main', calls=[('k', POINTER, None)])
    o.memb('k', 'g')
    case('a member called directly from a context that does not call through its class', HOST_ENV, o)

    o = Obj('t')
    routine(o, 'h')
    routine(o, 'g', slots=[(1, EITHER, 0, PARAM, 'p')])
    routine(o, 'irq', calls=['g'], flags=INTERRUPT)
    routine(o, 'main', calls=[('h', 0, 'g'), 'g'])
    case('a call made while the arguments of a function of two contexts wait', HOST_ENV, o)

    o = Obj('t')
    routine(o, 'g', slots=[(1, EITHER, 0, PARAM, 'p')])
    routine(o, 'dropped', calls=[('nothing', 0, 'g'), 'g'])
    routine(o, 'main', calls=['g'])
    case('a dropped function that calls what nothing defines while arguments wait', HOST_ENV, o)

    o = Obj('t')
    o.var('w', 2, zp_class=NEVER)
    c = o.code()
    c.abs(0xAD, o.v('w'))
    c.raw(0x60)
    o.func('main', c)
    case('a two-byte variable at the end of a page of the more range',
         'cpu 6502\nzeropage $00 $FF\ncode $0200 $BFFF\ndata $C000 $C000\nmore data $F8FF $F9FF\n'
         'exit loop\n', o)

    o = Obj('t')
    o.clas('k', [2])
    routine(o, 'g', slots=[(2, NEVER, 0, PARAM, 'p')])
    routine(o, 'main', calls=[('k', POINTER, None)])
    o.memb('k', 'g')
    case('a two-byte class parameter at the end of a page',
         'cpu 6502\nzeropage $00 $FF\ncode $0200 $BFFF\ndata $C0FF $EFFF\nexit loop\n', o)
    return found


# Programs whose objects are linked by lktest2: (source, environment).
PROGRAMS = [
    ('src/lextest.lth', 'src/compiler.env'),
    ('tests/cases/e2e/fp_dispatch.lth', 'host'),
    ('tests/cases/e2e/fp_callback.lth', 'host'),
    ('tests/cases/e2e/rec_eval.lth', 'host'),
    ('tests/cases/e2e/inits.lth', 'host'),
    ('tests/cases/e2e/sieve.lth', 'host'),
    ('tests/cases/e2e/inline_modules.lth', 'host'),
    ('tests/cases/e2e/modules2.lth', 'host'),
    ('tests/cases/e2e-michael/irq_shared.lth', 'michael'),
    ('tests/cases/e2e-config/farcall.lth', 'tests/cases/e2e-config/farcall_banks.env'),
    ('tests/cases/e2e-config/farcall.lth', 'tests/cases/e2e-config/farcall_ovl.env'),
    ('tests/cases/e2e-config/bankdata.lth', 'tests/cases/e2e-config/bankdata_banks.env'),
    ('tests/cases/e2e-config/inbank.lth', 'tests/cases/e2e-config/inbank.env'),
]

RECORDER = '''import json, os, shutil, sys
d = os.environ['LK_RECORD']
args = sys.argv[1:]
with open(args[0], 'rb') as f:
    files = {'env': f.read().decode('latin-1')}
names = []
for p in args[4:]:
    with open(p, 'rb') as f:
        files[os.path.basename(p)] = f.read().decode('latin-1')
    names.append(os.path.basename(p))
with open(os.path.join(d, 'link.json'), 'w') as f:
    json.dump({'main': args[1], 'objects': names, 'files': files}, f)
os.execv(sys.executable, [sys.executable, os.environ['LK_REAL']] + args)
'''


def program_case(source, env_name, work):
    """Build a program with build.py, keeping what its link was given."""
    import json
    import build
    d = tempfile.mkdtemp(dir=work)
    rec = os.path.join(d, 'recorder.py')
    with open(rec, 'w') as f:
        f.write(RECORDER)
    e = env_name if '/' not in env_name else os.path.join(support.LATHE, env_name)
    environ = dict(os.environ, LK_RECORD=d, LK_REAL=build.LINKER, LATHE_LINKER=rec)
    r = subprocess.run([sys.executable, os.path.join(support.DRIVER, 'build.py'),
                        os.path.join(support.LATHE, source), '-o', os.path.join(d, 'o.bin'), '--env', e],
                       env=environ, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise AssertionError('build of %s failed: %s' % (source, r.stderr.decode()[-500:]))
    with open(os.path.join(d, 'link.json')) as f:
        j = json.load(f)
    files = {name: text.encode('latin-1') for name, text in j['files'].items()}
    return Case('%s %s' % (source, env_name), files,
                ['env', j['main'], 'out.bin', 'out.map'] + j['objects'])


def synthetic_case(per_module):
    """lk_synthetic's program with `per_module` functions in each of its 30 modules (it has 23)."""
    import lk_synthetic
    saved = lk_synthetic.PER_MODULE
    lk_synthetic.PER_MODULE = per_module
    try:
        builders, _ = lk_synthetic.program(1)
    finally:
        lk_synthetic.PER_MODULE = saved
    files = {'e.env': ('cpu 6502\nzeropage $00 $FF\ncode $0200 $BFFF\ndata $C000 $EFFF\nstack $FF\n'
                       'exit call $F00F\n').encode()}
    names = []
    for b in builders:
        name = b.module_.name + '.lo'
        files[name] = b.bytes()
        names.append(name)
    return Case('lk_synthetic with %d functions a module' % per_module, files,
                ['e.env', 'p00', 'out.bin', 'out.map'] + names)


# lk_synthetic's program with 7 functions a module of its 30 has 239 functions, 1,086 slots,
# 1,038 calls, 1,243 symbols in object files and 2,883 bytes of names kept, which the small build
# links; with 8 the names kept and the symbols' words outgrow the work area (link error 10).
SYNTHETIC_FITS = 7
SYNTHETIC_OVER = 8

# Zero page sizes at which lktest4 allocates each program: promotion must choose at the smaller
# ones; each program's edge, where every candidate just fits, and one byte less are added.
ZP_SIZES = (16, 32, 64, 96)
ZP_PROGRAMS = ('src/lextest.lth', 'tests/cases/e2e/rec_eval.lth', 'tests/cases/e2e/fp_dispatch.lth',
               'tests/cases/e2e/fp_callback.lth', 'tests/cases/e2e-michael/irq_shared.lth',
               'tests/cases/e2e-config/bankdata.lth')


def with_zeropage(case, size):
    """The case with `size` bytes of zero page from the start its environment gives."""
    files = dict(case.files)
    name = case.args[0]
    lines = files[name].decode('latin-1').split('\n')
    for i, line in enumerate(lines):
        parts = line.split()
        if parts and parts[0] == 'zeropage':
            lo = int(parts[1].lstrip('$'), 16)
            lines[i] = 'zeropage $%02X $%02X' % (lo, min(0xFF, lo + size - 1))
    files[name] = '\n'.join(lines).encode('latin-1')
    return Case('%s, %d bytes of zero page' % (case.title, size), files, case.args)


def zp_edge(case, work):
    """The zero page every candidate of the case's program needs, or None if they do not all fit
    in 256 bytes: lktest4's twin at the most zero page, where allocate lays out three times."""
    d = tempfile.mkdtemp(dir=work)
    big = with_zeropage(case, 256)
    for name, data in big.files.items():
        with open(os.path.join(d, name), 'wb') as f:
            f.write(data)
    status, out, _ = host_run(lktest4, big.args, d)
    z = out.split(b'\n')[0].split()
    if status != 0 or int(z[4], 16) != 3:
        return None
    return int(z[3], 16)

BAD_ENVS = [
    'cpu 6502\nzeropage $00 $FF\ncode $0200 $BFFF\ndata $C000 $EFFF\n',
    'cpu z80\n',
    'zeropage $00 $1FF\ncode $0200 $BFFF\ndata $C000 $EFFF\nexit loop\n',
    'zeropage $00 $FF\ncode $0200 $BFFF\ndata $C000 $EFFF\nexit loop\ncode $0300 $0400\n',
    'zeropage $00 $FF\ncode $0200 $BFFF\ndata $C000 $EFFF\nexit stop\n',
    'zeropage $00 $FF\ncode $0200 $BFFF\ndata $0200 $EFFF\nexit loop\n',
    'zeropage $00 $FF\ncode $0200 $BFFF\ndata $C000 $EFFF\nexit loop\nwindow W $8000 $9FFF\n',
    'zeropage $00 $FF\ncode $0200 $7FFF\ndata $C000 $EFFF\nexit loop\nwindow W $8000 $9FFF\n'
    'switch W bank $F000 $1F\nbank W 1 $11 B1.BIN\nbank W 2 $12\nplace m W 2\n',
    'zeropage $00 $FF\ncode $0200 $7FFF\ndata $C000 $EFFF\nexit loop\n' + 'window ' + 'w' * 65 + ' $8000 $9FFF\n',
    'zeropage $00 $FF\ncode $0200 $7FFF\ndata $C000 $EFFF\nexit loop\n'
    + ''.join('region r%d fixed\n' % i for i in range(17)),
    'zeropage $00 $FF\ncode $0200 $7FFF\ndata $C000 $EFFF\nexit loop\n'
    + ''.join('window w%d $%X $%X\n' % (i, 0x8000 + i * 0x100, 0x80FF + i * 0x100) for i in range(5)),
    'zeropage $00 $FF\ncode $0200 $7FFF\ndata $C000 $EFFF\nexit loop\n'
    + ''.join('farcall %s\n' % ('x' * 60 + str(i)) for i in range(1))
    + ''.join('region %s fixed\n' % ('y' * 60 + str(i)) for i in range(6)),
    'zeropage $00 $FF\ncode $0200 $7FFF\ndata $C000 $EFFF\nexit loop\nwindow W $8000 $9FFF\n'
    'switch W overlay\noverlay W 2 O2.BIN\n',
    'zeropage $00 $FF\ncode $0200 $7FFF\ndata $C000 $EFFF\nexit loop\nwindow W $8000 $9FFF\n'
    'switch W bank $F000 $1F\nbank W 1 $11 B1.BIN\nplace m W 1\nplace m W 1\n',
    'zeropage $00 $FF\ncode $0200 $7FFF\ndata $C000 $EFFF\nexit loop\nwindow W $8000 $9FFF\n'
    'switch W bank $F000 $1F\nbank W 1 $11 B1.BIN\nplace m W 3\n',
    'zeropage $00 $FF\ncode $0200 $7FFF\ndata $C000 $EFFF\nexit loop\nwindow W $8000 $9FFF\n'
    'switch W bank $F000 $1F\nbank W 1 $11 B1.BIN\nplace m X 1\n',
    'zeropage $00 $FF\ncode $0200 $7FFF\ndata $C000 $EFFF\nexit loop\nmore data $F000 $F7FF\n'
    'more data $F800 $F8FF\n',
    'zeropage $00 $FF\ncode $0200 $7FFF\ndata $C000 $EFFF\nexit call $10000\n',
    'zeropage $00 $FF\ncode $0200 $7FFF\ndata $C000 $EFFF\nexit call $\n',
    'zeropage $00 $FF\ncode $0200 $7FFF\ndata $C000 $EFFF\nexit call 99999\n',
    'zeropage $00 $FF\ncode $0200 $7FFF\ndata $C000 $EFFF\nexit call 65535 1\n',
    'cpu\n',
    'zeropage $00\n',
    'exit\n',
    'zeropage $00 $FF\ncode $0200 $7FFF\ndata $C000 $EFFF\nexit loop\nstack $100\n',
    'zeropage $00 $FF\ncode $0200 $7FFF\ndata $C000 $EFFF\nexit loop\nwindow W $8000 $9FFF\n'
    'switch W bank $F000 $1F\nbank W 1 $11 B1.BIN\n' + ''.join('place m%d W 1\n' % i for i in range(33)),
    'zeropage $00 $FF\ncode $0200 $7FFF\ndata $C000 $EFFF\nexit loop\nwindow W $8000 $9FFF\n'
    'switch W bank farcall $1F\n',
] + [
    # `when NAME ENTRY` and `unless NAME ENTRY`: read, skipped, and their errors.
    'zeropage $00 $FF\ndata $C000 $EFFF\nexit loop\ndefine OFF 0\ndefine On\ndefine TWO $2\n' + lines
    for lines in ('when ON code $0300 $7FFF\nunless on code $0400 $7FFF\n',
                  'unless off code $0300 $7FFF\nWHEN Off code $0400 $7FFF\nwhen off place x W 1\n',
                  'when two code $0500 $7FFF\nwhen off code nonsense\nwhen off when nothing\n',
                  'when on when two unless off code $0700 $7FFF\nwhen on when off code $0400 $7FFF\n',
                  'define two 0\nwhen two code $0400 $7FFF\nunless two code $0900 $7FFF\n',
                  'code $0200 $7FFF\nwhen\n', 'code $0200 $7FFF\nunless OFF\n',
                  'code $0200 $7FFF\nwhen OFF ; exit stop\n', 'code $0200 $7FFF\nunless OFF when\n',
                  'code $0200 $7FFF\ndefine\n', 'code $0200 $7FFF\ndefine X 1 2\n',
                  'code $0200 $7FFF\ndefine X $10000\n', 'code $0200 $7FFF\nwhen THREE stack $FF\n',
                  'code $0200 $7FFF\nwhen three stack $FF\ndefine THREE 1\n',
                  'code $0200 $7FFF\nunless OFF when THREE stack $FF\n',
                  'code $0200 $7FFF\nunless OFF code $0200 $7FFF\n',
                  # Sixteen defines (three above), and a seventeenth.
                  'code $0200 $7FFF\n' + ''.join('define D%d %d\n' % (i, i & 1) for i in range(13))
                  + 'when d12 stack $FF\nwhen d11 stack $FE\nunless d0 more data $F000 $F0FF\n',
                  'code $0200 $7FFF\n' + ''.join('define D%d\n' % i for i in range(14)) + 'when d0 stack $F0\n')
]

BANKS = ('cpu 6502\nzeropage $00 $FF\ncode $0200 $7FFF\ndata $C000 $EFFF\nexit loop\nwindow W $8000 $9FFF\n'
         'switch W bank $F000 $1F\nbank W 1 $11 B1.BIN\nbank W 2 $12 B2.BIN\noutput raw\n')


def env_files():
    """Every environment file of lathe/env/, lathe/src/ and the configuration cases."""
    found = sorted(glob.glob(os.path.join(support.LATHE, 'env', '*.env')))
    found += sorted(glob.glob(os.path.join(support.SRC, '*.env')))
    found += sorted(glob.glob(os.path.join(support.LATHE, 'tests', 'cases', '*', '*.env')))
    texts = []
    for p in found:
        with open(p, 'rb') as f:
            texts.append((os.path.relpath(p, support.LATHE), f.read()))
    return texts


# ---- the tests ---------------------------------------------------------------------------

class LinkerTwins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-src-lk-')
        images = {}

        def make(name):
            where = os.path.join(cls.dir, name)
            os.makedirs(where)
            image = os.path.join(where, name + '.bin')
            import build
            build.build(os.path.join(support.SRC, name + '.lth'), image, env=ENV,
                        keep=os.path.join(where, 'work'))
            images[name] = image
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(make, ('lktest1', 'lktest2', 'lktest3', 'lktest4')))
        cls.lktest1 = images['lktest1']
        cls.lktest2 = images['lktest2']
        cls.lktest3 = images['lktest3']
        cls.lktest4 = images['lktest4']
        cls.links = recorded_links()
        cls.trace = Coverage() if os.environ.get('LATHE_LK_COVERAGE') else None
        if cls.trace:
            cls.trace.start()

    @classmethod
    def tearDownClass(cls):
        if cls.trace:
            cls.trace.stop()
            cls.trace.report()
        lk_small.load(False)
        shutil.rmtree(cls.dir, ignore_errors=True)

    def work(self):
        return tempfile.mkdtemp(dir=self.dir)

    def test_the_small_build_has_the_capacities_of_the_twins(self):
        lk_small.load(True)
        try:
            for module, values in lk_small.capacities().items():
                for name, value in values.items():
                    self.assertEqual(getattr(sys.modules[module], name), value)
            self.assertEqual(lk_tab.MAX_FUNCS, 320)
            self.assertEqual(len(lk_tab.work), lk_tab.WORK_SIZE)
        finally:
            lk_small.load(False)
        self.assertEqual(lk_tab.MAX_FUNCS, 896)

    def test_the_work_columns_of_the_graph_and_storage_do_not_overlap(self):
        for small in (True, False):
            lk_small.load(small)
            n = lk_tab.MAX_NODES
            # The image: the fix-ups held, each copy's address and a slot's name, below the node
            # columns (12 bytes a fix-up: lk_fix).
            self.assertLessEqual(lk_tab.W_SNAME + 128, lk_tab.W_OWN)
            # ... and the names of one file, as many as in the small build, with which the
            # corpus is tested.
            self.assertGreaterEqual(lk_tab.W_OWN - lk_map.W_HELD, 496)
            # The calls' chains while the classes' calls are added (lk_tab.build_chains).
            self.assertLessEqual(lk_tab.W_NEXT + lk_tab.MAX_EDGES, lk_tab.WORK_SIZE)
            # While what is kept is found: reach's stack, a DFIX record's entries, the files to read.
            self.assertLessEqual(lk_graph.NAMED + lk_tab.MAX_FIXES, lk_graph.NOW)
            self.assertLessEqual(lk_graph.LATER + lk_name.MAX_OBJECTS, lk_tab.W_SCC)
            # Tarjan's columns, then the set and the order, below the node columns.
            self.assertLessEqual(lk_graph.LOW + n, lk_tab.W_SCC)
            self.assertEqual(lk_tab.W_ORDER + n, lk_tab.W_OWN)
            # Storage: the layout, the zero page sizes, and promotion's counts, candidates and
            # list in the column of main memory bases, which ends the work area.
            self.assertLessEqual(lk_alloc.LAY_DOWN + n, lk_tab.W_ZSIZE)
            self.assertLessEqual(lk_tab.W_ZSIZE + n, lk_tab.W_SCC)
            self.assertEqual(lk_alloc.WEIGHT_COUNT, lk_tab.W_MBASE)
            self.assertLessEqual(lk_alloc.LIST + 2 * lk_alloc.MAX_TAKEN, lk_tab.WORK_SIZE)
        lk_small.load(False)

    def test_opcodes_numbers_messages_and_arguments(self):
        cases = [Case('tables', {}, ['x.env', 'aon', 'out.bin']),
                 Case('usage', {}, ['x.env', 'au', 'out.bin']),
                 Case('quiet open', {'y': b'y'}, ['x.env', 'qq', 'out.bin', 'out.map', 'y']),
                 Case('missing file', {}, ['x.env', 'qf', 'out.bin', 'out.map', 'nothing/here']),
                 Case('missing environment', {}, ['nothing.env', 'e', 'out.bin'])]
        self.assertEqual(lathe_and_host(self, self.lktest1, lktest1, cases, self.work()), 5)

    def test_every_environment_file(self):
        texts = env_files()
        texts += [('test env %d' % i, e.encode('latin-1')) for i, e in
                  enumerate(sorted(set(link[0] for link in self.links)))]
        texts += [('bad env %d' % i, e.encode('latin-1')) for i, e in enumerate(BAD_ENVS)]
        cases = [Case(title, {'x.env': text}, ['x.env', 'eib', 'out.bin']) for title, text in texts]
        self.assertGreater(lathe_and_host(self, self.lktest1, lktest1, cases, self.work()), 40)

    def test_images_and_bank_files(self):
        cases = [Case('behind', {'x.env': b'zeropage 0 $FF\ncode $1000 $1FFF\ndata $2000 $2FFF\nexit loop\n'},
                      ['x.env', 'es', 'out.bin']),
                 Case('in a directory', {'x.env': BANKS.encode(), 'sub/k': b''}, ['x.env', 'eib', 'sub/out.bin']),
                 Case('no such directory for the image', {'x.env': BANKS.encode()}, ['x.env', 'ei', 'no/out.bin']),
                 Case('no such directory for a bank', {'x.env': BANKS.encode()}, ['x.env', 'eb', 'no/out.bin'])]
        self.assertEqual(lathe_and_host(self, self.lktest1, lktest1, cases, self.work()), 4)

    def test_every_link_of_the_linkers_tests(self):
        cases = [link_case('link %d' % i, e, objects, main, args)
                 for i, (e, objects, main, args) in enumerate(self.links)]
        self.assertGreater(lathe_and_host(self, self.lktest2, lktest2, cases, self.work()), 200)

    def test_links_made_by_hand(self):
        from test_lk_support import HOST_ENV
        cases = [link_case(title, HOST_ENV, objects, main) for title, objects, main in hand_made_links()]
        cases.append(Case('an object file that cannot be opened', {'e.env': HOST_ENV.encode()},
                          ['e.env', 'm', 'out.bin', 'out.map', 'none.lo']))
        self.assertGreater(lathe_and_host(self, self.lktest2, lktest2, cases, self.work()), 30)

    @classmethod
    def programs(cls):
        """The cases of PROGRAMS and of lk_synthetic, built once."""
        if not hasattr(cls, 'program_cases'):
            work = tempfile.mkdtemp(dir=cls.dir)
            with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
                cls.program_cases = list(pool.map(lambda p: program_case(p[0], p[1], work), PROGRAMS))
            cls.program_cases.append(synthetic_case(SYNTHETIC_FITS))
            cls.program_cases.append(synthetic_case(SYNTHETIC_OVER))
        return cls.program_cases

    def test_programs(self):
        cases = self.programs()
        self.assertEqual(lathe_and_host(self, self.lktest2, lktest2, cases, self.work()), len(PROGRAMS) + 2)

    # lktest3 and lktest4: the call graph, the stubs, the start-up code and storage.

    def test_graph_and_storage_of_every_link_of_the_linkers_tests(self):
        cases = [link_case('link %d' % i, e, objects, main, args)
                 for i, (e, objects, main, args) in enumerate(self.links)]
        self.assertGreater(lathe_and_host(self, self.lktest3, lktest3, cases, self.work()), 200)
        self.assertGreater(lathe_and_host(self, self.lktest4, lktest4, cases, self.work()), 200)

    def test_graph_and_storage_of_links_made_by_hand(self):
        from test_lk_support import HOST_ENV
        cases = [link_case(title, HOST_ENV, objects, main) for title, objects, main in hand_made_links()]
        cases += [link_case(title, e, objects, main) for title, e, objects, main in graph_links()]
        self.assertGreater(lathe_and_host(self, self.lktest3, lktest3, cases, self.work()), 35)
        self.assertGreater(lathe_and_host(self, self.lktest4, lktest4, cases, self.work()), 35)

    def test_graph_and_storage_of_programs(self):
        cases = self.programs()
        self.assertEqual(lathe_and_host(self, self.lktest3, lktest3, cases, self.work()), len(PROGRAMS) + 2)
        self.assertEqual(lathe_and_host(self, self.lktest4, lktest4, cases, self.work()), len(PROGRAMS) + 2)

    def test_storage_in_zero_pages_of_several_sizes(self):
        work = self.work()
        chosen = [c for c in self.programs() if c.title.split()[0] in ZP_PROGRAMS]
        chosen.append(self.programs()[-2])
        cases = []
        edges = 0
        for case in chosen:
            sizes = list(ZP_SIZES)
            edge = zp_edge(case, work)
            if edge is not None:
                sizes += [edge, edge - 1]
                edges += 1
            cases += [with_zeropage(case, size) for size in sizes]
        self.assertGreater(edges, 3)
        self.assertEqual(lathe_and_host(self, self.lktest4, lktest4, cases, self.work()), len(cases))


# ---- what the host runs reach ------------------------------------------------------------

class Coverage:
    """The lines of the linker's host modules that run, by sys.settrace."""

    def __init__(self):
        self.files = {os.path.join(lathec_support.HOST, m + '.py'): m for m in lk_small.MODULES}
        self.hit = {m: set() for m in lk_small.MODULES}

    def tracer(self, frame, event, arg):
        m = self.files.get(frame.f_code.co_filename)
        if m is None:
            return None
        if event == 'line' or event == 'call':
            self.hit[m].add(frame.f_lineno)
        return self.tracer

    def start(self):
        sys.settrace(self.tracer)

    def stop(self):
        sys.settrace(None)

    def report(self):
        import ast
        print()
        for path, m in self.files.items():
            with open(path) as f:
                tree = ast.parse(f.read())
            lines = set()
            funcs = []
            for node in tree.body:
                if isinstance(node, ast.FunctionDef):
                    body = [n for n in ast.walk(node) if isinstance(n, ast.stmt) and n is not node
                            and not isinstance(n, ast.Global)
                            and not (isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Constant))]
                    own = set(n.lineno for n in body)
                    lines |= own
                    funcs.append((node.name, own))
            if not lines:
                continue
            reached = lines & self.hit[m]
            missed = [name for name, own in funcs if not (own & self.hit[m])]
            print('%-8s %4d of %4d statement lines (%3d%%); functions not reached: %s'
                  % (m, len(reached), len(lines), 100 * len(reached) // len(lines), ' '.join(missed) or '-'))
            if os.environ.get('LATHE_LK_COVERAGE') == 'lines' and reached:
                print('    lines not reached: %s' % ' '.join(str(n) for n in sorted(lines - reached)))


if __name__ == '__main__':
    unittest.main()
