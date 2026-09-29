#!/usr/bin/env python3
"""
Tests for the opendir emulator feature.

Runs the opendir_test.out program against various directory configurations
and validates the output.

Usage:
    python3 17/tests/opendir/test_opendir.py
"""

import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    NC = "\033[0m"


# Paths relative to project root
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
EMULATOR = PROJECT_ROOT.parent / "emulator" / "emulator.out"
TEST_PROGRAM = PROJECT_ROOT / "17" / "out" / "opendir_test.out"


def run_opendir(dir_path, cwd=None):
    """Run the opendir test program on the given directory path.
    Returns (output, exit_code)."""
    with tempfile.TemporaryDirectory() as run_tmpdir:
        stdout_file = Path(run_tmpdir) / "stdout"
        result = subprocess.run(
            [str(EMULATOR), str(TEST_PROGRAM), "--no-dump", "--load", "200",
             "--output", str(stdout_file), str(dir_path)],
            capture_output=True,
            timeout=10,
            cwd=cwd,
        )
        if stdout_file.exists():
            output = stdout_file.read_bytes().decode("utf-8", errors="replace")
        else:
            output = ""
        return output, result.returncode


def test_empty_directory():
    """Empty directory should produce no output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output, rc = run_opendir(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}"
        assert output == "", f"Expected empty output, got {output!r}"


def test_files_only():
    """Directory with only files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        for name in ["a.txt", "b.txt", "c.txt"]:
            Path(tmpdir, name).touch()
        output, rc = run_opendir(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}"
        assert output == "00 a.txt\n00 b.txt\n00 c.txt\n", f"Got {output!r}"


def test_dirs_only():
    """Directory with only subdirectories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        for name in ["alpha", "beta"]:
            Path(tmpdir, name).mkdir()
        output, rc = run_opendir(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}"
        assert output == "01 alpha\n01 beta\n", f"Got {output!r}"


def test_mixed():
    """Directory with both files and subdirectories, sorted alphabetically."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "readme.txt").touch()
        Path(tmpdir, "src").mkdir()
        Path(tmpdir, "data").mkdir()
        output, rc = run_opendir(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}"
        assert output == "01 data\n00 readme.txt\n01 src\n", f"Got {output!r}"


def test_alphabetical_order():
    """Entries should be sorted alphabetically."""
    with tempfile.TemporaryDirectory() as tmpdir:
        for name in ["zebra.txt", "apple.txt", "mango.txt"]:
            Path(tmpdir, name).touch()
        output, rc = run_opendir(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}"
        assert output == "00 apple.txt\n00 mango.txt\n00 zebra.txt\n", f"Got {output!r}"


def test_hidden_excluded():
    """Hidden files and directories (starting with .) should be excluded."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, ".hidden").touch()
        Path(tmpdir, ".git").mkdir()
        Path(tmpdir, "visible.txt").touch()
        output, rc = run_opendir(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}"
        assert output == "00 visible.txt\n", f"Got {output!r}"


def test_spaces_in_names():
    """Filenames and directory names with spaces."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "my file.txt").touch()
        Path(tmpdir, "a dir").mkdir()
        output, rc = run_opendir(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}"
        assert output == "01 a dir\n00 my file.txt\n", f"Got {output!r}"


def test_nonexistent_dir():
    """Non-existent directory should output ERROR and exit with code 1."""
    output, rc = run_opendir("/tmp/nonexistent_dir_12345")
    assert rc == 1, f"Expected exit code 1, got {rc}"
    assert output == "ERROR\n", f"Got {output!r}"


def test_readonly_file():
    """Read-only files should have the readonly metadata bit set."""
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir, "readonly.txt")
        p.touch()
        p.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        output, rc = run_opendir(tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}"
        assert output == "02 readonly.txt\n", f"Got {output!r}"


def test_trailing_slash():
    """Path with trailing slash should work the same as without."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "hello.txt").touch()
        # Run with trailing slash
        output1, rc1 = run_opendir(tmpdir + "/")
        # Run without trailing slash
        output2, rc2 = run_opendir(tmpdir)
        assert rc1 == 0 and rc2 == 0, f"Exit codes: {rc1}, {rc2}"
        assert output1 == output2, f"With slash: {output1!r}, without: {output2!r}"


def test_dot_directory():
    """'.' as path should list current working directory contents."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.txt").touch()
        output, rc = run_opendir(".", cwd=tmpdir)
        assert rc == 0, f"Expected exit code 0, got {rc}"
        assert output == "00 test.txt\n", f"Got {output!r}"


def main():
    if not EMULATOR.exists():
        print(f"Error: Emulator not found at {EMULATOR}")
        sys.exit(1)
    if not TEST_PROGRAM.exists():
        print(f"Error: Test program not found at {TEST_PROGRAM}")
        sys.exit(1)

    tests = [
        ("empty_directory", test_empty_directory),
        ("files_only", test_files_only),
        ("dirs_only", test_dirs_only),
        ("mixed", test_mixed),
        ("alphabetical_order", test_alphabetical_order),
        ("hidden_excluded", test_hidden_excluded),
        ("spaces_in_names", test_spaces_in_names),
        ("nonexistent_dir", test_nonexistent_dir),
        ("readonly_file", test_readonly_file),
        ("trailing_slash", test_trailing_slash),
        ("dot_directory", test_dot_directory),
    ]

    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            test_fn()
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
