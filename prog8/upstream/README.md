# Upstream-bootstrap target for the self-hosting Prog8 compiler

Goal: compile the self-hosting compiler (`../p1/p1.p8`) with the **upstream**
Prog8 compiler (not our bootstrap `p8c`) and run it on the emulator, proving
the compiler is valid upstream Prog8 and self-hosts from the official toolchain.

- `nmos.properties` -- a custom Prog8 compilation target for this repo's
  emulator (6502/65C02, no ROM, I/O via the emulator's `$F006+` syscall stubs,
  RAW output at `$0200`).
- `libraries/nmos/syslib.p8` -- the target's syslib (adapted from upstream's
  Neo6502 custom-target example; exit routed to the `$F00F` emulator stub).
- `mkimage.py` -- wraps a prog8 RAW binary into the emulator's
  `$0200..$FFFF` image (sets the `$FFFC` reset vector to the `$0200` entry).
- `build.sh <src.p8> <out.bin>` -- compile with upstream + wrap into an image.
- `setup.sh` -- fetch `prog8c.jar` + build the `64tass` assembler it needs.
- `hello.p8` -- smoke test (writes "HI\n" via the syscall stubs).
- `port_p1.py` -- transform `../p1/p1.p8` (p8c model) into upstream-legal source
  (`port_p1.py in.p8 out.p8`); exposes `port(src)` reused by the pipeline porter.
- `port_pipeline.py` -- port a pipeline pass (`p1_pass1_sh.p8` / `p1_pass2_sh.p8`),
  memory-slabbing the > 256-element arenas into raw-RAM peek/poke (upstream can't
  index word arrays past a byte). Also emits a per-pass `.properties` with the
  slab-base `memtop`.
- `selfhost.sh` -- build the pipeline with upstream prog8c, run it on the
  emulator to compile `p1.p8`, and diff against the p8c oracle.

Status: **DONE.** `bash setup.sh && bash selfhost.sh` builds the p1 pipeline with
upstream prog8c v12.1.1 for the `nmos` target, runs it on the emulator to compile
`p1.p8`, and the emitted `p1.s` is **byte-identical** to the p8c host oracle
(0-line normalized diff). The self-hosting compiler bootstraps from the official
toolchain. See `PORT_STATUS.md` for the full play-by-play (the three monolith
codegen divergences, the slab port, and the one pass2 codegen fix).
