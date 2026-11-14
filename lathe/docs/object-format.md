# Lathe: object files, version 2

Status (2026-11-14): specification for stages 1 to 5. It will grow (regions, banks, far calls) and the version byte changes when it does. Version 2 replaced version 1 on 2026-11-14: a fix-up kind for instructions that shrink, `DFIX` before its `DATA`, parameter names in `CLAS` and the `WGT` record. Nothing reads version 1 any more; a module in it is compiled again.

The compiler writes one object file (`.lo`) per module. The linker reads all of them. A host tool can also render them as asm17 text, which is how the linker is checked ([`architecture.md`](architecture.md)).

## Conventions

- Multi-byte numbers are little-endian.
- A **string** is a length byte followed by that many bytes.
- A file is a sequence of **records**: a type byte, a two-byte body length, the body.
- **Names** are lower case. A module-level name is `module.name`. Nothing else is named globally: a slot is identified by its function and its number.
- **Symbols** are numbered from 0 in the order their `SYM` records appear in the file. Every symbol a module defines or refers to has a `SYM` record before its first use.
- **What a record needs comes before it.** A function's fix-ups come before its code and those of constant data before the data, so a reader holds the fix-ups when the bytes they patch arrive, and reads each file in one pass from start to end.

## Records

| Type | Name | Body |
|---|---|---|
| `$01` | `MOD` | version (1 byte, value 2), CPU (0 = 6502, 1 = 65C02), module name (string). First record. |
| `$02` | `IMP` | Name of an imported module (string). Also written for a run-time module the code calls without an `import` (`rt_frame`, at the first call that saves a frame), so it can come after other records. |
| `$03` | `SYM` | Kind (1 byte), name (string). Kinds: 1 function, 2 variable, 3 constant data, 4 pointer class. |
| `$04` | `VAR` | Defines a module-level variable: symbol (2), size (2), class (1), weight (1), flags (1). A variable is storage only; it has no initial value in the object file. |
| `$06` | `DFIX` | Fix-ups for the `DATA` record just after it. Entries as in `FIX`. |
| `$05` | `DATA` | Defines constant data: symbol (2), then the bytes. |
| `$07` | `FUNC` | Starts a function: symbol (2), flags (1). Followed by its `SLOT`, `CALL`, `FIX` and `CODE` records and closed by `ENDF`. |
| `$08` | `SLOT` | One slot of the function, in slot-number order from 0: size (2), class (1), weight (1), kind (1), name (string). |
| `$09` | `CALL` | One call the function makes: callee symbol (2), flags (1), outer symbol (2). |
| `$0A` | `FIX` | All fix-ups for the function's code, sorted by offset. Each entry is 8 bytes: offset (2), kind (1), symbol (2), slot (1), addend (2). |
| `$0B` | `CODE` | The function's instructions. Instructions only: no data bytes. |
| `$0C` | `ENDF` | Ends the function. Empty body. |
| `$0D` | `CLAS` | A pointer class this module uses: symbol (2), flags (1), number of parameters (1), then for each parameter its size (2) and its name (string, empty if not known). |
| `$0E` | `MEMB` | This module takes a function's address as a class: class symbol (2), function symbol (2). |
| `$0F` | `WGT` | Weight this module adds to storage its own records do not hold: entries of 4 bytes, symbol (2), slot (1), weight (1). Outside functions. See "Weights". |
| `$00` | `END` | Last record. Empty body. |

Order within a function: `FUNC`, every `SLOT`, every `CALL`, `FIX`, `CODE`, `ENDF`. Everything the linker needs about a function comes before its code.

### Pointer classes

A function type is a pointer class, named `module.type` after the module that declares the type. Each module whose code or data uses the class, by a call through it, a fix-up to one of its parameters or a `MEMB` record, writes its `CLAS` record (after the class's `SYM` record, when it first uses it), and the sizes must agree. The first name any `CLAS` record gives a parameter is its name, in the map and in the text `lo2asm` writes. A parameter no `CLAS` record names is named, in the map, after the parameter of the first function recorded as the class's member, and otherwise `pN`. The compiler does not yet keep the names of a function type's parameters, so it writes empty names.

- **A call through a pointer** has a `CALL` record with the "through a pointer" flag whose callee is the class. Its arguments are stored by fix-ups that name the class and the parameter number (`slot`), and it is a `JSR` to a label of the caller, a fix-up naming the caller itself with the label's offset as addend, where the caller has a `JMP (pointer)`.
- **A member** is an ordinary function. It declares its parameter `SLOT` records, kind 0, as any function does, and its code reaches them by fix-ups that name itself and the slot number, whether or not it is a member, so that its address can be taken after it was compiled or by another module. The `MEMB` record of whichever module takes its address as the class tells the linker, which then gives those parameter slots, in the copy of the function for the context that calls through the class, the addresses of the class block's parameters: every fix-up to them, the member's own and its direct callers', lands there. The member's parameters must have the class's number and sizes (link error 24 otherwise). A function taken as two classes makes them one.
- **The `recursive` flag** of `CLAS` says the function type was declared `recursive`. The linker does not need it: the block counts as recursive, and the checks fall on the real calls into and out of it, whose `CALL` records say whether they save. The compiler writes it, and the tools show it.

### Weights

The weight of a slot or variable says how much it gains from zero page ([`codegen.md`](codegen.md), "Weights"); the linker moves the heaviest into zero page first. A module's `VAR` and `SLOT` records hold the weight of the uses in that module's own code, and of a slot only those in its own function. A `WGT` entry adds the weight of other uses:

| Symbol | Slot | Adds to |
|---|---|---|
| a variable another module defines | `$FF` | its weight: the uses of an imported variable. |
| a function | 0 to 254 | that slot's weight: the stores into a callee's parameter slots at a call, and any other use of another function's slot, whether that function is in this module or not. |
| a pointer class | 0 to 254 | that parameter's weight: the stores of the arguments of a call through a pointer. |

The linker adds every entry to what the defining records say, and a weight stops at 255. A `WGT` entry for a variable the module defines itself is not allowed, because its `VAR` record already counts those uses. The compiler counts a slot's uses by the instructions with a kind 5 fix-up, the ones zero page makes smaller, by the loops they are in as for its own slots, and writes one `WGT` record after each function that has some (no more than 64 slots each; uses of more are not counted) and one at the end of the module for the variables of other modules it used.

### Field values

| Field | Values |
|---|---|
| Slot and variable **class** | 0 must be in zero page; 1 either; 2 never in zero page. |
| **Weight** | 0 to 255: how much the slot gains from zero page. Uses are counted, those in loops more heavily, and the count stops at 255. |
| Slot **kind** | 0 parameter, 1 local, 2 temporary. Parameters come first, in order. |
| `VAR` **flags** | None yet; the byte is 0. |
| `FUNC` **flags** | bit 0 `recursive`; bit 1 `interrupt`; bit 2 exported; bit 3 parameters and results are in registers (`asm` functions). |
| `CALL` **flags** | bit 0: the caller saves its frame around this call; bit 1: the call is through a pointer and the callee symbol is a class. |
| `CALL` **outer** | The function or class whose arguments were being stored when this call was made, or `$FFFF` ([`code-model.md`](code-model.md), "Calls inside arguments"). |
| `CLAS` **flags** | bit 0 `recursive`. |

## Code and fix-ups

A fix-up says: put the address of a target, plus the addend, at this offset in the code.

| Fix-up kind | Meaning |
|---|---|
| 1 | Two bytes: the address. The instruction never shrinks. |
| 2 | One byte: the low byte of the address. |
| 3 | One byte: the high byte of the address. |
| 4 | One byte: the address, which must be in zero page. Used for `(zp),Y`, `(zp,X)` and slots already known to be in zero page. |
| 5 | Two bytes: the address, in an instruction that has a zero page form, which it takes if and only if the final address, addend included, is below `$100`. Only in code. |

In code, a two-byte address is kind 5 exactly when its instruction has a zero page form, and kind 1 otherwise: `JSR`, `JMP`, `JMP (abs)`, and the `abs,Y` instructions with no `zp,Y` twin (all but `LDX`). In constant data a two-byte address is always kind 1. A kind that does not suit the opcode is a bad fix-up (link error 29).

The **target** of a fix-up is given by its symbol and slot fields:

| Symbol is | Slot | Target |
|---|---|---|
| a function | `$FF` | The function's entry. If the function is the one being defined, a two-byte fix-up, or one with an addend, is an offset into its code: a label, the target of a `JMP`, or of the `JSR` of a call through a pointer. |
| a function | 0 to 254 | That slot of the function's frame. |
| a pointer class | 0 to 254 | That parameter of the class's shared block. |
| a variable or constant data | `$FF` | Its address. |

### The size of an instruction

The compiler cannot know whether a variable will be in zero page. The rule is the assembler's, and the fix-up kind carries what it needs from the opcode:

> An instruction whose operand is a kind 5 fix-up takes the zero page form if and only if the final address, addend included, is below `$100`.

- In the object file every such instruction is written in its three-byte absolute form. This is the **written layout**.
- Offsets in `FIX` entries, label addends and branch displacements all refer to the written layout.
- A function's final size is the length of its `CODE` record less one for each of its kind 5 fix-ups whose address is in zero page: the fix-ups alone give it, and the code need not be read.
- The linker removes one byte from each instruction that takes the zero page form, changes its opcode to the zero page one (8 less, but `$64` and `$74` for the 65C02's `STZ` at `$9C` and `$9E`), and corrects every branch displacement and label that the removal moves. Shrinking only brings a branch and its target closer, so a branch that fits in the written layout always fits.
- Branches are ordinary two-byte relative instructions with their displacement already filled in. A branch whose target is too far in the written layout is written by the compiler as the opposite branch around a `JMP` to a label.
- Kind 1 never shrinks, whatever the address: `LDA v,Y` and `JMP (v)` stay three bytes with `v` in zero page.

Because `CODE` holds only instructions, the linker and the text renderer find instruction boundaries by decoding opcodes.

## What the linker reads

Each step reads the object files from start to end; there is no seek. Reading a file again costs less than holding what it says: what the linker can find again in the files it does not keep.

| Step | Reads | Holds |
|---|---|---|
| Pass 1, the names to keep | `SYM`, and the symbol of `FUNC`, `VAR` and `DATA`. Reports nothing: an error is found by the step that finds it without this one. | A hash of each name of one file; which hashes are those of names more than one `SYM` record names. |
| Pass 1, the tables | Every record but the bytes of `CODE` and `DATA`: symbols, variables and their weights, functions with their slots and calls, classes, members, `WGT`. `FIX` and `DFIX` are only checked. | A few bytes per function, slot, call, variable and class parameter, and per symbol of each file; while the files are read, the names of the symbols more than one record names, and a weight for a slot of a function not read yet. |
| Pass 1, what is kept | `FUNC`, `FIX`, `DFIX` and the symbol of `DATA`: every file, then each file again that has something kept after the reading passed it. | The entries of one `DFIX` record until its `DATA` says whose they are. |
| Pass 1, sizes and placement | `FUNC`, `FIX` (counting the kind 5 entries whose address is in zero page, per context), the length of `CODE`, and `DATA` for its size. | Nothing about a function once it is placed. |
| The map | `SYM` and the records of the map's lines: a reading of each file for the functions, one for the constant data and one for the variables, of the files that have some; after the image, of the files that name a class, for the class parameters. | The names one file's lines need. |
| Pass 2 | Every record. A kept function's `FIX` entries are held while its `CODE` is written, a `DFIX` record's while its `DATA` is written. | The fix-ups of one function or one table (at most 512); the names of the file's kept functions that have slots, for the map. |

A function linked for several contexts is written once for each, its `CODE` record read again for each copy after the first: the only time a file is read twice in one pass.

## What the linker keeps

The linker keeps a function if an entry point reaches it by calls, or if kept code or kept constant data takes its address ([`code-model.md`](code-model.md), "Sharing frames"). It keeps a variable or a piece of constant data only if a fix-up of kept code (any copy) or of kept constant data names it. A kept table of pointers therefore keeps the tables, variables and functions it points to; a table nothing kept names keeps nothing, not even the functions in it. What is not kept gets no address and no map line, and takes no storage, zero page included.

- In code, an address is taken by a kind 2, 3 or 5 fix-up (`#<f`, `#>f`, `LDA f,X`); a kind 1 fix-up naming a function is a call, which needs a `CALL` record of its own.
- `module.$init` is always kept, so a variable given an initial value is kept, whether or not anything else reads it.
- A symbol need only be defined if something kept names it: by a call, a fix-up or a `MEMB` record (which is not inside a function, so always counts). A name only dropped code or dropped data uses may be missing from every object file. Otherwise the link fails with error 18.
- The records of what is dropped are read once, for the sizes and the names, and not checked further: a bad fix-up in a dropped table is not found.

## Initial values and start-up

**Rule: whether a program links never depends on where the linker puts a variable.** A variable may land in zero page or main memory; both must work. So variables carry no initial bytes.

- The compiler turns every initialiser of a module-level or `static` variable into code in a function named `module.$init`, written at the end of the module. A module with no initialisers has no such function.
- The linker makes a function `$init`: a `JSR module.$init` for each module that has one, in the order the objects are given, then `RTS`.
- The linker makes the start-up function `$start`, the first thing in the code range, from the environment file:

| Step | Code | When |
|---|---|---|
| Stack | `LDX #n` / `TXS` | The environment has `stack n`. |
| Decimal flag | `CLD` | Always. |
| Initial values | `JSR $init` | Some module has initialisers. |
| The program | `JSR mainmodule.main` | Always. |
| Exit | `LDA #0` / `JMP addr`, or `JMP` to itself, or `RTS`, or `STP` | `exit call addr`, `exit loop`, `exit return`, `exit stop`. `STP` is the 65C02's `$DB`, so `exit stop` needs `cpu 65c02`. |

`$init` follows `$start`, and the objects' functions follow that.

The environment's `output` entry says what the file holds. With `output image`, the default, it is memory from the start of the code range to `$FFFF`, and the reset vector holds the address of `$start`. With `output raw` it is the bytes from the start of the code range through the last byte the linker placed there, with no padding and no vectors; `$start` is first, so the load address is the entry.

## Rendering as assembler text

The host tool `lo2asm` turns object files into asm17 source.

| Object | Text |
|---|---|
| Symbol `mod.name` | Label `mod__name`. |
| Slot `n` of `mod.func` | Label `mod__func__slotname`. |
| Parameter `n` of class `mod.type` | Label `mod__type__name`, its name from the `CLAS` records, or `mod__type__pN` if they give none. |
| A label inside a function | Local label `.L` followed by the written offset in hex. |
| A fix-up | The label, with `+addend` if not zero, and `<` or `>` for kinds 2 and 3. Kinds 1 and 5 look the same: the assembler chooses the zero page form by the value, as the linker does for kind 5. |
| `DATA` | `.byte` lines. |
| `WGT` | Nothing: it is only for the linker's choice of zero page. |
| An instruction the NMOS 6502 does not have (`STP`, `WAI`) | `.byte` and its opcode, the mnemonic in a comment: asm17 has no 65C02 mnemonics. Only one-byte instructions are written so far; `lo2asm` refuses one with an operand. |

Rendering one module needs no addresses and gives the text the snapshot tests compare. Rendering a whole program takes the object files in link order and the linker's map: it writes an equate for every variable and slot the map lists first, then `$start` and `$init` as the linker makes them (the `STP` of `exit stop` as `.byte $DB`), then the functions and constant data the map lists, in the same order the linker places them, and for `output image` the reset vector at `$FFFC`. For `output raw` there are no vectors: the assembler's output runs from the origin to the last byte written. Assembling that text must give the same bytes as the linker's own file.

A function the linker copies for several contexts is rendered once per copy the map lists, `mod.f@N` as label `mod__fX40N` with slots `mod__fX40N__slotname`. In a copy for context N, a `JSR` or `JMP` to a function, and a slot of a function that has a copy for N, mean that copy. Every other reference to a function, and every reference from constant data, means the copy its address stands for (`code-model.md`, "Interrupts"): the one in the context that calls through its pointer class, or else its first copy. Variables, constant data and class blocks are never copied.
