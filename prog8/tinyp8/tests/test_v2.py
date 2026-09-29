"""tinyp8 v2 golden tests: variables (`let`) + variable references in
print_ub. These features only exist in tinyp8.p8 (the Prog8 version);
tinyp8.s stays at v1. We compile each .tp8 in goldens_v2/ via
tinyp8.p8, run the resulting binary, and diff captured stdout against
the expected golden.

This is the natural next stage of the bootstrap: tinyp8.p8 has grown
beyond the hand-written reference compiler, while the original v0/v1
corpus continues to be exercised by the equivalence tests.

SKIPs if vasm6502_oldstyle or the emulator binary are missing.
"""
from __future__ import annotations

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
GOLDENS_V2 = HERE / "goldens_v2"


def _have_vasm() -> bool:
    return shutil.which("vasm6502_oldstyle") is not None


@unittest.skipUnless(_have_vasm(), "vasm6502_oldstyle not on PATH")
@unittest.skipUnless(EMU.exists(), f"emulator not built at {EMU}")
class TinyP8V2(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(PROG8))

    def setUp(self):
        from tinyp8.__main__ import wrap_body_as_runnable, run_compiled
        self.wrap_body_as_runnable = wrap_body_as_runnable
        self.run_compiled = run_compiled
        self.workdir = Path(tempfile.mkdtemp(prefix="p8c_v2_"))
        # Build tinyp8.p8 -> tinyp8.bin via host p8c + vasm. The result
        # is reused across all v2 test cases in this class.
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

    def _check(self, tp8: Path, expected_path: Path) -> None:
        body = self.workdir / f"{tp8.stem}.body"
        r = subprocess.run(
            [str(EMU), str(self.p8_compiler), str(tp8), str(body),
             "--no-dump"],
            capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0,
                         msg=f"compiler failed on {tp8.name}:\n"
                             f"{r.stdout}\n{r.stderr}")
        runnable = self.workdir / f"{tp8.stem}.runnable"
        runnable.write_bytes(self.wrap_body_as_runnable(body.read_bytes()))
        stdout_path = self.workdir / f"{tp8.stem}.stdout"
        actual = self.run_compiled(runnable, stdout_path)
        expected = expected_path.read_text()
        self.assertEqual(actual, expected,
                         msg=f"\n--- expected ---\n{expected!r}\n"
                             f"--- actual ---\n{actual!r}\n")


def _make_test(p, expected):
    def t(self):
        self._check(p, expected)
    t.__name__ = f"test_v2_{p.stem}"
    return t


if GOLDENS_V2.exists():
    for p in sorted(GOLDENS_V2.glob("*.tp8")):
        exp = p.with_suffix(".expected.stdout")
        if exp.exists():
            setattr(TinyP8V2, f"test_v2_{p.stem}", _make_test(p, exp))


if __name__ == "__main__":
    unittest.main()
