#!/usr/bin/env python3
"""
Tests for test_runner directory scanning mode.

When the test runner is invoked with no arguments (argc == 0),
it should use opendir(".") to discover .txt test files in the
current directory and run them all.

Usage:
    python3 17/tests/test_runner/test_runner_dir.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path


# Paths relative to project root
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
EMULATOR = PROJECT_ROOT.parent / "emulator" / "emulator.out"
TEST_RUNNER = PROJECT_ROOT / "17" / "out" / "test_runner.out"


class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    NC = "\033[0m"


def run_test_runner(cwd, args=None, timeout=30):
    """Run the test runner in the given directory.

    Args:
        cwd: Working directory for the test runner
        args: Optional list of arguments (test filenames)
        timeout: Timeout in seconds

    Returns:
        (stderr_output, exit_code) - test runner output goes to stderr
    """
    cmd = [str(EMULATOR), str(TEST_RUNNER), "--no-dump"]
    if args:
        cmd.extend(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        timeout=timeout,
        cwd=cwd,
    )
    # Test runner output goes to stderr (via write_d / show_message)
    output = result.stderr.decode("utf-8", errors="replace")
    return output, result.returncode


# A minimal passing test file
SIMPLE_PASS_TEST = """\
---
NAME: simple_nop
INPUT:
 1: * = $0200
 2:   NOP
EXPECT_HEX: ea
---
"""

# A test file with two tests
TWO_TESTS = """\
---
NAME: test_nop
INPUT:
 1: * = $0200
 2:   NOP
EXPECT_HEX: ea
---
NAME: test_lda_imm
INPUT:
 1: * = $0200
 2:   LDA #$42
EXPECT_HEX: a9 42
---
"""


def test_single_txt_file_in_directory():
    """When argc==0 and directory has one .txt file, it should run it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "tests.txt").write_text(SIMPLE_PASS_TEST)
        output, rc = run_test_runner(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}\nOutput: {output}"
        assert "Running tests from tests.txt" in output, f"Missing header in: {output}"
        assert "simple_nop" in output, f"Missing test name in: {output}"
        assert "1 passed" in output, f"Missing pass count in: {output}"


def test_multiple_txt_files():
    """Multiple .txt files should all be processed in alphabetical order."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "02-second.txt").write_text(SIMPLE_PASS_TEST.replace(
            "simple_nop", "second_test"))
        Path(tmpdir, "01-first.txt").write_text(SIMPLE_PASS_TEST.replace(
            "simple_nop", "first_test"))
        output, rc = run_test_runner(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}\nOutput: {output}"
        # Check alphabetical order
        first_pos = output.index("01-first.txt")
        second_pos = output.index("02-second.txt")
        assert first_pos < second_pos, \
            f"Files not in alphabetical order:\n{output}"
        assert "2 passed" in output, f"Expected 2 passed in: {output}"


def test_non_txt_files_ignored():
    """Non-.txt files should be ignored."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(SIMPLE_PASS_TEST)
        Path(tmpdir, "readme.md").write_text("# Not a test")
        Path(tmpdir, "code.asm").write_text("NOP")
        Path(tmpdir, "data.bin").write_bytes(b"\x00\x01")
        output, rc = run_test_runner(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}\nOutput: {output}"
        assert "readme.md" not in output, f"Non-txt file processed: {output}"
        assert "code.asm" not in output, f"Non-txt file processed: {output}"
        assert "data.bin" not in output, f"Non-txt file processed: {output}"
        assert "1 passed" in output, f"Expected 1 passed in: {output}"


def test_directories_ignored():
    """Subdirectories should be ignored even if named .txt."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(SIMPLE_PASS_TEST)
        Path(tmpdir, "subdir.txt").mkdir()
        Path(tmpdir, "another_dir").mkdir()
        output, rc = run_test_runner(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}\nOutput: {output}"
        assert "subdir.txt" not in output, f"Directory was processed: {output}"
        assert "1 passed" in output, f"Expected 1 passed in: {output}"


def test_single_file_mode_still_works():
    """When a filename is passed as argument, use it directly (regression)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "mytest.txt").write_text(SIMPLE_PASS_TEST)
        output, rc = run_test_runner(tmpdir, args=["mytest.txt"])
        assert rc == 0, f"Expected exit code 0, got {rc}\nOutput: {output}"
        assert "Running tests from mytest.txt" in output, \
            f"Missing header in: {output}"
        assert "1 passed" in output, f"Expected 1 passed in: {output}"


def test_empty_directory():
    """Empty directory (no .txt files) should produce summary with all zeros."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output, rc = run_test_runner(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}\nOutput: {output}"
        assert "0 passed" in output, f"Expected 0 passed in: {output}"


def test_cumulative_counts_across_files():
    """Pass/fail/skip counts should accumulate across multiple files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "01-file.txt").write_text(TWO_TESTS)
        Path(tmpdir, "02-file.txt").write_text(SIMPLE_PASS_TEST)
        output, rc = run_test_runner(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}\nOutput: {output}"
        assert "3 passed" in output, f"Expected 3 passed in: {output}"


def test_long_input_lines():
    """INPUT lines longer than 255 chars should be streamed correctly."""
    # Make the line long via a long macro name (not a long arg list);
    # MACRO_MAX_ARGS = 32 caps the param count regardless of name length,
    # so we use a long name (100 chars) plus 32 params to push the
    # .macro line past 255 chars.
    long_name = "M" + "A" * 99
    params = ", ".join(f"a{i:02d}" for i in range(32))
    args = ", ".join(f"${i:02X}" for i in range(32))
    long_test = f"""\
---
NAME: long_input_line
INPUT:
 1: * = $0200
 2:   .macro {long_name} {params}
 3:   LDA #a00
 4:   .endmacro
 5:   {long_name} {args}
EXPECT_HEX: a9 00
---
"""
    # Verify the test file actually has lines >255 chars
    max_line = max(len(line) for line in long_test.splitlines())
    assert max_line > 255, f"Test setup error: max line is only {max_line} chars"

    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(long_test)
        output, rc = run_test_runner(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}\nOutput: {output}"
        assert "1 passed" in output, f"Expected 1 passed in: {output}"
        assert "LIMIT" not in output, f"Unexpected LIMIT in: {output}"


# A test with intentional byte mismatch (expect a9 42, input produces a9 43)
BYTE_MISMATCH_TEST = """\
---
NAME: byte_mismatch
INPUT:
 1: * = $0200
 2:   LDA #$43
EXPECT_HEX: a9 42
---
"""

# A test with length mismatch (expect 3 bytes, input produces 2)
LENGTH_MISMATCH_TEST = """\
---
NAME: length_mismatch
INPUT:
 1: * = $0200
 2:   LDA #$42
EXPECT_HEX: a9 42 ea
---
"""


def test_byte_mismatch_shows_hex_dumps():
    """On byte mismatch, failure output should include exp: and got: hex dumps."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(BYTE_MISMATCH_TEST)
        output, rc = run_test_runner(tmpdir)
        assert rc == 1, f"Expected exit code 1, got {rc}\nOutput: {output}"
        assert "FAIL" in output, f"Missing FAIL in: {output}"
        assert "exp: a9 42" in output, f"Missing exp hex dump in: {output}"
        assert "got: a9 43" in output, f"Missing got hex dump in: {output}"


def test_length_mismatch_shows_hex_dumps():
    """On length mismatch, failure output should include exp: and got: hex dumps."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(LENGTH_MISMATCH_TEST)
        output, rc = run_test_runner(tmpdir)
        assert rc == 1, f"Expected exit code 1, got {rc}\nOutput: {output}"
        assert "FAIL" in output, f"Missing FAIL in: {output}"
        assert "exp: a9 42 ea" in output, f"Missing exp hex dump in: {output}"
        assert "got: a9 42" in output, f"Missing got hex dump in: {output}"


# A test with wrong expected error message
WRONG_MSG_TEST = """\
---
NAME: wrong_msg
INPUT:
 1: * = $0200
 2:   LDA bogus
EXPECT_ERROR: 1
EXPECT_MSG: Wrong message text
---
"""


def test_wrong_msg_shows_actual():
    """On message mismatch, failure should show both expected and actual messages."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(WRONG_MSG_TEST)
        output, rc = run_test_runner(tmpdir)
        assert rc == 1, f"Expected exit code 1, got {rc}\nOutput: {output}"
        assert "FAIL" in output, f"Missing FAIL in: {output}"
        assert 'exp: "Wrong message text"' in output, \
            f"Missing expected msg in: {output}"
        assert 'got: "Label not found"' in output, \
            f"Missing actual msg in: {output}"


# A test that triggers an assembler error (for stderr suppression tests)
ERROR_TEST = """\
---
NAME: error_test
INPUT:
 1: * = $0200
 2:   LDA bogus
EXPECT_ERROR: 1
---
"""


def test_stderr_suppressed_by_default():
    """Assembler stderr (Error messages) should NOT appear in test runner output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(ERROR_TEST)
        output, rc = run_test_runner(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}\nOutput: {output}"
        assert "1 passed" in output, f"Expected 1 passed in: {output}"
        # The assembler's "Error 1 in file..." should NOT appear in output
        error_lines = [l for l in output.splitlines() if l.strip().startswith("Error ")]
        assert len(error_lines) == 0, \
            f"Assembler stderr should be suppressed, but found: {error_lines}"


# A test with wrong expected line number
WRONG_LINE_TEST = """\
---
NAME: wrong_line
INPUT:
 1: * = $0200
 2:   LDA bogus
EXPECT_ERROR: 1
EXPECT_LINE: 99
---
"""


def test_wrong_line_aligned_display():
    """On line mismatch, failure should show exp:/got: on separate lines."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(WRONG_LINE_TEST)
        output, rc = run_test_runner(tmpdir)
        assert rc == 1, f"Expected exit code 1, got {rc}\nOutput: {output}"
        assert "FAIL" in output, f"Missing FAIL in: {output}"
        assert "exp: line " in output, \
            f"Missing 'exp: line' in: {output}"
        assert "got: line " in output, \
            f"Missing 'got: line' in: {output}"


# A test with wrong expected error code
WRONG_CODE_TEST = """\
---
NAME: wrong_code
INPUT:
 1: * = $0200
 2:   LDA bogus
EXPECT_ERROR: 5
---
"""


def test_wrong_code_aligned_display():
    """On error code mismatch, failure should show exp:/got: on separate lines."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(WRONG_CODE_TEST)
        output, rc = run_test_runner(tmpdir)
        assert rc == 1, f"Expected exit code 1, got {rc}\nOutput: {output}"
        assert "FAIL" in output, f"Missing FAIL in: {output}"
        assert "exp: error " in output, \
            f"Missing 'exp: error' in: {output}"
        assert "got: error " in output, \
            f"Missing 'got: error' in: {output}"


# A simple EXPECT_STDERR test (file not found gives predictable stderr)
EXPECT_STDERR_TEST = """\
---
NAME: stderr_simple
INPUT:
 1: * = $0200
 2:   .include nonexistent_file_12345.asm
EXPECT_STDERR:
Error 39 in file _tr_in.tmp at line 2: File not found
---
"""


def test_expect_stderr_not_skipped():
    """Tests with simple EXPECT_STDERR should PASS, not SKIP."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(EXPECT_STDERR_TEST)
        output, rc = run_test_runner(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}\nOutput: {output}"
        assert "SKIP" not in output, f"Unexpected SKIP in: {output}"
        assert "1 passed" in output, f"Expected 1 passed in: {output}"


# A test with mismatched EXPECT_STDERR
EXPECT_STDERR_MISMATCH_TEST = """\
---
NAME: stderr_mismatch
INPUT:
 1: * = $0200
 2:   .include nonexistent_file_12345.asm
EXPECT_STDERR:
Error 99 in file wrong.asm at line 1: Wrong message
---
"""


def test_expect_stderr_mismatch_display():
    """On EXPECT_STDERR mismatch, failure should show exp: and got: content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(EXPECT_STDERR_MISMATCH_TEST)
        output, rc = run_test_runner(tmpdir)
        assert rc == 1, f"Expected exit code 1, got {rc}\nOutput: {output}"
        assert "FAIL" in output, f"Missing FAIL in: {output}"
        assert "exp: Error 99" in output, \
            f"Missing expected stderr in: {output}"
        assert "got: Error 39" in output, \
            f"Missing actual stderr in: {output}"


# A test with {{MAIN_FILE}} in EXPECT_STDERR
EXPECT_STDERR_MAIN_FILE_TEST = """\
---
NAME: stderr_main_file
INPUT:
 1: * = $0200
 2:   .include nonexistent_file_12345.asm
EXPECT_STDERR:
Error 39 in file {{MAIN_FILE}} at line 2: File not found
---
"""


def test_expect_stderr_main_file_placeholder():
    """{{MAIN_FILE}} in EXPECT_STDERR should be substituted with _tr_in.tmp."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(EXPECT_STDERR_MAIN_FILE_TEST)
        output, rc = run_test_runner(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}\nOutput: {output}"
        assert "SKIP" not in output, f"Unexpected SKIP in: {output}"
        assert "1 passed" in output, f"Expected 1 passed in: {output}"


# A test with bracketed INPUT (preserving whitespace)
BRACKETED_INPUT_TEST = """\
---
NAME: bracketed_input
INPUT:
 1: [* = $0200]
 2: [  .byte $41]
EXPECT_HEX: 41
---
"""


def test_bracketed_input():
    """INPUT lines with [content] brackets should preserve inner whitespace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(BRACKETED_INPUT_TEST)
        output, rc = run_test_runner(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}\nOutput: {output}"
        assert "1 passed" in output, f"Expected 1 passed in: {output}"


# A test with bracketed EXPECT_STDERR (preserving leading whitespace)
BRACKETED_STDERR_TEST = """\
---
NAME: bracketed_stderr
INPUT:
 1: * = $0200
 2:   .include nonexistent_file_12345.asm
EXPECT_STDERR:
[Error 39 in file _tr_in.tmp at line 2: File not found]
---
"""


def test_bracketed_stderr():
    """EXPECT_STDERR lines with [content] brackets should preserve whitespace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(BRACKETED_STDERR_TEST)
        output, rc = run_test_runner(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}\nOutput: {output}"
        assert "SKIP" not in output, f"Unexpected SKIP in: {output}"
        assert "1 passed" in output, f"Expected 1 passed in: {output}"


# A test with ARGS: debug
DEBUG_ARG_TEST = """\
---
NAME: debug_arg_test
ARGS: debug
INPUT:
 1: * = $0200
 2:   NOP
EXPECT_HEX: ea
---
"""


def test_debug_args_not_skipped():
    """Tests with ARGS: debug should PASS, not SKIP."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(DEBUG_ARG_TEST)
        output, rc = run_test_runner(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}\nOutput: {output}"
        assert "SKIP" not in output, f"Unexpected SKIP in: {output}"
        assert "1 passed" in output, f"Expected 1 passed in: {output}"


def test_verbose_flag_shows_stderr():
    """With -v flag, assembler stderr (Error messages) should appear in output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(ERROR_TEST)
        output, rc = run_test_runner(tmpdir, args=["-v", "test.txt"])
        assert rc == 0, f"Expected exit code 0, got {rc}\nOutput: {output}"
        assert "1 passed" in output, f"Expected 1 passed in: {output}"
        # With -v, the assembler's "Error" message should appear
        assert "Error " in output, \
            f"With -v, assembler stderr should appear in: {output}"


def test_quiet_flag_suppresses_pass():
    """With -q flag, passing test names should not appear in output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(SIMPLE_PASS_TEST)
        output, rc = run_test_runner(tmpdir, args=["-q", "test.txt"])
        assert rc == 0, f"Expected exit code 0, got {rc}\nOutput: {output}"
        assert "1 passed" in output, f"Expected summary in: {output}"
        assert "simple_nop" not in output, \
            f"Passing test name should be suppressed with -q: {output}"
        assert "Running tests from test.txt" in output, \
            f"File header should still appear with -q: {output}"


def test_quiet_flag_shows_failures():
    """With -q flag, failing tests should still appear in output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(BYTE_MISMATCH_TEST)
        output, rc = run_test_runner(tmpdir, args=["-q", "test.txt"])
        assert rc == 1, f"Expected exit code 1, got {rc}\nOutput: {output}"
        assert "byte_mismatch" in output, \
            f"Failing test should appear with -q: {output}"
        assert "FAIL" in output, f"Missing FAIL in: {output}"


def test_summary_fail_emphasis():
    """When tests fail, summary should use !!failed!! instead of failed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(BYTE_MISMATCH_TEST)
        output, rc = run_test_runner(tmpdir)
        assert rc == 1, f"Expected exit code 1, got {rc}\nOutput: {output}"
        assert "!!failed!!" in output, \
            f"Summary should use !!failed!! on failure: {output}"


def test_summary_no_emphasis_on_pass():
    """When all tests pass, summary should use plain 'failed' (no emphasis)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(SIMPLE_PASS_TEST)
        output, rc = run_test_runner(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}\nOutput: {output}"
        assert " failed," in output, f"Expected 'failed,' in: {output}"
        assert "!!failed!!" not in output, \
            f"Summary should NOT use !!failed!! when all pass: {output}"


# A single test file exercising every field type
ALL_FIELD_TYPES_TEST = """\
---
NAME: all_fields_hex
INPUT:
 1: * = $0200
 2:   NOP
EXPECT_HEX: ea
---
NAME: all_fields_error
INPUT:
 1: * = $0200
 2:   LDA bogus
EXPECT_ERROR: 1
EXPECT_LINE: 2
EXPECT_MSG: Label not found
---
NAME: all_fields_skip
SKIP:
INPUT:
 1: * = $0200
 2:   NOP
EXPECT_HEX: ea
---
NAME: all_fields_args
ARGS: define:MY_FLAG
INPUT:
 1: * = $0200
 2:   .ifdef MY_FLAG
 3:   NOP
 4:   .endif
EXPECT_HEX: ea
---
NAME: all_fields_stderr
INPUT:
 1: * = $0200
 2:   .include nonexistent_file_12345.asm
EXPECT_STDERR:
Error 39 in file {{MAIN_FILE}} at line 2: File not found
---
"""


def test_all_field_types_dispatched():
    """All field types (NAME, INPUT, EXPECT_HEX, EXPECT_ERROR, EXPECT_LINE,
    EXPECT_MSG, SKIP, ARGS, EXPECT_STDERR) dispatch correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(ALL_FIELD_TYPES_TEST)
        output, rc = run_test_runner(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}\nOutput: {output}"
        assert "all_fields_hex" in output, f"Missing hex test in: {output}"
        assert "all_fields_error" in output, f"Missing error test in: {output}"
        assert "all_fields_skip" in output, f"Missing skip test in: {output}"
        assert "all_fields_args" in output, f"Missing args test in: {output}"
        assert "all_fields_stderr" in output, f"Missing stderr test in: {output}"
        assert "4 passed" in output, f"Expected 4 passed in: {output}"
        assert "1 skipped" in output, f"Expected 1 skipped in: {output}"


# Two tests in one file: first triggers error, second is a normal hex pass
ERROR_THEN_PASS_TEST = """\
---
NAME: first_error_test
INPUT:
 1: * = $0200
 2:   LDA bogus
EXPECT_ERROR: 1
---
NAME: second_pass_test
INPUT:
 1: * = $0200
 2:   NOP
EXPECT_HEX: ea
---
"""


def test_error_then_pass_in_one_file():
    """Error test followed by hex test in same file: vectors must restore."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(ERROR_THEN_PASS_TEST)
        output, rc = run_test_runner(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}\nOutput: {output}"
        assert "first_error_test" in output, f"Missing error test in: {output}"
        assert "second_pass_test" in output, f"Missing pass test in: {output}"
        assert "2 passed" in output, f"Expected 2 passed in: {output}"


# A test with multiline stderr mismatch (both expected and actual have 2 lines)
MULTILINE_STDERR_MISMATCH_TEST = """\
---
NAME: multiline_stderr_mismatch
INPUT:
 1: * = $0200
 2:   .include nonexistent_file_12345.asm
EXPECT_STDERR:
Wrong first line
Wrong second line
---
"""


def test_multiline_stderr_continuation():
    """Multiline stderr mismatch should show continuation indent in both sections."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(MULTILINE_STDERR_MISMATCH_TEST)
        output, rc = run_test_runner(tmpdir)
        assert rc == 1, f"Expected exit code 1, got {rc}\nOutput: {output}"
        assert "FAIL" in output, f"Missing FAIL in: {output}"
        # Expected stderr has two lines with continuation indent
        assert "exp: Wrong first line" in output, \
            f"Missing expected first line in: {output}"
        assert "         Wrong second line" in output, \
            f"Missing continuation indent for expected in: {output}"


# Test that "at line N" is found even when "at" appears earlier in the message.
# Error 39 "File not found" at line 2 — the stderr is:
# "Error 39 in file _tr_in.tmp at line 2: File not found"
# The word "at" appears in "at line 2" (which is what we look for).
# Using a filename that contains "at" to test: "catering.asm"
LINE_NUMBER_AFTER_AT_TEST = """\
---
NAME: line_number_after_at
INPUT:
 1: * = $0200
 2:   .include catering.asm
EXPECT_ERROR: 39
EXPECT_LINE: 2
---
"""


def test_line_number_after_at_in_message():
    """Line number extraction works even when 'at' appears before 'at line N'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(LINE_NUMBER_AFTER_AT_TEST)
        output, rc = run_test_runner(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}\nOutput: {output}"
        assert "1 passed" in output, f"Expected 1 passed in: {output}"


def test_unknown_flag_ignored():
    """An unknown flag like -x should be silently ignored; tests still run."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").write_text(SIMPLE_PASS_TEST)
        output, rc = run_test_runner(tmpdir, args=["-x", "test.txt"])
        assert rc == 0, f"Expected exit code 0, got {rc}\nOutput: {output}"
        assert "1 passed" in output, f"Expected 1 passed in: {output}"


def main():
    quiet = "-q" in sys.argv or "--quiet" in sys.argv

    if not EMULATOR.exists():
        print(f"Error: Emulator not found at {EMULATOR}")
        sys.exit(1)
    if not TEST_RUNNER.exists():
        print(f"Error: Test runner not found at {TEST_RUNNER}")
        sys.exit(1)

    print("Running test_runner directory mode tests")

    tests = [
        ("single_txt_file_in_directory", test_single_txt_file_in_directory),
        ("multiple_txt_files", test_multiple_txt_files),
        ("non_txt_files_ignored", test_non_txt_files_ignored),
        ("directories_ignored", test_directories_ignored),
        ("single_file_mode_still_works", test_single_file_mode_still_works),
        ("empty_directory", test_empty_directory),
        ("cumulative_counts_across_files", test_cumulative_counts_across_files),
        ("long_input_lines", test_long_input_lines),
        ("byte_mismatch_shows_hex_dumps", test_byte_mismatch_shows_hex_dumps),
        ("length_mismatch_shows_hex_dumps", test_length_mismatch_shows_hex_dumps),
        ("wrong_msg_shows_actual", test_wrong_msg_shows_actual),
        ("stderr_suppressed_by_default", test_stderr_suppressed_by_default),
        ("verbose_flag_shows_stderr", test_verbose_flag_shows_stderr),
        ("wrong_line_aligned_display", test_wrong_line_aligned_display),
        ("wrong_code_aligned_display", test_wrong_code_aligned_display),
        ("expect_stderr_not_skipped", test_expect_stderr_not_skipped),
        ("expect_stderr_mismatch_display", test_expect_stderr_mismatch_display),
        ("expect_stderr_main_file_placeholder", test_expect_stderr_main_file_placeholder),
        ("bracketed_input", test_bracketed_input),
        ("bracketed_stderr", test_bracketed_stderr),
        ("debug_args_not_skipped", test_debug_args_not_skipped),
        ("quiet_flag_suppresses_pass", test_quiet_flag_suppresses_pass),
        ("quiet_flag_shows_failures", test_quiet_flag_shows_failures),
        ("summary_fail_emphasis", test_summary_fail_emphasis),
        ("summary_no_emphasis_on_pass", test_summary_no_emphasis_on_pass),
        ("all_field_types_dispatched", test_all_field_types_dispatched),
        ("unknown_flag_ignored", test_unknown_flag_ignored),
        ("error_then_pass_in_one_file", test_error_then_pass_in_one_file),
        ("multiline_stderr_continuation", test_multiline_stderr_continuation),
        ("line_number_after_at_in_message", test_line_number_after_at_in_message),
    ]

    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            test_fn()
            if not quiet:
                print(f"  {Colors.GREEN}PASS{Colors.NC} {name}")
            passed += 1
        except Exception as e:
            print(f"  {Colors.RED}FAIL{Colors.NC} {name}: {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
