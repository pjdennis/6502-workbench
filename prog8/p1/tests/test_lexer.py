"""On-target lexer equivalence test (Phase 6, M1).

Builds `p1/lexer.p8` (the Prog8 lexer port) with the host p8c + vasm,
runs it on the emulator's nmos-default machine over a corpus of real
`.p8` sources, and asserts the token-stream dump it writes is
byte-identical to the Python oracle (`p8c --dump-tokens`, i.e.
`serialize_tokens`).

This is the M1 milestone: the on-target lexer reproduces the canonical
token-dump frozen by `tests/test_serialize.py`. Because that dump is the
same contract the Python lexer is checked against, a green diff here
ties the 6502 lexer back to the host lexer.

The lexer is invoked exactly like tinyp8: positional args are the input
source and the output file; it reads via the $F018 read syscall and
writes via $F024. SKIPs cleanly if vasm6502_oldstyle or the emulator
binary are missing.
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
P1 = HERE.parent
PROG8 = P1.parent
REPO = PROG8.parents[1]
EMU = REPO / "emulator" / "emulator.out"
LEXER_SRC = P1 / "lexer.p8"
EXAMPLES = PROG8 / "examples"
SNAPS = PROG8 / "tests" / "snapshots"
TINYP8 = PROG8 / "tinyp8" / "tinyp8.p8"


def _have_vasm() -> bool:
    return shutil.which("vasm6502_oldstyle") is not None


def _corpus() -> list[Path]:
    paths: list[Path] = []
    for d in (EXAMPLES, SNAPS):
        if d.exists():
            paths.extend(sorted(d.glob("*.p8")))
    if TINYP8.exists():
        paths.append(TINYP8)
    # The lexer lexing its own source -- a self-reference checkpoint.
    paths.append(LEXER_SRC)
    return paths


@unittest.skipUnless(_have_vasm(), "vasm6502_oldstyle not on PATH")
@unittest.skipUnless(EMU.exists(), f"emulator not built at {EMU}")
class LexerEquivalence(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(PROG8))
        cls.workdir = Path(tempfile.mkdtemp(prefix="p1_lexer_"))
        # Build the lexer once: p8c -> .s -> vasm -> .bin.
        s_path = cls.workdir / "lexer.s"
        cls.lexer_bin = cls.workdir / "lexer.bin"
        r = subprocess.run(
            [sys.executable, "-m", "p8c", "--target", "nmos",
             str(LEXER_SRC), "-o", str(s_path)],
            capture_output=True, text=True, cwd=str(PROG8),
        )
        assert r.returncode == 0, f"p8c failed:\n{r.stdout}\n{r.stderr}"
        r = subprocess.run(
            [str(FW_VASM), "-Fbin", "-dotdir", "-ignore-mult-inc",
             "-esc", "-wfail", "-o", str(cls.lexer_bin), str(s_path)],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, f"vasm failed:\n{r.stdout}\n{r.stderr}"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.workdir, ignore_errors=True)

    def _python_dump(self, src: Path) -> str:
        r = subprocess.run(
            [sys.executable, "-m", "p8c", str(src), "--dump-tokens"],
            capture_output=True, text=True, cwd=str(PROG8),
        )
        self.assertEqual(r.returncode, 0,
                         msg=f"p8c --dump-tokens failed on {src.name}:\n"
                             f"{r.stdout}\n{r.stderr}")
        return r.stdout

    def _ontarget_dump(self, src: Path) -> str:
        out = self.workdir / f"{src.stem}.ontarget.dump"
        r = subprocess.run(
            [str(EMU), str(self.lexer_bin), str(src), str(out), "--no-dump"],
            capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0,
                         msg=f"emulator lexer failed on {src.name}:\n"
                             f"{r.stdout}\n{r.stderr}")
        return out.read_text()

    def _check(self, src: Path) -> None:
        self.assertEqual(self._python_dump(src), self._ontarget_dump(src),
                         msg=f"token dump differs for {src.name}")

    def test_no_trailing_newline(self):
        # A token ending exactly at EOF (no trailing newline) must not
        # loop: the emulator rewinds the input on EOF, so the lexer's
        # software-sticky EOF is what stops it. Regression for that fix.
        for snippet in ("5", "foo", "$ff", "x + 1"):
            with self.subTest(snippet=snippet):
                src = self.workdir / "noeol.p8"
                src.write_bytes(snippet.encode())   # deliberately no '\n'
                self.assertEqual(self._python_dump(src),
                                 self._ontarget_dump(src),
                                 msg=f"token dump differs for {snippet!r}")

    def test_lexer_corpus_edge_cases(self):
        # The thorough token-class corpus (every numeric base, every
        # char/string escape, keyword traps, multi-char-operator maximal
        # munch) from the serializer freeze suite, run on-target.
        from tests.test_serialize import LEXER_CORPUS  # noqa: E402
        for i, snippet in enumerate(LEXER_CORPUS):
            with self.subTest(snippet=snippet):
                src = self.workdir / f"corpus_{i:02d}.p8"
                src.write_text(snippet + "\n")
                self.assertEqual(self._python_dump(src),
                                 self._ontarget_dump(src),
                                 msg=f"token dump differs for {snippet!r}")


def _make(p: Path):
    def t(self):
        self._check(p)
    t.__name__ = f"test_lex_{p.stem}"
    return t


for _p in _corpus():
    setattr(LexerEquivalence, f"test_lex_{_p.stem}", _make(_p))


if __name__ == "__main__":
    unittest.main()
