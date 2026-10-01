# Tom Harte ProcessorTests harness

Cycle-exact CPU validation against the SingleStepTests/65x02 vectors.
Each opcode has up to 10000 JSON test cases pinning every CPU register,
RAM cell, and bus access for one instruction.

## Upstream

- Project: `SingleStepTests/65x02`
- URL: https://github.com/SingleStepTests/65x02
- Format per file: a JSON array of test objects with `name`, `initial`,
  `final`, and `cycles` keys. See the upstream README for details.

The data set is large (multiple GB), so it is **not** vendored here.
Run `tests/harte/fetch.sh` to clone it into `data/` (gitignored).

## Building and running

```
make harte                # runs all opcodes for both 6502 and wdc65c02
make harte HARTE_LIMIT=10 # only first 10 vectors per opcode (fast)
```

When `data/` is missing, `make harte` prints a warning and exits 0
(the harness is opt-in); it is not part of `make test` or `check_all`.

## Known deltas

NMOS undocumented opcodes whose Harte-modeled behavior diverges from
our implementation are listed in `known-deltas.md` and silently skipped
by the runner with the cited reason.

## Files

- `fetch.sh` -- clones SingleStepTests/65x02 into `data/`
- `data/` -- gitignored upstream JSON
- `known-deltas.md` -- per-opcode allow-list with rationale
