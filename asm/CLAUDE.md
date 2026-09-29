# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in toolchain/asm2. Run the commands below from this directory.

## Build Commands

```bash
# Full build and verification
./asmtestgen.sh

# Run assembler tests
python3 run_tests.py -q

# Build editor and run editor tests
python3 editor/tests/editor_tests.py -q

# Build just the emulator and initial bootstrap
make
```

The build succeeds when `17/out/asm.out == 17/out/asm_2.out` (self-assembly verification).

## Architecture

This is a self-hosting 6502 assembler built through progressive bootstrapping. The current assembler (`17/asm.asm`) can assemble its own source code.

Also, there is a vi-like editor with source code in `editor`

### Bootstrap Chain

A C bootstrap assembler assembles the initial versions, which then assemble progressively more capable versions (asm00 → asm01 → ... → asm17). Each version adds features needed by the next. Each version lives in its own subdirectory (`00/` through `17/`) with all its source files.

### Build Output Structure

Each version builds into its own `NN/out/` directory (e.g., `16/out/asm.out`). The root `out/` directory is used only for test outputs. The emulator auto-creates its `dump/` directory, so no symlinks or pre-creation are needed. `make clean` removes all per-version `out/` and `dump/` directories.

### Key Components

- **Instruction generators** (`NN/instgen.asm`): Generate `NN/out/inst.asm.out` files containing pre-computed instruction hash tables. These are `.include`d (as `out/inst.asm.out` relative to the version directory) by the assemblers to avoid runtime initialization.

- **Hash tables**: Used for both label lookup (`LHASHTAB` at $1F00) and instruction lookup (`IHASHTAB`). Hash entries are stored on a heap (`MEMP16`).

- **Macros**: Definitions are stored on the heap with parameter names. Invocations substitute arguments for parameters during expansion.

- **Two-pass assembly**: Pass 1 collects labels, Pass 2 resolves references and emits code.

### Memory Layout (asm17)

- `$0000-$00FF`: Zero page variables (see `.zeropage` section)
- `$0200-$03FF`: `FWDREF_LIST` (forward reference list, 512 bytes)
- `$0400-$04FF`: free (first half was `SCOPE_STACK` before Phase 3.6 of the
  source-stack unification work; second half was `MACRO_NAME_SAVE`, a
  128-byte buffer used by the pre-`ss_reserve_frame` `expand_macro` to
  stash the macro name across arg parsing -- reclaimed once expand_macro
  switched to ss_reserve_frame, which captures the name into the pending
  frame BEFORE arg parsing)
- `$0500-$05FF`: free (was `MACRO_ARG_BUF` before Phase 4.8)
- `$0600`: `TOKEN` buffer (current token being read, 128 bytes)
- `$0680-$068F`: `ELSE_SEEN_ARRAY` (per-nesting-level `.else` flags, 16 bytes,
  all used; accessed as `ELSE_SEEN_ARRAY - 1,Y` with Y = `COND_DEPTH` 1..16)
- `$0690-$06AF`: free (was `MACRO_ACTIVATION` 32-byte staging buffer until
  `expand_macro` switched to writing parsed slots directly into the new
  macro frame's payload region)
- `$0700`: `LHASHTAB` (label hash table)
- `$0800`: `IFDEF_DECISIONS` (256 bytes, deterministic pass-2 replay)
- `$2000+`: Generated code, then the heap grows upward from `HEAP`
- `$F000`: Source stack (grows downward)

The heap (`MEMP16`) grows upward storing hash entries, macro definitions, and forward references. The source stack (`SS_P16`) grows downward storing include-file contexts and macro activation frames; each frame begins with a 1-byte `frame_size` at offset 0 so push/pop and chain walks are O(1) per frame. Memory protection checks ensure heap and source stack don't collide, maintaining a 256-byte safety buffer for indexed addressing.

### Shared Code Pattern

Common code is factored into include files within each version directory:
- `17/common.asm`: Shared between `17/asm.asm` and `17/instgen.asm`
- `17/hash_table.asm`: Hash table implementation (included by common)

The hash table requires caller to define `HT_KEY` and `HT_V16` before including.

### Zero Page Conventions

Variables are allocated via `.byte 0` / `.word 0` in `.zeropage` section. Two-byte pointers use adjacent locations with a `16` suffix (e.g., `MEMP16`, `SS_P16`).

## Emulator Interface

The C emulator (`emulator.c`) provides memory-mapped I/O. Key addresses:
- `$F006`: Read byte from input
- `$F009`: Write byte to output
- `$F00C`: Write byte to error output

## Syntax Notes

The current assembler (asm17) uses standard 6502 syntax:
- `LDA #$42` for immediate mode
- `LDA $00` for zero page (automatic detection based on value)
- `LDA ($00),Y` for indirect indexed
- `LDA $1234,X` for indexed absolute

Early bootstrap levels (asm00-05) used non-standard syntax (`LDA#`, `LDAZ`, etc.) but asm06+ uses standard syntax.

### Expression Evaluation (asm13+)

Starting with asm13, the assembler supports expression evaluation with `+`, `-`, `<<`, and `>>` operators:

**Syntax:**
- `LDA #$10+$20` - Arithmetic in immediate mode
- `LDA #$01<<$04` - Left shift: $01 << 4 = $10
- `LDA #$80>>$02` - Right shift: $80 >> 2 = $20
- `foo = bar+$01` - Expressions in label assignments
- `.byte value+$05` - Expressions in data directives
- `LDA (ptr+$02,X)` - Expressions in address operands
- `LDA #'Z'-'A'` - Character constant arithmetic

**Operator Precedence:**
- Evaluation is strictly **left-to-right**
- No operator precedence: `$10+$20-$05` evaluates as `($10+$20)-$05`
- No parentheses for grouping (except for addressing modes)

**Byte Selectors:**
- `<` (low byte) and `>` (high byte) apply to the **entire expression result**
- `LDA #<addr+$10` means `<(addr+$10)`, not `(<addr)+$10`
- Byte selectors work with any expression: `LDA #>'A'+$100`

**Value Types:**
- Hex constants: `$10`, `$ABCD`
- Character literals: `'A'`, `'\n'`, `'\''`
- Labels: `foo`, `bar`
- All three types can be mixed in expressions

**Forward References:**
- If any term in an expression is a forward reference, the entire expression is treated as a forward reference
- The assembler resolves the complete expression in pass 2

### Conditional Assembly (asm14+, enhanced in asm17)

The assembler supports conditional assembly with `.ifdef`, `.ifndef`, `.else`, and `.endif` directives:

**Directives:**
- `.ifdef label` - Begin conditional block if label is defined (asm14+)
- `.ifndef label` - Begin conditional block if label is NOT defined (asm17+)
- `.else` - Alternative branch in conditional block (asm17+)
- `.endif` - End conditional block

**Basic Usage:**
```asm
DEBUG = $01          ; Define a label

.ifdef DEBUG
  LDA #$42           ; This code is assembled
.endif

.ifdef UNDEFINED
  LDA #$FF           ; This code is skipped
.endif

.ifndef PRODUCTION
  LDA #$01           ; Assembled if PRODUCTION not defined
.endif
```

**Using `.else`:**
```asm
.ifdef DEBUG
  LDA #$01           ; Debug code
.else
  LDA #$00           ; Production code
.endif

.ifndef FEATURE_X
  LDA #$10           ; Default behavior
.else
  LDA #$20           ; FEATURE_X enabled
.endif
```

**Nesting:**
- Conditional blocks can be nested up to 16 levels deep
- Each `.ifdef`/`.ifndef` must have a matching `.endif`
- Each conditional block can have at most one `.else`
- When a condition is false, nested conditionals are still parsed (for `.endif` matching) but their content is skipped

**Example with Nesting:**
```asm
.ifdef PLATFORM_6502
  LDA #$01
  .ifdef DEBUG
    JSR debug_init   ; Both conditions must be true
  .else
    JSR release_init ; PLATFORM_6502 true, DEBUG false
  .endif
.else
  .ifdef PLATFORM_65C02
    LDA #$02         ; PLATFORM_6502 false, PLATFORM_65C02 true
  .endif
.endif
```

**Command Line Defines:**
- Labels can be pre-defined via command line: `define:label`
- Multiple defines are supported: `./asm.out in out define:DEBUG define:FEATURE1`
- Pre-defined labels have value `$0001`

**Errors:**
- Error 19: `.endif without .ifdef` - Unmatched `.endif`
- Error 20: `Unclosed .ifdef` - Missing `.endif` at end of file
- Error 21: `Too many .ifdef directives` - IFDEF_DECISIONS buffer full (256 conditionals)
- Error 22: `.else without .ifdef` - `.else` outside conditional block
- Error 23: `Duplicate .else in conditional block` - Multiple `.else` in same block
- Error 24: `Conditional nesting exceeds 16 levels` - Too deeply nested
- Error 4: `Label expected` - `.ifdef`/`.ifndef` without a label name

### Macros (asm16+)

Starting with asm16, the assembler supports macros with parameters:

**Defining Macros:**
```asm
  .macro SET16 val ptr     ; Define macro with parameters
  LDA #<val
  STA ptr
  LDA #>val
  STA ptr+$01
  .endmacro
```

**Invoking Macros:**
```asm
  SET16 $1234 $10          ; Expands with val=$1234, ptr=$10
```

**Features:**
- Parameters are simple text substitution
- Local labels (`.label`) in macros are scoped to each invocation
- Macros can use expressions: `ptr+$01` expands correctly
- Up to 8 parameters per macro

**Errors:**
- Error 1E: `Unclosed macro` - Missing `.endmacro`
- Error 1F: `Macro not found` - Undefined macro invocation
- Error 20: `Expected macro name` - `.macro` without name
- Error 22: `Too many macro arguments` - More than 8 parameters

## Migration Patterns

Lessons learned from syntax migrations (e.g., DATA → .data):

1. **Global replacements need context awareness** - Avoid blind find/replace when identifiers share common substrings (e.g., `DATA` vs `MODE_DATA`). Check for compound identifiers before replacing.

2. **File copying requires systematic include updates** - When creating a new version, copy the entire version directory. Source filenames no longer have version suffixes, so only build script references need updating.

3. **Phased migration works well** - Add new feature alongside old, verify everything works, then remove old. This provides safety checkpoints at each phase.

4. **Self-hosting is powerful verification** - The assembler assembling itself catches subtle issues that unit tests might miss. Always run the full build chain after changes.

5. **Test suite retention is valuable** - Keep the old test suite as reference even when removing obsolete tests from the new one.
