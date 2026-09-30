"""Codegen snapshot tests.

For each .p8 under tests/snapshots/, compile it with p8c and diff the
emitted .s against the matching .expected.s file. Set the env var
P8C_UPDATE_SNAPSHOTS=1 to rewrite the .expected.s files in place
(useful when an intentional codegen change ripples through them).

This tier is the host-side oracle that, from Phase 5 onward, the
on-emulator compiler is checked against: any deviation between
`p8c .p8 -> .s` and `pN .p8 -> .s` (run inside the emulator) is a
bug, even if both happen to assemble to the same final binary.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from p8c.codegen import generate  # noqa: E402
from p8c.lex import lex  # noqa: E402
from p8c.parse import parse  # noqa: E402
from p8c.sema import analyze  # noqa: E402


SNAPS = ROOT / "tests" / "snapshots"


def compile_to_text(p8_path: Path) -> str:
    src = p8_path.read_text()
    prog = parse(lex(src, str(p8_path)), str(p8_path))
    analyze(prog)
    # Use a stable relative source-path comment so the snapshot is
    # location-independent.
    return generate(prog, p8_path.name)


class Snapshots(unittest.TestCase):
    pass


def _make_test(p8: Path, expected: Path):
    def t(self):
        actual = compile_to_text(p8)
        if os.environ.get("P8C_UPDATE_SNAPSHOTS") == "1":
            expected.write_text(actual)
            return
        self.assertEqual(actual, expected.read_text(),
                         msg=f"snapshot mismatch for {p8.name}; "
                             f"set P8C_UPDATE_SNAPSHOTS=1 to refresh")
    t.__name__ = f"test_snapshot_{p8.stem}"
    return t


if SNAPS.exists():
    for p in sorted(SNAPS.glob("*.p8")):
        exp = p.with_suffix(".expected.s")
        if not exp.exists():
            # Auto-create on first run so adding a snapshot is one file,
            # not two. Subsequent runs assert against it.
            exp.write_text(compile_to_text(p))
        setattr(Snapshots, f"test_snapshot_{p.stem}", _make_test(p, exp))


if __name__ == "__main__":
    unittest.main()
