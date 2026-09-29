"""Behavioral test for string literals used as data (their pool address).

A bare string literal in value position evaluates to the address of its
pool label (a uword): it can be assigned to a uword, passed to a uword
param, or used to initialize a uword. This is the primitive that lets the
self-hosting compiler (p1.p8) emit fixed assembly text from a pooled
string + a copy loop instead of a per-character `out_byte()` run.

Each case compiles a tiny program that walks a string literal's bytes via
`@(ptr)` and writes them to its output file (the nmos file-I/O shim that
tinyp8 / p1 use), runs it on the emulator, and checks the bytes match the
string. SKIPs without vasm + the emulator.
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
uword s
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
; write every byte of the NUL-terminated string at `p` to dst.
sub out_text(uword p) {
    uword q
    q = p
    while @(q) != 0 {
        _write(@(q), dst)
        q = q + 1
    }
}
"""

# Each case: (body statements, expected output bytes).
_CASES = [
    # string literal passed directly to a uword param
    ('out_text("hello")', b"hello"),
    # assigned to a uword var first, then passed
    ('s = "world"  out_text(s)', b"world"),
    # two distinct literals -> two distinct pool labels, in order
    ('out_text("ab")  out_text("cd")', b"abcd"),
    # escapes survive the pool round-trip (newline, quote, backslash, tab)
    (r'out_text("a\nb\"c\\d\te")', b'a\nb"c\\d\te'),
    # empty string literal -> immediate NUL terminator, writes nothing
    ('out_text("")  out_text("x")', b"x"),
]


def _have_vasm() -> bool:
    return shutil.which("vasm6502_oldstyle") is not None


@unittest.skipUnless(_have_vasm(), "vasm6502_oldstyle not on PATH")
@unittest.skipUnless(EMU.exists(), f"emulator not built at {EMU}")
class StringData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workdir = Path(tempfile.mkdtemp(prefix="p8c_strdata_"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.workdir, ignore_errors=True)

    def _run_case(self, body: str, expected: bytes) -> None:
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
        self.assertEqual(out.read_bytes(), expected,
                         msg=f"wrong output for: {body}")

    def test_cases(self):
        for body, expected in _CASES:
            with self.subTest(body=body):
                self._run_case(body, expected)


if __name__ == "__main__":
    unittest.main()
