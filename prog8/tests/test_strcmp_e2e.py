"""End-to-end test for strings.compare: compile a program that compares string
literals and writes a result string through the nmos file-I/O shim, run it on
the emulator, and check the bytes. Mirrors test_str_data_e2e's harness."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# firmware/vasm: vasm6502_oldstyle with the firmware include path.
FW_VASM = Path(__file__).resolve().parents[3] / "firmware" / "vasm"

HERE = Path(__file__).resolve()
PROG8 = HERE.parent.parent
REPO = PROG8.parent.parent
EMU = REPO / "emulator" / "emulator.out"

# Reuse the shim from the sibling e2e test, with `%import strings` added.
# Load the sibling by file path so its _SHIM is the executed (escape-resolved)
# value, not the raw source text.
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location(
    "_strdata_sibling", HERE.parent / "test_str_data_e2e.py")
_sib = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_sib)
_SHIM_STR = "%import strings\n" + _sib._SHIM

# body -> expected output bytes
_CASES = [
    ('if strings.compare("apple", "apple") == 0 { out_text("Y") }', b"Y"),
    ('if strings.compare("apple", "banana") != 0 { out_text("Y") }', b"Y"),
    ('if strings.compare("zebra", "apple") == 1 { out_text("G") }', b"G"),
    ('if strings.compare("apple", "zebra") == 255 { out_text("L") }', b"L"),
    # a proper prefix compares less than the longer string
    ('if strings.compare("ab", "abc") == 255 { out_text("P") }', b"P"),
    # equal-length, differing tail
    ('if strings.compare("abd", "abc") == 1 { out_text("D") }', b"D"),
]


def _have_vasm() -> bool:
    return shutil.which("vasm6502_oldstyle") is not None


@unittest.skipUnless(_have_vasm(), "vasm6502_oldstyle not on PATH")
@unittest.skipUnless(EMU.exists(), f"emulator not built at {EMU}")
class StrCompare(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workdir = Path(tempfile.mkdtemp(prefix="p8c_strcmp_"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.workdir, ignore_errors=True)

    def _run_case(self, body: str, expected: bytes) -> None:
        src = (_SHIM_STR + "  sub start() {\n    dst = _openout(_argv(1))\n    "
               + body + "\n    _close(dst)\n  }\n}\n")
        stem = f"case_{abs(hash(body)) & 0xffffff:06x}"
        p8 = self.workdir / f"{stem}.p8"
        s = self.workdir / f"{stem}.s"
        binf = self.workdir / f"{stem}.bin"
        out = self.workdir / f"{stem}.out"
        p8.write_text(src)
        r = subprocess.run([sys.executable, "-m", "p8c", "--target", "nmos", str(p8), "-o", str(s)],
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
