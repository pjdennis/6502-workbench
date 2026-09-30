"""Canonical S-expression serialization of the Prog8 AST (Phase 6, M0).

This freezes the AST-serialization **contract** that the eventual Prog8
(on-target) parser must reproduce byte-for-byte. The Python iterative
parser is the oracle; its serialized output is the golden the on-target
`p1` parser will be diffed against at every milestone (M1-M4). See
`PARSER_PORT_DESIGN.md` section 4.

What is and isn't serialized:

  * Only fields the **parser** fills are emitted. Sema-assigned fields
    (`sym`, `type`, `mangled`, `address`, `label`, `const_value`, ...)
    are deliberately omitted, because the on-target parser produces a
    pre-sema AST -- the serialization must describe exactly what parsing
    yields, nothing more.
  * Source `Loc` is omitted too: positions are not part of the
    structural contract, exactly as `tests/test_iter_parse.py::dump`
    already drops them.

Format: a deterministic, indented prefix S-expression, one head per
line, children indented two spaces, closing parens trailing. It is
intentionally human-readable so on-target mismatches are easy to
localize. The Python serializer here is plain recursion; the on-target
version is an explicit-stack tree walk that emits the identical bytes
(that is M3 work).
"""
from __future__ import annotations

from .ast import (
    AddressOf, ArrayLit, Assign, BinOp, Block, BoolLit, Break, Call, Continue, Defer,
    EnumDecl, ExprStmt, For, Ident, If, Index, InlineAsm, IntLit, MemAt,
    Node, Program, Repeat, Return, StrLit, StructDecl, Sub, UnaryOp,
    VarDecl, When, WhenChoice, While,
)

# Unary '-' must print distinctly from binary '-'; everything else uses
# its source spelling.
_UNARY_TAG = {"-": "u-", "~": "~", "not": "not"}


def _esc(s: str) -> str:
    """Escape a string literal deterministically. The escape set is
    small and trivially reproducible on the 6502: backslash, quote, and
    the three common control characters."""
    out = ['"']
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _form(head: str, children: list[list[str]]) -> list[str]:
    """Assemble one S-expression form.

    `head` is the opening text including '(' and the kind plus any
    leading scalar fields, but no closing paren. `children` is a list of
    already-rendered child forms (each a list of lines). The children are
    indented two spaces and the single closing paren is appended to the
    very last line so parens trail compactly.
    """
    if not children:
        return [head + ")"]
    lines = [head]
    for child in children:
        lines.extend("  " + ln for ln in child)
    lines[-1] = lines[-1] + ")"
    return lines


def ser(node: Node) -> list[str]:
    """Render an expression or statement node to a list of lines."""
    # ---- expressions ----
    if isinstance(node, IntLit):
        return _form(f"(int {node.value}", [])
    if isinstance(node, StrLit):
        return _form(f"(str {_esc(node.value)}", [])
    if isinstance(node, BoolLit):
        return _form(f"(bool {'true' if node.value else 'false'}", [])
    if isinstance(node, ArrayLit):
        return _form("(arr", [ser(e) for e in node.elements])
    if isinstance(node, Ident):
        return _form(f"(id {node.name}", [])
    if isinstance(node, AddressOf):
        return _form(f"(addr {node.name}", [])
    if isinstance(node, BinOp):
        return _form(f"({node.op}", [ser(node.lhs), ser(node.rhs)])
    if isinstance(node, UnaryOp):
        return _form(f"({_UNARY_TAG[node.op]}", [ser(node.operand)])
    if isinstance(node, MemAt):
        return _form("(mem", [ser(node.addr)])
    if isinstance(node, Index):
        children = [ser(node.array), ser(node.index)]
        if node.field is not None:
            children.append([f".{node.field}"])
        return _form("(idx", children)
    if isinstance(node, Call):
        path = ".".join(node.path)
        return _form(f"(call {path}", [ser(a) for a in node.args])

    # ---- statements ----
    if isinstance(node, Block):
        return _form("(block", [ser(s) for s in node.stmts])
    if isinstance(node, ExprStmt):
        return _form("(exprstmt", [ser(node.expr)])
    if isinstance(node, InlineAsm):
        return _form(f"(asm {_esc(node.text)}", [])
    if isinstance(node, VarDecl):
        ty = node.type_name
        if node.array_size is not None:
            ty += f"[{node.array_size}]"
        children = [ser(node.init)] if node.init is not None else []
        return _form(f"(var {ty} {node.name}", children)
    if isinstance(node, Assign):
        return _form(f"(assign {node.op}",
                     [ser(node.target), ser(node.rhs)])
    if isinstance(node, If):
        children = [ser(node.cond), ser(node.then_block)]
        if node.else_block is not None:
            children.append(ser(node.else_block))
        return _form("(if", children)
    if isinstance(node, While):
        return _form("(while", [ser(node.cond), ser(node.body)])
    if isinstance(node, Repeat):
        children = []
        if node.count is not None:
            children.append(ser(node.count))
        children.append(ser(node.body))
        return _form("(repeat", children)
    if isinstance(node, For):
        return _form(f"(for {node.var_name}",
                     [ser(node.lo), ser(node.hi), ser(node.body)])
    if isinstance(node, When):
        return _form("(when",
                     [ser(node.expr)] + [ser(c) for c in node.choices])
    if isinstance(node, WhenChoice):
        vals = _form("(vals", [ser(v) for v in node.values])
        return _form("(choice", [vals, ser(node.body)])
    if isinstance(node, Break):
        return ["(break)"]
    if isinstance(node, Continue):
        return ["(continue)"]
    if isinstance(node, Return):
        children = [ser(node.value)] if node.value is not None else []
        return _form("(return", children)
    if isinstance(node, Defer):
        return _form("(defer", [ser(node.stmt)])

    raise TypeError(f"serialize: unhandled node {type(node).__name__}")


def _ser_enum(e: EnumDecl) -> list[str]:
    members = []
    for (mname, mval) in e.members:
        members.append([f"({mname} {mval})" if mval is not None
                        else f"({mname} -)"])
    return _form(f"(enum {e.name}", [_form("(members", members)])


def _ser_struct(s: StructDecl) -> list[str]:
    fields = [[f"({ft} {fn})"] for (ft, fn) in s.fields]
    return _form(f"(struct {s.name}", [_form("(fields", fields)])


def _ser_sub(s: Sub) -> list[str]:
    kind = ("asmsub" if s.is_asmsub else "inline" if s.is_inline
            else "main" if s.is_main else "sub")
    params = _form("(params",
                   [[f"(param {p.type_name} {p.name})"] for p in s.params])
    head = f"(subdef {s.name} {kind} {s.return_type_name}"
    children = [params]
    if s.is_asmsub:
        children.append([f"(asmtarget {s.asm_target})"])
    else:
        children.append(ser(s.body))
    return _form(head, children)


def _ser_program(p: Program) -> list[str]:
    children = [
        _form(f"(address ${p.address:04x}", []),
        _form(f"(output {p.output_format}", []),
        _form(f"(target {p.target}", []),
        _form("(imports", [[f"(import {n})"] for n in p.imports]),
        _form("(vars", [ser(v) for v in p.module_vars]),
        _form("(enums", [_ser_enum(e) for e in p.enums]),
        _form("(structs", [_ser_struct(s) for s in p.structs]),
        _form("(subs", [_ser_sub(s) for s in p.subs]),
    ]
    return _form("(program", children)


def serialize(node) -> str:
    """Serialize a parsed AST (a `Program`, or any expression/statement
    node) to the canonical S-expression text, newline-terminated."""
    lines = _ser_program(node) if isinstance(node, Program) else ser(node)
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Token-stream serialization (Phase 6, M1 contract).
#
# The lexer port (`p1/lexer.p8`) is verified by dumping its token stream
# and diffing against this Python dump -- the same oracle pattern M0 set
# up for the AST. One token per line:
#
#     INT <decimal>            ; value already normalized ($ff/%1010/'A')
#     STR <escaped>            ; same escape set as string-literal AST
#     IDENT <text>             KW <text>            DIRECTIVE <text>
#     PUNCT <spelling>         ; punctuation/operator (kind == value)
#     EOF
#
# Source line/col are intentionally omitted: positions are not part of
# the structural contract (consistent with the AST serializer dropping
# Loc). M1 verifies *tokenization* -- bases, char/string escapes,
# keyword classification, and multi-char-operator maximal munch -- which
# is the hard part of the lexer. Position tracking, if verified later,
# gets its own dump.
# ---------------------------------------------------------------------------

def _tok_line(t) -> str:
    k = t.kind
    if k == "INT":
        return f"INT {t.value}"
    if k == "STR":
        return f"STR {_esc(t.value)}"
    if k in ("IDENT", "KW", "DIRECTIVE"):
        return f"{k} {t.value}"
    if k == "EOF":
        return "EOF"
    # Punctuation/operator token: kind is the source spelling.
    return f"PUNCT {t.kind}"


def serialize_tokens(tokens) -> str:
    """Serialize a lexer token list to the canonical token-dump text,
    newline-terminated."""
    return "".join(_tok_line(t) + "\n" for t in tokens)
