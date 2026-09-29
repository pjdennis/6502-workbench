"""On-target codegen equivalence test (Phase 7).

Builds `p1/p1.p8` (the self-hosting Prog8 compiler) with the host p8c +
vasm, runs it on the emulator over a corpus of `.p8` programs, and asserts
the `.s` assembly it writes is byte-identical to the host oracle
`python3 -m p8c source.p8 -o` -- the only normalization being the
`; source: <path>` comment line (exactly what the snapshot tests
normalize), since the on-target compiler has no host path to echo.

p1.p8 is a single-pass streaming compiler (lexer + shunting-yard expression
parser + frame-stack statement driver + node arena + a codegen back-end that
is a port of p8c/codegen.py). It is hand-maintained, upstream-Prog8 dialect.
See ../PHASE7_DESIGN.md.

Milestone P7-M1: `main { }` (nmos) -> prologue + ZP scratch bindings +
empty p8s_main + the nmos exit epilogue + reset vector.

SKIPs cleanly if vasm6502_oldstyle or the emulator binary are missing.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# firmware/vasm: vasm6502_oldstyle with the firmware include path.
FW_VASM = Path(__file__).resolve().parents[4] / "firmware" / "vasm"

HERE = Path(__file__).resolve().parent
P1 = HERE.parent
PROG8 = P1.parent
REPO = PROG8.parents[1]
EMU = REPO / "emulator" / "emulator.out"
P1_SRC = P1 / "p1.p8"
UPSTREAM = PROG8 / "upstream"
PROG8C_JAR = Path(os.environ.get("PROG8C", "/tmp/prog8c.jar"))
MKIMAGE = UPSTREAM / "mkimage.py"


def _have_prog8c() -> bool:
    return PROG8C_JAR.exists() and shutil.which("java") is not None


def build_p1_upstream(workdir: Path, src: Path = P1_SRC) -> Path:
    """Build a p1.p8-family source with the UPSTREAM prog8c (nmos target) and
    wrap it (mkimage) into a $0200..$FFFF emulator image. Returns the image
    path. This is the real wendy2 build path -- upstream's codegen is ~2.5x
    tighter than p8c+vasm, so the binary leaves room for the >256 peek/poke
    arena slabs that self-hosting needs (the p8c+vasm build reaches $EFC0 and
    has no room). A binary built by upstream emits byte-identical .s to one
    built by p8c+vasm: the monolith's codegen logic is independent of how the
    monolith itself was compiled."""
    raw = workdir / "p1.bin"
    img = workdir / "p1.img"
    r = subprocess.run(
        ["java", "-jar", str(PROG8C_JAR), "-target", "nmos.properties",
         "-out", str(workdir), str(src)],
        capture_output=True, text=True, cwd=str(UPSTREAM))
    assert r.returncode == 0, f"upstream prog8c failed:\n{r.stdout}\n{r.stderr}"
    assert raw.exists(), f"prog8c produced no binary:\n{r.stdout}\n{r.stderr}"
    r = subprocess.run(
        [sys.executable, str(MKIMAGE), str(raw), str(img)],
        capture_output=True, text=True)
    assert r.returncode == 0, f"mkimage failed:\n{r.stdout}\n{r.stderr}"
    return img


WENDY2_PROPS = "wendy2_selfhost.properties"  # 65c02, load $0200, memtop $C000
BOOT_SRC = REPO / "firmware" / "boards" / "wendy2" / "upload_and_run_eeprom_wendy2c.s"


def build_p1_wendy(workdir: Path, src: Path = P1_SRC):
    """Build the monolith for the wendy2c target (65c02, load $4000, memtop
    $F000) and assemble the wendy2c boot ROM. Returns (prog_bin, boot_rom).

    The program is a RAW binary at $4000 spanning into the one held-mapped
    bank ($8000-$EFFF); the emulator's --wendy2-prog preloads it directly into
    RAM (bank $01) and starts it, so the boot ROM is needed only for the reset
    vector. See WENDY2_MONOLITH_BANKING_PLAN.md."""
    prog_bin = workdir / "p1w.bin"
    r = subprocess.run(
        ["java", "-jar", str(PROG8C_JAR), "-target", WENDY2_PROPS,
         "-out", str(workdir), str(src)],
        capture_output=True, text=True, cwd=str(UPSTREAM))
    assert r.returncode == 0, f"wendy2 prog8c failed:\n{r.stdout}\n{r.stderr}"
    built = workdir / (src.stem + ".bin")
    assert built.exists(), f"wendy2 prog8c produced no binary:\n{r.stdout}\n{r.stderr}"
    if built != prog_bin:
        prog_bin.write_bytes(built.read_bytes())
    boot_rom = workdir / "boot.bin"
    r = subprocess.run(
        [str(FW_VASM), "-wdc02", "-wfail", "-Fbin", "-dotdir",
         "-ignore-mult-inc", "-esc", "-o", str(boot_rom), str(BOOT_SRC)],
        capture_output=True, text=True)
    assert r.returncode == 0, f"boot ROM vasm failed:\n{r.stdout}\n{r.stderr}"
    return prog_bin, boot_rom


_SOURCE_LINE = re.compile(r"^; source:.*$", re.MULTILINE)


def _norm(s: str) -> str:
    """Normalize the one location-dependent line (the `; source:` comment)."""
    return _SOURCE_LINE.sub("; source: SRC", s)


# P7-M1 corpus: empty `main { }` (nmos) at a few load addresses, exercising
# the prologue (incl. the .org address), the empty-main skeleton, the nmos
# exit epilogue, and the reset-vector trailer. The target is selected
# externally (the oracle passes `--target nmos`; the on-target p1 parser
# defaults to nmos/$0200) -- the source carries no `%target` directive.
M1_PROGRAMS = [
    '%address $0200\n%output raw\n%launcher none\nmain {\n\n  sub start() {\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\n\n  sub start() {\n  }\n}\n',                      # nmos default address -> $0200
    '%address $1000\n%output raw\n%launcher none\nmain {\n\n  sub start() {\n  }\n}\n',
    '%address $c000\n%output raw\n%launcher none\nmain {\n\n  sub start() {\n  }\n}\n',
]

# P7-M2 corpus: module scalar vars (ubyte / byte / uword, in various
# declaration orders) + simple assignment -- leaf RHS (`= literal`,
# `= var`), ubyte/uword widening on word stores, and byte augmented
# assignment (+= -= &= |= ^=) with a leaf operand. Exercises pass S
# (symbol table + ZP bump allocation), the ZP-binding block, and the
# byte/word leaf-expression + store codegen.
M2_PROGRAMS = [
    # all three scalar types, plain leaf assignment + widening
    '%output raw\n%launcher none\nmain {\n\nubyte x\nubyte y\nuword w\n\n  sub start() {\n    x = 1\n    y = x\n    w = $1234\n    w = x\n    w = y\n  }\n}\n',
    # byte type + augmented add of a var
    '%output raw\n%launcher none\nmain {\n\nbyte a\nbyte b\n\n  sub start() {\n    a = 5\n    b = a\n    a += b\n  }\n}\n',
    # every supported byte augmented op, literal + var operands
    '%output raw\n%launcher none\nmain {\n\nubyte x\nubyte y\n\n  sub start() {\n    x = $10\n    y = 2\n    x += 3\n    x -= 1\n    x += y\n    x -= y\n    x &= $0f\n    x |= y\n    x ^= 2\n  }\n}\n',
    # uword-only program (2-byte ZP slots), word leaf copy
    '%output raw\n%launcher none\nmain {\n\nuword p\nuword q\n\n  sub start() {\n    p = $beef\n    q = p\n  }\n}\n',
    # interleaved types -> non-trivial ZP addresses ($40 ub, $41 uw, $43 ub)
    '%output raw\n%launcher none\nmain {\n\nubyte a\nuword b\nubyte c\n\n  sub start() {\n    a = 1\n    b = a\n    c = 9\n  }\n}\n',
]

# Phase-7 "strings" slice (the p8c string-literal-as-data feature dogfooded
# by p1.p8 itself): a bare string literal assigned to a uword is its pool
# address. Exercises the ND_STR word-leaf codegen (lda #</ldy #> the label,
# numbered in encounter order) and the string-pool trailer (the _escape
# byte-list policy: printable runs, $XX for control / `"` / `\`, ", 0"
# terminator, "0" for the empty string), positioned between main and the
# reset vector.
M3_STR_PROGRAMS = [
    # one string
    '%output raw\n%launcher none\nmain {\n\nuword s\n\n  sub start() {\n    s = "hi"\n  }\n}\n',
    # several, in order; escapes (newline) and the empty string
    '%output raw\n%launcher none\nmain {\n\nuword s\nuword t\n\n  sub start() {\n    s = "hi"\n    t = "a\\nb"\n    s = ""\n  }\n}\n',
    # strings interleaved with scalar assignments (label order = encounter)
    '%output raw\n%launcher none\nmain {\n\nubyte x\nuword msg\n\n  sub start() {\n    x = 1\n    msg = "result: "\n    x += 2\n    msg = "done\\n"\n  }\n}\n',
    # every escape the pool emitter special-cases: \\ " \t \r plus a high byte
    '%output raw\n%launcher none\nmain {\n\nuword s\n\n  sub start() {\n    s = "tab\\there\\"q\\\\b\\r"\n  }\n}\n',
    # DUPLICATE strings dedup to one pool label: "x" appears 3x and "y" 2x,
    # interleaved with a unique "z". Labels: x=str_0, y=str_1, z=str_2 (each
    # distinct content interned once, in first-encounter order). Guards that
    # p8c's value-dedup and p1's intern_str_label agree.
    '%output raw\n%launcher none\nmain {\n\nuword s\n\n  sub start() {\n    s = "x"\n    s = "y"\n    s = "x"\n    s = "z"\n    s = "y"\n    s = "x"\n  }\n}\n',
]

# Phase-7 byte-expression slice: arithmetic / bitwise binops (+ - & | ^) in a
# byte assignment RHS, evaluated on p1's explicit work stack (p8c recurses;
# p1 can't). Covers the leaf-RHS fast path (left-nested chains a+b+c) and the
# generic CPU-stack spill path (a non-leaf RHS, e.g. b + (c + d)), which must
# match the host's dual-scratch-safe sequence (pha / sta __p8c_tmp1 / pla).
# Augmented assignment now shares the same binop emitter.
M3_EXPR_PROGRAMS = [
    # flat leaf op leaf, every supported op, literal + var operands
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte c\n\n  sub start() {\n    a = b + 1\n    a = b + c\n    a = b - c\n    a = b & c\n    a = b | 3\n    a = b ^ c\n  }\n}\n',
    # left-nested chains (leaf-RHS fast path, no spill)
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte c\nubyte d\n\n  sub start() {\n    a = b + c + a\n    a = b + c - d\n    a = ((b | c) & d) ^ a\n  }\n}\n',
    # right-nested / parenthesized RHS (generic spill path)
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte c\nubyte d\n\n  sub start() {\n    a = (b + c) - (a + 1)\n    a = b + (c + (d + 1))\n    a = (b - c) + (d - 1)\n  }\n}\n',
    # augmented assignment shares the binop emitter
    '%output raw\n%launcher none\nmain {\nubyte x\nubyte y\n\n  sub start() {\n    x = $10\n    y = 2\n    x += 3\n    x -= y\n    x &= $0f\n    x |= y\n    x ^= 2\n  }\n}\n',
]

# Phase-7 byte mul + shift slice: `*` (via the __p8c_mul_u8 runtime helper,
# emitted between main and the string pool only when used) and the shifts
# `<< >>` -- immediate counts unroll to repeated asl/lsr, variable counts emit
# a runtime loop with a .Lshl_top_N / .Lshl_end_N label pair (the global label
# counter must match p8c's _label_id sequence). Exercises the leaf-RHS path,
# the generic spill path, the dual-scratch pattern, and augmented <<= / >>=.
M3_MULSHIFT_PROGRAMS = [
    # mul: leaf-RHS (literal + var) and the generic spill path
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte c\nubyte d\n\n  sub start() {\n    a = b * c\n    a = b * 3\n    a = (b + c) * d\n    a = d * (b + c)\n  }\n}\n',
    # shifts: immediate (unrolled) and variable (loop, label pairs) counts
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte c\nubyte d\n\n  sub start() {\n    a = b << 2\n    a = b >> 1\n    a = b << c\n    a = b >> d\n    a = b << 0\n  }\n}\n',
    # the dual-scratch pattern (two shift sub-expressions in one binop) +
    # variable-count shifts in a binop (two label pairs, sequential ids)
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte c\nubyte d\n\n  sub start() {\n    a = (b << 3) + (b << 1)\n    a = (b << c) - (b >> d)\n  }\n}\n',
    # augmented <<= / >>= (leaf + variable count) alongside mul
    '%output raw\n%launcher none\nmain {\nubyte x\nubyte y\n\n  sub start() {\n    x = $10\n    y = 2\n    x <<= 3\n    x >>= 1\n    x <<= y\n    x >>= y\n    y = x * x\n  }\n}\n',
]

# Phase-7 byte unary slice: ~ (eor #$ff), - (two's complement: eor #$ff / clc /
# adc #$01). Integrated into the work-stack as a post-operand "apply" task, so
# the operand may itself be a nested expression (~(b+c), -(b*c), ~b+c). (`not`
# is also ported but needs a bool operand -- not reachable until comparisons
# land, so it is not in this corpus.)
M3_UNARY_PROGRAMS = [
    # ~ and - on a leaf operand
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\n\n  sub start() {\n    a = ~b\n    a = -b\n  }\n}\n',
    # operand is a nested expression (the work-stack handles the recursion)
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte c\n\n  sub start() {\n    a = ~(b + c)\n    a = -(b * c)\n    a = ~b + c\n  }\n}\n',
    # nested unary + unary mixed with mul/shift
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte c\n\n  sub start() {\n    a = - -b\n    a = ~b * c\n    a = -(b << 2)\n  }\n}\n',
]

# Phase-7 byte comparison slice: == != < <= > >= producing a 0/1 byte value
# (assigned to a ubyte), with the full unsigned branch sequences (incl. the
# extra .Lgt_no_N label for `>`) and the signed paths (SBC + overflow-corrected
# N flag, with .Lsgn_ok_N / .Lsgt_no_N). Signedness comes from BOTH leaf
# operands being the BYTE type (resolved via the symbol table). Also exercises
# `not` of a comparison (now that comparisons produce the bool `not` consumes)
# and a comparison with a nested (non-leaf) operand. Each label pair is
# allocated after the operands evaluate, matching p8c's _label_id order.
M3_CMP_PROGRAMS = [
    # unsigned, every op, leaf operands (var/var and var/literal)
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte c\n\n  sub start() {\n    a = b == c\n    a = b != c\n    a = b < c\n    a = b <= c\n    a = b > c\n    a = b >= c\n    a = b < 5\n  }\n}\n',
    # signed (both operands byte) -- the SBC / overflow path
    '%output raw\n%launcher none\nmain {\nubyte a\nbyte s\nbyte t\n\n  sub start() {\n    a = s == t\n    a = s != t\n    a = s < t\n    a = s <= t\n    a = s > t\n    a = s >= t\n  }\n}\n',
    # not of a comparison (bool -> not) + nested (non-leaf) operand
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte c\n\n  sub start() {\n    a = not (b < c)\n    a = (b + 1) < c\n    a = b > (c - 1)\n  }\n}\n',
    # uword operands: p8c's comparison codegen evaluates operands as BYTES
    # (it compares only low bytes -- a p8c limitation; _emit_word_cmp_into_a
    # is unreachable for comparison-as-value), so the existing byte cmp path
    # already matches. Locks that equivalence in.
    '%output raw\n%launcher none\nmain {\nubyte a\nuword x\nuword y\n\n  sub start() {\n    a = x < y\n    a = x == y\n    a = x >= y\n  }\n}\n',
]

# Phase-7 byte logical slice: short-circuit `and` / `or` (port of
# _emit_logical_into_a -- the label pair allocated mid-evaluation, after the
# lhs, and consumed by the tail after the rhs; nesting via a LIFO label-id
# stack) and `xor` (bitwise on 0/1: eval lhs / pha / eval rhs / sta tmp0 / pla
# / eor __p8c_tmp0). Operands must be bool (p8c), so they are comparisons here;
# also exercises nested and/or and `not` of a logical.
M3_LOGICAL_PROGRAMS = [
    # and / or / xor, each over two comparison operands
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte c\nubyte d\n\n  sub start() {\n    a = (b < c) and (b > d)\n    a = (b < c) or (b > d)\n    a = (b == c) xor (c == d)\n  }\n}\n',
    # nested and/or (LIFO label-stack discipline) + mixed
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte c\nubyte d\n\n  sub start() {\n    a = (b < c) and (c < d) and (b != d)\n    a = (b < c) or ((c < d) and (b != d))\n  }\n}\n',
    # not of a logical
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte c\nubyte d\n\n  sub start() {\n    a = not ((b < c) and (c < d))\n  }\n}\n',
]

# Phase-7 @() memory + &name slice (8-bit memory ops):
#   * @(IntLit) read/write -> direct absolute lda/sta $XXXX.
#   * @(<word leaf>) read/write -> address into __p8c_ptr0, (ptr0),y indirect.
#   * &name (address-of) as a uword value: lda #< / ldy #> the mangled label.
# The address word expression routes through codegen_word_expr (leaves + &name
# for now; the full word evaluator is the 16-bit slice). @() may appear as a
# binop operand (a = @(p) + 1) since the read is a self-contained byte leaf.
M3_MEMAT_PROGRAMS = [
    # @() read: literal, uword-var, and &var addresses
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nuword p\n\n  sub start() {\n    a = @($d020)\n    a = @(p)\n    a = @(&b)\n  }\n}\n',
    # @() write: literal, uword-var, &var; literal and computed RHS
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nuword p\n\n  sub start() {\n    @($d020) = a\n    @(p) = a\n    @(&b) = 7\n    @(p) = a + 1\n  }\n}\n',
    # @() as a binop operand + &name assigned to a uword
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nuword p\n\n  sub start() {\n    a = @(p) + 1\n    p = &b\n    p = &a\n  }\n}\n',
]

# Phase-7 WORD arithmetic/bitwise slice (16-bit): uword + - & | ^ on the word
# work stack (port of _emit_word_operands + _emit_word_binop_into_ay). The LHS
# is held on the CPU stack across the RHS eval (so a RHS reusing the wtmp
# scratch can't clobber it), RHS lands in __p8c_wtmp0, then the op combines
# both bytes with carry (+/-) or per-byte (&|^). ubyte operands widen to uword.
# (Word unary ~/- is a faithful port but p8c's sema rejects it, so untested.)
M3_WORDARITH_PROGRAMS = [
    # each binop, var/var and var/ubyte (widening)
    '%output raw\n%launcher none\nmain {\nuword w\nuword x\nuword y\nubyte b\n\n  sub start() {\n    w = x + y\n    w = x - y\n    w = x & y\n    w = x | y\n    w = x ^ y\n    w = x + b\n  }\n}\n',
    # left-nested chains and parenthesized (nesting-safety of the CPU-stack LHS)
    '%output raw\n%launcher none\nmain {\nuword w\nuword x\nuword y\n\n  sub start() {\n    w = x + y + w\n    w = (x + y) - (w + 1)\n    w = x + (y - w)\n  }\n}\n',
    # word augmented assignment (synthetic binop: w op= e -> w = w op e)
    '%output raw\n%launcher none\nmain {\nuword w\nuword x\n\n  sub start() {\n    w = $1000\n    w += x\n    w -= 1\n    w &= x\n    w |= $00ff\n    w ^= x\n  }\n}\n',
]

# Phase-7 WORD shift slice (16-bit): uword << / >> (port of _emit_word_shl /
# _emit_word_shr). A constant count in [0,16] unrolls the asl/rol (resp.
# lsr/ror) step n&15 times (with the n>=8 "shift a whole byte" special case);
# a variable count stashes the lhs into __p8c_wtmp0 and loops with a
# .Lwshl_top_N / .Lwshl_end_N (resp. wshr) label pair. Includes augmented
# <<= / >>= (the synthetic word binop path).
M3_WORDSHIFT_PROGRAMS = [
    # constant counts: <8, ==8, >8, ==16 (n&15==0 -> no-op), for both directions
    '%output raw\n%launcher none\nmain {\nuword w\nuword x\n\n  sub start() {\n    w = x << 1\n    w = x << 3\n    w = x << 8\n    w = x << 9\n    w = x << 16\n    w = x >> 1\n    w = x >> 4\n    w = x >> 8\n    w = x >> 12\n  }\n}\n',
    # variable counts (loop) + a nested lhs
    '%output raw\n%launcher none\nmain {\nuword w\nuword x\nubyte n\n\n  sub start() {\n    w = x << n\n    w = x >> n\n    w = (x + 1) << 2\n  }\n}\n',
    # augmented word shifts (synthetic binop, const + variable)
    '%output raw\n%launcher none\nmain {\nuword w\nubyte n\n\n  sub start() {\n    w = $0100\n    w <<= 2\n    w >>= 1\n    w <<= n\n    w >>= n\n  }\n}\n',
]

# P7-M4 control flow: if / if-else / while + break / continue. Conditions emit
# the compare straight into a (long-safe, inverted-branch) branch -- byte
# unsigned + signed and the 16-bit word compare -- or, for a non-comparison
# cond, materialize 0/1 and branch on zero. The statement driver is a work
# stack (no recursion), so blocks nest arbitrarily.
M4_CONTROL_PROGRAMS = [
    # if (no else), every byte comparison op as the condition
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte c\n\n  sub start() {\n    if a == b {\n        c = 1\n    }\n    if a < b {\n        c = 2\n    }\n    if a >= b {\n        c = 3\n    }\n    if a > b {\n        c = 4\n    }\n    if a <= b {\n        c = 5\n    }\n    if a != b {\n        c = 6\n    }\n  }\n}\n',
    # if / else, signed-byte and uword conditions
    '%output raw\n%launcher none\nmain {\nubyte a\nbyte s\nbyte t\nuword x\nuword y\n\n  sub start() {\n    if s < t {\n        a = 1\n    } else {\n        a = 2\n    }\n    if x < y {\n        a = 3\n    } else {\n        a = 4\n    }\n  }\n}\n',
    # while + break + continue, and a non-comparison condition (a plain var)
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte c\n\n  sub start() {\n    while a < b {\n        a = a + 1\n        if a == c {\n            break\n        }\n        if a == 9 {\n            continue\n        }\n        b = b - 1\n    }\n    while c != 0 {\n        c = c - 1\n    }\n  }\n}\n',
    # nested if inside if/else inside while
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte c\n\n  sub start() {\n    while a > b {\n        if c != 0 {\n            if a == b {\n                a = 7\n            } else {\n                a = 8\n            }\n        }\n        a = a - 1\n    }\n  }\n}\n',
]

# P7-M4 repeat: forever (count 0 -> top/jmp/end) and counted (push count on the
# CPU stack, decrement per iteration via the rep_dec tail, exit at 0; break pops
# the saved counter first). Literal and variable counts, with break/continue.
M4_REPEAT_PROGRAMS = [
    # forever loop with a break
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\n\n  sub start() {\n    repeat {\n        a = a + 1\n        if a == b {\n            break\n        }\n    }\n  }\n}\n',
    # counted (literal) loop
    '%output raw\n%launcher none\nmain {\nubyte a\n\n  sub start() {\n    repeat 10 {\n        a = a + 1\n    }\n  }\n}\n',
    # counted (variable) loop with break + continue
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte n\n\n  sub start() {\n    repeat n {\n        b = b - 1\n        if b == 0 {\n            break\n        }\n        if b == a {\n            continue\n        }\n        a = a + 1\n    }\n  }\n}\n',
]

# P7-M4 for: `for v in lo to hi` (inclusive ubyte range; v is a pre-declared
# var). Init v=lo; compare against hi at for_cont; inc; loop. Literal range,
# variable range, computed hi (the tmp0/tmp1 spill path), break/continue.
M4_FOR_PROGRAMS = [
    # literal range
    '%output raw\n%launcher none\nmain {\nubyte i\nubyte s\n\n  sub start() {\n    for i in 0 to 9 {\n        s = s + i\n    }\n  }\n}\n',
    # variable range + break
    '%output raw\n%launcher none\nmain {\nubyte i\nubyte s\nubyte lo\nubyte hi\nubyte a\n\n  sub start() {\n    for i in lo to hi {\n        s = s + 1\n        if s == a {\n            break\n        }\n    }\n  }\n}\n',
    # computed hi (spill path) + continue
    '%output raw\n%launcher none\nmain {\nubyte i\nubyte s\nubyte hi\nubyte a\n\n  sub start() {\n    for i in 1 to (hi - 1) {\n        s = s + i\n        if i == 3 {\n            continue\n        }\n        a = a + 1\n    }\n  }\n}\n',
]

# P7-M4 when: `when expr { v -> body  v1,v2 -> body  else -> body }`. expr is
# evaluated once (byte -> tmp0, word -> wtmp0); each arm matches its value(s)
# and jumps to its body, else to the next arm; else arm runs on no match.
# Byte + word selectors, multi-value arms, with/without else, and an arm body
# with a nested if (the classify_name shape).
M4_WHEN_PROGRAMS = [
    # byte selector: single + multi-value arms + else
    '%output raw\n%launcher none\nmain {\nubyte x\nubyte r\n\n  sub start() {\n    when x {\n        1 -> { r = 10 }\n        2, 3 -> { r = 20 }\n        else -> { r = 99 }\n    }\n  }\n}\n',
    # byte selector, no else
    '%output raw\n%launcher none\nmain {\nubyte x\nubyte r\n\n  sub start() {\n    when x {\n        5 -> { r = 1 }\n        6 -> { r = 2 }\n    }\n  }\n}\n',
    # word selector (16-bit value compare) + multi-value + else
    '%output raw\n%launcher none\nmain {\nuword w\nuword wr\n\n  sub start() {\n    when w {\n        $1000 -> { wr = 1 }\n        $2000, $3000 -> { wr = 2 }\n        else -> { wr = 9 }\n    }\n  }\n}\n',
    # arm bodies with nested control flow
    '%output raw\n%launcher none\nmain {\nubyte x\nubyte a\nubyte b\nubyte r\n\n  sub start() {\n    when x {\n        1 -> { if a == b { r = 1 } else { r = 2 } }\n        2 -> { while a < b { a = a + 1 } }\n        else -> { r = 0 }\n    }\n  }\n}\n',
]

# P7-M5 subs (slice 1): regular void subs with no params/locals, called as
# statements. Exercises the sub table (register_subs), pass B emission of
# non-main subs in source order, the per-sub return label + rts, and the call
# (jsr p8s_<name>). Bodies use module vars + control flow.
M5_SUB_PROGRAMS = [
    # two subs called from main, bodies touch module vars
    '%output raw\n%launcher none\nmain {\nubyte x\nubyte y\n\nsub foo() {\n    x = 5\n}\nsub bar() {\n    y = x + 1\n}\n  sub start() {\n    foo()\n    bar()\n  }\n}\n',
    # a sub whose body has control flow + a call from inside a loop
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\n\nsub bump() {\n    if a < b {\n        a = a + 1\n    }\n}\n  sub start() {\n    a = 0\n    b = 5\n    while a < b {\n        bump()\n    }\n  }\n}\n',
    # subs in source order foo, baz, qux -- emission order must match
    '%output raw\n%launcher none\nmain {\nubyte x\n\nsub foo() {\n    x = 1\n}\nsub baz() {\n    x = x + 2\n}\nsub qux() {\n    x = x * 3\n}\n  sub start() {\n    foo()\n    baz()\n    qux()\n  }\n}\n',
    # string literals in subs declared BEFORE main: pool labels must be
    # numbered in main-first EMISSION order (main's "M"=str_0, then first's
    # "F"=str_1, second's "S"=str_2), not source order. Regression guard
    # for the p8c/p1 string-label ordering divergence.
    '%output raw\n%launcher none\nmain {\nuword s\n\nsub first() {\n    s = "F"\n}\nsub second() {\n    s = "S"\n}\n  sub start() {\n    s = "M"\n    first()\n    second()\n  }\n}\n',
]

# P7 const slice: `const ubyte/uword NAME = <int>` declares a compile-time
# constant -- no ZP binding, no storage; every use site folds in the literal
# value (p8c does this in its Ident codegen; p1 mirrors it). Folding happens
# only where p8c folds: byte-leaf load (`x = C`), word-leaf load (`w = C`,
# ubyte const widened), and the comparison SPILL path (`if x == C` -> p8c's
# _cmp_leaf_operand returns None for a const, so it spills and folds during the
# full byte-expr eval). p8c does NOT fold a const in arithmetic operands or a
# for-bound (it emits the undefined mangled name there -- a p8c limitation), so
# this corpus avoids those, matching what p1.p8 itself can use.
CONST_PROGRAMS = [
    # byte-leaf + word-leaf folding, no ZP binding for the consts
    '%output raw\n%launcher none\nmain {\nconst ubyte LO = 5\nconst ubyte HI = 200\nubyte a\nuword w\n\n  sub start() {\n    a = LO\n    w = HI\n    a = HI\n  }\n}\n',
    # const in comparison conditions (if / while -> spill path folds the const)
    '%output raw\n%launcher none\nmain {\nconst ubyte K = 7\nubyte a\n\n  sub start() {\n    a = 0\n    if a == K {\n        a = K\n    }\n    while a == K {\n        a = K\n    }\n  }\n}\n',
    # const passed as a call arg (folds via the arg's byte/word leaf eval)
    '%output raw\n%launcher none\nmain {\nconst ubyte N = 42\nubyte a\n\nsub id(ubyte v) -> ubyte {\n    return v\n}\n  sub start() {\n    a = id(N)\n  }\n}\n',
    # a program whose ONLY module symbols are consts -> no ZP-binding block
    '%output raw\n%launcher none\nmain {\nconst ubyte A = 1\nconst ubyte B = 2\n\n  sub start() {\n    if A == B {\n    }\n  }\n}\n',
]

# P7 array DECLARATION slice: `ubyte[N] / uword[N] name` reserves a labeled
# `.byte 0,...` storage block (p8a_<name>, count*esize bytes) in the arrays
# trailer (between the mul helper and the string pool), with NO ZP binding.
# (Element INDEXING -- ND_INDEX read/store -- is not folded in yet; it needs
# low-window headroom this build does not have, so this corpus declares arrays
# but does not index them, which is byte-identical to p8c.)
ARRAY_DECL_PROGRAMS = [
    # ubyte + uword arrays interleaved with scalars: trailer order = source
    # order, scalars still get ZP bindings, arrays do not.
    '%output raw\n%launcher none\nmain {\nubyte[4] buf\nubyte x\nuword[3] tab\n\n  sub start() {\n    x = 1\n  }\n}\n',
    # an array as the only module symbol -> ZP-binding block omitted, trailer
    # present.
    '%output raw\n%launcher none\nmain {\nubyte[8] mem\n\n  sub start() {\n  }\n}\n',
]

# P7 array READ slice (ubyte fast `,y` path, matching p8c _array_fast_byte):
# const index -> `lda arr+N`; simple byte-var index -> `lda idx / tay /
# lda arr,y`. (Element STORE, uword arrays, >256 elems, and uword/complex
# indices are not folded in yet -- they need low-window headroom this build
# does not have.) So these read only, with const and byte-var indices.
ARRAY_READ_PROGRAMS = [
    # const index (absolute) and byte-var index (tay / ,y), plus a read feeding
    # an arithmetic op (the read is the leaf of `buf[i] + 1`).
    '%output raw\n%launcher none\nmain {\nubyte[8] buf\nubyte i\nubyte x\n\n  sub start() {\n    i = 3\n    x = buf[2]\n    x = buf[i]\n    x = buf[i] + 1\n  }\n}\n',
]

# P7-M5 subs (slice 2): return values + call-as-value (still no params/locals).
# `return [v]` evaluates v (byte -> A, word -> A:Y) with p8c's pha/pla dance,
# then jmps the per-sub .Lp8s_<name>_ret label; a call in an expression leaves
# its result in A (byte) or A:Y (word, ubyte-returning calls widen with ldy #0).
M5_RET_PROGRAMS = [
    # byte + word returns, call as a value (byte and word context)
    '%output raw\n%launcher none\nmain {\nubyte a\nuword w\n\nsub get5() -> ubyte {\n    return 5\n}\nsub dbl() -> ubyte {\n    return a + a\n}\nsub bigw() -> uword {\n    return $1234\n}\n  sub start() {\n    a = get5()\n    a = dbl() + 1\n    w = bigw()\n    w = get5()\n  }\n}\n',
    # conditional return (return inside an if, plus a fall-through return)
    '%output raw\n%launcher none\nmain {\nubyte a\n\nsub cls() -> ubyte {\n    if a > 3 {\n        return 1\n    }\n    return 0\n}\n  sub start() {\n    a = cls()\n  }\n}\n',
    # void sub with a bare `return` (early exit)
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\n\nsub maybe() {\n    if a == 0 {\n        return\n    }\n    b = b + 1\n}\n  sub start() {\n    maybe()\n  }\n}\n',
]

# P7-M5 subs (slice 3): params + call-with-args. Pass S now allocates each
# sub's params (p8v_<sub>_arg_<name>) in source order, continuing the ZP bump
# after module vars; the symbol table is scope-aware (a sub's params shadow
# module vars). A call evaluates each arg onto the CPU stack, then pops them
# into the param slots in reverse before the jsr (the reentrant-safe order).
M5_PARAM_PROGRAMS = [
    # one ubyte param, used in the body + returned
    '%output raw\n%launcher none\nmain {\nubyte g\n\nsub addone(ubyte v) -> ubyte {\n    return v + 1\n}\n  sub start() {\n    g = addone(5)\n  }\n}\n',
    # two ubyte params + a uword param
    '%output raw\n%launcher none\nmain {\nubyte g\nuword gw\n\nsub store2(ubyte a, ubyte b) {\n    g = a + b\n}\nsub setw(uword w) {\n    gw = w\n}\n  sub start() {\n    store2(3, 4)\n    setw($abcd)\n  }\n}\n',
    # three params, arg is an expression / a module var (shadowing check)
    '%output raw\n%launcher none\nmain {\nubyte g\n\nsub add3(ubyte a, ubyte b, ubyte c) -> ubyte {\n    return a + b + c\n}\n  sub start() {\n    g = add3(1, 2, g)\n  }\n}\n',
]

# P7-M5 subs (slice 4): local variables. Pass S walks each sub body in p8c's
# _walk_block order (depth-first, source order, recursing into if/while/for/
# repeat/when bodies) and allocates each local (p8v_<sub>_<name>) continuing
# the ZP bump after the sub's params. A local declaration with an initializer
# lowers to a store; locals (and params) shadow module vars by scope.
M5_LOCAL_PROGRAMS = [
    # top-level locals in main + a sub, init + use
    '%output raw\n%launcher none\nmain {\nubyte g\n\nsub twice(ubyte v) -> ubyte {\n    ubyte r\n    r = v + v\n    return r\n}\n  sub start() {\n    ubyte x\n    x = 3\n    g = twice(x)\n  }\n}\n',
    # a local loop var + a local accumulator (for-loop body)
    '%output raw\n%launcher none\nmain {\nubyte g\n\nsub compute(ubyte n) -> ubyte {\n    ubyte sum\n    sum = 0\n    ubyte i\n    for i in 0 to n {\n        sum = sum + i\n    }\n    return sum\n}\n  sub start() {\n    g = compute(5)\n  }\n}\n',
    # locals declared INSIDE nested blocks (if / while) -- allocation order
    '%output raw\n%launcher none\nmain {\nubyte g\nuword gw\n\nsub nested() {\n    ubyte a\n    a = 1\n    if g > 0 {\n        ubyte b\n        b = a + g\n        while b > 0 {\n            uword w\n            w = gw + 1\n            gw = w\n            b = b - 1\n        }\n    }\n    g = a\n}\n  sub start() {\n    nested()\n  }\n}\n',
]

# P7-M5 builtins: lsb / msb (uword -> ubyte), peek / poke (literal address),
# mkword (msb,lsb -> uword). Lowered to inline asm, not a jsr. Includes nested
# builtins in another's argument (exercises the reentrancy-safe bi_cn stack)
# and ubyte-result widening in word context.
M5_BUILTIN_PROGRAMS = [
    # lsb / msb / peek / poke / mkword, plain
    '%output raw\n%launcher none\nmain {\nubyte b\nuword w\n\n  sub start() {\n    w = $1234\n    b = lsb(w)\n    b = msb(w)\n    b = peek($d020)\n    poke($d021, b)\n    w = mkword($ab, $cd)\n  }\n}\n',
    # nested builtins (poke value + mkword arg contain lsb) -- reentrancy
    '%output raw\n%launcher none\nmain {\nubyte b\nuword w\n\n  sub start() {\n    w = $beef\n    poke($c000, lsb(w) + 1)\n    w = mkword(msb(w), lsb(w))\n  }\n}\n',
    # lsb in word context (ubyte result widens with ldy #0)
    '%output raw\n%launcher none\nmain {\nuword w\nuword v\n\n  sub start() {\n    v = $0102\n    w = lsb(v)\n    w = mkword($00, msb(v))\n  }\n}\n',
]


# Type casts (`expr as TYPE`): byte<->word narrowing/widening in byte and word
# context, casts of leaves and of compound (word-typed) expressions, and casts
# nested inside larger expressions. Byte-identical to p8c (the cast selects the
# operand-evaluation width; a uword->ubyte cast keeps the low byte, high = 0).
CAST_PROGRAMS = [
    '%output raw\n%launcher none\nmain {\nubyte x\nuword w\n  sub start() {\n    w = 300\n    x = w as ubyte\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte x\nuword w\n  sub start() {\n    x = 5\n    w = x as uword\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte x\nubyte y\nuword w\n  sub start() {\n    w = (x + y) as uword\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte x\nuword w\nuword v\n  sub start() {\n    x = (w + v) as ubyte\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte x\nuword v\nuword w\n  sub start() {\n    w = v + (x as uword)\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte x\nuword w\n  sub start() {\n    x = (w as ubyte) + 1\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte x\nuword v\n  sub start() {\n    v = (x as uword) << 2\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte x\nuword w\nuword v\n  sub start() {\n    x = (w + v + 5) as ubyte\n  }\n}\n',
]


# Array-element assignment (`arr[i] = rhs`): ubyte[] (const / byte-var /
# byte-expr / uword index) and uword[] (split lo/hi) stores. Byte-identical to
# p8c (the fast `,y` path, absolute for a const index, and the parked-rhs
# byte-index path).
ARRAY_STORE_PROGRAMS = [
    '%output raw\n%launcher none\nmain {\nubyte[8] arr\nubyte i\nubyte x\n  sub start() {\n    arr[3] = 9\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte[8] arr\nubyte i\nubyte x\n  sub start() {\n    arr[i] = x\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte[8] arr\nubyte i\nubyte x\n  sub start() {\n    arr[i] = x + 1\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte[8] arr\nubyte i\nubyte x\n  sub start() {\n    arr[i + 1] = x\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nuword[6] warr\nubyte i\nuword w\n  sub start() {\n    warr[2] = w\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nuword[6] warr\nubyte i\nuword w\n  sub start() {\n    warr[i] = w\n  }\n}\n',
]


# Word-context and uword[] array reads: uword[] element -> A:Y (split lo/hi),
# ubyte[] widened to uword, const/byte-var/expr/uword indices, reads inside
# larger expressions, and a uword[] element narrowed via an explicit cast.
ARRAY_READ_WORD_PROGRAMS = [
    '%output raw\n%launcher none\nmain {\nuword[6] warr\nubyte i\nuword w\n  sub start() {\n    w = warr[i]\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte[8] arr\nubyte i\nuword w\n  sub start() {\n    w = arr[i]\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nuword[6] warr\nuword w\n  sub start() {\n    w = warr[2]\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nuword[6] warr\nubyte i\nuword w\n  sub start() {\n    w = warr[i + 1]\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte[8] arr\nuword[6] warr\nubyte i\nuword w\n  sub start() {\n    w = arr[i] + warr[2]\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nuword[6] warr\nubyte i\nubyte x\n  sub start() {\n    x = warr[i] as ubyte\n  }\n}\n',
]


# Byte augmented assignment with a non-leaf RHS (array read / nested expr):
# p8c emits `lda lhs` then, for a non-leaf RHS, evaluates it to __p8c_tmp0,
# reloads lhs, and combines (the first `lda lhs` is dead). Leaf RHS applies in
# place. Byte-identical to p8c.
AUG_NONLEAF_PROGRAMS = [
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte[8] arr\n  sub start() {\n    a += arr[b]\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte[8] arr\n  sub start() {\n    a -= arr[b]\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte[8] arr\n  sub start() {\n    a |= arr[b]\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte[8] arr\n  sub start() {\n    a ^= arr[b]\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte[8] arr\n  sub start() {\n    a += arr[b] + 1\n  }\n}\n',
]


# Compound conditions (`and`/`or`/`not` short-circuit) in if/while: per-operand
# branching (no 0/1 materialized), with byte and word comparison leaves, nested
# and-chains, or with else, and the and_skip/or_skip labels. Byte-identical to
# p8c's _emit_cond_branch.
COMPOUND_COND_PROGRAMS = [
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte c\nubyte d\n  sub start() {\n    if a > b and c < d { a = 1 }\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\n  sub start() {\n    if a == 1 or b == 2 { a = 1 }\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte c\n  sub start() {\n    if a > 0 and b > 0 and c > 0 { a = 1 }\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\n  sub start() {\n    while a > 0 and b < 10 { a = a - 1 }\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\nubyte c\nubyte d\n  sub start() {\n    if (a > b) or (c == d) { a = 1 } else { a = 2 }\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nuword w\nuword v\nubyte a\nubyte b\n  sub start() {\n    if w > v and a > b { a = 1 }\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\n  sub start() {\n    if not (a == b) { a = 1 }\n  }\n}\n',
]


# peek()/poke() with a computed (non-literal) address: the address is parked
# in __p8c_aptr and accessed via (aptr),y (literal addresses still use the
# direct lda/sta $XXXX). Byte-identical to p8c.
PEEK_POKE_PROGRAMS = [
    '%output raw\n%launcher none\nmain {\nubyte a\nuword w\n  sub start() {\n    a = peek(w)\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte a\nuword w\n  sub start() {\n    poke(w, a)\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte a\nuword w\n  sub start() {\n    a = peek(w + 1)\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte a\nuword w\n  sub start() {\n    poke(w + 1, a)\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte a\n  sub start() {\n    a = peek($d020)\n    poke($d020, a)\n  }\n}\n',
    # peekw / pokew (uword via aptr): read into A:Y, write lo/hi.
    '%output raw\n%launcher none\nmain {\nuword w\nuword v\n  sub start() {\n    w = peekw(v)\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nuword w\nuword v\n  sub start() {\n    pokew(w, v)\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nuword w\nuword v\n  sub start() {\n    w = peekw(v + 2)\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nuword w\nuword v\n  sub start() {\n    pokew(w + 2, v)\n  }\n}\n',
]


# inline `%asm {{ ... }}` blocks: the lexer captures the raw body, normalizes
# each line (strip + join with '\n') into a string, and codegen re-emits each
# line with a 2-space indent -- a port of p8c's InlineAsm. Byte-identical.
INLINE_ASM_PROGRAMS = [
    '%output raw\n%launcher none\nmain {\n  sub start() {\n    %asm {{\n    nop\n    }}\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\n  sub start() {\n    %asm {{\n    lda #$01\n    clc\n    adc #$02\n    sta $d021\n    }}\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\nubyte a\n  sub start() {\n    a = 1\n    %asm {{\n    lda #$05\n    sta $d020\n    }}\n    a = 2\n  }\n}\n',
    '%output raw\n%launcher none\nmain {\n  sub start() {\n    %asm {{\nloop:\n    dex\n    bne loop\n    }}\n  }\n}\n',
]


# asmsub / extsub with register-ABI params (@A/@X/@Y/@AY). extsub is a pure
# `jsr $ADDR` decl; an asmsub-body emits a `p8s_<name>:` label + raw %asm. The
# call ABI loads X/Y-bound args first, then the A/AY-bound arg (so the
# A-evaluator can't clobber an already-loaded X/Y), then jsr. Register-bound
# params get no ZP/main storage. Byte-identical to p8c. (Placed inside `main`,
# as upstream requires -- p1.p8's own syscall asmsubs sit inside its main too.)
ASMSUB_PROGRAMS = [
    # extsub decl + register-ABI call (ubyte @A)
    '%output raw\n%launcher none\nmain {\n  extsub $F00F = sx(ubyte c @A)\n  sub start() {\n    ubyte x\n    x = 7\n    sx(x)\n  }\n}\n',
    # asmsub-body, ubyte @A -> ubyte @A, used as an expression
    '%output raw\n%launcher none\nmain {\n  asmsub dbl(ubyte v @A) -> ubyte @A {\n    %asm {{\n    asl  a\n    rts\n    }}\n  }\n  sub start() {\n    ubyte x\n    x = dbl(21)\n  }\n}\n',
    # multi-arg: @A + @X ordering (X loaded first, A last)
    '%output raw\n%launcher none\nmain {\n  asmsub wr(ubyte b @A, ubyte h @X) {\n    %asm {{\n    sta $d020\n    rts\n    }}\n  }\n  sub start() {\n    wr(5, 2)\n  }\n}\n',
    # @A + @Y ordering
    '%output raw\n%launcher none\nmain {\n  asmsub pp(ubyte a @A, ubyte i @Y) {\n    %asm {{\n    sta $1000,y\n    rts\n    }}\n  }\n  sub start() {\n    pp(7, 3)\n  }\n}\n',
    # extsub taking a uword @AY arg, returning ubyte @A
    '%output raw\n%launcher none\nmain {\n  extsub $F012 = op(uword fn @AY) -> ubyte @A\n  sub start() {\n    uword w\n    ubyte h\n    w = $1234\n    h = op(w)\n  }\n}\n',
    # asmsub returning uword @AY
    '%output raw\n%launcher none\nmain {\n  asmsub gw(ubyte i @A) -> uword @AY {\n    %asm {{\n    tay\n    lda #$00\n    rts\n    }}\n  }\n  sub start() {\n    uword w\n    w = gw(4)\n  }\n}\n',
]


def _have_vasm() -> bool:
    return shutil.which("vasm6502_oldstyle") is not None


@unittest.skipUnless(_have_prog8c(), f"upstream prog8c not found at {PROG8C_JAR}")
@unittest.skipUnless(_have_vasm(), "vasm6502_oldstyle not on PATH")
@unittest.skipUnless(EMU.exists(), f"emulator not built at {EMU}")
class P1Equivalence(unittest.TestCase):
    """Codegen-equivalence corpus: the p1.p8 monolith (single-pass parse +
    codegen), built for the wendy2c MACHINE (65c02, banking) and run on the
    wendy2c emulator -- reading source / writing output over the simulated
    $F800 disk with the upper-window RAM bank held mapped -- must reproduce
    p8c's `.s` byte-for-byte for each corpus program.

    The monolith parses the upstream-strict `main { sub start() {...} }` form
    (descend into the namespace, `start` is the SUBK_MAIN entry) -- the same
    one dialect as p8c and the _sh pipeline. It is the fuller reference: unlike
    the _sh pass2, it emits p8c's signed-`byte`/`word` compare arm, so the
    signed corpus programs are checked here too.

    The monolith's file I/O is the inline $F800 disk ABI (no %import), which
    only exists on the wendy2c machine, so the corpus runs there -- the same
    machine the banked self-host targets. The emitted .s is machine-independent
    (the monolith always emits nmos-target asm). See
    WENDY2_MONOLITH_BANKING_PLAN.md.
    """

    CAP = "2000000000"

    @classmethod
    def setUpClass(cls):
        cls.workdir = Path(tempfile.mkdtemp(prefix="p1_codegen_"))
        cls.prog_bin, cls.boot_rom = build_p1_wendy(cls.workdir)
        cls.disk = cls.workdir / "disk"
        cls.disk.mkdir()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.workdir, ignore_errors=True)

    def _oracle(self, src: str) -> str:
        inp = self.workdir / "oin.p8"
        out = self.workdir / "oracle.s"
        inp.write_text(src)
        r = subprocess.run(
            [sys.executable, "-m", "p8c", "--target", "nmos",
             str(inp), "-o", str(out)],
            capture_output=True, text=True, cwd=str(PROG8))
        self.assertEqual(r.returncode, 0,
                         msg=f"oracle failed on {src!r}:\n{r.stdout}\n{r.stderr}")
        return _norm(out.read_text())

    def _run_wendy(self, src: str):
        """Run the wendy2c monolith on `src` (staged as in.p8); return
        (out_text_or_None, completed_process)."""
        (self.disk / "in.p8").write_text(src)
        out = self.disk / "out.s"
        if out.exists():
            out.unlink()
        r = subprocess.run(
            [str(EMU), str(self.boot_rom), "--machine", "wendy2c",
             "--wendy2-prog", str(self.prog_bin), "--load", "0200",
             "--disk", str(self.disk), "--cycle-cap", self.CAP],
            capture_output=True, text=True)
        return (out.read_text() if out.exists() else None), r

    def _ontarget(self, src: str) -> str:
        text, r = self._run_wendy(src)
        self.assertIsNotNone(text,
                             msg=f"wendy2 p1 produced no out.s on {src!r}:\n"
                                 f"{r.stdout}\n{r.stderr}")
        return _norm(text)

    def _equiv(self, src: str) -> None:
        self.assertEqual(self._oracle(src), self._ontarget(src),
                         msg=f"codegen .s differs for {src!r}")

    def test_lenient_main_rejected(self):
        # The non-upstream `main { <statements> }` form (no `sub start()`) is
        # rejected -- the monolith bails (sys_exit) before emitting any asm,
        # mirroring p8c's ParseError -- not mis-compiled. (out.s is created
        # empty because it is opened before the parse, so check it stays empty.)
        text, r = self._run_wendy("ubyte a\nmain {\n    a = 5\n}\n")
        self.assertFalse(text,
                         msg="lenient `main { <stmts> }` should emit no asm "
                             f"(out.s empty/absent):\n{r.stdout}\n{r.stderr}")

    def test_m1_programs(self):
        for src in M1_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_m2_programs(self):
        for src in M2_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_m3_str_programs(self):
        for src in M3_STR_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_m3_expr_programs(self):
        for src in M3_EXPR_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_m3_mulshift_programs(self):
        for src in M3_MULSHIFT_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_m3_unary_programs(self):
        for src in M3_UNARY_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_m3_cmp_programs(self):
        for src in M3_CMP_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_m3_logical_programs(self):
        for src in M3_LOGICAL_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_m3_memat_programs(self):
        for src in M3_MEMAT_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_m3_wordarith_programs(self):
        for src in M3_WORDARITH_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_m3_wordshift_programs(self):
        for src in M3_WORDSHIFT_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_m4_control_programs(self):
        for src in M4_CONTROL_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_m4_repeat_programs(self):
        for src in M4_REPEAT_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_m4_for_programs(self):
        for src in M4_FOR_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_m4_when_programs(self):
        for src in M4_WHEN_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_m5_sub_programs(self):
        for src in M5_SUB_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_const_programs(self):
        for src in CONST_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_array_decl_programs(self):
        for src in ARRAY_DECL_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_array_read_programs(self):
        for src in ARRAY_READ_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_m5_ret_programs(self):
        for src in M5_RET_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_cast_programs(self):
        for src in CAST_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_array_store_programs(self):
        for src in ARRAY_STORE_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_array_read_word_programs(self):
        for src in ARRAY_READ_WORD_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_aug_nonleaf_programs(self):
        for src in AUG_NONLEAF_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_compound_cond_programs(self):
        for src in COMPOUND_COND_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_peek_poke_programs(self):
        for src in PEEK_POKE_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_inline_asm_programs(self):
        for src in INLINE_ASM_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_asmsub_programs(self):
        for src in ASMSUB_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_m5_param_programs(self):
        for src in M5_PARAM_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_m5_local_programs(self):
        for src in M5_LOCAL_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)

    def test_m5_builtin_programs(self):
        for src in M5_BUILTIN_PROGRAMS:
            with self.subTest(src=src):
                self._equiv(src)


PASS1_SRC = P1 / "p1_pass1_sh.p8"
PASS2_SRC = P1 / "p1_pass2_sh.p8"


@unittest.skipUnless(_have_vasm(), "vasm6502_oldstyle not on PATH")
@unittest.skipUnless(EMU.exists(), f"emulator not built at {EMU}")
class P1SelfHost(unittest.TestCase):
    """The strict self-host test: the two-pass on-target pipeline
    (p1_pass1_sh.p8 parse+symbols+AST-dump, then p1_pass2_sh.p8
    AST-load+codegen), built with p8c+vasm and run on the emulator, compiles
    its OWN two source files to assembly byte-identical to `p8c -o`.

    (The pipeline is sized for its own two passes -- NOT for the p1.p8 monolith,
    which combines both passes' globals and overflows the on-target symbol
    arrays. That is the whole reason the compiler was split into two passes;
    p1.p8 is exercised only as a host-p8c compilation, by the corpus tests.)

    The only normalization is the `; source:` comment line (_norm), exactly
    as the snapshot/equivalence tests do: the on-target compiler echoes the
    `SRC` placeholder while host p8c echoes the resolved absolute path.
    """

    @classmethod
    def _build(cls, src: Path, name: str) -> Path:
        s_path = cls.workdir / f"{name}.s"
        bin_path = cls.workdir / f"{name}.bin"
        r = subprocess.run(
            [sys.executable, "-m", "p8c", "--target", "nmos",
             str(src), "-o", str(s_path)],
            capture_output=True, text=True, cwd=str(PROG8))
        assert r.returncode == 0, f"p8c {name} failed:\n{r.stdout}\n{r.stderr}"
        r = subprocess.run(
            [str(FW_VASM), "-Fbin", "-dotdir", "-ignore-mult-inc",
             "-esc", "-wfail", "-o", str(bin_path), str(s_path)],
            capture_output=True, text=True)
        assert r.returncode == 0, f"vasm {name} failed:\n{r.stdout}\n{r.stderr}"
        return bin_path

    @classmethod
    def setUpClass(cls):
        cls.workdir = Path(tempfile.mkdtemp(prefix="p1_selfhost_"))
        cls.pass1_bin = cls._build(PASS1_SRC, "pass1")
        cls.pass2_bin = cls._build(PASS2_SRC, "pass2")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.workdir, ignore_errors=True)

    def _assert_self_hosts(self, src: Path, name: str):
        dump = self.workdir / f"{name}.dump"
        out = self.workdir / f"{name}.pipeline.s"
        # pass 1: parse + build symbols + dump the AST (binary).
        r = subprocess.run(
            [str(EMU), str(self.pass1_bin), "--cycle-cap", "30000000000",
             str(src), str(dump)],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0,
                         msg=f"pass1 failed on {name}:\n{r.stdout}\n{r.stderr}")
        # pass 2: load the AST + codegen the .s.
        r = subprocess.run(
            [str(EMU), str(self.pass2_bin), "--cycle-cap", "30000000000",
             "--no-dump", str(dump), str(out)],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0,
                         msg=f"pass2 failed on {name}:\n{r.stdout}\n{r.stderr}")
        # oracle: host p8c compiling the same source.
        oracle = self.workdir / f"{name}.oracle.s"
        r = subprocess.run(
            [sys.executable, "-m", "p8c", "--target", "nmos",
             str(src), "-o", str(oracle)],
            capture_output=True, text=True, cwd=str(PROG8))
        self.assertEqual(r.returncode, 0,
                         msg=f"oracle failed on {name}:\n{r.stdout}\n{r.stderr}")
        self.assertEqual(_norm(out.read_text()), _norm(oracle.read_text()),
                         msg=f"self-host pipeline output diverged from p8c on "
                             f"{name} (see RESUME_NOTES.md self-host section)")

    def test_pass1_self_hosts(self):
        self._assert_self_hosts(PASS1_SRC, "p1_pass1_sh")

    def test_pass2_self_hosts(self):
        self._assert_self_hosts(PASS2_SRC, "p1_pass2_sh")


@unittest.skipUnless(os.environ.get("P1_WENDY_SELFHOST"),
                     "slow (~18 min): set P1_WENDY_SELFHOST=1 to run")
@unittest.skipUnless(_have_prog8c(), f"upstream prog8c not found at {PROG8C_JAR}")
@unittest.skipUnless(_have_vasm(), "vasm6502_oldstyle not on PATH")
@unittest.skipUnless(EMU.exists(), f"emulator not built at {EMU}")
class P1WendySelfHost(unittest.TestCase):
    """The BANKED MONOLITH self-host: p1.p8 built for the wendy2c machine
    (65c02, multi-bank) and run on the wendy2c emulator compiles its OWN source
    (p1.p8) -- reading it from the simulated $F800 disk, holding the sym/node/
    cons arenas in a second RAM bank (logical bank 1) reached via the fixed-RAM
    $F810/$F830/$F850/$F870 accessor -- and emits assembly byte-for-byte
    identical to the host p8c oracle's compilation of the same p1.p8.

    This is the single-binary banked compiler self-hosting. It is SLOW (~18 min:
    the on-target compiler's O(n^2) identifier/string interning over its own
    ~6300-line source at the emulator's ~10 MHz 65c02 rate, ~11 G cycles), so it
    is gated behind P1_WENDY_SELFHOST. See WENDY2_MONOLITH_BANKING_PLAN.md (M5).
    """

    @classmethod
    def setUpClass(cls):
        cls.workdir = Path(tempfile.mkdtemp(prefix="p1_wselfhost_"))
        cls.prog_bin, cls.boot_rom = build_p1_wendy(cls.workdir)
        cls.disk = cls.workdir / "disk"
        cls.disk.mkdir()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.workdir, ignore_errors=True)

    def test_monolith_self_hosts(self):
        # stage p1.p8 itself as the fixed input name the wendy2 compiler reads.
        (self.disk / "in.p8").write_text(P1_SRC.read_text())
        out = self.disk / "out.s"
        if out.exists():
            out.unlink()
        r = subprocess.run(
            [str(EMU), str(self.boot_rom), "--machine", "wendy2c",
             "--wendy2-prog", str(self.prog_bin), "--load", "0200",
             "--disk", str(self.disk), "--cycle-cap", "60000000000"],
            capture_output=True, text=True)
        self.assertTrue(out.exists() and out.stat().st_size > 0,
                        msg=f"banked self-host produced no out.s:\n{r.stdout}\n{r.stderr}")
        # oracle: host p8c compiling the same p1.p8.
        oracle = self.workdir / "oracle.s"
        ro = subprocess.run(
            [sys.executable, "-m", "p8c", "--target", "nmos",
             str(P1_SRC), "-o", str(oracle)],
            capture_output=True, text=True, cwd=str(PROG8))
        self.assertEqual(ro.returncode, 0,
                         msg=f"oracle failed:\n{ro.stdout}\n{ro.stderr}")
        self.assertEqual(_norm(oracle.read_text()), _norm(out.read_text()),
                         msg="banked monolith self-host diverged from the p8c "
                             "oracle on p1.p8")


if __name__ == "__main__":
    unittest.main()
