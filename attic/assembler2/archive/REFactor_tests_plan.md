# Plan: Per-version test suites under assembler folders

> **Attic note:** historical. Paths (`22/`, `23/`, `editor/`, `assembler2/`) are from the old assembler2 layout; the live code is `asm/` (stages 00-17) and `editor/`. See `attic/assembler2/README.md`.


## Goals
- Move assembler test suites into per-version folders (e.g., `22/tests/`, `23/tests/`).
- Keep the test runner in the repo root (move from `tests/run_tests.py` to `run_tests.py`).
- For now, only the latest version (currently 22) gets tests; older versions stay as-is.
- Keep things simple; hard-code the latest assembler version in the runner.
- Update build/cleanup/watch scripts to match new paths.
- Use `git mv` for file moves.

## Target layout (initial)
- `run_tests.py` (moved to repo root)
- `22/tests/asm_tests.txt`
- `22/tests/file_stack_tests.txt`
- `22/tests/file_stack_test.asm`
- `tests/` folder remains only for legacy content (if anything), or becomes empty.

## Step-by-step plan

### 1) Move test runner to repo root
- `git mv tests/run_tests.py run_tests.py`
- Update any references to `tests/run_tests.py`:
  - `gogen.sh`
  - `README.md`

### 2) Move latest test suite into `22/tests/`
- `git mv tests/asm_tests.txt 22/tests/asm_tests.txt`
- `git mv tests/file_stack_tests.txt 22/tests/file_stack_tests.txt`
- `git mv tests/file_stack_test.asm 22/tests/file_stack_test.asm`

### 3) Update the test runner paths (hard-coded latest is OK)
- In `run_tests.py`, update:
  - Default test file list to `22/tests/asm_tests.txt` and `22/tests/file_stack_tests.txt`
  - File stack test program source to `22/tests/file_stack_test.asm` (if referenced)
  - Any path assumptions about `tests/` directory

### 4) Update build and watch scripts
- `asmtestgen.sh`
  - File stack build: update path to `22/tests/file_stack_test.asm`
- `gogen.sh`
  - Replace `tests/run_tests.py` with `run_tests.py`
  - Update watch list for `22/tests/*` paths
- `Makefile clean`
  - Update cleanup to remove any new per-version test outputs if needed
  - Ensure any `tests/` cleanup is still valid or removed

### 5) Update README and other docs
- `README.md`:
  - Update test runner command: `./run_tests.py`
  - Update tree docs to show `22/tests/` layout
  - Update instructions for creating `23` tests to use `23/tests/`

### 6) Validation
- Run `./asmtestgen.sh` (build chain + file stack program build)
- Run `./run_tests.py` (ensure defaults pick up new locations)
- Optional: run `gogen.sh` once to verify watch list is sane

## Notes / Constraints
- Keep latest version hard-coded in the runner for now.
- Don’t backfill older versions’ test suites yet.
- Keep changes minimal; avoid refactoring test formats.
