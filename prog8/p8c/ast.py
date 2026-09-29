"""Typed AST for the Prog8 subset.

Kept deliberately small for Phase 1. Each node carries a source
location (file, line, col) so diagnostics can pinpoint the user's
mistake even after many passes.

Type system here is Phase 1:
  * UBYTE, UWORD, BOOL, STR (literal only -- str values are emitted
    as zero-terminated byte arrays in the .data section).
  * VOID for sub returns.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---- Types ----------------------------------------------------------------

class Type:
    pass


@dataclass(frozen=True)
class TUByte(Type):
    def __repr__(self) -> str: return "ubyte"


@dataclass(frozen=True)
class TByte(Type):
    """Signed 8-bit. Same storage as ubyte; affects comparison codegen
    and (later) multiplication / division."""
    def __repr__(self) -> str: return "byte"


@dataclass(frozen=True)
class TUByteArray(Type):
    """ubyte[N] -- a fixed-size byte array. Stored in main memory
    (not ZP), addressed by an absolute label."""
    size: int
    def __repr__(self) -> str: return f"ubyte[{self.size}]"


@dataclass(frozen=True)
class TUWordArray(Type):
    """uword[N] -- a fixed-size word array (2 bytes/element, little-endian).
    Stored in main memory, addressed by an absolute label. Supports
    >256 elements and a uword index (16-bit pointer addressing)."""
    size: int
    def __repr__(self) -> str: return f"uword[{self.size}]"


@dataclass(frozen=True)
class TUWord(Type):
    def __repr__(self) -> str: return "uword"


@dataclass(frozen=True)
class TBool(Type):
    def __repr__(self) -> str: return "bool"


@dataclass(frozen=True)
class TStr(Type):
    def __repr__(self) -> str: return "str"


@dataclass(frozen=True)
class TVoid(Type):
    def __repr__(self) -> str: return "void"


UBYTE = TUByte()
BYTE = TByte()
UWORD = TUWord()
BOOL = TBool()
STR = TStr()
VOID = TVoid()


def type_from_name(name: str) -> Optional[Type]:
    return {"ubyte": UBYTE, "byte": BYTE, "uword": UWORD, "bool": BOOL,
            "str": STR, "void": VOID}.get(name)


# ---- Nodes ----------------------------------------------------------------

@dataclass
class Loc:
    file: str
    line: int
    col: int


@dataclass
class Node:
    loc: Loc


# Expressions

@dataclass
class BinOp(Node):
    """Binary operator on byte values.

    op is the source-level operator string ('+', '-', '&', '|', '^',
    '<<', '>>', '==', '!=', '<', '<=', '>', '>=', 'and', 'or').

    Comparison and logical ops produce BOOL; the others propagate the
    operand type. sema fills `type` and (for arith ops on mixed sizes)
    inserts widening if/when we add wider types.
    """
    op: str
    lhs: "Node"
    rhs: "Node"
    type: Type = UBYTE


@dataclass
class UnaryOp(Node):
    """Unary operator: 'not' (logical), '~' (bitwise), '-' (negate)."""
    op: str
    operand: "Node"
    type: Type = UBYTE


@dataclass
class Cast(Node):
    """`expr as TYPE` -- a type cast. The only forms the compiler needs are
    narrowing a uword to ubyte (low byte) and widening ubyte to uword (high
    byte = 0); these match upstream Prog8's `as` operator. sema sets `type`
    from `type_name`."""
    operand: "Node"
    type_name: str
    type: Type = UBYTE


@dataclass
class IntLit(Node):
    value: int
    type: Type = UBYTE          # narrowed by sema


@dataclass
class StrLit(Node):
    value: str
    type: Type = STR
    # During codegen sema assigns a unique label that the .data section
    # will use to emit the bytes; the expression itself becomes a uword
    # value (the address of that label).
    label: str = ""


@dataclass
class BoolLit(Node):
    value: bool
    type: Type = BOOL


@dataclass
class ArrayLit(Node):
    """`[e0, e1, ...]` initializer for an array variable. Sema resolves the
    elements to constant values (ints, or string-literal / &ident addresses
    for uword arrays) and attaches them to the array Symbol for emission."""
    elements: list = field(default_factory=list)
    type: Type = UBYTE          # element type context, set by sema


@dataclass
class Ident(Node):
    name: str
    # Resolved by sema:
    sym: Optional["Symbol"] = None
    type: Type = UBYTE


@dataclass
class Index(Node):
    """`arr[idx]` -- read or write target. Both `arr` and `idx` are
    arbitrary expressions; sema also handles `arr[idx].field` for
    arrays of structs (field name stored on the node)."""
    array: Node
    index: Node
    field: Optional[str] = None       # `arr[i].field` if non-None
    type: Type = UBYTE
    sym: Optional["Symbol"] = None    # filled by sema (array's symbol)


@dataclass
class MemAt(Node):
    """`@(expr)` -- read or write a byte at the address `expr` (uword)."""
    addr: Node
    type: Type = UBYTE


@dataclass
class AddressOf(Node):
    """`&name` -- the address (uword) of a named variable / array."""
    name: str
    sym: Optional["Symbol"] = None
    type: Type = UWORD


@dataclass
class Call(Node):
    # callee can be `a.b.c` -> we keep it as a dotted path list.
    path: list[str]
    args: list[Node]
    sym: Optional["Symbol"] = None
    type: Type = VOID


# Statements

@dataclass
class Block(Node):
    stmts: list[Node]


@dataclass
class ExprStmt(Node):
    expr: Node


@dataclass
class InlineAsm(Node):
    """%asm{{ raw assembly text }}; emitted verbatim into the output."""
    text: str


@dataclass
class VarDecl(Node):
    """`ubyte x` or `ubyte x = expr`. Also `ubyte[N] arr` for arrays.

    Sema mangles the name (p8v_<sub>_<name> for sub-scoped, p8v_<name>
    for module-scoped) and allocates storage. Scalars go in ZP; arrays
    are emitted as labeled .byte blocks in the program tail.
    """
    type_name: str
    name: str
    array_size: Optional[int] = None    # set if this is `ubyte[N] x`
    init: Optional[Node] = None
    sym: Optional["Symbol"] = None


@dataclass
class Assign(Node):
    """target = expr, plus augmented forms (+=, -=, |=, &=, ^=, <<=, >>=)."""
    target: Node          # always an Ident in Phase 2
    op: str               # '=', '+=', '-=', ...
    rhs: Node


@dataclass
class If(Node):
    cond: Node
    then_block: Block
    else_block: Optional[Block] = None


@dataclass
class While(Node):
    cond: Node
    body: Block


@dataclass
class Repeat(Node):
    """`repeat N { ... }` -- iterate the body N times (N is a constant
    or ubyte expression). N == 0 means 256 iterations to match the
    natural 6502 wrap; we'll document that in the language docs and
    test it explicitly."""
    count: Optional[Node]    # None means "forever"
    body: Block


@dataclass
class WhenChoice(Node):
    """One arm of a `when` statement: `value, value, ... -> block` or
    `else -> block`."""
    values: list[Node]            # empty list = else branch
    body: Block


@dataclass
class When(Node):
    """when expr { v1, v2 -> body; else -> body }"""
    expr: Node
    choices: list[WhenChoice]


@dataclass
class For(Node):
    """`for var in lo to hi { ... }` -- inclusive range. Phase 2 only
    supports ubyte ranges; the var must already exist OR be declared
    inline as `for ubyte i in 0 to 15`. We require pre-declaration for
    Phase 2 to keep the grammar tiny."""
    var_name: str
    lo: Node
    hi: Node
    body: Block
    sym: Optional["Symbol"] = None      # filled by sema


@dataclass
class Break(Node):
    pass


@dataclass
class Continue(Node):
    pass


# Top-level

@dataclass
class Param(Node):
    type_name: str       # 'ubyte' | 'uword'
    name: str
    sym: Optional["Symbol"] = None
    reg: Optional[str] = None   # register-ABI annotation: 'A'|'X'|'Y'|'AY' (asmsub)


@dataclass
class EnumDecl(Node):
    """`enum Name { A, B = 5, C }` -- a set of ubyte constants accessed
    as Name.A. Auto-assigns sequential values starting from 0 (or from
    the most recent explicit value)."""
    name: str
    members: list = field(default_factory=list)   # list of (member_name, IntLit | None)


@dataclass
class StructDecl(Node):
    """`struct Name { ubyte field1; uword field2 }` -- a fixed layout
    of named ubyte/uword fields. Each instance is stored as a
    contiguous block in main memory (like an array)."""
    name: str
    fields: list = field(default_factory=list)   # list of (type_name, field_name)


@dataclass
class Sub(Node):
    name: str
    body: Block
    params: list[Param] = field(default_factory=list)
    return_type_name: str = "void"      # 'void' | 'ubyte' | 'uword'
    mangled: str = ""                   # filled by sema, e.g. "p8s_main"
    is_main: bool = False
    is_asmsub: bool = False             # True iff `asmsub` declaration
    is_inline: bool = False             # `inline sub` -- emit body at call site, no JSR
    asm_target: Optional[str] = None    # for asmsub: the asm symbol to JSR to
    ret_reg: Optional[str] = None       # register-ABI return: 'A'|'X'|'Y'|'AY'


@dataclass
class Return(Node):
    value: Optional[Node]    # None => no return value (void)


@dataclass
class Defer(Node):
    """`defer stmt` -- run stmt just before each return path of the
    enclosing sub. Multiple defers run in LIFO order."""
    stmt: Node


@dataclass
class Program(Node):
    address: int = 0x4000       # default load address; %address overrides
    output_format: str = "raw"  # %output raw|prg|...
    target: str = "wendy2c"     # %target wendy2c|nmos
    subs: list[Sub] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    # Module-level variables collected by sema.
    module_vars: list[VarDecl] = field(default_factory=list)
    # Module-level enum declarations.
    enums: list[EnumDecl] = field(default_factory=list)
    # Module-level struct declarations + instances.
    structs: list[StructDecl] = field(default_factory=list)
    # All variables across the program (module + per-sub) with the
    # address sema assigned. Codegen emits `<mangled> = $XX` definitions
    # for each, then references them by name.
    all_vars: list["Symbol"] = field(default_factory=list)
    # Filled by sema during string lifting:
    strings: list[StrLit] = field(default_factory=list)


# ---- Symbol table ---------------------------------------------------------

@dataclass
class Symbol:
    name: str            # source name
    mangled: str         # codegen name
    type: Type
    kind: str            # 'sub', 'asmsub', 'extsub', 'var', 'const', 'string', 'builtin', 'array'
    # For asmsub/extsub: the address or label to call:
    asm_target: Optional[str] = None
    # For vars: the absolute address (we statically allocate from ZP).
    address: Optional[int] = None
    # For constants: the literal integer value.
    const_value: Optional[int] = None
    # For builtins, the callable that lowers them:
    lower_call: Optional[object] = None
