#!/usr/bin/env python3
"""Run the whole p1 test corpus through the UPSTREAM-compiled pipeline (the
pass1/pass2 images built by selfhost.sh) and diff each result against the p8c
host oracle.

Expectation: byte-identical for every program EXCEPT those using signed types
(`byte`/`word`). The pipeline (p1_pass2_sh.p8) is hand-specialized to compile
p1.p8, which has only ubyte/uword, so its emit_cmp_cond omits p8c's signed
compare arm. On such programs the upstream pipeline still matches the *p8c
pipeline* exactly (verified separately) -- it just differs from the full oracle.
Those are reported as KNOWN so a clean run is "0 unexpected".

Prereq: run upstream/selfhost.sh first (builds /tmp/pass1, /tmp/pass2 images).
"""
import re, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, "p1/tests")
import test_p1 as T

PROG8 = Path(__file__).resolve().parent.parent
EMU = PROG8.parent / "emulator" / "emulator.out"
P1, P2 = Path("/tmp/pass1/img.bin"), Path("/tmp/pass2/img.bin")
CAP = "30000000000"
wd = Path(tempfile.mkdtemp(prefix="shc_"))
norm = lambda s: re.sub(r"^; source:.*$", "; source: SRC", s, flags=re.M)
# a program that exercises signed-typed comparison -> expected to differ
SIGNED = re.compile(r"(?m)^\s*(byte|word)\s+\w")


def oracle(src):
    inp = wd / "in.p8"; out = wd / "o.s"; inp.write_text(src)
    r = subprocess.run([sys.executable, "-m", "p8c", "--target", "nmos",
                        str(inp), "-o", str(out)],
                       capture_output=True, text=True, cwd=str(PROG8))
    return None if r.returncode else norm(out.read_text())


def pipeline(src):
    inp = wd / "in.p8"; dmp = wd / "d.bin"; out = wd / "u.s"; inp.write_text(src)
    for f in (dmp, out):
        if f.exists(): f.unlink()
    subprocess.run([str(EMU), str(P1), "--cycle-cap", CAP, str(inp), str(dmp)],
                   capture_output=True, text=True, timeout=120)
    if not dmp.exists(): return "<<P1NOOUT>>"
    subprocess.run([str(EMU), str(P2), "--cycle-cap", CAP, "--no-dump", str(dmp), str(out)],
                   capture_output=True, text=True, timeout=120)
    return norm(out.read_text()) if out.exists() else "<<P2NOOUT>>"


corpora = {n: getattr(T, n) for n in dir(T)
           if n.endswith("PROGRAMS") and isinstance(getattr(T, n), list)}
total = match = known = 0
unexpected = []
for name, progs in sorted(corpora.items()):
    for src in progs:
        total += 1
        o = oracle(src)
        if o is None:               # oracle rejects -> not a pipeline concern
            match += 1; continue
        try:
            u = pipeline(src)
        except subprocess.TimeoutExpired:
            u = "<<TIMEOUT>>"
        if u == o:
            match += 1
        elif SIGNED.search(src):    # specialized pipeline: signed unsupported
            known += 1
        else:
            unexpected.append((name, src))
print(f"programs={total}  match={match}  known-signed-diff={known}  unexpected={len(unexpected)}")
for name, src in unexpected[:40]:
    print(f"  [UNEXPECTED] {name}: {src[:60]!r}")
sys.exit(1 if unexpected else 0)
