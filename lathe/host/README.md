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
- Recursion, except in functions named in `RECURSIVE` at the top of their module. Those become `recursive` functions in Lathe. (The list is a marker for the tests, not a variable: it is the one name that may be a Lathe keyword.)
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
| `fold.py` | Constant arithmetic, and the numbers of the operators. |
| `fbuf.py` | FBUF: the function buffer and branch lengths. |
| `out.py` | OUT: the object file writer. |
| `reg.py` | GEN, lowest part: the stack of lazy operands, the frame, who owns the registers and what they are known to hold. |
| `cond.py` | GEN, middle part: comparisons and conditions. |
| `gen.py` | GEN, top part: arithmetic with destination passing, stores, conversions, calls, the function being compiled, initial values. |
| `asmblock.py` | ASM: the embedded assembler for `asm` blocks and functions. It reaches variables and slots through the symbol table and REG's frame. |
| `expr.py` | EXPR: expressions and written types, parsed into operands on GEN's stack. |
| `stmt.py` | STMT: statements, and variable declarations (a body has them too). |
| `decl.py` | DECL, and reading and writing interface files. |
| `lathec.py` | The compiler's main program. |
| `link.py` | The linker's main program (with its own modules as it grows). |
| `driver/` | Ordinary Python, not ported: `lo.py` (read and write object files), `lodump.py` (print one), `lo2asm.py` (render as asm17 text), `build.py` (build and run a whole program), `boards.py` (run a program on an emulated board and read its LCD). |

## Command lines

```bash
python3 lathe/host/lathec.py [-c6502|-c65c02] [-dNAME[=NUMBER]]... SOURCE.lth OUTDIR [IMPORTDIR...]
```

Compiles one module. The module name is the file name without `.lth`, in lower case. Writes `OUTDIR/name.lo` (object file, `../docs/object-format.md`) and `OUTDIR/name.li` (interface). `import x` reads `x.li` from `OUTDIR`, then from each `IMPORTDIR`. On an error it prints `FILE:LINE:COL: error N: text` to the error output and exits with status 1.

The options come before the source file, in any order; a later `-c` wins. They give the constants that `#if` tests (`../docs/language.md`, "Conditional compilation"), predeclared like `true`, so a module's own declaration of the same name hides them:

| Option | Means |
|---|---|
| `-c6502`, `-c65c02` | The CPU the module is for: the CPU byte of its `MOD` record, and the instructions `asm` accepts. Predeclares the `bool` constant `cpu_65c02`, which is `false` without the option. |
| `-dNAME` | Predeclares the constant `NAME` (a name the language allows, not a keyword; case is folded) as the `bool` `true`. |
| `-dNAME=NUMBER` | Predeclares `NAME` as the decimal `NUMBER`, 0 to 65535, a number of no type yet (like `const NAME = NUMBER`). |

Anything else that starts with `-`, a name given twice, or a missing file name is error 60 (or 41 for the name).

```bash
python3 lathe/host/link.py ENV MAINMODULE OUT.bin OUT.map OBJECT.lo...
```

Links a program whose entry is `MAINMODULE.main`. Objects are placed in the order given.

```bash
python3 lathe/host/driver/build.py SOURCE.lth -o OUT.bin [--env NAME] [--run] [--asm] [--define NAME[=NUMBER]]...
```

Finds the modules a program imports (in `lathe/rt/` and beside the source; an `import` inside `#if` is found and compiled whatever the condition), compiles them in dependency order with `-c` from the environment's `cpu` entry, `-d` for each of its `define` entries and for each `--define`, links, and with `--run` runs the image on the emulator. `--asm` builds the image by the assembler path instead: `lo2asm` renders the objects and the map as asm17 text and `asm/pyasm.py` assembles it.

`--env NAME` reads `lathe/env/NAME.env` (default `host`). With `--env host`, `--run` runs the image on the emulator's default machine, copies the program's output and exits with the program's status. With `--env michael` or `--env wendy2`, `--run` runs the program on that board (`../docs/boards.md`) and prints the text the LCD shows when it stops: one line per LCD row, trailing spaces removed, and nothing else. A run that reaches the cycle cap without stopping is an error. What the driver knows about each board (emulator options, cycle cap, how to read the result) is in `driver/boards.py`; the load address is the start of the environment's `code` range.

## The environment file

Text, one entry per line, `;` starts a comment. Version 1 (it grows towards the form in `../docs/architecture.md`):

```
cpu       6502          ; or 65c02
zeropage  $00 $FF       ; first and last address the linker may use
code      $0200 $BFFF   ; where code and constant data go
data      $C000 $EFFF   ; where variables go
stack     $FF           ; optional: the start-up code sets the stack pointer
exit      call $F00F    ; when main returns: call ADDR with A = 0, or `loop`, `return` or `stop`
output    image         ; optional: `image` (the default) or `raw`
define    FAST          ; any number of these: a constant for #if, the bool true
define    LEVEL $10     ; or a number, 0 to $FFFF
```

`define` is for the compiler only: `build.py` passes it on as `-dNAME` or `-dNAME=NUMBER`, and the linker skips it, as it skips any entry it does not know. The linker writes the start-up code from the other entries (`../docs/object-format.md`, "Initial values and start-up"). `exit stop` ends it with `STP` (`$DB`), which only the 65C02 has: it needs `cpu 65c02`, or the link fails with error 39.

The output file:

| Entry | The file holds |
|---|---|
| `output image` | Memory from the start of `code` to `$FFFF`, with the reset vector at `$FFFC` pointing at `$start`. This is what the emulator's default machine loads. |
| `output raw` | The bytes from the start of `code` through the last byte the linker placed there. No padding and no vectors. `$start` is first, so the load address is the entry. |

Environment files are in `lathe/env/`:

| File | Machine |
|---|---|
| `host.env` | The emulator's default machine, with host services (`output image`, `exit call $F00F`). |
| `michael.env` | Michael, loaded at `$2000` (`output raw`, `exit stop`). |
| `wendy2.env` | Wendy 2, loaded at `$4000` (`output raw`, `exit stop`). |

`../docs/boards.md` describes the three machines.

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
| 2 | Constant | type (as below, or 6 for a number that has no type yet, 7 for such a number below zero, 8 for `nil`); value (2), in two's complement, sign-extended if the type is signed. A constant of an array type is a table: its value is 0, and it is the constant data `module.name`. |
| 3 | Variable | type; placement (1): 0 none, 1 at a fixed address, which follows (2), 2 declared `zp`, 4 declared `nozp`. |

- **Function flags:** bit 0 `extern`: a routine at a fixed address; bit 2 `asm`: a function whose body is assembly, called like an `extern` one (parameters and results in registers, no slots) but through its symbol. The other bits are kept for `recursive` and `inline`.
- **A member** is a type and a register (1 byte): 0 none, 1 `a`, 2 `x`, 3 `y`, 4 `ax`, 5 `ay`, 6 `xy`, 7 `c`. A parameter with register 0 is the callee's slot of the same number. A result always has its register: for a Lathe function that is `a` for a one-byte value, `ax` for a two-byte one and `c` for a `bool`.
- **A type** is 1 `byte`, 2 `sbyte`, 3 `word`, 4 `int`, 5 `bool`; `$10` followed by a type: a pointer to it; `$11`, the number of elements (2) and a type: an array of them, stored by column; or `$12` and the same: an array declared `rows`. Records and named types will take further codes.
- **A variable** that is neither `zp` nor at a fixed address is used through instructions in the absolute form, which the linker shrinks if it lands in zero page; one declared `zp` is used through zero page instructions from the start. One at a fixed address has no symbol in any object file.

Entries are in the order of the declarations. Kinds still to come: types (their definition, before any entry that uses them) and `inline` functions (the function entry, then its saved tokens with their length in front). A reader that meets a kind or version it does not know stops with error 51.

## Errors

Every error has a number; `err.py` lists them with their texts. 1 to 19 are about characters and tokens, 20 to 39 syntax (39 is "not implemented yet"), 40 to 59 meaning, 60 to 69 the command line and files, 70 to 98 a capacity of the compiler that was exceeded, 99 a fault in the compiler itself, 100 to 139 meaning again (40 to 59 filled up; 120 to 139 are arrays, strings and pointers), and 140 to 159 `asm` blocks and functions; the top of `err.py` has the table. A lexical error is reported at the character it was found at or at the start of its token; any other error at the start of the token that is wrong. For a value of the wrong type or out of range that means:

- operands that do not suit an operator: at the operator;
- a value that does not suit what it is given to (an assignment, an argument, a `return`, an initial value, a constant's type): at the first token of the value;
- a test that is not a `bool`: at the first token of the test;
- something that cannot be assigned to: at its first token.

A new error takes the next free number of its group.

## Tests

`lathe/verify.sh` runs everything; `tools/check_all.sh lathe` calls it. Tests are Python `unittest` files in `lathe/tests/`, run from the repository root: `python3 -m unittest discover -s lathe/tests`.

| Kind | Cases | Check |
|---|---|---|
| Unit | in the test file | One host module's functions. |
| Shape | `test_shape.py` | The rule above. |
| Snapshot | `tests/cases/snap/NAME.lth` | `lo2asm` of the compiled module equals `NAME.expected.asm`. |
| Error | `tests/cases/err/NAME.lth` | The first line is `; error N LINE COL`; the compiler must report exactly that. A line `; options ...` before `module` gives the compiler options. |
| End to end | `tests/cases/e2e/NAME.lth` | The program's output on the emulator equals `NAME.expected.out`. Built both ways (linker, and assembler path) once the linker exists; the two images must be identical. |
| End to end on a board | `tests/cases/e2e-michael/NAME.lth`, `tests/cases/e2e-wendy2/NAME.lth` | Built with `michael.env` or `wendy2.env`, both ways, with identical files required. The text the board's LCD shows when the program stops equals `NAME.expected.out`: one line per row, trailing spaces removed. |
| Boards | `test_boards.py` | Object files built with `lo.Builder` that show `HI` on each board's LCD, linked, built by the assembler path and run as `build.py --run` runs them. |
| Output forms | `test_lk_output.py` | `output raw`, `output image` and `exit stop`, by hand-worked bytes and by the assembler path. |

`lathe/tests/fuzz.py` is not part of the suite. It compiles and runs random programs and compares what they print with their true results: run it (`fuzz.py expr 1 200`, `fuzz.py stmt 1 200`) after any change to how code is generated. In stage 2a it found four faults that the cases written by hand had not; in stage 2b, once its statements used arrays and pointers, one more (a word in A and X stored into an element whose index needs X).

A snapshot or end-to-end case can import modules that lie beside it, and a line `; defines NAME NAME=NUMBER ...` before its `module` line builds it with those defines. A file called `lib*.lth` is such a module and not a case. Each expected output in `e2e/` was first compared with the output of a separate Python model of the program, so it is what the program must print and not merely what the compiler made it print.
