# Replace Runtime Buffer Configuration with Compile-Time Conditional Assembly

> **Attic note:** historical. Paths (`22/`, `23/`, `editor/`, `assembler2/`) are from the old assembler2 layout; the live code is `asm/` (stages 00-17) and `editor/`. See `attic/assembler2/README.md`.


## Context

The editor currently uses a debug build with runtime command-line argument parsing (`bufsize:NN`) to override the buffer size for testing. This approach adds ~100 lines of argument parsing code that's only used in tests. By moving to compile-time conditional assembly at the constant definition level, we:

- Eliminate runtime argument parsing complexity
- Make buffer size configuration explicit at compile time
- Keep the bulk of code clean (no scattered conditionals)
- Maintain the same test coverage with simpler infrastructure

The assembler will support `.ifndef` and `.else` directives, enabling clean conditional constant definition.

## Implementation Plan

### 1. Conditional Buffer Size Definition

**File: `editor/buffer.asm` (lines 11-18)**

Add conditional compilation to define TEXT_LIMIT based on build type:

```asm
TEXT_BUF    = $2000  ; Start of text buffer

; Buffer size: normal build = 40KB, small build = 256 bytes
.ifndef small_buffer
TEXT_LIMIT  = $C000  ; End of text buffer space (40KB: $2000-$BFFF)
.else
TEXT_LIMIT  = $2100  ; End of text buffer space (256 bytes: $2000-$20FF)
.endif

LINE_TBL    = $C000  ; Line pointer table (2 bytes per entry)
```

**Rationale:**
- Normal build (default): 40KB buffer as before
- Small buffer build (`define:small_buffer`): 256-byte buffer ($2000-$20FF)
- This matches current `bufsize:21` behavior exactly
- Conditional is isolated at constant definition, keeping rest of code clean
- No special assumptions about low byte (works with any page-aligned limit)

### 2. Remove Debug Argument Parsing

**File: `editor/editor.asm`**

Remove two sections:

**A. Remove parse_debug_args call (lines 84-87):**
```asm
  .ifdef enable_debug
  ; Parse additional arguments (debug build only)
  JSR parse_debug_args
  .endif
```

**B. Remove entire debug section (lines 214-313):**
- Zero-page variables (DBG_ARG_IDX, DBG_ARG_COUNT)
- `parse_debug_args` function (~70 lines)
- `parse_hex_digit` helper function
- Entire `.ifdef enable_debug` block

**Result:** Eliminates ~100 lines of runtime argument parsing code that's only used for testing.

### 3. Update Test Infrastructure

**File: `tests/editor_tests.py`**

**A. Update binary path (line 48):**
```python
# Old:
self.editor_debug_bin = base_dir / "editor" / "out" / "editor_debug.out"

# New:
self.editor_small_bin = base_dir / "editor" / "out" / "editor_small.out"
```

**B. Rename build function (lines 77-80):**
```python
def build_small_buffer_editor(self):
    """Assemble the editor with small buffer (256 bytes for testing)."""
    return self._assemble_editor(self.editor_small_bin,
                                 ["define:small_buffer"])
```

**C. Simplify test execution (lines 239-264):**

Rename `run_editor_debug` → `run_editor_small_buffer` and remove `extra_args` parameter:
```python
def run_editor_small_buffer(self, input_file: str, keys: bytes,
                            tmpdir: Path) -> tuple:
    """Run the small buffer editor with given keystroke sequence."""
    # ... same implementation but use self.editor_small_bin
    # Remove: if extra_args: cmd.extend(extra_args)
```

**D. Simplify test wrapper (lines 491-533):**

Rename `run_test_debug` → `run_test_small_buffer` and remove `extra_args` parameter:
```python
def run_test_small_buffer(self, name: str, initial_content: str, keys: bytes,
                          expected_content: str = None, expect_exit: int = 0,
                          expect_unmodified: bool = False):
    """Run a test using the small buffer editor (256 bytes)."""
    # ... call run_editor_small_buffer (no extra_args)
```

**E. Update build check (line 923):**
```python
if not self.build_small_buffer_editor():
    print("  Skipping bounds checking tests (small buffer build failed)")
```

**F. Update all 11 test cases (lines 932-1047):**

Remove `extra_args=["bufsize:21"]` from each test call:
```python
# Old pattern:
self.run_test_debug(
    "Test name",
    content,
    keys,
    extra_args=["bufsize:21"],
    expected_content=...
)

# New pattern:
self.run_test_small_buffer(
    "Test name",
    content,
    keys,
    expected_content=...
)
```

### 4. Update Documentation

**File: `editor/README.md`**

**Lines 38-39** - Buffer limits description:
```markdown
- **Buffer limits**: `TEXT_LIMIT` is conditionally defined at compile-time:
  - Normal build: `$C000` (40KB buffer: $2000-$BFFF)
  - Small buffer build (`define:small_buffer`): `$2100` (256 bytes: $2000-$20FF, used for testing)
```

**Lines 59-60** - Testing description:
```markdown
- Bounds checking tests build `editor_small.out` with `define:small_buffer`
  to create a 256-byte buffer, forcing truncation/read-only scenarios.
```

**Lines 74-76** - Build commands:
```markdown
- Assemble (release): `./emulator.out 23/out/asm.out editor/editor.asm editor/out/editor.out`
- Assemble (small buffer): `./emulator.out 23/out/asm.out editor/editor.asm editor/out/editor_small.out define:small_buffer`
- Run (console): `./emulator.out editor/out/editor.out --load 0400 --console <file>`
```

## Critical Files

- `editor/buffer.asm` - Add conditional TEXT_LIMIT definition
- `editor/editor.asm` - Remove ~100 lines of debug argument parsing
- `tests/editor_tests.py` - Rename debug→small_buffer, remove extra_args handling
- `editor/README.md` - Update documentation

## Verification

### Build Verification
1. **Normal build**: `./emulator.out 23/out/asm.out editor/editor.asm editor/out/editor.out`
   - Should assemble successfully
   - Should handle large files (40KB buffer)

2. **Small buffer build**: `./emulator.out 23/out/asm.out editor/editor.asm editor/out/editor_small.out define:small_buffer`
   - Should assemble successfully
   - Should truncate files >256 bytes

### Test Verification
```bash
./tests/editor_tests.py
```

Expected results:
- All existing tests pass
- All 11 bounds checking tests pass (now using compile-time small buffer)
- Tests should be cleaner (no runtime arguments needed)

### Functional Verification
1. **Normal editor**: Load and edit a 10KB file successfully
2. **Small buffer editor**: Verify 300-byte file gets truncated and enters read-only mode
3. **Code size**: Small buffer build should be ~100 bytes smaller than old debug build

## Benefits

1. **Code simplicity**: Removes ~100 lines of argument parsing
2. **Clean architecture**: Conditional at constant level, not scattered in code
3. **Type safety**: Compile-time constants vs runtime configuration
4. **Test clarity**: Build flag instead of runtime arguments
5. **Maintainability**: Easier to understand buffer size configuration
