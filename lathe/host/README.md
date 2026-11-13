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
| `decl.py` | DECL, and reading and writing interface files. |
| `stmt.py` | STMT. |
| `expr.py` | EXPR: lazy operands. |
| `gen.py` | GEN: instruction selection and register tracking. |
| `fbuf.py` | FBUF: the function buffer and branch lengths. |
| `out.py` | OUT: the object file writer. |
| `asmblock.py` | ASM: the embedded assembler for `asm` blocks and functions. |
| `lathec.py` | The compiler's main program. |
| `link.py` | The linker's main program (with its own modules as it grows). |
| `driver/` | Ordinary Python, not ported: `lo.py` (read and write object files), `lodump.py` (print one), `lo2asm.py` (render as asm17 text), `build.py` (build and run a whole program). |

## Command lines

```bash
python3 lathe/host/lathec.py SOURCE.lth OUTDIR [IMPORTDIR...]
```

Compiles one module. The module name is the file name without `.lth`, in lower case. Writes `OUTDIR/name.lo` (object file, `../docs/object-format.md`) and `OUTDIR/name.li` (interface). `import x` reads `x.li` from `OUTDIR`, then from each `IMPORTDIR`. On an error it prints `FILE:LINE:COL: error N: text` to the error output and exits with status 1.

```bash
python3 lathe/host/link.py ENV MAINMODULE OUT.bin OUT.map OBJECT.lo...
```

Links a program whose entry is `MAINMODULE.main`. Objects are placed in the order given.

```bash
python3 lathe/host/driver/build.py SOURCE.lth -o OUT.bin [--env NAME] [--run] [--asm]
```

Finds the modules a program imports (in `lathe/rt/` and beside the source), compiles them in dependency order, links, and with `--run` runs the image on the emulator. `--asm` builds the image by the assembler path instead: `lo2asm` renders the objects and the map as asm17 text and `asm/pyasm.py` assembles it.

## The environment file

Text, one entry per line, `;` starts a comment. Version 1 (it grows towards the form in `../docs/architecture.md`):

```
cpu       6502          ; or 65c02
zeropage  $00 $FF       ; first and last address the linker may use
code      $0200 $BFFF   ; where code and constant data go
data      $C000 $EFFF   ; where variables go
start     host_start.start   ; the function the reset vector points at
```

The image runs from the start of `code` to `$FFFF`, with the reset vector at `$FFFC`, which is what the emulator's default machine loads. Environment files are in `lathe/env/`; `host.env` describes that machine.

## The map file

Text, one item per line: kind, address and size in four hex digits, name; a slot line adds the slot number and name.

```
F 0200 0012 hello.main            ; function, in placement order
D 0212 0006 hello.$1              ; constant data
V C000 0001 demo.count            ; module-level variable
S 0010 0002 demo.spaces 0 s       ; slot 0 of demo.spaces
C 0012 0001 demo.handler 0 code   ; parameter 0 of a pointer class
```

Only functions the linker kept are listed.

## Tests

`lathe/verify.sh` runs everything; `tools/check_all.sh lathe` calls it. Tests are Python `unittest` files in `lathe/tests/`, run from the repository root.

| Kind | Cases | Check |
|---|---|---|
| Unit | in the test file | One host module's functions. |
| Shape | `test_shape.py` | The rule above. |
| Snapshot | `tests/cases/snap/NAME.lth` | `lo2asm` of the compiled module equals `NAME.expected.asm`. |
| Error | `tests/cases/err/NAME.lth` | The first line is `; error N LINE COL`; the compiler must report exactly that. |
| End to end | `tests/cases/e2e/NAME.lth` | The program's output on the emulator equals `NAME.expected.out`. Built both ways (linker, and assembler path) once the linker exists; the two images must be identical. |
