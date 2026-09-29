"""Behavioral tests for uword (16-bit element) arrays -- split lo/hi
storage, uword indices (truncated to a byte for <=256 arrays) -- and the
ubyte-element -> uword widening fix. Arrays are capped at 256 elements
(upstream's model); larger arenas use peek/poke slabs instead.

Each case compiles a tiny program that writes computed result bytes to
its output file (the nmos file-I/O shim tinyp8 uses), runs it on the
emulator, and checks the bytes. SKIPs without vasm + the emulator.
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
uword[8] w
ubyte[8] sb
uword idx
uword s
ubyte b
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

_CASES = [
    # uword array element write + read, little-endian
    ("w[0] = $1234  w[1] = $5678  "
     "_write(lsb(w[0]), dst)  _write(msb(w[0]), dst)  "
     "_write(lsb(w[1]), dst)  _write(msb(w[1]), dst)",
     [0x34, 0x12, 0x78, 0x56]),
    # uword array indexed by a uword variable
    ("idx = 3  w[idx as ubyte] = $abcd  "
     "_write(lsb(w[idx as ubyte]), dst)  _write(msb(w[idx as ubyte]), dst)",
     [0xcd, 0xab]),
    # uword-array arithmetic: s = w[0] + w[1]
    ("w[0] = $0102  w[1] = $0304  s = w[0] + w[1]  "
     "_write(lsb(s), dst)  _write(msb(s), dst)",
     [0x06, 0x04]),
    # ubyte element widened to uword (the widening fix): high byte = 0
    ("sb[2] = 200  s = sb[2]  _write(lsb(s), dst)  _write(msb(s), dst)",
     [200, 0]),
    # ubyte element read at a uword variable index (truncated to a byte)
    ("idx = 5  sb[idx as ubyte] = 170  s = sb[idx as ubyte]  "
     "_write(lsb(s), dst)  _write(msb(s), dst)",
     [170, 0]),
]


def _have_vasm() -> bool:
    return shutil.which("vasm6502_oldstyle") is not None


@unittest.skipUnless(_have_vasm(), "vasm6502_oldstyle not on PATH")
@unittest.skipUnless(EMU.exists(), f"emulator not built at {EMU}")
class Arrays16(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workdir = Path(tempfile.mkdtemp(prefix="p8c_arr16_"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.workdir, ignore_errors=True)

    def _run_case(self, body: str, expected: list[int]) -> None:
        src = (_SHIM + "  sub start() {\n    dst = _openout(_argv(1))\n    "
               + body + "\n    _close(dst)\n  }\n}\n")
        stem = f"arr_{abs(hash(body)) & 0xffffff:06x}"
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
