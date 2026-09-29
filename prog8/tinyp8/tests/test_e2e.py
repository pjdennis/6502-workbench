"""End-to-end goldens for tinyp8 (the 6502-native proof-of-concept).

For each .tp8 under tests/goldens/, this:
  1. Builds tinyp8.bin once (assembling tinyp8.s with vasm).
  2. Invokes tinyp8.bin *inside the emulator* with (.tp8, .body) as
     positional argv. The compiler reads source via the emulator's
     read syscall ($F018) and emits machine code via write ($F024).
  3. Wraps the body with a reset vector + padding to make it runnable.
  4. Runs the wrapped binary on the emulator, captures stdout via
     --output, and diffs that against the matching .expected.stdout.

The same tinyp8.bin processes every test source, so the .body
content has to actually be the product of on-emulator parsing +
codegen -- not pre-baked into the compiler. The 4 test cases below
cover the v0 surface (print literal, print_ub byte, multiple
statements, blank lines / comments).

SKIPs if vasm6502_oldstyle is missing or the emulator isn't built.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent           # tinyp8/tests
TP8 = HERE.parent                                  # tinyp8/
PROG8 = TP8.parent                                 # prog8/
REPO = PROG8.parents[1]                            # repo root
EMU = REPO / "emulator" / "emulator.out"
GOLDENS = HERE / "goldens"


def _have_vasm() -> bool:
    return shutil.which("vasm6502_oldstyle") is not None


@unittest.skipUnless(_have_vasm(), "vasm6502_oldstyle not on PATH")
@unittest.skipUnless(EMU.exists(), f"emulator not built at {EMU}")
class TinyP8Goldens(unittest.TestCase):
    """One method per .tp8 file in goldens/, generated lazily below."""

    @classmethod
    def setUpClass(cls):
        # Inject prog8/ on sys.path so we can `import tinyp8.__main__`.
        sys.path.insert(0, str(PROG8))

    def _run_one(self, tp8_path: Path, expected_path: Path) -> None:
        from tinyp8.__main__ import (build_tinyp8, run_tinyp8,
                                      wrap_body_as_runnable, run_compiled)

        build_tinyp8()
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            body = tdp / (tp8_path.stem + ".body")
            run_tinyp8(tp8_path, body)
            runnable = tdp / (tp8_path.stem + ".runnable")
            runnable.write_bytes(wrap_body_as_runnable(body.read_bytes()))
            stdout_path = tdp / "stdout.txt"
            actual = run_compiled(runnable, stdout_path)
        expected = expected_path.read_text()
        self.assertEqual(
            actual, expected,
            msg=f"\n--- expected ---\n{expected!r}\n"
                f"--- actual ---\n{actual!r}\n"
        )


def _make_test(p, expected):
    def t(self):
        self._run_one(p, expected)
    t.__name__ = f"test_{p.stem}"
    return t


if GOLDENS.exists():
    for p in sorted(GOLDENS.glob("*.tp8")):
        exp = p.with_suffix(".expected.stdout")
        if exp.exists():
            setattr(TinyP8Goldens, f"test_{p.stem}", _make_test(p, exp))


if __name__ == "__main__":
    unittest.main()
