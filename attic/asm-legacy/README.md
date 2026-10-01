# asm-legacy: early asm2 tests and scripts

What it is: files that lived at `toolchain/asm2/legacy/` (moved here 2026-09-29, `ae4defb`, pure `git mv`). They date from early asm2, before it had per-stage directories and before the chain was renumbered to `00`-`17` (2026-02-13).

- `bootstrap0.sh`: builds a C bootstrap assembler (`asm0c.c`, `asm0.asm`, names from before the stage directories; the equivalents are now `asm/00/asm.c` and `asm/00/asm.asm`) and checks that the stage-0 assembler self-assembles. It will not run as is.
- `instgen13_table.py`: Python copy of the scramble table from asm1's `hash_table13.asm`, used to work out the instruction-name hashes.
- `test*.asm`, `test_inc*.asm`: small test programs that include old stage paths such as `11/environment.asm`.
- `tests/asm18_tests.txt` to `asm21_tests.txt`: old test suites for assemblers that no longer exist (stages 18-21 were renumbered away), `generate_scope_tests.py`, and vim syntax files for the test format (`asmtest.vim`, `ftdetect-asmtest.vim`).
- `claude-plans/` (was `toolchain/asm2/.claude/`): two finished plans, `accumulator_syntax_migration.md` and `operand_consolidation_plan.md` (asm18/19 era). Both are marked COMPLETE. Their paths and `./asmtestgen.sh` commands are of that time.

Why it is parked: superseded by the per-stage suites. Nothing here runs against the current tree.

Live successor: `asm/` (stage tests are in `asm/NN/tests/`, run with `tools/check_all.sh asm`).
