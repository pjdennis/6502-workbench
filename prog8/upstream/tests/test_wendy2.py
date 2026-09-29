#!/usr/bin/env python3
"""End-to-end tests for the custom 'wendy2' banked Prog8 target.

For each demos/<name>.p8 that has a matching tests/goldens/<name>.expected.lcd,
compile it with upstream prog8c (-target wendy2.properties), boot+upload+run it
on the wendy2c emulator via wendy2_run.sh, and diff the final LCD frame against
the golden.

Skips cleanly if the toolchain isn't present (prog8c.jar / 64tass /
vasm6502_oldstyle / the built emulator).

Run:  python3 tests/test_wendy2.py        (from .../toolchain/prog8/upstream)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent          # .../upstream/tests
UP = HERE.parent                                 # .../upstream
REPO = UP.parents[2]                             # repo root
EMU = REPO / "emulator" / "emulator.out"
JAR = Path(os.environ.get("PROG8C", "/tmp/prog8c.jar"))
DEMOS = UP / "demos"
GOLDENS = HERE / "goldens"


def _have() -> tuple[bool, str]:
    if not JAR.exists():
        return False, f"prog8c jar not found at {JAR}"
    if shutil.which("64tass") is None:
        return False, "64tass not on PATH"
    if shutil.which("vasm6502_oldstyle") is None:
        return False, "vasm6502_oldstyle not on PATH"
    if not EMU.exists():
        return False, f"emulator not built at {EMU}"
    return True, ""


def _lcd_frame(p8_name: str) -> str:
    """Run wendy2_run.sh on demos/<name>.p8 and return the final LCD frame."""
    r = subprocess.run(
        ["bash", str(UP / "wendy2_run.sh"), f"demos/{p8_name}.p8"],
        cwd=str(UP), capture_output=True, text=True,
    )
    rows = [ln for ln in r.stdout.splitlines() if ln.startswith("  |") and ln.endswith("|")]
    if not rows:
        raise AssertionError(f"no LCD frame in output:\n{r.stdout}\n{r.stderr}")
    return "\n".join(rows) + "\n"


_ok, _why = _have()


@unittest.skipUnless(_ok, _why)
class Wendy2Goldens(unittest.TestCase):
    pass


def _make(name: str, golden: Path):
    def t(self):
        self.assertEqual(_lcd_frame(name), golden.read_text(),
                         msg=f"LCD frame mismatch for {name}")
    return t


# Plain demos run via the serial-upload boot ROM (no --disk). The disk- and
# monitor-backed demos have their own suites (test_wendy2_disk / _monitor).
PLAIN = ["m0_exit", "m1_hello", "t1_bank_probe", "t2_banked_data",
         "t3_banked_code", "t4_bank_counters", "t5_multibank_code"]

for name in PLAIN:
    g = GOLDENS / f"{name}.expected.lcd"
    if g.exists() and (DEMOS / f"{name}.p8").exists():
        setattr(Wendy2Goldens, f"test_{name}", _make(name, g))


if __name__ == "__main__":
    unittest.main(verbosity=2)
