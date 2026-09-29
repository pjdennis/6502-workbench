"""tinyp8 driver -- a *6502-native* compiler proof-of-concept.

Workflow:
    1. Build tinyp8.bin (the compiler) from tinyp8.s via vasm.
    2. Run tinyp8.bin inside the emulator with (source.tp8, output.body)
       as positional args.  tinyp8 reads source via $F018, emits machine
       code to the output file via $F024.  Compilation happens entirely
       on the simulated 6502.
    3. Wrap the body in a runnable binary by placing it at $0200 and
       attaching a reset vector at $FFFC -> $0200.
    4. Optionally run that binary inside the emulator to capture its
       stdout (via --output) and assert on it.

CLI:
    python3 -m tinyp8 source.tp8 -o source.body [--run-out]

The --run-out flag chains step 4 and prints the compiled program's
stdout to *this* script's stdout.  Without --run-out we stop after
step 3 and just leave .body and .runnable on disk.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# firmware/vasm: vasm6502_oldstyle with the firmware include path.
FW_VASM = Path(__file__).resolve().parents[3] / "firmware" / "vasm"


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
EMU = REPO / "emulator" / "emulator.out"
TINYP8_SRC = HERE / "tinyp8.s"
TINYP8_BIN = HERE / "out" / "tinyp8.bin"
COMPILED_LOAD_ADDR = 0x0200  # where the compiled program runs
RESET_VECTOR_ADDR = 0xFFFC


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def build_tinyp8(force: bool = False) -> Path:
    """Assemble tinyp8.s -> tinyp8.bin via vasm6502_oldstyle. Cached."""
    if TINYP8_BIN.exists() and not force \
            and TINYP8_BIN.stat().st_mtime >= TINYP8_SRC.stat().st_mtime:
        return TINYP8_BIN
    TINYP8_BIN.parent.mkdir(exist_ok=True)
    r = subprocess.run(
        [str(FW_VASM), "-Fbin", "-dotdir", "-ignore-mult-inc",
         "-esc", "-wfail", "-o", str(TINYP8_BIN), str(TINYP8_SRC)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit("vasm failed building tinyp8.bin")
    return TINYP8_BIN


def run_tinyp8(source_path: Path, body_path: Path) -> None:
    """Invoke the on-emulator compiler: tinyp8 source -> body."""
    bin_path = build_tinyp8()
    r = subprocess.run(
        [str(EMU), str(bin_path), str(source_path), str(body_path),
         "--no-dump"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit(
            f"tinyp8 compilation failed (emulator exit {r.returncode})"
        )


def wrap_body_as_runnable(body: bytes, load_addr: int = COMPILED_LOAD_ADDR) -> bytes:
    """Build a runnable 6502 image from a compiled-body blob.

    Layout in the resulting file (loaded at `load_addr` via --load):
      [body bytes][zero padding][reset vector low/high][irq vector 0/0]
    Total file size is (0x10000 - load_addr) bytes; the runnable
    occupies memory[load_addr ..= 0xFFFF].
    """
    out = bytearray(body)
    pad = (RESET_VECTOR_ADDR - load_addr) - len(body)
    if pad < 0:
        raise ValueError(
            f"compiled body is {len(body)} bytes; cannot fit between "
            f"${load_addr:04x} and ${RESET_VECTOR_ADDR:04x}"
        )
    out.extend(b"\x00" * pad)
    out.extend(load_addr.to_bytes(2, "little"))   # reset vector -> body start
    out.extend(b"\x00\x00")                       # irq vector (unused)
    assert len(out) == 0x10000 - load_addr
    return bytes(out)


def run_compiled(runnable_path: Path, capture_stdout_path: Path) -> str:
    """Run the wrapped binary on the emulator; return its stdout text."""
    r = subprocess.run(
        [str(EMU), str(runnable_path),
         "--load", f"{COMPILED_LOAD_ADDR:x}",
         "--output", str(capture_stdout_path),
         "--no-dump"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit(
            f"compiled program crashed (emulator exit {r.returncode})"
        )
    return capture_stdout_path.read_text()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tinyp8")
    p.add_argument("source", help="path to a .tp8 source file")
    p.add_argument("-o", "--output", help="path for the compiled .body "
                                          "(default: <source>.body)")
    p.add_argument("--run-out", action="store_true",
                   help="also wrap the body, run it on the emulator, "
                        "and print its stdout to ours")
    p.add_argument("--rebuild", action="store_true",
                   help="force a rebuild of tinyp8.bin even if it's up-to-date")
    args = p.parse_args(argv)

    if not have("vasm6502_oldstyle"):
        sys.stderr.write("tinyp8: vasm6502_oldstyle required on PATH\n")
        return 1
    if not EMU.exists():
        sys.stderr.write(f"tinyp8: emulator missing at {EMU}\n")
        return 1

    if args.rebuild:
        build_tinyp8(force=True)

    src = Path(args.source).resolve()
    body = Path(args.output).resolve() if args.output else src.with_suffix(".body")
    run_tinyp8(src, body)
    print(f"tinyp8: compiled {src.name} -> {body.name} ({body.stat().st_size} bytes)")

    if args.run_out:
        runnable = body.with_suffix(".runnable")
        runnable.write_bytes(wrap_body_as_runnable(body.read_bytes()))
        stdout_path = body.with_suffix(".stdout")
        text = run_compiled(runnable, stdout_path)
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
