"""Sema for the Prog8 subset.

Phase 1 jobs:
  * Validate that exactly one `sub main` exists.
  * Resolve dotted call paths (e.g. `txt.print`) against the stdlib
    symbol table; flag unknown calls.
  * Type string literals; their pool labels are assigned later, lazily,
    by codegen (main-first encounter order) so p1 stays byte-identical.
  * Mangle subroutine names to `p8s_<sub>` (Phase 1: no blocks-as-namespaces
    yet, so `p8s_main` is enough).
"""
from __future__ import annotations

from .ast import (
    AddressOf, ArrayLit, Assign, BinOp, Block, BoolLit, Break, Call, Cast,
    Continue,
    Defer, ExprStmt, For, Ident, If, Index, InlineAsm, IntLit, MemAt, Param,
    Program, Repeat, Return, StrLit, StructDecl, Sub, Symbol, TUByteArray,
    TUWordArray, Type, UnaryOp, VarDecl, When, WhenChoice, While, BOOL, BYTE, STR,
    UBYTE, UWORD, VOID, type_from_name,
)


# Single-byte types that share ZP storage and most arithmetic codegen.
_BYTE_TYPES = (UBYTE, BYTE)
_BYTE_TYPE_SET = {UBYTE, BYTE}
from .stdlib_decls import STDLIB_SYMBOLS, get_builtin


class SemaError(Exception):
    pass


# Zero-page reservations:
#   $00..$01  DISPLAY_STRING_PARAM (display_string ABI -- already used by
#             the existing .inc routines, see display_string.inc)
#   $02..$03  COUNTER scratch borrowed by some demos; we leave it alone
#   $04..$1F  spare (room for the existing display_hex_indirect helpers,
#             multi-byte arithmetic temps, etc.)
#   $20..$3F  __p8c_temp0..__p8c_tempN -- compiler-managed scratch
#   $40..$7F  Prog8 user variables (the next 64 bytes)
# The variable allocator starts at $40; codegen reserves three fixed
# scratch bytes at $20/$21/$22 for nested expression temps and loop
# counters.
ZP_VAR_BASE = 0x40
ZP_VAR_TOP = 0xff


class Sema:
    def __init__(self, prog: Program):
        self.prog = prog
        self.globals: dict[str, Symbol] = {}
        self.dotted: dict[tuple[str, ...], Symbol] = {}
        self._next_str_id = 0
        self._zp_next = ZP_VAR_BASE
        # Per-block locals stack -- index 0 is module scope, then per
        # sub. Phase 2 doesn't have nested blocks-as-scopes, so the
        # stack reflects only [module] or [module, sub].
        self._scope_stack: list[dict[str, Symbol]] = []
        # repeat-counter id allocator: each Repeat gets a unique label
        # suffix so nested loops don't collide.
        self._next_repeat_id = 0

    def run(self) -> None:
        # 0. Index struct decls by name and compute field offsets.
        self._structs: dict[str, dict] = {}
        for sd in self.prog.structs:
            offset = 0
            fields: dict[str, tuple] = {}    # name -> (offset, type)
            for ftype, fname in sd.fields:
                t = type_from_name(ftype)
                if t not in (UBYTE, BYTE, UWORD):
                    raise SemaError(
                        f"{sd.loc.file}:{sd.loc.line}:{sd.loc.col}: "
                        f"struct field {fname!r} of unsupported type {ftype!r}"
                    )
                size = 2 if t is UWORD else 1
                fields[fname] = (offset, t)
                offset += size
            self._structs[sd.name] = {"fields": fields, "size": offset}

        # 1. stdlib imports.
        for mod in self.prog.imports:
            if mod not in STDLIB_SYMBOLS:
                raise SemaError(f"unknown import {mod!r}")
            for sym in STDLIB_SYMBOLS[mod]:
                self.dotted[(mod, sym.name)] = sym

        # 2. Module-scope: register sub names + allocate module-var slots.
        seen_main = False
        for s in self.prog.subs:
            s.mangled = f"p8s_{s.name}"
            if s.name in self.globals:
                raise SemaError(f"duplicate sub {s.name!r}")
            ret_t = type_from_name(s.return_type_name)
            if ret_t is None:
                raise SemaError(f"sub {s.name!r}: bad return type "
                                f"{s.return_type_name!r}")
            kind = "asmsub" if s.is_asmsub else "sub"
            asm_target = s.asm_target if s.is_asmsub else None
            self.globals[s.name] = Symbol(
                name=s.name, mangled=s.mangled, type=ret_t, kind=kind,
                asm_target=asm_target,
            )
            if s.is_main:
                seen_main = True
        if not seen_main:
            raise SemaError("program has no `main { ... }` or `sub main()`")

        # Module-level vars (visible to every sub).
        self._scope_stack.append(self.globals)
        # Enum members come in as ubyte consts named `Enum.MEMBER`.
        for ed in self.prog.enums:
            next_val = 0
            for mname, mval in ed.members:
                if mval is not None:
                    next_val = mval
                qname = f"{ed.name}.{mname}"
                if qname in self.globals:
                    raise SemaError(
                        f"{ed.loc.file}:{ed.loc.line}:{ed.loc.col}: "
                        f"duplicate enum member {qname!r}"
                    )
                mangled = f"p8c_{ed.name}_{mname}"
                self.globals[qname] = Symbol(
                    name=qname, mangled=mangled, type=UBYTE, kind="const",
                    const_value=next_val & 0xFF,
                )
                next_val += 1
        for vd in self.prog.module_vars:
            self._declare_var(vd, mangled_prefix="p8v_", scope=self.globals)

        # 3. Per-sub: push a sub-scope, declare params + sub-locals.
        for s in self.prog.subs:
            sub_scope: dict[str, Symbol] = {}
            # asmsubs need their params resolved too -- callers need
            # the mangled-name slots to drop arg values into.
            self._scope_stack.append(sub_scope)
            for p in s.params:
                pt = type_from_name(p.type_name)
                if pt is None or pt not in (UBYTE, UWORD):
                    raise SemaError(
                        f"{p.loc.file}:{p.loc.line}:{p.loc.col}: "
                        f"param type {p.type_name!r} not supported"
                    )
                size = 1 if pt is UBYTE else 2
                mangled = f"p8v_{s.name}_arg_{p.name}"
                if p.reg is not None:
                    # register-ABI param (asmsub): the arg arrives in a CPU
                    # register, so it gets no memory slot and emits no storage.
                    sym = Symbol(name=p.name, mangled=mangled, type=pt,
                                 kind="var", address=None)
                    sub_scope[p.name] = sym
                    p.sym = sym
                    continue
                if self._zp_next + size > ZP_VAR_TOP:
                    sym = Symbol(name=p.name, mangled=mangled, type=pt,
                                 kind="var", address=None)
                else:
                    sym = Symbol(name=p.name, mangled=mangled, type=pt,
                                 kind="var", address=self._zp_next)
                    self._zp_next += size
                sub_scope[p.name] = sym
                p.sym = sym
                self.prog.all_vars.append(sym)
            if s.is_asmsub:
                # No body to walk.
                self._scope_stack.pop()
                continue
            self._current_sub = s
            self._walk_block(s.body, sub_name=s.name)
            self._current_sub = None
            self._scope_stack.pop()

        self._scope_stack.pop()

    # ---- declaration / scope ----

    def _lookup(self, name: str) -> Symbol | None:
        for scope in reversed(self._scope_stack):
            if name in scope:
                return scope[name]
        return None

    def _declare_var(self, vd: VarDecl, mangled_prefix: str,
                     scope: dict[str, Symbol]) -> Symbol:
        if vd.name in scope:
            raise SemaError(
                f"{vd.loc.file}:{vd.loc.line}:{vd.loc.col}: "
                f"variable {vd.name!r} already declared in this scope"
            )
        # struct-typed declaration: type_name is a user-defined struct.
        if vd.type_name in self._structs:
            info = self._structs[vd.type_name]
            mangled = f"p8st_{vd.name}"
            if vd.array_size is not None:
                # Array of structs.
                total = vd.array_size * info["size"]
                if total > 256:
                    raise SemaError(
                        f"{vd.loc.file}:{vd.loc.line}:{vd.loc.col}: "
                        f"struct array too large ({total} bytes; max 256)"
                    )
                sym = Symbol(name=vd.name, mangled=mangled, type=UBYTE,
                             kind="struct_array")
                sym.struct_type = vd.type_name    # type: ignore[attr-defined]
                sym.struct_info = info            # type: ignore[attr-defined]
                sym.struct_size = info["size"]    # type: ignore[attr-defined]
                sym.array_count = vd.array_size   # type: ignore[attr-defined]
                sym.total_bytes = total           # type: ignore[attr-defined]
            else:
                sym = Symbol(name=vd.name, mangled=mangled, type=UBYTE,
                             kind="struct_instance")
                sym.struct_type = vd.type_name    # type: ignore[attr-defined]
                sym.struct_info = info            # type: ignore[attr-defined]
                sym.struct_size = info["size"]    # type: ignore[attr-defined]
            scope[vd.name] = sym
            vd.sym = sym
            self.prog.all_vars.append(sym)
            if vd.init is not None:
                raise SemaError(
                    f"{vd.loc.file}:{vd.loc.line}:{vd.loc.col}: "
                    f"struct initializers not supported yet"
                )
            return sym
        # const form: type_name is "const-<base>". The initializer must
        # be a literal that we resolve here.
        if vd.type_name.startswith("const-"):
            base = vd.type_name[len("const-"):]
            t = type_from_name(base)
            if t not in (UBYTE, UWORD):
                raise SemaError(
                    f"{vd.loc.file}:{vd.loc.line}:{vd.loc.col}: "
                    f"const of type {base!r} not supported"
                )
            if vd.init is None or not isinstance(vd.init, IntLit):
                raise SemaError(
                    f"{vd.loc.file}:{vd.loc.line}:{vd.loc.col}: "
                    f"const must be initialized to an integer literal"
                )
            mangled = f"p8c_{vd.name}"
            sym = Symbol(name=vd.name, mangled=mangled, type=t, kind="const",
                         const_value=vd.init.value)
            scope[vd.name] = sym
            vd.sym = sym
            # No ZP allocation, no .all_vars entry -- it's pure compile-time.
            return sym
        # Array form: `ubyte[N] name` / `uword[N] name`.
        if vd.array_size is not None:
            if vd.type_name not in ("ubyte", "uword"):
                raise SemaError(
                    f"{vd.loc.file}:{vd.loc.line}:{vd.loc.col}: "
                    f"only ubyte/uword arrays supported (got {vd.type_name!r}[])"
                )
            # Arrays are byte-indexed (upstream's model): a uword array stores
            # its halves in two parallel byte arrays and a ubyte array uses
            # `lda label,y`, so the element count must fit a byte. Arenas larger
            # than this live as peek/poke slabs at fixed addresses instead.
            if vd.array_size <= 0 or vd.array_size > 256:
                raise SemaError(
                    f"{vd.loc.file}:{vd.loc.line}:{vd.loc.col}: "
                    f"array size must be 1..256 (got {vd.array_size}); "
                    f"larger arenas must use peek/poke slabs"
                )
            t = (TUWordArray(vd.array_size) if vd.type_name == "uword"
                 else TUByteArray(vd.array_size))
            mangled = f"{mangled_prefix.replace('p8v_', 'p8a_')}{vd.name}"
            sym = Symbol(name=vd.name, mangled=mangled, type=t, kind="array")
            scope[vd.name] = sym
            vd.sym = sym
            self.prog.all_vars.append(sym)
            if vd.init is not None:
                if not isinstance(vd.init, ArrayLit):
                    raise SemaError(
                        f"{vd.loc.file}:{vd.loc.line}:{vd.loc.col}: "
                        f"array initializer must be a list `[...]`"
                    )
                if len(vd.init.elements) != vd.array_size:
                    raise SemaError(
                        f"{vd.loc.file}:{vd.loc.line}:{vd.loc.col}: "
                        f"array has {vd.array_size} elements but initializer "
                        f"has {len(vd.init.elements)}"
                    )
                for el in vd.init.elements:
                    self._walk_expr(el)
                # codegen reads sym.init_lit to emit the .byte/.word values
                # (resolving any string-literal elements to their pool labels).
                sym.init_lit = vd.init           # type: ignore[attr-defined]
            return sym
        t = type_from_name(vd.type_name)
        if t is None or t not in (UBYTE, BYTE, UWORD):
            raise SemaError(
                f"{vd.loc.file}:{vd.loc.line}:{vd.loc.col}: "
                f"type {vd.type_name!r} not supported yet "
                f"(have ubyte | byte | uword)"
            )
        size = 2 if t is UWORD else 1
        mangled = f"{mangled_prefix}{vd.name}"
        if self._zp_next + size > ZP_VAR_TOP:
            # ZP is full: overflow this scalar into main memory as a
            # labeled byte/word reservation (address=None marks it). The
            # ZP allocator is a global bump allocator (never reset across
            # subs, for non-reentrancy safety), so a big program exhausts
            # the 192-byte ZP window; codegen references a memvar by its
            # label (absolute addressing) -- `lda <mangled>` works for
            # both. Programs that fit in ZP are unaffected.
            sym = Symbol(name=vd.name, mangled=mangled, type=t, kind="var",
                         address=None)
        else:
            sym = Symbol(name=vd.name, mangled=mangled, type=t, kind="var",
                         address=self._zp_next)
            self._zp_next += size
        scope[vd.name] = sym
        vd.sym = sym
        self.prog.all_vars.append(sym)
        if vd.init is not None:
            self._walk_expr(vd.init)
            if t in _BYTE_TYPES and vd.init.type not in _BYTE_TYPES:
                raise SemaError(
                    f"{vd.loc.file}:{vd.loc.line}:{vd.loc.col}: "
                    f"initializer type mismatch for {vd.type_name} {vd.name!r}"
                )
            if (t is UWORD and vd.init.type not in _BYTE_TYPES
                    and vd.init.type is not UWORD and vd.init.type is not STR):
                # A string literal coerces to uword (its pool address).
                raise SemaError(
                    f"{vd.loc.file}:{vd.loc.line}:{vd.loc.col}: "
                    f"initializer type mismatch for uword {vd.name!r}"
                )
        return sym

    # ---- statement / expression walks ----

    def _walk_block(self, blk: Block, sub_name: str) -> None:
        for st in blk.stmts:
            self._walk_stmt(st, sub_name=sub_name)

    def _walk_stmt(self, st, sub_name: str) -> None:
        if isinstance(st, ExprStmt):
            self._walk_expr(st.expr)
            return
        if isinstance(st, InlineAsm):
            return
        if isinstance(st, VarDecl):
            self._declare_var(st, mangled_prefix=f"p8v_{sub_name}_",
                              scope=self._scope_stack[-1])
            return
        if isinstance(st, Assign):
            if isinstance(st.target, MemAt):
                self._walk_expr(st.target)
                self._walk_expr(st.rhs)
                if st.rhs.type is not UBYTE:
                    raise SemaError(
                        f"{st.loc.file}:{st.loc.line}:{st.loc.col}: "
                        f"@(addr) write rhs must be ubyte (got {st.rhs.type!r})"
                    )
                if st.op != "=":
                    raise SemaError(
                        f"{st.loc.file}:{st.loc.line}:{st.loc.col}: "
                        f"augmented @(addr) writes not supported"
                    )
                return
            if isinstance(st.target, Index):
                self._walk_expr(st.target)
                self._walk_expr(st.rhs)
                tgt_t = st.target.type
                if tgt_t is UBYTE and st.rhs.type not in (UBYTE, BYTE):
                    raise SemaError(
                        f"{st.loc.file}:{st.loc.line}:{st.loc.col}: "
                        f"array element assign rhs must be ubyte (got {st.rhs.type!r})"
                    )
                if tgt_t is UWORD and st.rhs.type not in (UBYTE, UWORD, BYTE):
                    raise SemaError(
                        f"{st.loc.file}:{st.loc.line}:{st.loc.col}: "
                        f"array element assign rhs must be uword (got {st.rhs.type!r})"
                    )
                if st.op != "=":
                    raise SemaError(
                        f"{st.loc.file}:{st.loc.line}:{st.loc.col}: "
                        f"augmented assignment on arr[i] not supported yet"
                    )
                return
            assert isinstance(st.target, Ident)
            self._walk_expr(st.target)
            self._walk_expr(st.rhs)
            if st.target.sym is None or st.target.sym.kind not in ("var", "struct_instance"):
                raise SemaError(
                    f"{st.loc.file}:{st.loc.line}:{st.loc.col}: "
                    f"assignment target must be a variable or struct field"
                )
            tgt_t = st.target.type
            rhs_t = st.rhs.type
            if tgt_t in _BYTE_TYPES and rhs_t not in _BYTE_TYPES and rhs_t is not BOOL:
                raise SemaError(
                    f"{st.loc.file}:{st.loc.line}:{st.loc.col}: "
                    f"RHS type {rhs_t!r} not assignable to {tgt_t!r}"
                )
            if (tgt_t is UWORD and rhs_t not in _BYTE_TYPES
                    and rhs_t is not UWORD and rhs_t is not STR):
                # A string literal coerces to uword (its pool address).
                raise SemaError(
                    f"{st.loc.file}:{st.loc.line}:{st.loc.col}: "
                    f"RHS type {rhs_t!r} not assignable to uword"
                )
            return
        if isinstance(st, If):
            self._walk_expr(st.cond)
            if st.cond.type is not BOOL:
                raise SemaError(
                    f"{st.loc.file}:{st.loc.line}:{st.loc.col}: "
                    f"if condition must be a boolean (got {st.cond.type!r}); "
                    f"integer/truthy conditions are not upstream Prog8 -- "
                    f"write an explicit comparison such as `!= 0`"
                )
            self._walk_block(st.then_block, sub_name=sub_name)
            if st.else_block is not None:
                self._walk_block(st.else_block, sub_name=sub_name)
            return
        if isinstance(st, When):
            self._walk_expr(st.expr)
            if st.expr.type not in (UBYTE, UWORD):
                raise SemaError(
                    f"{st.loc.file}:{st.loc.line}:{st.loc.col}: "
                    f"when expression must be ubyte/uword (got {st.expr.type!r})"
                )
            for ch in st.choices:
                for v in ch.values:
                    self._walk_expr(v)
                self._walk_block(ch.body, sub_name=sub_name)
            return
        if isinstance(st, While):
            self._walk_expr(st.cond)
            if st.cond.type is not BOOL:
                raise SemaError(
                    f"{st.loc.file}:{st.loc.line}:{st.loc.col}: "
                    f"while condition must be a boolean (got {st.cond.type!r}); "
                    f"integer/truthy conditions are not upstream Prog8 -- "
                    f"write an explicit comparison such as `!= 0`"
                )
            self._walk_block(st.body, sub_name=sub_name)
            return
        if isinstance(st, Repeat):
            if st.count is not None:
                self._walk_expr(st.count)
                if st.count.type is not UBYTE:
                    raise SemaError(
                        f"{st.loc.file}:{st.loc.line}:{st.loc.col}: "
                        f"repeat count must be a ubyte expression"
                    )
            self._walk_block(st.body, sub_name=sub_name)
            # Assign a unique id so codegen can label this loop's branch
            # targets without collisions across nested repeats.
            st_id = self._next_repeat_id
            self._next_repeat_id += 1
            st.id = st_id  # type: ignore[attr-defined]
            return
        if isinstance(st, For):
            # The loop variable must be declared in scope (Phase 2; the
            # `for ubyte i in ...` shorthand comes later).
            sym = self._lookup(st.var_name)
            if sym is None:
                raise SemaError(
                    f"{st.loc.file}:{st.loc.line}:{st.loc.col}: "
                    f"for-loop variable {st.var_name!r} must be declared "
                    f"before the loop"
                )
            if sym.kind != "var" or sym.type is not UBYTE:
                raise SemaError(
                    f"{st.loc.file}:{st.loc.line}:{st.loc.col}: "
                    f"for-loop variable {st.var_name!r} must be a ubyte var"
                )
            st.sym = sym
            self._walk_expr(st.lo)
            self._walk_expr(st.hi)
            if st.lo.type is not UBYTE or st.hi.type is not UBYTE:
                raise SemaError(
                    f"{st.loc.file}:{st.loc.line}:{st.loc.col}: "
                    f"for-loop range must be ubyte"
                )
            self._walk_block(st.body, sub_name=sub_name)
            return
        if isinstance(st, (Break, Continue)):
            # Validity (must be inside a loop) checked at codegen time.
            return
        if isinstance(st, Defer):
            self._walk_stmt(st.stmt, sub_name=sub_name)
            return
        if isinstance(st, Return):
            cur = getattr(self, "_current_sub", None)
            assert cur is not None
            ret_t = type_from_name(cur.return_type_name)
            if ret_t is VOID:
                if st.value is not None:
                    raise SemaError(
                        f"{st.loc.file}:{st.loc.line}:{st.loc.col}: "
                        f"sub {cur.name!r} returns void; can't return a value"
                    )
                return
            if st.value is None:
                raise SemaError(
                    f"{st.loc.file}:{st.loc.line}:{st.loc.col}: "
                    f"sub {cur.name!r} declares -> {cur.return_type_name}; "
                    f"must return a value"
                )
            self._walk_expr(st.value)
            vt = st.value.type
            if ret_t is UBYTE and vt is not UBYTE:
                raise SemaError(
                    f"{st.loc.file}:{st.loc.line}:{st.loc.col}: "
                    f"return type mismatch: want ubyte, got {vt!r}"
                )
            if ret_t is UWORD and vt not in (UBYTE, UWORD):
                raise SemaError(
                    f"{st.loc.file}:{st.loc.line}:{st.loc.col}: "
                    f"return type mismatch: want uword, got {vt!r}"
                )
            return
        raise SemaError(f"sema: unhandled statement {type(st).__name__}")

    def _walk_expr(self, e) -> None:
        if isinstance(e, IntLit):
            e.type = UBYTE if 0 <= e.value <= 0xFF else UWORD
        elif isinstance(e, BoolLit):
            e.type = BOOL
        elif isinstance(e, StrLit):
            # String labels are assigned lazily in codegen, on first
            # reference, in main-first emission order -- so that p1 (which
            # interns string labels during its single codegen pass, main
            # first) produces byte-identical label numbering. Here we only
            # fix the type; codegen owns Program.strings + e.label.
            e.label = None
            e.type = STR
        elif isinstance(e, Ident):
            sym = self._lookup(e.name)
            if sym is None and "." in e.name:
                # Maybe `instance.field` -- look up the instance and
                # resolve the field offset.
                head, _, tail = e.name.partition(".")
                inst = self._lookup(head)
                if inst is not None and inst.kind == "struct_instance":
                    info = inst.struct_info       # type: ignore[attr-defined]
                    if tail not in info["fields"]:
                        raise SemaError(
                            f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                            f"struct {inst.struct_type!r} has no field {tail!r}"
                        )
                    offset, ft = info["fields"][tail]
                    # Synthesize a "field" symbol: the instance label
                    # plus an offset is its address; codegen reads it.
                    e.sym = inst
                    e.field_offset = offset       # type: ignore[attr-defined]
                    e.type = ft
                    return
            if sym is None:
                raise SemaError(
                    f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                    f"unknown identifier {e.name!r}"
                )
            e.sym = sym
            e.type = sym.type
        elif isinstance(e, MemAt):
            self._walk_expr(e.addr)
            if e.addr.type not in (UBYTE, UWORD):
                raise SemaError(
                    f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                    f"@(addr) address must be uword (got {e.addr.type!r})"
                )
            e.type = UBYTE
        elif isinstance(e, AddressOf):
            sym = self._lookup(e.name)
            if sym is None:
                raise SemaError(
                    f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                    f"unknown identifier &{e.name}"
                )
            if sym.kind not in ("var", "array"):
                raise SemaError(
                    f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                    f"can't take address of {sym.kind} {e.name!r}"
                )
            e.sym = sym
            e.type = UWORD
        elif isinstance(e, Index):
            if not isinstance(e.array, Ident):
                raise SemaError(
                    f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                    f"only `name[idx]` array indexing supported"
                )
            self._walk_expr(e.array)
            asym = e.array.sym
            if asym is None or asym.kind not in ("array", "struct_array"):
                raise SemaError(
                    f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                    f"{e.array.name!r} is not an array"
                )
            e.sym = asym
            self._walk_expr(e.index)
            if e.index.type not in (UBYTE, BYTE, UWORD):
                raise SemaError(
                    f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                    f"array index must be byte/ubyte/uword (got {e.index.type!r})"
                )
            if asym.kind == "struct_array":
                if e.field is None:
                    raise SemaError(
                        f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                        f"struct-array element access needs a .field"
                    )
                info = asym.struct_info       # type: ignore[attr-defined]
                if e.field not in info["fields"]:
                    raise SemaError(
                        f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                        f"struct has no field {e.field!r}"
                    )
                e.field_offset, e.type = info["fields"][e.field]   # type: ignore[attr-defined]
            else:
                if e.field is not None:
                    raise SemaError(
                        f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                        f"{e.array.name!r} is not a struct array"
                    )
                e.type = UWORD if isinstance(asym.type, TUWordArray) else UBYTE
        elif isinstance(e, Call):
            key = tuple(e.path)
            sym = self.dotted.get(key)
            if sym is None and len(e.path) == 1:
                sym = self.globals.get(e.path[0])
            if sym is None and len(e.path) == 1:
                sym = get_builtin(e.path[0])
            if sym is None:
                raise SemaError(
                    f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                    f"unknown call target {'.'.join(e.path)!r}"
                )
            if sym.kind not in ("sub", "asmsub", "extsub", "builtin"):
                raise SemaError(
                    f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                    f"{'.'.join(e.path)!r} is not callable"
                )
            e.sym = sym
            e.type = sym.type
            for a in e.args:
                self._walk_expr(a)
            # For user-defined subs / asmsubs we can type-check arg count
            # + arg types against the declared params.
            if sym.kind in ("sub", "asmsub") and len(e.path) == 1:
                target = next((s for s in self.prog.subs if s.name == sym.name), None)
                if target is not None:
                    if len(e.args) != len(target.params):
                        raise SemaError(
                            f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                            f"{sym.name!r} takes {len(target.params)} args, "
                            f"got {len(e.args)}"
                        )
                    for arg, p in zip(e.args, target.params):
                        pt = type_from_name(p.type_name)
                        if pt is UBYTE and arg.type is not UBYTE:
                            raise SemaError(
                                f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                                f"arg {p.name!r} wants ubyte, got {arg.type!r}"
                            )
                        if pt is UWORD and arg.type not in (UBYTE, UWORD, STR):
                            # A string literal coerces to uword (its address).
                            raise SemaError(
                                f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                                f"arg {p.name!r} wants uword, got {arg.type!r}"
                            )
        elif isinstance(e, BinOp):
            self._walk_expr(e.lhs)
            self._walk_expr(e.rhs)
            cmp_ops = {"==", "!=", "<", "<=", ">", ">="}
            logical_ops = {"and", "or", "xor"}
            if e.op in cmp_ops:
                ok = ({e.lhs.type, e.rhs.type} <= {UBYTE, BYTE, UWORD})
                if not ok:
                    raise SemaError(
                        f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                        f"comparison operands must both be byte/ubyte/uword"
                    )
                # If both operands are signed bytes, the comparison is
                # signed; sema marks the BinOp with a hint so codegen
                # can pick the right branch sequence.
                if e.lhs.type is BYTE and e.rhs.type is BYTE:
                    e.signed = True   # type: ignore[attr-defined]
                e.type = BOOL
            elif e.op in logical_ops:
                if e.lhs.type is not BOOL or e.rhs.type is not BOOL:
                    raise SemaError(
                        f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                        f"logical operands must both be bool"
                    )
                e.type = BOOL
            else:
                # Arithmetic / bitwise / shift.
                # Result is signed byte if both operands are byte;
                # otherwise unsigned. ubyte widens to uword.
                lt, rt = e.lhs.type, e.rhs.type
                if {lt, rt} == {BYTE}:
                    e.type = BYTE
                elif {lt, rt} <= _BYTE_TYPE_SET:
                    e.type = UBYTE
                elif {lt, rt} <= _BYTE_TYPE_SET | {UWORD}:
                    e.type = UWORD
                else:
                    raise SemaError(
                        f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                        f"binary op {e.op!r} needs byte/ubyte/uword operands "
                        f"(got {lt!r} and {rt!r})"
                    )
        elif isinstance(e, Cast):
            self._walk_expr(e.operand)
            t = type_from_name(e.type_name)
            if t not in (UBYTE, BYTE, UWORD):
                raise SemaError(
                    f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                    f"cannot cast to {e.type_name!r}"
                )
            if e.operand.type not in (UBYTE, BYTE, UWORD):
                raise SemaError(
                    f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                    f"cannot cast {e.operand.type!r} to {e.type_name!r}"
                )
            e.type = t
        elif isinstance(e, UnaryOp):
            self._walk_expr(e.operand)
            if e.op == "not":
                if e.operand.type is not BOOL:
                    raise SemaError(
                        f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                        f"`not` operand must be bool"
                    )
                e.type = BOOL
            elif e.op in ("~", "-"):
                if e.operand.type not in _BYTE_TYPES:
                    raise SemaError(
                        f"{e.loc.file}:{e.loc.line}:{e.loc.col}: "
                        f"unary {e.op!r} operand must be byte/ubyte"
                    )
                # `- ubyte` -> signed byte; `- byte` stays byte;
                # `~ x` keeps operand signedness.
                if e.op == "-":
                    e.type = BYTE
                else:
                    e.type = e.operand.type
            else:
                raise SemaError(f"unknown unary {e.op!r}")
        else:
            raise SemaError(f"sema: unhandled expr {type(e).__name__}")


def analyze(prog: Program) -> None:
    Sema(prog).run()
