#!/usr/bin/env python3
"""End-to-end tests for the wendy2c MONITOR ROM + simulated SPI disk.

Compiles program(s) with prog8c (-target wendy2.properties), stages them on a
temp disk alongside an 'autoexec' file, boots the monitor ROM with --disk (no
serial upload), and diffs the final LCD frame against a golden. The monitor
loads each autoexec line's program from disk over the $F800+ file-I/O OS
calls; programs return to the monitor on exit so multiple lines run in turn.

Skips cleanly if prog8c.jar / 64tass / vasm6502_oldstyle / emulator missing.
"""
from __future__ import annotations
import os, shutil, subprocess, tempfile, unittest
from pathlib import Path

# firmware/vasm: vasm6502_oldstyle with the firmware include path.
FW_VASM = Path(__file__).resolve().parents[4] / "firmware" / "vasm"

HERE = Path(__file__).resolve().parent
UP = HERE.parent
REPO = UP.parents[2]
EMU = REPO / "emulator" / "emulator.out"
JAR = Path(os.environ.get("PROG8C", "/tmp/prog8c.jar"))
MON_SRC = REPO / "firmware" / "boards" / "wendy2" / "wendy2c_monitor.s"
GOLDENS = HERE / "goldens"
OUT = UP / "out"

# An overlay routine for the storage-driven multibank demo (T6):
#   inc $0200 ; lda #'x' ; rts   -- bumps a shared counter, returns its tag
def _ov(tag: str) -> bytes:
    return bytes([0xEE, 0x00, 0x02, 0xA9, ord(tag), 0x60])

# golden name -> (autoexec text,
#                 {disk filename: demo basename to compile},
#                 {disk filename: raw bytes})
CASES = {
    "d2_autoexec": ("d2_autoexec\n", {"d2_autoexec": "d2_autoexec"}, {}),
    "d4_multi":    ("first\nsecond\n",
                    {"first": "d4_first", "second": "d4_second"}, {}),
    "t6_overlays": ("t6_overlays\n", {"t6_overlays": "t6_overlays"},
                    {"ov1": _ov("a"), "ov2": _ov("b"), "ov3": _ov("c")}),
}


def _have():
    if not JAR.exists():
        return False, f"prog8c jar not found at {JAR}"
    for t in ("64tass", "vasm6502_oldstyle"):
        if shutil.which(t) is None:
            return False, f"{t} not on PATH"
    if not EMU.exists():
        return False, f"emulator not built at {EMU}"
    return True, ""


def _compile(demo: str) -> Path:
    d = OUT / demo
    d.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["java", "-jar", str(JAR), "-target", "wendy2.properties", "-out", str(d),
         str(UP / "demos" / f"{demo}.p8")],
        cwd=str(UP), capture_output=True, text=True)
    binp = d / f"{demo}.bin"
    if r.returncode != 0 or not binp.exists():
        raise AssertionError(f"compile {demo} failed:\n{r.stdout}\n{r.stderr}")
    return binp


def _monitor_rom() -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    rom = OUT / "wendy2c_monitor.bin"
    r = subprocess.run(
        [str(FW_VASM), "-wdc02", "-wfail", "-Fbin", "-dotdir",
         "-ignore-mult-inc", "-esc", "-o", str(rom), str(MON_SRC)],
        cwd=str(REPO), capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"monitor build failed:\n{r.stdout}\n{r.stderr}")
    return rom


def _run(autoexec: str, files: dict, raw: dict) -> str:
    rom = _monitor_rom()
    disk = Path(tempfile.mkdtemp(prefix="wdisk_mon_"))
    try:
        for diskname, demo in files.items():
            shutil.copy(_compile(demo), disk / diskname)
        for diskname, data in raw.items():
            (disk / diskname).write_bytes(data)
        (disk / "autoexec").write_text(autoexec)
        r = subprocess.run(
            [str(EMU), str(rom), "--machine", "wendy2c", "--disk", str(disk),
             "--cycle-cap", "6000000"], capture_output=True, text=True)
        rows = [ln for ln in r.stderr.splitlines()
                if ln.startswith("  |") and ln.endswith("|")]
        if not rows:
            raise AssertionError(f"no LCD frame:\n{r.stdout}\n{r.stderr}")
        return "\n".join(rows) + "\n"
    finally:
        shutil.rmtree(disk, ignore_errors=True)


_ok, _why = _have()


@unittest.skipUnless(_ok, _why)
class Wendy2MonitorGoldens(unittest.TestCase):
    pass


def _make(autoexec, files, raw, golden):
    def t(self):
        self.assertEqual(_run(autoexec, files, raw), golden.read_text())
    return t


for _name, (_ax, _files, _raw) in CASES.items():
    _g = GOLDENS / f"{_name}.expected.lcd"
    if _g.exists():
        setattr(Wendy2MonitorGoldens, f"test_{_name}", _make(_ax, _files, _raw, _g))


# ---- packed multi-segment image (.w2x) cases ----
# golden name -> (main demo, [(bank, addr, bytes), ...])
PACKED = {
    "d5_banked_app": ("d5_banked_app", [
        (1, 0xA000, _ov("1")), (2, 0xA000, _ov("2")), (3, 0xA000, _ov("3")),
    ]),
}


def _run_packed(main_demo: str, segs: list) -> str:
    rom = _monitor_rom()
    disk = Path(tempfile.mkdtemp(prefix="wdisk_pack_"))
    work = Path(tempfile.mkdtemp(prefix="wpack_"))
    try:
        main_bin = _compile(main_demo)
        args = ["python3", str(UP / "wendy2_pack.py"), "-o", str(disk / "app"), str(main_bin)]
        for bank, addr, data in segs:
            blob = work / f"seg{bank}.bin"
            blob.write_bytes(data)
            args.append(f"{blob}@{bank}@{addr:X}")
        r = subprocess.run(args, capture_output=True, text=True)
        if r.returncode != 0:
            raise AssertionError(f"pack failed:\n{r.stdout}\n{r.stderr}")
        (disk / "autoexec").write_text("app\n")
        r = subprocess.run(
            [str(EMU), str(rom), "--machine", "wendy2c", "--disk", str(disk),
             "--cycle-cap", "6000000"], capture_output=True, text=True)
        rows = [ln for ln in r.stderr.splitlines()
                if ln.startswith("  |") and ln.endswith("|")]
        if not rows:
            raise AssertionError(f"no LCD frame:\n{r.stdout}\n{r.stderr}")
        return "\n".join(rows) + "\n"
    finally:
        shutil.rmtree(disk, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)


def _make_packed(main_demo, segs, golden):
    def t(self):
        self.assertEqual(_run_packed(main_demo, segs), golden.read_text())
    return t


for _name, (_main, _segs) in PACKED.items():
    _g = GOLDENS / f"{_name}.expected.lcd"
    if _g.exists():
        setattr(Wendy2MonitorGoldens, f"test_{_name}", _make_packed(_main, _segs, _g))


if __name__ == "__main__":
    unittest.main(verbosity=2)
