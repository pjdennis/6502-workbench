"""Self-host equivalence test.

For every .tp8 in goldens/, compile it twice:
  1. via tinyp8.bin (the hand-written 6502 asm compiler), and
  2. via tinyp8_p8.bin (tinyp8.p8 compiled by the host p8c).

Assert the two .body outputs are byte-identical.

A passing test means: a real working compiler -- written in Prog8 and
compiled by our own host p8c -- produces the same machine code as the
hand-tuned reference assembly version. That's the strict form of
"self-hosting works" for this proof-of-concept.

SKIPs if vasm6502_oldstyle or the emulator binary are missing.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# firmware/vasm: vasm6502_oldstyle with the firmware include path.
FW_VASM = Path(__file__).resolve().parents[4] / "firmware" / "vasm"

HERE = Path(__file__).resolve().parent
TP8 = HERE.parent
PROG8 = TP8.parent
REPO = PROG8.parents[1]
EMU = REPO / "emulator" / "emulator.out"
TINYP8_P8_SRC = TP8 / "tinyp8.p8"
GOLDENS = HERE / "goldens"


def _have_vasm() -> bool:
    return shutil.which("vasm6502_oldstyle") is not None


@unittest.skipUnless(_have_vasm(), "vasm6502_oldstyle not on PATH")
@unittest.skipUnless(EMU.exists(), f"emulator not built at {EMU}")
class SelfHostEquivalence(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(PROG8))

    def setUp(self):
        # Build BOTH compilers once per test method (cheap; mtime-cached
        # for the asm version and rebuilt-as-needed for the p8 version).
        from tinyp8.__main__ import build_tinyp8, run_tinyp8  # noqa
        self.workdir = Path(tempfile.mkdtemp(prefix="p8c_selfhost_"))

        # Compiler 1: tinyp8.s -> tinyp8.bin (cached).
        self.asm_compiler = build_tinyp8()

        # Compiler 2: tinyp8.p8 -> tinyp8_p8.s (via p8c) -> tinyp8_p8.bin (via vasm).
        self.p8_compiler = self.workdir / "tinyp8_p8.bin"
        s_path = self.workdir / "tinyp8_p8.s"

        r = subprocess.run(
            [sys.executable, "-m", "p8c", "--target", "nmos",
             str(TINYP8_P8_SRC), "-o", str(s_path)],
            capture_output=True, text=True, cwd=str(PROG8),
        )
        self.assertEqual(r.returncode, 0,
                         msg=f"p8c failed:\n{r.stdout}\n{r.stderr}")

        r = subprocess.run(
            [str(FW_VASM), "-Fbin", "-dotdir", "-ignore-mult-inc",
             "-esc", "-wfail", "-o", str(self.p8_compiler), str(s_path)],
            capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0,
                         msg=f"vasm failed:\n{r.stdout}\n{r.stderr}")

    def tearDown(self):
        shutil.rmtree(self.workdir, ignore_errors=True)

    def _run(self, compiler: Path, source: Path, body: Path) -> None:
        r = subprocess.run(
            [str(EMU), str(compiler), str(source), str(body), "--no-dump"],
            capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0,
                         msg=f"compiler failed on {source.name}:\n"
                             f"{r.stdout}\n{r.stderr}")

    def _check_pair(self, tp8: Path) -> None:
        body_asm = self.workdir / f"{tp8.stem}.asm.body"
        body_p8 = self.workdir / f"{tp8.stem}.p8.body"
        self._run(self.asm_compiler, tp8, body_asm)
        self._run(self.p8_compiler, tp8, body_p8)
        a = body_asm.read_bytes()
        b = body_p8.read_bytes()
        self.assertEqual(
            a, b,
            msg=f"\nCompiler outputs differ for {tp8.name}:\n"
                f"  hand-asm version: {a.hex()}\n"
                f"  prog8 version:    {b.hex()}\n"
        )


def _make_test(p):
    def t(self):
        self._check_pair(p)
    t.__name__ = f"test_equiv_{p.stem}"
    return t


if GOLDENS.exists():
    for p in sorted(GOLDENS.glob("*.tp8")):
        setattr(SelfHostEquivalence, f"test_equiv_{p.stem}", _make_test(p))


if __name__ == "__main__":
    unittest.main()
