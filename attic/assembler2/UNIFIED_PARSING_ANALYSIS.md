# Unified Parsing for Conditional Assembly - Implementation Analysis

> **Attic note:** historical. Paths (`22/`, `23/`, `editor/`, `assembler2/`) are from the old assembler2 layout; the live code is `asm/` (stages 00-17) and `editor/`. See `attic/assembler2/README.md`.


## Core Principle
**In skipping mode (SKIP_DEPTH > 0), follow the exact same parsing flow as normal mode, but suppress state-changing operations.**

## CRITICAL NOTES

### 1. Use Commit Helper Script
**ALWAYS use the `commit` helper script for commits during this work:**
```bash
./commit -m "First line" [-m "Additional line" ...]
```
Do NOT use `git commit` directly.

### 2. IFDEF_DECISIONS Buffer Safety
The existing code already protects against consuming IFDEF_DECISIONS entries for nested blocks within skipped regions. The check in `process_conditional_common` (line 294) prevents IFDEF_INDEX from incrementing when already skipping. **This protection is preserved by unified parsing.** See detailed explanation below.

## Benefits
1. **Single parsing path** - No duplicate tokenization/directive detection logic
2. **Syntax validation** - Invalid syntax in skipped blocks will now be caught (acceptable behavior change)
3. **Simpler code** - Conditional checks moved to operation sites, not parsing flow
4. **Easier maintenance** - One parsing path to understand and modify

## Existing Flag
**SKIP_DEPTH** already serves as our flag:
- `SKIP_DEPTH == 0`: Normal mode (execute all operations)
- `SKIP_DEPTH > 0`: Skipping mode (suppress state changes)

Zero page location already allocated in `directives.asm:29`

## Critical: IFDEF_DECISIONS Buffer Management

**IMPORTANT**: The existing code already handles this correctly, and the unified parsing approach preserves this behavior.

**The concern**: When skipping due to a false `.ifdef`, if we encounter a nested `.ifdef`, we must NOT consume entries from the `IFDEF_DECISIONS` buffer.

**How it works** (in `directives.asm:process_conditional_common`):
```asm
process_conditional_common:
  INC COND_DEPTH                    ; Always increment nesting depth
  LDA COND_DEPTH
  CMP #17
  BCS .nesting_too_deep
  LDA SKIP_DEPTH                    ; ← KEY CHECK (line 294)
  BNE .already_skipping             ; Already skipping, don't record or evaluate
  ; [Only reached when NOT skipping]
  ; Pass 1: Evaluate condition and store in IFDEF_DECISIONS[IFDEF_INDEX++]
  ; Pass 2: Read from IFDEF_DECISIONS[IFDEF_INDEX++]
.already_skipping:
  JMP skip_rest_of_line             ; Skip without touching IFDEF_INDEX
```

**Behavior**:
- When SKIP_DEPTH > 0 (already skipping):
  - COND_DEPTH still increments (needed for matching `.endif`)
  - IFDEF_INDEX does NOT increment (no decision stored/read)
  - Nested conditionals within skipped blocks are ignored

- When SKIP_DEPTH == 0 (not skipping):
  - COND_DEPTH increments
  - IFDEF_INDEX increments (decision stored in pass 1, read in pass 2)

**Example trace**:
```asm
; Pass 1:
.ifdef UNDEFINED    ; SKIP_DEPTH=0→1, COND_DEPTH=0→1, IFDEF_INDEX=0→1, store $00
  .ifdef DEBUG      ; SKIP_DEPTH=1, COND_DEPTH=1→2, IFDEF_INDEX=1 (no change!)
  .endif            ; SKIP_DEPTH=1, COND_DEPTH=2→1
.endif              ; SKIP_DEPTH=1→0, COND_DEPTH=1→0

; Pass 2: Same behavior, IFDEF_INDEX goes 0→1 only
```

**Unified parsing impact**: NONE - The check at line 294 happens inside `process_conditional_common`, which is still called the same way. Our changes only affect how we get TO the directive handlers, not what happens inside them.

**Verification test**: Include nested `.ifdef` blocks in skipped regions to ensure IFDEF_INDEX stays synchronized across passes.

**Debug verification** (if enable_debug is set): Can add temporary debug output in `process_conditional_common` to print IFDEF_INDEX values and verify they match between passes:
```asm
  ; After line 311 (pass 1) and line 329 (pass 2):
  .ifdef enable_debug
  LDA IFDEF_INDEX
  ; Print value to verify synchronization
  .endif
```

## Operations to Suppress When Skipping

### 1. Code Emission (`emit` function)
**Location**: `output.asm:20-38`

**Current code**:
```asm
emit:
  BIT IN_ZEROPAGE
  BMI .in_zeropage
  INC16 PC16
  BIT PASS
  BPL .skip
  JMP write
.skip:
  RTS
```

**Proposed change**:
```asm
emit:
  ; Check if skipping conditional assembly
  LDA SKIP_DEPTH
  BNE .skip           ; Skip if in false .ifdef block

  BIT IN_ZEROPAGE
  BMI .in_zeropage
  INC16 PC16
  BIT PASS
  BPL .skip
  JMP write
.skip:
  RTS
.in_zeropage:
  ; [existing zeropage logic - also needs skip check]
```

**Call sites affected**: All emit calls will automatically suppress when SKIP_DEPTH > 0
- `instructions.asm`: emit_instruction (4 call sites)
- `directives.asm`: data directives (.byte/.word/.asciiz) (8 call sites)
- Total: ~12 call sites, all fixed with one change

### 2. Label Capture and Hash Operations
**Location**: `labels.asm:103-186` (capture_label function)

**Operations to suppress in pass 1**:
- Line 155: `JSR hash_add` - Don't add label to hash table
- Line 165-166: Update LABEL_SCOPE16 and commit hash for globals
- Line 170: `JSR store_hash_value` - Don't store label value

**Proposed approach**: Add skip check at start of pass 1 section:
```asm
.pass_1:
  ; Check if skipping - if so, just parse but don't capture
  LDA SKIP_DEPTH
  BNE .skip_capture_parse_only

  ; LABEL_TYPE already set
  ; Add key to hash table first
  JSR select_label_hash_table
  JSR hash_add
  BCS .duplicate_label
  ; [rest of existing logic]

.skip_capture_parse_only:
  ; Parse the syntax but don't capture to hash
  JSR check_for_value
  BCS .skip_has_equals
  ; No = found, just skip spaces and return
  JMP .skip_spaces_and_return_processed_flag
.skip_has_equals:
  JSR read_value  ; Parse but don't store
  JMP .return_processed
```

**Call sites**: Only called once from main loop (asm.asm:241)

### 3. PC Updates (`update_pc` function)
**Location**: `output.asm:46-61`

The `* = $xxxx` directive calls `update_pc`. Should suppress when skipping.

**Proposed change**: Add skip check in update_pc:
```asm
update_pc:
  ; Check if skipping
  LDA SKIP_DEPTH
  BNE .skip_update

  BIT IN_ZEROPAGE
  BMI .no_fill
  ; [existing logic]

.skip_update:
  RTS
```

Or check in capture_label before calling:
```asm
.pc_value_present:
  JSR read_value
  JSR check_for_end_of_line
  BCC .err_unexpected_text
  ; Don't update PC if skipping
  LDA SKIP_DEPTH
  BNE .skip_pc_update
  JSR update_pc
.skip_pc_update:
  SEC
  RTS
```

### 4. Label Lookup Failures
**Location**: Various places that call `find_in_hash`

**Current behavior**: Fails with error if label not found (in expressions, operands)

**Desired behavior when skipping**: Don't error on missing labels

**Strategy**: Suppress errors, treat as forward reference or zero value

**Example location** - `expressions.asm` (parse_value):
```asm
parse_token:
  ; [token read]
  JSR find_in_hash
  BCS .not_found
  ; [existing logic]
.not_found:
  ; Check if skipping - if so, use dummy value
  LDA SKIP_DEPTH
  BNE .skip_mode_dummy
  JMP err_label_not_found
.skip_mode_dummy:
  ; Set dummy value and continue
  LDA #$00
  STA OPERAND16
  STA OPERAND16 + 1
  STA IS_FWDREF
  RTS
```

### 5. Macro Definition Capture
**Location**: `macro_expansion.asm:30-105` (dir_macro)

**Proposed approach**: Don't enter capture mode if skipping

**Implementation**:
```asm
dir_macro:
  ; Check if skipping - if so, just parse line and return
  LDA SKIP_DEPTH
  BNE .skip_macro_def

  ; [existing macro definition logic]

.skip_macro_def:
  ; Parse the macro name and parameters without capturing
  JSR check_for_end_of_line
  BCC .skip_read_name
  JMP skip_rest_of_line
.skip_read_name:
  JSR read_token
  ; Skip parameters
.skip_param_loop:
  JSR check_for_end_of_line
  BCS .skip_params_done
  JSR read_token
  JSR check_for_end_of_line
  BCS .skip_params_done
  CMP #','
  BNE .skip_params_done
  JSR read_char
  JMP .skip_param_loop
.skip_params_done:
  RTS
```

**Also need to handle `.endmacro`** when skipping:
```asm
dir_endmacro:
  ; Check if we're skipping - if so, just ignore (don't error)
  LDA SKIP_DEPTH
  BNE .skip_endmacro

  JMP err_endmacro_without_macro

.skip_endmacro:
  JMP skip_rest_of_line
```

## Modified Main Assembly Loop

**Current**: Three separate code paths (normal, skipping, macro capture)

**Proposed**: Two code paths (macro capture stays separate, normal + skipping unified)

```asm
.line_loop:
  JSR read_char
  BCC .character_read
  ; [EOF checks remain the same]
.character_read:
  INC16 CURR_LINE16

  ; Check if we're capturing macro body (stays separate)
  LDY IN_MACRO_DEF
  BEQ .not_capturing_macro
  JSR capture_macro_line
  JMP .line_loop

.not_capturing_macro:
  ; REMOVED: Check if we're skipping
  ; Now normal and skipping use same parsing path

  CMP #' '
  BEQ .line_starts_with_space
  JSR check_for_end_of_line
  BCS .back_to_line_loop
  JSR capture_label        ; Now handles SKIP_DEPTH internally
  BCC .check_for_opcode
  BCS .back_to_line_loop

.line_starts_with_space:
  JSR check_for_end_of_line
  BCS .back_to_line_loop

.check_for_opcode:
  CMP #'.'
  BNE .opcode

.directive:
  JSR read_char
  JSR process_directive    ; Now handles SKIP_DEPTH internally
  ; [rest remains the same]

.opcode:
  JSR lookup_mnemonic
  BCS .macro
  JSR parse_operand
  JSR emit_instruction     ; emit() now handles SKIP_DEPTH internally
  ; [rest remains the same]
```

## Directive Processing Changes

**Location**: `directives.asm:59-77` (process_directive)

**Current**: Dispatches to all directives

**Proposed**: Check SKIP_DEPTH and only allow conditional directives

```asm
process_directive:
  JSR read_token
  JSR select_instruction_hash_table
  JSR find_in_hash_instruction
  BCS .not_found

  ; Check for MODE_DIRECTIVE
  LDA (TABP16),Y
  CMP #MODE_DIRECTIVE
  BNE .not_found

  ; Extract handler address
  INY
  LDA (TABP16),Y
  STA JUMP_TARGET16
  INY
  LDA (TABP16),Y
  STA JUMP_TARGET16 + 1

  ; Check if skipping
  LDA SKIP_DEPTH
  BEQ .not_skipping

  ; In skip mode - only allow conditional directives
  CMPI16 JUMP_TARGET16, dir_ifdef
  BEQ .dispatch
  CMPI16 JUMP_TARGET16, dir_ifndef
  BEQ .dispatch
  CMPI16 JUMP_TARGET16, dir_else
  BEQ .dispatch
  CMPI16 JUMP_TARGET16, dir_endif
  BEQ .dispatch
  ; Not conditional - skip rest of line and return
  JMP skip_rest_of_line

.not_skipping:
.dispatch:
  JMP do_jump

.not_found:
  JMP err_unknown_directive
```

## Changes Summary

### Files to modify:
1. **asm.asm** (main loop):
   - Remove skipping mode code path (lines 208-235)
   - Delete: `.not_skipping:`, `.skip_not_space:`, `.skip_check_directive:`, `.skip_line:`
   - Normal path now handles both modes

2. **output.asm** (emit functions):
   - Add SKIP_DEPTH check at start of `emit` (3 lines added)
   - Add SKIP_DEPTH check in `update_pc` (3 lines added)

3. **labels.asm** (capture_label):
   - Add skip handling in pass 1 section (~15 lines added)
   - Parse syntax but don't modify hash table when skipping

4. **directives.asm** (directive processing):
   - Add conditional dispatch logic to `process_directive` (~15 lines added)
   - Modify `dir_macro` to skip capture when SKIP_DEPTH > 0 (~20 lines added)
   - Modify `dir_endmacro` to not error when SKIP_DEPTH > 0 (3 lines added)
   - Remove `process_conditional_directive` function (no longer needed, ~35 lines removed)

5. **expressions.asm** (parse_value):
   - Add SKIP_DEPTH check when label not found (~10 lines added)
   - Use dummy value instead of error

### Lines of code change estimate:
- **Added**: ~70 lines (skip checks in various operations)
- **Removed**: ~60 lines (duplicate skipping mode parsing path)
- **Net change**: +10 lines, but much cleaner architecture

## Testing Strategy

### Phase 1: Basic Validation
1. Run existing test suite - should pass without changes
2. Self-assembly (asm23 assembles itself) - critical validation

### Phase 2: Behavior Changes
Test that invalid syntax in skipped blocks now errors:
```asm
.ifdef UNDEFINED
  INVALID SYNTAX HERE  ; Should now error (previously ignored)
.endif
```

### Phase 3: Edge Cases
1. **Nested .ifdef with various depths** - Verify IFDEF_INDEX synchronization:
   ```asm
   ; This test verifies IFDEF_INDEX is NOT incremented for nested blocks in skipped regions
   .ifdef UNDEFINED
     ; This block skipped - no IFDEF_INDEX increment
     .ifdef ALSO_UNDEFINED
       ; Nested skip - still no IFDEF_INDEX increment
     .endif
   .endif

   .ifdef DEFINED
     ; This block assembled - IFDEF_INDEX should increment by exactly 1
     ; (not 3, which would happen if nested blocks consumed indices)
   .endif
   ```

2. **.ifdef with .macro definitions inside** - Macros in skipped blocks should be ignored
3. **Forward references in skipped blocks** - Should not error on undefined labels
4. **PC manipulation in skipped blocks** - `* = $xxxx` should not change PC
5. **Invalid syntax in skipped blocks** - Should now error (behavior change)

## Implementation Order

**IMPORTANT - Use Commit Helper Script**:
For all commits during this work, use the `commit` helper script:
```bash
./commit -m "First line of message" [-m "Additional line" ...]
```
Do NOT use `git commit` directly. The helper script ensures proper formatting and attribution.

**Commit after each step** to create clean checkpoints that can be reverted if needed.

### Steps:

1. **Add skip check to emit()** - Most impactful, easiest to verify
   - Modify `output.asm:emit` to check SKIP_DEPTH
   - Test: `./asmtestgen.sh` should pass
   - Commit: `./commit -m "Add SKIP_DEPTH check to emit()"`

2. **Add skip check to update_pc()** - Handle PC manipulation
   - Modify `output.asm:update_pc` to check SKIP_DEPTH
   - Test: `./asmtestgen.sh` should pass
   - Commit: `./commit -m "Add SKIP_DEPTH check to update_pc()"`

3. **Modify capture_label** - Add parse-only path for skipping
   - Modify `labels.asm:capture_label` pass 1 section
   - Test: `./asmtestgen.sh` should pass
   - Commit: `./commit -m "Add parse-only mode to capture_label when skipping"`

4. **Add dummy value handling in parse_value** - Handle undefined labels
   - Modify `expressions.asm:parse_value` to not error when SKIP_DEPTH > 0
   - Test: `./asmtestgen.sh` should pass
   - Commit: `./commit -m "Suppress label lookup errors when skipping"`

5. **Modify dir_macro and dir_endmacro** - Macro handling
   - Modify `directives.asm:dir_macro` to skip capture mode
   - Modify `directives.asm:dir_endmacro` to not error when skipping
   - Test: `./asmtestgen.sh` should pass
   - Commit: `./commit -m "Handle macro directives in skip mode"`

6. **Update process_directive** - Conditional dispatch
   - Modify `directives.asm:process_directive` for conditional dispatch
   - Test: `./asmtestgen.sh` should pass
   - Commit: `./commit -m "Add conditional dispatch to process_directive"`

7. **Remove old skipping code path from main loop** - Final cleanup
   - Remove lines 208-235 from `asm.asm`
   - Test: `./asmtestgen.sh` should pass
   - Commit: `./commit -m "Remove separate skipping mode code path"`

8. **Remove process_conditional_directive** - No longer needed
   - Remove function from `directives.asm` (lines 143-176)
   - Test: `./asmtestgen.sh` should pass
   - Commit: `./commit -m "Remove obsolete process_conditional_directive"`

Each step can be tested individually with self-assembly as validation.

---

## Implementation Status (Updated 2026-02-10)

### Completed Steps (1-6) ✓

**Steps 1-6 have been successfully implemented and committed.** The infrastructure for unified parsing is in place:

1. ✓ **emit() suppression** - Uses SKIP_DEPTH check with PHA/PLA to preserve A register
2. ✓ **update_pc() suppression** - Prevents PC updates when skipping
3. ✓ **capture_label parse-only mode** - Parses label syntax without capturing to hash table
4. ✓ **parse_value error suppression** - Returns dummy values for undefined labels when skipping
5. ✓ **Macro directive handling** - `.macro`/`.endmacro` parse but don't capture when skipping
6. ✓ **Conditional directive dispatch** - `process_directive` only allows conditionals when skipping

**Key implementation details:**
- `SKIP_FLAG` was initially created as a fast BIT-testable flag (bit 7 set when SKIP_DEPTH > 0)
- Discovered that `SKIP_FLAG` must be defined in `asm.asm` (not `directives.asm`) to avoid forward reference issues
- Final implementation uses `SKIP_DEPTH` directly with PHA/PLA in `emit()` to preserve A register
- All 456 tests pass, self-assembly succeeds

### Step 7 Status: DEFERRED ⏸️

**Attempted:** Removal of old skipping code path from main loop (lines 209-236 in `asm.asm`)

**Result:** Self-assembly failed with "Error 8: Branch out of range in common.asm at line 116"

**Root cause analysis:**
The assembler uses a forward reference store/replay mechanism to guarantee consistent addressing modes between passes. When the old skipping code path was removed:

1. Pass 1 and Pass 2 followed different code paths through the main loop
2. This caused subtle differences in PC values between passes
3. Branch offset calculations in pass 2 used incorrect PC values
4. Branches that should have been in range appeared out of range

**What was tried:**
- Adding defensive SKIP_FLAG synchronization in `dir_endif`
- Moving SKIP_FLAG definition to different locations
- Using SKIP_DEPTH directly instead of SKIP_FLAG
- Various branch restructuring in `common.asm`

**The actual problem:** The old skipping code path serves a critical function that the unified parsing approach doesn't yet replicate: **ensuring that skipped code has ZERO effect on pass consistency**.

### What's Needed for Step 7

To safely remove the old skipping code path, we need to ensure that **all parsing operations in skipped blocks are perfectly idempotent and have identical behavior in both passes**.

#### Current Issue

When unified parsing processes a skipped block, it still calls:
- `lookup_mnemonic` - Shouldn't have relevnt side effects
- `parse_operand` - Creates forward references; need to stop that happeniing

These operations may store forward reference decisions or affect state in ways that differ between passes, breaking the store/replay invariant.

#### Proposed Solution: Guard Forward Reference Recording

The conditional directives themselves need to ensure forward reference consistency. Specifically:

**1. Add pass-tracking to conditional state**

In `directives.asm`, track whether we're skipping in each pass:
```asm
IFDEF_SKIP_P1:  .byte   ; SKIP_DEPTH during pass 1 (stored per .ifdef)
IFDEF_SKIP_P2:  .byte   ; SKIP_DEPTH during pass 2 (must match!)
```

**2. Store skip state with IFDEF_DECISIONS**

Extend the IFDEF_DECISIONS buffer to store not just the condition result, but also whether that block was skipped:
```asm
; Current: IFDEF_DECISIONS[index] = $00 (skip) or $FF (don't skip)
; Proposed: IFDEF_DECISIONS[index] has bits:
;   bit 7: condition result ($00=skip, $80=don't skip)
;   bit 0: pass 1 skip state
;   bit 1: pass 2 skip state
```

**3. Verify consistency in .endif**

When exiting a conditional block, verify that SKIP_DEPTH had the same value in both passes:
```asm
dir_endif:
  ; ... existing logic ...
  BIT PASS
  BPL .pass1_endif
  ; Pass 2: verify skip state matched pass 1
  LDA SKIP_DEPTH_PASS1  ; Stored during pass 1
  CMP SKIP_DEPTH        ; Current pass 2 value
  BEQ .consistent
  JMP err_pass_mismatch ; New error: passes diverged!
.consistent:
  ; ... continue ...
```

**4. Guard all forward reference recording**

In `forward_ref.asm`, add checks before recording:
```asm
store_forward_ref:
  ; Don't record forward refs when skipping
  LDA SKIP_DEPTH
  BNE .skip_recording   ; Skip if in conditional block
  ; ... existing forward ref logic ...
.skip_recording:
  RTS
```

## Behavior Changes (Acceptable)

**Before**: Syntax inside false .ifdef blocks is not parsed, any text accepted
```asm
.ifdef UNDEFINED
  this is complete garbage and it's fine!
.endif
```

**After**: Syntax inside false .ifdef blocks IS parsed, must be valid
```asm
.ifdef UNDEFINED
  this is complete garbage  ; ERROR: Unknown instruction "this"
.endif
```

This is acceptable per user requirements - better to catch errors early.

## Performance Impact

**Neutral to slightly positive**:
- Skip checks are simple flag tests (LDA + BNE = 5 cycles worst case)
- Eliminates duplicate directive detection in skip mode (saves code)
- No additional memory required (SKIP_DEPTH already exists)

## Future Extensions

Once conditional assembly uses unified parsing, macro capture could be evaluated:
- Could macro capture become a "capture all, parse none" mode?
- Would require careful handling of nested strings, escapes
- Defer this analysis until after .ifdef consolidation is complete and tested
