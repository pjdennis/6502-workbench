# Plan: Migrate Accumulator Addressing Syntax

## Status: COMPLETE

## Summary

Successfully migrated accumulator addressing syntax from `ASL A` to `ASL` (no operand).

**Commits:**
- fe7035c: Phase 1 - asm18 supports both syntaxes
- e8e2e8d: Phase 2 - asm19 source uses new syntax, parser supports both
- 59cfac4: Phase 3 - asm19 removes old syntax support

**Results:**
- Cleaner parsing with no ambiguity between accumulator mode and label lookup
- asm18: 62 tests pass (supports both syntaxes for backward compatibility)
- asm19: 59 tests pass (new syntax only)

## Goal
Remove the "A" operand requirement for accumulator mode instructions (ASL, LSR, ROL, ROR).

**Current syntax:** `ASL A`, `LSR A`, `ROL A`, `ROR A`
**New syntax:** `ASL`, `LSR`, `ROL`, `ROR` (no operand)

This simplifies parsing and eliminates ambiguity between accumulator mode and label lookup.

---

## Background

### Instructions Supporting Accumulator Mode
Only 4 instructions in 6502 support accumulator addressing:
- **ASL** - Arithmetic Shift Left (opcode $0A)
- **LSR** - Logical Shift Right (opcode $4A)
- **ROL** - Rotate Left (opcode $2A)
- **ROR** - Rotate Right (opcode $6A)

### Current Implementation (asm18/asm19)

**Parsing logic** (lines 1418-1433 in asm18.asm):
1. When operand is not #, (, $, <, or >, goes to `.label_or_acc_operand`
2. Reads token into TOKEN buffer
3. Checks if token is exactly "A" (single character)
4. If yes → accumulator mode
5. If no → label lookup

**Problem:** This creates ambiguity and requires look-ahead. For `ASL A`:
- Could be accumulator mode
- Could be a label named "A"
- Parser must read token first to disambiguate

---

## Migration Strategy

### Phase 1: Modify asm18 to Accept Both Forms
**Goal:** Support both `ASL A` (old) and `ASL` (new) syntax

**Changes to asm18.asm:**

1. **Modify `.implied_mode` handler** (around line 1056)
   - Currently: sets MODE_NONE for all implied instructions
   - New: try MODE_ACC first using existing `find_opcode_for_mode`
   - If MODE_ACC not found → fall back to MODE_NONE

2. **Keep `.label_or_acc_operand` unchanged**
   - Still supports `ASL A` for backward compatibility
   - Label "A" will work in other contexts

**Implementation:**
```asm
.implied_mode
  PHA                  ; Save next char
  ; Try accumulator mode first
  LDA #MODE_ACC
  STA ADDR_MODE
  JSR find_opcode_for_mode
  BCC .use_accumulator  ; C=0 means opcode found
  ; No accumulator mode - use implied
  LDA #MODE_NONE
  STA ADDR_MODE
.use_accumulator
  LDA #$00
  STA OPERAND_L
  STA OPERAND_H
  PLA
  JMP emit_instruction
```

**Testing:**
- Update `tests/run_tests.sh` to accept test file and assembler as arguments
- Add tests for both `ASL A` and `ASL` (and LSR, ROL, ROR) to asm18_tests.txt
- Run: `./tests/run_tests.sh tests/asm18_tests.txt out/asm18.out`

**Verification:**
```bash
./asmtestgen.sh  # Full build
./tests/run_tests.sh tests/asm18_tests.txt out/asm18.out  # asm18 tests
./tests/run_tests.sh  # asm19 tests (default)
```

---

### Phase 2: Update asm19 Source to New Syntax
**Goal:** Change all accumulator instructions in asm19.asm to use new syntax

**Files to modify:**
- asm19.asm
- instgen19.asm
- All common19.asm, hash_table19.asm, etc. (any that use ASL A / LSR A / ROL A / ROR A)

**Search pattern:**
```bash
grep -n "ASL A\|LSR A\|ROL A\|ROR A" asm19.asm instgen19.asm common19.asm hash_table19.asm errors19.asm fwdref19.asm file_stack19.asm to_decimal19.asm
```

**Changes:**
- `ASL A` → `ASL`
- `LSR A` → `LSR`
- `ROL A` → `ROL`
- `ROR A` → `ROR`

**Verification:**
- asm18 (with both forms supported) should successfully assemble asm19
- Self-hosting check should pass

```bash
./asmtestgen.sh  # Should succeed
# Verify asm19.out == asm19_2.out
```

---

### Phase 3: Remove Old Syntax from asm19
**Goal:** Remove support for `ASL A` form in asm19

**Changes to asm19.asm:**

1. **Remove `.label_or_acc_operand` complexity**
   - Currently checks if token is exactly "A"
   - New: treat "A" as a label, no special case

2. **Simplify parsing logic** (lines 1050-1055)
   ```asm
   .not_msb
     ; Must be a label (no more accumulator check)
     JMP .is_label
   ```

3. **Keep the improved `.implied_mode`**
   - Uses find_opcode_for_mode to detect accumulator support

4. **Rename `.label_or_acc_operand` → `.is_label`**
   - Remove token == "A" check
   - Go directly to label lookup

**Testing:**
- Verify `ASL` still works (accumulator mode)
- Verify `ASL A` now treats "A" as a label (should fail if A not defined)
- Add negative test: `ASL A` without label A should error

**Verification:**
```bash
./asmtestgen.sh
./tests/run_tests.sh  # asm19 tests
```

---

## Test Plan

### Phase 1: Update Test Runner

Modify `tests/run_tests.sh` to accept optional arguments:
```bash
#!/bin/bash
# Usage: ./run_tests.sh [test_file] [assembler]
# Defaults: tests/asm19_tests.txt out/asm19.out

TEST_FILE=${1:-tests/asm19_tests.txt}
ASSEMBLER=${2:-out/asm19.out}

# ... rest of script uses $TEST_FILE and $ASSEMBLER
```

### Phase 1: Tests (add to asm18_tests.txt)

```
---
NAME: accumulator_mode_new_syntax
INPUT:
1: * = $0200
2:   ASL
3:   LSR
4:   ROL
5:   ROR
EXPECT_HEX: 0a 4a 2a 6a

---
NAME: accumulator_mode_old_syntax
INPUT:
1: * = $0200
2:   ASL A
3:   LSR A
4:   ROL A
5:   ROR A
EXPECT_HEX: 0a 4a 2a 6a

---
NAME: implied_mode_still_works
INPUT:
1: * = $0200
2:   NOP
3:   RTS
EXPECT_HEX: ea 60
```

### Phase 3: Tests (add to asm19_tests.txt)

```
---
NAME: accumulator_mode_no_operand
INPUT:
1: * = $0200
2:   ASL
3:   LSR
4:   ROL
5:   ROR
EXPECT_HEX: 0a 4a 2a 6a

---
NAME: accumulator_old_syntax_now_label
INPUT:
1: * = $0200
2:   ASL A
EXPECT_ERROR: 1
EXPECT_LINE: 2
EXPECT_MSG: Label not found
```

---

## Files to Modify

### Phase 1
- [ ] tests/run_tests.sh - add arguments for test file and assembler
- [ ] asm18.asm - modify `.implied_mode` to use find_opcode_for_mode
- [ ] tests/asm18_tests.txt - add both syntax tests

### Phase 2
- [ ] Search all asm19 files for `ASL A`, `LSR A`, `ROL A`, `ROR A`
- [ ] Replace with new syntax
- [ ] Verify build succeeds

### Phase 3
- [ ] asm19.asm - remove "A" check in operand parsing
- [ ] tests/asm19_tests.txt - add new syntax test, add negative test for old syntax

---

## Estimated Time
- Phase 1: 45-60 minutes (test runner + implement + test)
- Phase 2: 15-20 minutes (search + replace + verify)
- Phase 3: 20-30 minutes (remove code + test)
- **Total: 1.5-2 hours**

---

## Benefits for Operand Consolidation

After this migration:
1. **No ambiguity** - operand is either present or not
2. **Simpler parsing** - no need to look ahead and check for "A"
3. **Standard syntax** - matches most other assemblers
4. **Easier `parse_value`** - only called when operand exists

The operand consolidation plan can proceed with cleaner logic:
- If operand exists → call `parse_value`
- If no operand → implied or accumulator (determined by instruction)
