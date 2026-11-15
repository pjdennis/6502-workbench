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
| `kernel.py` | Text memory, token memory (INLINE's saved tokens), streams, the name heap, the symbol table. The other modules reach a symbol's columns only through `byte_of(s, C_X)`, `word_of(s, C_X)`, `set_byte()`, `set_word()`, `member_type_of(m)` and `member_value_of(m)`: in the twin they are in the region `SYMS` (`../docs/configurations.md`, "The symbol table in a region"). |
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
| `inline.py` | (Its twin is `lathe/src/inlines.lth`, module `inlines`: `inline` is a keyword.) The saved tokens of `inline` functions (SRC replays them, LEX reads them), what is found out about each body, the scope names in an expansion are looked up in, and the parameters and slots of the expansions under way. |
| `parts.py` | The pieces of EXPR and STMT that reach no cycle of their calls: type keywords, names and fields, the operators of each level and the operands they combine, a string as a value, a `for` loop's variable and step, the code of `with` blocks. A module of its own so that EXPR fits a bank of the BBC (2026-11-15). |
| `expr.py` | EXPR and STMT: expressions and written types, parsed into operands on GEN's stack; statements, and variable declarations (a body has them too). One file, because an `inline` call in an expression compiles statements. |
| `decl.py` | DECL, and reading and writing interface files. |
| `lathec.py` | The compiler's main program. |
| `link.py` | The linker's main program (with its own modules as it grows). |
| `driver/` | Ordinary Python, not ported: `lo.py` (read and write object files), `lodump.py` (print one), `lo2asm.py` (render as asm17 text), `build.py` (build and run a whole program), `boards.py` (run a program on an emulated board and read its LCD), `bbcrom.py` (a module image of BBC programs, and its loader: `../docs/boards.md`, "The ROM module"). |

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
python3 lathe/host/driver/build.py SOURCE.lth -o OUT.bin [--env NAME] [--run] [--asm] [--disk DIR] [--define NAME[=NUMBER]]...
```

Finds the modules a program imports (in `lathe/rt/` and beside the source; an `import` inside `#if` is found and compiled whatever the condition), and the run-time modules the compiled objects import without an `import` line (an `IMP` record the compiler writes, such as `rt_frame` for a module with calls that save a recursive function's frame; they are compiled after the others and linked last), compiles them in dependency order with `-c` from the environment's `cpu` entry, `-d` for each of its `define` entries and for each `--define`, links, and with `--run` runs the image on the emulator. `--asm` builds the image by the assembler path instead: `lo2asm` renders the objects and the map as asm17 text and `asm/pyasm.py` assembles it.

An environment that places code in a window (below) makes `build.py` compile and link the far-call module its `farcall` entry names, as it does `rt_frame`, and copy the bank or overlay files the linker wrote beside the image; `--run` puts them in the `--disk` directory, or runs the default machine in the image's directory, where overlays are loaded from. Such a program cannot be built by the assembler path: `--asm` is an error.

`--env NAME` reads `lathe/env/NAME.env` (default `host`). With `--env host`, `--run` runs the image on the emulator's default machine, copies the program's output and exits with the program's status. With `--env michael` or `--env wendy2`, `--run` runs the program on that board (`../docs/boards.md`) and prints the text the LCD shows when it stops: one line per LCD row, trailing spaces removed, and nothing else. A run that reaches the cycle cap without stopping is an error. With `--env wendy2disk`, `--run` runs the program with `--disk` on the directory `--disk DIR` (a temporary one without it), whose file `args` holds the arguments, one a line; it prints the file `out` the program wrote, copies `errors` to the error output and exits with the status in the file `status` (`../docs/boards.md`, "Wendy 2 with files"). What the driver knows about each board (emulator options, cycle cap, how to read the result) is in `driver/boards.py`; the load address is the start of the environment's `code` range. An environment file of another name runs on the board its `define BOARD` names (1 Michael, 2 Wendy 2, Wendy 2 with files if it also has `define DISK` not 0), or on the default machine if it has none.

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

The ranges are checked (link error 34): each the right way round, `zeropage` within `$00`–`$FF`, `code` and `data` at `$100` or above and sharing no address. Everything the linker places lies wholly inside its range; when the items of a range do not fit, the link error says by how many bytes (`zero page is full, 3 bytes over: a.main -> a.f`), counting the bytes skipped so that no two-byte item in main memory crosses a page on an NMOS 6502.

Version 2 adds the entries for code in windows (`../docs/configurations.md`, section 5, has the design and the decisions as built):

```
more      data $F810 $FFF9      ; a second range for variables
window    WIN $8000 $EFFF       ; an address range whose contents are switched
switch    WIN bank $F000 $1F    ; by the bits $1F of the register at $F000 (rt_bank's); or
                                ; `switch WIN overlay`: by loading a file; or `switch WIN bank
                                ; farcall`: banks the far-call module alone switches (rt_bbc's)
bank      WIN 1 $11 LATHE1.BIN  ; bank 1 (1 to 255), its register value, and its file
bank      WIN 4 $14             ; a bank without a file: no code may be placed in it
overlay   OVL 1 L5OV1.BIN       ; in a window switched by `overlay`: overlay 1 and its file
place     MODULE WIN 1          ; the module's code goes in bank or overlay 1 of WIN
region    NAMES WIN 4           ; the source's `in NAMES` is bank 4 of WIN; or `region NAMES fixed`
farcall   rt_bank               ; the far-call module: rt_bank (banks) or rt_ovl (overlays)
rom       WIN 1                 ; bank 1 of WIN is read-only: no variables, not loaded at start-up
```

- A window comes before its `switch`, which comes before the window's `bank` or `overlay` entries, which come before the `place` and `region` entries that name them. Names are folded to lower case; file names are kept as written.
- A window must lie at `$100` or above and share no address with `code`, `data`, `more` or another window (error 34). Code may be placed in one window only (50); its overlays are numbered from 1 with none missing (52); with a `place` entry there must be a `farcall` entry (54), whose module must be fixed (49), linked, and define `call` and `start` (46). Every placed module must be linked (44).
- With `more`, the frames are laid out first in `data`, and then each variable goes in `data` if it still fits there, else in `more`, in order.
- A module's code, and each copy of its functions for a context, goes in its bank or overlay, from the window's first address, in object order. A call from outside that bank or overlay, `@f` anywhere, and the start-up code's calls of `main` and of a module's `$init` go through a 6-byte stub in fixed memory (`JSR FARCALL.call`, the bank's value or the overlay's number, the function's address less one); a call inside the bank is a plain `JSR`. The stubs follow `$start` and `$init`, then the table `$banks` or `$overlays` that `FARCALL.start` reads, which `$start` calls before `$init`. A constant or variable of a placed module goes in its bank if only that bank's code names it and nothing takes its address (variables at the top of the bank, and never in an overlay); otherwise it is fixed. Frames are always fixed.
- A bank's contents are judged for the fit check by their size before shrinking, every variable that may go in it counted, so that whether a program links does not depend on zero page (45 says by how much it is over).
- An interrupt function must not be in a window (47) and must not reach a function in an overlay (48).
- A variable or constant `in` a region with a bank entry goes in that bank (constants from the window's first address with the bank's code, variables at its top), even if no code is placed; a region with no entry, or `fixed`, is ordinary fixed memory. Regions are in banks of one window, the one code is placed in (58), and need a `farcall` entry (54); constants of a region need a bank with a file (59). A function with a `with` block (a kind 6 fix-up) is kept in fixed memory, marked `k=N` in the map, even if its module is placed, and so is everything that runs inside a block: what a call made inside one reaches (a `CALL` flag), the functions taken as the class for a call through a pointer, and what those call, at any depth; the module's other functions stay in its bank and call a kept one with a plain `JSR`, and the data follow the functions that name them. A function with a block must not be reached from an interrupt function (57). (Until 2026-11-14 a function with a block in a window was error 55, and a call inside a block reaching a window 56: both retired.) The names `rt_with.X` the compiler writes for `with` blocks are read as `FARCALL.X` (`rt_bank.map`, `rt_bank.unmap`); with no `farcall` entry, `build.py` links `lathe/rt/rt_with.lth`, whose `map` and `unmap` are a lone `RTS` each. The map shows a bank of a region that has no file as `W 8000 0000 N -`. (Banked data is provisional, 2026-11-14: `../docs/configurations.md`, "As built: banked data".)
- Each bank or overlay that has a file in the window code is placed in is written to that file in the directory of `OUT.bin`: its bytes from the window's first address through the last byte of code or constant data placed in it.
- `rom WIN N`, after the bank's entry, makes bank N read-only (a ROM): it takes code and constant data but never a variable, so the variables of a module placed there go to fixed memory, and a variable in a region there is error 60; its file is written, but it is not in `$banks`, since it is there already; its `W` line ends with ` rom`. An unknown bank is 42, a second `rom` for it 43, one in a window switched by `overlay` 3.
- With no `place` entry, nothing is placed in a window and the output is what version 1 gives.

`define` is for the compiler only: `build.py` passes it on as `-dNAME` or `-dNAME=NUMBER`, and the linker skips it, as it skips any entry it does not know. The linker writes the start-up code from the other entries (`../docs/object-format.md`, "Initial values and start-up"). `exit stop` ends it with `STP` (`$DB`), which only the 65C02 has: it needs `cpu 65c02`, or the link fails with error 39. `exit return ADDR` ends it with `RTS`, as `exit return` does, and starts it with `TSX` / `STX ADDR`, which keeps the stack pointer the program was entered with, so that it can return to its caller from any depth (the BBC: `lathe/rt/bbc.lth`); ADDR must be outside the zero page, code, data and more ranges (error 34).

The output file:

| Entry | The file holds |
|---|---|
| `output image` | Memory from the start of `code` to `$FFFF`, with the reset vector at `$FFFC` pointing at `$start`. This is what the emulator's default machine loads. |
| `output raw` | The bytes from the start of `code` through the last byte the linker placed there. No padding and no vectors. `$start` is first, so the load address is the entry. |

Environment files are in `lathe/env/`:

| File | Machine |
|---|---|
| `host.env` | The emulator's default machine, with host services (`output image`, `exit call $F00F`). |
| `michael.env` | Michael, loaded at `$2000` (`output raw`, `exit stop`, `define BOARD 1`). |
| `wendy2.env` | Wendy 2, loaded at `$4000` (`output raw`, `exit stop`, `define BOARD 2`). |
| `wendy2disk.env` | Wendy 2 run with `--disk DIR`: the same, and `define DISK 1`. Files through `lathe/rt/disk.lth`; `define PORTS 1` makes `lathe/src/sys.lth` use them. |
| `bbc.env` | The BBC Model B+128 (`--machine bbcbplus`), run with `*RUN`: NMOS 6502, zero page `$00-$8F`, code from PAGE (`$1900`, `output raw`) and the variables up to HIMEM (`$7BFF`), `more data $0401 $06FF`, `exit return $0400`, `define BOARD 3`. Files and the console through `lathe/rt/bbc.lth`, the MOS; `define PORTS 2` makes `lathe/src/sys.lth` use it, and a program's `import host` is `lathe/rt/bbc/host.lth`, host's interface over bbc. `lathe/src/compiler-bbc.env` is the same with the split moved and `SMALL`, for the compiler's test programs. |
| `bbc-rom.env` | The BBC's ROM form (stage 12, step 3): `bbc-bank.env`'s machine with the window `$8050-$BFDF` (the module's reserved bytes are `$8000-$804F` of every bank); a program adds its `bank`, `rom`, `place` and `region` lines (`bbcrom.rom_env` makes them) and is put in a module image by `lathe/host/driver/bbcrom.py` (`lathe/docs/boards.md`, "The ROM module"). |
| `bbc-bank.env` | The BBC banked (stage 12, step 3): `bbc.env` with the window `$8000-$BFDF`, `switch WIN bank farcall`, `farcall rt_bbc` and `define MODULE_SLOT 4`; a program adds its own `bank`, `place` and `region` lines. A bank's value is `$80 + n` for bank n of the module, s for sideways slot s (`lathe/docs/boards.md`, "Banked: the module and sideways RAM"). `lathe/src/compiler-bbc-bank.env` places the compiler's test programs so. |

`BOARD` is read by `lathe/rt/board.lth`, the source of what the board modules (`via`, `lcd`, `timer`) know about each board (`../docs/boards.md`, "Board modules").

`../docs/boards.md` describes the four machines.

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
D 021C 0011 $banks                ; the table of banks ($overlays), after $init's line
F 8000 0006 lib.show b=1          ; a function in bank or overlay 1 (D and V lines too)
T 4016 0006 lib.show              ; its stub, after its F line (a copy's: lib.show@1)
W 8000 0013 1 INBANK.BIN          ; bank or overlay 1: the bytes of its file, and the file
F 4300 0012 lib.fill k=1          ; a function of a module in bank 1 kept in fixed memory
W 8000 0040 2 ROM2.BIN rom        ; a read-only bank (`rom WIN 2`)
```

A C line names the parameter by its name in the class's `CLAS` records; one they leave unnamed (the compiler does not yet write the names) takes the name of the parameter of the class's first member, or `pN`.

Only what the linker kept is listed: functions reachable from an entry point, and those whose address kept code or kept constant data takes (`../docs/code-model.md`, "Sharing frames"); variables and constant data that kept code or kept constant data names (`../docs/object-format.md`, "What the linker keeps"). A function reachable from several contexts (`../docs/code-model.md`, "Interrupts") has one F line and one set of S lines per copy. Its first copy, for the lowest of those contexts, has the function's name; each further copy, for context N, is `name@N`. Context 0 is the main program and 1, 2… the interrupt functions in object order. An F line of a first copy whose context is not 0 (a function only interrupt contexts reach) ends with that context's number, so that every copy's context is known.

## The interface file

`name.li` lists what a module exports. It is binary, and is read straight into the symbol table: no tokens, no parsing. Its types become symbols as they are read. Of the rest, an `import` without a list reads everything: its inline functions become symbols, its functions, constants and variables are kept frozen in the name heap and become symbols only when the importer names them (`kernel.py`, "Frozen symbols"; `../docs/architecture.md`, "What stays in memory"). An `import` with a list reads only the entries it names and those the bodies of the inline functions it reads name (the `LI_USES` entries below), makes each a symbol at once, with the name the list or the `LI_USES` entry made, and passes over the others; those only the bodies need are marked `kernel.SF_HIDDEN`, so that the importer's own code cannot name them (`../docs/language.md`, "Import lists"). Numbers are little-endian and a string is a length byte and its characters, as in object files.

**Version 2** (2026-11-14, for import lists) added the `LI_USES` entries; an interface without exported inline functions differs from version 1 only in the version byte. Nothing reads version 1: a module whose interface is of it is compiled again (`../docs/object-format.md`, "Versions").

```
header   "LI", version (1 byte, value 2), module name (string)
entries  each: kind (1 byte, not 0), name (string), then what that kind has
end      a 0 byte
```

| Kind | Entry | After the name |
|---|---|---|
| 1 | Function | flags (1); if flag bit 0 is set, the address (2); number of parameters (1) and that many members; number of results (1) and that many members. |
| 2 | Constant | type (as below, or 6 for a number that has no type yet, 7 for such a number below zero, 8 for `nil`); value (2), in two's complement, sign-extended if the type is signed. A constant of an array type is a table: its value is 0, and it is the constant data `module.name`. |
| 3 | Variable | type; placement (1): 0 none, 1 at a fixed address, which follows (2), 2 declared `zp`, 4 declared `nozp`, 8 `in` a region, whose name follows (string). |
| 4 | Named type | flags (1); the type it is another name for. |
| 5 | Record | flags (1); number of fields (1), and for each its name (string) and type. The offsets follow from the sizes. |
| 6 | Enumeration | flags (1). Its constants are constant entries of its type. |
| 7 | Function type | flags (1); number of parameters (1) and that many members; number of results (1) and that many members, as for a function. |
| 9 | Constant in a region | as kind 2 (a table: value 0), then the region's name (string). |
| 8 | Module | (nothing). A module this one imports, written only if this one exports an `inline` function. The reader imports it too, if it has not yet (or reads it again for what the `LI_USES` entries it wants name of it), and knows it by its name in this module's scope: the bodies of this module's inline functions can use it, the reader's own code cannot. |
| 10 | Uses | the number of names (1), then each as a module name (string, empty for this module) and a name (string). One for each exported `inline` function, whose name the entry has, before every other entry, the newest function first: what its body names that an importer must read with it. That is each function, constant and variable of this module the body names by a plain name (its parameters and locals apart), and each `m.name` of a module `m` this module imports; types and modules are not listed, because every import reads them. A reader that wants the function (its list names it, another wanted function's entry does, or it reads the module whole) wants those names too; newest first, a function that another names is wanted by the time its own entry is read (`decl.read_uses()`, `inline.write_uses()`). |

- **Function flags:** bit 0 `extern`: a routine at a fixed address; bit 1 `recursive`; bit 2 `asm`: a function whose body is assembly, called like an `extern` one (parameters and results in registers, no slots) but through its symbol; bit 3 `inline`: its saved tokens follow its members (below); bit 4 `interrupt`: it cannot be called, only have its address taken.
- **An inline function's saved tokens** follow its results: the name of the source file it was read from (string), the line of its first token (2), its flags (1: bit 0 pure, bit 1 its only `return` is its last statement, `lathe/host/inline.py`), 0, or 1 and the name (string) of the one variable of the program a pure body assigns to, for each parameter its name (string) and 1 if the body assigns to it, else 0 (1), then its tokens in the form of `lex.py` (at `SAVED_LINE`) but with each name written as a string instead of its place in the name heap, and a 0 byte (T_EOF) after the last.
- **A member** is a type and a register (1 byte): 0 none, 1 `a`, 2 `x`, 3 `y`, 4 `ax`, 5 `ay`, 6 `xy`, 7 `c`. A parameter with register 0 is the callee's slot of the same number; for a Lathe function the first ones are also passed in registers, which follow from their types and are not written (`../docs/code-model.md`, "Convention"). A result always has its register: for a Lathe function that is `a` for a one-byte value, `ax` for a two-byte one and `c` for a `bool`.
- **A type** is 1 `byte`, 2 `sbyte`, 3 `word`, 4 `int`, 5 `bool`; `$10` followed by a type: a pointer to it; `$11`, the number of elements (2) and a type: an array of them, stored by column; `$12` and the same: an array declared `rows`; or `$13`, a module name and a type name (strings): that module's record, enumeration or function type. Another name for a type is not a type code: what it names is written instead.
- **Type flags:** bit 0 `pub`; bit 1, for a function type, `recursive`. Every record, enumeration and function type of the module is written, so that the entries which use one can name it; one without the flag cannot be named by an importer. Another name for a type is written only if it is `pub`. The parameters of a function type have no names in the entry: only their types matter.
- **The module of a `$13` type** must have been imported before, by the module that reads the entry (error 135 if not); the module itself, whose interface is being read, counts.
- **A variable** that is neither `zp` nor at a fixed address is used through instructions in the absolute form, which the linker shrinks if it lands in zero page; one declared `zp` is used through zero page instructions from the start. One at a fixed address has no symbol in any object file.

Entries are in the order of the declarations, so a type's entry comes before any entry that uses it, and a record's fields can use the record (`next: ^Link`), whose entry is read before them. A reader that meets a kind or version it does not know stops with error 51.

## Errors

Every error has a number; `err.py` lists them with their texts. 1 to 19 are about characters and tokens, 20 to 39 syntax (39 is "not implemented yet"), 40 to 59 meaning, 60 to 69 the command line and files, 70 to 98 a capacity of the compiler that was exceeded, 99 a fault in the compiler itself, 100 to 139 meaning again (40 to 59 filled up; 120 to 127 are arrays, strings and pointers, 128 to 139 records, enumerations and named types), 140 to 149 `asm` blocks and functions, 150 to 164 function types, calls through pointers and recursion, and 165 to 179 `inline` and `interrupt` functions; the top of `err.py` has the table. An error found while an inline function's body is expanded is reported at its place in that body, in that function's file. A lexical error is reported at the character it was found at or at the start of its token; any other error at the start of the token that is wrong. For a value of the wrong type or out of range that means:

- operands that do not suit an operator: at the operator;
- a value that does not suit what it is given to (an assignment, an argument, a `return`, an initial value, a constant's type): at the first token of the value;
- a test that is not a `bool`: at the first token of the test;
- something that cannot be assigned to: at its first token.

A new error takes the next free number of its group.

## The linker in Lathe

The linker's twins are `lathe/src/lk_*.lth`, each the transliteration of its host module, with the conventions at the top of `lk_err.lth`. Their tables at the capacities that link the compiler take 53,952 bytes, which with the linker's code is more than the emulator's default machine has. So a capacity that sizes a table is written twice in the twin:

```
#if LKSMALL
pub const MAX_FUNCS = 400
#else
pub const MAX_FUNCS = 800
#end
```

`LKSMALL` is defined only by the linker's own environment file, `lathe/src/linker.env` (`define LKSMALL 1`), with which the test programs `lktest1.lth` to `lktest4.lth` are built; an environment that builds the linker at full size says `define LKSMALL 0`. No other environment needs the name, and the compiler's corpus (`memory_report.py`) compiles the linker's modules with that file. The host modules have only the full values: `lathe/tests/lk_small.py` reads the `#if LKSMALL` blocks of the twins and runs the host modules again with those constants replaced, so that the identity test (`test_src_lk.py`) runs both at the same capacities, and runs them again at full size when it is done. The host modules hold no trace of it.

The small build takes two fifths of what grows with the program: 320 functions, 1,280 slots, 1,200 calls (lowered again when banked data added code to the twins), 360 nodes (so a work area of 3,600 words), 320 variables and constants, 1,400 symbols in object files (1,600 until the banked linker needed the room), 256 fix-ups held, and promotion's list of 32 copies taken (`lk_alloc.MAX_TAKEN`, which must end inside the work area: 9 × 360 + 264 + 2 × 32 ≤ 3,600 words). The rest is as at full size. Its tables take about 23 KB. `linker.env` gives code `$0200-$985F` and variables `$9860-$EFFF` (`$90FF` and `$9100` when this was written, `$94FF` and `$9500` until the linker kept functions in fixed memory, 2026-11-14): `lktest4`, which runs the phases up to storage, leaves 44 bytes of code and 63 of variables free. (Halving the full capacities, the step before, left 28.5 KB of tables, too much beside the graph and storage.) It reads `lk_synthetic`'s program with 7 functions in each of its 30 modules: 239 functions, 1,086 slots, 1,038 calls, 1,243 symbols in object files and 2,883 bytes of names kept; with 8 the names kept and the symbols' words fill the work area (link error 10). That is about a third of the compiler.

`lathe/tests/size_report.py --linker` measures the twins over their test programs and the whole linker built banked.

**The whole linker** is `lathe/src/link.lth` with the nineteen twins it imports: 45.4 KB of code, which does not fit the emulator's default machine beside its tables, so it runs banked on emulated Wendy 2 with files (`../docs/spikes.md`, "The whole linker in Lathe, banked on Wendy 2, measured"):

- `lathe/src/linker-bank.env`: Wendy 2 with `--disk` (`define BOARD 2`, `DISK 1`, `PORTS 1`: files through `lathe/rt/disk.lth`), the small build's tables (`LKSMALL 1`), all in fixed memory, variables at `$0200-$58BF` and `$F810-$FFF9` (`more`), fixed code at `$58C0-$7FFF`, and the code by phase in three banks of the window `$8000-$EFFF`. Fixed: what every phase calls many times, `lk_tab`, `lk_rec`, `lk_sym`, `sys`, `disk` and the run-time. Bank 1, reading: `link`, `lk_err`, `lk_file`, `lk_envf`, `lk_scan`, `lk_name`; bank 2, the graph and storage: `lk_graph`, `lk_alloc`; bank 3, placement and output: `lk_place`, `lk_fix`, `lk_map`, `lk_emit`, `lk_out`, `lk_boot`, `lk_win`, `lk_op`. The file says why.
- `lathe/tests/lk_banked.py`: `build_linker(dir)` builds it (`dir/link.bin`, its bank files `LINK1.BIN` to `LINK3.BIN` beside it); `run(image, files, args)` links in a directory of its own holding the case's files and the bank files, with the arguments in the file `args`, and returns the status, the error output, every file the run wrote and the CPU cycles. They are the linker's counterparts of `src_support.build_banked` and `run_banked`, which serve the compiler's test programs.
- `lathe/tests/lk_bank_report.py [DIR]` measures it: resident bytes and banks from the map, the cycles of linking lextest, `lk_synthetic` and a banked program, by phase, the far calls (a counting `rt_bank`) and where they go (the host run's calls between banks).

The banked linker takes up to 40 object files and, through `disk.lth`, at most 48 arguments of 256 bytes in all; it links `lk_synthetic`'s program at 7 functions a module (239 functions), about 30% of the compiler.

## Tests

`lathe/verify.sh` runs everything; `tools/check_all.sh lathe` calls it. Tests are Python `unittest` files in `lathe/tests/`, run from the repository root: `python3 -m unittest discover -s lathe/tests`.

| Kind | Cases | Check |
|---|---|---|
| Unit | in the test file | One host module's functions. |
| Shape | `test_shape.py` | The rule above. |
| Snapshot | `tests/cases/snap/NAME.lth` | `lo2asm` of the compiled module equals `NAME.expected.asm`. |
| Error | `tests/cases/err/NAME.lth` | The first line is `; error N LINE COL`; the compiler must report exactly that. A line `; options ...` before `module` gives the compiler options. |
| End to end | `tests/cases/e2e/NAME.lth` | The program's output on the emulator equals `NAME.expected.out`. Built both ways (linker, and assembler path) once the linker exists; the two images must be identical. |
| Link error | `tests/cases/linkerr/NAME.lth` | The first line is `; link error N`: the program compiles, and `build.py` fails at linking with that error, the linker's message in its own. Each further line before `module` that starts with `; says ` gives text the message must hold. |
| End to end on a board | `tests/cases/e2e-michael/NAME.lth`, `tests/cases/e2e-wendy2/NAME.lth` | Built with `michael.env` or `wendy2.env`, both ways, with identical files required. The text the board's LCD shows when the program stops equals `NAME.expected.out`: one line per row, trailing spaces removed, and an empty line for an empty row. These use the board modules of `lathe/rt/`; a Wendy 2 case whose source is the Michael one is a link to it. |
| End to end with files | `tests/cases/e2e-wendy2disk/NAME.lth` | Built with `wendy2disk.env` both ways and run on a directory holding a copy of `NAME.disk/` (its input files; the arguments in `args`). The file `out` it writes equals `NAME.expected.out`, `errors` equals `NAME.expected.err` (or is empty), the status is the `; status N` line before `module` (default 0), and each `; same IN OUT` line names an output that must hold exactly the bytes of input `IN`. |
| Files on Wendy 2 | `test_disk.py` | `lathe/rt/disk.lth` has the functions of `host.lth` that `sys.lth` uses, with the same types; `sys.lth` chooses `disk` or `host` with `#if PORTS`, each call written the same way under both; `copytest.lth` built with `wendy2disk.env` (`PORTS 1`) runs on Wendy 2 as `test_src_sys.py` runs it on the default machine (`PORTS 0`); every environment of the compiler defines `PORTS`. |
| Configurations | `tests/cases/e2e-config/NAME.lth` | One program linked in several configurations: each line `; config ENV` before `module` names an environment file beside the case (or in `lathe/env/`), and the program runs on the machine that environment names. The output equals `NAME.ENV.expected.out` if there is one, else `NAME.expected.out`; a configuration that places no code in a window is also built by the assembler path, with identical images required; each `; same MODULE...` line names modules whose objects must be the same in every configuration (but for the CPU byte of the `MOD` record). The cases are spike L5's program in Lathe (`farcall.lth`) and its timer test (`farirq.lth`), banked, in overlays and all in one; a module in a bank called only from its bank (`inbank.lth`); constants and a variable in a bank (`bankdata.lth`); variables and constants in regions, a data bank with no file and one with a file, with every way out of a `with` block (`regions.lth`); a timer interrupt inside a `with` block whose handler far-calls into a code bank (`withirq.lth`); functions kept in fixed memory and a read-only bank, with a pointer into a region passed down (`kept.lth`). |
| EXPR in Lathe | `test_src_expr.py` | `lathe/src/exprtest.lth`, the test of `expr.lth`, built with `compiler-bank.env` and run on Wendy 2 (it has about 68 KB of code), against `expr.py` at the full capacities: each section of `scripts/expr.txt` declares names and reads a piece of real source through LEX and SRC (bodies of functions with every statement, expressions, conditions, constants, types, declarations, inline expansions, the nesting limit and every error EXPR reports); every third section by default, all with `LATHE_BANKED_ALL=1`. Output, error output, status and object file must be identical, and every statement of `expr.py` but three must run, `with` blocks included (`LATHE_EXPR_COVERAGE=1` lists them). |
| The compiler in Lathe | `test_src_lathec.py` | `lathe/src/lathec.lth`, the compiler's main module, with the twins of all seventeen host modules, built with `compiler-bank.env` and run on Wendy 2, compiles every module of the corpus that `memory_report.py` compiles (snapshot, error and end-to-end cases, `lathe/rt/`, `lathe/src/`) and 49 inputs made for what the corpus lacks (command lines that are errors, file names that cannot be a module's, damaged interfaces, each capacity of the small build), each with the options `memory_report.options_of()` gives it, in a directory holding its source and its imports' interfaces (made by the host at full size), as `lathec OPTIONS NAME.lth .`. The status, output, error output and files written must equal those of the host compiler at the small capacities (`lathec_small.py`, a process for each run). An input fits if the host gives it no capacity error, or it is an error case that gives its own error; one that does not fit is compared too. By default each kind's every few inputs that fit (every sixth error case, every third end-to-end module, every second snapshot case, all the others) and every twelfth that does not, about 200 in 50 s; all of them with `LATHE_BANKED_ALL=1`. Every error number but five (`NOT_REPORTED`) is given by an input that fits, and every statement of `decl.py` and `lathec.py` but three runs in one (`LATHE_LATHEC_COVERAGE=1` lists them, `LATHE_LATHEC_REPORT=1` prints the counts). It runs the compiler at the small capacities (`define SMALL 1`); with `LATHE_LATHEC_FULL=1` the banked compiler at full size against `lathec.py` at full size, where all 687 inputs fit and are the same. |
| The compiler compiles itself | `test_src_selfhost.py` | The gate of stage 7: `lathec.lth` built with `compiler-bank.env` at full size compiles its own seventeen modules and `sys` on Wendy 2, each with `compiler.env`'s options in a directory with its source and the host's interfaces of its imports, and the object and interface files, status and output equal the host compiler's. By default the five smallest (9 s); all with `LATHE_SELFHOST=1` (about a minute, 815 million cycles of Wendy 2); `LATHE_SELFHOST_REPORT=1` prints the cycles of each. |
| Banked test programs | `test_src_banked.py` | `outtest`, `regtest`, `condtest` and `gentest` built with `compiler-bank.env` and run on Wendy 2 (above, "The banked build"): every section of `out.txt`, `reg.txt` and `cond.txt`, and every fourth of `gen.txt` (all with `LATHE_BANKED_ALL=1`, 26 s instead of 16), gives the Python's output, at the full capacities on both sides; each module is in its bank, the big tables in the data banks, each table at its full size; resident code and stubs are under 16 KB. |
| Far calls | `test_farcall.py` | `farcall.lth` with the linker's stubs and tables: a far call costs 182 cycles more than a call into a bank and 82 into the overlay in the window, against the same objects all in one; the program makes 49 overlay loads; the routines' and stubs' sizes; status 255 for a missing bank or overlay file; where `bankdata.lth`'s constants and variable went. `WithBlocks`: a `with` block costs 94 cycles with its region in a bank, 32 with it in fixed memory (`region NAME fixed` and `farcall rt_bank`: `rt_bank.map(0)` maps nothing), 24 all in one (`rt_with`). |
| Windows | `test_lk_windows.py` | Environment version 2 on objects built by hand: every new link error, `more`, placement in a bank and its file, a bank judged before shrinking and whatever zero page takes, stubs for interrupt contexts, and which constants and variables go in a bank (fix-up kinds 7 and 8, an address formed only to reach an element, do not keep a table fixed); regions (`Regions`): placement, kind 6, the map, `rt_with.` read as the far-call module, link errors 45, 54 and 57 to 59, damaged `RGN` records, and the functions kept in fixed memory; read-only banks (`ReadOnly`, link error 60). |
| Banked data | `test_banked_data.py` | What the compiler writes for `in REGION` and `with REGION do … end`: `RGN` records, the kind 6 fix-up and the name it takes (the first used, or the module's first of the region), the calls of `rt_with.map` and `unmap` and the temporary, flagged calls, `return`, `break` and `continue` out of blocks, nesting, inline expansions and statics in blocks, interfaces that hold an importer to the rule; fix-up kinds 7 and 8 for an address formed only to reach an element, 2 and 3 for one `@` takes. Error cases 118, 119, 182 and 184 are in `cases/err/` (183 is retired), and 168 for `with` in an inline function (`inline_with.lth`). |
| The BBC | `test_bbc.py` | `lathe/rt/bbc.lth` has every function of `host.lth` with the same types, and only NMOS instructions; `bbc.env` keeps the MOS's memory free and keeps S where bbc looks; the driver's command line (quotes), line end and status; small programs on the emulated B+128 with `--bbc-strict`: arguments (quoted, empty, extra spaces), output with its line end, standard input, a file copied byte for byte (CR and LF in it), an empty file, the end of a file read again, a missing file, a name the filing system refuses (`Bad name`, caught), `exit(0)` from inside a call, a status as the MOS error `Exit N`, files closed by `exit`, the `.inf` file. |
| `sys` on the BBC | `test_bbc_sys.py` | Each `#if PORTS` of `sys.lth` is the `#else` of an `#if PORTS == 2` with the same text for `bbc`; `bbc.lth` has no `$init` (it is imported, unused, in every build); every environment's `PORTS` fits its machine; `copytest.lth` built with `bbc.env` gives the cases of `test_disk.py`'s on the BBC. |
| The corpus on the BBC | `test_bbc_cases.py` | Every case of `tests/cases/e2e/` but two built with `bbc.env` both ways (the images must be the same) and run on the BBC with `--bbc-strict`, in parallel: the output must be the expected one. `asm_pointer` and `state` are left out: they store at addresses that are the MOS's on the BBC (the test checks that they still do). |
| Test programs on the BBC | `test_bbc_src.py` | `lextest` (its corners and every source of the project), `errtest` (every error number), `kerneltest` (every mode) and `srctest` (every case) built with `compiler-bbc.env` and run on the BBC (`bbc_support.py`), against their twins at the small build's capacities with the error output joined to the output, files by their base names: status, output and files written must be the same; each fits PAGE to HIMEM. |
| Banked on the BBC | `test_bbc_bank.py` | `lathe/rt/rt_bbc.lth` with `lathe/env/bbc-bank.env`: code in banks of the module (the developer's form, RAM, `--bbc-module-ram --bbc-module-scheme direct16`) and regions in sideways RAM slots, run with `*RUN` and `--bbc-strict`. `farcall.lth`, `bankdata.lth` and `regions.lth` of `cases/e2e-config/` give their Wendy 2 output (and where their code, constants and variables went); a missing bank file is status 255; `switch WIN bank farcall` takes no register. A program of its own: regions in two sideways slots at the same addresses, nested blocks, a block entered from two banks at each level of a recursion between them, a far call made inside a block (through an address taken in asm, as a handler's would be), MOS file calls from a bank and inside a block with a name the filing system refuses; the same all in one. Sixteen modules in the sixteen banks of the module. The costs: 187 cycles a far call from fixed code (197 between banks), 64 a `with` block from fixed code (79 from a bank), against the same objects all in one; `call` and `back`'s size and the stubs'. |
| The ROM module on the BBC | `test_bbc_rom.py` | `lathe/host/driver/bbcrom.py`'s image of three programs, each linked with its own ROM environment (`lathe/env/bbc-rom.env`, `bbcrom.rom_env`) and started by its `*` command (`boards.run_module`, `--bbc-strict`): `*FIRST` (farcall, bankdata and regions of `cases/e2e-config/`: far calls between banks, a module's variable in main RAM, regions with constants copied to sideways RAM), `*SECOND` (`test_bbc_bank.py`'s program) and `*THIRD` (all in one), each with arguments giving what it gives with `*RUN` banked and all in one, from the same objects; every power-on bank of the latch; slots 7 and 2; the image through `LOADMOD` in the module's RAM form, and the loader's errors; `Exit 9`; the end in a language ROM made in the test, or the service call returned where there is none; unknown commands left unclaimed with the latch put back; `*HELP`; other service calls leave the latch alone; the reserved bytes of every bank; the tool's listing, command line and checks. |
| Test programs in the ROM | `test_bbc_rom_src.py` | `outtest`, `regtest`, `condtest` and `gentest` in the small build, each in a module image with its banks `rom` (`compiler-bbc-bank.env` through `bbcrom.rom_env`), started by `*GENTEST` and so on: every section of their scripts against the twins, files included; no variable in a bank of the module, the regions in slots 12 and 13, everything fixed below HIMEM. |
| Banked test programs on the BBC | `test_bbc_bank_src.py` | `outtest`, `regtest`, `condtest` and `gentest` built with `lathe/src/compiler-bbc-bank.env` in the small build (`bbc_support.build_banked`: code in five banks of the module, the big tables in sideways slots 12 and 13) and run on the BBC: every section of their scripts against the twins at the small capacities, files included; the placement; each fits PAGE to HIMEM. `outtest`, `regtest` and `condtest` again at full capacities with the split moved for each (against the twins at their own); `gentest` does not fit so (link error 26, 1,344 bytes over). `gentest` again with `kernel`, `lex`, `src`, `fbuf` and `err` placed, the linker keeping fixed their functions with blocks (576 bytes over at full capacities). |
| Boards | `test_boards.py` | Object files built with `lo.Builder` that show `HI` on each board's LCD, linked, built by the assembler path and run as `build.py --run` runs them. |
| Output forms | `test_lk_output.py` | `output raw`, `output image`, `exit stop` and `exit return ADDR`, by hand-worked bytes and by the assembler path. |
| Zero page promotion | `test_lk_promotion.py` | The synthetic program and random ones, linked as the linker links and with every candidate judged on a fresh layout: the maps must be the same, and the layouts fewer. |
| Memory | `test_lk_memory.py` | The linker's tables, laid out as Lathe lays them out, within a ceiling that only comes down (`lk_memory_report.py`). |
| The whole linker | `test_src_link.py` | `lathe/src/link.lth` built with `linker-bank.env` and run on Wendy 2 with files (`lk_banked.py`), against `link.py` over the host modules at the same capacities, on real links: the programs of the end-to-end corpus (`tests/cases/e2e`, `e2e-michael`, `e2e-wendy2`, `e2e-wendy2disk`, each configuration of `e2e-config`, `linkerr`, and lextest), recorded as `build.py` links them; the links the linker's own tests make; the links made by hand of `test_src_lk.py` and `edge_links` (bad fix-ups, slots of dropped functions, a call through a pointer inside a `with` block, a variable kept off a page boundary in a bank); and `lk_synthetic` at the largest size the small build takes and one larger. Error output, status and every file written must be identical. By default a part of each (`SUBSET`, every tenth recorded link, every third made by hand; 60 s); `LATHE_LK_ALL=1` runs all (about 3 minutes); `LATHE_LK_COVERAGE=1` prints the lines of `lk_fix`, `lk_place`, `lk_map`, `lk_emit` and `link` the host runs reach. |
| The linker in Lathe | `test_src_lk.py` | The linker's twins (`lathe/src/lk_*.lth`) through `lktest1.lth` to `lktest4.lth`, built with `lathe/src/linker.env`, against the same drivers over the host modules at the same capacities: every environment file, every link the linker's tests make (they are run again with their links recorded), links made by hand for what those do not reach, twelve compiled programs and `lk_synthetic`'s program at the largest size the small build takes and one larger. `lktest3` runs the phases of `link.py` to the stubs and prints the contexts, nodes, edges, sets and their order and the stubs, then writes `$start`, `$init`, the stubs and the table for made-up code addresses (`lk_graph`, `lk_win`, `lk_boot`); `lktest4` runs them through storage and prints every address allocation gives and how often promotion laid zero page out (`lk_alloc`), also at 16, 32, 64 and 96 bytes of zero page and at each program's edge, where every candidate just fits, and a byte less. Output, error output, status and files written must be identical. With `LATHE_LK_COVERAGE=1` it prints the lines of the host modules the runs reach (`=lines`: which are not). |

`lathe/tests/fuzz.py` is not part of the suite. It compiles and runs random programs and compares what they print with their true results: run it (`fuzz.py expr 1 200`, `fuzz.py stmt 1 200`) after any change to how code is generated. In stage 2a it found four faults that the cases written by hand had not; in stage 2b, once its statements used arrays and pointers, one more (a word in A and X stored into an element whose index needs X).

`lathe/tests/memory_report.py [--corpus]` counts the bytes the compiler's tables take as Lathe lays them out, and with `--corpus` compiles every module of `lathe/src/`, `lathe/rt/` and `lathe/tests/cases/` and prints each table's peak use (`test_memory.py` checks the total). `lathe/tests/size_report.py [DIR]` builds `lathe/src/lextest.lth` and prints its code bytes per module and its largest functions: the measure for changes to code generation. `lathe/tests/arg_report.py DIR` reads that build's objects and counts what passing arguments in registers would save.

### The small build

The test programs of the Lathe twins (`lathe/src/*test.lth`) run on the emulator's default machine, 60 KB for code and variables. At the compiler's full capacities, those with more than 20 KB of code (`regtest`, `condtest`, `gentest`, `asmtest`, `inlinetest`) do not fit beside the tables, so they are built small:

- Each twin declares its big tables' capacities under `#if SMALL`: the name heap, the symbol rows and members, the text memory and the token memory (`kernel`), the function buffer (`fbuf`), the constant table and its fix-ups (`out`), the string being read (`lex`), the saved tokens (`inline`). An array of more than 256 elements stays above 256, because its index is a `word`. The name heap is 1,536 bytes (768 until the compiler ran banked: the keywords and the predeclared names take about 700, and at 1,536 most of the corpus fits, `test_src_lathec.py`).
- `lathe/src/compiler.env` defines `SMALL 0`, `compiler-small.env` defines `SMALL 1` and moves the split between code and variables up (`src_support.build_program(name, dir, small=True)`). `#if SMALL` is an error where `SMALL` is not defined, so every environment that compiles the twins defines it; `memory_report.py` compiles the modules of `lathe/src/` with `compiler.env`'s options.
- The Python side runs with the same capacities: `script_host.SMALL` lists them, and `check_script(..., small=True)` sets them in the host modules while each section runs (the host's arrays stay at full size; only the limits are checked). `test_memory.py` checks that `script_host.SMALL` and the twins' `#if SMALL` constants agree, and that the twins' other value is the host's own.

The scripts do not come near these tables' limits but for the sections written to (`out.txt`'s table of 2,048 bytes is why `outtest` stays at full size).

### The banked build

The test programs can also run on emulated Wendy 2 with `--disk`, their code in banks (`../docs/configurations.md`, "Measured on the compiler's test programs"):

- `lathe/src/compiler-bank.env`: Wendy 2 with files (`define BOARD 2`, `DISK 1`, `PORTS 1`, so `sys` uses `lathe/rt/disk.lth`), the full tables (`SMALL 0`), fixed code at `$3C00-$7FFF` below the window, variables at `$0200-$3BFF` and, as they outgrow it, `$F810-$FFF9` (`more`); code in banks: expr, parts, lathec and the drivers `script`, `listing` and `regcmd` in bank 1, gen, reg, typetab and `slotview` (regcmd's reader of REG's slot columns, so that they stay in bank 2) in bank 2, cond, asmblock, inlines and fold in bank 3, decl and out in bank 5; data: the regions `NAMES` (the name heap) in bank 4, which has no file, and `MSGS`, `FUNCBUF`, `STRING`, `TOKENS`, `OUTTAB` and `WANTS` (err's messages, the function buffer and its labels, LEX's string, INLINE's saved tokens, OUT's constant table and its fix-ups, DECL's rows of what an import wants) in bank 6, whose file holds the messages; `SYMS`, kernel's symbol and member columns, is a region kept in fixed memory (`region SYMS fixed`), where a block costs 32 cycles. The file says why each is where it is; `../docs/configurations.md`, "Step 10: the tables in data banks" and "The symbol table in a region", have the numbers. The split is set by `lathec`, with 547 bytes to spare above its code (2026-11-15).
- `src_support.build_program(name, dir, small=True, banked=True)` builds the same at the small build's capacities (`banked_env` writes `define SMALL 1`), for `test_src_lathec.py`, whose inputs were made for those.
- `src_support.build_program(name, dir, banked=True)` (`build_banked`) writes the program's own environment, `dir/NAME.env`: that file with `place NAME WIN 1` for the main module, and without the `place` lines of modules the program does not link (an unlinked placed module is link error 44). The bank files go beside the image.
- `src_support.run_banked(image, args)` runs it as `run` runs the default machine's build and returns the same `(status, output, error output, cycles)`: in a directory of its own, with the bank files, each argument that is a file copied in and named by its base name in the file `args`, and each output file an argument names copied back after the run. The cycle cap is 400 million oscillator ticks, 200 million CPU cycles; the start-up loads the banks at about 70 cycles a byte, 2 million cycles for gentest.
- `script_host.check_script(..., banked=True)` compares as before; it runs the Python in the script's directory with the same base names, so messages that name a file agree. `chosen(n)` picks sections.
- `lathe/tests/bank_report.py [DIR] [--program NAME --script NAME]` measures a program banked against all in one: resident code, banks, stubs, cycles, far calls (counted by a copy of `rt_bank` that adds to a counter) and the cost of loading the banks; with `--selfhost [--all-placed] NAME...` the compiler compiling `lathe/src/NAME.lth`, with `--all-placed` kernel, lex, fbuf, err and src placed too and the regions that are fixed (`SYMS`) in bank 7, apart from the names and the function buffer as on the BBC, and the fixed code by module with what each placed module keeps in fixed memory, and what main memory must hold on a machine whose code banks are ROM (variables not in a region, kept and other fixed code, stubs, fixed constants).

A snapshot or end-to-end case can import modules that lie beside it, and a line `; defines NAME NAME=NUMBER ...` before its `module` line builds it with those defines. A file called `lib*.lth`, or whose first line starts with `; imported by`, is such a module and not a case. Each expected output in `e2e/` was first compared with the output of a separate Python model of the program, so it is what the program must print and not merely what the compiler made it print.
