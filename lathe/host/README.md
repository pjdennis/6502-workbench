# Lathe host tools

The reference compiler and allocator, in Python. They are the first implementation, the test oracle, and the tools that build the Lathe-written compiler until it builds itself (`../docs/architecture.md`, "The host reference compiler").

## The one rule: write Lathe in Python

Every file here except those under `driver/` will be rewritten in Lathe, function for function, and the two versions must produce the same bytes. So the Python uses only what Lathe has. `../tests/test_shape.py` enforces the list below.

**Allowed**

- Module-level variables holding an `int` or `bool`.
- Module-level arrays of fixed size: `[0] * N` (a list of ints) or `bytearray(N)`, with `N` a named constant. Elements are assigned by index; the array never grows or shrinks.
- Module-level constants: ints, and byte strings (`b"..."`) used as read-only tables or texts.
- Functions whose parameters and results are ints or bools. A function returns nothing, one value, or a value and a `bool`.
- `if` / `elif` / `else`, `while`, `for i in range(a, b)` and `range(a, b, -1)`, `break`, `continue`, `return`.
- Integer arithmetic and comparison, `and` / `or` / `not` on bools, `&  |  ^  ~  <<  >>` on ints. Mask results to the width the Lathe type will have (`& 0xFF`, `& 0xFFFF`): Lathe wraps, Python does not.
- `import` of other host modules, used as `module.name`.

**Not allowed**

- Classes, dicts, sets, tuples as data, list methods (`append`, `pop`, slices that copy), comprehensions, generators, lambdas, closures, decorators, `try` / `except` / `raise`, `with`, string formatting, Python `str` values at all outside `driver/` and `env.py`.
- Recursion, except in functions named in `RECURSIVE` at the top of their module. Those become `recursive` functions in Lathe.
- Default arguments, keyword arguments, `*args`.
- Arithmetic that relies on values wider than 16 bits.

**How records are held.** As parallel arrays indexed by a small int (`sym_kind[i]`, `sym_type[i]`), which is Lathe's column storage, or as byte ranges in a `bytearray` heap reached through accessor functions.

**How text is held.** Names and strings live in a `bytearray` heap and are passed as an offset. Fixed texts such as mnemonics and messages are `b"..."` constants.

**Errors.** `err.fatal(number)` reports and exits. It never returns, and nothing catches it.

**The outside world** is reached only through `env.py`, which offers the calls of the emulator's host interface (`asm/17/environment.asm`): open, read a byte, write a byte, close, arguments, exit. On the target the same calls are `extern` declarations.

## Files

| File | Component (see `../docs/architecture.md`) |
|---|---|
| `env.py` | The host interface, in ordinary Python. Not ported: the target has the real thing. |
| `kernel.py` | Streams, the symbol heap, name hashing. |
| `err.py` | Error numbers and reporting. |
| `src.py` | SRC: the source stack. |
| `lex.py` | LEX. |
| `types.py` | The type table. |
| `decl.py` | DECL. |
| `stmt.py` | STMT. |
| `expr.py` | EXPR: lazy operands. |
| `gen.py` | GEN: instruction selection and register tracking. |
| `fbuf.py` | FBUF: the function buffer and branch lengths. |
| `out.py` | OUT: assembler text and frame records. |
| `asmblock.py` | ASM: inline assembly. |
| `lathec.py` | The compiler's main program: one module in, `.asm`, `.lfm` and `.li` out. |
| `alloc.py` | The allocator's main program: all `.lfm` in, `alloc.asm` and a map out. |
| `driver/` | Ordinary Python, not ported: builds a whole program by running the compiler on each module in order, then the allocator, then asm17 on the emulator. |

## Running

```bash
python3 lathe/host/lathec.py FILE.lth OUTDIR        # compile one module
python3 lathe/host/alloc.py ENV.cfg OUTDIR MODULE…  # allocate storage for a program
python3 lathe/host/driver/build.py FILE.lth -o OUT.bin [--env NAME] [--run]
```

Tests: `lathe/verify.sh`, which `tools/check_all.sh lathe` runs.
