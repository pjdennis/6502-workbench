"""End-to-end LCD goldens.

For each .p8 under tests/goldens/, runs p8c --run, captures the
emulator's final LCD frame, and diffs it against the matching
.expected.lcd file.

SKIPs if vasm6502_oldstyle is missing OR if the emulator binary
hasn't been built. Same skip discipline as the existing wendy2c
goldens.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]   # prog8
REPO = ROOT.parent                        # repo root
EMULATOR = ROOT.parent / "emulator" / "emulator.out"
GOLDENS = ROOT / "tests" / "goldens"


def _have_vasm() -> bool:
    return shutil.which("vasm6502_oldstyle") is not None


@unittest.skipUnless(_have_vasm(), "vasm6502_oldstyle not on PATH")
@unittest.skipUnless(EMULATOR.exists(), f"emulator not built at {EMULATOR}")
class E2EGoldens(unittest.TestCase):
    """One test method per golden file -- discovered lazily."""

    def _run_one(self, p8_path: Path, expected_path: Path) -> None:
        cmd = [
            sys.executable, "-m", "p8c", str(p8_path),
            "-o", str(p8_path.with_suffix(".s")),
            "--run",
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        r = subprocess.run(cmd, capture_output=True, text=True,
                           cwd=str(ROOT), env=env)
        self.assertEqual(r.returncode, 0,
                         msg=f"p8c failed:\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}")
        # Emulator prints LCD frame on stderr; we route it through
        # p8c's stdout. Grab the |...|-wrapped lines under "lcd:" as the
        # frame (the "lcd-hex:" rows after them are the raw bytes).
        lines = r.stdout.splitlines()
        start = next((i + 1 for i, ln in enumerate(lines) if ln.endswith(": lcd:")), len(lines))
        rows = []
        for ln in lines[start:]:
            if not (ln.startswith("  |") and ln.endswith("|")):
                break
            rows.append(ln)
        actual = "\n".join(rows) + "\n"
        expected = expected_path.read_text()
        self.assertEqual(actual, expected,
                         msg=f"LCD frame mismatch for {p8_path.name}\n"
                             f"---expected---\n{expected}\n---actual---\n{actual}")


def _make_test(p8_path: Path, expected_path: Path):
    def t(self):
        self._run_one(p8_path, expected_path)
    t.__name__ = f"test_golden_{p8_path.stem}"
    return t


# Dynamic test-method registration.
if GOLDENS.exists():
    for p in sorted(GOLDENS.glob("*.p8")):
        exp = p.with_suffix(".expected.lcd")
        if exp.exists():
            setattr(E2EGoldens, f"test_golden_{p.stem}", _make_test(p, exp))


if __name__ == "__main__":
    unittest.main()
