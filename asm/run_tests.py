#!/usr/bin/env python3
"""
Unified test runner for 6502 assembler project.

Supports two test types:
  - assembler: Tests the current assembler with assembly source input
  - source_stack: Tests the source stack component with file I/O operations

Usage:
    ./run_tests.py [options] [test_file...]

Options:
    -f, --filter PATTERN   Only run tests matching PATTERN
    -v, --verbose          Show detailed output for passing tests
    -h, --help             Show this help message

If no test files specified, runs the default test suites.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "emulator"))
from persistent_emulator import PersistentEmulator


ASM_VERSION = "17"

# Test-run input/output filenames passed as argv to the assembler.
# These match the self-hosted test runner's TR_INPUT_FILE / TR_OUTPUT_FILE
# (test_runner.asm:91-92) so the assembler sees identical paths under
# both harnesses -- frame_size and traceback output stay deterministic
# across machines, OS tempdir conventions, and checkout depth.
TR_INPUT_FILE = "_tr_in.tmp"
TR_OUTPUT_FILE = "_tr_out.tmp"
TR_ERR_FILE = "_tr_err.tmp"


class TestType(Enum):
    ASSEMBLER = "assembler"
    SOURCE_STACK = "source_stack"


class TestResult(Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


# ANSI colors
class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    NC = "\033[0m"  # No Color

    @classmethod
    def disable(cls):
        cls.RED = cls.GREEN = cls.YELLOW = cls.NC = ""


@dataclass
class Test:
    name: str = ""
    description: str = ""
    test_type: Optional[TestType] = None
    mode: str = ""  # For source_stack tests
    input_text: str = ""  # For assembler tests (INPUT field)
    input_text_bracketed: bool = False  # True if [line] format was used for INPUT
    files: dict = field(default_factory=dict)  # For source_stack tests
    main_file: str = ""  # First file defined
    expect_hex: str = ""
    expect_fwdref: str = ""
    expect_stdout: str = ""
    expect_stderr: str = ""
    expect_stderr_bracketed: bool = False  # True if [line] format was used
    expect_error: str = ""
    expect_line: str = ""
    expect_msg: str = ""
    args: str = ""
    skip: str = ""
    missing_input: bool = False


@dataclass
class TestOutcome:
    result: TestResult
    details: list = field(default_factory=list)


class TestRunner:
    def __init__(self, base_dir: Path, verbose: bool = False, quiet: bool = False,
                 asm_version: str = ASM_VERSION, python_mode: bool = False,
                 use_server: bool = True):
        self.base_dir = base_dir
        self.verbose = verbose
        self.quiet = quiet
        self.python_mode = python_mode
        self.use_server = use_server and not python_mode and int(asm_version) >= 9
        self.asm_version = asm_version
        self.emulator = base_dir.parents[1] / "emulator" / "emulator.out"
        self.assembler = self._resolve_assembler_binary(base_dir, asm_version)
        self.source_stack_test = base_dir / asm_version / "out" / "source_stack_test.out"
        self.python_asm = base_dir / "pyasm.py"

        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.current_test_file = None  # Track current test file for relative includes

        if self.use_server:
            self.emu = PersistentEmulator(self.emulator)
            self._tmpdir_obj = tempfile.TemporaryDirectory(prefix='asm_tests_')
            self.shared_tmpdir = Path(self._tmpdir_obj.name)
        else:
            self.emu = None
            self.shared_tmpdir = None

    @staticmethod
    def _resolve_assembler_binary(base_dir: Path, asm_version: str) -> Path:
        """Determine the correct assembler binary for a given version."""
        version = int(asm_version)
        if version <= 5:
            return base_dir / asm_version / "out" / "asm.out"
        elif version <= 8:
            return base_dir / asm_version / "out" / "asmc.out"
        elif version <= 14:
            return base_dir / asm_version / "out" / "asm.out"
        else:  # v15+
            return base_dir / asm_version / "out" / "asm_debug.out"

    def _read_text_safe(self, filepath: Path) -> str:
        """Read a file, converting non-UTF8 bytes to [0xNN] format."""
        data = filepath.read_bytes()
        result = []
        for byte in data:
            if byte == 0x0A:  # newline
                result.append('\n')
            elif byte == 0x0D:  # carriage return
                result.append('\r')
            elif byte == 0x09:  # tab
                result.append('\t')
            elif 0x20 <= byte <= 0x7E:  # printable ASCII
                result.append(chr(byte))
            else:
                result.append(f'[0x{byte:02X}]')
        return ''.join(result)

    def check_prerequisites(self, test_type: TestType) -> bool:
        """Check that required executables exist."""
        if self.python_mode:
            if test_type == TestType.ASSEMBLER:
                if not self.python_asm.exists():
                    print(f"Error: Python assembler not found at {self.python_asm}")
                    return False
                return True
            elif test_type == TestType.SOURCE_STACK:
                return True  # Will be skipped
            return True

        if not self.emulator.exists():
            print(f"Error: Emulator not found at {self.emulator}")
            print("Run the build first")
            return False

        if test_type == TestType.ASSEMBLER:
            if not self.assembler.exists():
                print(f"Error: Assembler not found at {self.assembler}")
                print("Run the build first")
                return False
        elif test_type == TestType.SOURCE_STACK:
            if not self.source_stack_test.exists():
                print(f"Error: File stack test program not found at {self.source_stack_test}")
                print("Run the build first")
                return False

        return True

    def parse_test_file(self, filepath: Path) -> list[Test]:
        """Parse a test file and return list of Test objects."""
        tests = []
        current = Test()
        section = ""  # Current multi-line section: 'input', 'file', 'stdout', 'stderr'
        section_name = ""  # For FILE sections, the filename

        with open(filepath) as f:
            for line in f:
                line = line.rstrip("\n")

                # Skip comments and blank lines outside sections
                if section == "":
                    if re.match(r"^\s*#", line) or re.match(r"^\s*$", line):
                        continue

                # Test separator
                if line == "---":
                    if current.name:
                        self._finalize_test(current)
                        tests.append(current)
                    current = Test()
                    section = ""
                    continue

                # Parse fields
                if m := re.match(r"^NAME:\s*(.*)", line):
                    current.name = m.group(1)
                    section = ""
                elif m := re.match(r"^DESCRIPTION:\s*(.*)", line):
                    current.description = m.group(1)
                    section = ""
                elif m := re.match(r"^TYPE:\s*(.*)", line):
                    current.test_type = TestType(m.group(1))
                    section = ""
                elif m := re.match(r"^MODE:\s*(.*)", line):
                    current.mode = m.group(1)
                    section = ""
                elif re.match(r"^INPUT:", line):
                    section = "input"
                    current.input_text = ""
                elif m := re.match(r"^FILE\s+(\S+):", line):
                    section = "file"
                    section_name = m.group(1)
                    current.files[section_name] = ""
                    if not current.main_file:
                        current.main_file = section_name
                elif re.match(r"^EXPECT_STDOUT:", line):
                    section = "stdout"
                    current.expect_stdout = ""
                elif re.match(r"^EXPECT_STDERR:", line):
                    section = "stderr"
                    current.expect_stderr = ""
                elif m := re.match(r"^EXPECT_HEX:\s*(.*)", line):
                    current.expect_hex = m.group(1)
                    section = ""
                elif m := re.match(r"^EXPECT_FWDREF:\s*(.*)", line):
                    current.expect_fwdref = m.group(1)
                    section = ""
                elif m := re.match(r"^EXPECT_ERROR:\s*(.*)", line):
                    current.expect_error = m.group(1)
                    section = ""
                elif m := re.match(r"^EXPECT_LINE:\s*(.*)", line):
                    current.expect_line = m.group(1)
                    section = ""
                elif m := re.match(r"^EXPECT_MSG:\s*(.*)", line):
                    current.expect_msg = m.group(1)
                    section = ""
                elif m := re.match(r"^ARGS:\s*(.*)", line):
                    current.args = m.group(1)
                    section = ""
                elif m := re.match(r"^SKIP:\s*(.*)", line):
                    current.skip = m.group(1)
                    section = ""
                elif re.match(r"^MISSING_INPUT$", line):
                    current.missing_input = True
                    section = ""
                elif section == "input":
                    # Strip line number prefix: optional spaces, digits, colon, required space
                    line = re.sub(r"^\s*\d+: ", "", line)
                    # Check for bracketed format: [content]
                    line, is_bracketed = self._parse_bracketed_line(line)
                    if is_bracketed:
                        current.input_text_bracketed = True
                    if current.input_text:
                        current.input_text += "\n"
                    current.input_text += line
                elif section == "file":
                    # Strip line number prefix: optional spaces, digits, colon, required space
                    line = re.sub(r"^\s*\d+: ", "", line)
                    current.files[section_name] += line + "\n"
                elif section == "stdout":
                    # Skip comment and blank lines in expected output sections
                    if re.match(r"^\s*#", line) or re.match(r"^\s*$", line):
                        continue
                    if current.expect_stdout:
                        current.expect_stdout += "\n"
                    current.expect_stdout += line
                elif section == "stderr":
                    # Skip comment and blank lines in expected output sections
                    if re.match(r"^\s*#", line) or re.match(r"^\s*$", line):
                        continue
                    # Check for bracketed format: [content]
                    line, is_bracketed = self._parse_bracketed_line(line)
                    if is_bracketed:
                        current.expect_stderr_bracketed = True
                    if current.expect_stderr:
                        current.expect_stderr += "\n"
                    current.expect_stderr += line

        # Don't forget the last test
        if current.name:
            self._finalize_test(current)
            tests.append(current)

        return tests

    def _parse_bracketed_line(self, line: str) -> tuple[str, bool]:
        """Parse a line that may use [content] bracket format for whitespace preservation.

        Returns (content, is_bracketed) where content has brackets stripped if present.
        """
        if line.startswith("[") and line.endswith("]"):
            return line[1:-1], True
        return line, False

    def _finalize_test(self, test: Test):
        """Infer test type if not explicitly set."""
        if test.test_type is None:
            if test.mode or test.files:
                test.test_type = TestType.SOURCE_STACK
            else:
                test.test_type = TestType.ASSEMBLER

    def run_test(self, test: Test, filter_pattern: str = "") -> Optional[TestOutcome]:
        """Run a single test and return the outcome."""
        # Apply filter
        if filter_pattern and filter_pattern not in test.name:
            return None

        # Handle skipped tests
        if test.skip:
            return TestOutcome(TestResult.SKIP, [test.skip])

        # In python mode, skip source_stack tests and small_heap tests
        if self.python_mode:
            if test.test_type == TestType.SOURCE_STACK:
                return TestOutcome(TestResult.SKIP, ["source_stack tests not applicable in python mode"])
            if "small_heap" in test.args:
                return TestOutcome(TestResult.SKIP, ["small_heap not applicable in python mode"])

        if test.test_type == TestType.ASSEMBLER:
            if self.use_server:
                return self._run_assembler_test_server(test)
            return self._run_assembler_test(test)
        elif test.test_type == TestType.SOURCE_STACK:
            if self.use_server:
                return self._run_source_stack_test_server(test)
            return self._run_source_stack_test(test)
        else:
            return TestOutcome(TestResult.SKIP, ["Unknown test type"])

    def _run_assembler_test(self, test: Test) -> TestOutcome:
        """Run an assembler test.

        Mirrors the self-hosted test runner's discipline: cwd is the
        directory of the .txt test file, and the input/output paths the
        assembler sees are the bare basenames TR_INPUT_FILE /
        TR_OUTPUT_FILE. That keeps frame_size and traceback output
        identical across machines, OS tempdir conventions, and checkout
        depth, and lets `.include subdir/foo.asm` resolve naturally
        without any symlink/tempdir setup."""
        test_dir = self.current_test_file.parent if self.current_test_file else Path(".")
        asm_file = test_dir / TR_INPUT_FILE
        bin_file = test_dir / TR_OUTPUT_FILE
        err_file = test_dir / TR_ERR_FILE

        try:
            # Write input file (unless testing missing input file)
            if not test.missing_input:
                asm_file.write_text(test.input_text + "\n")
            elif asm_file.exists():
                asm_file.unlink()

            # Stale output from a prior crashed run could mask a real
            # failure-to-emit; remove it.
            if bin_file.exists():
                bin_file.unlink()

            # Pass the input/output files as basenames; the assembler
            # runs with cwd=test_dir below, so frame name = TR_INPUT_FILE
            # regardless of where the test repo lives.
            if self.python_mode:
                # Python assembler mode
                cmd = [
                    sys.executable,
                    str(self.python_asm),
                    TR_INPUT_FILE,
                    TR_OUTPUT_FILE,
                ]
                # Add args (ARGS overrides the default "debug" argument)
                if test.args:
                    cmd.extend(test.args.split())
                else:
                    cmd.append("debug")
            else:
                # Emulator mode - version-aware command construction
                version = int(self.asm_version)
                if version <= 7:
                    # v01-v07: --load 2000 --input FILE --output FILE
                    cmd = [
                        str(self.emulator),
                        str(self.assembler),
                        "--no-dump",
                        "--error-output", TR_ERR_FILE,
                        "--load", "2000",
                        "--input", TR_INPUT_FILE,
                        "--output", TR_OUTPUT_FILE,
                    ]
                elif version <= 8:
                    # v08: --input FILE --output FILE (no --load)
                    cmd = [
                        str(self.emulator),
                        str(self.assembler),
                        "--no-dump",
                        "--error-output", TR_ERR_FILE,
                        "--input", TR_INPUT_FILE,
                        "--output", TR_OUTPUT_FILE,
                    ]
                else:
                    # v09+: positional args
                    cmd = [
                        str(self.emulator),
                        str(self.assembler),
                        "--no-dump",
                        "--error-output", TR_ERR_FILE,
                        TR_INPUT_FILE,
                        TR_OUTPUT_FILE,
                    ]
                    # Add args (ARGS overrides the default "debug" argument)
                    if test.args:
                        cmd.extend(test.args.split())
                    elif version >= 11:
                        cmd.append("debug")

            if self.python_mode:
                with open(err_file, "w") as err_fh:
                    result = subprocess.run(cmd, stderr=err_fh, capture_output=False, cwd=test_dir)
            else:
                result = subprocess.run(cmd, capture_output=True, cwd=test_dir)

            exit_code = result.returncode
            stderr_text = self._read_text_safe(err_file) if err_file.exists() else ""

            # If the assembler couldn't even write to err_file (e.g.
            # emulator-level failure: missing input, bad --error-output
            # path, segfault) the actual diagnostic is on the emulator's
            # own stderr. result.stderr is None in python_mode (we
            # redirect to err_fh directly) but bytes in emulator mode.
            if exit_code != 0 and not stderr_text and getattr(result, "stderr", None):
                stderr_text = result.stderr.decode("latin-1", errors="replace")

            # Determine if this is a positive or negative test
            if test.expect_hex:
                return self._check_positive_assembler_test(test, bin_file, stderr_text, exit_code, asm_file)
            elif test.expect_error:
                return self._check_negative_assembler_test(test, stderr_text, exit_code, asm_file)
            elif test.expect_stderr:
                return self._check_stderr_test(test, stderr_text, exit_code, asm_file)
            else:
                return TestOutcome(TestResult.SKIP, ["No expectation defined"])
        finally:
            # Clean up the temp files we created in test_dir, including
            # any stale ones from crashed runs.
            for f in (asm_file, bin_file, err_file):
                if f.exists():
                    try:
                        f.unlink()
                    except OSError:
                        pass

    def _check_positive_assembler_test(
        self, test: Test, bin_file: Path, stderr_text: str, exit_code: int, asm_file: Path
    ) -> TestOutcome:
        """Check a positive assembler test (expects success)."""
        details = []

        if exit_code != 0:
            details.append("Unexpected error:")
            # Show every non-empty stderr line, not just ones starting
            # with "Error ". Emulator-level failures (e.g. "could not
            # open input file") don't use the "Error N" prefix and were
            # silently dropped before, leaving a bare "Unexpected error:"
            # with no detail.
            for line in stderr_text.strip().split("\n"):
                if line:
                    details.append(f"  {line}")
            return TestOutcome(TestResult.FAIL, details)

        # Check hex output
        if bin_file.exists():
            actual_hex = bin_file.read_bytes().hex()
            actual_hex = " ".join(actual_hex[i : i + 2] for i in range(0, len(actual_hex), 2))
        else:
            actual_hex = ""

        expected_hex = self._normalize_hex(test.expect_hex)
        actual_hex = self._normalize_hex(actual_hex)

        if expected_hex != actual_hex:
            details.append(f"Expected hex: {expected_hex}")
            details.append(f"Actual hex:   {actual_hex}")

        # Check forward reference count if specified
        if test.expect_fwdref:
            actual_fwdref = ""
            for line in stderr_text.split("\n"):
                if "Forward references forced to absolute:" in line:
                    m = re.search(r": (\d+)$", line)
                    if m:
                        actual_fwdref = m.group(1)
                    break

            if actual_fwdref != test.expect_fwdref:
                details.append(f"Expected fwdref count: {test.expect_fwdref}")
                details.append(f"Actual fwdref count:   {actual_fwdref}")

        # Check stderr if specified
        if test.expect_stderr:
            self._check_stderr(test, stderr_text, asm_file, details)

        if details:
            return TestOutcome(TestResult.FAIL, details)
        return TestOutcome(TestResult.PASS)

    def _check_negative_assembler_test(
        self, test: Test, stderr_text: str, exit_code: int, asm_file: Path
    ) -> TestOutcome:
        """Check a negative assembler test (expects failure)."""
        details = []

        if exit_code == 0:
            details.append("Expected error, got success")
            return TestOutcome(TestResult.FAIL, details)

        # Parse error output
        actual_error = ""
        actual_line = ""
        actual_msg = ""

        for line in stderr_text.split("\n"):
            if line.startswith("Error "):
                m = re.match(r"Error (\d+)", line)
                if m:
                    actual_error = m.group(1)
                m = re.search(r"at line (\d+)", line)
                if m:
                    actual_line = m.group(1)
                m = re.search(r": ([^:]+)$", line)
                if m:
                    actual_msg = m.group(1)
                break

        if actual_error != test.expect_error:
            details.append(f"Error code: expected {test.expect_error}, got {actual_error}")

        if test.expect_line and actual_line != test.expect_line:
            details.append(f"Line: expected {test.expect_line}, got {actual_line}")

        if test.expect_msg and test.expect_msg != actual_msg:
            details.append(f"Message: expected '{test.expect_msg}', got '{actual_msg}'")

        # Check full stderr if specified
        if test.expect_stderr:
            self._check_stderr(test, stderr_text, asm_file, details)

        if details:
            return TestOutcome(TestResult.FAIL, details)
        return TestOutcome(TestResult.PASS)

    def _check_stderr(
        self, test: Test, stderr_text: str, asm_file: Path, details: list[str]
    ):
        """Check stderr output matches expected. Appends failures to details list."""
        actual_stderr = stderr_text

        # Replace placeholder with the file path the assembler ACTUALLY
        # saw (the basename, since we run with cwd=test_dir and pass
        # TR_INPUT_FILE as argv[0]). The asm_file Path is still useful
        # for diagnostics but isn't what gets written into tracebacks.
        # Append \n since the assembler always terminates stderr with a
        # newline.
        expected_stderr = test.expect_stderr.replace("{{MAIN_FILE}}", TR_INPUT_FILE) + "\n"

        if actual_stderr != expected_stderr:
            self._add_comparison(details, "stderr", expected_stderr, actual_stderr,
                                 bracketed=test.expect_stderr_bracketed)

    def _check_stderr_test(
        self, test: Test, stderr_text: str, exit_code: int, asm_file: Path
    ) -> TestOutcome:
        """Check a test that only specifies expected stderr output (no hex or error code)."""
        details = []
        self._check_stderr(test, stderr_text, asm_file, details)
        if details:
            return TestOutcome(TestResult.FAIL, details)
        return TestOutcome(TestResult.PASS)

    def _run_assembler_test_server(self, test: Test) -> TestOutcome:
        """Run an assembler test using server mode.

        Like _run_assembler_test, this uses cwd=test_dir and basenames
        for the input/output files so the assembler sees TR_INPUT_FILE /
        TR_OUTPUT_FILE regardless of where the repo lives. (The shared
        tmpdir is no longer used by this path -- temp files live in
        test_dir alongside the test fixtures.)"""
        test_dir = self.current_test_file.parent if self.current_test_file else Path(".")
        asm_file = test_dir / TR_INPUT_FILE
        bin_file = test_dir / TR_OUTPUT_FILE

        try:
            # Write input file (unless testing missing input file)
            if test.missing_input:
                if asm_file.exists():
                    asm_file.unlink()
            else:
                asm_file.write_text(test.input_text + "\n")

            # Remove stale output
            if bin_file.exists():
                bin_file.unlink()

            args = [TR_INPUT_FILE, TR_OUTPUT_FILE]
            if test.args:
                args.extend(test.args.split())
            elif int(self.asm_version) >= 11:
                args.append("debug")

            exit_code, _, stderr_data = self.emu.run(
                self.assembler, args=args,
                cwd=str(test_dir),
                inline_stderr=True)

            stderr_text = stderr_data.decode('latin-1') if stderr_data else ""

            if test.expect_hex:
                return self._check_positive_assembler_test(
                    test, bin_file, stderr_text, exit_code, asm_file)
            elif test.expect_error:
                return self._check_negative_assembler_test(
                    test, stderr_text, exit_code, asm_file)
            elif test.expect_stderr:
                return self._check_stderr_test(
                    test, stderr_text, exit_code, asm_file)
            else:
                return TestOutcome(TestResult.SKIP, ["No expectation defined"])
        finally:
            for f in (asm_file, bin_file):
                if f.exists():
                    try:
                        f.unlink()
                    except OSError:
                        pass

    def _run_source_stack_test_server(self, test: Test) -> TestOutcome:
        """Run a source stack test using server mode."""
        if not test.mode or not test.main_file:
            return TestOutcome(TestResult.SKIP, ["Missing mode or file"])

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            for filename, content in test.files.items():
                if test.mode == "memory":
                    content = re.sub(
                        r"@include\s+(\S+)", rf"@include {tmpdir}/\1", content)

                filepath = tmpdir / filename
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(content)

            main_file = tmpdir / test.main_file

            exit_code, output, stderr_data = self.emu.run(
                self.source_stack_test,
                args=[test.mode, str(main_file)],
                load_addr=0x200,
                cwd=str(tmpdir),
                inline_output=True,
                inline_stderr=True)

            actual_stdout = output.decode('latin-1') if output else ""
            actual_stderr = stderr_data.decode('latin-1') if stderr_data else ""

            actual_stdout = self._normalize_text(actual_stdout)
            expected_stdout = self._normalize_text(test.expect_stdout)

            # Compare stderr exactly; append \n since program always
            # terminates stderr with a newline
            expected_stderr = test.expect_stderr + "\n" if test.expect_stderr else ""

            details = []

            if expected_stdout or actual_stdout:
                if actual_stdout != expected_stdout:
                    self._add_comparison(details, "stdout", expected_stdout, actual_stdout)

            if expected_stderr or actual_stderr:
                if actual_stderr != expected_stderr:
                    self._add_comparison(details, "stderr", expected_stderr, actual_stderr)

            if details:
                return TestOutcome(TestResult.FAIL, details)
            return TestOutcome(TestResult.PASS)

    def _run_source_stack_test(self, test: Test) -> TestOutcome:
        """Run a file stack test."""
        if not test.mode or not test.main_file:
            return TestOutcome(TestResult.SKIP, ["Missing mode or file"])

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Write input files
            for filename, content in test.files.items():
                # Transform @include directives for nested/memory modes
                if test.mode == "memory":
                    content = re.sub(
                        r"@include\s+(\S+)", rf"@include {tmpdir}/\1", content
                    )

                filepath = tmpdir / filename
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(content)

            main_file = tmpdir / test.main_file
            stdout_file = tmpdir / "stdout"
            stderr_file = tmpdir / "stderr"

            # Run test program
            cmd = [
                str(self.emulator),
                str(self.source_stack_test),
                "--no-dump",
                "--load", "200",
                "--output", str(stdout_file),
                "--error-output", str(stderr_file),
                test.mode,
                str(main_file),
            ]

            # Run with cwd set to tmpdir so nested includes resolve correctly
            subprocess.run(cmd, capture_output=True, cwd=tmpdir)

            # Read outputs
            actual_stdout = self._read_text_safe(stdout_file) if stdout_file.exists() else ""
            actual_stderr = self._read_text_safe(stderr_file) if stderr_file.exists() else ""

            # Normalize stdout
            actual_stdout = self._normalize_text(actual_stdout)
            expected_stdout = self._normalize_text(test.expect_stdout)

            # Compare stderr exactly; append \n since program always
            # terminates stderr with a newline
            expected_stderr = test.expect_stderr + "\n" if test.expect_stderr else ""

            details = []

            if expected_stdout or actual_stdout:
                if actual_stdout != expected_stdout:
                    self._add_comparison(details, "stdout", expected_stdout, actual_stdout)

            if expected_stderr or actual_stderr:
                if actual_stderr != expected_stderr:
                    self._add_comparison(details, "stderr", expected_stderr, actual_stderr)

            if details:
                return TestOutcome(TestResult.FAIL, details)
            return TestOutcome(TestResult.PASS)

    def _normalize_hex(self, hex_str: str) -> str:
        """Normalize hex string: lowercase, single spaces."""
        return " ".join(hex_str.lower().split())

    def _normalize_text(self, text: str) -> str:
        """Normalize text: strip trailing whitespace from lines and end."""
        if not text:
            return ""
        lines = [line.rstrip() for line in text.split("\n")]
        return "\n".join(lines).rstrip()

    def _add_comparison(
        self, details: list[str], label: str, expected: str, actual: str,
        bracketed: bool = False
    ):
        """Add expected vs actual comparison to details list."""
        details.append(f"Expected {label}:")
        self._add_indented(details, expected, bracketed=bracketed)
        details.append(f"Actual {label}:")
        self._add_indented(details, actual, bracketed=bracketed)

    def _add_indented(self, details: list[str], text: str, bracketed: bool = False):
        """Add indented text lines to details list."""
        if not text:
            details.append("  (empty)")
            return
        for line in text.split("\n"):
            if bracketed:
                details.append(f"  [{line}]")
            else:
                details.append(f"  {line}")

    def print_result(self, name: str, outcome: TestOutcome):
        """Print test result."""
        printf_name = f"  {name:<40} "

        if outcome.result == TestResult.PASS:
            if not self.quiet:
                print(f"{printf_name}{Colors.GREEN}PASS{Colors.NC}")
            self.passed += 1
        elif outcome.result == TestResult.FAIL:
            print(f"{printf_name}{Colors.RED}FAIL{Colors.NC}")
            for detail in outcome.details:
                print(f"    {detail}")
            self.failed += 1
        elif outcome.result == TestResult.SKIP:
            reason = outcome.details[0] if outcome.details else ""
            print(f"{printf_name}{Colors.YELLOW}SKIP{Colors.NC} ({reason})")
            self.skipped += 1

    def run_test_file(self, filepath: Path, filter_pattern: str = ""):
        """Run all tests in a file."""
        tests = self.parse_test_file(filepath)

        # Check prerequisites for test types in this file
        test_types = set(t.test_type for t in tests if t.test_type)
        for tt in test_types:
            if not self.check_prerequisites(tt):
                return

        try:
            display_path = filepath.relative_to(self.base_dir)
        except ValueError:
            display_path = filepath
        print(f"Running tests from {display_path}")
        if not self.quiet:
            print()

        # Set current test file for relative include resolution
        self.current_test_file = filepath

        for test in tests:
            outcome = self.run_test(test, filter_pattern)
            if outcome:
                self.print_result(test.name, outcome)

    def print_summary(self):
        """Print final summary."""
        print()
        print("=" * 40)
        parts = [f"{Colors.GREEN}{self.passed} passed{Colors.NC}"]
        if self.failed:
            parts.append(f"{Colors.RED}{self.failed} failed{Colors.NC}")
        if self.skipped:
            parts.append(f"{Colors.YELLOW}{self.skipped} skipped{Colors.NC}")
        print(f"Results: {', '.join(parts)}")
        print("=" * 40)


def main():
    parser = argparse.ArgumentParser(
        description="Unified test runner for 6502 assembler project"
    )
    parser.add_argument(
        "test_files",
        nargs="*",
        help="Test files to run (default: <asm_version>/tests/asm_tests.txt and <asm_version>/tests/source_stack_tests.txt)",
    )
    parser.add_argument(
        "-f", "--filter", default="", help="Only run tests matching this pattern"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose output"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Only show failures and summary"
    )
    parser.add_argument(
        "--no-color", action="store_true", help="Disable colored output"
    )
    parser.add_argument(
        "--version", default=ASM_VERSION,
        help=f"Assembler version to test (default: {ASM_VERSION})"
    )
    parser.add_argument(
        "--python", action="store_true",
        help="Use Python assembler (pyasm.py) instead of emulator"
    )
    parser.add_argument(
        "--no-server", action="store_true",
        help="Use subprocess per test instead of persistent emulator server"
    )

    args = parser.parse_args()

    if args.no_color:
        Colors.disable()

    # Determine base directory (repo root)
    script_dir = Path(__file__).parent.resolve()
    base_dir = script_dir

    runner = TestRunner(base_dir, verbose=args.verbose, quiet=args.quiet,
                        asm_version=args.version, python_mode=args.python,
                        use_server=not args.no_server)

    print("=" * 40)
    print("Test Suite")
    print("=" * 40)
    print()

    # Default test files if none specified
    if not args.test_files:
        latest_tests_dir = script_dir / args.version / "tests"

        # Check for modular structure (v23+)
        asm_subdir = latest_tests_dir / "asm"
        source_stack_subdir = latest_tests_dir / "source_stack"

        if asm_subdir.exists() and asm_subdir.is_dir():
            # Modular structure: discover all .txt files
            args.test_files = []

            # Add source_stack tests first
            if source_stack_subdir.exists():
                for test_file in sorted(source_stack_subdir.glob("*.txt")):
                    args.test_files.append(str(test_file))

            # Add asm tests (alphabetically sorted - numeric prefixes preserve logical order)
            for test_file in sorted(asm_subdir.glob("*.txt")):
                args.test_files.append(str(test_file))
        else:
            # Legacy structure (v22 and earlier)
            args.test_files = [
                str(latest_tests_dir / "source_stack_tests.txt"),
                str(latest_tests_dir / "asm_tests.txt"),
            ]

    for test_file in args.test_files:
        filepath = Path(test_file)
        if not filepath.is_absolute():
            # Try relative to current dir first, then script dir
            if not filepath.exists():
                filepath = script_dir / test_file
        if not filepath.exists():
            print(f"Error: Test file not found: {test_file}")
            continue

        runner.run_test_file(filepath, args.filter)
        if not args.quiet:
            print()

    if runner.emu:
        runner.emu.close()

    runner.print_summary()

    sys.exit(1 if runner.failed > 0 else 0)


if __name__ == "__main__":
    main()
