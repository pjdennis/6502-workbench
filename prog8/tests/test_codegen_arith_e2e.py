"""Behavioral regression for the dual-scratch binary-expression codegen.

Host p8c evaluates a binary op by computing both operands and combining
them. Each operand may itself need a scratch temp (a shift, a nested
binop, a unary). The fix this guards: the first-evaluated operand is held
on the CPU stack while the second is evaluated, so a fixed scratch slot
is never aliased across the two sides. Before the fix,
`(v << 3) + (v << 1)` (both sides need scratch) produced the wrong value.

Each case below compiles a tiny program that writes computed result bytes
to its output file (the same nmos file-I/O shim tinyp8 uses), runs it on
the emulator, and checks the bytes. SKIPs without vasm + the emulator.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# firmware/vasm: vasm6502_oldstyle with the firmware include path.
FW_VASM = Path(__file__).resolve().parents[3] / "firmware" / "vasm"

HERE = Path(__file__).resolve().parent
PROG8 = HERE.parent
REPO = PROG8.parents[1]
EMU = REPO / "emulator" / "emulator.out"

_SHIM = """%address $0200
%output raw
%launcher none
main {
ubyte dst
uword w
ubyte b
ubyte p
ubyte q
ubyte r
ubyte s
ubyte[4] arr
extsub $F015 = _close(ubyte handle @A)
asmsub _argv(ubyte i @A) -> uword @AY {
    %asm {{
        jsr  $f01e
        pha
        txa
        tay
        pla
        rts
    }}
}
asmsub _openout(uword filename @AY) -> ubyte @A {
    %asm {{
        pha
        tya
        tax
        pla
        jsr  $f021
        rts
    }}
}
asmsub _write(ubyte v @A, ubyte handle @X) {
    %asm {{
        jsr  $f024
        rts
    }}
}
"""

# Each case: (body statements, expected output bytes). The body may use
# w/b/p/q/r/s and must call `_write(<byte>, dst)` for each expected byte.
_CASES = [
    # word '+' with both operands needing scratch (the original bug)
    ("w = 5  w = (w << 3) + (w << 1)  _write(lsb(w), dst)", [50]),
    # word '-' with both operands shifted
    ("w = 10  w = (w << 4) - (w << 1)  _write(lsb(w), dst)", [140]),
    # word bitwise with both operands shifted
    ("w = 15  w = (w << 4) | (w << 1)  _write(lsb(w), dst)", [254]),
    # word compare with both operands shifted, in an if
    ("p = 2  q = 1  if (p << 4) > (q << 4) { _write(1, dst) } else { _write(0, dst) }",
     [1]),
    # deeply nested word adds: ((a+b)+(c+d)) -- LHS and RHS both binops
    ("w = 0  p = 1  q = 2  r = 3  s = 4  "
     "w = (p + q) + (r + s)  _write(lsb(w), dst)", [10]),
    # byte generic path: non-leaf RHS binop
    ("p = 1  q = 2  r = 3  s = 4  b = (p + q) + (r + s)  _write(b, dst)", [10]),
    # byte multiply with a non-leaf RHS (exercises the tmp1 slot fix)
    ("p = 3  q = 2  r = 2  b = p * (q + r)  _write(b, dst)", [12]),
    # mkword whose low-byte arg is an array read: the array index uses Y,
    # which must not clobber the stashed high byte.
    ("arr[0] = 1  arr[1] = 2  w = mkword(arr[0], arr[1])  "
     "_write(msb(w), dst)  _write(lsb(w), dst)", [1, 2]),
]


def _have_vasm() -> bool:
    return shutil.which("vasm6502_oldstyle") is not None


@unittest.skipUnless(_have_vasm(), "vasm6502_oldstyle not on PATH")
@unittest.skipUnless(EMU.exists(), f"emulator not built at {EMU}")
class DualScratchArith(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workdir = Path(tempfile.mkdtemp(prefix="p8c_arith_"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.workdir, ignore_errors=True)

    def _run_case(self, body: str, expected: list[int]) -> None:
        src = (_SHIM + "  sub start() {\n    dst = _openout(_argv(1))\n    "
               + body + "\n    _close(dst)\n  }\n}\n")
        stem = f"case_{abs(hash(body)) & 0xffffff:06x}"
        p8 = self.workdir / f"{stem}.p8"
        s = self.workdir / f"{stem}.s"
        binf = self.workdir / f"{stem}.bin"
        out = self.workdir / f"{stem}.out"
        p8.write_text(src)
        r = subprocess.run(
            [sys.executable, "-m", "p8c", "--target", "nmos", str(p8), "-o", str(s)],
            capture_output=True, text=True, cwd=str(PROG8))
        self.assertEqual(r.returncode, 0, msg=f"p8c:\n{r.stdout}\n{r.stderr}")
        r = subprocess.run(
            [str(FW_VASM), "-Fbin", "-dotdir", "-ignore-mult-inc",
             "-esc", "-wfail", "-o", str(binf), str(s)],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, msg=f"vasm:\n{r.stdout}\n{r.stderr}")
        r = subprocess.run([str(EMU), str(binf), "/dev/null", str(out),
                            "--no-dump"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, msg=f"emulator:\n{r.stdout}\n{r.stderr}")
        self.assertEqual(list(out.read_bytes()), expected,
                         msg=f"wrong result for: {body}")

    def test_cases(self):
        for body, expected in _CASES:
            with self.subTest(body=body):
                self._run_case(body, expected)


if __name__ == "__main__":
    unittest.main()
