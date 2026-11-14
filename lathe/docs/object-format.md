# Lathe: object files, version 1

Status (2026-11-13): specification for stages 1 to 5. It will grow (regions, banks, far calls) and the version byte changes when it does.

The compiler writes one object file (`.lo`) per module. The linker reads all of them. A host tool can also render them as asm17 text, which is how the linker is checked ([`architecture.md`](architecture.md)).

## Conventions

- Multi-byte numbers are little-endian.
- A **string** is a length byte followed by that many bytes.
- A file is a sequence of **records**: a type byte, a two-byte body length, the body.
- **Names** are lower case. A module-level name is `module.name`. Nothing else is named globally: a slot is identified by its function and its number.
- **Symbols** are numbered from 0 in the order their `SYM` records appear in the file. Every symbol a module defines or refers to has a `SYM` record before its first use.

## Records

| Type | Name | Body |
|---|---|---|
| `$01` | `MOD` | version (1 byte, value 1), CPU (0 = 6502, 1 = 65C02), module name (string). First record. |
| `$02` | `IMP` | Name of an imported module (string). |
| `$03` | `SYM` | Kind (1 byte), name (string). Kinds: 1 function, 2 variable, 3 constant data, 4 pointer class. |
| `$04` | `VAR` | Defines a module-level variable: symbol (2), size (2), class (1), weight (1), flags (1). A variable is storage only; it has no initial value in the object file. |
| `$05` | `DATA` | Defines constant data: symbol (2), then the bytes. |
| `$06` | `DFIX` | Fix-ups for the `DATA` record just before it. Entries as in `FIX`. |
| `$07` | `FUNC` | Starts a function: symbol (2), flags (1). Followed by its `SLOT`, `CALL`, `FIX` and `CODE` records and closed by `ENDF`. |
| `$08` | `SLOT` | One slot of the function, in slot-number order from 0: size (2), class (1), weight (1), kind (1), name (string). |
| `$09` | `CALL` | One call the function makes: callee symbol (2), flags (1), outer symbol (2). |
| `$0A` | `FIX` | All fix-ups for the function's code, sorted by offset. Each entry is 8 bytes: offset (2), kind (1), symbol (2), slot (1), addend (2). |
| `$0B` | `CODE` | The function's instructions. Instructions only: no data bytes. |
| `$0C` | `ENDF` | Ends the function. Empty body. |
| `$0D` | `CLAS` | A pointer class this module uses: symbol (2), flags (1), number of parameters (1), then the size of each parameter (2 each). |
| `$0E` | `MEMB` | This module takes a function's address as a class: class symbol (2), function symbol (2). |
| `$00` | `END` | Last record. Empty body. |

Order within a function: `FUNC`, every `SLOT`, every `CALL`, `FIX`, `CODE`, `ENDF`. Everything the linker's first pass needs comes before the code.

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
| 1 | Two bytes: the address. |
| 2 | One byte: the low byte of the address. |
| 3 | One byte: the high byte of the address. |
| 4 | One byte: the address, which must be in zero page. Used for `(zp),Y`, `(zp,X)` and slots already known to be in zero page. |

The **target** of a fix-up is given by its symbol and slot fields:

| Symbol is | Slot | Target |
|---|---|---|
| a function | `$FF` | The function's entry. If the function is the one being defined, the addend is an offset into its code: a label. |
| a function | 0 to 254 | That slot of the function's frame. |
| a pointer class | 0 to 254 | That parameter of the class's shared block. |
| a variable or constant data | `$FF` | Its address. |

### The size of an instruction

The compiler cannot know whether a variable will be in zero page. The rule is the assembler's:

> An instruction whose operand is a two-byte fix-up (kind 1), and whose opcode has a zero page form, takes the zero page form if and only if the final address, addend included, is below `$100`.

- In the object file every such instruction is written in its three-byte absolute form. This is the **written layout**.
- Offsets in `FIX` entries, label addends and branch displacements all refer to the written layout.
- The linker removes one byte from each instruction that takes the zero page form, changes its opcode, and corrects every branch displacement and label that the removal moves. Shrinking only brings a branch and its target closer, so a branch that fits in the written layout always fits.
- Branches are ordinary two-byte relative instructions with their displacement already filled in. A branch whose target is too far in the written layout is written by the compiler as the opposite branch around a `JMP` to a label.
- `JMP` and `JSR` have no zero page form and never shrink.

Because `CODE` holds only instructions, the linker and the text renderer find instruction boundaries by decoding opcodes.

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
| Exit | `LDA #0` / `JMP addr`, or `JMP` to itself, or `RTS` | `exit call addr`, `exit loop`, `exit return`. |

`$init` follows `$start`, and the objects' functions follow that. The reset vector holds the address of `$start`.

## Rendering as assembler text

The host tool `lo2asm` turns object files into asm17 source.

| Object | Text |
|---|---|
| Symbol `mod.name` | Label `mod__name`. |
| Slot `n` of `mod.func` | Label `mod__func__slotname`. |
| A label inside a function | Local label `.L` followed by the written offset in hex. |
| A fix-up | The label, with `+addend` if not zero, and `<` or `>` for kinds 2 and 3. |
| `DATA` | `.byte` lines. |

Rendering one module needs no addresses and gives the text the snapshot tests compare. Rendering a whole program takes the object files in link order and the linker's map: it writes an equate for every variable and slot first, then `$start` and `$init` as the linker makes them, then the functions the linker kept, in the same order the linker places them. Assembling that text must give the same bytes as the linker's own image.
