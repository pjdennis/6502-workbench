# Stage 17 tests

| Path | What it is |
|---|---|
| `asm/*.txt` | The assembler test suites (the executable specification of the syntax), run by `../../run_tests.py` and by the native runner `17/test_runner.asm`. The subdirectories `include/`, `ifdefs/`, `overflow/` and `scope/` hold files the tests `.include`. |
| `source_stack/` | Tests for the source stack alone: `source_stack_test.asm` is the harness, `source_stack_tests.txt` the cases (modes `echo`, `lines`, `info`, `memory`, `frames`, `oom`; format in the file's header). |
| `test_runner/test_runner_dir.py` | Checks the native runner's directory mode. |
| `opendir/` | `opendir_test.asm` and `test_opendir.py`: the host `opendir` call. |

## Format of `asm/*.txt`

Tests are separated by a line `---`. Lines starting with `#` between tests are comments.

| Field | Meaning |
|---|---|
| `NAME:` | Test identifier. |
| `DESCRIPTION:` | Optional one-line description. |
| `INPUT:` | Source text follows, one line per following line, each prefixed `N: ` (the prefix is stripped). `[text]` brackets preserve leading or trailing spaces. |
| `ARGS:` | Command-line arguments for the assembler (default `debug`), e.g. `define:X`. |
| `EXPECT_HEX:` | Expected output bytes, hex. |
| `EXPECT_FWDREF:` | Expected forward-reference list entries. |
| `EXPECT_ERROR:` | Expected error code (decimal, as in `17/errors.asm`). |
| `EXPECT_LINE:` | Expected line number of the error. |
| `EXPECT_MSG:` | Expected error message. |
| `EXPECT_STDERR:` | Expected stderr text follows, as for `INPUT:`. |
| `SKIP:` | Skip the test, with the reason. |
| `MISSING_INPUT` | Run with no input file. |

`FILE name:` (extra input files) and `EXPECT_STDOUT:` are also understood by `run_tests.py`, and `MODE:` / `TYPE:` select the source-stack test type.

Run them: `python3 run_tests.py -q` (from `asm/`, after `./asmtestgen.sh`), or natively inside the emulator with the test runner build (`asmtestgen.sh` lines for `define:enable_test_runner`).
