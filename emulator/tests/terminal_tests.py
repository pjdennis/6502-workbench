#!/usr/bin/env python3
"""
Test runner for terminal mode serial I/O.

Tests the emulator's --terminal mode by assembling a test program,
running it with --terminal --input/--output, and verifying output.

Usage:
    python3 tests/terminal_tests.py [-v]
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


# ANSI colors
class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    NC = "\033[0m"

    @classmethod
    def disable(cls):
        cls.RED = cls.GREEN = cls.YELLOW = cls.NC = ""


class TerminalTestRunner:
    def __init__(self, base_dir: Path, verbose: bool = False):
        self.base_dir = base_dir
        self.verbose = verbose
        self.emulator = base_dir / "emulator" / "emulator.out"
        self.assembler = base_dir / "toolchain" / "asm2" / "17" / "out" / "asm.out"
        self.test_asm = base_dir / "emulator" / "tests" / "terminal_test.asm"
        self.test_bin = base_dir / "emulator" / "tests" / "out" / "terminal_test.out"
        self.dsr_test_asm = base_dir / "emulator" / "tests" / "terminal_dsr_test.asm"
        self.dsr_test_bin = base_dir / "emulator" / "tests" / "out" / "terminal_dsr_test.out"
        self.wait_test_asm = base_dir / "emulator" / "tests" / "wait_ready_serial_test.asm"
        self.wait_test_bin = base_dir / "emulator" / "tests" / "out" / "wait_ready_serial_test.out"
        self.passed = 0
        self.failed = 0

    def _assemble(self, src, dst):
        """Assemble a test program."""
        if not self.emulator.exists():
            print(f"Error: Emulator not found at {self.emulator}")
            return False
        if not self.assembler.exists():
            print(f"Error: Assembler not found at {self.assembler}")
            return False

        dst.parent.mkdir(exist_ok=True)
        result = subprocess.run(
            [str(self.emulator), str(self.assembler),
             "--no-dump", str(src), str(dst)],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"Error: Failed to assemble {src.name}:")
            print(result.stderr)
            return False
        return True

    def build_test_program(self):
        """Assemble the terminal test program."""
        return self._assemble(self.test_asm, self.test_bin)

    def build_dsr_test_program(self):
        """Assemble the DSR test program."""
        return self._assemble(self.dsr_test_asm, self.dsr_test_bin)

    def run_dsr_test(self, name: str, extra_args: list = None,
                     expected_output: bytes = None):
        """Run the DSR test program and verify output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            keys_file = tmpdir / "input.bin"
            output_file = tmpdir / "output.bin"
            keys_file.write_bytes(b"")  # No input needed

            cmd = [str(self.emulator), str(self.dsr_test_bin),
                   "--no-dump", "--load", "0400", "--terminal",
                   "--input", str(keys_file),
                   "--output", str(output_file)]
            if extra_args:
                cmd.extend(extra_args)

            try:
                result = subprocess.run(cmd, capture_output=True, timeout=10)
            except subprocess.TimeoutExpired:
                self._fail(name, "Timed out (infinite loop?)")
                return
            except Exception as e:
                self._fail(name, f"Error: {e}")
                return

            if result.returncode != 0:
                self._fail(name,
                    f"Expected exit code 0, got {result.returncode}\n"
                    f"  stderr: {result.stderr.decode('utf-8', errors='replace')}")
                return

            output = output_file.read_bytes() if output_file.exists() else b""
            if expected_output is not None:
                if output != expected_output:
                    self._fail(name,
                        f"Output mismatch:\n"
                        f"  Expected: {expected_output!r}\n"
                        f"  Actual:   {output!r}")
                    return

            self._pass(name)

    def run_terminal(self, input_bytes: bytes, tmpdir: Path,
                     extra_args: list = None, binary: Path = None) -> tuple:
        """Run a test program (default: the echo program) in terminal mode
        with file I/O.

        Returns (exit_code, output_bytes).
        """
        keys_file = tmpdir / "input.bin"
        output_file = tmpdir / "output.bin"
        keys_file.write_bytes(input_bytes)

        cmd = [str(self.emulator), str(binary or self.test_bin), "--no-dump",
               "--load", "0400", "--terminal", "--input", str(keys_file),
               "--output", str(output_file)]
        if extra_args:
            cmd.extend(extra_args)

        result = subprocess.run(cmd, capture_output=True, timeout=10)

        output = output_file.read_bytes() if output_file.exists() else b""
        return result.returncode, output

    def _pass(self, name: str):
        self.passed += 1
        if self.verbose:
            print(f"  {Colors.GREEN}PASS{Colors.NC} {name}")

    def _fail(self, name: str, reason: str):
        self.failed += 1
        print(f"  {Colors.RED}FAIL{Colors.NC} {name}: {reason}")

    def run_emulator_args_test(self, name: str, extra_args: list,
                               expect_exit: int = 0):
        """Test emulator CLI argument validation (no test program needed)."""
        cmd = [str(self.emulator), str(self.test_bin), "--no-dump",
               "--load", "0400", "--terminal"] + extra_args
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=10)
        except subprocess.TimeoutExpired:
            self._fail(name, "Timed out")
            return
        except Exception as e:
            self._fail(name, f"Error: {e}")
            return
        if result.returncode != expect_exit:
            self._fail(name,
                f"Expected exit code {expect_exit}, got {result.returncode}")
            return
        self._pass(name)

    def run_test(self, name: str, input_bytes: bytes,
                 expected_output: bytes = None,
                 expect_exit: int = 0,
                 extra_args: list = None,
                 binary: Path = None):
        """Run a terminal test case."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            try:
                exit_code, output = self.run_terminal(input_bytes, tmpdir,
                                                      extra_args=extra_args,
                                                      binary=binary)
            except subprocess.TimeoutExpired:
                self._fail(name, "Timed out (infinite loop?)")
                return
            except Exception as e:
                self._fail(name, f"Error: {e}")
                return

            if exit_code != expect_exit:
                self._fail(name,
                    f"Expected exit code {expect_exit}, got {exit_code}")
                return

            if expected_output is not None:
                if output != expected_output:
                    self._fail(name,
                        f"Output mismatch:\n"
                        f"  Expected: {expected_output!r}\n"
                        f"  Actual:   {output!r}")
                    return

            self._pass(name)

    def run_all_tests(self):
        """Run all terminal mode tests."""
        print("=" * 60)
        print("Terminal Mode Test Suite")
        print("=" * 60)

        if not self.build_test_program():
            return False

        # Echo test: send "Hello" + Ctrl+D, verify echoed output
        self.run_test(
            "Echo test",
            input_bytes=b"Hello\x04",
            expected_output=b"Hello"
        )

        # Exit test: send just Ctrl+D, verify clean exit with empty output
        self.run_test(
            "Exit on Ctrl+D",
            input_bytes=b"\x04",
            expected_output=b""
        )

        # ANSI passthrough: send ESC sequence bytes, verify they pass through
        self.run_test(
            "Binary passthrough",
            input_bytes=b"\x1b[2J\x04",
            expected_output=b"\x1b[2J"
        )

        # Multi-byte echo: various characters including CR/LF
        self.run_test(
            "CR/LF echo",
            input_bytes=b"ab\r\ncd\x04",
            expected_output=b"ab\r\ncd"
        )

        # Baud rate: --baud without --cpu-mhz or --mhz should error
        self.run_emulator_args_test(
            "Baud without clock errors",
            ["--baud", "9600"],
            expect_exit=1
        )

        # Baud rate: echo still works with --baud and --cpu-mhz
        self.run_test(
            "Echo with baud rate",
            input_bytes=b"Hi\x04",
            expected_output=b"Hi",
            extra_args=["--cpu-mhz", "1", "--baud", "9600"]
        )

        # --pace-mask in terminal mode: input is held until the program is
        # idle, and each hold must release (the run completes)
        with tempfile.TemporaryDirectory() as mask_dir:
            mask_file = Path(mask_dir) / "mask.bin"
            mask_file.write_bytes(b"111")
            self.run_test(
                "Echo with paced input",
                input_bytes=b"Hi\x04",
                expected_output=b"Hi",
                extra_args=["--cpu-mhz", "1", "--baud", "300",
                            "--pace-mask", str(mask_file)]
            )

        # --cpu-mhz alone doesn't break existing tests
        self.run_test(
            "cpu-mhz without baud",
            input_bytes=b"Ok\x04",
            expected_output=b"Ok",
            extra_args=["--cpu-mhz", "1"]
        )

        # DSR tests
        if not self.build_dsr_test_program():
            print("Skipping DSR tests (build failed)")
        else:
            # Output prefix: ESC[999;999H + ESC[6n (command bytes written before response)
            cmd_prefix = b"\x1b[999;999H\x1b[6n"

            # DSR basic response: default 24x80
            self.run_dsr_test(
                "DSR basic response (24x80)",
                extra_args=["--rows", "24", "--cols", "80"],
                expected_output=cmd_prefix + b"\x1b[24;80R"
            )

            # DSR with custom size
            self.run_dsr_test(
                "DSR custom size (10x40)",
                extra_args=["--rows", "10", "--cols", "40"],
                expected_output=cmd_prefix + b"\x1b[10;40R"
            )

            # DSR with baud rate
            self.run_dsr_test(
                "DSR with baud rate",
                extra_args=["--rows", "10", "--cols", "40",
                            "--cpu-mhz", "1", "--baud", "9600"],
                expected_output=cmd_prefix + b"\x1b[10;40R"
            )

        # wait_ready: the program waits up to 1 s for 'A', then 10 ms and
        # 50 ms for 'B', then 1 s after the input has ended, writing each
        # result ($FF ready, $00 timed out) and each byte it reads
        if not self._assemble(self.wait_test_asm, self.wait_test_bin):
            self._fail("wait_ready tests", "wait_ready_serial_test.asm did not assemble")
        else:
            # 300 baud at 1 MHz: 'B' arrives 33 ms after 'A', so the 10 ms
            # wait times out and the 50 ms wait gets it; waits cost no host
            # time because emulated time jumps to the next arrival
            self.run_test(
                "wait_ready: 300 baud, byte one byte-time away",
                input_bytes=b"AB",
                expected_output=b"\xffA\x00\xffB\x00",
                extra_args=["--cpu-mhz", "1", "--baud", "300"],
                binary=self.wait_test_bin
            )
            # 9600 baud: 'B' is ~1 ms behind 'A', inside the 10 ms wait
            self.run_test(
                "wait_ready: 9600 baud, returns when the byte arrives",
                input_bytes=b"AB",
                expected_output=b"\xffA\xff\xffB\x00",
                extra_args=["--cpu-mhz", "1", "--baud", "9600"],
                binary=self.wait_test_bin
            )
            # No baud model: file input is ready at once, and once it has
            # ended nothing more can arrive, so the last wait ends at once
            self.run_test(
                "wait_ready: no baud model, file input",
                input_bytes=b"AB",
                expected_output=b"\xffA\xff\xffB\x00",
                binary=self.wait_test_bin
            )

        # Print results
        total = self.passed + self.failed
        print()
        print("=" * 60)
        if self.failed == 0:
            print(f"Results: {Colors.GREEN}{self.passed} passed{Colors.NC} "
                  f"of {total} tests")
        else:
            print(f"Results: {Colors.GREEN}{self.passed} passed{Colors.NC}, "
                  f"{Colors.RED}{self.failed} failed{Colors.NC} "
                  f"of {total} tests")
        print("=" * 60)

        return self.failed == 0


def main():
    parser = argparse.ArgumentParser(description="Terminal mode tests")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show passing tests")
    args = parser.parse_args()

    if not sys.stdout.isatty():
        Colors.disable()

    base_dir = Path(__file__).resolve().parent.parent.parent
    runner = TerminalTestRunner(base_dir, verbose=args.verbose)
    success = runner.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
