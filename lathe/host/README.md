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
- A Lathe keyword as a name (`end`, `type`, `word`, `at`, …), or two names in one file that differ only in case: Lathe folds case, so `DIGITS` and `digits` would be one name. `../tests/test_names.py` checks the compiler's files.

**How records are held.** As parallel arrays indexed by a small int (`sym_kind[i]`, `sym_type[i]`), which is Lathe's column storage, or as byte ranges in a `bytearray` heap reached through accessor functions.

**How text is held.** Names and strings live in a `bytearray` heap and are passed as an offset. Fixed texts such as mnemonics and messages are `b"..."` constants.

**Errors.** `err.fatal(number)` reports and exits. It never returns, and nothing catches it.

**The outside world** is reached only through `env.py`, which offers the calls of the emulator's host interface (`asm/17/environment.asm`): open, read a byte, write a byte, close, arguments, exit. On the target the same calls are `extern` declarations.

**Starting.** A tool's file ends with `if env.is_program(__name__):` and a call of its `main()`. `env.is_program` takes the arguments from the command line; the tool itself holds no Python string.

**Modules do not import each other.** Lathe forbids import cycles, so the host files do too: each of the compiler's files imports only files above it in the table below (`../tests/test_layers.py`).

## Files

| File | Component (see `../docs/architecture.md`) |
|---|---|
| `env.py` | The host interface, in ordinary Python. Not ported: the target has the real thing. |
| `err.py` | Error numbers and reporting. |
| `kernel.py` | Text memory, streams, the name heap, the symbol table. |
| `src.py` | SRC: the source stack. |
| `lex.py` | LEX. |
| `typetab.py` | The type table. (Not `types.py`: that name would hide Python's own `types` module from every program started in this directory.) |
| `fbuf.py` | FBUF: the function buffer and branch lengths. |
| `out.py` | OUT: the object file writer. |
| `gen.py` | GEN: the stack of lazy operands, instruction selection and register tracking. |
| `asmblock.py` | ASM: the embedded assembler for `asm` blocks and functions. |
| `expr.py` | EXPR: expressions and written types, parsed into operands on GEN's stack. |
| `stmt.py` | STMT. |
| `decl.py` | DECL, and reading and writing interface files. |
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
stack     $FF           ; optional: the start-up code sets the stack pointer
exit      call $F00F    ; when main returns: call ADDR with A = 0, or `loop`, or `return`
```

The linker writes the start-up code from these entries (`../docs/object-format.md`, "Initial values and start-up").

The image runs from the start of `code` to `$FFFF`, with the reset vector at `$FFFC`, which is what the emulator's default machine loads. Environment files are in `lathe/env/`; `host.env` describes that machine.

## The map file

Text, one item per line: kind, address and size in four hex digits, name; a slot line adds the slot number and name.

```
F 0200 0012 hello.main            ; function, in placement order
F 0212 0012 hello.main@1          ; a further copy of it, for context 1
F 0224 0008 hello.tick 1          ; a first copy for a context other than 0
D 022C 0006 hello.$1              ; constant data
V C000 0001 demo.count            ; module-level variable
S 0010 0002 demo.spaces 0 s       ; slot 0 of demo.spaces
S 0020 0002 demo.spaces@1 0 s     ; slot 0 of its copy for context 1
C 0012 0001 demo.handler 0 code   ; parameter 0 of a pointer class
```

Only functions the linker kept are listed: those reachable from an entry point, and those whose address kept code or constant data takes (`../docs/code-model.md`, "Sharing frames"). A function reachable from several contexts (`../docs/code-model.md`, "Interrupts") has one F line and one set of S lines per copy. Its first copy, for the lowest of those contexts, has the function's name; each further copy, for context N, is `name@N`. Context 0 is the main program and 1, 2… the interrupt functions in object order. An F line of a first copy whose context is not 0 (a function only interrupt contexts reach) ends with that context's number, so that every copy's context is known.

## The interface file

`name.li` lists what a module exports. It is binary, and is read straight into the symbol table: no tokens, no parsing. Numbers are little-endian and a string is a length byte and its characters, as in object files.

```
header   "LI", version (1 byte, value 1), module name (string)
entries  each: kind (1 byte, not 0), name (string), then what that kind has
end      a 0 byte
```

| Kind | Entry | After the name |
|---|---|---|
| 1 | Function | flags (1); if flag bit 0 is set, the address (2); number of parameters (1) and that many members; number of results (1) and that many members. |

- **Function flags:** bit 0 `extern`: a routine at a fixed address. The other bits are kept for `recursive`, `asm` and `inline`.
- **A member** is a type and a register (1 byte): 0 none, 1 `a`, 2 `x`, 3 `y`, 4 `ax`, 5 `ay`, 6 `xy`, 7 `c`. A parameter with register 0 is the callee's slot of the same number.
- **A type** is 1 `byte`, 2 `sbyte`, 3 `word`, 4 `int`, 5 `bool`, or `$10` followed by a type: a pointer to it. Arrays, records and named types will take further codes.

Entries are in the order of the declarations. Kinds still to come: constants (type and value), variables (type), types (their definition, before any entry that uses them) and `inline` functions (the function entry, then its saved tokens with their length in front). A reader that meets a kind or version it does not know stops with error 51.

## Errors

Every error has a number; `err.py` lists them with their texts. 1 to 19 are about characters and tokens, 20 to 39 syntax (39 is "not implemented yet"), 40 to 59 meaning, 60 to 69 the command line and files, 70 to 98 a capacity of the compiler that was exceeded, and 99 is a fault in the compiler itself. A lexical error is reported at the character it was found at or at the start of its token; any other error at the start of the token that is wrong, except that an argument which does not fit its parameter is reported at the argument's first token.

## Tests

`lathe/verify.sh` runs everything; `tools/check_all.sh lathe` calls it. Tests are Python `unittest` files in `lathe/tests/`, run from the repository root: `python3 -m unittest discover -s lathe/tests`.

| Kind | Cases | Check |
|---|---|---|
| Unit | in the test file | One host module's functions. |
| Shape | `test_shape.py` | The rule above. |
| Snapshot | `tests/cases/snap/NAME.lth` | `lo2asm` of the compiled module equals `NAME.expected.asm`. |
| Error | `tests/cases/err/NAME.lth` | The first line is `; error N LINE COL`; the compiler must report exactly that. |
| End to end | `tests/cases/e2e/NAME.lth` | The program's output on the emulator equals `NAME.expected.out`. Built both ways (linker, and assembler path) once the linker exists; the two images must be identical. |
