#!/usr/bin/env python3
"""End-to-end tests for the wendy2 disk subsystem (--disk file-I/O OS calls).

Each case names a demo .p8, the disk files to stage, and the matching
tests/goldens/<name>.expected.lcd. The demo is compiled with prog8c
(-target wendy2.properties), uploaded via the boot ROM, and run with the
staged host directory mounted as --disk; the final LCD frame is diffed
against the golden.

Skips cleanly if prog8c.jar / 64tass / vasm6502_oldstyle / the emulator
are missing. Run from .../toolchain/prog8/upstream.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
UP = HERE.parent
REPO = UP.parents[2]                             # repo root
EMU = REPO / "emulator" / "emulator.out"
JAR = Path(os.environ.get("PROG8C", "/tmp/prog8c.jar"))
GOLDENS = HERE / "goldens"

# name -> dict of disk files to stage (filename -> bytes)
CASES = {
    "d1_catfile": {"greeting": b"disk OK!"},
}


def _have() -> tuple[bool, str]:
    if not JAR.exists():
        return False, f"prog8c jar not found at {JAR}"
    for tool in ("64tass", "vasm6502_oldstyle"):
        if shutil.which(tool) is None:
            return False, f"{tool} not on PATH"
    if not EMU.exists():
        return False, f"emulator not built at {EMU}"
    return True, ""


def _run(name: str, files: dict[str, bytes]) -> str:
    disk = Path(tempfile.mkdtemp(prefix=f"wdisk_{name}_"))
    try:
        for fn, data in files.items():
            (disk / fn).write_bytes(data)
        r = subprocess.run(
            ["bash", str(UP / "wendy2_disk_run.sh"), f"demos/{name}.p8", str(disk)],
            cwd=str(UP), capture_output=True, text=True,
        )
        rows = [ln for ln in r.stdout.splitlines() if ln.startswith("  |") and ln.endswith("|")]
        if not rows:
            raise AssertionError(f"no LCD frame:\n{r.stdout}\n{r.stderr}")
        return "\n".join(rows) + "\n"
    finally:
        shutil.rmtree(disk, ignore_errors=True)


_ok, _why = _have()


@unittest.skipUnless(_ok, _why)
class Wendy2DiskGoldens(unittest.TestCase):
    pass


def _make(name: str, files: dict[str, bytes], golden: Path):
    def t(self):
        self.assertEqual(_run(name, files), golden.read_text(),
                         msg=f"LCD mismatch for {name}")
    return t


for _name, _files in CASES.items():
    _g = GOLDENS / f"{_name}.expected.lcd"
    if _g.exists() and (UP / "demos" / f"{_name}.p8").exists():
        setattr(Wendy2DiskGoldens, f"test_{_name}", _make(_name, _files, _g))


if __name__ == "__main__":
    unittest.main(verbosity=2)
