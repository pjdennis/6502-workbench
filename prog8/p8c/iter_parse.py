"""Iterative (non-recursive) expression parser -- Phase 6, step 1.

The host parser in `parse.py` is recursive descent. Prog8 forbids
recursion (subs are non-reentrant by design), so the parser cannot be
ported to Prog8 as-is. To self-host the *real* p8c, the parser must be
rebuilt around explicit stacks.

This module is the first slice of that work: an iterative expression
parser built on the shunting-yard algorithm with two explicit stacks
(operands + operators) and a small marker stack folded into the
operator stack. It produces AST nodes that are structurally identical
(modulo source `Loc`) to `parse.py`'s `parse_expr`, which the test
suite verifies over a corpus of expression inputs.

The shape here -- a flat dispatch loop over tokens, with no call into
itself -- is exactly what a Prog8 port needs. Parentheses, function
calls (with comma-separated args), prefix unary operators, and the
postfix `arr[idx]` / `arr[idx].field` forms are all handled without
recursion: nested groupings live as markers on the operator stack, and
each marker records the operand-stack depth ("floor") it was opened
at, so reductions never reach past their own sub-expression.

Only expression parsing is covered for now; statements remain in
`parse.py`. A later push extends the same machinery to statements and
then switches the compiler over.
"""
from __future__ import annotations

from typing import Optional

from .ast import (
    AddressOf, ArrayLit, BinOp, BoolLit, Call, Cast, Ident, Index, IntLit, Loc,
    MemAt, Node, StrLit, UnaryOp,
)
from .lex import Token
from .parse import ParseError, _OP_PRECEDENCE

# Prefix unary operators bind tighter than every binary operator, so we
# give them a precedence above the top of the binary ladder.
_UNARY_PREC = len(_OP_PRECEDENCE) + 100


class IterParser:
    """Iterative expression parser over a token list.

    Mirrors the slice of `parse.Parser`'s interface that the rest of the
    compiler relies on (`peek` / `eat` / `match` / `pos`), so it can be
    slotted in where `parse_expr` is called today.
    """

    def __init__(self, tokens: list[Token], filename: str):
        self.toks = tokens
        self.pos = 0
        self.filename = filename

    # ---- token helpers (same semantics as parse.Parser) ----

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

    def loc(self, t: Token) -> Loc:
        return Loc(self.filename, t.line, t.col)

    # ---- operator-stack records ----
    #
    # Each entry is a small dict tagged by 'k':
    #   {'k':'binop', 'op':str, 'prec':int, 'loc':Loc}
    #   {'k':'unop',  'op':str, 'loc':Loc}
    #   {'k':'lparen','floor':int}                 -- grouping '('
    #   {'k':'memat', 'floor':int, 'loc':Loc}      -- '@(' ... ')'
    #   {'k':'call',  'path':list, 'args':list, 'floor':int, 'loc':Loc}
    #   {'k':'lbracket', 'floor':int}              -- postfix 'arr['
    #
    # 'floor' is the operand-stack length when the marker was opened, so
    # reductions for that marker never consume operands beneath it.

    @staticmethod
    def _is_op(rec: dict) -> bool:
        return rec["k"] in ("binop", "unop")

    @staticmethod
    def _is_marker(rec: dict) -> bool:
        return rec["k"] in ("lparen", "memat", "call", "lbracket")

    @staticmethod
    def _op_prec(rec: dict) -> int:
        return _UNARY_PREC if rec["k"] == "unop" else rec["prec"]

    # ---- main entry ----

    def parse_expr(self) -> Node:
        operands: list[Node] = []
        ops: list[dict] = []
        # True when the next token should start an operand (i.e. we're in
        # a prefix position): at the start, and after a binary/unary
        # operator, '(', '@(', '[', or ','. False when an operand has just
        # been produced (infix position).
        expect_operand = True
        # Only a freshly-parsed bare identifier may be followed by a '['
        # index -- this matches the recursive parser, which attaches the
        # index inside parse_dotted_or_call and nowhere else.
        index_ok = False

        def apply(rec: dict) -> None:
            if rec["k"] == "binop":
                rhs = operands.pop()
                lhs = operands.pop()
                operands.append(BinOp(loc=lhs.loc, op=rec["op"], lhs=lhs, rhs=rhs))
            else:  # unop
                operand = operands.pop()
                operands.append(
                    UnaryOp(loc=rec["loc"], op=rec["op"], operand=operand))

        def reduce_to_marker() -> Optional[dict]:
            """Apply operators until the top of `ops` is a marker; return
            that marker (left in place), or None if `ops` empties."""
            while ops and self._is_op(ops[-1]):
                apply(ops.pop())
            return ops[-1] if ops and self._is_marker(ops[-1]) else None

        while True:
            t = self.peek()

            # ---- closing / separator tokens ----
            if t.kind in (")", "]", ","):
                marker = reduce_to_marker()
                if t.kind == ")":
                    if marker is None:
                        break                       # ')' belongs to an outer construct
                    if marker["k"] == "lparen":
                        ops.pop()                   # operand stays as the group value
                        self.pos += 1
                        expect_operand = False
                        index_ok = False
                        continue
                    if marker["k"] == "memat":
                        ops.pop()
                        addr = operands.pop()
                        operands.append(MemAt(loc=marker["loc"], addr=addr))
                        self.pos += 1
                        expect_operand = False
                        index_ok = False
                        continue
                    if marker["k"] == "call":
                        ops.pop()
                        if len(operands) > marker["floor"]:
                            marker["args"].append(operands.pop())
                        operands.append(Call(loc=marker["loc"],
                                             path=marker["path"],
                                             args=marker["args"]))
                        self.pos += 1
                        expect_operand = False
                        index_ok = False
                        continue
                    raise ParseError(
                        f"{self.filename}:{t.line}:{t.col}: unexpected ')'")
                if t.kind == "]":
                    if marker is None or marker["k"] != "lbracket":
                        break
                    ops.pop()
                    index = operands.pop()
                    array = operands.pop()
                    self.pos += 1                   # consume ']'
                    field = None
                    if self.peek().kind == ".":
                        self.pos += 1
                        field = self.eat("IDENT").value
                    operands.append(Index(loc=array.loc, array=array,
                                          index=index, field=field))
                    expect_operand = False
                    index_ok = False
                    continue
                # t.kind == ","
                if marker is None or marker["k"] != "call":
                    break
                marker["args"].append(operands.pop())
                self.pos += 1
                expect_operand = True
                index_ok = False
                continue

            if expect_operand:
                index_ok = False
                if t.kind == "INT":
                    operands.append(IntLit(loc=self.loc(t), value=t.value))
                    self.pos += 1
                    expect_operand = False
                elif t.kind == "STR":
                    operands.append(StrLit(loc=self.loc(t), value=t.value))
                    self.pos += 1
                    expect_operand = False
                elif t.kind == "KW" and t.value in ("true", "false"):
                    operands.append(BoolLit(loc=self.loc(t),
                                            value=(t.value == "true")))
                    self.pos += 1
                    expect_operand = False
                elif t.kind == "KW" and t.value == "not":
                    ops.append({"k": "unop", "op": "not", "loc": self.loc(t)})
                    self.pos += 1
                elif t.kind in ("~", "-"):
                    ops.append({"k": "unop", "op": t.kind, "loc": self.loc(t)})
                    self.pos += 1
                elif t.kind == "&":
                    self.pos += 1
                    n = self.eat("IDENT")
                    operands.append(AddressOf(loc=self.loc(t), name=n.value))
                    expect_operand = False
                elif t.kind == "@":
                    self.pos += 1
                    self.eat("(")
                    ops.append({"k": "memat", "floor": len(operands),
                                "loc": self.loc(t)})
                elif t.kind == "(":
                    ops.append({"k": "lparen", "floor": len(operands)})
                    self.pos += 1
                elif t.kind == "[":
                    # array literal `[e0, e1, ...]` (an array variable
                    # initializer). Each element is a full expression; a plain
                    # parse_expr stops at the separating ',' / closing ']'.
                    self.pos += 1
                    elems: list[Node] = []
                    if self.peek().kind != "]":
                        elems.append(self.parse_expr())
                        while self.peek().kind == ",":
                            self.pos += 1
                            elems.append(self.parse_expr())
                    self.eat("]")
                    operands.append(ArrayLit(loc=self.loc(t), elements=elems))
                    expect_operand = False
                elif t.kind == "IDENT":
                    first = t
                    path = [self.eat("IDENT").value]
                    while self.peek().kind == ".":
                        self.pos += 1
                        path.append(self.eat("IDENT").value)
                    if self.peek().kind == "(":
                        self.pos += 1
                        ops.append({"k": "call", "path": path, "args": [],
                                    "floor": len(operands), "loc": self.loc(first)})
                        # expect_operand stays True (parse first arg)
                    else:
                        name = path[0] if len(path) == 1 else ".".join(path)
                        operands.append(Ident(loc=self.loc(first), name=name))
                        expect_operand = False
                        index_ok = True
                else:
                    raise ParseError(
                        f"{self.filename}:{t.line}:{t.col}: expected expression, "
                        f"got {t.kind} {t.value!r}")
                continue

            # ---- infix position ----
            # `expr as TYPE` -- type cast. Lowest precedence: it applies to the
            # whole sub-expression in the current grouping, so first reduce all
            # pending operators (down to the nearest marker), then wrap the
            # resulting operand. (The transform only ever emits a parenthesized
            # `(inner as ubyte)`, so this binds to all of `inner`.)
            if t.kind == "KW" and t.value == "as":
                self.pos += 1
                tn = self.eat("KW")          # a type keyword: ubyte/uword/...
                while ops and self._is_op(ops[-1]):
                    apply(ops.pop())
                operand = operands.pop()
                operands.append(Cast(loc=operand.loc, operand=operand,
                                     type_name=tn.value))
                expect_operand = False
                index_ok = False
                continue
            op = (t.value if (t.kind == "KW" and t.value in _OP_PRECEDENCE)
                  else (t.kind if t.kind in _OP_PRECEDENCE else None))
            if op is not None:
                prec = _OP_PRECEDENCE[op]
                while ops and self._is_op(ops[-1]) and self._op_prec(ops[-1]) >= prec:
                    apply(ops.pop())
                ops.append({"k": "binop", "op": op, "prec": prec,
                            "loc": self.loc(t)})
                self.pos += 1
                expect_operand = True
                index_ok = False
                continue
            if t.kind == "[" and index_ok:
                ops.append({"k": "lbracket", "floor": len(operands)})
                self.pos += 1
                expect_operand = True
                index_ok = False
                continue
            # Anything else ends the expression.
            break

        # Drain remaining operators; any leftover marker is unbalanced.
        while ops:
            rec = ops.pop()
            if self._is_marker(rec):
                raise ParseError(
                    f"{self.filename}: unbalanced '{rec['k']}' in expression")
            apply(rec)

        if len(operands) != 1:
            t = self.peek()
            raise ParseError(
                f"{self.filename}:{t.line}:{t.col}: malformed expression")
        return operands[0]


def parse_expr(tokens: list[Token], filename: str, pos: int = 0):
    """Parse a single expression starting at `pos`; return (node, new_pos)."""
    p = IterParser(tokens, filename)
    p.pos = pos
    node = p.parse_expr()
    return node, p.pos
