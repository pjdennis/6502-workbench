"""Recursive-descent parser for the Prog8 subset.

Phase 1 grammar (informal):
    program     := { directive | sub }*
    directive   := DIRECTIVE [value]
                 ; %address $XXXX, %output raw, %import name, %option ...
    sub         := 'sub' IDENT '(' ')' '->' typename block
                 | 'sub' IDENT '(' ')' block               ; void return
    typename    := 'ubyte' | 'uword' | 'bool' | 'str' | 'void'
    block       := '{' { stmt }* '}'
    stmt        := callstmt | inline_asm
    callstmt    := dotted_ident '(' arglist ')'
    dotted_ident:= IDENT { '.' IDENT }*
    arglist     := [ expr { ',' expr } ]
    expr        := strlit | intlit | bool_lit | dotted_ident_or_call
    inline_asm  := %asm '{{' ... '}}'

That's it for now -- enough for `sub main() { txt.print("hi") }`.
"""
from __future__ import annotations

from typing import Optional

from .ast import (
    AddressOf, ArrayLit, Assign, BinOp, Block, BoolLit, Break, Call, Continue,
    Defer, EnumDecl, ExprStmt, For, Ident, If, Index, InlineAsm, IntLit, Loc,
    MemAt, Node, Param, Program, Repeat, Return, StrLit, StructDecl, Sub,
    UnaryOp, VarDecl, When, WhenChoice, While, type_from_name,
)


# Keywords that introduce a statement we know how to parse.
_STMT_KW = {"if", "while", "when", "repeat", "for", "break", "continue",
            "return", "defer"}
from .lex import Token


# Type keywords accepted by VarDecl in Phase 2.
_TYPE_KWS = {"ubyte", "byte", "uword"}

# Binary-op precedence ladder, lowest precedence first. Each entry is
# (precedence-name, set-of-tokens-at-this-level). Higher index = higher
# precedence -- so we climb from the bottom of this list when parsing.
_OP_LEVELS = [
    ("logical_or",  {"or", "xor"}),
    ("logical_and", {"and"}),
    ("equality",    {"==", "!="}),
    ("comparison",  {"<", "<=", ">", ">="}),
    ("bitor",       {"|"}),
    ("bitxor",      {"^"}),
    ("bitand",      {"&"}),
    ("shift",       {"<<", ">>"}),
    ("additive",    {"+", "-"}),
    ("multiplicative", {"*"}),
]
# Build (token_kind -> level_index) for O(1) lookups.
_OP_PRECEDENCE: dict[str, int] = {}
for _idx, (_name, _tokens) in enumerate(_OP_LEVELS):
    for _t in _tokens:
        _OP_PRECEDENCE[_t] = _idx

_AUG_OPS = {"+=", "-=", "&=", "|=", "^=", "<<=", ">>="}


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens: list[Token], filename: str,
                 iter_expr: bool = True, iter_stmt: bool = True):
        self.toks = tokens
        self.pos = 0
        self.filename = filename
        # The iterative (non-recursive) parser is now the DEFAULT path:
        # expression parsing goes through iter_parse.IterParser and block
        # parsing through parse_block_iter. The recursive-descent code
        # below is retained as the equivalence oracle that
        # tests/test_iter_parse.py checks the iterative parser against
        # (and as the reference for the eventual Prog8 port); pass
        # iter_expr=False / iter_stmt=False to select it.
        #
        # iter_stmt implies iter_expr, so a fully-recursive parse needs
        # both flags off.
        self.iter_stmt = iter_stmt
        self.iter_expr = iter_expr or iter_stmt

    # ---- token helpers ----

    def peek(self, ahead: int = 0) -> Token:
        return self.toks[self.pos + ahead]

    def eat(self, kind: str, value=None) -> Token:
        t = self.peek()
        if t.kind != kind or (value is not None and t.value != value):
            raise ParseError(
                f"{self.filename}:{t.line}:{t.col}: expected {kind}"
                f"{' ' + repr(value) if value is not None else ''}, got "
                f"{t.kind} {t.value!r}"
            )
        self.pos += 1
        return t

    def match(self, kind: str, value=None) -> Optional[Token]:
        t = self.peek()
        if t.kind == kind and (value is None or t.value == value):
            self.pos += 1
            return t
        return None

    def loc(self, t: Token) -> Loc:
        return Loc(self.filename, t.line, t.col)

    # ---- top-level ----

    def parse_program(self) -> Program:
        prog = Program(loc=self.loc(self.peek()))
        while self.peek().kind != "EOF":
            t = self.peek()
            if t.kind == "DIRECTIVE":
                self.parse_directive(prog)
            elif t.kind == "KW" and t.value == "main":
                # `main { ... }` is the upstream namespace form: a block of
                # DECLARATIONS (subs, vars, consts) containing a `sub start()`
                # entry. `main` is just a namespace; its members flatten into
                # the program and `start` becomes the entry sub. The lenient
                # entry-body form (`main { <statements> }`) is NOT upstream
                # Prog8 and is no longer accepted -- write `main { sub start() {
                # ... } }`.
                self.pos += 1                       # consume 'main'
                self._parse_main_namespace(prog)
            else:
                # Strict upstream Prog8: the top level holds only directives
                # and named blocks (`main { ... }`). Bare declarations outside
                # a block were a lenient p8c extension and are no longer
                # accepted -- wrap them in `main { ... }`.
                raise ParseError(
                    f"{self.filename}:{t.line}:{t.col}: top-level declarations "
                    f"outside a block are not upstream Prog8; put them inside "
                    f"`main {{ ... }}` (got {t.kind} {t.value!r})")
        return prog

    def _parse_toplevel_decl(self, prog: Program) -> None:
        """Parse one top-level declaration (sub / asmsub / const / enum / struct
        / var / struct-instance) and append it to `prog`. Shared by the program
        loop and the `main { ... }` namespace body."""
        t = self.peek()
        if t.kind == "KW" and t.value == "sub":
            prog.subs.append(self.parse_sub())
        elif t.kind == "KW" and t.value == "inline":
            # `inline sub ...` -- inlined at every call site.
            self.pos += 1
            self.eat("KW", "sub")
            s = self.parse_sub_body_after_kw()
            s.is_inline = True
            prog.subs.append(s)
        elif t.kind == "KW" and t.value == "asmsub":
            prog.subs.append(self.parse_asmsub())
        elif t.kind == "KW" and t.value == "extsub":
            prog.subs.append(self.parse_extsub())
        elif t.kind == "KW" and t.value == "const":
            prog.module_vars.append(self.parse_const_decl())
        elif t.kind == "KW" and t.value == "enum":
            prog.enums.append(self.parse_enum_decl())
        elif t.kind == "KW" and t.value == "struct":
            prog.structs.append(self.parse_struct_decl())
        elif t.kind == "KW" and t.value in _TYPE_KWS:
            # Module-level variable declaration.
            prog.module_vars.append(self.parse_var_decl())
        elif (t.kind == "IDENT"
              and any(s.name == t.value for s in prog.structs)):
            # `StructName instance` OR `StructName[N] arr_name`.
            self.pos += 1
            array_size = None
            if self.match("["):
                sz = self.eat("INT")
                self.eat("]")
                array_size = sz.value
            name_tok = self.eat("IDENT")
            vd = VarDecl(loc=self.loc(t), type_name=t.value,
                         name=name_tok.value, array_size=array_size)
            prog.module_vars.append(vd)
        else:
            raise ParseError(
                f"{self.filename}:{t.line}:{t.col}: expected sub, directive, "
                f"or variable declaration, got {t.kind} {t.value!r}"
            )

    def _parse_main_namespace(self, prog: Program) -> None:
        """Parse `main { <decls incl. `sub start()`> }`: flatten the members
        into `prog` and mark `start` as the entry (`is_main`)."""
        self.eat("{")
        while self.peek().kind != "}":
            self._parse_toplevel_decl(prog)
        self.eat("}")
        start = next((s for s in prog.subs if s.name == "start"), None)
        if start is None:
            raise ParseError(
                f"{self.filename}: `main` block has no `sub start()` entry "
                f"(the lenient `main {{ <statements> }}` form is not upstream "
                f"Prog8; wrap the body in `sub start() {{ ... }}`)")
        start.is_main = True

    def parse_directive(self, prog: Program) -> None:
        t = self.eat("DIRECTIVE")
        name = t.value
        if name == "address":
            v = self.eat("INT")
            prog.address = v.value
        elif name == "output":
            v = self.eat("IDENT")
            prog.output_format = v.value
        elif name == "launcher":
            # `%launcher none` -- upstream directive; p8c emits no launcher, so
            # accept and ignore it (keeps the converged source one-dialect).
            self.eat("IDENT")
        elif name == "memtop":
            # `%memtop $XXXX` -- upstream allocator ceiling, so its code/data/BSS
            # stays below the baked peek/poke slab region. p8c lays storage out
            # explicitly (it never allocates over the slabs), so accept + ignore.
            self.eat("INT")
        elif name == "import":
            v = self.eat("IDENT")
            prog.imports.append(v.value)
        elif name == "option":
            # bare list of options; we accept and ignore for now.
            while self.peek().kind == "IDENT":
                self.pos += 1
                if self.match(",") is None:
                    break
        else:
            raise ParseError(
                f"{self.filename}:{t.line}:{t.col}: unknown directive %{name}"
            )

    def parse_sub(self) -> Sub:
        self.eat("KW", "sub")
        return self.parse_sub_body_after_kw()

    def parse_sub_body_after_kw(self) -> Sub:
        """Parse a sub's `name(...) -> rt { body }` after the leading
        `sub` / `inline sub` keywords have already been consumed."""
        name_tok = self.eat("IDENT")
        self.eat("(")
        params: list[Param] = []
        if self.peek().kind != ")":
            params.append(self._parse_param())
            while self.match(","):
                params.append(self._parse_param())
        self.eat(")")
        ret = "void"
        if self.match("->"):
            t = self.eat("KW")
            ret = t.value
        body = self.parse_block()
        return Sub(loc=self.loc(name_tok), name=name_tok.value, body=body,
                   params=params, return_type_name=ret,
                   is_main=(name_tok.value == "main"))

    def _parse_param(self) -> Param:
        t = self.eat("KW")
        if t.value not in _TYPE_KWS:
            raise ParseError(
                f"{self.filename}:{t.line}:{t.col}: expected type in param list"
            )
        n = self.eat("IDENT")
        reg = self._parse_reg_annotation()
        return Param(loc=self.loc(t), type_name=t.value, name=n.value, reg=reg)

    def _parse_reg_annotation(self) -> Optional[str]:
        """Optional `@A` / `@X` / `@Y` / `@AY` register-ABI annotation."""
        if self.peek().kind != "@":
            return None
        self.eat("@")
        r = self.eat("IDENT")
        if r.value not in ("A", "X", "Y", "AY"):
            raise ParseError(
                f"{self.filename}:{r.line}:{r.col}: "
                f"bad register {r.value!r} (expected A, X, Y, or AY)")
        return r.value

    def parse_asmsub(self) -> Sub:
        """`asmsub name(params @REG) -> rt @REG { %asm {{ ... }} }` -- the
        register-ABI inline-body form: args arrive in the named registers, the
        body is emitted under the sub label, no static-param prologue. (An
        address-only external sub is declared with `extsub $ADDR = name(...)`;
        the retired `asmsub name(...) = $ADDR` form is no longer accepted.)
        """
        kw = self.eat("KW", "asmsub")
        name_tok = self.eat("IDENT")
        params = self._parse_param_list()
        ret = "void"
        ret_reg = None
        if self.match("->"):
            ret = self.eat("KW").value
            ret_reg = self._parse_reg_annotation()
        if self.peek().kind == "=":
            raise ParseError(
                f"{self.filename}:{kw.line}:{kw.col}: the `asmsub {name_tok.value}"
                f"(...) = $ADDR` form is retired; use `extsub $ADDR = "
                f"{name_tok.value}(...)`")
        body = self.parse_block()
        return Sub(loc=self.loc(kw), name=name_tok.value, body=body,
                   params=params, return_type_name=ret, ret_reg=ret_reg,
                   is_asmsub=True)

    def parse_extsub(self) -> Sub:
        """`extsub $ADDR = name(params @REG) -> rt @REG` -- upstream's
        address-first external-sub declaration; calling `name(...)` JSRs
        $ADDR with args in the annotated registers. Equivalent to the
        `asmsub name(...) = $ADDR` form."""
        kw = self.eat("KW", "extsub")
        addr_tok = self.eat("INT")
        self.eat("=")
        name_tok = self.eat("IDENT")
        params = self._parse_param_list()
        ret = "void"
        ret_reg = None
        if self.match("->"):
            ret = self.eat("KW").value
            ret_reg = self._parse_reg_annotation()
        return Sub(loc=self.loc(kw), name=name_tok.value,
                   body=Block(loc=self.loc(kw), stmts=[]),
                   params=params, return_type_name=ret, ret_reg=ret_reg,
                   is_asmsub=True, asm_target=f"${addr_tok.value:04x}")

    def _parse_param_list(self) -> list[Param]:
        self.eat("(")
        params: list[Param] = []
        if self.peek().kind != ")":
            params.append(self._parse_param())
            while self.match(","):
                params.append(self._parse_param())
        self.eat(")")
        return params

    def parse_block(self) -> Block:
        if self.iter_stmt:
            return self.parse_block_iter()
        ob = self.eat("{")
        stmts: list[Node] = []
        while self.peek().kind != "}":
            stmts.append(self.parse_stmt())
        self.eat("}")
        return Block(loc=self.loc(ob), stmts=stmts)

    # ---- iterative (non-recursive) block / statement parsing ----
    #
    # The recursive `parse_block` / `parse_stmt` / parse_if|while|... chain
    # nests via Python's call stack, which can't be ported to Prog8. This
    # driver replaces that nesting with an explicit stack of block frames.
    # Leaf statements (var decls, assignments, calls, break/continue/return,
    # inline asm) are still parsed by the existing helpers -- they don't
    # recurse into blocks, and their sub-expressions go through the
    # iterative expression parser (iter_stmt implies iter_expr). Only the
    # block-nesting dimension becomes a loop here.
    #
    # Each frame is a dict:
    #   kind:   'root'|'then'|'else'|'while'|'for'|'repeat'|'when'|'when_choice'
    #   mode:   'stmts' (a normal block) or 'choices' (a `when` body)
    #   stmts:  accumulated statements (stmts-mode)
    #   ob_loc: Loc of the opening '{' (for the Block node)
    #   defer:  Loc if this statement was prefixed with `defer`, else None
    #   plus per-kind header data (cond / count / var,lo,hi / expr / etc.)
    def parse_block_iter(self) -> Block:
        ob = self.eat("{")
        frames: list[dict] = [
            {"kind": "root", "mode": "stmts", "stmts": [],
             "ob_loc": self.loc(ob), "defer": None}
        ]
        result: Optional[Block] = None
        pending_defer: Optional[Loc] = None

        def attach(node: Node) -> None:
            # Append a freshly built statement to the current block frame.
            frames[-1]["stmts"].append(node)

        while frames:
            fr = frames[-1]

            # `when` body: a sequence of choices, not statements.
            if fr["mode"] == "choices":
                t = self.peek()
                if t.kind == "}":
                    self.eat("}")
                    node: Node = When(loc=fr["loc"], expr=fr["expr"],
                                      choices=fr["choices"])
                    if fr["defer"] is not None:
                        node = Defer(loc=fr["defer"], stmt=node)
                    frames.pop()
                    if not frames:
                        result = node  # unreachable: when is never the root
                    else:
                        attach(node)
                    continue
                values: list[Node] = []
                if t.kind == "KW" and t.value == "else":
                    self.pos += 1
                else:
                    values.append(self.parse_expr())
                    while self.match(","):
                        values.append(self.parse_expr())
                self.eat("->")
                cob = self.eat("{")
                frames.append({"kind": "when_choice", "mode": "stmts",
                               "stmts": [], "ob_loc": self.loc(cob),
                               "defer": None, "when_loc": fr["loc"],
                               "values": values})
                continue

            # Normal block frame.
            t = self.peek()
            if t.kind == "}":
                self.eat("}")
                block = Block(loc=fr["ob_loc"], stmts=fr["stmts"])
                kind = fr["kind"]
                frames.pop()
                if kind == "root":
                    result = block
                    continue
                if kind == "when_choice":
                    # Attach a choice to the enclosing `when` frame.
                    frames[-1]["choices"].append(
                        WhenChoice(loc=fr["when_loc"], values=fr["values"],
                                   body=block))
                    continue
                # Build the compound node this block belongs to.
                if kind == "then":
                    # Peek for an `else` -- if present, open its block and
                    # defer building the If until the else-block closes.
                    if self.peek().kind == "KW" and self.peek().value == "else":
                        self.pos += 1
                        eob = self.eat("{")
                        frames.append({"kind": "else", "mode": "stmts",
                                       "stmts": [], "ob_loc": self.loc(eob),
                                       "defer": fr["defer"], "loc": fr["loc"],
                                       "cond": fr["cond"], "then_block": block})
                        continue
                    node = If(loc=fr["loc"], cond=fr["cond"],
                              then_block=block, else_block=None)
                elif kind == "else":
                    node = If(loc=fr["loc"], cond=fr["cond"],
                              then_block=fr["then_block"], else_block=block)
                elif kind == "while":
                    node = While(loc=fr["loc"], cond=fr["cond"], body=block)
                elif kind == "for":
                    node = For(loc=fr["loc"], var_name=fr["var"], lo=fr["lo"],
                               hi=fr["hi"], body=block)
                elif kind == "repeat":
                    node = Repeat(loc=fr["loc"], count=fr["count"], body=block)
                else:
                    raise ParseError(
                        f"{self.filename}: internal: bad frame kind {kind!r}")
                if fr["defer"] is not None:
                    node = Defer(loc=fr["defer"], stmt=node)
                attach(node)
                continue

            # A statement. First peel off any `defer` prefix.
            if t.kind == "KW" and t.value == "defer":
                self.pos += 1
                pending_defer = self.loc(t)
                continue
            mod, pending_defer = pending_defer, None
            opened = self._iter_stmt_dispatch(t, frames, mod)
            if not opened:
                # A simple (leaf) statement was parsed; wrap + attach it.
                node = self._last_simple
                if mod is not None:
                    node = Defer(loc=mod, stmt=node)
                attach(node)

        assert result is not None
        return result

    def _iter_stmt_dispatch(self, t: Token, frames: list[dict],
                            mod: Optional[Loc]) -> bool:
        """Parse one statement. If it opens a compound (pushing a block
        frame), return True. Otherwise parse a leaf statement, stash it in
        self._last_simple, and return False."""
        if t.kind == "DIRECTIVE" and t.value == "asm":
            self._last_simple = self.parse_inline_asm()
            return False
        if t.kind == "KW":
            if t.value in _TYPE_KWS:
                self._last_simple = self.parse_var_decl()
                return False
            if t.value == "if":
                self.pos += 1
                cond = self.parse_expr()
                ob = self.eat("{")
                frames.append({"kind": "then", "mode": "stmts", "stmts": [],
                               "ob_loc": self.loc(ob), "defer": mod,
                               "loc": self.loc(t), "cond": cond})
                return True
            if t.value == "while":
                self.pos += 1
                cond = self.parse_expr()
                ob = self.eat("{")
                frames.append({"kind": "while", "mode": "stmts", "stmts": [],
                               "ob_loc": self.loc(ob), "defer": mod,
                               "loc": self.loc(t), "cond": cond})
                return True
            if t.value == "when":
                self.pos += 1
                expr = self.parse_expr()
                self.eat("{")
                frames.append({"kind": "when", "mode": "choices",
                               "choices": [], "defer": mod,
                               "loc": self.loc(t), "expr": expr})
                return True
            if t.value == "repeat":
                self.pos += 1
                count = None
                if self.peek().kind != "{":
                    count = self.parse_expr()
                ob = self.eat("{")
                frames.append({"kind": "repeat", "mode": "stmts", "stmts": [],
                               "ob_loc": self.loc(ob), "defer": mod,
                               "loc": self.loc(t), "count": count})
                return True
            if t.value == "for":
                self.pos += 1
                name = self.eat("IDENT")
                self.eat("KW", "in")
                lo = self.parse_expr()
                self.eat("KW", "to")
                hi = self.parse_expr()
                ob = self.eat("{")
                frames.append({"kind": "for", "mode": "stmts", "stmts": [],
                               "ob_loc": self.loc(ob), "defer": mod,
                               "loc": self.loc(t), "var": name.value,
                               "lo": lo, "hi": hi})
                return True
            if t.value == "break":
                self.pos += 1
                self._last_simple = Break(loc=self.loc(t))
                return False
            if t.value == "continue":
                self.pos += 1
                self._last_simple = Continue(loc=self.loc(t))
                return False
            if t.value == "return":
                self.pos += 1
                value = None
                nxt = self.peek()
                if nxt.kind not in ("}", "KW") or (
                    nxt.kind == "KW" and nxt.value in ("true", "false")
                ):
                    value = self.parse_expr()
                self._last_simple = Return(loc=self.loc(t), value=value)
                return False
        # Anything else: assignment or expression statement.
        self._last_simple = self.parse_assign_or_expr()
        return False

    # ---- statements ----

    def parse_struct_decl(self) -> StructDecl:
        """`struct Name { ubyte fa; uword fb }` -- ubyte/uword fields."""
        kw = self.eat("KW", "struct")
        name_tok = self.eat("IDENT")
        self.eat("{")
        fields: list = []
        while self.peek().kind != "}":
            ft = self.eat("KW")
            if ft.value not in _TYPE_KWS:
                raise ParseError(
                    f"{self.filename}:{ft.line}:{ft.col}: "
                    f"field type {ft.value!r} not supported in struct"
                )
            fn = self.eat("IDENT")
            fields.append((ft.value, fn.value))
            # Allow ; or , as separators; both optional before }.
            self.match(";")
            self.match(",")
        self.eat("}")
        return StructDecl(loc=self.loc(kw), name=name_tok.value, fields=fields)

    def parse_enum_decl(self) -> EnumDecl:
        """`enum Name { A, B = $10, C }` -- ubyte constants accessed
        as Name.A. Missing values auto-increment from the previous."""
        kw = self.eat("KW", "enum")
        name_tok = self.eat("IDENT")
        self.eat("{")
        members: list = []
        while self.peek().kind != "}":
            mname = self.eat("IDENT")
            value = None
            if self.match("="):
                value = self.eat("INT").value
            members.append((mname.value, value))
            if not self.match(","):
                break
        self.eat("}")
        return EnumDecl(loc=self.loc(kw), name=name_tok.value, members=members)

    def parse_const_decl(self) -> VarDecl:
        """`const ubyte NAME = $42` -- compile-time constant.

        Lowered into a VarDecl with a "const" type-name marker so sema
        knows to fold uses into the literal value instead of generating
        a load. The initializer MUST be a literal for Phase 3.
        """
        c = self.eat("KW", "const")
        t = self.eat("KW")
        if t.value not in _TYPE_KWS:
            raise ParseError(
                f"{self.filename}:{t.line}:{t.col}: expected type after const"
            )
        name = self.eat("IDENT")
        self.eat("=")
        init = self.parse_expr()
        # Use a synthetic type_name so sema can spot const decls.
        vd = VarDecl(loc=self.loc(c), type_name=f"const-{t.value}",
                     name=name.value, init=init)
        return vd

    def parse_var_decl(self) -> VarDecl:
        t = self.eat("KW")
        if t.value not in _TYPE_KWS:
            raise ParseError(
                f"{self.filename}:{t.line}:{t.col}: expected type keyword, got {t.value!r}"
            )
        # Optional `[N]` (explicit size) or `[]` (size inferred from the
        # initializer) -- array form.
        array_size = None
        inferred = False
        if self.match("["):
            if self.peek().kind == "]":
                inferred = True          # `ubyte[] x = [...]`
            else:
                array_size = self.eat("INT").value
            self.eat("]")
        name = self.eat("IDENT")
        init = None
        if self.match("="):
            init = self.parse_expr()
        if inferred:
            if not isinstance(init, ArrayLit):
                raise ParseError(
                    f"{self.filename}:{t.line}:{t.col}: `{t.value}[]` needs an "
                    f"array initializer `[...]`"
                )
            array_size = len(init.elements)
        return VarDecl(loc=self.loc(t), type_name=t.value, name=name.value,
                       array_size=array_size, init=init)

    def parse_stmt(self) -> Node:
        t = self.peek()
        if t.kind == "DIRECTIVE" and t.value == "asm":
            return self.parse_inline_asm()
        if t.kind == "KW":
            if t.value in _TYPE_KWS:
                return self.parse_var_decl()
            if t.value == "if":
                return self.parse_if()
            if t.value == "while":
                return self.parse_while()
            if t.value == "when":
                return self.parse_when()
            if t.value == "repeat":
                return self.parse_repeat()
            if t.value == "for":
                return self.parse_for()
            if t.value == "break":
                self.pos += 1
                return Break(loc=self.loc(t))
            if t.value == "continue":
                self.pos += 1
                return Continue(loc=self.loc(t))
            if t.value == "defer":
                self.pos += 1
                body_stmt = self.parse_stmt()
                return Defer(loc=self.loc(t), stmt=body_stmt)
            if t.value == "return":
                self.pos += 1
                value = None
                # If next token starts an expression, parse it.
                nxt = self.peek()
                if nxt.kind not in ("}", "KW") or (
                    nxt.kind == "KW" and nxt.value in ("true", "false")
                ):
                    value = self.parse_expr()
                return Return(loc=self.loc(t), value=value)
        # Otherwise: assignment statement or expression statement.
        return self.parse_assign_or_expr()

    def parse_if(self) -> If:
        kw = self.eat("KW", "if")
        cond = self.parse_expr()
        then_blk = self.parse_block()
        else_blk = None
        if self.match("KW", "else"):
            else_blk = self.parse_block()
        return If(loc=self.loc(kw), cond=cond, then_block=then_blk, else_block=else_blk)

    def parse_while(self) -> While:
        kw = self.eat("KW", "while")
        cond = self.parse_expr()
        body = self.parse_block()
        return While(loc=self.loc(kw), cond=cond, body=body)

    def parse_when(self) -> When:
        kw = self.eat("KW", "when")
        expr = self.parse_expr()
        self.eat("{")
        choices: list[WhenChoice] = []
        while self.peek().kind != "}":
            values: list[Node] = []
            # 'else -> body' has no values; everything else is a comma
            # list of expressions terminated by '->'.
            if self.peek().kind == "KW" and self.peek().value == "else":
                self.pos += 1
            else:
                values.append(self.parse_expr())
                while self.match(","):
                    values.append(self.parse_expr())
            self.eat("->")
            body = self.parse_block()
            choices.append(WhenChoice(loc=self.loc(kw), values=values, body=body))
        self.eat("}")
        return When(loc=self.loc(kw), expr=expr, choices=choices)

    def parse_repeat(self) -> Repeat:
        kw = self.eat("KW", "repeat")
        # `repeat { ... }` -- forever.
        # `repeat N { ... }` -- N times (N a ubyte expression or const).
        count = None
        if self.peek().kind != "{":
            count = self.parse_expr()
        body = self.parse_block()
        return Repeat(loc=self.loc(kw), count=count, body=body)

    def parse_for(self) -> For:
        kw = self.eat("KW", "for")
        name = self.eat("IDENT")
        self.eat("KW", "in")
        lo = self.parse_expr()
        self.eat("KW", "to")
        hi = self.parse_expr()
        body = self.parse_block()
        return For(loc=self.loc(kw), var_name=name.value, lo=lo, hi=hi, body=body)

    def parse_assign_or_expr(self) -> Node:
        # `@(addr) = byte` -- write a byte to a runtime-computed addr.
        if self.peek().kind == "@":
            save = self.pos
            self.pos += 1
            self.eat("(")
            addr = self.parse_expr()
            self.eat(")")
            target = MemAt(loc=self.loc(self.toks[save]), addr=addr)
            if self.peek().kind == "=":
                self.eat("=")
                rhs = self.parse_expr()
                return Assign(loc=self.loc(self.toks[save]),
                              target=target, op="=", rhs=rhs)
            # Otherwise an expression statement that reads memory.
            return ExprStmt(loc=target.loc, expr=target)
        # Assignments: `IDENT = ...`, `IDENT[idx] = ...`, plus their
        # augmented forms. Anything else is an expression statement.
        if self.peek().kind == "IDENT":
            save = self.pos
            ident = self.eat("IDENT")
            # Allow `instance.field` for struct-field assignment.
            name = ident.value
            while self.match("."):
                m = self.eat("IDENT")
                name += "." + m.value
            target: Node = Ident(loc=self.loc(ident), name=name)
            # Optional `[idx]` -- array element target; optional `.field`.
            if self.peek().kind == "[":
                self.eat("[")
                idx = self.parse_expr()
                self.eat("]")
                field = None
                if self.match("."):
                    f = self.eat("IDENT")
                    field = f.value
                target = Index(loc=self.loc(ident), array=target, index=idx,
                               field=field)
            if self.peek().kind == "=":
                self.eat("=")
                rhs = self.parse_expr()
                return Assign(loc=self.loc(ident), target=target, op="=", rhs=rhs)
            if self.peek().kind in _AUG_OPS:
                op_tok = self.eat(self.peek().kind)
                rhs = self.parse_expr()
                return Assign(loc=self.loc(ident), target=target, op=op_tok.kind, rhs=rhs)
            # Not an assign; rewind for call/expr parsing.
            self.pos = save
        return self.parse_call_stmt()

    def parse_inline_asm(self) -> InlineAsm:
        d = self.eat("DIRECTIVE", "asm")
        # Both forms reach the parser as `{{ STR }}`: the legacy quoted body is
        # a string literal, and the raw `%asm {{ ... }}` body was normalized
        # into a STR token by the lexer. So one path handles both.
        if self.peek(0).kind != "{" or self.peek(1).kind != "{":
            raise ParseError(
                f"{self.filename}:{d.line}:{d.col}: %asm must be followed by {{{{ ... }}}}"
            )
        self.eat("{"); self.eat("{")
        body = self.eat("STR").value
        self.eat("}"); self.eat("}")
        return InlineAsm(loc=self.loc(d), text=body)

    def parse_call_stmt(self) -> ExprStmt:
        e = self.parse_expr()
        return ExprStmt(loc=e.loc, expr=e)

    # ---- expressions ----

    def parse_expr(self) -> Node:
        """Top of the expression precedence ladder."""
        if self.iter_expr:
            # Delegate to the iterative parser, sharing this parser's
            # token stream and cursor so it consumes the same span.
            from .iter_parse import IterParser
            ip = IterParser(self.toks, self.filename)
            ip.pos = self.pos
            node = ip.parse_expr()
            self.pos = ip.pos
            return node
        return self._parse_binop(level=0)

    def _parse_binop(self, level: int) -> Node:
        if level >= len(_OP_LEVELS):
            return self.parse_unary()
        left = self._parse_binop(level + 1)
        while True:
            t = self.peek()
            # Accept both punctuation tokens ('+', '<<', etc.) and
            # keyword operators ('and', 'or', 'xor') at this level.
            op = t.value if (t.kind == "KW" and t.value in _OP_PRECEDENCE) else (
                t.kind if t.kind in _OP_PRECEDENCE else None
            )
            if op is None or _OP_PRECEDENCE[op] != level:
                return left
            self.pos += 1
            right = self._parse_binop(level + 1)
            left = BinOp(loc=left.loc, op=op, lhs=left, rhs=right)

    def parse_unary(self) -> Node:
        t = self.peek()
        if t.kind == "KW" and t.value == "not":
            self.pos += 1
            return UnaryOp(loc=self.loc(t), op="not", operand=self.parse_unary())
        if t.kind == "~":
            self.pos += 1
            return UnaryOp(loc=self.loc(t), op="~", operand=self.parse_unary())
        if t.kind == "-":
            self.pos += 1
            return UnaryOp(loc=self.loc(t), op="-", operand=self.parse_unary())
        if t.kind == "&":
            self.pos += 1
            n = self.eat("IDENT")
            return AddressOf(loc=self.loc(t), name=n.value)
        if t.kind == "@":
            self.pos += 1
            self.eat("(")
            addr = self.parse_expr()
            self.eat(")")
            return MemAt(loc=self.loc(t), addr=addr)
        return self.parse_primary()

    def parse_primary(self) -> Node:
        t = self.peek()
        if t.kind == "(":
            self.pos += 1
            inner = self.parse_expr()
            self.eat(")")
            return inner
        if t.kind == "STR":
            self.pos += 1
            return StrLit(loc=self.loc(t), value=t.value)
        if t.kind == "INT":
            self.pos += 1
            return IntLit(loc=self.loc(t), value=t.value)
        if t.kind == "KW" and t.value in ("true", "false"):
            self.pos += 1
            return BoolLit(loc=self.loc(t), value=(t.value == "true"))
        if t.kind == "[":
            # array literal: [e0, e1, ...]  (used as an array variable initializer)
            self.pos += 1
            elems: list[Node] = []
            if self.peek().kind != "]":
                elems.append(self.parse_expr())
                while self.match(","):
                    elems.append(self.parse_expr())
            self.eat("]")
            return ArrayLit(loc=self.loc(t), elements=elems)
        if t.kind == "IDENT":
            return self.parse_dotted_or_call()
        raise ParseError(
            f"{self.filename}:{t.line}:{t.col}: expected expression, got "
            f"{t.kind} {t.value!r}"
        )

    def parse_dotted_or_call(self) -> Node:
        first = self.eat("IDENT")
        path = [first.value]
        while self.match("."):
            nxt = self.eat("IDENT")
            path.append(nxt.value)
        if self.match("("):
            args: list[Node] = []
            if self.peek().kind != ")":
                args.append(self.parse_expr())
                while self.match(","):
                    args.append(self.parse_expr())
            self.eat(")")
            return Call(loc=self.loc(first), path=path, args=args)
        # Bare identifier (or dotted path).
        name = path[0] if len(path) == 1 else ".".join(path)
        node: Node = Ident(loc=self.loc(first), name=name)
        # Optional `[idx]` -- array element read; optionally followed
        # by `.field` for arrays of structs.
        if self.peek().kind == "[":
            self.eat("[")
            idx = self.parse_expr()
            self.eat("]")
            field = None
            if self.match("."):
                f = self.eat("IDENT")
                field = f.value
            node = Index(loc=self.loc(first), array=node, index=idx, field=field)
        return node


def parse(tokens: list[Token], filename: str,
          iter_expr: bool = True, iter_stmt: bool = True) -> Program:
    return Parser(tokens, filename, iter_expr=iter_expr,
                  iter_stmt=iter_stmt).parse_program()
