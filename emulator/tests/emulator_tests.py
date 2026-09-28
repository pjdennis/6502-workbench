#!/usr/bin/env python3
"""
Test runner for emulator non-core logic.

Tests memory-mapped I/O ports, file handling, argument passing,
and other emulator features outside of core 6502 instruction emulation.

Usage:
    python3 tests/emulator_tests.py [-v] [-f FILTER]
"""

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from persistent_emulator import PersistentEmulator


class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    NC = "\033[0m"

    @classmethod
    def disable(cls):
        cls.RED = cls.GREEN = cls.YELLOW = cls.NC = ""


class EmulatorTestRunner:
    def __init__(self, base_dir: Path, verbose=False, filter_pattern=None):
        self.base_dir = base_dir
        self.verbose = verbose
        self.filter_pattern = filter_pattern
        self.emulator = base_dir / "emulator" / "emulator.out"
        self.assembler = base_dir / "toolchain" / "asm2" / "17" / "out" / "asm.out"
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.emu = None
        self._tmpdir_obj = tempfile.TemporaryDirectory(prefix='emu_tests_')
        self.tmpdir = Path(self._tmpdir_obj.name)

    def _pass(self, name: str):
        self.passed += 1
        if self.verbose:
            print(f"  {Colors.GREEN}PASS{Colors.NC} {name}")

    def _fail(self, name: str, reason: str):
        self.failed += 1
        print(f"  {Colors.RED}FAIL{Colors.NC} {name}: {reason}")

    def _skip(self, name: str, reason: str):
        self.skipped += 1
        if self.verbose:
            print(f"  {Colors.YELLOW}SKIP{Colors.NC} {name}: {reason}")

    def _should_run(self, name: str) -> bool:
        if self.filter_pattern is None:
            return True
        return self.filter_pattern.lower() in name.lower()

    def _assert_eq(self, name: str, actual, expected) -> bool:
        if actual != expected:
            self._fail(name, f"expected {expected!r}, got {actual!r}")
            return False
        self._pass(name)
        return True

    def make_binary(self, instructions, org=0x0400):
        """Build a minimal 6502 binary from raw bytes.

        Appends reset vector (last 2 bytes = org address).
        Returns path to temp binary file.
        """
        code = bytes(instructions)
        code += bytes([org & 0xFF, (org >> 8) & 0xFF])
        path = self.tmpdir / f"test_{self.passed + self.failed}.bin"
        path.write_bytes(code)
        return path

    def _assemble(self, src, dst):
        """Assemble a test program."""
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

    def _get_server(self):
        """Get or create PersistentEmulator instance."""
        if self.emu is None:
            self.emu = PersistentEmulator(self.emulator)
        return self.emu

    def run_server(self, binary, load_addr=0x0400, args=None,
                   mode='standard', rows=0, cols=0, keys=None):
        """Run binary via PersistentEmulator with inline output+stderr capture.

        Returns (exit_code, output_bytes, stderr_bytes).
        """
        emu = self._get_server()
        return emu.run(binary, args=args, load_addr=load_addr, mode=mode,
                       rows=rows, cols=cols, keys=keys,
                       inline_output=True, inline_stderr=True)

    def run_subprocess(self, binary_or_args, extra_args=None, timeout=10):
        """Run emulator as subprocess. Returns subprocess.CompletedProcess."""
        if isinstance(binary_or_args, list):
            cmd = [str(self.emulator)] + binary_or_args
        else:
            cmd = [str(self.emulator), str(binary_or_args),
                   "--no-dump", "--load", "0400"]
            if extra_args:
                cmd.extend(extra_args)
        return subprocess.run(cmd, capture_output=True, timeout=timeout)

    # ---- Exit code tests ----

    def test_exit_code_explicit(self):
        """Writing to port $F003 sets exit code."""
        name = "Exit code via port"
        if not self._should_run(name):
            return
        # LDA #$2A / STA $F003
        binary = self.make_binary([0xA9, 0x2A, 0x8D, 0x03, 0xF0])
        exit_code, _, _ = self.run_server(binary)
        self._assert_eq(name, exit_code, 0x2A)

    def test_exit_code_zero(self):
        """Exit code 0 means clean exit."""
        name = "Exit code zero"
        if not self._should_run(name):
            return
        # LDA #$00 / STA $F003
        binary = self.make_binary([0xA9, 0x00, 0x8D, 0x03, 0xF0])
        exit_code, _, _ = self.run_server(binary)
        self._assert_eq(name, exit_code, 0)

    def test_exit_code_ff(self):
        """Exit code 255 (max byte value)."""
        name = "Exit code 255"
        if not self._should_run(name):
            return
        # LDA #$FF / STA $F003
        binary = self.make_binary([0xA9, 0xFF, 0x8D, 0x03, 0xF0])
        exit_code, _, _ = self.run_server(binary)
        self._assert_eq(name, exit_code, 255)

    def test_cycle_timeout(self):
        """Infinite loop triggers cycle timeout."""
        name = "Cycle timeout"
        if not self._should_run(name):
            return
        # JMP $0400 (infinite loop)
        binary = self.make_binary([0x4C, 0x00, 0x04])
        exit_code, _, _ = self.run_server(binary)
        self._assert_eq(name, exit_code, 1)

    # ---- Stdout/stderr tests ----

    def _make_write_binary(self, port, data_bytes):
        """Build binary that writes data_bytes to a port, then exits 0.

        port: target port address (e.g. 0xF001 for stdout)
        data_bytes: bytes to write
        """
        code = []
        for b in data_bytes:
            code += [0xA9, b,                             # LDA #b
                     0x8D, port & 0xFF, (port >> 8)]      # STA port
        code += [0xA9, 0x00, 0x8D, 0x03, 0xF0]           # LDA #0 / STA $F003
        return self.make_binary(code)

    def test_stdout_single_byte(self):
        """Write one byte to stdout via port $F001."""
        name = "Stdout single byte"
        if not self._should_run(name):
            return
        binary = self._make_write_binary(0xF001, b"A")
        exit_code, output, _ = self.run_server(binary)
        if not self._assert_eq(name, output, b"A"):
            return

    def test_stdout_string(self):
        """Write multiple bytes to stdout."""
        name = "Stdout string"
        if not self._should_run(name):
            return
        binary = self._make_write_binary(0xF001, b"Hello")
        exit_code, output, _ = self.run_server(binary)
        self._assert_eq(name, output, b"Hello")

    def test_stderr_single_byte(self):
        """Write one byte to stderr via port $F002."""
        name = "Stderr single byte"
        if not self._should_run(name):
            return
        binary = self._make_write_binary(0xF002, b"E")
        exit_code, _, stderr = self.run_server(binary)
        self._assert_eq(name, stderr, b"E")

    def test_stdout_and_stderr_separate(self):
        """Stdout and stderr are independent streams."""
        name = "Stdout and stderr separate"
        if not self._should_run(name):
            return
        code = []
        code += [0xA9, ord('O'), 0x8D, 0x01, 0xF0]  # 'O' to stdout
        code += [0xA9, ord('E'), 0x8D, 0x02, 0xF0]  # 'E' to stderr
        code += [0xA9, ord('K'), 0x8D, 0x01, 0xF0]  # 'K' to stdout
        code += [0xA9, 0x00, 0x8D, 0x03, 0xF0]      # exit 0
        binary = self.make_binary(code)
        exit_code, output, stderr = self.run_server(binary)
        if not self._assert_eq(name + " (stdout)", output, b"OK"):
            return
        self._assert_eq(name + " (stderr)", stderr, b"E")

    # ---- File I/O tests ----

    def _build_file_tests(self):
        """Assemble file I/O test programs. Returns True on success."""
        tests_dir = self.base_dir / "emulator" / "tests"
        out_dir = tests_dir / "out"
        programs = [
            ("file_read_test", tests_dir / "file_read_test.asm",
             out_dir / "file_read_test.out"),
            ("file_write_test", tests_dir / "file_write_test.asm",
             out_dir / "file_write_test.out"),
            ("file_unclosed_test", tests_dir / "file_unclosed_test.asm",
             out_dir / "file_unclosed_test.out"),
        ]
        ok = True
        for name, src, dst in programs:
            if not self._assemble(src, dst):
                ok = False
        if ok:
            self.file_read_bin = out_dir / "file_read_test.out"
            self.file_write_bin = out_dir / "file_write_test.out"
            self.file_unclosed_bin = out_dir / "file_unclosed_test.out"
        return ok

    def test_file_read(self):
        """Open file, read all bytes, write to stdout."""
        name = "File read"
        if not self._should_run(name):
            return
        test_file = self.tmpdir / "read_input.txt"
        test_file.write_bytes(b"Hello, file!")
        exit_code, output, _ = self.run_server(
            self.file_read_bin, args=[str(test_file)])
        if exit_code != 0:
            self._fail(name, f"exit code {exit_code}")
            return
        self._assert_eq(name, output, b"Hello, file!")

    def test_file_read_empty(self):
        """Read from empty file produces no output."""
        name = "File read empty"
        if not self._should_run(name):
            return
        test_file = self.tmpdir / "empty.txt"
        test_file.write_bytes(b"")
        exit_code, output, _ = self.run_server(
            self.file_read_bin, args=[str(test_file)])
        if exit_code != 0:
            self._fail(name, f"exit code {exit_code}")
            return
        self._assert_eq(name, output, b"")

    def test_file_read_binary(self):
        """Read file with all byte values 0-255."""
        name = "File read binary"
        if not self._should_run(name):
            return
        # Exclude 0x04 (EOT/Ctrl+D) which is the EOF sentinel
        test_data = bytes(b for b in range(256) if b != 0x04)
        test_file = self.tmpdir / "binary.dat"
        test_file.write_bytes(test_data)
        exit_code, output, _ = self.run_server(
            self.file_read_bin, args=[str(test_file)])
        if exit_code != 0:
            self._fail(name, f"exit code {exit_code}")
            return
        self._assert_eq(name, output, test_data)

    def test_file_write(self):
        """Open file for writing, write bytes, close."""
        name = "File write"
        if not self._should_run(name):
            return
        out_file = self.tmpdir / "write_output.txt"
        exit_code, _, _ = self.run_server(
            self.file_write_bin, args=[str(out_file)],
            keys=b"test data")
        if exit_code != 0:
            self._fail(name, f"exit code {exit_code}")
            return
        self._assert_eq(name, out_file.read_bytes(), b"test data")

    def test_file_unclosed(self):
        """Unclosed file handle reports error on stderr."""
        name = "File unclosed warning"
        if not self._should_run(name):
            return
        test_file = self.tmpdir / "unclosed_input.txt"
        test_file.write_bytes(b"data")
        result = self.run_subprocess(
            self.file_unclosed_bin,
            extra_args=[str(test_file)])
        if b"not closed" not in result.stderr:
            self._fail(name,
                f"expected 'not closed' in stderr, got {result.stderr!r}")
            return
        self._pass(name)

    # ---- Argument passing tests ----

    def _build_args_test(self):
        """Assemble args test program. Returns True on success."""
        tests_dir = self.base_dir / "emulator" / "tests"
        out_dir = tests_dir / "out"
        src = tests_dir / "args_test.asm"
        self.args_test_bin = out_dir / "args_test.out"
        return self._assemble(src, self.args_test_bin)

    def test_argc_zero(self):
        """No args: argc returns 0."""
        name = "Argc zero"
        if not self._should_run(name):
            return
        exit_code, output, _ = self.run_server(self.args_test_bin)
        self._assert_eq(name, output, b"\x00")

    def test_argc_one(self):
        """One arg: argc returns 1."""
        name = "Argc one"
        if not self._should_run(name):
            return
        exit_code, output, _ = self.run_server(
            self.args_test_bin, args=["hello"])
        self._assert_eq(name, output, b"\x01hello\n")

    def test_argc_multiple(self):
        """Multiple args: argc correct, all values accessible."""
        name = "Argc multiple"
        if not self._should_run(name):
            return
        exit_code, output, _ = self.run_server(
            self.args_test_bin, args=["foo", "bar", "baz"])
        self._assert_eq(name, output, b"\x03foo\nbar\nbaz\n")

    def test_argv_spaces(self):
        """Args with spaces are preserved."""
        name = "Argv with spaces"
        if not self._should_run(name):
            return
        exit_code, output, _ = self.run_server(
            self.args_test_bin, args=["hello world"])
        self._assert_eq(name, output, b"\x01hello world\n")

    # ---- Terminal size tests ----

    def _build_term_size_test(self):
        """Assemble term size test program. Returns True on success."""
        tests_dir = self.base_dir / "emulator" / "tests"
        out_dir = tests_dir / "out"
        src = tests_dir / "term_size_test.asm"
        self.term_size_bin = out_dir / "term_size_test.out"
        return self._assemble(src, self.term_size_bin)

    def test_term_size_default(self):
        """Default terminal size is 24x80."""
        name = "Term size default"
        if not self._should_run(name):
            return
        exit_code, output, _ = self.run_server(self.term_size_bin)
        self._assert_eq(name, output, bytes([24, 80]))

    def test_term_rows_override(self):
        """--rows override via server ROWS command."""
        name = "Term rows override"
        if not self._should_run(name):
            return
        exit_code, output, _ = self.run_server(self.term_size_bin, rows=50)
        if len(output) >= 1:
            self._assert_eq(name, output[0], 50)
        else:
            self._fail(name, f"expected 2 bytes, got {output!r}")

    def test_term_cols_override(self):
        """--cols override via server COLS command."""
        name = "Term cols override"
        if not self._should_run(name):
            return
        exit_code, output, _ = self.run_server(self.term_size_bin, cols=120)
        if len(output) >= 2:
            self._assert_eq(name, output[1], 120)
        else:
            self._fail(name, f"expected 2 bytes, got {output!r}")

    def test_term_size_capped(self):
        """Sizes over 255 read as 255 on the byte-wide ports, not mod 256."""
        name = "Term size over 255 capped"
        if not self._should_run(name):
            return
        exit_code, output, _ = self.run_server(self.term_size_bin,
                                               rows=300, cols=256)
        self._assert_eq(name, output, bytes([255, 255]))

    # ---- Stdin read (read_b) tests ----

    def test_stdin_read(self):
        """Read bytes from stdin via read_b port."""
        name = "Stdin read"
        if not self._should_run(name):
            return
        # Build a program that reads stdin bytes and writes them to stdout
        # Uses stubs: read_b ($F006) checks EOF, reads byte; write_b ($F009)
        code = []
        # .loop: JSR $F006 (read_b) / BCS .done / JSR $F009 (write_b) / JMP .loop
        code += [0x20, 0x06, 0xF0]      # JSR read_b
        code += [0xB0, 0x06]             # BCS .done (+6)
        code += [0x20, 0x09, 0xF0]       # JSR write_b
        code += [0x4C, 0x00, 0x04]       # JMP .loop
        # .done: LDA #0 / STA $F003
        code += [0xA9, 0x00, 0x8D, 0x03, 0xF0]
        binary = self.make_binary(code)
        exit_code, output, _ = self.run_server(binary, keys=b"Hello stdin")
        self._assert_eq(name, output, b"Hello stdin")

    # ---- wait_ready tests ----

    def _build_wait_ready_tests(self):
        tests_dir = self.base_dir / "emulator" / "tests"
        out_dir = tests_dir / "out"
        self.wait_ready_bin = out_dir / "wait_ready_test.out"
        self.wait_ready_exit_bin = out_dir / "wait_ready_exit_test.out"
        return (self._assemble(tests_dir / "wait_ready_test.asm",
                               self.wait_ready_bin)
                and self._assemble(tests_dir / "wait_ready_exit_test.asm",
                                   self.wait_ready_exit_bin))

    def _build_direct_io_test(self):
        tests_dir = self.base_dir / "emulator" / "tests"
        self.direct_io_bin = tests_dir / "out" / "direct_io_test.out"
        return self._assemble(tests_dir / "direct_io_test.asm", self.direct_io_bin)

    DIRECT_IO_EXPECTED = b"\x1b[3;17H\x1b[K\x1b[2@\x80q"

    def test_direct_io_subprocess(self):
        """--direct-io: screen calls write their ANSI sequences, and ESC[A is
        read as KEY_UP."""
        name = "direct-io: screen calls and keys (subprocess)"
        if not self._should_run(name):
            return
        keys = self.tmpdir / "direct_keys.bin"
        out = self.tmpdir / "direct_out.bin"
        keys.write_bytes(b"\x1b[Aq")
        result = self.run_subprocess(self.direct_io_bin, extra_args=[
            "--direct-io", "--input", str(keys), "--output", str(out)])
        if result.returncode != 0:
            self._fail(name, f"exit code {result.returncode}: {result.stderr!r}")
            return
        self._assert_eq(name, out.read_bytes(), self.DIRECT_IO_EXPECTED)

    def test_direct_io_server(self):
        name = "direct-io: screen calls and keys (server MODE direct)"
        if not self._should_run(name):
            return
        exit_code, output, _ = self.run_server(self.direct_io_bin, mode='direct', keys=b"\x1b[Aq")
        if exit_code != 0:
            self._fail(name, f"exit code {exit_code}")
            return
        self._assert_eq(name, output, self.DIRECT_IO_EXPECTED)

    def _build_strict_api_test(self):
        tests_dir = self.base_dir / "emulator" / "tests"
        self.strict_api_bin = tests_dir / "out" / "strict_api_test.out"
        return self._assemble(tests_dir / "strict_api_test.asm", self.strict_api_bin)

    # write_b, con_read ('q'), wait_ready (a key ready), scr_cursor_off:
    # each followed by its N V Z C flags, A, X, Y (strict_api_test.asm).
    # The flags a call does not name come back inverted: all four for
    # write_b and con_read, all but N for wait_ready; scr_cursor_off
    # (whose own flags come from its LDA #$FB) changes A and Y
    STRICT_API_EXPECTED = (b"w" + bytes([0xC2]) + b"w\x5a\xa5"
                           + bytes([0xC3]) + b"q\x5a\xa5"
                           + bytes([0xC2, 0xFF, 0x5A, 0xA5])
                           + b"\x1b[?25l" + bytes([0x42, 0xFB, 0x5A, 0x5A]))

    def test_strict_api_subprocess(self):
        """--strict-api: calls keep only what their contract says."""
        name = "strict-api: flags and registers a call does not name change (subprocess)"
        if not self._should_run(name):
            return
        keys = self.tmpdir / "strict_keys.bin"
        out = self.tmpdir / "strict_out.bin"
        keys.write_bytes(b"qr")
        result = self.run_subprocess(self.strict_api_bin, extra_args=[
            "--direct-io", "--strict-api", "--input", str(keys), "--output", str(out)])
        if result.returncode != 0:
            self._fail(name, f"exit code {result.returncode}: {result.stderr!r}")
            return
        self._assert_eq(name, out.read_bytes(), self.STRICT_API_EXPECTED)

    def test_strict_api_server(self):
        name = "strict-api: flags and registers a call does not name change (server)"
        if not self._should_run(name):
            return
        emu = self._get_server()
        exit_code, output, _ = emu.run(self.strict_api_bin, load_addr=0x0400, mode='direct',
                                       strict_api=True, keys=b"qr",
                                       inline_output=True, inline_stderr=True)
        if exit_code != 0:
            self._fail(name, f"exit code {exit_code}")
            return
        self._assert_eq(name, output, self.STRICT_API_EXPECTED)

    # The same program with the standard stubs, which happen to keep more
    STANDARD_API_EXPECTED = (b"w" + bytes([0x01]) + b"w\x5a\xa5"
                             + bytes([0x00]) + b"q\x5a\xa5"
                             + bytes([0x81, 0xFF, 0x5A, 0xA5])
                             + b"\x1b[?25l" + bytes([0x01, 0x04, 0x5A, 0xA5]))

    def test_standard_api_after_strict_server(self):
        """The server rebuilds the stubs when a run leaves --strict-api."""
        name = "strict-api: the server's next standard run has the standard stubs"
        if not self._should_run(name):
            return
        emu = self._get_server()
        exit_code, output, _ = emu.run(self.strict_api_bin, load_addr=0x0400, mode='direct',
                                       keys=b"qr", inline_output=True, inline_stderr=True)
        if exit_code != 0:
            self._fail(name, f"exit code {exit_code}")
            return
        self._assert_eq(name, output, self.STANDARD_API_EXPECTED)

    def test_wait_ready_input_queued(self):
        """With --input every byte is ready at once; once a read has hit the
        end of the input, wait_ready returns CON_EOF. X and Y survive."""
        name = "wait_ready: ready while input is queued, then end of input"
        if not self._should_run(name):
            return
        exit_code, output, _ = self.run_server(self.wait_ready_bin, keys=b"AB")
        if exit_code != 0:
            self._fail(name, f"exit code {exit_code} (1: X or Y changed)")
            return
        self._assert_eq(name, output, b"\xffA\xffB\xff\x00\x01")

    def test_wait_ready_ends_pace_pause(self):
        """During a --pace-mask pause the paced key is not typed yet: a wait
        times out, and the program's next request for input ends the pause
        (the log records the output written by then)."""
        name = "wait_ready: times out in a --pace-mask pause, which then ends"
        if not self._should_run(name):
            return
        keys = self.tmpdir / "wait_keys.bin"
        mask = self.tmpdir / "wait_mask.bin"
        log = self.tmpdir / "wait_pace.log"
        out = self.tmpdir / "wait_out.bin"
        keys.write_bytes(b"AB")
        mask.write_bytes(b"11")
        result = self.run_subprocess(self.wait_ready_bin, extra_args=[
            "--input", str(keys), "--output", str(out),
            "--pace-mask", str(mask), "--pace-log", str(log)])
        if result.returncode != 0:
            self._fail(name, f"exit code {result.returncode}")
            return
        if out.read_bytes() != b"\xffA\x00\xffB\x00\xff\x00\x01":
            self._fail(name, f"output {out.read_bytes()!r}")
            return
        # each pause ends with "<input bytes read> <output bytes written>"
        self._assert_eq(name, log.read_text().splitlines(), ["1 3", "2 6"])

    def _run_console_wait(self, send):
        """Run wait_ready_exit_test (a 200 ms wait) in --console mode with
        stdin on a pipe that stays open, after writing `send` to it.
        Returns (exit code, seconds taken); the exit code is None if the
        program did not finish within 10 s."""
        cmd = [str(self.emulator), str(self.wait_ready_exit_bin),
               "--no-dump", "--load", "0400", "--console"]
        start = time.monotonic()
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        try:
            if send:
                proc.stdin.write(send)
                proc.stdin.flush()
            code = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            code = None
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            proc.stdin.close()
        return code, time.monotonic() - start

    def test_wait_ready_console_timeout(self):
        """In console mode the wait is real time: with no key it returns
        $00 once the 200 ms have passed."""
        name = "wait_ready (console): times out when no key comes"
        if not self._should_run(name):
            return
        code, secs = self._run_console_wait(None)
        if code is None:
            self._fail(name, "did not return within 10 s")
        elif code != 0:
            self._fail(name, f"expected exit code 0 (timed out), got {code}")
        elif secs < 0.2:
            self._fail(name, f"returned after {secs:.3f} s, before the timeout")
        else:
            self._pass(name)

    def test_wait_ready_console_key(self):
        """A key already waiting makes wait_ready return $FF."""
        name = "wait_ready (console): returns $FF when a key is waiting"
        if not self._should_run(name):
            return
        code, _ = self._run_console_wait(b"x")
        self._assert_eq(name, code, 255)

    # ---- CLI argument validation tests ----

    def _cli_test(self, name, args, expect_exit=1, expect_stderr=None):
        """Run emulator with given args, check exit code and stderr."""
        if not self._should_run(name):
            return
        result = subprocess.run(
            [str(self.emulator)] + args,
            capture_output=True, timeout=10)
        if result.returncode != expect_exit:
            self._fail(name,
                f"expected exit {expect_exit}, got {result.returncode}")
            return
        if expect_stderr and expect_stderr not in result.stderr.decode():
            self._fail(name,
                f"expected {expect_stderr!r} in stderr, "
                f"got {result.stderr.decode()!r}")
            return
        self._pass(name)

    def test_cli_no_args(self):
        """No arguments shows usage."""
        self._cli_test("CLI no args", [], expect_stderr="usage:")

    def test_cli_unknown_option(self):
        """Unknown option errors."""
        self._cli_test("CLI unknown option",
            ["/dev/null", "--bogus"], expect_stderr="unknown option")

    def test_cli_console_terminal_exclusive(self):
        """--console and --terminal are mutually exclusive."""
        # Need a real binary file for this to get past file loading
        binary = self.make_binary([0xA9, 0x00, 0x8D, 0x03, 0xF0])
        self._cli_test("CLI console+terminal exclusive",
            [str(binary), "--no-dump", "--load", "0400",
             "--console", "--terminal"],
            expect_stderr="mutually exclusive")

    def test_cli_baud_without_clock(self):
        """--baud without --cpu-mhz or --mhz errors."""
        binary = self.make_binary([0xA9, 0x00, 0x8D, 0x03, 0xF0])
        self._cli_test("CLI baud without clock",
            [str(binary), "--no-dump", "--load", "0400",
             "--terminal", "--baud", "9600"],
            expect_stderr="--baud requires")

    def test_cli_load_missing_value(self):
        """--load without a value errors."""
        self._cli_test("CLI load missing value",
            ["/dev/null", "--load"], expect_stderr="--load requires")

    def test_cli_missing_code_file(self):
        """Non-existent code file errors."""
        self._cli_test("CLI missing code file",
            ["/tmp/nonexistent_6502_binary_xyz"],
            expect_stderr="could not open code file")

    # ---- Test execution ----

    def run_all_tests(self):
        print("=" * 60)
        print("Emulator Test Suite")
        print("=" * 60)

        if not self.emulator.exists():
            print(f"Error: Emulator not found at {self.emulator}")
            return False

        print("\n--- Exit code ---")
        self.test_exit_code_explicit()
        self.test_exit_code_zero()
        self.test_exit_code_ff()
        self.test_cycle_timeout()

        print("\n--- Stdout/stderr ---")
        self.test_stdout_single_byte()
        self.test_stdout_string()
        self.test_stderr_single_byte()
        self.test_stdout_and_stderr_separate()

        if not self.assembler.exists():
            print("\n--- File I/O (skipped: assembler not built) ---")
        elif not self._build_file_tests():
            print("\n--- File I/O (skipped: assembly failed) ---")
        else:
            print("\n--- File I/O ---")
            self.test_file_read()
            self.test_file_read_empty()
            self.test_file_read_binary()
            self.test_file_write()
            self.test_file_unclosed()

            if not self._build_args_test():
                print("\n--- Arguments (skipped: assembly failed) ---")
            else:
                print("\n--- Arguments ---")
                self.test_argc_zero()
                self.test_argc_one()
                self.test_argc_multiple()
                self.test_argv_spaces()

        if not self.assembler.exists():
            print("\n--- Terminal size (skipped: assembler not built) ---")
        elif not self._build_term_size_test():
            print("\n--- Terminal size (skipped: assembly failed) ---")
        else:
            print("\n--- Terminal size ---")
            self.test_term_size_default()
            self.test_term_rows_override()
            self.test_term_cols_override()
            self.test_term_size_capped()

        print("\n--- Stdin read ---")
        self.test_stdin_read()

        print("\n--- wait_ready ---")
        if not self.assembler.exists():
            self._fail("wait_ready tests", "assembler not built")
        elif not self._build_wait_ready_tests():
            self._fail("wait_ready tests", "test programs did not assemble")
        else:
            self.test_wait_ready_input_queued()
            self.test_wait_ready_ends_pace_pause()
            self.test_wait_ready_console_timeout()
            self.test_wait_ready_console_key()

        print("\n--- direct-io ---")
        if not self.assembler.exists():
            self._fail("direct-io tests", "assembler not built")
        elif not self._build_direct_io_test():
            self._fail("direct-io tests", "test program did not assemble")
        else:
            self.test_direct_io_subprocess()
            self.test_direct_io_server()

        print("\n--- strict-api ---")
        if not self.assembler.exists():
            self._fail("strict-api tests", "assembler not built")
        elif not self._build_strict_api_test():
            self._fail("strict-api tests", "test program did not assemble")
        else:
            self.test_strict_api_subprocess()
            self.test_strict_api_server()
            self.test_standard_api_after_strict_server()

        print("\n--- CLI argument validation ---")
        self.test_cli_no_args()
        self.test_cli_unknown_option()
        self.test_cli_console_terminal_exclusive()
        self.test_cli_baud_without_clock()
        self.test_cli_load_missing_value()
        self.test_cli_missing_code_file()

        # Print results
        total = self.passed + self.failed
        print()
        print("=" * 60)
        parts = []
        if self.passed:
            parts.append(f"{Colors.GREEN}{self.passed} passed{Colors.NC}")
        if self.failed:
            parts.append(f"{Colors.RED}{self.failed} failed{Colors.NC}")
        if self.skipped:
            parts.append(f"{Colors.YELLOW}{self.skipped} skipped{Colors.NC}")
        print(f"Results: {', '.join(parts)} of {total} tests")
        print("=" * 60)

        if self.emu:
            self.emu.close()

        return self.failed == 0

    def cleanup(self):
        if self.emu:
            self.emu.close()
        self._tmpdir_obj.cleanup()


def main():
    parser = argparse.ArgumentParser(description="Emulator tests")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show passing tests")
    parser.add_argument("-f", "--filter", type=str, default=None,
                        help="Only run tests matching pattern")
    args = parser.parse_args()

    if not sys.stdout.isatty():
        Colors.disable()

    base_dir = Path(__file__).resolve().parent.parent.parent
    runner = EmulatorTestRunner(base_dir, verbose=args.verbose,
                                filter_pattern=args.filter)
    try:
        success = runner.run_all_tests()
    finally:
        runner.cleanup()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
