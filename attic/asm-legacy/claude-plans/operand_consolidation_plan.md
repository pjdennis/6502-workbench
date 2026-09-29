# Plan: Consolidate Operand Value Parsing

## Status: COMPLETE

Successfully consolidated all operand value parsing into a single `parse_value` function.

**Commits:**
- eab0eb9: Add parse_value function
- 65562d6: Use parse_value for label-based addressing
- cae5890: Use parse_value for immediate mode
- 6658d50: Use parse_value for indirect modes
- a7a020a: Use parse_value for hex/lsb/msb operands
- 1d7136c: Add comprehensive forward reference tests (22 tests)

**Results:**
- Single unified function handles all value forms
- Code reduction: -75 lines (169 removed, 94 added)
- Test coverage: 59 → 81 tests (added 22 forward ref tests)
- All tests pass, self-hosting verified
- Forward reference logic preserved exactly

---

## Phase 1 Findings: Forward Reference Handling in asm19

**Line numbers current as of commit 59cfac4 (after accumulator syntax removal)**

### Current Forward Reference Mechanism

#### Key Functions

1. **`read_and_find_existing_label`** (line 277)
   - Used when parsing `<label` or `>label` (with operators)
   - If label not found in pass 1: sets HEX1=HEX2=$00, returns normally (no error)
   - If label not found in pass 2: jumps to err_label_not_found
   - **Does NOT set IS_FWDREF flag**

2. **`.is_label` section** (lines 1391-1425)
   - Used when parsing bare labels (no < or > prefix)
   - Reads token with `JSR read_token` (line 1393)
   - Looks up label via `check_local_label` + `select_label_hash_table` + `find_in_hash` (lines 1396-1398)
   - If not found in pass 1:
     - Sets IS_FWDREF = $FF (line 1405)
     - Sets HEX1=HEX2=$00 (lines 1407-1408)
   - If found:
     - Sets IS_FWDREF = $00 (line 1415)
   - Stores result in OPERAND_L/H (lines 1418-1421)
   - **This is the ONLY place IS_FWDREF is set**

3. **`handle_fwdref_mode`** (line 1533)
   - Called ONLY for ZP/ZPX/ZPY mode selection (lines 1447, 1467, 1487)
   - In pass 1 with forward ref: calls add_forward_ref, returns C=1 (use ABS)
   - In pass 2: calls check_forward_ref to see if PC is in list
   - Purpose: Forces absolute addressing for forward refs (can't know if <= $FF in pass 1)

#### Where Forward Reference Tracking Happens

**Forward refs are ONLY tracked for bare labels in ZP-capable contexts:**

- `label` (non-indexed) - around lines 1477-1495; calls handle_fwdref_mode at line 1487
  - If value <= $FF and ZP mode exists and not forward ref → use ZP
  - Otherwise → use ABS

- `label,X` (X-indexed) - around lines 1437-1455; calls handle_fwdref_mode at line 1447
  - If value <= $FF and ZPX mode exists and not forward ref → use ZPX
  - Otherwise → use ABSX

- `label,Y` (Y-indexed) - around lines 1457-1475; calls handle_fwdref_mode at line 1467
  - If value <= $FF and ZPY mode exists and not forward ref → use ABSY
  - Otherwise → use ABSY

**Forward refs are NOT tracked for:**
- `#<label`, `#>label` - immediate mode (lines 1067-1092)
- `<label`, `>label` - .data directive (lines 1567-1578)
- Any context where operators explicitly extract byte

#### Why Operators Bypass Tracking

When `<` or `>` is used:
1. Uses `read_and_find_existing_label` (not `.is_label`)
2. IS_FWDREF flag is never set
3. No call to `handle_fwdref_mode`
4. Result: Always uses the specified byte, no ZP/ABS optimization

This makes sense because:
- `#<label` - user explicitly requested low byte
- `#>label` - user explicitly requested high byte
- No ambiguity about addressing mode

### Implications for parse_value Function

#### Design Requirements

The `parse_value` function must distinguish between:

1. **Bare label** → needs forward ref tracking
   - Set IS_FWDREF flag based on lookup result
   - Return C=1 to signal "undecorated label"
   - Caller will call handle_fwdref_mode if doing ZP selection

2. **Operator-prefixed label** (`<label` or `>label`) → NO tracking
   - Use read_and_find_existing_label (current behavior)
   - Return C=0 to signal "decorated label"
   - Caller skips handle_fwdref_mode

3. **Hex value** (`$12` or `$1234`) → NO tracking
   - Use read_hex_byte_or_word
   - Return C=0
   - Caller skips handle_fwdref_mode

#### Proposed Interface

```asm
; Parse a value: $12, $1234, label, <label, or >label
; On entry: A contains first character
; On exit:  A contains next character
;           OPERAND_L, OPERAND_H contain parsed value
;           IS_FWDREF set if bare label was forward ref (pass 1 only)
;           C=1 if bare label, C=0 otherwise
;           X, Y preserved
```

The C flag tells caller whether to call `handle_fwdref_mode`.

---

## Phase 2: Implement `parse_value` and Refactor Incrementally (1.5-2 hours)

**Strategy:** Implement the function, then refactor one addressing mode at a time. Test and commit after each mode.

### Step 1: Implement `parse_value` function (30 min)

**Function Structure:**
```asm
parse_value
  ; On entry: A contains first character
  ; On exit:  A contains next character
  ;           OPERAND_L, OPERAND_H contain parsed value
  ;           IS_FWDREF set if bare label was forward ref (pass 1 only)
  ;           C=1 if bare label, C=0 otherwise
  ;           X, Y preserved

  CMP #'$'
  BEQ .hex
  CMP #'<'
  BEQ .low_byte
  CMP #'>'
  BEQ .high_byte
  ; Otherwise: bare label - needs forward ref tracking
  ; Reuse logic from .is_label (lines 1391-1425)
  ; Set IS_FWDREF based on lookup result
  ; Return C=1 (SEC before RTS)
  ...
.hex
  JSR read_char        ; Skip $
  JSR read_hex_byte_or_word  ; Returns next char in A
  BCC .one_byte
  ; Two bytes
  PHA                  ; Save next char
  LDA HEX2
  STA OPERAND_L
  LDA HEX1
  STA OPERAND_H
  PLA                  ; Restore next char
  CLC                  ; Signal not bare label
  RTS
.one_byte
  PHA                  ; Save next char
  LDA HEX1
  STA OPERAND_L
  LDA #$00
  STA OPERAND_H
  PLA                  ; Restore next char
  CLC                  ; Signal not bare label
  RTS
.low_byte
  JSR read_char        ; Skip <
  JSR read_and_find_existing_label  ; Returns next char in A
  PHA                  ; Save next char
  LDA HEX2             ; Low byte
  STA OPERAND_L
  LDA #$00
  STA OPERAND_H
  PLA                  ; Restore next char
  CLC                  ; Signal not bare label
  RTS
.high_byte
  JSR read_char        ; Skip >
  JSR read_and_find_existing_label  ; Returns next char in A
  PHA                  ; Save next char
  LDA HEX1             ; High byte
  STA OPERAND_L
  LDA #$00
  STA OPERAND_H
  PLA                  ; Restore next char
  CLC                  ; Signal not bare label
  RTS
```

**Testing:** Add basic test cases to verify function works in isolation (if possible) or with simplest addressing mode.

**Commit:** "Add parse_value function for operand consolidation"

### Step 2: Refactor Addressing Modes (1-1.5 hours)

Refactor one mode at a time. After each:
1. Run `./asmtestgen.sh` to verify build
2. Run `./tests/run_tests.sh` to verify tests
3. Commit with message: "Use parse_value for [mode] addressing"

**Order:**

1. **Absolute Mode** (non-indexed) - simplest case
   - Find current parsing code (around line 1477+)
   - Replace with `JSR parse_value`
   - Handle C flag: if C=1 and value <= $FF and ZP exists → call `handle_fwdref_mode`
   - Test and commit

2. **Immediate Mode** (except char literals)
   - Current code: lines 1040-1092
   - Replace hex and label parsing with `JSR parse_value`
   - Keep char literal handling as-is (lines 1093+)
   - C flag can be ignored (no ZP selection for immediate)
   - Test and commit

3. **Absolute Indexed** (,X and ,Y)
   - Current code: around lines 1437-1475
   - Replace value parsing with `JSR parse_value`
   - Handle C flag for ZPX/ZPY vs ABSX/ABSY selection
   - Test and commit (can be one commit for both X and Y, or separate)

4. **Indirect Modes** (($zp),Y and ($zp,X))
   - Replace value parsing with `JSR parse_value`
   - These always need ZP; emit will catch if value > $FF
   - Test and commit

5. **Branch/Relative Mode**
   - Currently uses `.is_label` directly
   - Can likely use `JSR parse_value` (C=1 expected)
   - Test and commit

6. **.data directive** (optional - might already work)
   - Currently has separate logic (lines 1552+)
   - Could potentially use `parse_value` for consistency
   - Test and commit if changed

---

## Phase 3: Cleanup (15 min)

- Remove dead code (old inline parsing logic that's been replaced)
- Update comments
- Final full build and test verification
- Update this plan to COMPLETE status
- Commit: "Cleanup after operand consolidation"

---

## Success Criteria
1. Single `parse_value` function handles all value parsing
2. Uniform syntax: `$12`, `$1234`, `label`, `<label`, `>label` work everywhere (context-appropriate)
3. Validation happens at emit time (not parse time)
4. Forward reference handling preserved exactly as before
5. All 59 tests pass
6. ~100-200 lines of duplicate code removed
7. 6-8 commits total (1 for parse_value, 1-6 for addressing modes, 1 for cleanup)

## Estimated Time: 2-2.5 hours

(Previous estimate was 3-4 hours. Based on accumulator syntax migration taking ~30% of estimated time, this might complete faster, but keeping conservative estimate since this is more complex.)
