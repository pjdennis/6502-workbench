# hardware: duplicates from the Michael Arduino directory

Split out of `hardware/michael/arduino/` on 2026-09-24 (`f7355c1`) because they duplicate live files. Kept at their old relative path.

- `michael/arduino/hello-again.s`: byte-identical to `firmware/programs/wendy/hello.s` (Ben Eater's hello world, copied to test the Michael board).
- `michael/arduino/compile_and_program.sh`: same as `tools/upload/compile_and_program.sh` (assemble and burn an AT28C256 with `minipro`); its `$HERE/../../../firmware/vasm` path assumed the old location and does not resolve from here.

Live successors: `hardware/michael/arduino/` (Arduino sketches), `firmware/programs/wendy/hello.s`, `tools/upload/`.
