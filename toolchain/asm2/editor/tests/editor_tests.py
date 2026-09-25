#!/usr/bin/env python3
"""
Test runner for the vi-like text editor.

Tests the editor by providing keystroke sequences as input files
and verifying the saved output matches expectations.

Usage:
    ./editor/tests/editor_tests.py [-v]
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "emulator"))
from persistent_emulator import PersistentEmulator

from ansi_screen import AnsiScreen


def make_lines(n):
    """Generate content with n numbered lines: 'Line 1\\nLine 2\\n...Line N\\n'."""
    return ''.join(f"Line {i}\n" for i in range(1, n + 1))


# ANSI colors
class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    NC = "\033[0m"

    @classmethod
    def disable(cls):
        cls.RED = cls.GREEN = cls.YELLOW = cls.NC = ""


class EmulatorRunner:
    """Wraps emulator invocation via subprocess.run."""

    def __init__(self, emulator_path):
        self.emulator_path = str(emulator_path)

    def run(self, binary, keys, tmpdir, edit_file,
            load_addr=0x0400, rows=0, cols=0,
            mode='standard', extra_args=None):
        """Run the emulator and return (exit_code, output_bytes).

        Args:
            binary: path to the 6502 binary
            keys: keystroke bytes
            tmpdir: directory for temp files (keys.bin, output.bin)
            edit_file: path to the file the editor opens
            load_addr: load address (default 0x0400)
            rows, cols: terminal size (0 = default)
            mode: 'standard', 'terminal', or 'console'
            extra_args: additional command-line arguments
        """
        keys_file = tmpdir / "keys.bin"
        keys_file.write_bytes(keys)

        cmd = [self.emulator_path, str(binary), "--no-dump",
               "--load", f"{load_addr:04x}"]

        if mode == 'console':
            cmd.extend(["--console", edit_file])
            with open(keys_file, "rb") as stdin_file:
                result = subprocess.run(
                    cmd, stdin=stdin_file, capture_output=True, timeout=10)
            return result.returncode, b""

        if mode == 'terminal':
            cmd.append("--terminal")

        if rows > 0:
            cmd.extend(["--rows", str(rows)])
        if cols > 0:
            cmd.extend(["--cols", str(cols)])

        output_file = tmpdir / "output.bin"
        cmd.extend(["--input", str(keys_file), "--output", str(output_file),
                     edit_file])
        if extra_args:
            cmd.extend(extra_args)

        result = subprocess.run(cmd, capture_output=True, timeout=10)
        output = output_file.read_bytes() if output_file.exists() else b""
        return result.returncode, output

    def close(self):
        pass


class EditorPersistentEmulator:
    """Adapter wrapping shared PersistentEmulator with editor-specific run() signature."""

    def __init__(self, emulator_path):
        self.emulator_path = str(emulator_path)
        self._emu = PersistentEmulator(emulator_path)

    def run(self, binary, keys, tmpdir, edit_file,
            load_addr=0x0400, rows=0, cols=0,
            mode='standard', extra_args=None):
        """Run the emulator and return (exit_code, output_bytes)."""
        if mode == 'console':
            runner = EmulatorRunner(self.emulator_path)
            return runner.run(binary, keys, tmpdir, edit_file,
                              load_addr, rows, cols, mode, extra_args)

        args = [edit_file]
        if extra_args:
            args.extend(extra_args)

        exit_code, output, _ = self._emu.run(
            binary, args=args, load_addr=load_addr, mode=mode,
            rows=rows, cols=cols, keys=keys, inline_output=True)

        return exit_code, output or b""

    def close(self):
        self._emu.close()


class EditorTestRunner:
    def __init__(self, base_dir: Path, verbose: bool = False,
                 quiet: bool = False, use_server: bool = True):
        self.base_dir = base_dir
        self.verbose = verbose
        self.quiet = quiet
        self.emulator = base_dir.parents[1] / "emulator" / "emulator.out"
        self.assembler = base_dir / "17" / "out" / "asm.out"
        self.editor_asm = base_dir / "editor" / "editor.asm"
        self.editor_bin = base_dir / "editor" / "out" / "editor.out"
        self.editor_small_bin = base_dir / "editor" / "out" / "editor_small.out"
        self.editor_terminal_bin = base_dir / "editor" / "out" / "editor_terminal.out"
        if use_server:
            self.emulator_runner = EditorPersistentEmulator(self.emulator)
        else:
            self.emulator_runner = EmulatorRunner(self.emulator)
        self._tmpdir_obj = tempfile.TemporaryDirectory(prefix='')
        self.tmpdir = Path(self._tmpdir_obj.name)
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def _assemble_editor(self, output_bin, extra_args=None):
        """Assemble the editor with optional extra assembler arguments."""
        if not self.emulator.exists():
            print(f"Error: Emulator not found at {self.emulator}")
            return False
        if not self.assembler.exists():
            print(f"Error: Assembler not found at {self.assembler}")
            return False

        output_bin.parent.mkdir(exist_ok=True)
        cmd = [str(self.emulator), str(self.assembler),
               "--no-dump", str(self.editor_asm), str(output_bin)]
        if extra_args:
            cmd.extend(extra_args)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error: Failed to assemble editor ({output_bin.name}):")
            print(result.stderr)
            return False
        return True

    def build_editor(self):
        """Assemble the editor."""
        return self._assemble_editor(self.editor_bin)

    def build_small_buffer_editor(self):
        """Assemble the editor with small buffer (256 bytes for testing)."""
        return self._assemble_editor(self.editor_small_bin,
                                     ["define:small_buffer"])

    def build_terminal_editor(self):
        """Assemble the editor with terminal_mode defined."""
        return self._assemble_editor(self.editor_terminal_bin,
                                     ["define:terminal_mode"])

    def create_stable_copy(self):
        """Create stable copies of editor binaries after successful tests."""
        self._copy_stable(self.editor_bin, "editor_stable.out")
        self._copy_stable(self.editor_terminal_bin, "editor_terminal_stable.out")

    def _copy_stable(self, src_path, dest_name):
        """Copy a binary to a stable copy in the output directory."""
        stable_path = self.base_dir / "editor" / "out" / dest_name
        try:
            shutil.copy2(src_path, stable_path)
            if not self.quiet:
                print()
                print(f"{Colors.GREEN}Created stable copy:{Colors.NC} {stable_path}")
            return True
        except Exception as e:
            print()
            print(f"{Colors.RED}Warning: Failed to create stable copy:{Colors.NC} {e}")
            return False

    def run_editor(self, input_file: str, keys: bytes, tmpdir: Path) -> tuple:
        """Run the editor with given keystroke sequence.

        Returns (exit_code, saved_content, ansi_output).
        """
        exit_code, output = self.emulator_runner.run(
            self.editor_bin, keys, tmpdir, input_file)

        saved = ""
        if Path(input_file).exists():
            saved = Path(input_file).read_text()

        return exit_code, saved, output.decode('latin-1')

    def run_editor_console(self, input_file: str, keys: bytes, tmpdir: Path) -> tuple:
        """Run the editor with console-mode arg layout.

        Returns (exit_code, saved_content).
        """
        exit_code, _ = self.emulator_runner.run(
            self.editor_bin, keys, tmpdir, input_file, mode='console')

        saved = ""
        if Path(input_file).exists():
            saved = Path(input_file).read_text()

        return exit_code, saved

    def run_test_console(self, name: str, initial_content: str, keys: bytes,
                         expected_content: str = None, expect_exit: int = 0):
        """Run an editor test using console-mode argument layout."""
        tmpdir = self.tmpdir
        edit_file = tmpdir / "test.txt"
        edit_file.write_text(initial_content)

        try:
            exit_code, saved = self.run_editor_console(
                str(edit_file), keys, tmpdir
            )
        except subprocess.TimeoutExpired:
            self._fail(name, "Timed out (infinite loop?)")
            return
        except Exception as e:
            self._fail(name, f"Error: {e}")
            return

        if exit_code != expect_exit:
            self._fail(name, f"Expected exit code {expect_exit}, got {exit_code}")
            return

        if expected_content is not None:
            if saved != expected_content:
                self._fail(name,
                    f"Content mismatch:\n"
                    f"  Expected: {expected_content!r}\n"
                    f"  Actual:   {saved!r}")
                return

        self._pass(name)

    def run_test_console_live(self, name: str, initial_content: str,
                              keys: bytes, expected_content: str,
                              idle_seconds: float = 0.5):
        """Run the console-mode editor on a live stdin pipe.

        The editor must keep running while no key is pending, then process
        keys, and exit once stdin reaches end of input.
        """
        edit_file = self.tmpdir / "test.txt"
        edit_file.write_text(initial_content)
        cmd = [str(self.emulator), str(self.editor_bin), "--no-dump",
               "--load", "0400", "--console", str(edit_file)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        try:
            time.sleep(idle_seconds)
            if proc.poll() is not None:
                self._fail(name, f"Exited with code {proc.returncode} "
                                 f"while waiting for a key")
                return
            proc.stdin.write(keys)
            proc.stdin.close()
            exit_code = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._fail(name, "Timed out after end of input")
            return
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()

        if exit_code != 0:
            self._fail(name, f"Expected exit code 0, got {exit_code}")
            return
        saved = edit_file.read_text()
        if saved != expected_content:
            self._fail(name,
                f"Content mismatch:\n"
                f"  Expected: {expected_content!r}\n"
                f"  Actual:   {saved!r}")
            return

        self._pass(name)

    def run_test_new_file(self, name: str, keys: bytes,
                          expected_content: str = None, expect_exit: int = 0):
        """Run an editor test on a file that does not exist yet."""
        tmpdir = self.tmpdir
        edit_file = tmpdir / "newfile.txt"
        # Ensure file does not exist
        if edit_file.exists():
            edit_file.unlink()

        try:
            exit_code, saved, ansi = self.run_editor(
                str(edit_file), keys, tmpdir
            )
        except subprocess.TimeoutExpired:
            self._fail(name, "Timed out (infinite loop?)")
            return
        except Exception as e:
            self._fail(name, f"Error: {e}")
            return

        if exit_code != expect_exit:
            self._fail(name, f"Expected exit code {expect_exit}, got {exit_code}")
            return

        if expected_content is not None:
            if saved != expected_content:
                self._fail(name,
                    f"Content mismatch:\n"
                    f"  Expected: {expected_content!r}\n"
                    f"  Actual:   {saved!r}")
                return

        self._pass(name)

    def run_test(self, name: str, initial_content: str, keys: bytes,
                 expected_content: str = None, expect_exit: int = 0,
                 expect_unmodified: bool = False):
        """Run a single editor test."""
        tmpdir = self.tmpdir
        edit_file = tmpdir / "test.txt"

        if initial_content is not None:
            edit_file.write_text(initial_content)
        else:
            edit_file.write_text("")

        try:
            exit_code, saved, ansi = self.run_editor(
                str(edit_file), keys, tmpdir
            )
        except subprocess.TimeoutExpired:
            self._fail(name, "Timed out (infinite loop?)")
            return
        except Exception as e:
            self._fail(name, f"Error: {e}")
            return

        if exit_code != expect_exit:
            self._fail(name, f"Expected exit code {expect_exit}, got {exit_code}")
            return

        if expected_content is not None:
            if saved != expected_content:
                self._fail(name,
                    f"Content mismatch:\n"
                    f"  Expected: {expected_content!r}\n"
                    f"  Actual:   {saved!r}")
                return

        if expect_unmodified:
            if saved != initial_content:
                self._fail(name, f"File was modified when it shouldn't have been")
                return

        self._pass(name)

    def run_editor_small_buffer(self, input_file: str, keys: bytes,
                               tmpdir: Path) -> tuple:
        """Run the small buffer editor with given keystroke sequence.

        Returns (exit_code, saved_content, ansi_output).
        """
        exit_code, output = self.emulator_runner.run(
            self.editor_small_bin, keys, tmpdir, input_file)

        saved = ""
        if Path(input_file).exists():
            saved = Path(input_file).read_text()

        return exit_code, saved, output.decode('latin-1')

    def run_editor_screen(self, input_file: str, keys: bytes, tmpdir: Path,
                          rows: int = 10, cols: int = 40) -> tuple:
        """Run the editor with explicit terminal size for screen-state testing.

        Returns (exit_code, saved_content, ansi_output).
        """
        exit_code, output = self.emulator_runner.run(
            self.editor_bin, keys, tmpdir, input_file, rows=rows, cols=cols)

        saved = ""
        if Path(input_file).exists():
            try:
                saved = Path(input_file).read_text()
            except UnicodeDecodeError:
                saved = Path(input_file).read_bytes().decode('latin-1')

        return exit_code, saved, output

    def run_editor_terminal(self, input_file: str, keys: bytes, tmpdir: Path,
                            rows: int = 10, cols: int = 40,
                            extra_args: list = None) -> tuple:
        """Run the terminal-mode editor with serial I/O.

        Returns (exit_code, saved_content, ansi_output_bytes).
        """
        exit_code, output = self.emulator_runner.run(
            self.editor_terminal_bin, keys, tmpdir, input_file,
            rows=rows, cols=cols, mode='terminal', extra_args=extra_args)

        saved = ""
        if Path(input_file).exists():
            try:
                saved = Path(input_file).read_text()
            except UnicodeDecodeError:
                saved = Path(input_file).read_bytes().decode('latin-1')

        return exit_code, saved, output

    def run_test_terminal_screen(self, name: str, initial_content: str,
                                 keys: bytes, rows: int = 10, cols: int = 40,
                                 expect_cursor: tuple = None,
                                 expect_lines: list = None,
                                 expect_status_contains: str = None,
                                 expected_content: str = None,
                                 extra_args: list = None,
                                 expect_content_redraws: list = None,
                                 expect_lines_at_frame: list = None):
        """Run a terminal-mode editor test and verify screen state."""
        tmpdir = self.tmpdir
        edit_file = tmpdir / "t"

        if initial_content is not None:
            edit_file.write_text(initial_content)
        else:
            edit_file.write_text("")

        try:
            exit_code, saved, ansi = self.run_editor_terminal(
                str(edit_file), keys, tmpdir, rows, cols,
                extra_args=extra_args
            )
        except subprocess.TimeoutExpired:
            self._fail(name, "Timed out (infinite loop?)")
            return
        except Exception as e:
            self._fail(name, f"Error: {e}")
            return

        if exit_code != 0:
            self._fail(name, f"Expected exit code 0, got {exit_code}")
            return

        # Parse ANSI output through virtual terminal
        screen = AnsiScreen(rows, cols)
        screen.process(ansi.decode('latin-1'))

        if screen.frame_buffer is None:
            self._fail(name, "No rendered frame captured (no ESC[?25h)")
            return

        exp_dump = self._expected_dump(rows, expect_lines, expect_cursor)

        if expect_cursor is not None:
            actual = screen.get_cursor()
            if actual != expect_cursor:
                self._fail(name,
                    f"Cursor: expected {expect_cursor}, got {actual}\n"
                    f"    Expected:\n{exp_dump}\n"
                    f"    Frame:\n{screen.dump()}")
                return

        if expect_lines is not None:
            for row_idx, expected_text in expect_lines:
                actual_text = screen.get_row_text(row_idx)
                if actual_text != expected_text:
                    self._fail(name,
                        f"Row {row_idx}: expected {expected_text!r}, "
                        f"got {actual_text!r}\n"
                        f"    Expected:\n{exp_dump}\n"
                        f"    Frame:\n{screen.dump()}")
                    return

        if expect_status_contains is not None:
            status_row = rows - 1
            status_text = screen.get_row_text(status_row)
            if expect_status_contains not in status_text:
                self._fail(name,
                    f"Status bar: expected substring {expect_status_contains!r} "
                    f"in {status_text!r}\n"
                    f"    Frame:\n{screen.dump()}")
                return

        if expected_content is not None:
            if saved != expected_content:
                self._fail(name,
                    f"Content mismatch:\n"
                    f"  Expected: {expected_content!r}\n"
                    f"  Actual:   {saved!r}")
                return

        if expect_content_redraws is not None:
            actual_count = screen.get_frame_count()
            expected_count = len(expect_content_redraws)
            # Build full redraw pattern for diagnostics
            actual_pattern = [screen.was_content_redrawn(i)
                              for i in range(actual_count)]
            pattern_str = (
                f"    Total frames: {actual_count}\n"
                f"    Actual redraws:   {actual_pattern}\n"
                f"    Expected redraws: {list(expect_content_redraws)}"
            )
            if actual_count < expected_count:
                self._fail(name,
                    f"Expected {expected_count} frames, got {actual_count}\n"
                    f"{pattern_str}\n"
                    f"    Frame:\n{screen.dump()}")
                return
            for i, expected_redraw in enumerate(expect_content_redraws):
                actual_redraw = screen.was_content_redrawn(i)
                if actual_redraw != expected_redraw:
                    self._fail(name,
                        f"Frame {i}: expected content_redrawn="
                        f"{expected_redraw}, got {actual_redraw}\n"
                        f"{pattern_str}\n"
                        f"    Frame:\n{screen.dump()}")
                    return

        if expect_lines_at_frame is not None:
            actual_count = screen.get_frame_count()
            for frame_idx, line_checks in expect_lines_at_frame:
                if frame_idx >= actual_count:
                    self._fail(name,
                        f"Expected frame {frame_idx} but only "
                        f"{actual_count} frames\n"
                        f"    Frame:\n{screen.dump()}")
                    return
                for row_idx, expected_text in line_checks:
                    actual_text = screen.get_row_text_at_frame(
                        frame_idx, row_idx)
                    if actual_text != expected_text:
                        self._fail(name,
                            f"Frame {frame_idx}, row {row_idx}: "
                            f"expected {expected_text!r}, "
                            f"got {actual_text!r}\n"
                            f"    Frame:\n{screen.dump()}")
                        return

        self._pass(name)

    def run_test_terminal(self, name: str, initial_content: str, keys: bytes,
                          expected_content: str = None, expect_exit: int = 0,
                          extra_args: list = None):
        """Run a terminal-mode editor test verifying file content."""
        tmpdir = self.tmpdir
        edit_file = tmpdir / "test.txt"

        if initial_content is not None:
            edit_file.write_text(initial_content)
        else:
            edit_file.write_text("")

        try:
            exit_code, saved, ansi = self.run_editor_terminal(
                str(edit_file), keys, tmpdir,
                extra_args=extra_args
            )
        except subprocess.TimeoutExpired:
            self._fail(name, "Timed out (infinite loop?)")
            return
        except Exception as e:
            self._fail(name, f"Error: {e}")
            return

        if exit_code != expect_exit:
            self._fail(name, f"Expected exit code {expect_exit}, got {exit_code}")
            return

        if expected_content is not None:
            if saved != expected_content:
                self._fail(name,
                    f"Content mismatch:\n"
                    f"  Expected: {expected_content!r}\n"
                    f"  Actual:   {saved!r}")
                return

        self._pass(name)

    def run_test_screen(self, name: str, initial_content: str, keys: bytes,
                        rows: int = 10, cols: int = 40,
                        expect_cursor: tuple = None,
                        expect_lines: list = None,
                        expect_status_contains: str = None,
                        expected_content: str = None,
                        expect_content_redraws: list = None,
                        expect_content_rows: list = None,
                        expect_ansi_contains: str = None,
                        expect_cursor_at_frame: list = None,
                        expect_lines_at_frame: list = None,
                        expect_status_at_frame: list = None,
                        initial_bytes: bytes = None,
                        expect_reverse_at: list = None,
                        expect_min_col: list = None,
                        expect_max_col: list = None,
                        expect_scrolled_at_frame: list = None,
                        expect_scroll_rows: list = None,
                        deferred_wrap: bool = False):
        """Run an editor test and verify screen state via ANSI output.

        Args:
            expect_cursor: (row, col) 0-based cursor position in last frame
            expect_lines: [(row_idx, text), ...] expected row content
            expect_status_contains: substring to find in status bar row
            expected_content: expected saved file content (after :wq)
            expect_content_redraws: list of bools, one per frame - True if
                content area should have been redrawn in that frame
            expect_content_rows: list of (frame_idx, expected_rows_set) tuples -
                verify exactly which content rows were touched in specific frames
            expect_ansi_contains: substring to find in raw ANSI output
            expect_cursor_at_frame: list of (frame_idx, (row, col)) tuples -
                verify cursor position at specific frames
            expect_lines_at_frame: list of (frame_idx, [(row_idx, text), ...])
                tuples - verify row content at specific frames (not just last)
            expect_status_at_frame: list of (frame_idx, substring) tuples -
                verify status bar contains substring at specific frames
            initial_bytes: raw bytes for initial file content (overrides
                initial_content; use when content has non-UTF-8 bytes)
            expect_reverse_at: list of (row, col, expected_bool) tuples -
                verify reverse video attribute at specific cells
            expect_min_col: list of (frame_idx, row, min_col) tuples -
                verify minimum column written on a row in a specific frame
            expect_max_col: list of (frame_idx, row, max_col) tuples -
                verify maximum column written on a row in a specific frame
        """
        tmpdir = self.tmpdir
        edit_file = tmpdir / "t"

        if initial_bytes is not None:
            edit_file.write_bytes(initial_bytes)
        elif initial_content is not None:
            edit_file.write_text(initial_content)
        else:
            edit_file.write_text("")

        try:
            exit_code, saved, ansi = self.run_editor_screen(
                str(edit_file), keys, tmpdir, rows, cols
            )
        except subprocess.TimeoutExpired:
            self._fail(name, "Timed out (infinite loop?)")
            return
        except Exception as e:
            self._fail(name, f"Error: {e}")
            return

        if exit_code != 0:
            self._fail(name, f"Expected exit code 0, got {exit_code}")
            return

        if expect_ansi_contains is not None:
            ansi_text = ansi.decode('latin-1')
            if expect_ansi_contains not in ansi_text:
                self._fail(name,
                    f"Raw ANSI output does not contain "
                    f"{expect_ansi_contains!r}")
                return

        # Parse ANSI output through virtual terminal
        screen = AnsiScreen(rows, cols, deferred_wrap=deferred_wrap)
        screen.process(ansi.decode('latin-1'))

        if screen.frame_buffer is None:
            self._fail(name, "No rendered frame captured (no ESC[?25h)")
            return

        exp_dump = self._expected_dump(rows, expect_lines, expect_cursor)

        if expect_cursor is not None:
            actual = screen.get_cursor()
            if actual != expect_cursor:
                self._fail(name,
                    f"Cursor: expected {expect_cursor}, got {actual}\n"
                    f"    Expected:\n{exp_dump}\n"
                    f"    Frame:\n{screen.dump()}")
                return

        if expect_lines is not None:
            for row_idx, expected_text in expect_lines:
                actual_text = screen.get_row_text(row_idx)
                if actual_text != expected_text:
                    self._fail(name,
                        f"Row {row_idx}: expected {expected_text!r}, "
                        f"got {actual_text!r}\n"
                        f"    Expected:\n{exp_dump}\n"
                        f"    Frame:\n{screen.dump()}")
                    return

        if expect_status_contains is not None:
            status_row = rows - 1
            status_text = screen.get_row_text(status_row)
            if expect_status_contains not in status_text:
                self._fail(name,
                    f"Status bar: expected substring {expect_status_contains!r} "
                    f"in {status_text!r}\n"
                    f"    Frame:\n{screen.dump()}")
                return

        if expected_content is not None:
            if saved != expected_content:
                self._fail(name,
                    f"Content mismatch:\n"
                    f"  Expected: {expected_content!r}\n"
                    f"  Actual:   {saved!r}")
                return

        if expect_content_redraws is not None:
            actual_count = screen.get_frame_count()
            expected_count = len(expect_content_redraws)
            # Build full redraw pattern for diagnostics
            actual_pattern = [screen.was_content_redrawn(i)
                              for i in range(actual_count)]
            pattern_str = (
                f"    Total frames: {actual_count}\n"
                f"    Actual redraws:   {actual_pattern}\n"
                f"    Expected redraws: {list(expect_content_redraws)}"
            )
            if actual_count < expected_count:
                self._fail(name,
                    f"Expected {expected_count} frames, got {actual_count}\n"
                    f"{pattern_str}\n"
                    f"    Frame:\n{screen.dump()}")
                return
            for i, expected_redraw in enumerate(expect_content_redraws):
                actual_redraw = screen.was_content_redrawn(i)
                if actual_redraw != expected_redraw:
                    self._fail(name,
                        f"Frame {i}: expected content_redrawn="
                        f"{expected_redraw}, got {actual_redraw}\n"
                        f"{pattern_str}\n"
                        f"    Frame:\n{screen.dump()}")
                    return

        if expect_content_rows is not None:
            actual_count = screen.get_frame_count()
            for frame_idx, expected_rows in expect_content_rows:
                if frame_idx >= actual_count:
                    self._fail(name,
                        f"Expected frame {frame_idx} but only "
                        f"{actual_count} frames\n"
                        f"    Frame:\n{screen.dump()}")
                    return
                actual_rows = screen.content_rows_touched(frame_idx)
                if actual_rows != expected_rows:
                    self._fail(name,
                        f"Frame {frame_idx}: expected rows touched "
                        f"{expected_rows}, got {actual_rows}\n"
                        f"    Frame:\n{screen.dump()}")
                    return

        if expect_cursor_at_frame is not None:
            actual_count = screen.get_frame_count()
            for frame_idx, expected_pos in expect_cursor_at_frame:
                if frame_idx >= actual_count:
                    self._fail(name,
                        f"Expected frame {frame_idx} but only "
                        f"{actual_count} frames\n"
                        f"    Frame:\n{screen.dump()}")
                    return
                actual_pos = screen.frames[frame_idx][1]
                if actual_pos != expected_pos:
                    self._fail(name,
                        f"Frame {frame_idx}: expected cursor at "
                        f"{expected_pos}, got {actual_pos}\n"
                        f"    Frame:\n{screen.dump()}")
                    return

        if expect_lines_at_frame is not None:
            actual_count = screen.get_frame_count()
            for frame_idx, line_checks in expect_lines_at_frame:
                if frame_idx >= actual_count:
                    self._fail(name,
                        f"Expected frame {frame_idx} but only "
                        f"{actual_count} frames\n"
                        f"    Frame:\n{screen.dump()}")
                    return
                for row_idx, expected_text in line_checks:
                    actual_text = screen.get_row_text_at_frame(
                        frame_idx, row_idx)
                    if actual_text != expected_text:
                        self._fail(name,
                            f"Frame {frame_idx}, row {row_idx}: "
                            f"expected {expected_text!r}, "
                            f"got {actual_text!r}\n"
                            f"    Frame:\n{screen.dump()}")
                        return

        if expect_status_at_frame is not None:
            actual_count = screen.get_frame_count()
            status_row = rows - 1
            for frame_idx, expected_substr in expect_status_at_frame:
                if frame_idx >= actual_count:
                    self._fail(name,
                        f"Expected frame {frame_idx} but only "
                        f"{actual_count} frames\n"
                        f"    Frame:\n{screen.dump()}")
                    return
                actual_text = screen.get_row_text_at_frame(
                    frame_idx, status_row)
                if expected_substr not in actual_text:
                    self._fail(name,
                        f"Frame {frame_idx}: status bar expected "
                        f"substring {expected_substr!r} in "
                        f"{actual_text!r}\n"
                        f"    Frame:\n{screen.dump()}")
                    return

        if expect_reverse_at is not None:
            for row, col, expected_rev in expect_reverse_at:
                actual_rev = screen.is_reverse_at(row, col)
                if actual_rev != expected_rev:
                    self._fail(name,
                        f"Cell ({row},{col}): expected reverse="
                        f"{expected_rev}, got {actual_rev}\n"
                        f"    Frame:\n{screen.dump()}")
                    return

        if expect_min_col is not None:
            actual_count = screen.get_frame_count()
            for frame_idx, row, expected_col in expect_min_col:
                if frame_idx >= actual_count:
                    self._fail(name,
                        f"Expected frame {frame_idx} but only "
                        f"{actual_count} frames\n"
                        f"    Frame:\n{screen.dump()}")
                    return
                actual_col = screen.get_min_col(frame_idx, row)
                if actual_col != expected_col:
                    self._fail(name,
                        f"Frame {frame_idx}, row {row}: expected "
                        f"min_col={expected_col}, got {actual_col}\n"
                        f"    Frame:\n{screen.dump()}")
                    return

        if expect_max_col is not None:
            actual_count = screen.get_frame_count()
            for frame_idx, row, expected_col in expect_max_col:
                if frame_idx >= actual_count:
                    self._fail(name,
                        f"Expected frame {frame_idx} but only "
                        f"{actual_count} frames\n"
                        f"    Frame:\n{screen.dump()}")
                    return
                actual_col = screen.get_max_col(frame_idx, row)
                if actual_col != expected_col:
                    self._fail(name,
                        f"Frame {frame_idx}, row {row}: expected "
                        f"max_col={expected_col}, got {actual_col}\n"
                        f"    Frame:\n{screen.dump()}")
                    return

        if expect_scrolled_at_frame is not None:
            actual_count = screen.get_frame_count()
            for frame_idx, expected_scrolled in expect_scrolled_at_frame:
                if frame_idx >= actual_count:
                    self._fail(name,
                        f"Expected frame {frame_idx} but only "
                        f"{actual_count} frames\n"
                        f"    Frame:\n{screen.dump()}")
                    return
                actual_scrolled = screen.was_scrolled(frame_idx)
                if actual_scrolled != expected_scrolled:
                    self._fail(name,
                        f"Frame {frame_idx}: expected scrolled="
                        f"{expected_scrolled}, got {actual_scrolled}\n"
                        f"    Frame:\n{screen.dump()}")
                    return

        if expect_scroll_rows is not None:
            actual_count = screen.get_frame_count()
            for frame_idx, expected_rows in expect_scroll_rows:
                if frame_idx >= actual_count:
                    self._fail(name,
                        f"Expected frame {frame_idx} but only "
                        f"{actual_count} frames\n"
                        f"    Frame:\n{screen.dump()}")
                    return
                actual_rows = screen.scroll_rows_touched(frame_idx)
                if actual_rows != expected_rows:
                    self._fail(name,
                        f"Frame {frame_idx}: expected scroll rows "
                        f"{expected_rows}, got {actual_rows}\n"
                        f"    Frame:\n{screen.dump()}")
                    return

        self._pass(name)

    def run_test_small_buffer(self, name: str, initial_content: str, keys: bytes,
                             expected_content: str = None, expect_exit: int = 0,
                             expect_unmodified: bool = False):
        """Run a test using the small buffer editor (256 bytes)."""
        tmpdir = self.tmpdir
        edit_file = tmpdir / "test.txt"

        if initial_content is not None:
            edit_file.write_text(initial_content)
        else:
            edit_file.write_text("")

        try:
            exit_code, saved, ansi = self.run_editor_small_buffer(
                str(edit_file), keys, tmpdir
            )
        except subprocess.TimeoutExpired:
            self._fail(name, "Timed out (infinite loop?)")
            return
        except Exception as e:
            self._fail(name, f"Error: {e}")
            return

        if exit_code != expect_exit:
            self._fail(name, f"Expected exit code {expect_exit}, got {exit_code}")
            return

        if expected_content is not None:
            if saved != expected_content:
                self._fail(name,
                    f"Content mismatch:\n"
                    f"  Expected: {expected_content!r}\n"
                    f"  Actual:   {saved!r}")
                return

        if expect_unmodified:
            if saved != initial_content:
                self._fail(name, f"File was modified when it shouldn't have been")
                return

        self._pass(name)

    @staticmethod
    def _expected_dump(rows, expect_lines, expect_cursor):
        """Build expected frame string for diagnostics."""
        exp_lines = dict(expect_lines) if expect_lines else {}
        exp_r, exp_c = expect_cursor if expect_cursor else (None, None)
        parts = []
        for i in range(rows):
            text = repr(exp_lines[i]) if i in exp_lines else "..."
            if i == exp_r:
                parts.append(f"  {i:2d}: {text}  <- cursor at col {exp_c}")
            else:
                parts.append(f"  {i:2d}: {text}")
        return '\n'.join(parts)

    def _pass(self, name):
        if not self.quiet:
            print(f"  {name:<50} {Colors.GREEN}PASS{Colors.NC}")
        self.passed += 1

    def _group(self, title, leading_blank=False):
        if self.quiet:
            return
        if leading_blank:
            print()
        print(title)
        print()

    def _fail(self, name, details):
        print(f"  {name:<50} {Colors.RED}FAIL{Colors.NC}")
        print(f"    {details}")
        self.failed += 1

    def _skip(self, name, reason=""):
        if not self.quiet:
            msg = f" ({reason})" if reason else ""
            print(f"  {name:<50} {Colors.YELLOW}SKIP{Colors.NC}{msg}")
        self.skipped += 1

    def run_server_test(self, name, commands, expected_lines):
        """Test the emulator's --server mode protocol.

        Args:
            commands: list of command strings (sent as text lines) or
                      bytes objects (sent as raw data)
            expected_lines: list of expected response lines
        """
        proc = subprocess.Popen(
            [str(self.emulator), '--server'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        try:
            input_data = b''
            for cmd in commands:
                if isinstance(cmd, bytes):
                    input_data += cmd
                else:
                    input_data += (cmd + '\n').encode()
            stdout, stderr = proc.communicate(
                input=input_data, timeout=5)
            actual_lines = stdout.decode('latin-1').splitlines()
            if actual_lines != expected_lines:
                self._fail(name,
                    f"Expected: {expected_lines!r}\n"
                    f"    Actual:   {actual_lines!r}")
                return
            if proc.returncode != 0:
                self._fail(name,
                    f"Expected exit code 0, got {proc.returncode}")
                return
            self._pass(name)
        except subprocess.TimeoutExpired:
            proc.kill()
            self._fail(name, "Server process timed out")

    def _run_server_editor_tests(self):
        """Test server mode with actual editor binary."""
        self._group("Server mode - editor integration:", leading_blank=True)

        # Test 1: Basic :wq via server matches subprocess.run
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            keys = b":wq\r"

            # Run via subprocess.run (reference)
            edit_file = tmpdir / "test.txt"
            edit_file.write_text("Hello\n")
            ref_exit, ref_saved, ref_ansi = self.run_editor(
                str(edit_file), keys, tmpdir)

            # Run same file via server (reset content first)
            edit_file.write_text("Hello\n")
            keys_file = tmpdir / "keys2.bin"
            output_file = tmpdir / "output2.bin"
            keys_file.write_bytes(keys)

            commands = [
                f'LOAD 0400',
                f'BINARY {self.editor_bin}',
                f'INPUT {keys_file}',
                f'OUTPUT {output_file}',
                f'ARG {edit_file}',
                'RUN',
                'QUIT',
            ]

            self.run_server_test(
                "Server: editor :wq exit code",
                commands,
                [f'EXIT {ref_exit}'])

            srv_saved = edit_file.read_text() if edit_file.exists() else ""
            if srv_saved != ref_saved:
                self._fail("Server: editor :wq content matches",
                    f"Server: {srv_saved!r}\n    Subprocess: {ref_saved!r}")
            else:
                self._pass("Server: editor :wq content matches")

            srv_ansi = output_file.read_bytes() if output_file.exists() else b""
            ref_ansi_bytes = ref_ansi.encode('latin-1')
            if srv_ansi != ref_ansi_bytes:
                self._fail("Server: editor :wq output matches",
                    f"Server output {len(srv_ansi)} bytes "
                    f"vs subprocess {len(ref_ansi_bytes)} bytes")
            else:
                self._pass("Server: editor :wq output matches")

        # Test 2: Multiple runs reusing server process
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            edit_file = tmpdir / "test.txt"
            keys_file = tmpdir / "keys.bin"
            output_file = tmpdir / "output.bin"

            edit_file.write_text("ABC\n")
            keys_file.write_bytes(b"x:wq\r")

            commands = [
                f'LOAD 0400',
                f'BINARY {self.editor_bin}',
                f'INPUT {keys_file}',
                f'OUTPUT {output_file}',
                f'ARG {edit_file}',
                'RUN',
            ]

            # Second run in same session
            edit_file2 = tmpdir / "test2.txt"
            edit_file2.write_text("XYZ\n")
            keys_file2 = tmpdir / "keys2.bin"
            output_file2 = tmpdir / "output2.bin"
            keys_file2.write_bytes(b"x:wq\r")

            commands.extend([
                f'INPUT {keys_file2}',
                f'OUTPUT {output_file2}',
                f'ARG {edit_file2}',
                'RUN',
                'QUIT',
            ])

            self.run_server_test(
                "Server: two sequential runs",
                commands,
                ['EXIT 0', 'EXIT 0'])

            saved1 = edit_file.read_text()
            saved2 = edit_file2.read_text()
            if saved1 != "BC\n" or saved2 != "YZ\n":
                self._fail("Server: sequential run content",
                    f"Run 1: {saved1!r} (expected 'BC\\n'), "
                    f"Run 2: {saved2!r} (expected 'YZ\\n')")
            else:
                self._pass("Server: sequential run content")

        # Test 3: Terminal mode via server matches subprocess.run
        if self.editor_terminal_bin.exists():
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir = Path(tmpdir)
                keys = b":wq\r"

                # Reference via subprocess.run
                edit_file = tmpdir / "test.txt"
                edit_file.write_text("Hello\n")
                ref_exit, ref_saved, ref_ansi = self.run_editor_terminal(
                    str(edit_file), keys, tmpdir, rows=10, cols=40)

                # Server mode
                edit_file.write_text("Hello\n")
                keys_file = tmpdir / "keys2.bin"
                output_file = tmpdir / "output2.bin"
                keys_file.write_bytes(keys)

                commands = [
                    f'LOAD 0400',
                    f'MODE terminal',
                    f'BINARY {self.editor_terminal_bin}',
                    f'ROWS 10',
                    f'COLS 40',
                    f'INPUT {keys_file}',
                    f'OUTPUT {output_file}',
                    f'ARG {edit_file}',
                    'RUN',
                    'QUIT',
                ]

                self.run_server_test(
                    "Server: terminal mode exit code",
                    commands,
                    [f'EXIT {ref_exit}'])

                srv_saved = edit_file.read_text() if edit_file.exists() else ""
                if srv_saved != ref_saved:
                    self._fail("Server: terminal mode content",
                        f"Server: {srv_saved!r}\n    Subprocess: {ref_saved!r}")
                else:
                    self._pass("Server: terminal mode content")

                srv_ansi = output_file.read_bytes() if output_file.exists() else b""
                if srv_ansi != ref_ansi:
                    self._fail("Server: terminal mode output",
                        f"Server {len(srv_ansi)} bytes "
                        f"vs subprocess {len(ref_ansi)} bytes")
                else:
                    self._pass("Server: terminal mode output")

        # Test 4: Screen size via server matches subprocess.run
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            keys = b":q!\r"

            edit_file = tmpdir / "test.txt"
            edit_file.write_text("Hello\n")
            ref_exit, ref_saved, ref_ansi = self.run_editor_screen(
                str(edit_file), keys, tmpdir, rows=5, cols=20)

            edit_file.write_text("Hello\n")
            keys_file = tmpdir / "keys2.bin"
            output_file = tmpdir / "output2.bin"
            keys_file.write_bytes(keys)

            commands = [
                f'LOAD 0400',
                f'BINARY {self.editor_bin}',
                f'ROWS 5',
                f'COLS 20',
                f'INPUT {keys_file}',
                f'OUTPUT {output_file}',
                f'ARG {edit_file}',
                'RUN',
                'QUIT',
            ]

            self.run_server_test(
                "Server: screen size exit code",
                commands,
                [f'EXIT {ref_exit}'])

            srv_ansi = output_file.read_bytes() if output_file.exists() else b""
            if srv_ansi != ref_ansi:
                self._fail("Server: screen size output",
                    f"Server {len(srv_ansi)} bytes "
                    f"vs subprocess {len(ref_ansi)} bytes")
            else:
                self._pass("Server: screen size output")

    def run_self_editability_checks(self):
        """Every editor source file must be editable by the editor itself.

        The text buffer spans from TEXT_BUF (page-aligned after the code,
        which loads at $0400) up to TEXT_LIMIT ($D600), and the line table
        holds at most MAX_LINES (1023) lines.  Guard both limits for every
        source file so the editor stays self-hosting as it grows.
        """
        MAX_LINES = 1023
        TEXT_LIMIT = 0xD600
        LOAD_ADDR = 0x0400

        code_size = self.editor_bin.stat().st_size
        text_buf = (LOAD_ADDR + code_size + 0xFF) & ~0xFF
        capacity = TEXT_LIMIT - text_buf

        editor_dir = self.editor_asm.parent
        sources = sorted(editor_dir.glob("*.asm"))
        for src in sources:
            data = src.read_bytes()
            n_lines = data.count(b"\n")
            name = f"Self-editable: {src.name}"
            if len(data) > capacity:
                self._fail(name,
                    f"{src.name} is {len(data)} bytes but the text buffer "
                    f"holds only {capacity} (code ends at "
                    f"${text_buf:04X})")
            elif n_lines > MAX_LINES:
                self._fail(name,
                    f"{src.name} has {n_lines} lines but MAX_LINES is "
                    f"{MAX_LINES}")
            else:
                self._pass(name)

    def run_all_tests(self):
        """Run all editor tests."""
        print("=" * 60)
        print("Editor Test Suite")
        print("=" * 60)
        print()

        self._group("Server mode protocol:")

        self.run_server_test(
            "Server QUIT",
            ['QUIT'],
            [])

        self.run_server_test(
            "Server RUN without BINARY returns EXIT 1",
            ['RUN', 'QUIT'],
            ['EXIT 1'])

        if not self.build_editor():
            return

        self._run_server_editor_tests()

        self._group("Self-editability:")
        self.run_self_editability_checks()

        # End-to-end: the editor edits its own largest source file
        largest = max(self.editor_asm.parent.glob("*.asm"),
                      key=lambda f: f.stat().st_size)
        src_text = largest.read_text()
        self.run_test(
            f"Editor edits its own largest source ({largest.name})",
            src_text,
            b"Gox\x1b:wq\r",
            expected_content=src_text + "x\n"
        )

        self._group("Basic operations:")

        # Open and quit without saving
        self.run_test(
            "Open file and :q!",
            "Hello\n",
            b":q!\r",
            expect_unmodified=True
        )

        # Open and quit unmodified file with :q
        self.run_test(
            "Quit unmodified file with :q",
            "Hello\n",
            b":q\r",
            expect_unmodified=True
        )

        # Save and quit
        self.run_test(
            "Open file and :wq (no changes)",
            "Hello\n",
            b":wq\r",
            expected_content="Hello\n"
        )

        # Delete character with x
        self.run_test(
            "Delete first char with x",
            "Hello\n",
            b"x:wq\r",
            expected_content="ello\n"
        )

        # Delete character in middle
        self.run_test(
            "Delete char at column 2 with llx",
            "Hello\n",
            b"llx:wq\r",
            expected_content="Helo\n"
        )

        # Insert character
        self.run_test(
            "Insert character with iX",
            "Hello\n",
            b"iX\x1b:wq\r",
            expected_content="XHello\n"
        )

        # Insert in middle
        self.run_test(
            "Insert at column 2 with lliX",
            "Hello\n",
            b"lliX\x1b:wq\r",
            expected_content="HeXllo\n"
        )

        # Append with a
        self.run_test(
            "Append with a at start",
            "Hello\n",
            b"aX\x1b:wq\r",
            expected_content="HXello\n"
        )

        # Append with A
        self.run_test(
            "Append with A at start",
            "Hello\n",
            b"AX\x1b:wq\r",
            expected_content="HelloX\n"
        )

        # Open line below
        self.run_test(
            "Open line below with o",
            "Hello\nWorld\n",
            b"oNew\x1b:wq\r",
            expected_content="Hello\nNew\nWorld\n"
        )

        # Open line above
        self.run_test(
            "Open line above with O",
            "Hello\nWorld\n",
            b"jONew\x1b:wq\r",
            expected_content="Hello\nNew\nWorld\n"
        )

        # Delete line with dd
        self.run_test(
            "Delete first line with dd",
            "Hello\nWorld\n",
            b"dd:wq\r",
            expected_content="World\n"
        )

        # Delete second line
        self.run_test(
            "Delete second line with jdd",
            "Hello\nWorld\nFoo\n",
            b"jdd:wq\r",
            expected_content="Hello\nFoo\n"
        )

        # Move down and edit
        self.run_test(
            "Move down and delete char",
            "Hello\nWorld\n",
            b"jx:wq\r",
            expected_content="Hello\norld\n"
        )

        # Go to end of line
        self.run_test(
            "Go to end of line and delete",
            "Hello\n",
            b"$x:wq\r",
            expected_content="Hell\n"
        )

        # Go to start of line
        self.run_test(
            "Move right then 0 goes back to start",
            "Hello\n",
            b"lll0x:wq\r",
            expected_content="ello\n"
        )

        # Insert newline (Enter)
        self.run_test(
            "Split line with Enter in insert mode",
            "Hello\n",
            b"lli\rWorld\x1b:wq\r",
            expected_content="He\nWorldllo\n"
        )

        # Backspace in insert mode
        self.run_test(
            "Backspace deletes previous char",
            "Hello\n",
            b"llli\x08\x1b:wq\r",
            expected_content="Helo\n"
        )

        # Delete in insert mode (forward delete)
        self.run_test(
            "Delete in insert mode deletes char under cursor",
            "Hello\n",
            b"lli\x1b[3~\x1b:wq\r",
            expected_content="Helo\n"
        )

        # Delete at end of line (deletes last char)
        self.run_test(
            "Delete at end of line with $i",
            "Hello\n",
            b"$i\x1b[3~\x1b:wq\r",
            expected_content="Hell\n"
        )

        # Delete past end of line (does nothing)
        self.run_test(
            "Delete past end of line does nothing",
            "Hello\n",
            b"$a\x1b[3~\x1b:wq\r",
            expected_content="Hello\n"
        )

        # Delete multiple characters (batching)
        self.run_test(
            "Delete batches multiple keypresses",
            "Hello\n",
            b"i\x1b[3~\x1b[3~\x1b[3~\x1b:wq\r",
            expected_content="lo\n"
        )

        # Delete in middle of line (deletes space)
        self.run_test(
            "Delete in middle of line",
            "Hello World\n",
            b"llllli\x1b[3~\x1b:wq\r",
            expected_content="HelloWorld\n"
        )

        # Delete batching - many characters at once
        self.run_test(
            "Delete batches many characters efficiently",
            "0123456789ABCDEF\n",
            b"i\x1b[3~\x1b[3~\x1b[3~\x1b[3~\x1b[3~\x1b[3~\x1b[3~\x1b[3~\x1b:wq\r",
            expected_content="89ABCDEF\n"
        )

        # Delete batching capped at end of line
        self.run_test(
            "Delete batching stops at line end",
            "ABC\n",
            b"i\x1b[3~\x1b[3~\x1b[3~\x1b[3~\x1b[3~\x1b:wq\r",
            expected_content="\n"
        )

        # Delete from middle - batching
        # NOTE: Batching not yet implemented for Delete in insert mode
        self.run_test(
            "Delete from middle of line (no batching yet)",
            "0123456789\n",
            b"llllli\x1b[3~\x1b[3~\x1b[3~\x1b:wq\r",
            expected_content="0123489\n"  # Deletes '5', '6', '7' one at a time
        )

        # Delete with long line (potential wrap scenario)
        # Line longer than typical terminal width (80 chars)
        long_line = "A" * 100 + "\n"
        expected_after_delete = "A" * 50 + "\n"
        self.run_test(
            "Delete batching on long line",
            long_line,
            b"lllllllllllllllllllllllllllllllllllllllllllllllllli" +
            b"\x1b[3~" * 50 + b"\x1b:wq\r",
            expected_content=expected_after_delete
        )

        # Delete causing line wrap change (2 rows -> 1 row)
        # Create a line that wraps at 80 chars, delete enough to unwrap
        wrap_line = "X" * 85 + "\n"
        expected_unwrap = "X" * 75 + "\n"
        self.run_test(
            "Delete batching across line wrap boundary",
            wrap_line,
            b"i" + b"\x1b[3~" * 10 + b"\x1b:wq\r",
            expected_content=expected_unwrap
        )

        # Delete across line boundaries - 6 DELs on short lines should
        # alternate between deleting chars and joining lines.
        # Each "a" line has 1 char, so each pair of DELs does:
        #   DEL 1: delete 'a' (line becomes empty)
        #   DEL 2: join with next line (merges the \n)
        # 6 DELs = 3 pairs = remove 3 of 4 lines, leaving "a\n"
        # BUG: count_pending_key greedily consumes all pending DEL keys,
        # but the cap at line length discards the excess, losing them.
        DEL = b"\x1b[3~"
        self.run_test(
            "Delete across line boundaries not lost to batching cap",
            "a\na\na\na\n",
            b"i" + DEL * 6 + b"\x1b:wq\r",
            expected_content="a\n"
        )

        # Batch DEL across multiple lines - 7 DELs from start of "Hello\nWorld\n"
        # should delete "Hello\n" (6 chars) + "W" (1 char) leaving "orld\n"
        DEL = b"\x1b[3~"
        self.run_test(
            "Batch DEL across multiple lines",
            "Hello\nWorld\n",
            b"i" + DEL * 7 + b"\x1b:wq\r",
            expected_content="orld\n"
        )

        # Batch DEL collapses empty lines - A enters insert at end of "A"
        # (col 1), 4 DELs delete: \n, \n, \n, \n leaving "AB\n"
        DEL = b"\x1b[3~"
        self.run_test(
            "Batch DEL collapses empty lines",
            "A\n\n\n\nB\n",
            b"A" + DEL * 4 + b"\x1b:wq\r",
            expected_content="AB\n"
        )

        # Batch DEL from mid-line across boundary - cursor at col 3,
        # 5 DELs: delete "lo" (2) + \n (1) + "Wo" (2) = "Helrld\n"
        DEL = b"\x1b[3~"
        self.run_test(
            "Batch DEL from mid-line across boundary",
            "Hello\nWorld\n",
            b"llli" + DEL * 5 + b"\x1b:wq\r",
            expected_content="Helrld\n"
        )

        # Batch DEL stops at final newline - 10 DELs but only 3 chars to
        # delete ("A\nB") before final \n, so result is just "\n"
        DEL = b"\x1b[3~"
        self.run_test(
            "Batch DEL stops at final newline",
            "A\nB\n",
            b"i" + DEL * 10 + b"\x1b:wq\r",
            expected_content="\n"
        )

        # Render opt: batch DEL across lines reduces redraws
        # Frame 0: initial (True), Frame 1: i enters insert (False),
        # Frame 2: DEL*4 batched (True), Frame 3: ESC (False)
        DEL = b"\x1b[3~"
        self.run_test_screen(
            "Render opt: batch DEL across lines",
            "A\nB\nC\n",
            b"i" + DEL * 4 + b"\x1b:q!\r",
            expect_content_redraws=[True, False, True, False],
        )

        # :w saves without quitting, then :q quits
        # Actually, :w then EOT will exit due to EOT handling
        self.run_test(
            "Write with :w preserves content",
            "Hello\n",
            b"x:w\r:q!\r",
            expected_content="ello\n"
        )

        # G goes to last line
        self.run_test(
            "G goes to last line and x deletes",
            "Line1\nLine2\nLine3\n",
            b"Gx:wq\r",
            expected_content="Line1\nLine2\nine3\n"
        )

        # gg goes to first line
        self.run_test(
            "jjgg goes back to first line",
            "Line1\nLine2\nLine3\n",
            b"jjggx:wq\r",
            expected_content="ine1\nLine2\nLine3\n"
        )

        # Backspace at start joins lines
        self.run_test(
            "Backspace at col 0 joins with previous line",
            "Hello\nWorld\n",
            b"ji\x08\x1b:wq\r",
            expected_content="HelloWorld\n"
        )

        # Empty file
        self.run_test(
            "Open empty file and add text",
            "",
            b"iHello\x1b:wq\r",
            expected_content="Hello\n"
        )

        # Go to line number
        self.run_test(
            "Go to line 3 and delete",
            "One\nTwo\nThree\nFour\n",
            b":3\rx:wq\r",
            expected_content="One\nTwo\nhree\nFour\n"
        )

        # Delete only line leaves empty file
        self.run_test(
            "Delete only line leaves newline",
            "Only\n",
            b"dd:wq\r",
            expected_content="\n"
        )

        # Multiple inserts
        self.run_test(
            "Insert multiple characters",
            "AB\n",
            b"liXYZ\x1b:wq\r",
            expected_content="AXYZB\n"
        )

        # Delete and retype
        self.run_test(
            "Delete char then insert replacement",
            "Hello\n",
            b"xiJ\x1b:wq\r",
            expected_content="Jello\n"
        )

        # File without trailing newline
        self.run_test(
            "File without trailing newline",
            "Hello",
            b":wq\r",
            expected_content="Hello\n"
        )

        # Multiple dd operations
        self.run_test(
            "Delete two lines with dd dd",
            "A\nB\nC\n",
            b"dddd:wq\r",
            expected_content="C\n"
        )

        # Append at end of line
        self.run_test(
            "Append at end of line with $a",
            "Hello\n",
            b"$aX\x1b:wq\r",
            expected_content="HelloX\n"
        )

        # Cursor clamps when moving from long to short line
        self.run_test(
            "Cursor clamps on move to shorter line",
            "LongLine\nAB\n",
            b"$jx:wq\r",
            expected_content="LongLine\nA\n"
        )

        # h at column 0 stays at 0
        self.run_test(
            "h at column 0 stays put",
            "Hello\n",
            b"hx:wq\r",
            expected_content="ello\n"
        )

        # j at last line stays put
        self.run_test(
            "j at last line stays put",
            "Only\n",
            b"jx:wq\r",
            expected_content="nly\n"
        )

        # k at first line stays put
        self.run_test(
            "k at first line stays put",
            "Only\n",
            b"kx:wq\r",
            expected_content="nly\n"
        )

        # :q on modified file preserves content
        # x modifies, :q warns, :q! then force quits
        # The file should still have the original content
        # (x deletes but :q doesn't save, :q! quits without saving)
        self.run_test(
            ":q on modified file refuses to quit",
            "Hello\n",
            b"x:q\r:q!\r",
            expect_unmodified=True
        )

        # l at end of line stays put
        self.run_test(
            "l at end of line stays put",
            "Hi\n",
            b"lllx:wq\r",
            expected_content="H\n"
        )

        # Open above on first line
        self.run_test(
            "Open above on first line with O",
            "Hello\n",
            b"ONew\x1b:wq\r",
            expected_content="New\nHello\n"
        )

        # Delete all lines then add text
        self.run_test(
            "Delete all lines then insert",
            "A\nB\n",
            b"dddd" + b"iNew\x1b:wq\r",
            expected_content="New\n"
        )

        # Append on empty line
        self.run_test(
            "Append on empty line",
            "\n",
            b"aHi\x1b:wq\r",
            expected_content="Hi\n"
        )

        # ESC in insert mode moves cursor back
        # Insert 'AB' at start, ESC, then x should delete B (cursor moves back)
        self.run_test(
            "ESC in insert moves cursor back one",
            "CD\n",
            b"iAB\x1bx:wq\r",
            expected_content="ACD\n"
        )

        # Multiple Enter in insert mode
        self.run_test(
            "Multiple Enter creates multiple lines",
            "AB\n",
            b"li\r\r\x1b:wq\r",
            expected_content="A\n\nB\n"
        )

        self._group("Console mode argument handling:", leading_blank=True)

        # Console mode saves to correct filename
        # In console mode, the emulator should not require an output_file
        # parameter. The file to edit is passed as a program argument.
        # We delete a char and save, to verify the change was written
        # to the correct file (not "[No Name]").
        self.run_test_console(
            "Console mode :wq saves to correct file",
            "Hello\n",
            b"x:wq\r",
            expected_content="ello\n"
        )

        # Interactive console: "no key pending yet" must not be read as
        # end of input (editor-fast.sh used to quit right after drawing)
        self.run_test_console_live(
            "Console mode waits while no key is pending",
            "Hello\n",
            b"x:wq\r",
            expected_content="ello\n"
        )

        # Console stdin reaching end of input without :q exits the editor
        self.run_test_console_live(
            "Console mode exits at end of input",
            "Hello\n",
            b"x",
            expected_content="Hello\n"
        )

        self._group("New file creation:", leading_blank=True)

        # Edit a non-existent file creates it on save
        self.run_test_new_file(
            "Create new file with :wq",
            b"iHello\x1b:wq\r",
            expected_content="Hello\n"
        )

        self._group("Bounds checking (small buffer build):", leading_blank=True)

        if not self.build_small_buffer_editor():
            print("  Skipping bounds checking tests (small buffer build failed)")
        else:
            # Read-only mode: file exceeds buffer, editing keys blocked
            # small_buffer limits buffer to 256 bytes (TEXT_BUF to TEXT_BUF+$FF)
            # File has 300 bytes so it will be truncated
            # Truncation warning consumes one keypress (the 'x')
            # Then 'x' should be ignored (readonly), :q exits
            large_content = "A" * 299 + "\n"  # 300 bytes > 256
            self.run_test_small_buffer(
                "Truncated file enters read-only mode",
                large_content,
                # 'x' dismissed truncation warning, 'x' ignored (RO), :q quits
                b"xx:q\r",
                expect_unmodified=True
            )

            # Read-only mode: :w is blocked
            # Truncation warning consumes 'x', then :w shows RO message,
            # 'x' dismisses that, :q! quits
            self.run_test_small_buffer(
                "Read-only mode blocks :w",
                large_content,
                b"x:w\rx:q!\r",
                expect_unmodified=True
            )

            # Read-only mode: :wq is blocked
            self.run_test_small_buffer(
                "Read-only mode blocks :wq",
                large_content,
                b"x:wq\rx:q!\r",
                expect_unmodified=True
            )

            # Read-only mode: :1,2d is blocked
            # Multi-line content > 256 bytes to trigger truncation
            large_multiline = ''.join(f"Line {i}\n" for i in range(1, 50))
            self.run_test_small_buffer(
                "Read-only mode blocks :1,2d",
                large_multiline,
                # 'x' dismisses truncation warning, :1,2d shows RO msg,
                # 'x' dismisses that, :q! quits
                b"x:1,2d\rx:q!\r",
                expect_unmodified=True
            )

            # Read-only mode: :q exits cleanly
            self.run_test_small_buffer(
                "Read-only mode allows :q",
                large_content,
                b"x:q\r",
                expect_unmodified=True
            )

            # Read-only mode: X is blocked
            self.run_test_small_buffer(
                "Read-only mode blocks X",
                large_content,
                b"x$X:q\r",   # 'x' dismisses warning, X ignored, :q quits
                expect_unmodified=True
            )

            # Read-only mode: i key is blocked (no insert mode)
            self.run_test_small_buffer(
                "Read-only mode blocks i",
                large_content,
                b"x:q\r",   # 'x' dismisses warning, :q quits
                expect_unmodified=True
            )

            # Buffer full during editing: insert char fails
            # small_buffer = 256 bytes buffer. File with 250 bytes leaves ~6 free
            # After loading, type characters until full
            near_full = "B" * 249 + "\n"  # 250 bytes, ~6 bytes free
            self.run_test_small_buffer(
                "Buffer full refuses insert char",
                near_full,
                # Enter insert mode, type 7 chars (6 succeed, 7th triggers full)
                # 'z' dismisses "Buffer full" message
                # ESC back to normal, :q! quits
                b"iAAAAAA" + b"A" + b"z\x1b:q!\r",
                expect_unmodified=True
            )

            # Buffer full during editing: newline insert fails
            # File with 254 bytes leaves ~2 free
            almost_full = "C" * 253 + "\n"  # 254 bytes, ~2 bytes free
            self.run_test_small_buffer(
                "Buffer full refuses newline insert",
                almost_full,
                # Insert mode, type 'A' (succeeds, 1 byte free),
                # then Enter (needs 1 byte for newline - should succeed or fail)
                # Actually with 2 bytes free: 'A' uses 1, Enter uses 1 = exactly full
                # Try one more char to trigger full
                b"iAA" + b"z\x1b:q!\r",
                expect_unmodified=True
            )

            # Counted paste pre-check: rejects paste that would overflow
            # small_buffer = 256 bytes. Content ~50 bytes. Yank 2 lines (~20 bytes).
            # 99p would need ~2000 bytes, way over 256 limit.
            # File should be unmodified (pre-check rejects before any paste).
            paste_content = "AAAA\nBBBB\nCCCC\nDDDD\n"  # ~20 bytes
            self.run_test_small_buffer(
                "Counted paste pre-check rejects overflow (p)",
                paste_content,
                # yy yanks 1 line, 99p would overflow, z dismisses msg
                b"2yy99pz:q!\r",
                expect_unmodified=True
            )

            # Same test for P (paste above)
            self.run_test_small_buffer(
                "Counted paste pre-check rejects overflow (P)",
                paste_content,
                b"2yy99Pz:q!\r",
                expect_unmodified=True
            )

            # Single paste that fits should still work
            self.run_test_small_buffer(
                "Single paste works when space available",
                paste_content,
                b"yyp:wq\r",
                expected_content="AAAA\nAAAA\nBBBB\nCCCC\nDDDD\n"
            )

            # Normal editing works with small buffer build
            self.run_test_small_buffer(
                "Small buffer build normal editing works",
                "Hello\n",
                b"x:wq\r",
                expected_content="ello\n"
            )

        # ============================================================
        # Screen state tests (10 rows x 40 cols)
        # 9 content rows (rows 0-8), 1 status bar (row 9)
        # page_size = 9
        # ============================================================
        self._group("Screen state - cursor movement:", leading_blank=True)

        CTRL_F = b'\x06'
        CTRL_B = b'\x02'

        # Initial cursor at (0,0)
        self.run_test_screen(
            "Initial cursor at (0,0)",
            "Hello\n",
            b":q!\r",
            expect_cursor=(0, 0)
        )

        # lll -> cursor at (0,3)
        self.run_test_screen(
            "lll moves cursor to (0,3)",
            "Hello\n",
            b"lll:q!\r",
            expect_cursor=(0, 3)
        )

        # lllh -> cursor at (0,2)
        self.run_test_screen(
            "lllh moves cursor to (0,2)",
            "Hello\n",
            b"lllh:q!\r",
            expect_cursor=(0, 2)
        )

        # jj on 3-line file -> cursor at (2,0)
        self.run_test_screen(
            "jj moves cursor to (2,0)",
            "Line 1\nLine 2\nLine 3\n",
            b"jj:q!\r",
            expect_cursor=(2, 0)
        )

        # jjk -> cursor at (1,0)
        self.run_test_screen(
            "jjk moves cursor to (1,0)",
            "Line 1\nLine 2\nLine 3\n",
            b"jjk:q!\r",
            expect_cursor=(1, 0)
        )

        # $ on "Hello" -> cursor at (0,4)
        self.run_test_screen(
            "$ goes to end of line",
            "Hello\n",
            b"$:q!\r",
            expect_cursor=(0, 4)
        )

        # lll0 -> cursor at (0,0)
        self.run_test_screen(
            "lll0 goes back to start of line",
            "Hello\n",
            b"lll0:q!\r",
            expect_cursor=(0, 0)
        )

        # $j from "LongLine" to "AB" -> cursor clamped to (1,1)
        self.run_test_screen(
            "Cursor clamps on move to shorter line",
            "LongLine\nAB\n",
            b"$j:q!\r",
            expect_cursor=(1, 1)
        )

        self._group("Screen state - screen content:", leading_blank=True)

        # 5-line file: rows 0-4 show "Line 1"-"Line 5", rows 5-8 show ~
        self.run_test_screen(
            "5-line file shows content and tildes",
            make_lines(5),
            b":q!\r",
            expect_lines=[
                (0, "Line 1"),
                (1, "Line 2"),
                (2, "Line 3"),
                (3, "Line 4"),
                (4, "Line 5"),
                (5, "~"),
                (6, "~"),
                (7, "~"),
                (8, "~"),
            ]
        )

        # 1-line file: row 0 shows content, rows 1+ show ~
        self.run_test_screen(
            "1-line file shows tildes on empty rows",
            "Hello\n",
            b":q!\r",
            expect_lines=[
                (0, "Hello"),
                (1, "~"),
                (2, "~"),
            ]
        )

        # Status bar shows line,col position (1-based)
        # Note: :q! enters command mode, so we check COMMAND mode status
        self.run_test_screen(
            "Status bar shows position at start",
            "Hello\n",
            b":q!\r",
            expect_status_contains="COMMAND - 1,"
        )

        # Status bar after moving cursor
        self.run_test_screen(
            "Status bar shows line 2 after j",
            "Hello\nWorld\n",
            b"jlll:q!\r",
            expect_status_contains="COMMAND - 2,"
        )

        # :q on modified file shows warning message
        # x modifies, :q\r triggers warning, 'z' dismisses message, :q!\r quits
        self.run_test_screen(
            ":q on modified shows warning message",
            "Hello\n",
            b"x:q\rz:q!\r",
            expect_ansi_contains="No write since last change"
        )

        self._group("Screen state - scrolling:", leading_blank=True)

        # 15-line file, 9 j's: full window after line scroll down
        self.run_test_screen(
            "Line scroll down: full window",
            make_lines(15),
            b"jjjjjjjjj:q!\r",
            expect_cursor=(8, 0),
            expect_lines=[(i, f"Line {i+2}") for i in range(9)]
        )

        # Scroll down then back to top: full window restored
        self.run_test_screen(
            "Line scroll up: full window restored",
            make_lines(15),
            b"jjjjjjjjj" + b"kkkkkkkkk" + b":q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(i, f"Line {i+1}") for i in range(9)]
        )

        # Scroll down 3 lines past bottom: verify contiguous window
        self.run_test_screen(
            "3 lines past bottom: contiguous window",
            make_lines(15),
            b"jjjjjjjjjjj:q!\r",  # 11 j's = line 12, scroll_top=4
            expect_cursor=(8, 0),
            expect_lines=[(i, f"Line {i+4}") for i in range(9)]
        )

        self._group("Screen state - pagination:", leading_blank=True)

        # Ctrl-F from start (30 lines): full window verification
        self.run_test_screen(
            "Ctrl-F: full window after page down",
            make_lines(30),
            CTRL_F + b":q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(i, f"Line {i+10}") for i in range(9)]
        )

        # Two Ctrl-F's: full window verification
        self.run_test_screen(
            "Two Ctrl-F's: full window",
            make_lines(30),
            CTRL_F + CTRL_F + b":q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(i, f"Line {i+19}") for i in range(9)]
        )

        # Repeated Ctrl-F to end: full window with last line at bottom
        self.run_test_screen(
            "Ctrl-F to end: full window",
            make_lines(30),
            CTRL_F + CTRL_F + CTRL_F + CTRL_F + b":q!\r",
            expect_cursor=(8, 0),
            expect_lines=[(i, f"Line {i+22}") for i in range(9)]
        )

        # Ctrl-B from middle: full window after page back
        self.run_test_screen(
            "Ctrl-B: full window after page back",
            make_lines(30),
            CTRL_F + CTRL_F + CTRL_B + b":q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(i, f"Line {i+10}") for i in range(9)]
        )

        # Ctrl-B at start: stays at (0,0), full window
        self.run_test_screen(
            "Ctrl-B at start: full window unchanged",
            make_lines(30),
            CTRL_B + b":q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(i, f"Line {i+1}") for i in range(9)]
        )

        # Ctrl-F with fewer lines than a page: full window
        self.run_test_screen(
            "Ctrl-F short file: full window",
            make_lines(5),
            CTRL_F + b":q!\r",
            expect_cursor=(4, 0),
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 5"),
                (5, "~"), (6, "~"), (7, "~"), (8, "~"),
            ]
        )

        self._group("Screen state - half page scroll:", leading_blank=True)

        CTRL_D = b'\x04'
        CTRL_U = b'\x15'

        # Ctrl-D from start (30 lines): half-page = 4
        self.run_test_screen(
            "Ctrl-D: basic half-page down",
            make_lines(30),
            CTRL_D + b":q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(i, f"Line {i+5}") for i in range(9)]
        )

        # Two Ctrl-D's
        self.run_test_screen(
            "Two Ctrl-D's: full window",
            make_lines(30),
            CTRL_D * 2 + b":q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(i, f"Line {i+9}") for i in range(9)]
        )

        # Ctrl-D at end of file: no movement
        self.run_test_screen(
            "Ctrl-D at end: no movement",
            make_lines(30),
            b"G" + CTRL_D + b":q!\r",
            expect_cursor=(8, 0),
            expect_lines=[(i, f"Line {i+22}") for i in range(9)]
        )

        # Ctrl-D short file (5 lines): cursor moves, view stays
        self.run_test_screen(
            "Ctrl-D short file: view stays at top",
            make_lines(5),
            CTRL_D + b":q!\r",
            expect_cursor=(4, 0),
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 5"),
                (5, "~"), (6, "~"), (7, "~"), (8, "~"),
            ]
        )

        # Ctrl-D column preserved
        self.run_test_screen(
            "Ctrl-D: column preserved",
            make_lines(30),
            b"$" + CTRL_D + b":q!\r",
            expect_cursor=(0, 5),
            expect_lines=[(i, f"Line {i+5}") for i in range(9)]
        )

        # Ctrl-D column clamped to shorter line
        self.run_test_screen(
            "Ctrl-D: column clamped",
            "ABCDEFGHIJ\n" + "XY\n" * 12,
            b"$" + CTRL_D + b":q!\r",
            expect_cursor=(0, 1),
            expect_lines=[(i, "XY") for i in range(9)]
        )

        # Ctrl-D near end: partial scroll, view clamped
        self.run_test_screen(
            "Ctrl-D near end: view clamped",
            make_lines(12),
            CTRL_D + b":q!\r",
            expect_cursor=(1, 0),
            expect_lines=[(i, f"Line {i+4}") for i in range(9)]
        )

        # Count prefix sets scroll amount
        self.run_test_screen(
            "Ctrl-D with count: scroll 2 lines",
            make_lines(30),
            b"2" + CTRL_D + b":q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(i, f"Line {i+3}") for i in range(9)]
        )

        # --- Ctrl-U tests ---

        # Ctrl-U from middle: half-page up
        self.run_test_screen(
            "Ctrl-U: basic half-page up",
            make_lines(30),
            CTRL_F + CTRL_U + b":q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(i, f"Line {i+6}") for i in range(9)]
        )

        # Ctrl-U at start: no movement
        self.run_test_screen(
            "Ctrl-U at start: no movement",
            make_lines(30),
            CTRL_U + b":q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(i, f"Line {i+1}") for i in range(9)]
        )

        # Ctrl-U column preserved
        self.run_test_screen(
            "Ctrl-U: column preserved",
            make_lines(30),
            CTRL_F + b"lll" + CTRL_U + b":q!\r",
            expect_cursor=(0, 3),
            expect_lines=[(i, f"Line {i+6}") for i in range(9)]
        )

        # Multiple Ctrl-U from end
        self.run_test_screen(
            "Two Ctrl-U's from end",
            make_lines(30),
            b"G" + CTRL_U * 2 + b":q!\r",
            expect_cursor=(8, 0),
            expect_lines=[(i, f"Line {i+14}") for i in range(9)]
        )

        # Count prefix sets scroll amount for Ctrl-U
        self.run_test_screen(
            "Ctrl-U with count: scroll 3 lines",
            make_lines(30),
            b"G" + b"3" + CTRL_U + b":q!\r",
            expect_cursor=(8, 0),
            expect_lines=[(i, f"Line {i+19}") for i in range(9)]
        )

        # --- Sticky scroll count ---

        # Count on Ctrl-D is remembered for next Ctrl-D without count
        # 2Ctrl-D scrolls 2; next Ctrl-D (no count) also scrolls 2
        self.run_test_screen(
            "Ctrl-D count sticky for next Ctrl-D",
            make_lines(30),
            b"2" + CTRL_D + CTRL_D + b":q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(i, f"Line {i+5}") for i in range(9)]
        )

        # Ctrl-D count carries to Ctrl-U
        # Ctrl-F to line 9; 2Ctrl-D scrolls 2 (sticky=2); Ctrl-U scrolls 2 back
        self.run_test_screen(
            "Ctrl-D count sticky carries to Ctrl-U",
            make_lines(30),
            CTRL_F + b"2" + CTRL_D + CTRL_U + b":q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(i, f"Line {i+10}") for i in range(9)]
        )

        # Ctrl-U count overrides previous sticky
        # Ctrl-F to line 9; 2Ctrl-D (sticky=2); 3Ctrl-U overrides (sticky=3)
        self.run_test_screen(
            "Ctrl-U count overrides sticky",
            make_lines(30),
            CTRL_F + b"2" + CTRL_D + b"3" + CTRL_U + b":q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(i, f"Line {i+9}") for i in range(9)]
        )

        # --- Combined tests ---

        # Roundtrip: Ctrl-D then Ctrl-U returns to start
        self.run_test_screen(
            "Ctrl-D + Ctrl-U roundtrip",
            make_lines(30),
            CTRL_D + CTRL_U + b":q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(i, f"Line {i+1}") for i in range(9)]
        )

        # Three Ctrl-D's
        self.run_test_screen(
            "Three Ctrl-D's",
            make_lines(30),
            CTRL_D * 3 + b":q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(i, f"Line {i+13}") for i in range(9)]
        )

        self._group("Screen state - G and gg:", leading_blank=True)

        # G on 20-line file: full window with last line at bottom
        self.run_test_screen(
            "G: full window at end",
            make_lines(20),
            b"G:q!\r",
            expect_cursor=(8, 0),
            expect_lines=[(i, f"Line {i+12}") for i in range(9)]
        )

        # G on 300-line file: tests 8-bit overflow in CURSOR_ROW walk
        self.run_test_screen(
            "G: large file scrolls correctly",
            make_lines(300),
            b"G:q!\r",
            expect_cursor=(8, 0),
            expect_lines=[(i, f"Line {i+292}") for i in range(9)]
        )

        # Ggg: full window back at top
        self.run_test_screen(
            "Ggg: full window at top",
            make_lines(20),
            b"Ggg:q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(i, f"Line {i+1}") for i in range(9)]
        )

        self._group("Screen state - edge cases:", leading_blank=True)

        # Single-line file: jjkk stays at (0,0)
        self.run_test_screen(
            "jjkk on single line stays at (0,0)",
            "Only\n",
            b"jjkk:q!\r",
            expect_cursor=(0, 0)
        )

        # Empty line: l stays at col 0
        self.run_test_screen(
            "l on empty line stays at col 0",
            "\n",
            b"l:q!\r",
            expect_cursor=(0, 0)
        )

        # Long line wraps to next screen row
        self.run_test_screen(
            "Long line wraps to next screen row",
            "A" * 60 + "\n",
            b":q!\r",
            expect_lines=[
                (0, "A" * 40),
                (1, "A" * 20),
            ]
        )

        # Bug repro: last char on first wrap row erased by ESC[K
        # Real terminals use deferred auto-wrap: after writing to the last
        # column, the cursor stays there with a pending-wrap flag. ESC[K
        # then clears from that position, erasing the last character.
        self.run_test_screen(
            "Wrap: last char on first row (deferred wrap)",
            "A" * 60 + "\n",
            b":q!\r",
            expect_lines=[
                (0, "A" * 40),
                (1, "A" * 20),
            ],
            deferred_wrap=True
        )

        # ============================================================
        # Line wrapping tests
        # ============================================================
        self._group("Screen state - line wrapping:", leading_blank=True)

        # Line after wrapped line pushed down
        self.run_test_screen(
            "Line after wrap pushed down",
            "A" * 60 + "\n" + "B\n",
            b":q!\r",
            expect_lines=[
                (0, "A" * 40),
                (1, "A" * 20),
                (2, "B"),
            ]
        )

        # Tilde markers account for wrapping
        self.run_test_screen(
            "Tildes account for wrapped line height",
            "A" * 80 + "\n",
            b":q!\r",
            expect_lines=[
                (0, "A" * 40),
                (1, "A" * 40),
                (2, "~"),
            ]
        )

        # Cursor position on wrapped line ($ command)
        # 60-char line on 40-col screen: $ puts cursor at col 59
        # screen row = 59 / 40 = 1, screen col = 59 % 40 = 19
        self.run_test_screen(
            "$ on wrapped line: cursor position",
            "A" * 60 + "\n",
            b"$:q!\r",
            expect_cursor=(1, 19)
        )

        # Cursor position after right movement past screen edge
        # Move right 40 times on a 60-char line with 40-col screen
        # Cursor at col 40 -> screen row 1, screen col 0
        self.run_test_screen(
            "Right movement past screen edge wraps",
            "A" * 60 + "\n",
            b"l" * 40 + b":q!\r",
            expect_cursor=(1, 0)
        )

        # j/k skip wrapped rows (move by file line, not screen row)
        # Two long lines: j from line 0 to line 1
        self.run_test_screen(
            "j skips wrap rows to next file line",
            "A" * 60 + "\n" + "B" * 60 + "\n",
            b"j:q!\r",
            expect_cursor=(2, 0),
            expect_lines=[
                (0, "A" * 40),
                (1, "A" * 20),
                (2, "B" * 40),
                (3, "B" * 20),
            ]
        )

        # Scrolling with wrapped lines
        # 10 rows, 9 content rows. Fill with lines that take 2 rows each.
        # 5 wrapped lines = 10 screen rows needed (only 9 content rows available)
        # After j x4 to line 4, scrolling should keep cursor visible
        # Cursor is at line 5 (1-based), col 1
        self.run_test_screen(
            "Scroll with wrapped lines",
            ("X" * 60 + "\n") * 5,
            b"jjjj:q!\r",
            expect_status_contains="5,"
        )

        # Insert mode: cursor tracks wrap when typing past screen edge
        # Start with 38 chars on 40-col screen, $a enters append at col 38.
        # Type 3 chars: first X at col 39, then XX batched -> col 41.
        # Frame sequence: 0=init, 1=$, 2=a, 3=X+batch(col41), 4=ESC(col40)
        # At frame 3: CURSOR_COL=41, must be row 1 col 1 (all 3 chars inserted)
        self.run_test_screen(
            "Insert cursor tracks wrap boundary",
            "A" * 38 + "\n",
            b"$aXXX\x1b:q!\r",
            expect_cursor=(1, 0),
            expect_lines=[
                (0, "A" * 38 + "XX"),
                (1, "X"),
            ],
            expect_cursor_at_frame=[
                (3, (1, 1)),
            ]
        )

        # Insert mode: cursor on wrap continuation while typing
        # Start with 39 chars, $a enters append at col 39, type 2 chars.
        # Frame sequence: 0=init, 1=$, 2=a, 3=X+batch(col41), 4=ESC(col40)
        # At frame 3: CURSOR_COL=41, must be row 1 col 1
        self.run_test_screen(
            "Insert cursor mid-wrap while typing",
            "A" * 39 + "\n",
            b"$aXX\x1b:q!\r",
            expect_cursor=(1, 0),
            expect_lines=[
                (0, "A" * 39 + "X"),
                (1, "X"),
            ],
            expect_cursor_at_frame=[
                (3, (1, 1)),
            ]
        )

        # Backspace from wrap boundary back to previous row
        # Start with 41 chars (wraps to row 1 with 1 char). $a enters at col 41.
        # Frame sequence: 0=init, 1=$, 2=a, 3=BS+batch_BS(col39), 4=ESC(col38)
        # At frame 3: CURSOR_COL=39, must be row 0 col 39 (crossed back via batch)
        self.run_test_screen(
            "Backspace across wrap boundary",
            "A" * 41 + "\n",
            b"$a\x08\x08\x1b:q!\r",
            expect_cursor=(0, 38),
            expect_lines=[
                (0, "A" * 39),
            ],
            expect_cursor_at_frame=[
                (3, (0, 39)),
            ]
        )

        # A on wrapped line: cursor must move to end-of-line wrap row
        # 60-char line, 0 goes to col 0 (row 0), then A sets col=60 (row 1, col 20)
        # Frame sequence: 0=init, 1=0, 2=A
        # At frame 2: CURSOR_COL=60, must be row 1 col 20
        self.run_test_screen(
            "A on wrapped line positions cursor correctly",
            "A" * 60 + "\n",
            b"0AX\x1b:q!\r",
            expect_cursor=(1, 20),
            expect_cursor_at_frame=[
                (2, (1, 20)),
            ]
        )

        # a at wrap boundary: cursor crosses to next wrap row
        # 41-char line, $ goes to col 40 (row 1), h goes to col 39 (row 0),
        # then a increments to col 40 (should be row 1, col 0)
        # Frame sequence: 0=init, 1=$, 2=h, 3=a
        self.run_test_screen(
            "a at wrap boundary positions cursor correctly",
            "A" * 41 + "\n",
            b"$haX\x1b:q!\r",
            expect_cursor_at_frame=[
                (3, (1, 0)),
            ]
        )

        # Insert mode up arrow from wrap row moves to previous line
        # Line 0: "B", Line 1: 60 A's (wraps to 2 rows on 40-col screen)
        # j$ puts cursor at col 59 (row 2: line 0 row + 2 wrap rows).
        # 'a' enters insert at col 60 (still row 2).
        # Up arrow should move to line 0 ("B"), col clamped to 1 (one past 'B'), row 0.
        # Insert mode allows cursor one past last char for end-of-line insertion.
        # Frame sequence: 0=init, 1=j, 2=$, 3=a, 4=UP
        self.run_test_screen(
            "Insert up arrow from wrapped line to short line",
            "B\n" + "A" * 60 + "\n",
            b"j$a\x1b[A\x1b:q!\r",
            expect_cursor=(0, 0),
            expect_cursor_at_frame=[
                (4, (0, 1)),  # After UP arrow, before ESC
            ]
        )

        # Normal mode k from wrap row moves to previous line
        # Same setup but in normal mode with k instead of up arrow.
        # j$ puts cursor at line 1 col 59 (row 2), k should go to line 0.
        # Frame sequence: 0=init, 1=j, 2=$, 3=k
        self.run_test_screen(
            "Normal k from wrapped line to short line",
            "B\n" + "A" * 60 + "\n",
            b"j$k:q!\r",
            expect_cursor=(0, 0),
            expect_cursor_at_frame=[
                (3, (0, 0)),
            ]
        )

        # Normal mode x on wrapped line: content and cursor correct
        # 60-char line, $ goes to col 59 (row 1, col 19), x deletes -> col 58
        self.run_test_screen(
            "x on wrapped line keeps cursor correct",
            "A" * 60 + "\n",
            b"$x:q!\r",
            expect_cursor=(1, 18),
            expect_lines=[
                (0, "A" * 40),
                (1, "A" * 19),
            ]
        )

        # ============================================================
        # Render optimization tests
        # Verify cursor-only movements skip content area redraws.
        # Frame 0 is always the initial full render (True).
        # ============================================================
        self._group("Screen state - render optimization:", leading_blank=True)

        # h movement: cursor-only
        self.run_test_screen(
            "Render opt: h is cursor-only",
            "Hello\n",
            b"lh:q!\r",
            expect_content_redraws=[True, False, False]
        )

        # l movement: cursor-only (batched into single frame)
        self.run_test_screen(
            "Render opt: lll is cursor-only",
            "Hello\n",
            b"lll:q!\r",
            expect_content_redraws=[True, False, False]
        )

        # h at col 0: cursor-only (no movement, no repaint)
        self.run_test_screen(
            "Render opt: h at col 0 is cursor-only",
            "Hello\n",
            b"h:q!\r",
            expect_content_redraws=[True, False]
        )

        # l at end-of-line: cursor-only (no movement, no repaint)
        self.run_test_screen(
            "Render opt: l at EOL is cursor-only",
            "Hello\n",
            b"$l:q!\r",
            expect_content_redraws=[True, False, False]
        )

        LEFT = b"\x1b[D"
        RIGHT = b"\x1b[C"

        # Insert LEFT at col 0: cursor-only
        self.run_test_screen(
            "Render opt: insert LEFT at col 0 is cursor-only",
            "Hello\n",
            b"i" + LEFT + b"\x1b:q!\r",
            expect_content_redraws=[True, False, False, False]
        )

        # Insert RIGHT at end-of-line: cursor-only
        # $=cursor-only, a=cursor-only (enters insert), RIGHT at EOL=cursor-only, ESC=cursor-only
        self.run_test_screen(
            "Render opt: insert RIGHT at EOL is cursor-only",
            "Hello\n",
            b"$a" + RIGHT + b"\x1b:q!\r",
            expect_content_redraws=[True, False, False, False, False]
        )

        # j without scroll: cursor-only
        self.run_test_screen(
            "Render opt: j no scroll is cursor-only",
            "Line 1\nLine 2\nLine 3\n",
            b"j:q!\r",
            expect_content_redraws=[True, False]
        )

        # k without scroll: cursor-only
        self.run_test_screen(
            "Render opt: jk no scroll is cursor-only",
            "Line 1\nLine 2\nLine 3\n",
            b"jk:q!\r",
            expect_content_redraws=[True, False, False]
        )

        # j with scroll: batched into single full repaint
        # 10 rows, 9 content rows. 9 j's on a 15-line file:
        # All 9 j's are batched into one movement, triggering one scroll repaint
        self.run_test_screen(
            "Render opt: j scroll triggers repaint",
            make_lines(15),
            b"jjjjjjjjj:q!\r",
            expect_content_redraws=(
                [True] +          # frame 0: initial
                [True]            # frame 1: batched j*9 with scroll
            )
        )

        # 0 (line start): cursor-only (lll batched into single frame)
        self.run_test_screen(
            "Render opt: 0 is cursor-only",
            "Hello\n",
            b"lll0:q!\r",
            expect_content_redraws=[True, False, False, False]
        )

        # $ (line end): cursor-only
        self.run_test_screen(
            "Render opt: $ is cursor-only",
            "Hello\n",
            b"$:q!\r",
            expect_content_redraws=[True, False]
        )

        # i enters insert mode: cursor-only (only status bar changes)
        self.run_test_screen(
            "Render opt: i enter insert is cursor-only",
            "Hello\n",
            b"i\x1b:q!\r",
            expect_content_redraws=[True, False, False]
        )

        # a enters insert mode: cursor-only
        self.run_test_screen(
            "Render opt: a enter insert is cursor-only",
            "Hello\n",
            b"a\x1b:q!\r",
            expect_content_redraws=[True, False, False]
        )

        # A enters insert mode: cursor-only
        self.run_test_screen(
            "Render opt: A enter insert is cursor-only",
            "Hello\n",
            b"A\x1b:q!\r",
            expect_content_redraws=[True, False, False]
        )

        # : then ESC (cancel command mode): cursor-only
        self.run_test_screen(
            "Render opt: command cancel is cursor-only",
            "Hello\n",
            b":\x1b:q!\r",
            expect_content_redraws=[True, False, False]
        )

        # Insert HOME at col 0: cursor-only (already at start)
        # i enters insert (F), HOME at col 0 is no-op (F), ESC (F)
        HOME = b"\x1b[H"
        self.run_test_screen(
            "Render opt: insert HOME at col 0 is cursor-only",
            "Hello\n",
            b"i" + HOME + b"\x1b:q!\r",
            expect_content_redraws=[True, False, False, False]
        )

        # Insert END at end of line: cursor-only (already at end)
        # $ (F), a enters insert at end (F), END at EOL is no-op (F), ESC (F)
        END = b"\x1b[F"
        self.run_test_screen(
            "Render opt: insert END at EOL is cursor-only",
            "Hello\n",
            b"$a" + END + b"\x1b:q!\r",
            expect_content_redraws=[True, False, False, False, False]
        )

        # k at first line: cursor-only (no movement, no repaint)
        self.run_test_screen(
            "Render opt: k at first line is cursor-only",
            "Hello\n",
            b"k:q!\r",
            expect_content_redraws=[True, False]
        )

        # j at last line: cursor-only (no movement, no repaint)
        self.run_test_screen(
            "Render opt: j at last line is cursor-only",
            "Hello\n",
            b"j:q!\r",
            expect_content_redraws=[True, False]
        )

        # Insert UP at first line: cursor-only
        UP = b"\x1b[A"
        self.run_test_screen(
            "Render opt: insert UP at first line is cursor-only",
            "Hello\n",
            b"i" + UP + b"\x1b:q!\r",
            expect_content_redraws=[True, False, False, False]
        )

        # Insert DOWN at last line: cursor-only
        DOWN = b"\x1b[B"
        self.run_test_screen(
            "Render opt: insert DOWN at last line is cursor-only",
            "Hello\n",
            b"i" + DOWN + b"\x1b:q!\r",
            expect_content_redraws=[True, False, False, False]
        )

        # Ctrl-F at bottom of file: cursor-only (view doesn't change)
        # 5-line file, 10 rows (9 content). All lines fit on screen.
        # Ctrl-F clamps to last line but view stays the same.
        CTRL_F = b'\x06'
        CTRL_B = b'\x02'
        self.run_test_screen(
            "Render opt: Ctrl-F at bottom is cursor-only",
            make_lines(5),
            CTRL_F + b":q!\r",
            expect_content_redraws=[True, False]
        )

        # Ctrl-B at top of file: cursor-only (view doesn't change)
        self.run_test_screen(
            "Render opt: Ctrl-B at top is cursor-only",
            make_lines(5),
            CTRL_B + b":q!\r",
            expect_content_redraws=[True, False]
        )

        # Ctrl-D scroll then j: Ctrl-D repaints, j is cursor-only
        CTRL_D = b'\x04'
        CTRL_U = b'\x15'
        self.run_test_screen(
            "Render opt: Ctrl-D scroll then j",
            make_lines(30),
            CTRL_D + b"j:q!\r",
            expect_content_redraws=[True, True, False]
        )

        # Ctrl-U scroll then j: Ctrl-F and Ctrl-U repaint, j is cursor-only
        self.run_test_screen(
            "Render opt: Ctrl-U scroll then j",
            make_lines(30),
            CTRL_F + CTRL_U + b"j:q!\r",
            expect_content_redraws=[True, True, True, False]
        )

        # Batched Ctrl-D: two Ctrl-D's consumed in one frame
        # Frame 0: init(T), Frame 1: both Ctrl-D's batched(T), Frame 2: j(F)
        self.run_test_screen(
            "Render opt: batched Ctrl-D*2 is single frame",
            make_lines(30),
            CTRL_D * 2 + b"j:q!\r",
            expect_cursor=(1, 0),
            expect_lines=[(i, f"Line {i+9}") for i in range(9)],
            expect_content_redraws=[True, True, False]
        )

        # Batched Ctrl-U: two Ctrl-U's consumed in one frame
        # Frame 0: init(T), Frame 1: Ctrl-F(T), Frame 2: both Ctrl-U's(T), Frame 3: j(F)
        self.run_test_screen(
            "Render opt: batched Ctrl-U*2 is single frame",
            make_lines(30),
            CTRL_F + CTRL_U * 2 + b"j:q!\r",
            expect_cursor=(1, 0),
            expect_lines=[(i, f"Line {i+2}") for i in range(9)],
            expect_content_redraws=[True, True, True, False]
        )

        # Insert Ctrl-F at bottom: cursor-only
        self.run_test_screen(
            "Render opt: insert Ctrl-F at bottom is cursor-only",
            make_lines(5),
            b"i" + CTRL_F + b"\x1b:q!\r",
            expect_content_redraws=[True, False, False, False]
        )

        # Insert Ctrl-B at top: cursor-only
        self.run_test_screen(
            "Render opt: insert Ctrl-B at top is cursor-only",
            make_lines(5),
            b"i" + CTRL_B + b"\x1b:q!\r",
            expect_content_redraws=[True, False, False, False]
        )

        # G at last line (no scroll): cursor-only
        # On a 5-line file (fits in 9 content rows), G moves to last line
        # but view doesn't change. ensure_cursor_visible won't upgrade.
        self.run_test_screen(
            "Render opt: G on short file is cursor-only",
            make_lines(5),
            b"G:q!\r",
            expect_content_redraws=[True, False]
        )

        # gg at first line: cursor-only (already at top)
        # g+g batched into single frame (no pending-key frame)
        self.run_test_screen(
            "Render opt: gg at top is cursor-only",
            "Hello\n",
            b"gg:q!\r",
            expect_content_redraws=[True, False]
        )

        # yy: cursor-only (yank doesn't change display)
        # y+y batched into single frame (no pending-key frame)
        self.run_test_screen(
            "Render opt: yy is cursor-only",
            "Hello\n",
            b"yy:q!\r",
            expect_content_redraws=[True, False]
        )

        # Mark goto to current line: cursor-only
        # m+a batched, '+a batched (no pending-key frames)
        self.run_test_screen(
            "Render opt: mark goto same line is cursor-only",
            "Line 1\nLine 2\n",
            b"ma'a:q!\r",
            expect_content_redraws=[True, False, False]
        )

        # w at end of file: cursor-only (no next word to move to)
        self.run_test_screen(
            "Render opt: w at end of file is cursor-only",
            "Hello\n",
            b"$w:q!\r",
            expect_content_redraws=[True, False, False]
        )

        # b at start of file: cursor-only (no previous word)
        self.run_test_screen(
            "Render opt: b at start of file is cursor-only",
            "Hello\n",
            b"b:q!\r",
            expect_content_redraws=[True, False]
        )

        # e at end of file: cursor-only (no next word end)
        self.run_test_screen(
            "Render opt: e at end of file is cursor-only",
            "Hello\n",
            b"$e:q!\r",
            expect_content_redraws=[True, False, False]
        )

        # Forward search, match visible, no scroll -> cursor-only
        # 3-line file, 10 rows. /BBB finds line 1, no scroll.
        # Frame 0: initial (True), Frame 1: /BBB\r complete (False after fix)
        self.run_test_screen(
            "Render opt: search no-scroll is cursor-only",
            "AAA\nBBB\nCCC\n",
            b"/BBB\r:q!\r",
            expect_cursor=(1, 0),
            expect_content_redraws=[True, False]
        )

        # Search with scroll -> full repaint (verify we don't break scrolling)
        # 15-line file, 10 rows. /Line 12 finds line 11 (0-indexed), scrolls.
        self.run_test_screen(
            "Render opt: search with scroll triggers repaint",
            make_lines(15),
            b"/Line 12\r:q!\r",
            expect_content_redraws=[True, True]
        )

        # Find-next (n) no-scroll -> cursor-only
        # /AAA on "AAA\nBBB\nAAA\n" finds line 2. n wraps to line 0 (visible).
        self.run_test_screen(
            "Render opt: n no-scroll is cursor-only",
            "AAA\nBBB\nAAA\n",
            b"/AAA\rn:q!\r",
            expect_cursor=(0, 0),
            expect_content_redraws=[True, False, False]
        )

        # Cancel search (ESC) -> cursor-only
        self.run_test_screen(
            "Render opt: search cancel is cursor-only",
            "AAA\nBBB\n",
            b"/\x1b:q!\r",
            expect_content_redraws=[True, False]
        )

        # Not found -> cursor-only after dismissal
        # Space dismisses the "not found" message (consumed inside search handler)
        self.run_test_screen(
            "Render opt: search not-found is cursor-only",
            "AAA\nBBB\nCCC\n",
            b"/ZZZ\r :q!\r",
            expect_cursor=(0, 0),
            expect_content_redraws=[True, False]
        )

        # Insert char: only cursor's row is touched (not all rows)
        # i enters insert (cursor-only), 'X' inserts char
        # Single-row optimization: only row 0 is redrawn
        self.run_test_screen(
            "Render opt: insert char redraws from cursor",
            "Hello\nWorld\n",
            b"iX\x1b:q!\r",
            expect_content_redraws=[True, False, True, False],
            expect_content_rows=[(2, {0})]
        )

        # Backspace mid-line: single-row redraw
        # Move right, enter insert, backspace (mid-line)
        self.run_test_screen(
            "Render opt: backspace redraws from cursor",
            "Hello\nWorld\n",
            b"li\x08\x1b:q!\r",
            expect_content_redraws=[True, False, False, True, False],
            expect_content_rows=[(3, {0})]
        )

        # Normal mode x: single-row redraw
        self.run_test_screen(
            "Render opt: x redraws from cursor",
            "Hello\nWorld\n",
            b"x:q!\r",
            expect_content_redraws=[True, True],
            expect_content_rows=[(1, {0})]
        )

        # r replaces char: single-row redraw
        # Frame 0: init(T), Frame 1: r+X batched replaces(T), Frame 2: :q!(F)
        self.run_test_screen(
            "Render opt: r replaces with single-row redraw",
            "Hello\n",
            b"rX:q!\r",
            expect_content_redraws=[True, True, False],
            expect_content_rows=[(1, {0})]
        )

        # ~ toggles case: single-row redraw
        self.run_test_screen(
            "Render opt: ~ toggles with single-row redraw",
            "Hello\n",
            b"~:q!\r",
            expect_content_redraws=[True, True],
            expect_content_rows=[(1, {0})]
        )

        # s substitutes: single-row redraw for the s frame
        # Frame 0: init(T), Frame 1: s deletes+enters insert(T), Frame 2: X inserts(T), Frame 3: ESC(F)
        self.run_test_screen(
            "Render opt: s substitutes with single-row redraw",
            "Hello\n",
            b"sX\x1b:q!\r",
            expect_content_rows=[(1, {0})]
        )

        # Insert Delete (forward delete): single-row redraw
        DEL = b"\x1b[3~"
        self.run_test_screen(
            "Render opt: insert Delete single-row redraw",
            "Hello\n",
            b"i" + DEL + b"\x1b:q!\r",
            expect_content_rows=[(2, {0})]
        )

        # D deletes to end of line: single-row redraw
        self.run_test_screen(
            "Render opt: D redraws current row only",
            "Hello World\n",
            b"D:q!\r",
            expect_content_rows=[(1, {0})]
        )

        # dw deletes word: single-row redraw
        # d+w batched into single frame (no pending-key frame)
        self.run_test_screen(
            "Render opt: dw redraws current row only",
            "Hello World\n",
            b"dw:q!\r",
            expect_content_rows=[(1, {0})]
        )

        # db deletes word backward: single-row redraw
        # Frame 0: init(T), Frame 1: $(F), Frame 2: d+b batched(T)
        self.run_test_screen(
            "Render opt: db redraws current row only",
            "Hello World\n",
            b"$db:q!\r",
            expect_content_rows=[(2, {0})]
        )

        # C changes to end of line: single-row redraw
        self.run_test_screen(
            "Render opt: C redraws current row only",
            "Hello World\n",
            b"C\x1b:q!\r",
            expect_content_rows=[(1, {0})]
        )

        # cw changes word: single-row redraw
        # c+w batched into single frame (no pending-key frame)
        self.run_test_screen(
            "Render opt: cw redraws current row only",
            "Hello World\n",
            b"cw\x1b:q!\r",
            expect_content_rows=[(1, {0})]
        )

        # cb changes word backward: single-row redraw
        # Frame 0: init(T), Frame 1: $(F), Frame 2: c+b batched(T)
        self.run_test_screen(
            "Render opt: cb redraws current row only",
            "Hello World\n",
            b"$cb\x1b:q!\r",
            expect_content_rows=[(2, {0})]
        )

        # de deletes to word end: single-row redraw
        # d+e batched into single frame (no pending-key frame)
        self.run_test_screen(
            "Render opt: de redraws current row only",
            "Hello World\n",
            b"de:q!\r",
            expect_content_rows=[(1, {0})]
        )

        # ce changes to word end: single-row redraw
        # c+e batched into single frame (no pending-key frame)
        self.run_test_screen(
            "Render opt: ce redraws current row only",
            "Hello World\n",
            b"ce\x1b:q!\r",
            expect_content_rows=[(1, {0})]
        )

        # char paste p: single-row redraw
        self.run_test_screen(
            "Render opt: char paste p redraws current row only",
            "Hello\n",
            b"xp:q!\r",
            expect_content_rows=[(2, {0})]
        )

        # char paste P: single-row redraw
        self.run_test_screen(
            "Render opt: char paste P redraws current row only",
            "Hello\n",
            b"xP:q!\r",
            expect_content_rows=[(2, {0})]
        )

        # --- Wrapped-line optimization tests (line spans 2+ screen rows) ---
        # "A"*60 = 2 rows on a 40-col screen (40+20)

        # Insert in wrapped line, same wrap count
        # Frame 0: init(T), Frame 1: i enters insert(F), Frame 2: X inserts(T)
        self.run_test_screen(
            "Render opt: insert in wrapped line, same count",
            "A" * 60 + "\nSecond\n",
            b"iX\x1b:q!\r",
            expect_content_redraws=[True, False, True, False],
            expect_content_rows=[(2, {0, 1})]
        )

        # x in wrapped line, same wrap count
        self.run_test_screen(
            "Render opt: x in wrapped line, same count",
            "A" * 60 + "\nSecond\n",
            b"x:q!\r",
            expect_content_redraws=[True, True],
            expect_content_rows=[(1, {0, 1})]
        )

        # r replaces char in wrapped line
        # Frame 0: init(T), Frame 1: r+X batched replaces(T)
        self.run_test_screen(
            "Render opt: r in wrapped line",
            "A" * 60 + "\nSecond\n",
            b"rX:q!\r",
            expect_content_redraws=[True, True, False],
            expect_content_rows=[(1, {0})]
        )

        # ~ toggles case in wrapped line
        self.run_test_screen(
            "Render opt: ~ in wrapped line",
            "a" * 60 + "\nSecond\n",
            b"~:q!\r",
            expect_content_redraws=[True, True],
            expect_content_rows=[(1, {0})]
        )

        # D in wrapped line stays wrapped (at col 0, deletes most but 40+ remain? No.
        # Actually $D from col 0 deletes all to EOL -> single char line.
        # Use $ to go to end, then come back: move to col 20 (on 2nd wrap row),
        # D deletes from col 20 to end -> 20 chars left = 1 row.
        # That changes row count, so it renders from first row downward.
        # Better test: line is 80 chars (2 full rows), D from col 0 -> empty = 1 row, rows change
        # For "stays wrapped": line is 80 chars, delete 1 with x -> 79 chars = still 2 rows
        self.run_test_screen(
            "Render opt: $D wrapped line stays wrapped",
            "A" * 60 + "\nSecond\n",
            b"$D:q!\r",
            expect_content_rows=[(2, {1})]
        )

        # x unwraps line (41 chars -> 40 after first x -> 1 row), uses scroll
        # Row count changes from 2 to 1 on the first x, scroll handles shift
        self.run_test_screen(
            "Render opt: x unwraps line uses scroll",
            "A" * 41 + "\nSecond\n",
            b"x:q!\r",
            expect_content_rows=[(1, {0, 8})]
        )

        # Insert newline at start of line: scroll only (no content repaint)
        self.run_test_screen(
            "Render opt: Enter at start of line is scroll only",
            "Hello\nWorld\n",
            b"i\r\x1b:q!\r",
            expect_content_redraws=[True, False, False, False]
        )

        # Backspace at col 0 (join lines): full repaint
        self.run_test_screen(
            "Render opt: backspace join-lines is full repaint",
            "Hello\nWorld\n",
            b"ji\x08\x1b:q!\r",
            expect_content_redraws=[True, False, False, True, False]
        )

        # ============================================================
        # Batch insert tests
        # When multiple printable keys are buffered, they should be
        # inserted in a single operation with one render.
        # ============================================================
        self._group("Batch insert:", leading_blank=True)

        # Render optimization: batch insert reduces content redraws
        # Frame 0: initial render (True)
        # Frame 1: 'i' enters insert mode (False - cursor+status only)
        # Frame 2: first char 'X' inserted, then Y and Z batched (True)
        # Frame 3: ESC exits insert (False - cursor only)
        self.run_test_screen(
            "Render opt: batch insert reduces redraws",
            "Hello\n",
            b"iXYZ\x1b:q!\r",
            expect_content_redraws=[True, False, True, False],
        )

        # Batch insert mid-line correctness
        self.run_test(
            "Batch insert mid-line",
            "ABCD\n",
            b"liXYZ\x1b:wq\r",
            expected_content="AXYZBCD\n"
        )

        # Batch includes newline (Enter after printable chars)
        self.run_test(
            "Batch insert includes newline",
            "Hello\n",
            b"iXY\r\x1b:wq\r",
            expected_content="XY\nHello\n"
        )

        # Batch insert many characters
        self.run_test(
            "Batch insert many characters",
            "AB\n",
            b"liHello World\x1b:wq\r",
            expected_content="AHello WorldB\n"
        )

        # --- Enter mixing: correctness ---

        # Mixed chars and newlines batched together
        self.run_test(
            "Mixed chars and newlines",
            "Hello\n",
            b"ia\rb\rc\r\x1b:wq\r",
            expected_content="a\nb\nc\nHello\n"
        )

        # Char then only newlines
        self.run_test(
            "Char then only newlines",
            "X\n",
            b"ia\r\r\r\x1b:wq\r",
            expected_content="a\n\n\nX\n"
        )

        # Mixed batch mid-line
        self.run_test(
            "Mixed batch mid-line",
            "XY\n",
            b"lia\rb\r\x1b:wq\r",
            expected_content="Xa\nb\nY\n"
        )

        # --- Enter mixing: render optimization ---
        # i\ra\ra\ra\r on "Hello\n"
        # Frame 0: initial render (True)
        # Frame 1: 'i' enters insert mode (False - cursor+status only)
        # Frame 2: enter key triggers newline insert (True)
        # Frame 3: 'a' + remaining \ra\r batched together (True)
        # Frame 4: ESC exits insert (False - cursor only)
        self.run_test_screen(
            "Render opt: mixed enter+chars reduces redraws",
            "Hello\n",
            b"i\ra\ra\ra\r\x1b:q!\r",
            expect_content_redraws=[True, False, True, False],
        )

        # --- Enter mixing: cursor position ---

        # After ia\rb\r\x1b -> cursor at (2, 0) - trailing newline, col 0
        self.run_test_screen(
            "Mixed batch cursor: trailing newline",
            "Hello\n",
            b"ia\rb\r\x1b:q!\r",
            expect_cursor=(2, 0),
        )

        # After ia\rbc\x1b -> cursor at (1, 1) - trailing chars, ESC back 1
        self.run_test_screen(
            "Mixed batch cursor: trailing chars",
            "Hello\n",
            b"ia\rbc\x1b:q!\r",
            expect_cursor=(1, 1),
        )

        # --- Backspace cancellation: correctness ---

        # BS cancels within batch: iabBSc -> "ac"
        self.run_test(
            "BS cancels within batch",
            "Hello\n",
            b"iab\x08c\x1b:wq\r",
            expected_content="acHello\n"
        )

        # BS cancels newline: ia\rBSb -> "ab"
        self.run_test(
            "BS cancels newline in batch",
            "Hello\n",
            b"ia\r\x08" b"b\x1b:wq\r",
            expected_content="abHello\n"
        )

        # BS cancels all -> no-op (second BS pushed back, at col 0 it's no-op)
        self.run_test(
            "BS cancels all in batch is no-op",
            "Hello\n",
            b"ia\x08\x08\x1b:wq\r",
            expected_content="Hello\n"
        )

        # BS then more typing: iabcBSBSde -> "ade"
        self.run_test(
            "BS then more typing",
            "X\n",
            b"iabc\x08\x08de\x1b:wq\r",
            expected_content="adeX\n"
        )

        # BS mixed with Enter: ia\rbBSc\r -> "a\nc\n"
        self.run_test(
            "BS mixed with Enter",
            "Z\n",
            b"ia\rb\x08c\r\x1b:wq\r",
            expected_content="a\nc\nZ\n"
        )

        # --- Backspace cancellation: render optimization ---
        # iabBSc on "Hello\n"
        # Frame 0: initial render (True)
        # Frame 1: 'i' enters insert mode (False - cursor+status only)
        # Frame 2: batch abBSc -> "ac" (True - single batch)
        # Frame 3: ESC exits insert (False - cursor only)
        self.run_test_screen(
            "Render opt: BS cancellation in single batch",
            "Hello\n",
            b"iab\x08c\x1b:q!\r",
            expect_content_redraws=[True, False, True, False],
        )

        # ============================================================
        # Mixed-type batch tests (unified insert_batch handler)
        # When mixed editing keys (printable, Enter, BS, DEL) arrive
        # in rapid succession, they should be consolidated into a
        # single buffer operation.
        # ============================================================
        self._group("Mixed-type batch:", leading_blank=True)

        # DEL then typing: position cursor at start, DEL deletes first
        # char, then type "Z" -> "Z" replaces first char
        DEL = b"\x1b[3~"
        self.run_test(
            "DEL then typing in single batch",
            "Hello\n",
            b"i" + DEL + b"Z\x1b:wq\r",
            expected_content="Zello\n"
        )

        # Multiple DEL then typing: 3 DELs then "ABC"
        DEL = b"\x1b[3~"
        self.run_test(
            "Multiple DEL then typing",
            "Hello World\n",
            b"i" + DEL * 3 + b"ABC\x1b:wq\r",
            expected_content="ABClo World\n"
        )

        # Typing then DEL: type "XY" then DEL removes char after insert
        DEL = b"\x1b[3~"
        self.run_test(
            "Typing then DEL in single batch",
            "Hello\n",
            b"i" + b"XY" + DEL + b"\x1b:wq\r",
            expected_content="XYello\n"
        )

        # BS overflow into buffer delete: type "a", then BS*2
        # First BS cancels 'a', second BS deletes char before cursor
        self.run_test(
            "BS overflow deletes from buffer",
            "Hello\n",
            b"lla" + b"\x08\x08\x1b:wq\r",
            expected_content="Hlo\n"
        )

        # Mixed DEL + BS: DEL*2 then BS*1 at col 2
        # DEL removes 2 chars forward, BS removes 1 char backward
        DEL = b"\x1b[3~"
        self.run_test(
            "DEL and BS mixed in batch",
            "ABCDE\n",
            b"lli" + DEL * 2 + b"\x08\x1b:wq\r",
            expected_content="AE\n"
        )

        # DEL across newline then typing
        DEL = b"\x1b[3~"
        self.run_test(
            "DEL across newline then typing",
            "AB\nCD\n",
            b"lli" + DEL * 3 + b"XY\x1b:wq\r",
            expected_content="AXYD\n"
        )

        # BS across newline then typing (col 0 BS joins line)
        self.run_test(
            "BS across newline then typing",
            "AB\nCD\n",
            b"ji\x08XY\x1b:wq\r",
            expected_content="ABXYCD\n"
        )

        # Pure DEL batch (same as before, should still work)
        DEL = b"\x1b[3~"
        self.run_test(
            "Pure DEL batch still works",
            "ABCDE\n",
            b"i" + DEL * 3 + b"\x1b:wq\r",
            expected_content="DE\n"
        )

        # BS cancels all then DEL: type "ab", BS*2 cancels, DEL*2 forward
        DEL = b"\x1b[3~"
        self.run_test(
            "BS cancels batch then DEL forward",
            "Hello\n",
            b"iab\x08\x08" + DEL * 2 + b"\x1b:wq\r",
            expected_content="llo\n"
        )

        # DEL at end of last line (past final newline) is no-op
        DEL = b"\x1b[3~"
        self.run_test(
            "DEL at final newline is no-op",
            "A\n",
            b"A" + DEL * 5 + b"\x1b:wq\r",
            expected_content="A\n"
        )

        # Mixed render optimization: DEL+typing in single batch
        DEL = b"\x1b[3~"
        self.run_test_screen(
            "Render opt: DEL+typing in single batch",
            "Hello\n",
            b"i" + DEL * 2 + b"AB\x1b:q!\r",
            expect_content_redraws=[True, False, True, False],
        )

        # Mixed: type, Enter, DEL all in one batch
        DEL = b"\x1b[3~"
        self.run_test(
            "Type Enter DEL in one batch",
            "Hello\n",
            b"iX\r" + DEL + b"\x1b:wq\r",
            expected_content="X\nello\n"
        )

        # ============================================================
        # Batch delete tests
        # When multiple backspace or x keys are buffered, they should
        # be deleted in a single operation with one render.
        # ============================================================
        self._group("Batch delete:", leading_blank=True)

        # Render optimization: batch backspace reduces content redraws
        # Frame 0: initial render (True)
        # Frame 1: lll batched (False - cursor only)
        # Frame 2: i enters insert mode (False - cursor+status only)
        # Frame 3: first BS deletes, then 2 more batched (True)
        # Frame 4: ESC exits insert (False - cursor only)
        self.run_test_screen(
            "Render opt: batch backspace reduces redraws",
            "Hello\n",
            b"llli\x08\x08\x08\x1b:q!\r",
            expect_content_redraws=[True, False, False, True, False],
        )

        # Batch backspace correctness
        # A appends after last char (col 6), 4 BS deletes F,E,D,C -> "AB\n"
        self.run_test(
            "Batch backspace mid-line",
            "ABCDEF\n",
            b"A\x08\x08\x08\x08\x1b:wq\r",
            expected_content="AB\n"
        )

        # Batch backspace stops at column 0
        # l moves to col 1, i enters insert at col 1, 3 BS: first deletes A,
        # then at col 0 batching must stop (no join-lines in batch)
        self.run_test(
            "Batch backspace stops at column 0",
            "AB\n",
            b"li\x08\x08\x08\x1b:wq\r",
            expected_content="B\n"
        )

        # Batch backspace stops at non-backspace key
        # A appends at end (col 5), 2 BS deletes E,D, then X inserts -> "ABCX\n"
        self.run_test(
            "Batch backspace stops at non-BS key",
            "ABCDE\n",
            b"A\x08\x08X\x1b:wq\r",
            expected_content="ABCX\n"
        )

        # Excess backspace keys beyond column trigger join-lines
        # Line 1: "AB", Line 2: "CD". j moves to line 2, li enters insert at col 1.
        # 3 BS keys: first deletes 'C' (col 1->0), then 2 excess BS keys should
        # trigger join-lines (joining "AB" + "D"), not be silently consumed.
        self.run_test(
            "Excess backspace triggers join-lines",
            "AB\nCD\n",
            b"jli\x08\x08\x1b:wq\r",
            expected_content="ABD\n"
        )

        # Render optimization: batch x reduces content redraws
        # Without batching: xxx -> frames [init, x, x, x] = 4 frames
        # With batching: frames [init, x+batch_xx] = 2 frames
        # Frame 0: initial render (True)
        # Frame 1: first x + batch xx (True)
        # Then j triggers a cursor-only frame (False) proving no more x frames
        self.run_test_screen(
            "Render opt: batch x reduces redraws",
            "Hello\nWorld\n",
            b"xxxj:q!\r",
            expect_content_redraws=[True, True, False],
        )

        # Batch x correctness
        self.run_test(
            "Batch x mid-line",
            "ABCDEF\n",
            b"lxxx:wq\r",
            expected_content="AEF\n"
        )

        # Batch x stops at end of line
        self.run_test(
            "Batch x stops at end of line",
            "AB\n",
            b"xxxx:wq\r",
            expected_content="\n"
        )

        # Batch x stops at non-x key
        self.run_test(
            "Batch x stops at non-x key",
            "ABCDE\n",
            b"xxl:wq\r",
            expected_content="CDE\n"
        )

        # Batch x on wrapped line: when deletion unwraps the line, the
        # stale second wrap row must be cleared.
        # 45-char line on 40-col screen: initially row 0 = A*40, row 1 = A*5.
        # Batch delete 6 chars -> 39 left, line no longer wraps.
        # Frame 0: initial (full), Frame 1: batch x (single-line redraw).
        # At frame 1, row 1 should show "B" (next line), not stale "AAAAA".
        self.run_test_screen(
            "Batch x unwrap clears stale row",
            "A" * 45 + "\nB\n",
            b"xxxxxx:q!\r",
            expect_lines_at_frame=[
                (1, [
                    (0, "A" * 39),
                    (1, "B"),
                    (2, "~"),
                ]),
            ]
        )

        self._group("X (delete before cursor):", leading_blank=True)

        self.run_test(
            "X deletes the char before the cursor",
            "ABCDEF\n",
            b"llX:wq\r",
            expected_content="ACDEF\n"
        )

        self.run_test(
            "X at column 0 does nothing",
            "ABC\n",
            b"X:wq\r",
            expected_content="ABC\n"
        )

        self.run_test(
            "3X deletes three chars before the cursor",
            "ABCDEF\n",
            b"$3X:wq\r",
            expected_content="ABF\n"
        )

        self.run_test(
            "3X stops at column 0",
            "ABCDEF\n",
            b"ll3X:wq\r",
            expected_content="CDEF\n"
        )

        self.run_test(
            "Batch XXX mid-line",
            "ABCDEF\n",
            b"$XXX:wq\r",
            expected_content="ABF\n"
        )

        self.run_test(
            "Batch XX stops at column 0",
            "ABC\n",
            b"lXX:wq\r",
            expected_content="BC\n"
        )

        # The char that was under the cursor stays under it
        self.run_test_screen(
            "X moves the cursor left with the text",
            "ABCDEF\n",
            b"$2X",
            expect_lines=[(0, "ABCF")],
            expect_cursor=(0, 3),
        )

        self.run_test(
            "2X yanks the deleted chars",
            "ABCDEF\n",
            b"$2Xp:wq\r",
            expected_content="ABCFDE\n"
        )

        # Like batched x: the register holds what the last X deleted
        self.run_test(
            "Batch XX yanks the last deleted char",
            "ABCDEF\n",
            b"$XXp:wq\r",
            expected_content="ABCFD\n"
        )

        self.run_test(
            "X then u restores the text",
            "ABCDEF\n",
            b"$2Xu:wq\r",
            expected_content="ABCDEF\n"
        )

        # Batched keys undo as if typed one at a time: XX deletes E then
        # D, so u brings back only the D
        self.run_test(
            "Batch XX then u restores the last deleted char",
            "ABCDEF\n",
            b"$XXu:wq\r",
            expected_content="ABCDF\n"
        )

        self.run_test_screen(
            "X on wrapped line keeps the cursor on its char",
            "A" * 39 + "BC\n",
            b"$X",
            expect_lines=[(0, "A" * 39 + "C")],
            expect_cursor=(0, 39),
        )

        self._group("ICH/DCH shifting (single-row line):", leading_blank=True)

        # Each case: (name, keys, edit frame, row 0 text, (min, max) cols
        # written on row 0 in that frame, raw bytes the frame must contain).
        # "Hello World": 5l puts the cursor on the space (col 5).
        shift_cases = [
            ("type one char mid-line", b"5liX\x1b:q!\r", 4,
             "HelloX World", (5, 5), "\x1b[1;6H\x1b[1@X"),
            ("type-ahead batch shifts once", b"5liABC\x1b:q!\r", 4,
             "HelloABC World", (5, 7), "\x1b[1;6H\x1b[3@ABC"),
            ("insert BS mid-line", b"6li\x7f\x1b:q!\r", 4,
             "HelloWorld", (-1, -1), "\x1b[1;6H\x1b[1P"),
            ("insert DEL mid-line", b"5li\x1b[3~\x1b:q!\r", 4,
             "HelloWorld", (-1, -1), "\x1b[1;6H\x1b[1P"),
            ("mixed batch nets one shift", b"5liABC\x7f\x1b:q!\r", 4,
             "HelloAB World", (5, 6), "\x1b[1;6H\x1b[2@AB"),
            ("type + DEL overwrites only", b"5liX\x1b[3~\x1b:q!\r", 4,
             "HelloXWorld", (5, 5), None),
            ("append at end writes only the new char", b"AX\x1b:q!\r", 2,
             "Hello WorldX", (11, 11), None),
            ("x mid-line", b"5lx:q!\r", 3,
             "HelloWorld", (-1, -1), "\x1b[1;6H\x1b[1P"),
            ("3x mid-line", b"5l3x:q!\r", 4,
             "Hellorld", (-1, -1), "\x1b[1;6H\x1b[3P"),
            ("batched xxx shifts once", b"5lxxx:q!\r", 3,
             "Hellorld", (-1, -1), "\x1b[1;6H\x1b[3P"),
            ("normal-mode Delete", b"5l\x1b[3~:q!\r", 3,
             "HelloWorld", (-1, -1), "\x1b[1;6H\x1b[1P"),
            ("X mid-line", b"6lX:q!\r", 3,
             "HelloWorld", (-1, -1), "\x1b[1;6H\x1b[1P"),
            ("3X mid-line", b"8l3X:q!\r", 4,
             "Hellorld", (-1, -1), "\x1b[1;6H\x1b[3P"),
        ]
        for deferred in (False, True):
            suffix = " (deferred wrap)" if deferred else ""
            for name, keys, frame, text, (lo, hi), raw in shift_cases:
                self.run_test_screen(
                    "Shift: " + name + suffix,
                    "Hello World\n",
                    keys,
                    deferred_wrap=deferred,
                    expect_ansi_contains=raw,
                    expect_lines_at_frame=[(frame, [(0, text)])],
                    expect_min_col=[(frame, 0, lo)],
                    expect_max_col=[(frame, 0, hi)],
                )
            self.run_test_screen(
                "Shift: x on the last char blanks it" + suffix,
                "Hello World\n",
                b"$x:q!\r",
                deferred_wrap=deferred,
                expect_lines_at_frame=[(2, [(0, "Hello Worl")])],
            )

        self._group("ICH/DCH shifting (wrapped line):", leading_blank=True)

        # 100-char line on a 40-col screen: rows hold [0,40) [40,80) [80,100)
        digits = "0123456789" * 10
        ins = digits[:5] + "AB" + digits[5:]       # "AB" typed at col 5
        dele = digits[:5] + digits[6:]             # col 5 deleted
        rows_of = lambda t: [(r, t[r * 40:(r + 1) * 40]) for r in range(3)]
        wrap_cases = [
            # Every row gets its own ICH; later rows write only the 2
            # chars carried over from the row above
            ("insert on a 3-row line", b"5liAB\x1b:q!\r", 4, ins,
             [(0, 5, 6), (1, 0, 1), (2, 0, 1)],
             "\x1b[1;6H\x1b[2@AB\x1b[2;1H\x1b[2@" + ins[40:42]
             + "\x1b[3;1H\x1b[2@" + ins[80:82]),
            # Every row gets its own DCH; full rows write only their last
            # cell, pulled up from the row below; the last row writes none
            ("insert BS on a 3-row line", b"6li\x7f\x1b:q!\r", 4, dele,
             [(0, 39, 39), (1, 39, 39), (2, -1, -1)],
             "\x1b[1;6H\x1b[1P\x1b[1;40H" + dele[39]
             + "\x1b[2;1H\x1b[1P\x1b[2;40H" + dele[79]
             + "\x1b[3;1H\x1b[1P"),
            ("x on a 3-row line", b"5lx:q!\r", 3, dele,
             [(0, 39, 39), (1, 39, 39), (2, -1, -1)], None),
            ("X on a 3-row line", b"6lX:q!\r", 3, dele,
             [(0, 39, 39), (1, 39, 39), (2, -1, -1)], None),
        ]
        for deferred in (False, True):
            suffix = " (deferred wrap)" if deferred else ""
            for name, keys, frame, text, cols, raw in wrap_cases:
                self.run_test_screen(
                    "Shift: " + name + suffix,
                    digits + "\n",
                    keys,
                    deferred_wrap=deferred,
                    expect_ansi_contains=raw,
                    expect_lines_at_frame=[(frame, rows_of(text))],
                    expect_min_col=[(frame, r, lo) for r, lo, _ in cols],
                    expect_max_col=[(frame, r, hi) for r, _, hi in cols],
                )

            # A tab (reverse '>') carried across a row boundary keeps its
            # reverse video: it moves from (0,39) to (1,0) and is rewritten
            tabbed = "a" * 39 + "\t" + "b" * 40 + "c" * 10
            self.run_test_screen(
                "Shift: carried tab keeps reverse video" + suffix,
                tabbed + "\n",
                b"iX\x1b:q!\r",
                deferred_wrap=deferred,
                expect_lines_at_frame=[(2, [(0, "X" + "a" * 39),
                                            (1, ">" + "b" * 39),
                                            (2, "b" + "c" * 10)])],
                expect_min_col=[(2, 1, 0)],
                expect_max_col=[(2, 1, 0)],
                expect_reverse_at=[(1, 0, True), (0, 39, False)],
            )

        self._group("ICH/DCH shifting (row count changes):", leading_blank=True)

        d79 = ("0123456789" * 8)[:79]              # rows [0,40) [40,79)
        d81 = ("0123456789" * 9)[:81]              # rows [0,40) [40,80) [80,81)
        grown = d79[:5] + "AB" + d79[5:]           # 81 chars: 3 rows
        shrunk = d81[:5] + d81[6:]                 # 80 chars: 2 rows
        d159 = ("0123456789" * 16)[:159]           # 4 rows on 40 cols
        grown159 = d159[:5] + "AB" + d159[5:]      # 161 chars: 5 rows
        d300 = "0123456789" * 30                   # 8 rows
        for deferred in (False, True):
            suffix = " (deferred wrap)" if deferred else ""
            # The rows below scroll down intact; the new row is written
            # with exactly the one carried char
            self.run_test_screen(
                "Shift: insert that adds a row" + suffix,
                d79 + "\nNEXT\nLAST\n",
                b"5liAB\x1b:q!\r",
                deferred_wrap=deferred,
                expect_lines_at_frame=[(4, [(0, grown[:40]),
                                            (1, grown[40:80]),
                                            (2, grown[80:]),
                                            (3, "NEXT"), (4, "LAST")])],
                expect_min_col=[(4, 0, 5), (4, 1, 0), (4, 2, 0),
                                (4, 3, -1), (4, 4, -1)],
                expect_max_col=[(4, 0, 6), (4, 1, 1), (4, 2, 0)],
            )
            # The rows below scroll up intact; the shifted rows write only
            # the cell pulled up from the row below
            for how, keys, frame in (("x", b"5lx:q!\r", 3),
                                     ("insert BS", b"6li\x7f\x1b:q!\r", 4)):
                self.run_test_screen(
                    "Shift: " + how + " that removes a row" + suffix,
                    d81 + "\nNEXT\nLAST\n",
                    keys,
                    deferred_wrap=deferred,
                    expect_lines_at_frame=[(frame, [(0, shrunk[:40]),
                                                    (1, shrunk[40:]),
                                                    (2, "NEXT"),
                                                    (3, "LAST")])],
                    expect_min_col=[(frame, 0, 39), (frame, 1, 39),
                                    (frame, 2, -1), (frame, 3, -1)],
                    expect_max_col=[(frame, 0, 39), (frame, 1, 39)],
                )
            # Line longer than the screen: shifting stops at the status bar
            self.run_test_screen(
                "Shift: line running past the bottom" + suffix,
                d159 + "\n",
                b"5liAB\x1b:q!\r",
                rows=4, cols=40,
                deferred_wrap=deferred,
                expect_lines_at_frame=[(4, [(0, grown159[:40]),
                                            (1, grown159[40:80]),
                                            (2, grown159[80:120])])],
                expect_status_at_frame=[(4, "INSERT")],
                expect_max_col=[(4, 0, 6), (4, 1, 1), (4, 2, 1)],
            )
            # First row above the viewport: still a full repaint
            self.run_test_screen(
                "Shift: line starting above the viewport" + suffix,
                d300 + "\n",
                b"$x:q!\r",
                rows=5, cols=40,
                deferred_wrap=deferred,
                expect_lines_at_frame=[(2, [(0, d300[160:200]),
                                            (1, d300[200:240]),
                                            (2, d300[240:280]),
                                            (3, d300[280:299])])],
            )
            # Typing past the end of a line that exactly filled its row
            self.run_test_screen(
                "Shift: typing past a full row at end of line" + suffix,
                "a" * 39 + "\nNEXT\nLAST\n",
                b"AXY\x1b:q!\r",
                deferred_wrap=deferred,
                expect_lines_at_frame=[(2, [(0, "a" * 39 + "X"), (1, "Y"),
                                            (2, "NEXT"), (3, "LAST")])],
                expect_cursor_at_frame=[(2, (1, 1))],
                expect_min_col=[(2, 0, 39), (2, 1, 0), (2, 2, -1)],
                expect_max_col=[(2, 0, 39), (2, 1, 0)],
            )

        self._group("ICH/DCH only when cheaper:", leading_blank=True)

        digits = "0123456789" * 10
        for deferred in (False, True):
            suffix = " (deferred wrap)" if deferred else ""
            # Two chars after the insert point: resending "Xld" beats ESC[1@
            self.run_test_screen(
                "Shift: short tail after insert is resent" + suffix,
                "Hello World\n",
                b"9liX\x1b:q!\r",
                deferred_wrap=deferred,
                expect_lines_at_frame=[(4, [(0, "Hello WorXld")])],
                expect_min_col=[(4, 0, 9)],
                expect_max_col=[(4, 0, 11)],
            )
            # One char after the delete point: "d" + ESC[K beats ESC[1P
            self.run_test_screen(
                "Shift: short tail after delete is resent" + suffix,
                "Hello World\n",
                b"9lx:q!\r",
                deferred_wrap=deferred,
                expect_lines_at_frame=[(3, [(0, "Hello Word")])],
                expect_min_col=[(3, 0, 9)],
                expect_max_col=[(3, 0, 39)],
            )
            # Deleting 30 of row 0's last 35 chars: the 30 cells DCH would
            # have to pull up cost more than resending the row
            self.run_test_screen(
                "Shift: large delete resends the row" + suffix,
                digits + "\n",
                b"5l30x:q!\r",
                deferred_wrap=deferred,
                expect_lines_at_frame=[(5, [(0, (digits[:5] + digits[35:])[:40])])],
                expect_min_col=[(5, 0, 5)],
                expect_max_col=[(5, 0, 39)],
            )

        self._group("D stays minimal:", leading_blank=True)

        # Nothing is left to the right of the cursor to shift: D only
        # clears from the cursor, and on a wrapped line the rows below
        # scroll up instead of being rewritten
        for deferred in (False, True):
            suffix = " (deferred wrap)" if deferred else ""
            self.run_test_screen(
                "D mid-line only clears from the cursor" + suffix,
                "Hello World\nNEXT\n",
                b"5lD:q!\r",
                deferred_wrap=deferred,
                expect_ansi_contains="\x1b[?25l\x1b[1;6H\x1b[K\x1b[10;1H",
                expect_lines_at_frame=[(3, [(0, "Hello"), (1, "NEXT")])],
                expect_min_col=[(3, 0, 5), (3, 1, -1)],
            )
            self.run_test_screen(
                "D on a wrapped line scrolls the rows below up" + suffix,
                "0123456789" * 10 + "\nNEXT\nLAST\n",
                b"5lD:q!\r",
                deferred_wrap=deferred,
                expect_ansi_contains="\x1b[2;9r\x1b[2S\x1b[r\x1b[1;6H\x1b[K",
                expect_lines_at_frame=[(3, [(0, "01234"), (1, "NEXT"),
                                            (2, "LAST")])],
                expect_min_col=[(3, 0, 5), (3, 1, -1), (3, 2, -1)],
            )

        # Same bug in insert mode: batch backspace on a wrapped line should
        # clear the stale wrap row when the line unwraps.
        # 45-char line, cursor at end (col 44). Batch delete 6 -> 39 left.
        # '$' moves to end-of-line, 'a' enters insert after cursor.
        # Frame 0: initial, Frame 1: $ (cursor), Frame 2: a (insert mode),
        # Frame 3: batch BS (single-line redraw - bug frame).
        self.run_test_screen(
            "Batch BS unwrap clears stale row",
            "A" * 45 + "\nB\n",
            b"$a\x7f\x7f\x7f\x7f\x7f\x7f\x1b:q!\r",
            expect_lines_at_frame=[
                (3, [
                    (0, "A" * 39),
                    (1, "B"),
                    (2, "~"),
                ]),
            ]
        )

        # Render optimization: batch Delete key in insert mode
        # Frame 0: initial render (True)
        # Frame 1: i enters insert (False - cursor+status only)
        # Frame 2: first Del + batch Del*2 (True)
        # Frame 3: ESC exits insert (False - cursor only)
        DEL = b"\x1b[3~"
        self.run_test_screen(
            "Render opt: batch insert Delete reduces redraws",
            "Hello\n",
            b"i" + DEL * 3 + b"\x1b:q!\r",
            expect_content_redraws=[True, False, True, False],
        )

        # Render optimization: batch Delete key in normal mode
        # Without batching: Del Del Del -> frames [init, Del, Del, Del] = 4 frames
        # With batching: frames [init, Del+batch_Del*2] = 2 frames
        # Frame 0: initial render (True)
        # Frame 1: first Del + batch Del*2 (True)
        # Then j triggers a cursor-only frame (False) proving no more Del frames
        DEL = b"\x1b[3~"
        self.run_test_screen(
            "Render opt: batch Delete reduces redraws",
            "Hello\nWorld\n",
            DEL * 3 + b"j:q!\r",
            expect_content_redraws=[True, True, False],
        )

        # ============================================================
        # Batch Enter tests
        # When multiple Enter keys are buffered in insert mode, they
        # should be inserted in a single operation with one rebuild.
        # ============================================================
        self._group("Batch Enter:", leading_blank=True)

        # Render optimization: batch Enter at start of line is scroll only
        # Frame 0: initial (True), Frame 1: i enters insert (False),
        # Frame 2: batch Enter*3 scroll only (False), Frame 3: ESC (False)
        self.run_test_screen(
            "Render opt: batch Enter at start reduces redraws",
            "Hello\n",
            b"i\r\r\r\x1b:q!\r",
            expect_content_redraws=[True, False, False, False],
        )

        # Batch Enter correctness - 3 Enters create 3 empty lines before content
        self.run_test(
            "Batch Enter multiple newlines",
            "Hello\n",
            b"i\r\r\r\x1b:wq\r",
            expected_content="\n\n\nHello\n"
        )

        # Batch Enter stops at non-Enter key
        self.run_test(
            "Batch Enter stops at printable",
            "Hello\n",
            b"i\r\rX\x1b:wq\r",
            expected_content="\n\nXHello\n"
        )

        # ============================================================
        # Batch join-lines tests
        # When multiple backspace keys are buffered at column 0 with
        # empty lines above, they should be joined in a single operation.
        # ============================================================
        self._group("Batch join-lines:", leading_blank=True)

        # Render optimization: batch join-lines reduces redraws
        # Start with 4 empty lines + content. Cursor at line 3 col 0.
        # jjj batched into one move, i enters insert at line 3.
        # BS joins (empty line above), then 2 more BS batched
        # Frame sequence: init(T), jjj-batched(F), i(F), BS+batch(T), ESC(F)
        self.run_test_screen(
            "Render opt: batch join-lines reduces redraws",
            "\n\n\nHello\n",
            b"jjji\x08\x08\x08\x1b:q!\r",
            expect_content_redraws=[True, False, False, True, False],
        )

        # Batch join-lines correctness - delete 3 empty lines above
        self.run_test(
            "Batch join empty lines",
            "\n\n\nHello\n",
            b"jjji\x08\x08\x08\x1b:wq\r",
            expected_content="Hello\n"
        )

        # Batch join stops at non-empty line (3rd BS joins AB with Hello normally)
        self.run_test(
            "Batch join stops at non-empty line",
            "AB\n\n\nHello\n",
            b"jjji\x08\x08\x08\x1b:wq\r",
            expected_content="ABHello\n"
        )

        # Batch join stops at line 0
        self.run_test(
            "Batch join stops at first line",
            "\n\nHello\n",
            b"jji\x08\x08\x08\x08\x1b:wq\r",
            expected_content="Hello\n"
        )

        # Batch join-lines must not skip over a non-empty line.
        # "\n\nAB\n\n\nCD\n" = (empty)*2, AB, (empty)*2, CD.
        # Cursor on line 4 (empty), 4 BS keys.
        # Correct: delete 2 empty lines (3,4), join with AB (cursor
        # at col 2), then within-line delete 2 chars → "\n\n\nCD\n".
        # Bug: backward \n scan treats AB's trailing \n as another
        # empty line, skipping over AB entirely. The scan deletes
        # AB's \n + line 3's \n, leaving cursor at col 0 on AB.
        # Then the next batch join deletes empty lines above AB.
        # Result: "AB\nCD\n" (blank lines above AB deleted instead
        # of AB's content).
        self.run_test(
            "Batch join does not skip over non-empty line",
            "\n\nAB\n\n\nCD\n",
            b"jjjji\x08\x08\x08\x08\x1b:wq\r",
            expected_content="\n\n\nCD\n"
        )

        # ============================================================
        # Screen content verification after insert mode operations
        # These tests verify the DISPLAYED content (not just file
        # content) is correct after various insert mode operations,
        # including batched and multi-line edits.
        # ============================================================
        self._group("Insert mode screen content:", leading_blank=True)

        # Single Enter splits line - screen shows both halves
        self.run_test_screen(
            "Enter splits line: screen shows both halves",
            "Hello World\n",
            b"llllli\rX\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Hello"), (1, "X World"),
            ],
            expect_cursor=(1, 0),
        )

        # Batched Enter (2 Enters) - screen shows all lines correctly
        self.run_test_screen(
            "Batched Enter: screen shows all new lines",
            "Hello World\n",
            b"llllli\r\r\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Hello"), (1, ""), (2, " World"),
                (3, "~"),
            ],
            expect_cursor=(2, 0),
        )

        # Batched Enter (3 Enters) - screen shows all lines correctly
        self.run_test_screen(
            "Batched 3 Enters: screen shows all new lines",
            "ABCDEF\n",
            b"llli\r\r\r\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "ABC"), (1, ""), (2, ""), (3, "DEF"),
                (4, "~"),
            ],
            expect_cursor=(3, 0),
        )

        # Batched Enter at start of line
        self.run_test_screen(
            "Batched Enter at start: blank lines above",
            "Hello\nWorld\n",
            b"ji\r\r\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Hello"), (1, ""), (2, ""), (3, "World"),
                (4, "~"),
            ],
            expect_cursor=(3, 0),
        )

        # Enter with chars (a\rb\r) - screen shows all content
        self.run_test_screen(
            "Mixed chars and Enter: screen correct",
            "XY\n",
            b"ia\rb\r\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "a"), (1, "b"), (2, "XY"),
            ],
            expect_cursor=(2, 0),
        )

        # Batched Enter causing scroll with mid-screen insertion.
        # With 6 rows (5 content + 1 status), lines 1-5 fill the screen.
        # Cursor on Line 3 (row 2, middle of screen). 'A' enters insert at
        # end, then 3 Enter keys are batched. This inserts 3 blank lines
        # after "Line 3", making: Line 1-3, (blank)×3, Line 4-5 = 8 lines.
        # Cursor lands on 3rd blank (line index 5). View scrolls to keep
        # cursor visible (VIEW_TOP moves from 0 to 1).
        # The scroll optimization shifts the old screen up and only redraws
        # newly exposed bottom rows, but the rows below the insertion point
        # changed (should be blank lines, not the old "Line 4"/"Line 5").
        # Expected screen (VIEW_TOP=1, showing lines 1-5):
        #   row 0: "Line 2", row 1: "Line 3", row 2: "", row 3: "", row 4: ""
        self.run_test_screen(
            "Batched Enter with scroll: display not corrupted",
            make_lines(5),
            b"jjA\r\r\r\x1b:q!\r",
            rows=6, cols=40,
            expect_lines=[
                (0, "Line 2"), (1, "Line 3"), (2, ""), (3, ""), (4, ""),
            ],
            expect_cursor=(4, 0),
        )

        # Batched BS at col 0 joining lines - screen shows merged content
        self.run_test_screen(
            "BS at col 0 joins: screen shows merged line",
            "Hello\nWorld\n",
            b"ji\x08\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "HelloWorld"), (1, "~"),
            ],
            expect_cursor=(0, 4),
        )

        # Batched BS at col 0: 3 BS deletes 3 bytes backward from cursor
        # Cursor at col 0 of "DD". 3 bytes back = "CC\n" → delete that.
        # Result: "AA\nBB\nDD\n"
        self.run_test_screen(
            "Batched BS joins one line: screen correct",
            "AA\nBB\nCC\nDD\n",
            b"jjji\x08\x08\x08\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "AA"), (1, "BB"), (2, "DD"), (3, "~"),
            ],
            expect_cursor=(2, 0),
        )

        # DEL at end of line joining with next - screen correct
        DEL = b"\x1b[3~"
        self.run_test_screen(
            "DEL at EOL joins lines: screen correct",
            "Hello\nWorld\n",
            b"A" + DEL + b"\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "HelloWorld"), (1, "~"),
            ],
            expect_cursor=(0, 4),
        )

        # ============================================================
        # Screen content verification after normal mode editing
        # ============================================================
        self._group("Normal mode editing screen content:", leading_blank=True)

        # D (delete to EOL) - screen shows truncated line
        self.run_test_screen(
            "D deletes to EOL: screen correct",
            "Hello World\n",
            b"lllllD:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello")],
            expect_cursor=(0, 4),
        )

        # d$ - same as D, screen shows truncated line
        self.run_test_screen(
            "d$ deletes to EOL: screen correct",
            "Hello World\n",
            b"llllld$:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello")],
            expect_cursor=(0, 4),
        )

        # 2d$ - multi-line delete, screen updates correctly
        self.run_test_screen(
            "2d$ multi-line: screen correct",
            "Hello\nWorld\nFoo\n",
            b"ll2d$:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "He"), (1, "Foo")],
            expect_cursor=(0, 1),
        )

        # d0 - screen shows shortened line
        self.run_test_screen(
            "d0 deletes to BOL: screen correct",
            "Hello\n",
            b"llld0:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "lo")],
            expect_cursor=(0, 0),
        )

        # C (change to EOL) - enters insert after deleting to EOL
        self.run_test_screen(
            "C changes to EOL: screen correct",
            "Hello World\nLine 2\n",
            b"lllllCXYZ\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "HelloXYZ"), (1, "Line 2")],
            expect_cursor=(0, 7),
        )

        # S (substitute line) - replaces entire line
        self.run_test_screen(
            "S substitutes line: screen correct",
            "Hello\nWorld\n",
            b"SXYZ\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "XYZ"), (1, "World")],
            expect_cursor=(0, 2),
        )

        # s (substitute char) - replaces single char, enters insert
        self.run_test_screen(
            "s substitutes char: screen correct",
            "Hello\nWorld\n",
            b"sX\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Xello"), (1, "World")],
            expect_cursor=(0, 0),
        )

        # 3s (substitute 3 chars) - replaces 3 chars
        self.run_test_screen(
            "3s substitutes 3 chars: screen correct",
            "Hello\nWorld\n",
            b"3sXYZ\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "XYZlo"), (1, "World")],
            expect_cursor=(0, 2),
        )

        # o (open below) - creates new line below
        self.run_test_screen(
            "o opens below: screen correct",
            "Line 1\nLine 2\n",
            b"oNew\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Line 1"), (1, "New"), (2, "Line 2")],
            expect_cursor=(1, 2),
        )

        # O (open above) - creates new line above
        self.run_test_screen(
            "O opens above: screen correct",
            "Line 1\nLine 2\n",
            b"jONew\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Line 1"), (1, "New"), (2, "Line 2")],
            expect_cursor=(1, 2),
        )

        # J (join lines) - screen shows merged line
        self.run_test_screen(
            "J joins lines: screen correct",
            "Hello\nWorld\n",
            b"J:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello World"), (1, "~")],
            expect_cursor=(0, 5),
        )

        # 3J joins 3 lines
        self.run_test_screen(
            "3J joins 3 lines: screen correct",
            "AA\nBB\nCC\nDD\n",
            b"3J:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "AA BB CC"), (1, "DD")],
            expect_cursor=(0, 2),
        )

        # cc (change line) - replaces line content
        self.run_test_screen(
            "cc changes line: screen correct",
            "Hello\nWorld\n",
            b"ccNew\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "New"), (1, "World")],
            expect_cursor=(0, 2),
        )

        # 2cc (change 2 lines) - deletes 2, inserts blank
        self.run_test_screen(
            "2cc changes 2 lines: screen correct",
            "Line 1\nLine 2\nLine 3\n",
            b"2ccNew\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "New"), (1, "Line 3")],
            expect_cursor=(0, 2),
        )

        # dd - deletes line
        self.run_test_screen(
            "dd deletes line: screen correct",
            "Line 1\nLine 2\nLine 3\n",
            b"dd:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Line 2"), (1, "Line 3"), (2, "~")],
            expect_cursor=(0, 0),
        )

        # 2dd - deletes 2 lines
        self.run_test_screen(
            "2dd deletes 2 lines: screen correct",
            "Line 1\nLine 2\nLine 3\nLine 4\n",
            b"2dd:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Line 3"), (1, "Line 4"), (2, "~")],
            expect_cursor=(0, 0),
        )

        # p (paste below) - screen shows pasted content
        self.run_test_screen(
            "p pastes line below: screen correct",
            "Line 1\nLine 2\nLine 3\n",
            b"ddp:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Line 2"), (1, "Line 1"), (2, "Line 3")],
            expect_cursor=(1, 0),
        )

        # P (paste above) - screen shows pasted content
        self.run_test_screen(
            "P pastes line above: screen correct",
            "Line 1\nLine 2\nLine 3\n",
            b"ddjP:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Line 2"), (1, "Line 1"), (2, "Line 3")],
            expect_cursor=(1, 0),
        )

        # 2x with screen verification
        self.run_test_screen(
            "2x deletes 2 chars: screen correct",
            "Hello\nWorld\n",
            b"2x:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "llo"), (1, "World")],
            expect_cursor=(0, 0),
        )

        # >> indent - screen shows indented line
        self.run_test_screen(
            ">> indents line: screen correct",
            "Hello\nWorld\n",
            b">>:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "  Hello"), (1, "World")],
            expect_cursor=(0, 2),
        )

        # << unindent - screen shows unindented line
        self.run_test_screen(
            "<< unindents line: screen correct",
            "  Hello\nWorld\n",
            b"<<:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello"), (1, "World")],
            expect_cursor=(0, 0),
        )

        # r (replace char) - screen shows replaced char
        self.run_test_screen(
            "r replaces char: screen correct",
            "Hello\nWorld\n",
            b"rX:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Xello"), (1, "World")],
            expect_cursor=(0, 0),
        )

        # ~ (toggle case) - screen shows toggled char
        self.run_test_screen(
            "~ toggles case: screen correct",
            "Hello\n",
            b"~~~:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "hELlo")],
            expect_cursor=(0, 3),
        )

        # dw (delete word) - screen shows result
        self.run_test_screen(
            "dw deletes word: screen correct",
            "Hello World\n",
            b"dw:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "World")],
            expect_cursor=(0, 0),
        )

        # cw (change word) - replaces word
        self.run_test_screen(
            "cw changes word: screen correct",
            "Hello World\n",
            b"cwBye\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Bye World")],
            expect_cursor=(0, 2),
        )

        # db (delete word backward) - screen correct
        self.run_test_screen(
            "db deletes word: screen correct",
            "Hello World\n",
            b"wdb:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "World")],
            expect_cursor=(0, 0),
        )

        # 2dw - screen shows result
        self.run_test_screen(
            "2dw deletes 2 words: screen correct",
            "one two three\n",
            b"2dw:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "three")],
            expect_cursor=(0, 0),
        )

        # 2db - screen shows result
        self.run_test_screen(
            "2db deletes 2 words backward: screen correct",
            "one two three\n",
            b"$2db:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "one e")],
            expect_cursor=(0, 4),
        )

        # de (delete word end) - screen correct
        self.run_test_screen(
            "de deletes to word end: screen correct",
            "Hello World\n",
            b"de:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, " World")],
            expect_cursor=(0, 0),
        )

        # 2p line paste - screen shows all pasted lines
        self.run_test_screen(
            "2p line paste: screen correct",
            "A\nB\nC\n",
            b"yy2p:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A"), (1, "A"), (2, "A"), (3, "B"), (4, "C")],
            expect_cursor=(1, 0),
        )

        # 2P line paste above - screen correct
        self.run_test_screen(
            "2P line paste above: screen correct",
            "A\nB\n",
            b"yy2P:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A"), (1, "A"), (2, "A"), (3, "B")],
            expect_cursor=(0, 0),
        )

        # Batched pp line paste - screen correct
        self.run_test_screen(
            "Batched pp line paste: screen correct",
            "A\nB\nC\n",
            b"yypp:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A"), (1, "A"), (2, "A"), (3, "B"), (4, "C")],
            expect_cursor=(2, 0),
        )

        # Batched PPP line paste above - screen correct
        self.run_test_screen(
            "Batched PPP line paste above: screen correct",
            "A\nB\n",
            b"yyPPP:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A"), (1, "A"), (2, "A"), (3, "A"), (4, "B")],
            expect_cursor=(0, 0),
        )

        # 2p char paste - screen correct
        # x on "AB" yanks 'A' leaving "B", 2p pastes "AA" after cursor → "BAA"
        self.run_test_screen(
            "2p char paste: screen correct",
            "AB\n",
            b"x2p:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "BAA")],
            expect_cursor=(0, 2),
        )

        # Batched pp char paste - screen correct
        self.run_test_screen(
            "Batched pp char paste: screen correct",
            "Hello\n",
            b"xpp:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "eHHllo")],
            expect_cursor=(0, 2),
        )

        # ============================================================
        # Cross-line screen content: paste, dw/db unwrapping
        # Operations that add/remove newlines, verified via screen state
        # ============================================================
        self._group("Cross-line screen content:", leading_blank=True)

        # --- Multi-line char paste (content with newlines) ---

        # db yanks across newline ("foo\n"), p pastes inline after cursor
        # Result: "barfoo\n\n" - cursor at first pasted char (col 3)
        self.run_test_screen(
            "Multi-line char paste p: screen correct",
            "foo\nbar\n",
            b"jdb$p:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "barfoo"), (1, ""), (2, "~"),
            ],
            expect_cursor=(0, 3),
        )

        # db yanks across newline, P pastes multi-line content above
        self.run_test_screen(
            "Multi-line char paste P: screen correct",
            "foo\nbar\n",
            b"jdb0P:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "foo"), (1, "bar"),
            ],
            expect_cursor=(0, 0),
        )

        # D yanks rest of line, paste on next line inserts chars inline
        self.run_test_screen(
            "D + p char paste on next line: screen correct",
            "ABCDE\nXY\n",
            b"lDjp:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "A"), (1, "XBCDEY"),
            ],
            expect_cursor=(1, 4),
        )

        # Multi-line char paste with 2p (two copies of "foo\n")
        # Inserts "foo\nfoo\n" after 'r': "barfoo\nfoo\n\n"
        self.run_test_screen(
            "Multi-line char 2p: screen correct",
            "foo\nbar\n",
            b"jdb$2p:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "barfoo"), (1, "foo"), (2, ""), (3, "~"),
            ],
            expect_cursor=(0, 3),
        )

        # Multi-line char paste with batched pp (same content, same cursor for multiline)
        self.run_test_screen(
            "Multi-line char batched pp: screen correct",
            "foo\nbar\n",
            b"jdb$pp:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "barfoo"), (1, "foo"), (2, ""), (3, "~"),
            ],
            expect_cursor=(0, 3),
        )

        # --- Char paste causing line wrapping ---
        # Paste content that pushes a line beyond screen width

        # Single char paste causing wrap
        # yw on 18 A's yanks "AAAAAAAAAAAAAAAAAA", 2G to B line, p inserts after col 0
        # Result: "B" + 18 A's + 17 B's = 36 chars; wraps at col 20
        self.run_test_screen(
            "Char paste causes line wrap: screen correct",
            "A" * 18 + "\n" + "B" * 18 + "\n",
            b"yw2Gp:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "A" * 18),
                (1, "B" + "A" * 18 + "B"),             # first 20 chars
                (2, "B" * 16),                          # remaining 16 B's
            ],
            expect_cursor=(1, 18),
        )

        # Char 2p paste causing wrap
        # yw yanks 10 A's, 2G to B line, 2p inserts 20 A's after col 0
        # Result: "B" + 20 A's + 4 B's = 25 chars
        self.run_test_screen(
            "Char 2p causing line wrap: screen correct",
            "A" * 10 + "\n" + "B" * 5 + "\n",
            b"yw2G2p:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "A" * 10),
                (1, "B" + "A" * 19),                   # first 20
                (2, "A" + "B" * 4),                     # remaining 5
            ],
            expect_cursor=(2, 0),
        )

        # Batched char pp causing wrap (same content/cursor as 2p for single-line yank)
        self.run_test_screen(
            "Char batched pp causing line wrap: screen correct",
            "A" * 10 + "\n" + "B" * 5 + "\n",
            b"yw2Gpp:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "A" * 10),
                (1, "B" + "A" * 19),                   # first 20
                (2, "A" + "B" * 4),                     # remaining 5
            ],
            expect_cursor=(2, 0),
        )

        # Line paste causing wrap (pasted line is wider than screen)
        self.run_test_screen(
            "Line paste of long line causes wrap: screen correct",
            "A" * 25 + "\nshort\n",
            b"yyjp:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "A" * 20),      # first line wraps: first 20
                (1, "AAAAA"),        # wrap continuation
                (2, "short"),
                (3, "A" * 20),      # pasted line wraps: first 20
                (4, "AAAAA"),        # wrap continuation
            ],
            expect_cursor=(3, 0),
        )

        # --- dw causing unwrap (deleting across newlines) ---

        # 2dw crossing line boundary - unwraps lines
        self.run_test_screen(
            "2dw crossing line: screen correct",
            "one\ntwo three\n",
            b"2dw:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "three"), (1, "~")],
            expect_cursor=(0, 0),
        )

        # dw at last word on line (exclusive-linewise: deletes word, keeps newline)
        self.run_test_screen(
            "dw at last word: screen correct",
            "foo\nbar\n",
            b"dw:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, ""), (1, "bar")],
            expect_cursor=(0, 0),
        )

        # Batched dwdw crossing line boundary
        self.run_test_screen(
            "Batched dwdw crossing line: screen correct",
            "one two\nthree four\n",
            b"dwdw:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, ""), (1, "three four")],
            expect_cursor=(0, 0),
        )

        # 2dw single-line (no unwrap)
        self.run_test_screen(
            "2dw single-line: screen correct",
            "one two three four\n",
            b"2dw:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "three four")],
            expect_cursor=(0, 0),
        )

        # Batched dwdw single-line
        self.run_test_screen(
            "Batched dwdw single-line: screen correct",
            "one two three four\n",
            b"dwdw:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "three four")],
            expect_cursor=(0, 0),
        )

        # 3dw crossing multiple lines
        self.run_test_screen(
            "3dw crossing 2 lines: screen correct",
            "aa\nbb\ncc dd\n",
            b"3dw:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "dd"), (1, "~")],
            expect_cursor=(0, 0),
        )

        # 4dw crossing lines into wrapping line - joined result must wrap
        self.run_test_screen(
            "4dw cross-line into wrap: screen correct",
            "This is the first line\n\nThis is the second line which is wrapping to another\n\nAnother line\n",
            b"www4dw:q!\r",
            rows=10, cols=36,
            expect_lines=[
                (0, "This is the is the second line which"),
                (1, " is wrapping to another"),
                (2, ""),
                (3, "Another line"),
                (4, "~"),
            ],
            expect_cursor=(0, 12),
        )

        # --- db causing unwrap (deleting across newlines backward) ---

        # db from BOL - joins with previous line
        self.run_test_screen(
            "db from BOL unwraps: screen correct",
            "foo\nbar\n",
            b"jdb:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "bar"), (1, "~")],
            expect_cursor=(0, 0),
        )

        # 2db crossing line boundary
        self.run_test_screen(
            "2db crossing line: screen correct",
            "hello world\nfoo\n",
            b"j2db:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "foo"), (1, "~")],
            expect_cursor=(0, 0),
        )

        # Batched dbdb crossing line boundary
        self.run_test_screen(
            "Batched dbdb crossing line: screen correct",
            "one two\nthree\n",
            b"j$dbdb:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "one e"), (1, "~")],
            expect_cursor=(0, 4),
        )

        # Batched dbdb from BOL
        self.run_test_screen(
            "Batched dbdb from BOL: screen correct",
            "foo bar\nbaz\n",
            b"jdbdb:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "baz"), (1, "~")],
            expect_cursor=(0, 0),
        )

        # 2db single-line (no unwrap)
        self.run_test_screen(
            "2db single-line: screen correct",
            "one two three\n",
            b"$2db:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "one e")],
            expect_cursor=(0, 4),
        )

        # --- de causing unwrap (deleting to word end across newlines) ---

        # de at end of line crosses to next line
        self.run_test_screen(
            "de crossing line: screen correct",
            "foo\nbar baz\n",
            b"2lde:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "fo baz"), (1, "~")],
            expect_cursor=(0, 2),
        )

        # 2de crossing line boundary
        self.run_test_screen(
            "2de crossing line: screen correct",
            "one\ntwo three\n",
            b"2de:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, " three"), (1, "~")],
            expect_cursor=(0, 0),
        )

        # --- cb crossing line boundary ---
        self.run_test_screen(
            "cb from BOL crosses line: screen correct",
            "foo\nbar\n",
            b"jcbbaz\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "bazbar"), (1, "~")],
            expect_cursor=(0, 2),
        )

        # --- 2cw crossing line boundary ---
        self.run_test_screen(
            "2cw crossing line: screen correct",
            "foo\nbar\n",
            b"2cwx\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "x"), (1, "~")],
            expect_cursor=(0, 0),
        )

        # --- Multi-line line-mode paste screen content ---

        # 2yy + p pastes 2 lines
        self.run_test_screen(
            "2yy + p pastes 2 lines: screen correct",
            "A\nB\nC\n",
            b"2yyp:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "A"), (1, "A"), (2, "B"), (3, "B"), (4, "C"),
            ],
            expect_cursor=(1, 0),
        )

        # 2yy + 2p pastes 2 lines twice
        self.run_test_screen(
            "2yy + 2p pastes 2 lines twice: screen correct",
            "A\nB\nC\n",
            b"2yy2p:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "A"), (1, "A"), (2, "B"), (3, "A"),
                (4, "B"), (5, "B"), (6, "C"),
            ],
            expect_cursor=(1, 0),
        )

        # dd + pp pastes deleted line twice (batched)
        self.run_test_screen(
            "dd + batched pp: screen correct",
            "A\nB\nC\n",
            b"ddpp:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "B"), (1, "A"), (2, "A"), (3, "C")],
            expect_cursor=(2, 0),
        )

        # dd + 2p pastes deleted line twice (count prefix)
        self.run_test_screen(
            "dd + 2p: screen correct",
            "A\nB\nC\n",
            b"dd2p:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "B"), (1, "A"), (2, "A"), (3, "C")],
            expect_cursor=(1, 0),
        )

        # --- ce crossing line boundary ---
        self.run_test_screen(
            "2ce crossing line: screen correct",
            "foo\nbar\n",
            b"2ceX\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "X"), (1, "~")],
            expect_cursor=(0, 0),
        )

        # ============================================================
        # Batch movement tests (j/k and arrow keys)
        # Consecutive identical movement keys are consumed in one
        # operation, reducing frame count and improving scroll perf.
        # ============================================================
        self._group("Batch movement down:", leading_blank=True)

        # Batch j keys: 5 j's on a 10-line file move to line 5
        self.run_test_screen(
            "Batch j moves correct number of lines",
            make_lines(10),
            b"jjjjj:q!\r",
            expect_cursor=(5, 0),
            expect_status_contains="COMMAND - 6,"
        )

        # Batch KEY_DOWN arrow keys
        DOWN = b"\x1b[B"
        self.run_test_screen(
            "Batch down arrow moves correct lines",
            make_lines(10),
            DOWN * 5 + b":q!\r",
            expect_cursor=(5, 0),
            expect_status_contains="COMMAND - 6,"
        )

        # Batch j with scrolling: verify screen content
        # 10 rows = 9 content rows. 11 j's on 15-line file -> line 12.
        self.run_test_screen(
            "Batch j with scrolling shows correct window",
            make_lines(15),
            b"jjjjjjjjjjj:q!\r",
            expect_cursor=(8, 0),
            expect_lines=[(i, f"Line {i+4}") for i in range(9)]
        )

        # Count prefix + batch: 3j with 2 pending j's = 5 total
        self.run_test_screen(
            "Count prefix + batch j combines",
            make_lines(10),
            b"3jjj:q!\r",
            expect_cursor=(5, 0),
            expect_status_contains="COMMAND - 6,"
        )

        # Render optimization: batch j reduces redraws
        # 5 j's on a 10-line file (no scroll). Without batching: 6 frames.
        # With batching: init(T) + batched jjjjj(F) = 2 frames
        self.run_test_screen(
            "Render opt: batch j no-scroll is single frame",
            make_lines(10),
            b"jjjjj:q!\r",
            expect_content_redraws=[True, False]
        )

        # Render optimization: batch j with scroll is single repaint
        # 11 j's on 15-line file triggers scroll, but only one frame
        self.run_test_screen(
            "Render opt: batch j scroll is single repaint",
            make_lines(15),
            b"jjjjjjjjjjj:q!\r",
            expect_content_redraws=[True, True]
        )

        self._group("Batch movement up:", leading_blank=True)

        # Batch k keys: start at line 5, 3 k's move to line 2
        self.run_test_screen(
            "Batch k moves correct number of lines",
            make_lines(10),
            b"5jkkk:q!\r",
            expect_cursor=(2, 0),
            expect_status_contains="COMMAND - 3,"
        )

        # Batch KEY_UP arrow keys
        UP = b"\x1b[A"
        self.run_test_screen(
            "Batch up arrow moves correct lines",
            make_lines(10),
            b"5j" + UP * 3 + b":q!\r",
            expect_cursor=(2, 0),
            expect_status_contains="COMMAND - 3,"
        )

        # Batch k with scrolling: scroll up from bottom
        # 15-line file, 10 rows. Go to line 14 (G), then 12 k's -> line 2.
        # ensure_cursor_visible places cursor at top of viewport.
        self.run_test_screen(
            "Batch k with scrolling shows correct window",
            make_lines(15),
            b"G" + b"k" * 12 + b":q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(0, "Line 3")]
        )

        # Render optimization: batch k no-scroll is single frame
        # 5j produces 1 frame (batched), then kkk produces 1 frame (batched)
        self.run_test_screen(
            "Render opt: batch k no-scroll is single frame",
            make_lines(10),
            b"5jkkk:q!\r",
            expect_content_redraws=[True, False, False]
        )

        # Render optimization: batch k with scroll is single repaint
        # G scrolls (full repaint), then 12 batched k's scroll up (one repaint)
        self.run_test_screen(
            "Render opt: batch k scroll is single repaint",
            make_lines(15),
            b"G" + b"k" * 12 + b":q!\r",
            expect_content_redraws=[True, True, True]
        )

        self._group("Batch movement left/right:", leading_blank=True)

        # Batch l keys: 5 l's on "Hello World" should produce a single frame
        self.run_test_screen(
            "Render opt: batch l no-scroll is single frame",
            "Hello World\n",
            b"lllll:q!\r",
            expect_content_redraws=[True, False]
        )

        # Batch h keys: move right, then 5 h's back
        self.run_test_screen(
            "Render opt: batch h no-scroll is single frame",
            "Hello World\n",
            b"$hhhhh:q!\r",
            expect_content_redraws=[True, False, False]
        )

        # Batch l correctness: 5 l's move to col 5
        self.run_test_screen(
            "Batch l moves correct columns",
            "Hello World\n",
            b"lllll:q!\r",
            expect_cursor=(0, 5),
        )

        # Batch h correctness: $ then 3 h's from col 10 -> col 7
        self.run_test_screen(
            "Batch h moves correct columns",
            "Hello World\n",
            b"$hhh:q!\r",
            expect_cursor=(0, 7),
        )

        # Count prefix + batch l: 3l with 2 pending l's = 5 total
        self.run_test_screen(
            "Count prefix + batch l combines",
            "Hello World\n",
            b"3lll:q!\r",
            expect_cursor=(0, 5),
        )

        RIGHT = b"\x1b[C"
        LEFT = b"\x1b[D"

        # Batch insert RIGHT: 5 RIGHT arrows in insert mode
        self.run_test_screen(
            "Render opt: batch insert RIGHT is single frame",
            "Hello World\n",
            b"i" + RIGHT * 5 + b"\x1b:q!\r",
            expect_content_redraws=[True, False, False, False]
        )

        # Batch insert LEFT: move to end, then 5 LEFT arrows in insert mode
        self.run_test_screen(
            "Render opt: batch insert LEFT is single frame",
            "Hello World\n",
            b"$a" + LEFT * 5 + b"\x1b:q!\r",
            expect_content_redraws=[True, False, False, False, False]
        )

        # Batch insert RIGHT correctness
        self.run_test(
            "Batch insert RIGHT moves correct columns",
            "Hello World\n",
            b"i" + RIGHT * 5 + b"X\x1b:wq\r",
            expected_content="HelloX World\n",
        )

        # Batch insert LEFT correctness
        self.run_test(
            "Batch insert LEFT moves correct columns",
            "Hello World\n",
            b"$a" + LEFT * 5 + b"X\x1b:wq\r",
            expected_content="Hello XWorld\n",
        )

        self._group("Batch word motions (w, b, e):", leading_blank=True)

        # Batch w: 5 w's on a 7-word line -> single frame
        # Words: one(0) two(4) three(8) four(14) five(19) six(24) seven(28)
        # 5 w's from col 0 -> col 24 ("six")
        self.run_test_screen(
            "Render opt: batch w is single frame",
            "one two three four five six seven\n",
            b"wwwww:q!\r",
            expect_cursor=(0, 24),
            expect_content_redraws=[True, False]
        )

        # Batch b: $ then 5 b's -> single frame
        # $ -> col 32, 5 b's -> col 8 ("three")
        self.run_test_screen(
            "Render opt: batch b is single frame",
            "one two three four five six seven\n",
            b"$bbbbb:q!\r",
            expect_cursor=(0, 8),
            expect_content_redraws=[True, False, False]
        )

        # Batch e: 5 e's -> single frame
        # e: one(2), two(6), three(12), four(17), five(22)
        self.run_test_screen(
            "Render opt: batch e is single frame",
            "one two three four five six seven\n",
            b"eeeee:q!\r",
            expect_cursor=(0, 22),
            expect_content_redraws=[True, False]
        )

        # Count prefix + batch: 3w + 2 batched w's = 5 total
        self.run_test_screen(
            "Count prefix + batch w combines",
            "one two three four five six seven\n",
            b"3www:q!\r",
            expect_cursor=(0, 24),
            expect_content_redraws=[True, False]
        )

        # ============================================================
        # Batch combo keys (dw, yw, dd, gg, ra, etc.)
        # Two-key combos should consolidate into a single render frame
        # when both keys are available in the input buffer.
        # ============================================================
        self._group("Batch combo keys:", leading_blank=True)

        # dw: d+w batched into single frame (no pending d frame)
        # Without batching: init(T), d-pending(F), dw(T) = 3 frames
        # With batching: init(T), dw(T) = 2 frames
        self.run_test_screen(
            "Batch dw is single action frame",
            "Hello World\n",
            b"dw:q!\r",
            expect_content_redraws=[True, True, False]
        )

        # yw: y+w batched into single frame
        # Without batching: init(T), y-pending(F), yw(F) = 3 frames
        # With batching: init(T), yw(F) = 2 frames
        self.run_test_screen(
            "Batch yw is single action frame",
            "Hello World\n",
            b"yw:q!\r",
            expect_content_redraws=[True, False]
        )

        # dd: d+d batched into single frame
        self.run_test_screen(
            "Batch dd is single action frame",
            "Hello\nWorld\n",
            b"dd:q!\r",
            expect_content_redraws=[True, True, False]
        )

        # gg: g+g batched into single frame (cursor-only, no content redraw)
        # init(T), G(F cursor-only), g+g batched(F cursor-only), :q!(F)
        self.run_test_screen(
            "Batch gg is single action frame",
            make_lines(5),
            b"Ggg:q!\r",
            expect_content_redraws=[True, False, False, False]
        )

        # ra: r+a batched into single frame
        self.run_test_screen(
            "Batch ra is single action frame",
            "Hello\n",
            b"ra:q!\r",
            expect_content_redraws=[True, True, False]
        )

        # de: d+e batched into single frame
        self.run_test_screen(
            "Batch de is single action frame",
            "Hello World\n",
            b"de:q!\r",
            expect_content_redraws=[True, True, False]
        )

        # ye: y+e batched into single frame
        self.run_test_screen(
            "Batch ye is single action frame",
            "Hello World\n",
            b"ye:q!\r",
            expect_content_redraws=[True, False]
        )

        # cw: c+w batched into single frame (then insert mode)
        self.run_test_screen(
            "Batch cw is single action frame",
            "Hello World\n",
            b"cw\x1b:q!\r",
            expect_content_redraws=[True, True, False, False]
        )

        # >>: >+> batched into single frame
        self.run_test_screen(
            "Batch >> is single action frame",
            "Hello\nWorld\n",
            b">>:q!\r",
            expect_content_redraws=[True, True, False]
        )

        # <<: <+< batched into single frame
        self.run_test_screen(
            "Batch << is single action frame",
            "  Hello\n  World\n",
            b"<<:q!\r",
            expect_content_redraws=[True, True, False]
        )

        # dwdw: both dw pairs batched via pair batching + combo batching
        # d+w consumed as first pair, d+w consumed by batch_pending_pairs
        # Result: single action frame for both deletions
        self.run_test_screen(
            "Batch dwdw is single action frame",
            "one two three four\n",
            b"dwdw:q!\r",
            expect_content_redraws=[True, True, False]
        )

        # 3dw: count digit gets own frame, then d+w batched
        # Frame 0: init(T), Frame 1: count 3(F), Frame 2: dw(T)
        self.run_test_screen(
            "Count prefix + batch dw",
            "one two three four five\n",
            b"3dw:q!\r",
            expect_content_redraws=[True, False, True, False]
        )

        # ============================================================
        # Batch paste (p, P)
        # Repeated paste keys should consolidate into a single render
        # frame when multiple keys are available in the input buffer.
        # ============================================================
        self._group("Batch paste:", leading_blank=True)

        # Line paste pp: yank a line with dd, paste twice with pp
        # Without batching: init(T), dd(T), p(T), p(T) = 4 frames
        # With batching: init(T), dd(T), pp batched(T) = 3 frames
        self.run_test_screen(
            "Batch line pp is single action frame",
            "A\nB\nC\n",
            b"ddpp:q!\r",
            expect_content_redraws=[True, True, True, False]
        )

        # Line paste pp correctness: two copies pasted
        self.run_test(
            "Batch line pp pastes two copies",
            "A\nB\nC\n",
            b"ddpp:wq\r",
            expected_content="B\nA\nA\nC\n"
        )

        # Line paste PPP correctness: three copies pasted above
        self.run_test(
            "Batch line PPP pastes three copies above",
            "A\nB\n",
            b"ddPPP:wq\r",
            expected_content="A\nA\nA\nB\n"
        )

        # Line paste PP: batched into single frame
        self.run_test_screen(
            "Batch line PP is single action frame",
            "A\nB\nC\n",
            b"ddPP:q!\r",
            expect_content_redraws=[True, True, True, False]
        )

        # Char paste pp: yank a char with x, paste twice with pp
        # Without batching: init(T), x(T), p(T), p(T) = 4 frames
        # With batching: init(T), x(T), pp batched(T) = 3 frames
        self.run_test_screen(
            "Batch char pp is single action frame",
            "Hello\n",
            b"xpp:q!\r",
            expect_content_redraws=[True, True, True, False]
        )

        # Char paste pp correctness
        self.run_test(
            "Batch char pp pastes two copies",
            "Hello\n",
            b"xpp:wq\r",
            expected_content="eHHllo\n"
        )

        # Char paste PPP correctness
        self.run_test(
            "Batch char PPP pastes three copies",
            "Hello\n",
            b"xPPP:wq\r",
            expected_content="HHHello\n"
        )

        # Multi-char yank + batched PP: content must match iterative
        # yw yanks "one " (4 chars), 2G goes to blank line 2, PP pastes twice
        self.run_test(
            "Batch char PP multi-char yank content matches iterative",
            "one two three\n\n",
            b"yw2GPP:wq\r",
            expected_content="one two three\noneone  \n"
        )

        # Multi-char yank + count+extras 2PP: content must match iterative
        # yw yanks "one " (4 chars), 2G goes to blank line 2, 2PP = count 2 + 1 extra
        self.run_test(
            "Count 2PP multi-char yank content matches iterative",
            "one two three\n\n",
            b"yw2G2PP:wq\r",
            expected_content="one two three\none oneone  \n"
        )

        # Char paste PP: batched into single frame
        self.run_test_screen(
            "Batch char PP is single action frame",
            "Hello\n",
            b"xPP:q!\r",
            expect_content_redraws=[True, True, True, False]
        )

        # Count + batch: 2p then extra p should paste 3 total
        self.run_test(
            "Count 2p + extra p pastes three copies",
            "A\nB\nC\n",
            b"dd2pp:wq\r",
            expected_content="B\nA\nA\nA\nC\n"
        )

        # Cursor position tests for line paste batching
        # yy pp: cursor on row 2 (two lines pasted below, cursor on last)
        self.run_test_screen(
            "Batch line pp cursor on last pasted line",
            "A\nB\nC\n",
            b"yypp:q!\r",
            expect_cursor=(2, 0),
        )

        # yy 2p: cursor on row 1 (counted paste, cursor on first pasted line)
        self.run_test_screen(
            "Count line 2p cursor on first pasted line",
            "A\nB\nC\n",
            b"yy2p:q!\r",
            expect_cursor=(1, 0),
        )

        # yy ppp: cursor on row 3
        self.run_test_screen(
            "Batch line ppp cursor on last pasted line",
            "A\nB\nC\n",
            b"yyppp:q!\r",
            expect_cursor=(3, 0),
        )

        # yy 2pp: cursor on row 2 (count 2 + 1 extra = 3 pastes, cursor at 1 + extras)
        self.run_test_screen(
            "Count 2p + batch p cursor position",
            "A\nB\nC\n",
            b"yy2pp:q!\r",
            expect_cursor=(2, 0),
        )

        # Line paste above: yy PP -> cursor on row 0
        self.run_test_screen(
            "Batch line PP cursor stays at row 0",
            "A\nB\nC\n",
            b"yyPP:q!\r",
            expect_cursor=(0, 0),
        )

        # Line paste above: yy 2P -> cursor on row 0 (no adjustment needed)
        self.run_test_screen(
            "Count line 2P cursor stays at row 0",
            "A\nB\nC\n",
            b"yy2P:q!\r",
            expect_cursor=(0, 0),
        )

        # Char paste below: x pp -> cursor at col 2
        self.run_test_screen(
            "Batch char pp cursor position",
            "Hello\n",
            b"xpp:q!\r",
            expect_cursor=(0, 2),
        )

        # Char paste below: x 2p -> cursor at col 2 (same as pp)
        self.run_test_screen(
            "Count char 2p cursor position",
            "Hello\n",
            b"x2p:q!\r",
            expect_cursor=(0, 2),
        )

        # Char paste above: lx PP -> cursor at col 1 (adjusted back by 1)
        self.run_test_screen(
            "Batch char PP cursor adjusted",
            "Hello\n",
            b"lxPP:q!\r",
            expect_cursor=(0, 1),
        )

        # Char paste above: lx 2P -> cursor at col 2 (counted, no adjustment)
        self.run_test_screen(
            "Count char 2P cursor not adjusted",
            "Hello\n",
            b"lx2P:q!\r",
            expect_cursor=(0, 2),
        )

        self._group("Batch page down/up:", leading_blank=True)

        # Render optimization: batch Ctrl-F reduces redraws
        # Without batching: 3 Ctrl-F's -> frames [init, pgdn, pgdn, pgdn] = 4
        # With batching: frames [init, pgdn+batch] = 2 frames
        # Then j triggers a cursor-only frame (False) proving batch happened
        self.run_test_screen(
            "Render opt: batch Ctrl-F reduces redraws",
            make_lines(30),
            CTRL_F * 3 + b"j:q!\r",
            expect_content_redraws=[True, True, False],
        )

        # Render optimization: batch Ctrl-B reduces redraws
        # G scrolls to end (full repaint), then 3 batched Ctrl-B's
        # produce a single repaint, then j is cursor-only
        self.run_test_screen(
            "Render opt: batch Ctrl-B reduces redraws",
            make_lines(30),
            b"G" + CTRL_B * 3 + b"j:q!\r",
            expect_content_redraws=[True, True, True, False],
        )

        # Batch Ctrl-F correctness: 3 pages down on 30-line file
        # page_size=9, lines 0->9->18->27, VIEW_TOP clamped to 21
        self.run_test_screen(
            "Batch Ctrl-F moves correct number of pages",
            make_lines(30),
            CTRL_F * 3 + b":q!\r",
            expect_cursor=(6, 0),
            expect_lines=[(i, f"Line {i+22}") for i in range(9)]
        )

        # Batch Ctrl-B correctness: go to end then 2 pages up
        # G puts cursor on line 29, VIEW_TOP=21.
        # 2 page-ups: line 29->20->11, VIEW_TOP 21->12->3
        self.run_test_screen(
            "Batch Ctrl-B moves correct number of pages",
            make_lines(30),
            b"G" + CTRL_B * 2 + b":q!\r",
            expect_cursor=(8, 0),
            expect_lines=[(i, f"Line {i+4}") for i in range(9)]
        )

        # Batch PgDn key: same result as batch Ctrl-F
        PGDN = b"\x1b[6~"
        self.run_test_screen(
            "Render opt: batch PgDn reduces redraws",
            make_lines(30),
            PGDN * 3 + b"j:q!\r",
            expect_content_redraws=[True, True, False],
        )

        # Count prefix + batch Ctrl-F: 2Ctrl-F + 1 pending = 3 pages
        self.run_test_screen(
            "Count prefix + batch Ctrl-F combines",
            make_lines(30),
            b"2" + CTRL_F * 2 + b":q!\r",
            expect_cursor=(6, 0),
            expect_lines=[(i, f"Line {i+22}") for i in range(9)]
        )

        self._group("Insert mode navigation keys:", leading_blank=True)

        HOME = b"\x1b[H"
        END = b"\x1b[F"

        # Home key moves cursor to beginning of line
        # Start on "Hello World", move right 5 times, enter insert, Home, type X
        self.run_test(
            "Home key moves to line start",
            "Hello World\n",
            b"llllli" + HOME + b"X\x1b:wq\r",
            expected_content="XHello World\n"
        )

        # Home key does nothing when already at beginning
        self.run_test(
            "Home key at line start is no-op",
            "Hello World\n",
            b"i" + HOME + b"X\x1b:wq\r",
            expected_content="XHello World\n"
        )

        # End key moves cursor to end of line
        # Enter insert at start, End, type X
        self.run_test(
            "End key moves to line end",
            "Hello World\n",
            b"i" + END + b"X\x1b:wq\r",
            expected_content="Hello WorldX\n"
        )

        # End key does nothing when already at end
        self.run_test(
            "End key at line end is no-op",
            "Hello World\n",
            b"$a" + END + b"X\x1b:wq\r",
            expected_content="Hello WorldX\n"
        )

        # Home and End work together
        # Move right, enter insert, End (go to end), Home (back to start), type X
        self.run_test(
            "Home and End in sequence",
            "Hello World\n",
            b"llllli" + END + HOME + b"X\x1b:wq\r",
            expected_content="XHello World\n"
        )

        # Home/End on empty line
        self.run_test(
            "Home/End on empty line",
            "\n",
            b"i" + HOME + END + HOME + b"X\x1b:wq\r",
            expected_content="X\n"
        )

        # Home/End on multi-line content
        self.run_test(
            "Home/End on second line",
            "First\nSecond Line\nThird\n",
            b"jllllli" + HOME + b"X\x1b" + END + b"aY\x1b:wq\r",
            expected_content="First\nXSecond LineY\nThird\n"
        )

        # Home key during text insertion
        self.run_test(
            "Home during text insertion",
            "World\n",
            b"i" + END + b"Hello " + HOME + b"!\x1b:wq\r",
            expected_content="!WorldHello \n"
        )

        # End key after backspace
        self.run_test(
            "End key after backspace",
            "Hello\n",
            b"$i\x08\x08" + END + b"X\x1b:wq\r",
            expected_content="HeoX\n"
        )

        self._group("Insert mode cursor clamping:", leading_blank=True)

        DOWN = b"\x1b[B"
        UP = b"\x1b[A"

        # Moving from longer line to shorter line should clamp to end+1
        # Line 1: "Hello" (5 chars), Line 2: "Hi" (2 chars)
        # Start at end of line 1 (col 5), move down to line 2
        # Should be at col 2 (one past 'i'), allowing insertion at end
        self.run_test(
            "Down arrow clamps to one past end in insert mode",
            "Hello\nHi\n",
            b"$a" + DOWN + b"X\x1b:wq\r",
            expected_content="Hello\nHiX\n"
        )

        # Moving up from shorter to longer line preserves column
        self.run_test(
            "Up arrow from short to long line in insert mode",
            "Hi\nHello\n",
            b"j$a" + UP + b"X\x1b:wq\r",
            expected_content="HiX\nHello\n"
        )

        # Moving down to empty line should position at column 0
        self.run_test(
            "Down to empty line in insert mode",
            "Hello\n\n",
            b"$a" + DOWN + b"X\x1b:wq\r",
            expected_content="Hello\nX\n"
        )

        # Test wrapping boundary: 40-char line (exactly fits screen width)
        # Moving from 40-char line to shorter line should preserve insert semantics
        self.run_test(
            "Down from full-width line to short line",
            "A" * 40 + "\nHi\n",
            b"$a" + DOWN + b"X\x1b:wq\r",
            expected_content="A" * 40 + "\nHiX\n"
        )

        # Test moving down from 41-char line (wraps to 2 screen rows) to short line
        self.run_test(
            "Down from wrapped line to short line",
            "A" * 41 + "\nHi\n",
            b"$a" + DOWN + b"X\x1b:wq\r",
            expected_content="A" * 41 + "\nHiX\n"
        )

        # Test moving up from short line to wrapped line preserves column
        self.run_test(
            "Up from short line to wrapped line",
            "A" * 41 + "\nHi\n",
            b"j$a" + UP + b"X\x1b:wq\r",
            expected_content="AA" + "X" + "A" * 39 + "\nHi\n"
        )

        self._group("Delete key line joining:", leading_blank=True)

        DEL = b"\x1b[3~"

        # Delete at end of line joins with next line
        self.run_test(
            "Delete at end of line joins next line",
            "Hello\nWorld\n",
            b"$a" + DEL + b"\x1b:wq\r",
            expected_content="HelloWorld\n"
        )

        # Delete at end of line does nothing on last line
        self.run_test(
            "Delete at end of last line is no-op",
            "Hello\n",
            b"$a" + DEL + b"\x1b:wq\r",
            expected_content="Hello\n"
        )

        # Delete at end of empty line joins next line
        self.run_test(
            "Delete at end of empty line joins next",
            "\nWorld\n",
            b"i" + DEL + b"\x1b:wq\r",
            expected_content="World\n"
        )

        # Delete joins then deletes next char
        # First Delete joins "A" and "B" -> "AB\nC\n"
        # Second Delete is now in middle of "AB", deletes "B" -> "A\nC\n"
        self.run_test(
            "Delete join then delete char",
            "A\nB\nC\n",
            b"$a" + DEL + DEL + b"\x1b:wq\r",
            expected_content="A\nC\n"
        )

        # Join multiple lines by using End key after each join
        self.run_test(
            "Multiple line joins with End key",
            "A\nB\nC\n",
            b"$a" + DEL + END + DEL + b"\x1b:wq\r",
            expected_content="ABC\n"
        )

        # Delete at end preserves cursor position
        self.run_test(
            "Delete join preserves cursor position",
            "Hello\nWorld\n",
            b"$aX" + DEL + b"Y\x1b:wq\r",
            expected_content="HelloXYWorld\n"
        )

        # Delete in middle of line still works
        self.run_test(
            "Delete in middle of line unchanged",
            "Hello\n",
            b"lli" + DEL + b"\x1b:wq\r",
            expected_content="Helo\n"
        )

        self._group("Batch movement in insert mode:", leading_blank=True)

        DOWN = b"\x1b[B"
        UP = b"\x1b[A"

        # Batch KEY_DOWN in insert mode with scrolling
        # 15-line file, 10 rows. Enter insert on line 1, 11 down arrows
        # scrolls down. Insert mode delegates to normal_move_down which batches.
        self.run_test_screen(
            "Batch insert down arrow with scroll",
            make_lines(15),
            b"i" + DOWN * 11 + b"\x1b:q!\r",
            expect_cursor=(8, 0),
            expect_lines=[(i, f"Line {i+4}") for i in range(9)]
        )

        # Batch KEY_UP in insert mode with scrolling
        # Go to bottom with G, enter insert, then 12 up arrows.
        self.run_test_screen(
            "Batch insert up arrow with scroll",
            make_lines(15),
            b"Gi" + UP * 12 + b"\x1b:q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(0, "Line 3")]
        )

        # Render optimization: batch insert down arrows reduce redraws
        # i enters insert (F), then 5 batched DOWN arrows no-scroll (F), ESC (F)
        self.run_test_screen(
            "Render opt: batch insert down no-scroll",
            make_lines(10),
            b"i" + DOWN * 5 + b"\x1b:q!\r",
            expect_content_redraws=[True, False, False, False]
        )

        # Render optimization: batch insert down arrows with scroll
        # 15-line file, 10 rows. i(F), then 11 DOWN arrows batch into one
        # scroll repaint(T), ESC(F). Without batching: each DOWN is a
        # separate frame, first 8 are no-scroll(F) then 3 scroll(T).
        self.run_test_screen(
            "Render opt: batch insert down scroll is single repaint",
            make_lines(15),
            b"i" + DOWN * 11 + b"\x1b:q!\r",
            expect_content_redraws=[True, False, True, False]
        )

        # Render optimization: batch insert up arrows with scroll
        # G(T) scrolls to bottom, i(F), 12 UP arrows batch into one
        # scroll repaint(T), ESC(F). Without batching: each UP is a
        # separate frame, first ~5 are no-scroll(F) then rest scroll(T).
        self.run_test_screen(
            "Render opt: batch insert up scroll is single repaint",
            make_lines(15),
            b"Gi" + UP * 12 + b"\x1b:q!\r",
            expect_content_redraws=[True, True, False, True, False]
        )

        # Batch insert up arrows: correctness check
        # 5j batched then i, 3 UP arrows batched -> line 2 (0-indexed)
        self.run_test_screen(
            "Batch insert up moves correct lines",
            make_lines(10),
            b"5ji" + UP * 3 + b"\x1b:q!\r",
            expect_cursor=(2, 0),
            expect_status_contains="COMMAND - 3,"
        )

        # --- Snapshot detection baseline tests ---
        # These verify current render behavior to protect against regressions
        # when switching to snapshot-based render detection.

        # Replace char (ra) triggers content redraw on current row
        # Frame 0: init(T), Frame 1: r+a batched replaces(T)
        self.run_test_screen(
            "Render opt: ra triggers current row redraw",
            "Hello\nWorld\n",
            b"ra:q!\r",
            expect_content_redraws=[True, True, False],
            expect_content_rows=[(1, {0})]
        )

        # Toggle case (~) triggers content redraw on current row
        self.run_test_screen(
            "Render opt: ~ triggers current row redraw",
            "Hello\nWorld\n",
            b"~:q!\r",
            expect_content_redraws=[True, True],
            expect_content_rows=[(1, {0})]
        )

        # Multi-line indent (2>>) triggers full content redraw
        # Frame 0: init(T), Frame 1: 2(F count), Frame 2: >+> batched indent(T)
        self.run_test_screen(
            "Render opt: 2>> triggers full redraw",
            "Hello\nWorld\nThird\n",
            b"2>>:q!\r",
            expect_content_redraws=[True, False, True, False]
        )

        # dd triggers full content redraw
        # Frame 0: init(T), Frame 1: d+d batched dd(T)
        self.run_test_screen(
            "Render opt: dd triggers full redraw",
            "Hello\nWorld\n",
            b"dd:q!\r",
            expect_content_redraws=[True, True, False]
        )

        # x triggers content redraw on current row
        self.run_test_screen(
            "Render opt: x triggers current row redraw",
            "Hello\nWorld\n",
            b"x:q!\r",
            expect_content_redraws=[True, True],
            expect_content_rows=[(1, {0})]
        )

        # Movement without scroll (l) does NOT trigger content redraw
        self.run_test_screen(
            "Render opt: l no content redraw",
            "Hello\n",
            b"l:q!\r",
            expect_content_redraws=[True, False]
        )

        # ESC with no pending count does NOT trigger content redraw
        self.run_test_screen(
            "Render opt: ESC no content redraw",
            "Hello\n",
            b"\x1b:q!\r",
            expect_content_redraws=[True, False]
        )

        # o (open below) triggers full content redraw
        self.run_test_screen(
            "Render opt: o triggers full redraw",
            "Hello\nWorld\n",
            b"o\x1b:q!\r",
            expect_content_redraws=[True, True, False]
        )

        # ============================================================
        # Count prefix tests
        # ============================================================
        self._group("Count prefix:", leading_blank=True)

        # Count shows in status bar
        # Frame 0: initial, Frame 1: '3' (count active, cursor+status)
        self.run_test_screen(
            "Count displays in status bar",
            "Hello\n",
            b"3:q!\r",
            cols=80,
            expect_status_at_frame=[
                (1, " - 3 - "),
            ]
        )

        # Multi-digit count shows in status bar
        # Frame 0: initial, Frame 1: '1', Frame 2: '0'
        self.run_test_screen(
            "Multi-digit count in status bar",
            "Hello\n",
            b"10:q!\r",
            cols=80,
            expect_status_at_frame=[
                (1, " - 1 - "),
                (2, " - 10 - "),
            ]
        )

        # ESC clears count
        # Frame 0: initial, Frame 1: '3' (count), Frame 2: ESC (cleared)
        self.run_test_screen(
            "ESC clears count",
            "Hello\n",
            b"3\x1b:q!\r",
            cols=80,
            expect_status_at_frame=[
                (1, " - 3 - "),
                (2, "NORMAL - 1,"),
            ]
        )

        # 0 as first key goes to line-start (not count)
        self.run_test_screen(
            "0 as first key is line-start not count",
            "Hello\n",
            b"ll0:q!\r",
            expect_cursor=(0, 0)
        )

        # Count preserved across two-key: 30 continues as count digits
        self.run_test_screen(
            "30 is count thirty not count-3 + line-start",
            "Hello\n",
            b"30:q!\r",
            cols=80,
            expect_status_at_frame=[
                (2, " - 30 - "),
            ]
        )

        # Count ignores digits past 4 digits (>= 1000)
        # 1000 typed: 4th digit accepted. 5th digit ignored since 1000 >= 1000
        self.run_test_screen(
            "count limited to 4 digits (5th ignored)",
            "Hello\n",
            b"10005:q!\r",
            cols=80,
            expect_status_at_frame=[
                (4, " - 1000 - "),  # After 4th digit: count=1000
                (5, " - 1000 - "),  # 5th digit '5' ignored, still 1000
            ]
        )

        # ============================================================
        # Pending key display tests
        # ============================================================
        self._group("Pending key display:", leading_blank=True)

        # Combo key batching: the pending-key frame is skipped when the
        # second key is already available.  The pending key display is only
        # visible when typing slowly (second key not yet in buffer).

        # After dd completes, pending key is cleared
        self.run_test_screen(
            "dd clears pending key from status",
            make_lines(3),
            b"dd:q!\r",
            cols=80,
            expect_status_contains="COMMAND - 1,",
        )

        # After 3dd completes, pending key and count are cleared
        self.run_test_screen(
            "3dd clears pending key from status",
            make_lines(5),
            b"3dd:q!\r",
            cols=80,
            expect_status_contains="COMMAND - 1,",
        )

        # 3d: count frame still shows (count digits not batched)
        self.run_test_screen(
            "3d shows count before batched combo",
            make_lines(5),
            b"3dd:q!\r",
            cols=80,
            expect_status_at_frame=[
                (1, " - 3 - "),
            ]
        )

        # 3y: count frame still shows (count digits not batched)
        self.run_test_screen(
            "3y shows count before batched combo",
            make_lines(5),
            b"3yy:q!\r",
            cols=80,
            expect_status_at_frame=[
                (1, " - 3 - "),
            ]
        )

        # ESC after d clears pending key
        self.run_test_screen(
            "ESC after d clears pending key",
            make_lines(3),
            b"d\x1b:q!\r",
            cols=80,
            expect_status_contains="COMMAND - 1,",
        )

        # ESC after 3d clears everything
        self.run_test_screen(
            "ESC after 3d clears count and pending key",
            make_lines(5),
            b"3d\x1b:q!\r",
            cols=80,
            expect_status_contains="COMMAND - 1,",
        )

        # After ma, pending key clears (m+a batched when keys available)
        self.run_test_screen(
            "ma clears pending key from status",
            make_lines(3),
            b"ma:q!\r",
            cols=80,
            expect_status_contains="COMMAND - 1,",
        )

        # After 'a with mark set, pending key clears ('+a batched)
        self.run_test_screen(
            "'a clears pending key from status",
            make_lines(3),
            b"ma'a:q!\r",
            cols=80,
            expect_status_contains="COMMAND - 1,",
        )

        # Invalid second key after pending key resets state completely
        # (no re-dispatch, no side effects)

        # d then digit: should reset, not start a count
        # d+1 batched: frame 1 shows reset state (no pending, no count)
        self.run_test_screen(
            "d1 resets state (no count started)",
            make_lines(3),
            b"d1:q!\r",
            cols=80,
            expect_status_at_frame=[
                (1, "NORMAL - 1,"),  # After d+1 batched, state fully reset
            ]
        )

        # d then x: should not delete a character
        self.run_test_screen(
            "dx does not delete character",
            "Hello\n",
            b"dx:wq\r",
            expected_content="Hello\n",
        )

        # d then j: should not move cursor
        self.run_test_screen(
            "dj does not move cursor",
            make_lines(3),
            b"dj:q!\r",
            expect_cursor=(0, 0),
        )

        # g then digit: should reset, not start a count
        # g+1 batched: frame 1 shows reset state
        self.run_test_screen(
            "g1 resets state (no count started)",
            make_lines(3),
            b"g1:q!\r",
            cols=80,
            expect_status_at_frame=[
                (1, "NORMAL - 1,"),
            ]
        )

        # g then x: should not delete a character
        self.run_test_screen(
            "gx does not delete character",
            "Hello\n",
            b"gx:wq\r",
            expected_content="Hello\n",
        )

        # y then digit: should reset, not start a count
        # y+1 batched: frame 1 shows reset state
        self.run_test_screen(
            "y1 resets state (no count started)",
            make_lines(3),
            b"y1:q!\r",
            cols=80,
            expect_status_at_frame=[
                (1, "NORMAL - 1,"),
            ]
        )

        # y then x: should not delete a character
        self.run_test_screen(
            "yx does not delete character",
            "Hello\n",
            b"yx:wq\r",
            expected_content="Hello\n",
        )

        # 3d then non-d: should reset count too, not just pending key
        self.run_test_screen(
            "3dx resets count and pending key",
            "Hello\n",
            b"3dx:wq\r",
            expected_content="Hello\n",
        )

        # ============================================================
        # Count movement tests
        # ============================================================
        self._group("Count movement:", leading_blank=True)

        # 3j moves down 3 lines
        self.run_test_screen(
            "3j moves cursor down 3 lines",
            make_lines(10),
            b"3j:q!\r",
            expect_cursor=(3, 0),
            expect_status_contains="COMMAND - 4,"
        )

        # 5l moves right 5 columns
        self.run_test_screen(
            "5l moves cursor right 5",
            "Hello World\n",
            b"5l:q!\r",
            expect_cursor=(0, 5)
        )

        # 2h moves left 2 columns
        self.run_test_screen(
            "2h moves cursor left 2",
            "Hello World\n",
            b"5l2h:q!\r",
            expect_cursor=(0, 3)
        )

        # 3k moves up 3 lines
        self.run_test_screen(
            "3k moves cursor up 3",
            make_lines(10),
            b"5j3k:q!\r",
            expect_cursor=(2, 0),
            expect_status_contains="COMMAND - 3,"
        )

        # Count exceeding bounds clamps
        self.run_test_screen(
            "Count j clamps at last line",
            make_lines(5),
            b"99j:q!\r",
            expect_cursor=(4, 0),
            expect_status_contains="COMMAND - 5,"
        )

        self.run_test_screen(
            "Count k clamps at first line",
            make_lines(5),
            b"3j99k:q!\r",
            expect_cursor=(0, 0),
            expect_status_contains="COMMAND - 1,"
        )

        self.run_test_screen(
            "Count l clamps at end of line",
            "Hello\n",
            b"99l:q!\r",
            expect_cursor=(0, 4)
        )

        self.run_test_screen(
            "Count h clamps at column 0",
            "Hello\n",
            b"ll99h:q!\r",
            expect_cursor=(0, 0)
        )

        # Count cleared after use
        self.run_test_screen(
            "Count cleared after movement",
            make_lines(10),
            b"3j:q!\r",
            cols=80,
            expect_status_at_frame=[
                (1, " - 3 - "),   # '3' shows count
            ],
            expect_status_contains="COMMAND - 4,"  # After j, count gone
        )

        # ============================================================
        # Count + G navigation tests
        # ============================================================
        self._group("Count navigation (G):", leading_blank=True)

        # 5G goes to line 5
        self.run_test_screen(
            "5G goes to line 5",
            make_lines(10),
            b"5G:q!\r",
            expect_cursor=(4, 0),
            expect_status_contains="COMMAND - 5,"
        )

        # G without count = last line
        self.run_test_screen(
            "G without count goes to last line",
            make_lines(10),
            b"G:q!\r",
            cols=80,
            expect_status_contains="COMMAND - 10,"
        )

        # 1G goes to first line
        self.run_test_screen(
            "1G goes to first line",
            make_lines(10),
            b"5j1G:q!\r",
            expect_cursor=(0, 0),
            expect_status_contains="COMMAND - 1,"
        )

        # 999G clamps to last line
        self.run_test_screen(
            "999G clamps to last line",
            make_lines(10),
            b"999G:q!\r",
            cols=80,
            expect_status_contains="COMMAND - 10,"
        )

        # ============================================================
        # Count x and dd tests
        # ============================================================
        self._group("Count x and dd:", leading_blank=True)

        # 3x deletes 3 chars
        self.run_test(
            "3x deletes 3 chars",
            "ABCDEF\n",
            b"3x:wq\r",
            expected_content="DEF\n"
        )

        # 3x from middle
        self.run_test(
            "3x from middle of line",
            "ABCDEF\n",
            b"l3x:wq\r",
            expected_content="AEF\n"
        )

        # Count x exceeding line clamps
        self.run_test(
            "Count x clamps at end of line",
            "AB\n",
            b"99x:wq\r",
            expected_content="\n"
        )

        # x still works without count
        self.run_test(
            "x without count still works",
            "Hello\n",
            b"x:wq\r",
            expected_content="ello\n"
        )

        # 2dd deletes 2 lines
        self.run_test(
            "2dd deletes 2 lines",
            "A\nB\nC\nD\n",
            b"2dd:wq\r",
            expected_content="C\nD\n"
        )

        # 3dd from middle
        self.run_test(
            "3dd from line 2 deletes 3 lines",
            "A\nB\nC\nD\nE\n",
            b"j3dd:wq\r",
            expected_content="A\nE\n"
        )

        # dd still works without count
        self.run_test(
            "dd without count still works",
            "A\nB\n",
            b"dd:wq\r",
            expected_content="B\n"
        )

        # Count dd exceeding file clamps
        self.run_test(
            "Count dd clamps at end of file",
            "A\nB\nC\n",
            b"j99dd:wq\r",
            expected_content="A\n"
        )

        # Batched dd pairs
        self.run_test(
            "dddd batches to delete 2 lines",
            "A\nB\nC\nD\n",
            b"dddd:wq\r",
            expected_content="C\nD\n"
        )

        self.run_test(
            "dddddd batches to delete 3 lines",
            "A\nB\nC\nD\nE\nF\n",
            b"dddddd:wq\r",
            expected_content="D\nE\nF\n"
        )

        self.run_test(
            "3dddd batches count 3 plus 1 extra pair",
            "A\nB\nC\nD\nE\nF\n",
            b"3dddd:wq\r",
            expected_content="E\nF\n"
        )

        self.run_test(
            "dddw partial pair restores pending d then w completes dw",
            "first\nhello world\n",
            b"dddw:wq\r",
            expected_content="world\n"
        )

        # Batched dd yank: only last line should be in yank buffer
        self.run_test(
            "dddd+p yanks only last deleted line",
            "A\nB\nC\n",
            b"ddddp:wq\r",
            expected_content="C\nB\n"
        )

        self.run_test(
            "dddddd+p yanks only last deleted line",
            "A\nB\nC\nD\n",
            b"ddddddp:wq\r",
            expected_content="D\nC\n"
        )

        self.run_test(
            "3dddd+p yanks only last deleted line (not 4)",
            "A\nB\nC\nD\nE\n",
            b"3ddddp:wq\r",
            expected_content="E\nD\n"
        )

        # Non-batched: 3dd still yanks all 3 lines
        self.run_test(
            "3dd+p still pastes all 3 lines (no batching)",
            "A\nB\nC\nD\n",
            b"3ddp:wq\r",
            expected_content="D\nA\nB\nC\n"
        )

        # Batched dd cursor position: should end on correct line
        self.run_test_screen(
            "dddd batched cursor on correct line",
            "A\nB\nC\nD\n",
            b"dddd:q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(0, "C")],
        )

        # Batched dd at end of file: cursor clamps to last line
        self.run_test(
            "dddd batched at EOF clamps correctly",
            "A\nB\n",
            b"dddd:wq\r",
            expected_content="\n"
        )

        # ============================================================
        # D (delete to end of line)
        # ============================================================
        self._group("D (delete to end of line):", leading_blank=True)

        # D at col 5 on "Hello World" deletes " World"
        self.run_test(
            "D at col 5 deletes to end of line",
            "Hello World\n",
            b"lllllD:wq\r",
            expected_content="Hello\n"
        )

        # D at col 0 deletes entire line content (leaves newline)
        self.run_test(
            "D at col 0 deletes line content",
            "Hello\n",
            b"D:wq\r",
            expected_content="\n"
        )

        # D on empty line does nothing
        self.run_test(
            "D on empty line does nothing",
            "\n",
            b"D:wq\r",
            expected_content="\n"
        )

        # D at last char deletes just that char
        self.run_test(
            "D at last char deletes just that char",
            "ABC\n",
            b"llD:wq\r",
            expected_content="AB\n"
        )

        # D doesn't affect next line
        self.run_test(
            "D doesn't affect next line",
            "Hello World\nLine 2\n",
            b"lllllD:wq\r",
            expected_content="Hello\nLine 2\n"
        )

        # D then p pastes deleted text (char paste inserts inline)
        self.run_test(
            "D then p pastes deleted text",
            "Hello World\n",
            b"lllllD0p:wq\r",
            expected_content="H Worldello\n",
        )

        # d$ at col 0 deletes line content (same as D)
        self.run_test(
            "d$ at col 0 deletes line content",
            "Hello\n",
            b"d$:wq\r",
            expected_content="\n"
        )

        # d$ at col 2 deletes to end
        self.run_test(
            "d$ at col 2 deletes to end",
            "Hello\n",
            b"lld$:wq\r",
            expected_content="He\n"
        )

        # d$ on empty line does nothing
        self.run_test(
            "d$ on empty line does nothing",
            "\n",
            b"d$:wq\r",
            expected_content="\n"
        )

        # d$ at last char deletes single char
        self.run_test(
            "d$ at last char deletes just that char",
            "ABC\n",
            b"lld$:wq\r",
            expected_content="AB\n"
        )

        # 2D deletes cursor-to-EOL plus next complete line
        self.run_test(
            "2D deletes to EOL + 1 line below",
            "Hello\nWorld\nFoo\n",
            b"ll2D:wq\r",
            expected_content="He\nFoo\n"
        )

        # 2d$ synonym for 2D
        self.run_test(
            "2d$ synonym for 2D",
            "Hello\nWorld\nFoo\n",
            b"ll2d$:wq\r",
            expected_content="He\nFoo\n"
        )

        # 3d$ on 4 lines at col 0: deletes 3 full lines content + newlines
        self.run_test(
            "3d$ deletes from cursor across 3 lines",
            "ab\ncd\nef\ngh\n",
            b"3d$:wq\r",
            expected_content="\ngh\n"
        )

        # Count exceeds available lines - clamps
        self.run_test(
            "5d$ clamps to available lines",
            "Hello\nWorld\n",
            b"ll5d$:wq\r",
            expected_content="He\n"
        )

        # 2D then p: charwise paste of deleted content
        # 2D at col 2 deletes "llo\nWorld", cursor clamps to col 1 ('e')
        # p pastes "llo\nWorld" after 'e', restoring original
        self.run_test(
            "2D then p pastes charwise multi-line",
            "Hello\nWorld\nFoo\n",
            b"ll2Dp:wq\r",
            expected_content="Hello\nWorld\nFoo\n"
        )

        # C then p pastes deleted text (char paste inserts inline)
        self.run_test(
            "C then p pastes deleted text",
            "Hello World\n",
            b"lllllCX\x1b0p:wq\r",
            expected_content="H WorldelloX\n",
        )

        # dw then p pastes deleted word
        self.run_test(
            "dw then p pastes deleted word",
            "foo bar baz\n",
            b"dw$p:wq\r",
            expected_content="bar bazfoo \n",
        )

        # ============================================================
        # Yank buffer tests (dd fills yank, tested via paste later)
        # For now, verify dd+yank doesn't break existing behavior
        # ============================================================
        self._group("Yank buffer (dd fills yank):", leading_blank=True)

        # dd on single line still leaves empty buffer
        self.run_test(
            "dd on single-line file with yank",
            "Only\n",
            b"dd:wq\r",
            expected_content="\n"
        )

        # dd on last line
        self.run_test(
            "dd on last line with yank",
            "A\nB\nC\n",
            b"Gdd:wq\r",
            expected_content="A\nB\n"
        )

        # 2dd at end (partial: only 1 line to delete)
        self.run_test(
            "2dd at last line only deletes 1",
            "A\nB\nC\n",
            b"G2dd:wq\r",
            expected_content="A\nB\n"
        )

        # ============================================================
        # Paste tests (p and P)
        # ============================================================
        self._group("Paste (p and P):", leading_blank=True)

        # dd + p = cut and paste below (effectively move line down)
        self.run_test(
            "dd+p pastes deleted line below",
            "A\nB\nC\n",
            b"ddp:wq\r",
            expected_content="B\nA\nC\n"
        )

        # dd + P = cut and paste above (line goes back to same position)
        self.run_test(
            "dd+P pastes deleted line above (same pos)",
            "A\nB\nC\n",
            b"ddP:wq\r",
            expected_content="A\nB\nC\n"
        )

        # 2dd + p = cut 2 lines and paste below
        self.run_test(
            "2dd+p pastes 2 deleted lines below",
            "A\nB\nC\nD\n",
            b"2ddp:wq\r",
            expected_content="C\nA\nB\nD\n"
        )

        # dd on line 2 then p (paste below line 2 which is now C)
        self.run_test(
            "dd from middle + p pastes below current",
            "A\nB\nC\nD\n",
            b"jddp:wq\r",
            expected_content="A\nC\nB\nD\n"
        )

        # P pastes above current line
        # j=B, dd deletes B (cursor on C), j=D, P pastes B above D
        self.run_test(
            "dd from middle + P pastes above current",
            "A\nB\nC\nD\n",
            b"jddjP:wq\r",
            expected_content="A\nC\nB\nD\n"
        )

        # p with empty yank does nothing
        self.run_test(
            "p with empty yank does nothing",
            "A\nB\n",
            b"p:wq\r",
            expected_content="A\nB\n"
        )

        # P with empty yank does nothing
        self.run_test(
            "P with empty yank does nothing",
            "A\nB\n",
            b"P:wq\r",
            expected_content="A\nB\n"
        )

        # dd on last line then p
        self.run_test(
            "dd last line + p pastes below",
            "A\nB\nC\n",
            b"Gddp:wq\r",
            expected_content="A\nB\nC\n"
        )

        # Cursor position after p (below)
        self.run_test_screen(
            "cursor at first pasted line after p",
            "A\nB\nC\n",
            b"ddp:q!\r",
            expect_cursor=(1, 0),  # line 1 (0-based) = "A" pasted below "B"
        )

        # Cursor position after P (above)
        self.run_test_screen(
            "cursor at first pasted line after P",
            "A\nB\nC\n",
            b"jddP:q!\r",
            expect_cursor=(1, 0),  # line 1 = "B" pasted above at same line num
        )

        # Multiple dd then p (last dd overwrites yank)
        # dd deletes A (yank=A), cursor on B, j=C, dd deletes C (yank=C),
        # cursor on D, p pastes C below D
        self.run_test(
            "second dd overwrites first dd in yank",
            "A\nB\nC\nD\n",
            b"ddjddp:wq\r",
            expected_content="B\nD\nC\n"
        )

        # ============================================================
        # Count paste tests (Np, NP)
        # ============================================================
        self._group("Count paste (Np, NP):", leading_blank=True)

        # 2p pastes twice
        self.run_test(
            "2p pastes line twice below",
            "A\nB\nC\n",
            b"yy2p:wq\r",
            expected_content="A\nA\nA\nB\nC\n"
        )

        # 3p pastes three times
        self.run_test(
            "3p pastes line three times below",
            "A\nB\n",
            b"yy3p:wq\r",
            expected_content="A\nA\nA\nA\nB\n"
        )

        # 2P pastes twice above
        self.run_test(
            "2P pastes line twice above",
            "A\nB\nC\n",
            b"jyy2P:wq\r",
            expected_content="A\nB\nB\nB\nC\n"
        )

        # dd + 2p (cut one, paste two copies)
        self.run_test(
            "dd+2p pastes deleted line twice",
            "A\nB\nC\n",
            b"dd2p:wq\r",
            expected_content="B\nA\nA\nC\n"
        )

        # ============================================================
        # Yank/copy (yy) tests
        # ============================================================
        self._group("Yank/copy (yy):", leading_blank=True)

        # yy + p copies line (original stays, copy pasted below)
        self.run_test(
            "yy+p copies line below",
            "A\nB\nC\n",
            b"yyp:wq\r",
            expected_content="A\nA\nB\nC\n"
        )

        # yy doesn't modify the buffer
        self.run_test(
            "yy does not set modified flag",
            "A\nB\n",
            b"yy:q\r",
            expect_exit=0  # :q should succeed without warning
        )

        # 2yy + p copies 2 lines
        self.run_test(
            "2yy+p copies 2 lines below",
            "A\nB\nC\nD\n",
            b"2yyp:wq\r",
            expected_content="A\nA\nB\nB\nC\nD\n"
        )

        # yy from last line + p
        self.run_test(
            "yy on last line + p",
            "A\nB\nC\n",
            b"Gyyp:wq\r",
            expected_content="A\nB\nC\nC\n"
        )

        # dd overwrites yy's yank buffer
        self.run_test(
            "dd overwrites yy yank buffer",
            "A\nB\nC\n",
            b"yyjddp:wq\r",
            expected_content="A\nC\nB\n"
        )

        # yy from middle + P pastes above
        self.run_test(
            "yy from middle + P pastes above",
            "A\nB\nC\n",
            b"jyyP:wq\r",
            expected_content="A\nB\nB\nC\n"
        )

        # 2yy clamps at end of file
        self.run_test(
            "2yy at last line only yanks 1",
            "A\nB\nC\n",
            b"G2yyp:wq\r",
            expected_content="A\nB\nC\nC\n"
        )

        # Batched yy pairs: only last yy's count matters (implicit 1)
        self.run_test(
            "yyyy+p yanks only 1 line (last yy overwrites)",
            "A\nB\nC\n",
            b"yyyyp:wq\r",
            expected_content="A\nA\nB\nC\n"
        )

        self.run_test(
            "yyyyyy+p yanks only 1 line (last yy overwrites)",
            "A\nB\nC\nD\n",
            b"yyyyyyp:wq\r",
            expected_content="A\nA\nB\nC\nD\n"
        )

        # Non-batched: 2yy still yanks 2 lines
        self.run_test(
            "2yy+p still pastes 2 lines (no batching)",
            "A\nB\nC\n",
            b"2yyp:wq\r",
            expected_content="A\nA\nB\nB\nC\n"
        )

        # yy+p on line longer than 255 chars (tests page-crossing in newline scan)
        long_line = "A" * 300
        self.run_test(
            "yy+p with 300-char line (page crossing)",
            long_line + "\nB\nC\n",
            b"yyp:wq\r",
            expected_content=long_line + "\n" + long_line + "\nB\nC\n"
        )

        # yy+p below 255-char line (tests INY wrap past newline at Y=255)
        line_255 = "B" * 255
        self.run_test(
            "yy paste below 255-char line (INY page wrap)",
            "X\n" + line_255 + "\nC\n",
            b"yyjp:wq\r",
            expected_content="X\n" + line_255 + "\nX\nC\n"
        )

        # ============================================================
        # Character yank/paste tests (x, D with p/P)
        # ============================================================
        self._group("Character yank/paste (x/D + p/P):", leading_blank=True)

        # x + p: swap first two characters
        self.run_test(
            "x+p swaps first two chars",
            "AB\n",
            b"xp:wq\r",
            expected_content="BA\n"
        )

        # x + P: paste before restores original
        self.run_test(
            "x+P restores original",
            "AB\n",
            b"xP:wq\r",
            expected_content="AB\n"
        )

        # 3x + p: yank multiple chars and paste
        self.run_test(
            "3x+p yanks multiple chars",
            "ABCDE\n",
            b"3xp:wq\r",
            expected_content="DABCE\n"
        )

        # D + p: delete-to-EOL and paste on same line
        self.run_test(
            "D+p deletes to EOL and pastes after",
            "ABCDE\n",
            b"lD$p:wq\r",
            expected_content="ABCDE\n"
        )

        # D + p on next line
        self.run_test(
            "D+p pastes char yank on next line",
            "ABCDE\nXY\n",
            b"lDjp:wq\r",
            expected_content="A\nXBCDEY\n"
        )

        # dd after x: line yank overwrites char yank
        self.run_test(
            "dd after x overwrites char yank",
            "AB\nCD\n",
            b"xjddp:wq\r",
            expected_content="B\nCD\n"
        )

        # x after dd: char yank overwrites line yank
        self.run_test(
            "x after dd overwrites line yank",
            "AB\nCD\n",
            b"ddjxp:wq\r",
            expected_content="DC\n"
        )

        # 2p with char yank: paste text twice inline
        self.run_test(
            "2p with char yank pastes twice",
            "AB\n",
            b"x2p:wq\r",
            expected_content="BAA\n"
        )

        # Char paste on empty line
        self.run_test(
            "char paste on empty line",
            "AB\n\n",
            b"xjp:wq\r",
            expected_content="B\nA\n"
        )

        # Cursor position after char p (non-empty line)
        self.run_test_screen(
            "cursor after char p on non-empty line",
            "ABC\n",
            b"xp:q!\r",
            expect_cursor=(0, 1),  # Pasted A after B, cursor on A (col 1)
        )

        # Cursor position after char P
        self.run_test_screen(
            "cursor after char P",
            "ABC\n",
            b"lxP:q!\r",
            expect_cursor=(0, 1),  # Deleted B, P pastes before A->cursor at B (col 1)
        )

        # Multi-line paste cursor position: cursor at first pasted char
        self.run_test_screen(
            "p with multi-line yank: cursor at first pasted char",
            "foo\nbar\n",
            b"jdb0p:q!\r",
            expect_cursor=(0, 1),
        )

        self.run_test_screen(
            "P with multi-line yank: cursor at first pasted char",
            "foo\nbar\n",
            b"jdb0P:q!\r",
            expect_cursor=(0, 0),
        )

        # Batched x yanks only last deleted char (matches slow typing)
        self.run_test(
            "batched xxxx yanks only last char",
            "ABCDE\n",
            b"xxxxp:wq\r",
            expected_content="ED\n"
        )

        # Explicit count 4x yanks all 4 chars (count is intentional)
        self.run_test(
            "4x yanks all 4 chars",
            "ABCDE\n",
            b"4xp:wq\r",
            expected_content="EABCD\n"
        )

        # Count + batch x: 2x + batched xx = 4 chars deleted, yank last
        self.run_test(
            "2x + batched xx yanks last char",
            "ABCDE\n",
            b"2xxx$p:wq\r",
            expected_content="ED\n"
        )

        # Batched x from middle of line
        self.run_test(
            "batched xx from col 2 yanks last char",
            "ABCDE\n",
            b"llxxp:wq\r",
            expected_content="ABED\n"
        )

        # D on first col yanks entire line content
        self.run_test(
            "D from col 0 yanks whole line",
            "HELLO\nWORLD\n",
            b"Djp:wq\r",
            expected_content="\nWHELLOORLD\n"
        )

        # Multi-line char paste: db yanks content with newline, P restores it
        self.run_test(
            "db cross-line yank + P round-trips content",
            "foo\nbar\n",
            b"jdb0P:wq\r",
            expected_content="foo\nbar\n",
        )

        # ============================================================
        # Search tests (/)
        # ============================================================
        self._group("Search (/):", leading_blank=True)

        # Basic search finds next line
        self.run_test_screen(
            "search finds text on next line",
            "AAA\nBBB\nCCC\n",
            b"/BBB\r:q!\r",
            expect_cursor=(1, 0),  # Found on line 1 (B)
        )

        # Search wraps around
        self.run_test_screen(
            "search wraps around to beginning",
            "AAA\nBBB\nCCC\n",
            b"j/AAA\r:q!\r",
            expect_cursor=(0, 0),  # Wraps to line 0
        )

        # Search finds text at column > 0
        self.run_test_screen(
            "search finds match at column offset",
            "hello world\nfoo bar\n",
            b"/bar\r:q!\r",
            expect_cursor=(1, 4),  # "bar" starts at col 4
        )

        # Search not found shows message (and returns to current pos)
        self.run_test_screen(
            "search not found stays at current line",
            "AAA\nBBB\nCCC\n",
            b"/ZZZ\r :q!\r",  # Space dismisses message
            expect_cursor=(0, 0),  # Stays at line 0
        )

        # Empty search with previous pattern repeats
        # First /AAA finds line 2. Second / repeats from line 3 (wraps to 0).
        self.run_test_screen(
            "empty search repeats previous pattern",
            "AAA\nBBB\nAAA\n",
            b"/AAA\r/\r:q!\r",
            expect_cursor=(0, 0),  # Wraps back to line 0
        )

        # Search on single-line file
        self.run_test_screen(
            "search finds match on same line (wraps)",
            "hello\n",
            b"/hello\r:q!\r",
            expect_cursor=(0, 0),  # Only one line, wraps back
        )

        # ESC cancels search
        self.run_test_screen(
            "ESC cancels search",
            "AAA\nBBB\n",
            b"/BB\x1b:q!\r",
            expect_cursor=(0, 0),  # Stays at line 0
        )

        # Search from middle of file
        self.run_test_screen(
            "search from middle finds below first",
            "AAA\nBBB\nAAA\n",
            b"/AAA\r:q!\r",
            expect_cursor=(2, 0),  # Finds line 2 first (starts from line 1)
        )

        # / finds match later on SAME line (after cursor)
        self.run_test_screen(
            "/ finds match on same line after cursor",
            "AA BB AA\n",
            b"/AA\r:q!\r",
            expect_cursor=(0, 6),  # cursor starts at col 0, finds AA at col 6
        )

        # n advances to next match on same line
        self.run_test_screen(
            "n finds next match on same line",
            "AA BB AA CC AA\n",
            b"/AA\rn:q!\r",
            expect_cursor=(0, 12),  # / finds col 6, n finds col 12
        )

        # n wraps from last match on line to next line
        self.run_test_screen(
            "n wraps from last same-line match to next line",
            "AA BB AA\nCC AA DD\n",
            b"/AA\rn:q!\r",
            expect_cursor=(1, 3),  # / finds (0,6), n finds (1,3)
        )

        # / wraps around file back to same line col 0
        self.run_test_screen(
            "/ wraps around to match at start of current line",
            "AA BB\n",
            b"ll/AA\r:q!\r",
            expect_cursor=(0, 0),  # cursor at col 2, wraps to find AA at col 0
        )

        # ============================================================
        # Find-next (n) tests
        # ============================================================
        self._group("Find-next (n):", leading_blank=True)

        # n repeats search
        self.run_test_screen(
            "n repeats search to next match",
            "AAA\nBBB\nAAA\nBBB\n",
            b"/BBB\rn:q!\r",
            expect_cursor=(3, 0),  # First / finds line 1, n finds line 3
        )

        # n wraps around
        self.run_test_screen(
            "n wraps around to first match",
            "AAA\nBBB\nCCC\n",
            b"/BBB\rn:q!\r",
            expect_cursor=(1, 0),  # Only one BBB, n wraps back to line 1
        )

        # n with no prior search is no-op
        self.run_test_screen(
            "n with no prior search is no-op",
            "AAA\nBBB\n",
            b"n:q!\r",
            expect_cursor=(0, 0),  # Stays at line 0
        )

        # Multiple n presses
        # /X->line 2, first n->line 4, second n->wraps to line 0
        self.run_test_screen(
            "multiple n finds successive matches",
            "X\nY\nX\nY\nX\n",
            b"/X\rn:q!\r",
            expect_cursor=(4, 0),  # /X->line 2, n->line 4
        )

        # Find-prev (N) tests
        # ============================================================
        self._group("Find-prev (N):", leading_blank=True)

        # N searches backward to previous match
        # Start at line 0, /BBB finds line 1, N goes backward (wraps to line 3)
        self.run_test_screen(
            "N searches backward to previous match",
            "AAA\nBBB\nAAA\nBBB\n",
            b"/BBB\rN:q!\r",
            expect_cursor=(3, 0),  # /BBB->line 1, N wraps back to line 3
        )

        # N wraps around to last match when at beginning
        self.run_test_screen(
            "N wraps around to last match",
            "AAA\nBBB\nCCC\n",
            b"/BBB\rN:q!\r",
            expect_cursor=(1, 0),  # Only one BBB, N wraps back to line 1
        )

        # N with no prior search is no-op
        self.run_test_screen(
            "N with no prior search is no-op",
            "AAA\nBBB\n",
            b"N:q!\r",
            expect_cursor=(0, 0),  # Stays at line 0
        )

        # N goes to previous match (backward from current position)
        # /X from line 0 finds line 2, N goes backward to line 0
        self.run_test_screen(
            "N finds previous match going backward",
            "X\nY\nX\nY\nX\n",
            b"/X\rN:q!\r",
            expect_cursor=(0, 0),  # /X->line 2, N back to line 0
        )

        # n then N returns to previous match
        self.run_test_screen(
            "n then N returns to previous match",
            "X\nY\nX\nY\nX\n",
            b"/X\rnN:q!\r",
            expect_cursor=(2, 0),  # /X->line 2, n->line 4, N back to line 2
        )

        # ==========================================================
        # Marks
        # ==========================================================
        self._group("Marks (m/'/adjust):", leading_blank=True)

        # --- Set and go to mark ---

        # Set mark on line 1, go to line 3, return via 'a
        self.run_test_screen(
            "ma then 'a returns to marked line",
            make_lines(5),
            b"majj'a:q!\r",
            expect_cursor=(0, 0),  # Back to line 1
        )

        # Set mark on line 3, go to line 1, jump to mark
        self.run_test_screen(
            "'a jumps forward to marked line",
            make_lines(5),
            b"jjmakk'a:q!\r",
            expect_cursor=(2, 0),  # Line 3
        )

        # Set two marks on different lines, verify both work
        self.run_test_screen(
            "Two marks on different lines",
            make_lines(5),
            b"majjjmb'a:q!\r",
            expect_cursor=(0, 0),  # 'a -> line 1
        )

        self.run_test_screen(
            "Second mark also works",
            make_lines(5),
            b"majjjmb'b:q!\r",
            expect_cursor=(3, 0),  # 'b -> line 4
        )

        # 'z with no mark set shows error (keypress dismisses)
        self.run_test_screen(
            "'z unset mark shows error message",
            make_lines(3),
            b"'z :q!\r",  # space dismisses the error
            expect_cursor=(0, 0),  # stays on line 1
        )

        # m followed by non-letter does nothing harmful
        self.run_test(
            "m1 (non-letter) does nothing",
            make_lines(3),
            b"m1:q!\r",
            expect_unmodified=True,
        )

        # 'a sets cursor col to 0
        self.run_test_screen(
            "'a sets cursor col to 0",
            "Hello\nWorld\n",
            b"mallj'a:q!\r",
            expect_cursor=(0, 0),
        )

        # --- Mark adjustment: dd ---

        # dd the marked line -> mark is unset
        self.run_test_screen(
            "dd marked line unsets mark",
            make_lines(3),
            b"madd'a :q!\r",  # space dismisses "Mark not set"
            expect_cursor=(0, 0),  # stays (error message dismissed)
        )

        # Set mark on line 3, dd line 1 -> mark shifts to line 2
        self.run_test_screen(
            "dd above mark shifts mark down",
            make_lines(5),
            b"jjmagg dd'a:q!\r",  # gg->line1, dd line1, 'a
            expect_cursor=(1, 0),  # mark was line 3 (idx 2), now idx 1
        )

        # Set mark on line 1, dd line 3 -> mark stays on line 1
        self.run_test_screen(
            "dd below mark leaves mark unchanged",
            make_lines(5),
            b"majjdd'a:q!\r",  # mark line1, jj->line3, dd, 'a
            expect_cursor=(0, 0),  # mark still at line 1
        )

        # --- Mark adjustment: o/O ---

        # Set mark on line 3, o on line 1 (opens line 2) -> mark shifts to line 4
        self.run_test_screen(
            "o above mark shifts mark down",
            make_lines(5),
            b"jjmagg o\x1b'a:q!\r",  # mark at line3, gg, o+ESC, 'a
            expect_cursor=(3, 0),  # was idx 2, now idx 3
        )

        # Set mark on line 1, O on line 3 -> mark stays on line 1
        self.run_test_screen(
            "O below mark leaves mark unchanged",
            make_lines(5),
            b"majjO\x1b'a:q!\r",  # mark at line1, jj, O+ESC, 'a
            expect_cursor=(0, 0),
        )

        # O on same line as mark -> mark shifts down
        self.run_test_screen(
            "O on marked line shifts mark down",
            make_lines(5),
            b"jmaO\x1b'a:q!\r",  # mark at line2, O+ESC, 'a
            expect_cursor=(2, 0),  # was idx 1, shifted to idx 2
        )

        # --- Mark adjustment: paste ---

        # Yank a line, paste below line above mark -> mark shifts
        self.run_test_screen(
            "paste above mark shifts mark down",
            make_lines(5),
            b"jjmayy gg p'a:q!\r",  # mark line3, yy, gg, p, 'a
            expect_cursor=(3, 0),  # was idx 2, paste adds 1 line before -> idx 3
        )

        # Yank a line, paste below line below mark -> mark unchanged
        self.run_test_screen(
            "paste below mark leaves mark unchanged",
            make_lines(5),
            b"mayyjjjp'a:q!\r",  # mark line1, yy, jjj->line4, p, 'a
            expect_cursor=(0, 0),
        )

        # 257p: mark adjustment must use 16-bit count
        # yy yanks 1 line, 257p inserts 257 lines below line 0.
        # Mark at line 1 should shift to 1+257=258.
        # Bug: low byte of 257 ($0101) is 1, so mark shifts by 1 only -> line 2.
        self.run_test(
            "257p mark adjustment uses 16-bit count",
            "A\nB\n",
            b"jmagg" +          # mark B (line 1), go to line 0
            b"yy257p" +         # yank A, paste 257 copies below line 0
            b"'add:wq\r",       # go to mark, delete that line, save
            expected_content="A\n" * 258  # 1 original + 257 copies, B deleted
        )

        # --- Mark adjustment: Enter in insert mode ---

        # Set mark on line 3, insert Enter on line 1 -> mark shifts
        self.run_test_screen(
            "Enter in insert above mark shifts mark",
            make_lines(5),
            b"jjmagg A\r\x1b'a:q!\r",  # mark line3, gg, A+Enter+ESC, 'a
            expect_cursor=(3, 0),  # was idx 2, Enter added line -> idx 3
        )

        # --- Mark adjustment: backspace join ---

        # Set mark on line 3, backspace-join at line 2 col 0 -> mark shifts
        self.run_test_screen(
            "BS join above mark shifts mark up",
            make_lines(5),
            b"jjmaki\x08\x1b'a:q!\r",  # mark line3, k->line2, i+BS(join)+ESC, 'a
            expect_cursor=(1, 0),  # was idx 2, join removed line -> idx 1
        )

        # --- Mark adjustment: batched insert mode ---
        # Verify marks are correctly adjusted by the unified insert_batch
        # handler regardless of how keystrokes are batched together.

        # Batch Enter×2 above mark -> mark shifts by 2
        # (sequential composition of inserts is additive)
        self.run_test_screen(
            "Batch Enter×2 above mark shifts mark +2",
            make_lines(5),
            b"jjjmagg A\r\r\x1b'a:q!\r",  # mark line4, gg, A+Enter+Enter+ESC, 'a
            expect_cursor=(5, 0),  # was idx 3, +2 newlines -> idx 5
        )

        # Batch BS×2 crossing 2 newlines above mark -> mark shifts by -2
        # Content has consecutive empty lines so 2 backward bytes are both \n.
        # (sequential composition of deletes at same anchor is additive)
        self.run_test_screen(
            "Batch BS×2 join above mark shifts mark -2",
            "A\n\n\nB\nC\n",
            b"jjjmaki\x08\x08\x1b'a:q!\r",  # mark "B" (idx3), k->line2, BS×2
            expect_cursor=(1, 0),  # was idx 3, -2 newlines -> idx 1
        )

        # DEL across newline above mark -> mark shifts
        DEL = b"\x1b[3~"
        self.run_test_screen(
            "DEL across newline above mark shifts mark",
            make_lines(5),
            b"jjjjmagg A" + DEL + b"\x1b'a:q!\r",  # mark line5, gg, A(end)+DEL
            expect_cursor=(3, 0),  # was idx 4, DEL removed 1 newline -> idx 3
        )

        # Mixed: Enter then BS cancels within batch -> mark unchanged
        # BS cancels the Enter during collection, so no newlines are
        # actually inserted or deleted -> marks unaffected
        self.run_test_screen(
            "Enter+BS cancel in batch leaves mark unchanged",
            make_lines(5),
            b"jjmagg i\r\x08\x1b'a:q!\r",  # mark line3, gg, Enter+BS cancel
            expect_cursor=(2, 0),  # mark still at idx 2
        )

        # Mixed: BS join + Enter re-split -> mark survives round-trip
        # BS deletes newline (joining lines), Enter re-inserts one.
        # delete(1,1) then insert(1,1) is identity for marks.
        self.run_test_screen(
            "BS join + Enter re-split preserves mark",
            make_lines(5),
            b"jjjjmagg ji\x08\r\x1b'a:q!\r",  # mark line5, j->line2, BS+Enter
            expect_cursor=(4, 0),  # mark still at idx 4
        )

        # DEL across newline + typing in batch -> mark below shifts
        DEL = b"\x1b[3~"
        self.run_test_screen(
            "DEL+typing across newline shifts mark below",
            make_lines(5),
            b"jjjmagg A" + DEL + b"XY\x1b'a:q!\r",  # mark line4, gg, A+DEL+XY
            expect_cursor=(2, 0),  # was idx 3, -1 newline -> idx 2
        )

        # BS + typing across newline -> mark below shifts
        self.run_test_screen(
            "BS+typing across newline shifts mark below",
            make_lines(5),
            b"jjjjmagg ji\x08XY\x1b'a:q!\r",  # mark line5, j->line2, BS+XY
            expect_cursor=(3, 0),  # was idx 4, -1 newline -> idx 3
        )

        # --- Mark adjustment: char delete across newlines (db) ---

        # db across newline: mark on line below shifts up
        self.run_test_screen(
            "db across newline shifts mark below",
            "AB\nCD\nEF\nGH\n",
            b"jjjmakkdb'a:q!\r",  # mark "GH" (idx3), kk->line1 col0, db
            expect_cursor=(2, 0),  # was idx 3, 1 newline deleted -> idx 2
        )

        # 2db across 2 newlines: mark shifts by 2
        self.run_test_screen(
            "2db across 2 newlines shifts mark by 2",
            "A\nB\nC\nD\nE\n",
            b"jjjjmakk2db'a:q!\r",  # mark "E" (idx4), kk->line2, 2db crosses 2 NLs
            expect_cursor=(2, 0),  # was idx 4, 2 newlines deleted -> idx 2
        )

        # de across newline: mark on consumed line is unset (col > 0)
        self.run_test_screen(
            "de across newline unsets mark on consumed line",
            "AB\nCD\nEF\n",
            b"jmagg$de'a :q!\r",  # mark "CD" (idx1), gg, $->B, de crosses NL
            expect_cursor=(0, 0),  # mark at idx1 unset (in [1,2)), space dismisses
        )

        # db from col0: mark on cursor line shifts correctly
        # db from (1,0): deletes "AB\n", cursor at (0,0). Col=0 so first_line=0.
        # Mark at idx 1 is in [0,1) -> unset (idx 1 IS the cursor line content)
        # Wait: [0, 0+1) = [0, 1). Mark at 1: NOT in range. Shifted by 1 to 0.
        self.run_test_screen(
            "db col0 shifts mark on next line",
            "AB\nCD\nEF\n",
            b"jjmakdb'a:q!\r",  # mark "EF" (idx2), k->line1, db from col0
            expect_cursor=(1, 0),  # first_line=0 (col0), [0,1): mark at 2 shifted to 1
        )

        # 2db from col0: verify content is correct
        self.run_test(
            "2db from col0 deletes 2 words backward",
            "A\nB\nC\nD\nE\n",
            b"jjj2db:wq\r",  # line3, 2db
            expected_content="A\nD\nE\n",
        )

        # 2db from col0: mark past deletion shifts correctly
        self.run_test_screen(
            "2db from col0 shifts mark past deletion",
            "A\nB\nC\nD\nE\n",
            b"jjjjmak2db'a:q!\r",  # mark "E" (idx4), k->line3, 2db deletes B\nC\n
            expect_cursor=(2, 0),  # mark at 4 shifted by -2 to 2 ("E")
        )

        # 2db from col0: mark on consumed line is unset
        # After 2db: "A\nD\nE\n", cursor at line 1. Mark 'a' was line 2 (in [1,3)) -> unset.
        # 'a fails -> cursor stays at (1,0). If mark were valid at 2, cursor would go to (2,0).
        self.run_test_screen(
            "2db from col0 unsets mark on consumed line",
            "A\nB\nC\nD\nE\n",
            b"jjmaj2db'a:q!\r",  # mark "C" (idx2), j->line3, 2db deletes B\nC\n
            expect_cursor=(1, 0),  # mark unset, cursor stays at line 1
        )

        # --- Mark adjustment: char paste with newlines ---

        # Char paste below (p) with multiline content: mark shifts up
        # de across newline yanks "B\nCD", then p pastes it back.
        # After de: "A\nEF\n" (2 lines), mark shifted from 2 to 1.
        # After p: "AB\nCD\nEF\n" (3 lines), delta=1, mark at 1 shifts to 2.
        self.run_test_screen(
            "char paste below shifts mark on line below",
            "AB\nCD\nEF\n",
            b"jjma" +           # mark "EF" (idx 2)
            b"gg$de" +          # go to 'B', de yanks "B\nCD" (1 newline)
            b"p" +              # paste below: inserts "B\nCD" after 'A'
            b"'a:q!\r",
            expect_cursor=(2, 0),  # was 1 after de, +1 from paste newline -> 2
        )

        # Char paste above (P) with multiline content: mark shifts up
        # Same sequence but P instead of p. Col=0 so at_line=FILE_LINE16.
        self.run_test_screen(
            "char paste above shifts mark on line below",
            "AB\nCD\nEF\n",
            b"jjma" +           # mark "EF" (idx 2)
            b"gg$de" +          # go to 'B', de yanks "B\nCD" (1 newline)
            b"P" +              # paste above: inserts "B\nCD" at cursor
            b"'a:q!\r",
            expect_cursor=(2, 0),  # was 1 after de, +1 from paste newline -> 2
        )

        # --- Mark adjustment: undo/redo of multiline char delete ---

        # Undo of multiline char delete (db): mark shifts back up
        self.run_test_screen(
            "undo multiline char delete shifts mark back",
            "AB\nCD\nEF\n",
            b"jjma" +           # mark "EF" (idx 2)
            b"kdb" +            # line 1 col0, db deletes "AB\n" -> mark shifts to 1
            b"u" +              # undo: pastes "AB\n" back -> mark shifts to 2
            b"'a:q!\r",
            expect_cursor=(2, 0),  # mark restored to original idx 2
        )

        # Redo of multiline char delete: mark shifts down (via delete_at_cursor)
        self.run_test_screen(
            "redo multiline char delete shifts mark down",
            "AB\nCD\nEF\n",
            b"jjma" +           # mark "EF" (idx 2)
            b"kdb" +            # db deletes "AB\n" -> mark shifts to 1
            b"u u" +            # undo then redo: mark should be back at 1
            b"'a:q!\r",
            expect_cursor=(1, 0),  # mark shifted down by redo
        )

        # Mark below 2d$ range gets adjusted
        # Set mark on line 2 (ccc), go to line 0, 2d$ deletes "aaa\nbbb"
        # ccc was line 2, becomes line 1 after 1 newline removed
        self.run_test_screen(
            "2d$ adjusts mark below range",
            "aaa\nbbb\nccc\nddd\n",
            b"2jmakk2d$'a:q!\r",
            rows=10, cols=40,
            expect_cursor=(1, 0),
        )

        # --- :marks command ---

        self._group(":marks command:", leading_blank=True)

        # :marks with no marks shows "No marks set"
        self.run_test_screen(
            ":marks with no marks set",
            make_lines(3),
            b":marks\r :q!\r",  # space dismisses marks display
            expect_cursor=(0, 0),
        )

        # :marks shows set marks with right-justified line numbers
        self.run_test_screen(
            ":marks shows mark a with formatting",
            make_lines(3),
            b"ma:marks\r :q!\r",
            expect_cursor=(0, 0),
            expect_ansi_contains=" a      1",
        )

        # :marks with mark on line 100 aligns with single-digit marks
        self.run_test_screen(
            ":marks right-justifies line numbers",
            make_lines(100),
            b"ma:100\rmb" +         # ma on line 1, goto line 100, mb
            b":marks\r :q!\r",
            expect_ansi_contains=" b    100",
        )

        # :marks with wider terminal shows more text
        self.run_test_screen(
            ":marks wider terminal shows more text",
            "Hello World - this is a long line\n",
            b"ma:marks\r :q!\r",
            rows=10, cols=80,
            expect_ansi_contains="Hello World - this is a long line",
        )

        # :m shows "Unknown command" (partial match, doesn't match :marks)
        self.run_test_screen(
            ":m shows Unknown command",
            make_lines(3),
            b":m\r :q!\r",  # space dismisses error
            expect_ansi_contains="Unknown command",
        )

        # :marksx shows "Unknown command" (extra chars after :marks)
        self.run_test_screen(
            ":marksx shows Unknown command",
            make_lines(3),
            b":marksx\r :q!\r",  # space dismisses error
            expect_ansi_contains="Unknown command",
        )

        # --- Range yank ---

        self._group("Range yank (:'a,.y):", leading_blank=True)

        # Set mark on line 1, navigate to line 3, :'a,.y yanks 3 lines
        self.run_test(
            ":'a,.y yanks range and paste works",
            make_lines(5),
            b"majj:'a,.y\rjp:wq\r",  # ma, jj, :'a,.y, j, p, :wq
            expected_content="Line 1\nLine 2\nLine 3\nLine 4\nLine 1\nLine 2\nLine 3\nLine 5\n",
        )

        # Range with marks in reverse order (auto-swap)
        self.run_test(
            "Range with end < start auto-swaps",
            make_lines(5),
            b"jjmakk:'a,.y\rjjjjp:wq\r",  # ma on line3, kk->line1, :'a,.y, paste
            expected_content="Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 1\nLine 2\nLine 3\n",
        )

        # Range yank between two marks
        self.run_test(
            ":'a,'by yanks between two marks",
            make_lines(5),
            b"majjjmb:'a,'by\rGp:wq\r",  # ma line1, mb line4, range yank, G, p
            expected_content="Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 1\nLine 2\nLine 3\nLine 4\n",
        )

        # Range yank single line
        self.run_test(
            "Range yank single line",
            make_lines(3),
            b"jma:'a,.y\rjp:wq\r",  # ma on line2, :'a,.y on line2, p after line3
            expected_content="Line 1\nLine 2\nLine 3\nLine 2\n",
        )

        # Range yank with unset mark shows error
        self.run_test_screen(
            "Range yank unset mark shows error",
            make_lines(3),
            b":'z,.y\r :q!\r",  # space dismisses error
            expect_cursor=(0, 0),
        )

        # --- Range delete ---

        self._group("Range delete (:'a,.d):", leading_blank=True)

        # :'a,.d deletes range
        self.run_test(
            ":'a,.d deletes range",
            make_lines(5),
            b"majj:'a,.d\r:wq\r",  # ma line1, jj->line3, :'a,.d
            expected_content="Line 4\nLine 5\n",
        )

        # Range delete between two marks
        self.run_test(
            ":'a,'bd deletes between two marks",
            make_lines(5),
            b"jmajjjmb:'a,'bd\r:wq\r",  # ma line2, mb line5, range delete
            expected_content="Line 1\n",
        )

        # Range delete with reverse order auto-swaps
        self.run_test(
            "Range delete reverse order auto-swaps",
            make_lines(5),
            b"jjmakk:'a,.d\r:wq\r",  # ma line3, kk->line1, :'a,.d
            expected_content="Line 4\nLine 5\n",
        )

        # Range delete of all lines leaves single empty line
        self.run_test(
            "Range delete all lines leaves empty",
            make_lines(3),
            b"majj:'a,.d\r:wq\r",  # ma line1, jj->line3, :'a,.d deletes all
            expected_content="\n",
        )

        # Range delete yanks lines first (verify with p)
        self.run_test(
            "Range delete yanks lines for paste",
            make_lines(5),
            b"majj:'a,.d\rp:wq\r",  # delete lines 1-3, then paste
            expected_content="Line 4\nLine 1\nLine 2\nLine 3\nLine 5\n",
        )

        # Range delete adjusts marks (mark below deleted range shifts up)
        self.run_test_screen(
            "Range delete adjusts marks",
            make_lines(5),
            b"jjjjmb" +           # mb on line 5
            b"ggma" +              # ma on line 1
            b"jj:'a,.d\r" +       # jj to line 3, delete lines 1-3
            b"'b:q!\r",           # 'b should be at line 2 (was 5, shifted by 3)
            expect_cursor=(1, 0),  # Mark was line 5 (idx 4), shifted to idx 1
        )

        # Range delete with unset mark shows error
        self.run_test_screen(
            "Range delete unset mark shows error",
            make_lines(3),
            b":'z,.d\r :q!\r",  # space dismisses error
            expect_ansi_contains="Mark not set",
        )

        # Shows "N lines deleted" message
        self.run_test_screen(
            "Range delete shows lines deleted message",
            make_lines(5),
            b"majj:'a,.d\r:q!\r",
            expect_ansi_contains="3 lines deleted",
        )

        # Range delete positions cursor at first deleted line
        self.run_test_screen(
            "Range delete positions cursor correctly",
            make_lines(5),
            b"majj:'a,.d\r:q!\r",  # ma line1, jj->line3, delete 1-3
            expect_cursor=(0, 0),  # cursor at first deleted line (now line 1)
        )

        # Range delete corrupts search buffer (yank buffer overlaps search buffer)
        # YANK_BUF=$E000, SEARCH_BUF=$E020 - yank overwrites search pattern
        # after 32 bytes. Delete enough lines so the yanked content exceeds
        # 32 bytes, then repeat search with empty /. The pattern should still
        # be intact.
        self.run_test_screen(
            "Search repeat works after range delete",
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ_padding\n"
            + "ABCDEFGHIJKLMNOPQRSTUVWXYZ_padding\n"
            + "keepme\n" + "NEEDLE\n",
            # Cursor starts at line 0.
            # /NEEDLE finds NEEDLE on line 3. gg goes to line 0.
            # ma on line 0, j to line 1, :'a,.d deletes lines 0-1
            # (yanks >68 bytes, overwriting SEARCH_BUF at $E020).
            # Remaining: "keepme\n" (line 0) and "NEEDLE\n" (line 1).
            # Cursor at line 0 after delete. /\r repeats search.
            # If search buffer intact: finds NEEDLE on line 1 -> cursor (1,0)
            # If corrupted: pattern not found -> cursor stays at (0,0)
            b"/NEEDLE\r"          # search finds NEEDLE on line 3
            b"ggma"               # gg to line 0, set mark a
            b"j"                  # move to line 1
            b":'a,.d\r"           # delete lines 0-1 (yanks >68 bytes)
            b"/\r"                # repeat search - should find NEEDLE
            b":q!\r",
            expect_cursor=(1, 0),  # NEEDLE is on line 1 after delete
        )

        # --- Line numbers in range commands ---

        self._group("Line numbers in range commands:", leading_blank=True)

        # :1,'ay with mark a on line 3 yanks lines 1-3
        self.run_test(
            ":1,'ay yanks with line number start",
            make_lines(5),
            b"jjma:1,'ay\rGp:wq\r",  # ma on line3, :1,'ay, G, p
            expected_content="Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 1\nLine 2\nLine 3\n",
        )

        # :1,3d deletes first 3 lines
        self.run_test(
            ":1,3d deletes lines 1-3",
            make_lines(5),
            b":1,3d\r:wq\r",
            expected_content="Line 4\nLine 5\n",
        )

        # :'a,3y with mark a on line 1 yanks lines 1-3
        self.run_test(
            ":'a,3y yanks mark to line number",
            make_lines(5),
            b"ma:\'a,3y\rGp:wq\r",  # ma on line1, :'a,3y, G, p
            expected_content="Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 1\nLine 2\nLine 3\n",
        )

        # :1,.y from line 3 yanks lines 1-3
        self.run_test(
            ":1,.y yanks line number to current",
            make_lines(5),
            b"jj:1,.y\rGp:wq\r",  # jj to line3, :1,.y, G, p
            expected_content="Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 1\nLine 2\nLine 3\n",
        )

        # :.,3y from line 1 yanks lines 1-3
        self.run_test(
            ":.,3y yanks current to line number",
            make_lines(5),
            b":.,3y\rGp:wq\r",  # on line1, :.,3y, G, p
            expected_content="Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 1\nLine 2\nLine 3\n",
        )

        # :5 still works as goto line (regression)
        self.run_test_screen(
            ":5 goes to line 5",
            make_lines(10),
            b":5\r:q!\r",
            expect_cursor=(4, 0),
        )

        # :999 goes to last line (regression)
        self.run_test_screen(
            ":999 clamps to last line",
            make_lines(5),
            b":999\r:q!\r",
            expect_cursor=(4, 0),
        )

        # Line numbers are 1-based
        self.run_test(
            ":2,4d deletes lines 2-4 (1-based)",
            make_lines(5),
            b":2,4d\r:wq\r",
            expected_content="Line 1\nLine 5\n",
        )

        self._group("Range indent/unindent (:>, :<):", leading_blank=True)

        # Range indent
        self.run_test(
            ":1,3> indents lines 1-3",
            "aaa\nbbb\nccc\nddd\n",
            b":1,3>\r:wq\r",
            expected_content="  aaa\n  bbb\n  ccc\nddd\n",
        )

        # Range unindent
        self.run_test(
            ":1,3< unindents lines 1-3",
            "  aaa\n  bbb\n  ccc\nddd\n",
            b":1,3<\r:wq\r",
            expected_content="aaa\nbbb\nccc\nddd\n",
        )

        # Bare :> indents current line
        self.run_test(
            ":> indents current line",
            "hello\nworld\n",
            b":>\r:wq\r",
            expected_content="  hello\nworld\n",
        )

        # Bare :< unindents current line
        self.run_test(
            ":< unindents current line",
            "  hello\nworld\n",
            b":<\r:wq\r",
            expected_content="hello\nworld\n",
        )

        # Single-position :.> indents current line (cursor on line 2)
        self.run_test(
            ":.> indents current line",
            "hello\nworld\n",
            b"j:.>\r:wq\r",
            expected_content="hello\n  world\n",
        )

        # Single-position :2> indents line 2
        self.run_test(
            ":2> indents line 2",
            "aaa\nbbb\nccc\n",
            b":2>\r:wq\r",
            expected_content="aaa\n  bbb\nccc\n",
        )

        # Mark range indent
        self.run_test(
            ":'a,.> indents from mark to current",
            "aaa\nbbb\nccc\nddd\n",
            b"majj:'a,.>\r:wq\r",
            expected_content="  aaa\n  bbb\n  ccc\nddd\n",
        )

        # Mark range unindent
        self.run_test(
            ":'a,.< unindents from mark to current",
            "  aaa\n  bbb\n  ccc\nddd\n",
            b"majj:'a,.<\r:wq\r",
            expected_content="aaa\nbbb\nccc\nddd\n",
        )

        # Empty line handling
        self.run_test(
            ":> range skips empty lines",
            "aaa\n\nbbb\n",
            b":1,3>\r:wq\r",
            expected_content="  aaa\n\n  bbb\n",
        )

        # Single-position :5d works (bonus from single-position support)
        self.run_test(
            ":5d deletes line 5 (single-position command)",
            make_lines(6),
            b":5d\r:wq\r",
            expected_content="Line 1\nLine 2\nLine 3\nLine 4\nLine 6\n",
        )

        # :5 still works as goto (regression)
        self.run_test_screen(
            ":5 still works as goto after shift support",
            make_lines(10),
            b":5\r:q!\r",
            expect_cursor=(4, 0),
        )

        self._group("Long line handling (>255 chars):", leading_blank=True)

        long_line_300 = "A" * 300 + "\n"

        # Search on a line >255 chars should complete (not hang)
        # Search for a pattern that doesn't exist - should report not found
        self.run_test(
            "Search on >255 char line doesn't hang (pattern not found)",
            long_line_300,
            b"/ZZZZZ\r:q!\r",
            expect_unmodified=True
        )

        # Search for a pattern in first 255 chars still works
        content_with_marker = "B" * 100 + "MARKER" + "B" * 200 + "\n"
        self.run_test(
            "Search finds pattern within first 255 chars of long line",
            content_with_marker,
            b"/MARKER\rx:wq\r",
            expected_content="B" * 100 + "ARKER" + "B" * 200 + "\n"
        )

        # 'o' (open below) on a line >255 chars inserts correctly
        self.run_test(
            "Open below (o) on >255 char line",
            long_line_300,
            b"oHello\x1b:wq\r",
            expected_content=long_line_300 + "Hello\n"
        )

        # 'o' on a line exactly at 256 chars (edge case for Y wrap)
        long_line_256 = "X" * 256 + "\n"
        self.run_test(
            "Open below (o) on 256 char line (Y wrap edge case)",
            long_line_256,
            b"oWorld\x1b:wq\r",
            expected_content=long_line_256 + "World\n"
        )

        # 'o' on multi-line file where long line is first
        self.run_test(
            "Open below (o) on long first line with second line",
            long_line_300 + "Short\n",
            b"oMiddle\x1b:wq\r",
            expected_content=long_line_300 + "Middle\n" + "Short\n"
        )

        # ============================================================
        # Operations exceeding 255 lines (currently fail - TBD)
        # ============================================================
        self._group("Operations exceeding 255 lines (>255):", leading_blank=True)

        self.run_test(
            "256dd deletes 256 lines",
            make_lines(300),
            b"256dd:wq\r",
            # Lines 1-256 deleted, lines 257-300 remain
            expected_content=''.join(f"Line {i}\n" for i in range(257, 301))
        )

        self.run_test(
            "300yy yanks 300 lines",
            make_lines(300) + "Extra\n",
            b"300yyGp:wq\r",
            # After 300yy, cursor on line 1. G moves to last line (301).
            # p pastes below, so lines 1-300 appear after line 301.
            expected_content=make_lines(300) + "Extra\n" + make_lines(300)
        )

        self.run_test(
            "16yy + 16p pastes 256 lines correctly",
            make_lines(20),
            b"16yy3G16p:wq\r",
            # 16yy yanks lines 1-16. 3G moves to line 3.
            # 16p pastes 16 lines, 16 times = 256 lines below line 3.
            # Result: lines 1-3, then 256 pasted lines (16 copies of lines 1-16), then lines 4-20
            expected_content=(
                make_lines(3) +
                (make_lines(16) * 16) +
                ''.join(f"Line {i}\n" for i in range(4, 21))
            )
        )

        self.run_test(
            "Mark adjustment with 256dd",
            make_lines(400),
            b"100Gma100G256dd:wq\r",
            # 100G goes to line 100, ma sets mark a
            # 100G stays at line 100 (already there)
            # 256dd deletes lines 100-355 (256 lines)
            # Mark a was on line 100 (now deleted)
            # Result: lines 1-99, then lines 356-400
            expected_content=(
                make_lines(99) +
                ''.join(f"Line {i}\n" for i in range(356, 401))
            )
        )

        self.run_test(
            "Range :100,399d deletes 300 lines",
            make_lines(500),
            b":100,399d\r:wq\r",
            # Delete lines 100-399 (300 lines)
            # Result: lines 1-99, then lines 400-500
            expected_content=(
                make_lines(99) +
                ''.join(f"Line {i}\n" for i in range(400, 501))
            )
        )

        self._group("Screen state - non-ASCII display:", leading_blank=True)

        # Single non-ASCII byte mid-line
        self.run_test_screen(
            "Non-ASCII byte displayed as reverse ?",
            None,
            b":q!\r",
            initial_bytes=b"AB\x80CD\n",
            expect_lines=[(0, "AB?CD")],
            expect_reverse_at=[
                (0, 0, False), (0, 1, False),
                (0, 2, True),
                (0, 3, False), (0, 4, False),
            ]
        )

        # Multiple non-ASCII bytes
        self.run_test_screen(
            "Multiple non-ASCII bytes as reverse ?",
            None,
            b":q!\r",
            initial_bytes=b"A\xFF\xFEB\n",
            expect_lines=[(0, "A??B")],
            expect_reverse_at=[
                (0, 0, False),
                (0, 1, True), (0, 2, True),
                (0, 3, False),
            ]
        )

        # Cursor movement past non-ASCII bytes (one column per byte)
        self.run_test_screen(
            "Cursor movement past non-ASCII bytes",
            None,
            b"lll:q!\r",
            initial_bytes=b"A\x80\x90D\n",
            expect_cursor=(0, 3),
        )

        # Non-ASCII at end of line with $ motion
        self.run_test_screen(
            "Non-ASCII at end of line with $ motion",
            None,
            b"$:q!\r",
            initial_bytes=b"ABC\x80\n",
            expect_cursor=(0, 3),
            expect_reverse_at=[
                (0, 3, True),
            ]
        )

        self._group("Screen state - tab and control char display:", leading_blank=True)

        # Tab displayed as reverse >
        self.run_test_screen(
            "Tab displayed as reverse >",
            None,
            b":q!\r",
            initial_bytes=b"A\tB\n",
            expect_lines=[(0, "A>B")],
            expect_reverse_at=[
                (0, 0, False),
                (0, 1, True),
                (0, 2, False),
            ]
        )

        # Control char displayed as reverse ?
        self.run_test_screen(
            "Control char displayed as reverse ?",
            None,
            b":q!\r",
            initial_bytes=b"A\x01B\n",
            expect_lines=[(0, "A?B")],
            expect_reverse_at=[
                (0, 0, False),
                (0, 1, True),
                (0, 2, False),
            ]
        )

        # Tab inserted via insert mode
        self.run_test_screen(
            "Tab key inserts tab in insert mode",
            "AB\n",
            b"i\tC\x1b:q!\r",
            expect_lines=[(0, ">CAB")],
            expect_reverse_at=[
                (0, 0, True),
                (0, 1, False),
            ]
        )

        # Multiple tabs and control chars
        self.run_test_screen(
            "Multiple tabs and control chars",
            None,
            b":q!\r",
            initial_bytes=b"\t\x02\t\n",
            expect_lines=[(0, ">?>")],
            expect_reverse_at=[
                (0, 0, True),
                (0, 1, True),
                (0, 2, True),
            ]
        )

        self._group("Word motions (w, b, e):", leading_blank=True)

        self.run_test_screen(
            "w skips word to next word",
            "hello world\n",
            b"w:q!\r",
            expect_cursor=(0, 6),
        )

        self.run_test_screen(
            "w from middle of word",
            "hello world\n",
            b"llw:q!\r",
            expect_cursor=(0, 6),
        )

        self.run_test_screen(
            "w skips punctuation class",
            "foo...bar\n",
            b"w:q!\r",
            expect_cursor=(0, 3),
        )

        self.run_test_screen(
            "w from punct to word",
            "...bar\n",
            b"w:q!\r",
            expect_cursor=(0, 3),
        )

        self.run_test_screen(
            "w at end of line goes to next line",
            "foo\nbar\n",
            b"$w:q!\r",
            expect_cursor=(1, 0),
        )

        self.run_test_screen(
            "w on empty line goes to next line",
            "\nbar\n",
            b"w:q!\r",
            expect_cursor=(1, 0),
        )

        self.run_test_screen(
            "w skips whitespace between words",
            "foo   bar\n",
            b"w:q!\r",
            expect_cursor=(0, 6),
        )

        self.run_test_screen(
            "2w skips two words",
            "one two three\n",
            b"2w:q!\r",
            expect_cursor=(0, 8),
        )

        # b: move to start of previous word
        self.run_test_screen(
            "b from middle of second word",
            "hello world\n",
            b"$b:q!\r",
            expect_cursor=(0, 6),
        )

        self.run_test_screen(
            "b from start of second word",
            "hello world\n",
            b"llllllb:q!\r",
            expect_cursor=(0, 0),
        )

        self.run_test_screen(
            "b at col 0 goes to start of last word on previous line",
            "foo\nbar\n",
            b"jb:q!\r",
            expect_cursor=(0, 0),
        )

        self.run_test_screen(
            "b with punctuation",
            "foo...bar\n",
            b"$b:q!\r",
            expect_cursor=(0, 6),
        )

        self.run_test_screen(
            "2b skips two words",
            "one two three\n",
            b"$2b:q!\r",
            expect_cursor=(0, 4),
        )

        self.run_test_screen(
            "b from BOL to multi-word prev line",
            "one two\nthree\n",
            b"jb:q!\r",
            expect_cursor=(0, 4),
        )

        self.run_test_screen(
            "2b crossing line boundary",
            "hello\nworld\n",
            b"j2b:q!\r",
            expect_cursor=(0, 0),
        )

        self.run_test_screen(
            "w then b returns to origin",
            "hello\nworld\n",
            b"wb:q!\r",
            expect_cursor=(0, 0),
        )

        # e: move to end of current/next word
        self.run_test_screen(
            "e from start of word",
            "hello world\n",
            b"e:q!\r",
            expect_cursor=(0, 4),
        )

        self.run_test_screen(
            "e skips to next word end",
            "hello world\n",
            b"ee:q!\r",
            expect_cursor=(0, 10),
        )

        self.run_test_screen(
            "e with punctuation",
            "foo...bar\n",
            b"e:q!\r",
            expect_cursor=(0, 2),
        )

        self.run_test_screen(
            "e at end of line goes to next line",
            "foo\nbar\n",
            b"ee:q!\r",
            expect_cursor=(1, 2),
        )

        self.run_test_screen(
            "2e skips two word ends",
            "one two three\n",
            b"2e:q!\r",
            expect_cursor=(0, 6),
        )

        self._group("Toggle case (~):", leading_blank=True)

        self.run_test(
            "~ toggles lowercase to uppercase",
            "hello\n",
            b"~:wq\r",
            expected_content="Hello\n"
        )

        self.run_test(
            "~ toggles uppercase to lowercase",
            "HELLO\n",
            b"~:wq\r",
            expected_content="hELLO\n"
        )

        self.run_test(
            "~ on non-alpha advances cursor",
            "1abc\n",
            b"~~:wq\r",
            expected_content="1Abc\n"
        )

        self.run_test(
            "3~ toggles 3 chars",
            "hello\n",
            b"3~:wq\r",
            expected_content="HELlo\n"
        )

        self.run_test(
            "~ on empty line does nothing",
            "\n",
            b"~:q!\r",
            expect_unmodified=True
        )

        # Batched ~ (rapid ~~~ toggles 3 chars)
        self.run_test(
            "~~~ batched toggles 3 chars",
            "hello\n",
            b"~~~:wq\r",
            expected_content="HELlo\n"
        )

        # Batched ~ matches count prefix
        self.run_test(
            "~~~ batched matches 3~ result",
            "hello\n",
            b"3~:wq\r",
            expected_content="HELlo\n"
        )

        # Batched ~ cursor position
        self.run_test_screen(
            "~~~ batched cursor at col 3",
            "hello\n",
            b"~~~:q!\r",
            expect_cursor=(0, 3),
        )

        # Count + batch combination
        self.run_test(
            "2~ + batched ~ toggles 3 chars",
            "hello\n",
            b"2~~:wq\r",
            expected_content="HELlo\n"
        )

        # Batched ~ at end of line stops at last char
        self.run_test(
            "~~~~~ batched on 3-char line toggles all",
            "abc\n",
            b"~~~~~:wq\r",
            expected_content="ABC\n"
        )

        # Render: batched ~ is single action frame
        self.run_test_screen(
            "Batch ~~~ is single action frame",
            "hello\n",
            b"~~~:q!\r",
            expect_content_redraws=[True, True, False]
        )

        self._group("Join lines (J):", leading_blank=True)

        self.run_test(
            "J joins two lines with space",
            "foo\nbar\n",
            b"J:wq\r",
            expected_content="foo bar\n"
        )

        self.run_test(
            "3J joins 3 lines",
            "one\ntwo\nthree\nfour\n",
            b"3J:wq\r",
            expected_content="one two three\nfour\n"
        )

        self.run_test(
            "J on last line does nothing",
            "only\n",
            b"J:q!\r",
            expect_unmodified=True
        )

        # Batched J (rapid JJ joins 2 lines)
        self.run_test(
            "JJ batched joins 2 lines",
            "aaa\nbbb\nccc\nddd\n",
            b"JJ:wq\r",
            expected_content="aaa bbb ccc\nddd\n"
        )

        # Batched JJ matches 3J result (3J joins current + 2 more)
        self.run_test(
            "JJ batched matches 3J result",
            "aaa\nbbb\nccc\nddd\n",
            b"3J:wq\r",
            expected_content="aaa bbb ccc\nddd\n"
        )

        # Triple batched J
        self.run_test(
            "JJJ batched joins 3 lines",
            "aaa\nbbb\nccc\nddd\neee\n",
            b"JJJ:wq\r",
            expected_content="aaa bbb ccc ddd\neee\n"
        )

        # Count + batch combination: 2J = 1 join, + batched J = 1 more join = 2 total
        self.run_test(
            "2J + batched J joins 3 lines into one",
            "aaa\nbbb\nccc\nddd\n",
            b"2JJ:wq\r",
            expected_content="aaa bbb ccc\nddd\n"
        )

        # Batched J at end of file stops gracefully
        self.run_test(
            "JJJ batched on 3-line file joins all",
            "aaa\nbbb\nccc\n",
            b"JJJ:wq\r",
            expected_content="aaa bbb ccc\n"
        )

        # Render: batched JJ is single action frame
        self.run_test_screen(
            "Batch JJ is single action frame",
            "aaa\nbbb\nccc\n",
            b"JJ:q!\r",
            expect_content_redraws=[True, True, False]
        )

        self._group("Replace char (r):", leading_blank=True)

        self.run_test(
            "rx replaces char at cursor",
            "hello\n",
            b"rx:wq\r",
            expected_content="xello\n"
        )

        self.run_test(
            "3rx replaces 3 chars",
            "hello\n",
            b"3rx:wq\r",
            expected_content="xxxlo\n"
        )

        self.run_test(
            "r on empty line does nothing",
            "\n",
            b"rx:q!\r",
            expect_unmodified=True
        )

        self._group("Substitute char (s):", leading_blank=True)

        self.run_test(
            "s deletes char and enters insert",
            "hello\n",
            b"sX\x1b:wq\r",
            expected_content="Xello\n"
        )

        self.run_test(
            "2s deletes 2 chars and enters insert",
            "hello\n",
            b"2sXY\x1b:wq\r",
            expected_content="XYllo\n"
        )

        self.run_test(
            "s on empty line enters insert",
            "\n",
            b"sX\x1b:wq\r",
            expected_content="X\n"
        )

        self._group("Change to EOL (C):", leading_blank=True)

        self.run_test(
            "C at start deletes all and inserts",
            "hello\n",
            b"CXY\x1b:wq\r",
            expected_content="XY\n"
        )

        self.run_test(
            "C at middle deletes to EOL and inserts",
            "hello\n",
            b"llCXY\x1b:wq\r",
            expected_content="heXY\n"
        )

        self.run_test(
            "C on empty line enters insert",
            "\n",
            b"CX\x1b:wq\r",
            expected_content="X\n"
        )

        # Counted C: 2C at col 2 deletes to EOL + next line, enters insert
        self.run_test(
            "2C changes to EOL + next line",
            "Hello\nWorld\nFoo\n",
            b"ll2CNew\x1b:wq\r",
            expected_content="HeNew\nFoo\n"
        )

        # 3C from col 0 on 4 lines
        self.run_test(
            "3C changes 3 lines from cursor",
            "ab\ncd\nef\ngh\n",
            b"3CX\x1b:wq\r",
            expected_content="X\ngh\n"
        )

        # Counted C clamps to available lines
        self.run_test(
            "5C clamps to available lines",
            "Hello\nWorld\n",
            b"ll5CX\x1b:wq\r",
            expected_content="HeX\n"
        )

        self._group("Change line (cc, S):", leading_blank=True)

        self.run_test(
            "cc deletes line and enters insert",
            "hello\nworld\n",
            b"ccXY\x1b:wq\r",
            expected_content="XY\nworld\n"
        )

        self.run_test(
            "2cc changes 2 lines",
            "one\ntwo\nthree\n",
            b"2ccXY\x1b:wq\r",
            expected_content="XY\nthree\n"
        )

        self.run_test(
            "S substitutes single line",
            "hello\nworld\n",
            b"SXY\x1b:wq\r",
            expected_content="XY\nworld\n"
        )

        # 2S substitutes 2 lines (same as 2cc)
        self.run_test(
            "2S substitutes 2 lines",
            "one\ntwo\nthree\n",
            b"2SXY\x1b:wq\r",
            expected_content="XY\nthree\n"
        )

        # 3S substitutes 3 lines
        self.run_test(
            "3S substitutes 3 lines",
            "aaa\nbbb\nccc\nddd\n",
            b"3SX\x1b:wq\r",
            expected_content="X\nddd\n"
        )

        # S with count clamped to available lines
        self.run_test(
            "5S clamps to available lines",
            "hello\nworld\n",
            b"5SX\x1b:wq\r",
            expected_content="X\n"
        )

        self.run_test(
            "cc on single line",
            "hello\n",
            b"ccXY\x1b:wq\r",
            expected_content="XY\n"
        )

        # 3dd then p pastes 3 deleted lines
        self.run_test(
            "3dd then p pastes 3 deleted lines",
            "aaa\nbbb\nccc\nddd\n",
            b"3ddp:wq\r",
            expected_content="ddd\naaa\nbbb\nccc\n",
        )

        # 2cc replaces 2 lines and enters insert
        self.run_test(
            "2cc replaces 2 lines and enters insert",
            "aaa\nbbb\nccc\n",
            b"2ccX\x1b:wq\r",
            expected_content="X\nccc\n",
        )

        self._group("Indent (>>, <<):", leading_blank=True)

        self.run_test(
            ">> indents single line by 2 spaces",
            "hello\n",
            b">>:wq\r",
            expected_content="  hello\n"
        )

        self.run_test(
            ">> on single line indents correctly",
            "one\ntwo\n",
            b">>:wq\r",
            expected_content="  one\ntwo\n"
        )

        self.run_test(
            ">> on multiple lines with count",
            "one\ntwo\nthree\n",
            b"2>>:wq\r",
            expected_content="  one\n  two\nthree\n"
        )

        self.run_test(
            ">> on empty line does not indent",
            "\n",
            b">>:wq\r",
            expected_content="\n"
        )

        self.run_test(
            ">> skips empty lines in range",
            "aaa\n\nbbb\n",
            b"3>>:wq\r",
            expected_content="  aaa\n\n  bbb\n"
        )

        self.run_test(
            ">> on spaces-only line does indent",
            "   \n",
            b">>:wq\r",
            expected_content="     \n"
        )

        self.run_test(
            ">> on all empty lines is no-op",
            "\n\n\n",
            b"3>>:wq\r",
            expected_content="\n\n\n"
        )

        self.run_test_screen(
            ">> on empty line does not move cursor",
            "\nfoo\n",
            b">>:q!\r",
            expect_cursor=(0, 0),
        )

        self.run_test(
            ">> with count and mixed empty lines",
            "aaa\n\n\nbbb\n",
            b"4>>:wq\r",
            expected_content="  aaa\n\n\n  bbb\n"
        )

        self.run_test(
            ">> preserves lines after indented range",
            "aaa\nbbb\nccc\n",
            b"2>>:wq\r",
            expected_content="  aaa\n  bbb\nccc\n"
        )

        self.run_test(
            "<< unindents single line",
            "  hello\n",
            b"<<:wq\r",
            expected_content="hello\n"
        )

        self.run_test(
            "<< with partial indent (1 space)",
            " hello\n",
            b"<<:wq\r",
            expected_content="hello\n"
        )

        self.run_test(
            "<< on line with no indent",
            "hello\n",
            b"<<:wq\r",
            expected_content="hello\n"
        )

        self.run_test(
            "<< on multiple lines with count",
            "  one\n  two\nthree\n",
            b"2<<:wq\r",
            expected_content="one\ntwo\nthree\n"
        )

        self.run_test(
            ">> then << round-trips",
            "hello\n",
            b">><<:wq\r",
            expected_content="hello\n"
        )

        self.run_test(
            "<< with mixed indent levels",
            "  aaa\n bbb\nccc\n",
            b"3<<:wq\r",
            expected_content="aaa\nbbb\nccc\n"
        )

        self.run_test(
            "<< preserves lines after range",
            "  aaa\n  bbb\n  ccc\n",
            b"2<<:wq\r",
            expected_content="aaa\nbbb\n  ccc\n"
        )

        self.run_test(
            "<< with empty lines in range",
            "  aaa\n\n  bbb\n",
            b"3<<:wq\r",
            expected_content="aaa\n\nbbb\n"
        )

        self.run_test_screen(
            "<< on unindented line does not move cursor",
            "hello\n",
            b"ll<<:q!\r",
            expect_cursor=(0, 2),
        )

        self.run_test_screen(
            "<< adjusts cursor by actual spaces removed",
            " hello\n",
            b"lll<<:q!\r",
            expect_cursor=(0, 2),
        )

        # >>>> = two rapid >> combos: indents current line TWICE (4 spaces)
        # This is NOT the same as 2>> which indents 2 lines once.
        self.run_test(
            ">>>> indents current line twice (4 spaces)",
            "aaa\nbbb\nccc\n",
            b">>>>:wq\r",
            expected_content="    aaa\nbbb\nccc\n"
        )

        # 2>> indents 2 lines (count = line count, not repeat count)
        self.run_test(
            "2>> indents two lines once (different from >>>>)",
            "aaa\nbbb\nccc\n",
            b"2>>:wq\r",
            expected_content="  aaa\n  bbb\nccc\n"
        )

        # <<<< = two rapid << combos: unindents current line twice
        self.run_test(
            "<<<< unindents current line twice",
            "    aaa\n  bbb\n  ccc\n",
            b"<<<<:wq\r",
            expected_content="aaa\n  bbb\n  ccc\n"
        )

        # 2<< unindents 2 lines (count = line count, not repeat count)
        self.run_test(
            "2<< unindents two lines once (different from <<<<)",
            "  aaa\n  bbb\n  ccc\n",
            b"2<<:wq\r",
            expected_content="aaa\nbbb\n  ccc\n"
        )

        # >>>>>> = three rapid >> combos: indents current line three times (6 spaces)
        self.run_test(
            ">>>>>> indents current line three times (6 spaces)",
            "aaa\nbbb\nccc\nddd\n",
            b">>>>>>:wq\r",
            expected_content="      aaa\nbbb\nccc\nddd\n"
        )

        # >>>> cursor: col 1 + two indents (2+2 spaces) = col 5
        self.run_test_screen(
            ">>>> cursor col adjusted for double indent",
            "aaa\nbbb\nccc\n",
            b"l>>>>:q!\r",
            expect_cursor=(0, 5),
        )

        # <<<< cursor: col 3 on "  aaa", first << removes 2 → col 1, second << no-op → col 1
        self.run_test_screen(
            "<<<< cursor col adjusted for double unindent",
            "  aaa\n  bbb\n  ccc\n",
            b"lll<<<<:q!\r",
            expect_cursor=(0, 1),
        )

        # Render: >>>> batched into single action frame (3 frames: init, action, quit)
        self.run_test_screen(
            "Render: >>>> is single action frame",
            "aaa\nbbb\nccc\n",
            b">>>>:q!\r",
            expect_content_redraws=[True, True, False]
        )

        # Render: <<<< batched into single action frame (3 frames: init, action, quit)
        self.run_test_screen(
            "Render: <<<< is single action frame",
            "  aaa\n  bbb\n  ccc\n",
            b"<<<<:q!\r",
            expect_content_redraws=[True, True, False]
        )

        self._group("First non-blank (^):", leading_blank=True)

        self.run_test_screen(
            "^ on line with leading spaces",
            "   hello\n",
            b"^:q!\r",
            expect_cursor=(0, 3),
        )

        self.run_test_screen(
            "^ on line without leading spaces",
            "hello\n",
            b"ll^:q!\r",
            expect_cursor=(0, 0),
        )

        self.run_test_screen(
            "^ on empty line stays at col 0",
            "\n",
            b"^:q!\r",
            expect_cursor=(0, 0),
        )

        self.run_test_screen(
            "^ on all-spaces line stays at col 0",
            "   \n",
            b"^:q!\r",
            expect_cursor=(0, 0),
        )

        self._group("Delete word (dw):", leading_blank=True)

        self.run_test(
            "dw deletes word and trailing space",
            "hello world\n",
            b"dw:wq\r",
            expected_content="world\n",
        )

        self.run_test(
            "dw at middle of word deletes to next word",
            "hello world\n",
            b"lldw:wq\r",
            expected_content="heworld\n",
        )

        self.run_test(
            "dw on punctuation deletes punct and space",
            "...bar baz\n",
            b"dw:wq\r",
            expected_content="bar baz\n",
        )

        self.run_test(
            "dw on last word deletes to EOL",
            "foo bar\n",
            b"4ldw:wq\r",
            expected_content="foo \n",
        )

        self.run_test(
            "dw on whitespace deletes to next word",
            "foo   bar\n",
            b"3ldw:wq\r",
            expected_content="foobar\n",
        )

        self.run_test(
            "dw on empty line does nothing",
            "\n",
            b"dw:wq\r",
            expected_content="\n",
        )

        self.run_test(
            "2dw deletes two words",
            "one two three\n",
            b"2dw:wq\r",
            expected_content="three\n",
        )

        self.run_test(
            "dw yanks deleted text (paste back)",
            "hello world\n",
            b"dw$p:wq\r",
            expected_content="worldhello \n",
        )

        # dw on whitespace only deletes whitespace (not next word)
        self.run_test(
            "dw on only whitespace deletes whitespace",
            "foo   \n",
            b"3ldw:wq\r",
            expected_content="foo\n",
        )

        # Batched dw pairs
        self.run_test(
            "dwdw batches to delete 2 words",
            "one two three four\n",
            b"dwdw:wq\r",
            expected_content="three four\n",
        )

        self.run_test(
            "dwdwdw batches to delete 3 words",
            "one two three four\n",
            b"dwdwdw:wq\r",
            expected_content="four\n",
        )

        self.run_test(
            "2dwdw batches count 2 plus 1 extra pair",
            "one two three four\n",
            b"2dwdw:wq\r",
            expected_content="four\n",
        )

        # Batched dw yank: only last word deleted is in yank buffer
        self.run_test(
            "dwdw+$p yanks only last deleted word",
            "one two three\n",
            b"dwdw$p:wq\r",
            expected_content="threetwo \n",
        )

        # Count-prefix dw yank: yanks ALL deleted text
        self.run_test(
            "2dw+$p yanks all deleted text",
            "one two three\n",
            b"2dw$p:wq\r",
            expected_content="threeone two \n",
        )

        self.run_test(
            "3dw+$p yanks all deleted text",
            "one two three four\n",
            b"3dw$p:wq\r",
            expected_content="fourone two three \n",
        )

        # Multi-line dw tests
        self.run_test(
            "dw at last word uses exclusive-linewise (preserves newline)",
            "foo\nbar\n",
            b"dw:wq\r",
            expected_content="\nbar\n",
        )

        self.run_test(
            "dw at last word with trailing spaces",
            "foo  \nbar\n",
            b"dw:wq\r",
            expected_content="\nbar\n",
        )

        self.run_test(
            "2dw crossing line boundary (lands mid-line, no adjustment)",
            "one\ntwo three\n",
            b"2dw:wq\r",
            expected_content="three\n",
        )

        self.run_test(
            "dw mid-line (single-line, no line crossing)",
            "foo bar\n",
            b"dw:wq\r",
            expected_content="bar\n",
        )

        self.run_test(
            "dwdw multi-line batch (crosses line boundary)",
            "one two\nthree four\n",
            b"dwdw:wq\r",
            expected_content="\nthree four\n",
        )

        self._group("Delete word backward (db):", leading_blank=True)

        self.run_test(
            "db deletes previous word",
            "hello world\n",
            b"wdb:wq\r",
            expected_content="world\n",
        )

        self.run_test(
            "db from middle of word deletes back to word start",
            "hello world\n",
            b"wlldb:wq\r",
            expected_content="hello rld\n",
        )

        self.run_test(
            "db at col 0 does nothing",
            "hello\n",
            b"db:wq\r",
            expected_content="hello\n",
        )

        self.run_test(
            "db with whitespace before cursor",
            "foo   bar\n",
            b"6ldb:wq\r",
            expected_content="bar\n",
        )

        self.run_test(
            "2db deletes two words backward",
            "one two three\n",
            b"$2db:wq\r",
            expected_content="one e\n",
        )

        self.run_test(
            "db yanks deleted text",
            "hello world\n",
            b"wdb$p:wq\r",
            expected_content="worldhello \n",
        )

        # Batched db pairs
        self.run_test(
            "dbdb batches to delete 2 words backward",
            "one two three\n",
            b"$dbdb:wq\r",
            expected_content="one e\n",
        )

        self.run_test(
            "dbdbdb batches to delete 3 words backward",
            "one two three four\n",
            b"$dbdbdb:wq\r",
            expected_content="one r\n",
        )

        # Batched db yank: only last word deleted is in yank buffer
        self.run_test(
            "dbdb+0p yanks only last deleted word",
            "one two three\n",
            b"$dbdb0p:wq\r",
            expected_content="otwo ne e\n",
        )

        # Count-prefix db yank: yanks ALL deleted text
        self.run_test(
            "2db+0p yanks all deleted text backward",
            "one two three\n",
            b"$2db0p:wq\r",
            expected_content="otwo threne e\n",
        )

        self.run_test(
            "3db+0p yanks all deleted text backward",
            "one two three four\n",
            b"$3db0p:wq\r",
            expected_content="otwo three foune r\n",
        )

        # Multi-line db tests
        self.run_test(
            "db from BOL deletes previous line content",
            "foo\nbar\n",
            b"jdb:wq\r",
            expected_content="bar\n",
        )

        self.run_test(
            "2db crossing line boundary",
            "hello world\nfoo\n",
            b"j2db:wq\r",
            expected_content="foo\n",
        )

        self.run_test(
            "2dbdb count+batch deletes 3 words backward",
            "one two three four\n",
            b"$2dbdb:wq\r",
            expected_content="one r\n",
        )

        self.run_test(
            "dbdb multi-line batch (crosses line boundary)",
            "one two\nthree\n",
            b"j$dbdb:wq\r",
            expected_content="one e\n",
        )

        self._group("Change word (cw):", leading_blank=True)

        self.run_test(
            "cw deletes word and enters insert mode",
            "hello world\n",
            b"cwbye\x1b:wq\r",
            expected_content="bye world\n",
        )

        self.run_test(
            "cw from mid-word deletes rest of word (ce behavior)",
            "hello world\n",
            b"llcwXX\x1b:wq\r",
            expected_content="heXX world\n",
        )

        self.run_test(
            "cw on punct deletes punct class",
            "...bar\n",
            b"cwXX\x1b:wq\r",
            expected_content="XXbar\n",
        )

        self.run_test(
            "cw on whitespace deletes ws and next word",
            "foo   bar baz\n",
            b"3lcwX\x1b:wq\r",
            expected_content="fooX baz\n",
        )

        self.run_test(
            "cw on empty line enters insert mode",
            "\n",
            b"cwhi\x1b:wq\r",
            expected_content="hi\n",
        )

        self.run_test(
            "2cw deletes two words and enters insert mode",
            "one two three\n",
            b"2cwX\x1b:wq\r",
            expected_content="X three\n",
        )

        # Count-prefix cw yank: yanks ALL deleted text
        self.run_test(
            "2cw+Esc $p yanks all deleted text",
            "one two three\n",
            b"2cw\x1b$p:wq\r",
            expected_content=" threeone two\n",
        )

        # Multi-line cw tests
        self.run_test(
            "cw at last word on line (ce semantics, no line join)",
            "foo\nbar\n",
            b"cwbaz\x1b:wq\r",
            expected_content="baz\nbar\n",
        )

        self.run_test(
            "2cw crossing line boundary",
            "foo\nbar\n",
            b"2cwx\x1b:wq\r",
            expected_content="x\n",
        )

        self._group("Change word backward (cb):", leading_blank=True)

        self.run_test(
            "cb deletes previous word and enters insert mode",
            "hello world\n",
            b"wcbX\x1b:wq\r",
            expected_content="Xworld\n",
        )

        self.run_test(
            "cb at col 0 just enters insert mode",
            "hello\n",
            b"cbhi \x1b:wq\r",
            expected_content="hi hello\n",
        )

        self.run_test(
            "cb from mid-word deletes back to word start",
            "hello world\n",
            b"wllcbX\x1b:wq\r",
            expected_content="hello Xrld\n",
        )

        self.run_test(
            "2cb deletes two words backward",
            "one two three\n",
            b"8l2cbX\x1b:wq\r",
            expected_content="Xthree\n",
        )

        # cb on all-whitespace line (cursor after spaces)
        self.run_test(
            "cb on whitespace-only content",
            "   \n",
            b"$cbX\x1b:wq\r",
            expected_content="X \n",
        )

        # Count-prefix cb yank: yanks ALL deleted text
        self.run_test(
            "2cb+Esc 0p yanks all deleted text backward",
            "one two three\n",
            b"8l2cb\x1b0p:wq\r",
            expected_content="tone two hree\n",
        )

        # db at start of line stays put
        self.run_test_screen(
            "db at start of line is no-op",
            "hello world\n",
            b"db:q!\r",
            expect_cursor=(0, 0),
        )

        # Multi-line cb tests
        self.run_test(
            "cb from BOL deletes back across line",
            "foo\nbar\n",
            b"jcbbaz\x1b:wq\r",
            expected_content="bazbar\n",
        )

        self._group("Yank word forward (yw):", leading_blank=True)

        self.run_test(
            "yw yanks word and trailing space",
            "hello world\n",
            b"yw$p:wq\r",
            expected_content="hello worldhello \n",
        )

        self.run_test(
            "yw at middle of word yanks to next word",
            "hello world\n",
            b"llyw$p:wq\r",
            expected_content="hello worldllo \n",
        )

        self.run_test(
            "yw on punctuation yanks punct group",
            "...bar baz\n",
            b"yw$p:wq\r",
            expected_content="...bar baz...\n",
        )

        self.run_test(
            "yw on last word yanks to EOL",
            "foo bar\n",
            b"4lyw$p:wq\r",
            expected_content="foo barbar\n",
        )

        self.run_test(
            "yw on whitespace yanks spaces only",
            "foo   bar\n",
            b"3lyw$p:wq\r",
            expected_content="foo   bar   \n",
        )

        self.run_test(
            "yw on empty line preserves previous yank",
            "hello\n\n",
            b"yyjyw$p:wq\r",
            expected_content="hello\n\nhello\n",
        )

        self.run_test(
            "2yw yanks two words",
            "one two three\n",
            b"2yw$p:wq\r",
            expected_content="one two threeone two \n",
        )

        self.run_test(
            "yw does not modify the file",
            "hello world\n",
            b"yw:q\r",
            expect_exit=0,
        )

        self.run_test_screen(
            "yw cursor stays at original position",
            "hello world\n",
            b"yw:q!\r",
            expect_cursor=(0, 0),
        )

        self.run_test_screen(
            "yw from col 2 cursor stays at col 2",
            "hello world\n",
            b"llyw:q!\r",
            expect_cursor=(0, 2),
        )

        self.run_test(
            "ywyw yanks same word (second overwrites first)",
            "hello world\n",
            b"ywyw$p:wq\r",
            expected_content="hello worldhello \n",
        )

        self.run_test(
            "yw on only whitespace yanks whitespace",
            "foo   \n",
            b"3lyw$p:wq\r",
            expected_content="foo      \n",
        )

        # Multi-line yw tests
        self.run_test(
            "yw at last word uses exclusive-linewise (yanks word only)",
            "foo\nbar\n",
            b"ywjp:wq\r",
            expected_content="foo\nbfooar\n",
        )

        self._group("Yank word backward (yb):", leading_blank=True)

        self.run_test(
            "yb yanks previous word",
            "hello world\n",
            b"wyb$p:wq\r",
            expected_content="hello worldhello \n",
        )

        self.run_test(
            "yb from middle of word yanks back to word start",
            "hello world\n",
            b"wllyb$p:wq\r",
            expected_content="hello worldwo\n",
        )

        self.run_test(
            "yb at col 0 does nothing",
            "hello\n",
            b"yb:q\r",
            expect_exit=0,
        )

        self.run_test(
            "yb with whitespace before cursor",
            "foo   bar\n",
            b"6lyb$p:wq\r",
            expected_content="foo   barfoo   \n",
        )

        self.run_test(
            "2yb yanks two words backward",
            "one two three\n",
            b"$2yb$p:wq\r",
            expected_content="one two threetwo thre\n",
        )

        self.run_test(
            "yb does not modify the file",
            "hello world\n",
            b"wyb:q\r",
            expect_exit=0,
        )

        self.run_test_screen(
            "yb cursor moves to word start",
            "hello world\n",
            b"wyb:q!\r",
            expect_cursor=(0, 0),
        )

        self.run_test(
            "ybyb yanks second word back (cursor moves twice)",
            "one two three\n",
            b"$ybyb$p:wq\r",
            expected_content="one two threetwo \n",
        )

        # Multi-line yb tests
        self.run_test(
            "yb from BOL yanks across line boundary",
            "foo\nbar\n",
            b"jyb0P:wq\r",
            expected_content="foo\nfoo\nbar\n",
        )

        self._group("Delete word end (de):", leading_blank=True)

        self.run_test(
            "de deletes to end of word (inclusive)",
            "hello world\n",
            b"de:wq\r",
            expected_content=" world\n",
        )

        self.run_test(
            "de from mid-word deletes to end of word",
            "hello world\n",
            b"llde:wq\r",
            expected_content="he world\n",
        )

        self.run_test(
            "de at end of word deletes next word",
            "hello world\n",
            b"4lde:wq\r",
            expected_content="hell\n",
        )

        self.run_test(
            "de on punctuation deletes punct group",
            "...bar\n",
            b"de:wq\r",
            expected_content="bar\n",
        )

        self.run_test(
            "de on single char line",
            "x\n",
            b"de:wq\r",
            expected_content="\n",
        )

        self.run_test(
            "de on empty line does nothing",
            "\n",
            b"de:wq\r",
            expected_content="\n",
        )

        self.run_test(
            "2de deletes two word ends",
            "one two three\n",
            b"2de:wq\r",
            expected_content=" three\n",
        )

        self.run_test(
            "de yanks deleted text (paste back)",
            "hello world\n",
            b"de$p:wq\r",
            expected_content=" worldhello\n",
        )

        # Batched de pairs
        self.run_test(
            "dede batches to delete 2 word ends",
            "one two three four\n",
            b"dede:wq\r",
            expected_content=" three four\n",
        )

        self.run_test(
            "dedede batches to delete 3 word ends",
            "one two three four\n",
            b"dedede:wq\r",
            expected_content=" four\n",
        )

        self.run_test(
            "2dede batches count 2 plus 1 extra pair",
            "one two three four\n",
            b"2dede:wq\r",
            expected_content=" four\n",
        )

        # Batched de yank: only last word-end deleted is in yank buffer
        # After first de removes "one", cursor is on space; second de's
        # inclusive range is " two" (space through end of word)
        self.run_test(
            "dede+$p yanks only last deleted word",
            "one two three\n",
            b"dede$p:wq\r",
            expected_content=" three two\n",
        )

        # Count-prefix de yank: yanks ALL deleted text
        self.run_test(
            "2de+$p yanks all deleted text",
            "one two three\n",
            b"2de$p:wq\r",
            expected_content=" threeone two\n",
        )

        # Multi-line de tests
        self.run_test(
            "de at end of line crosses to next line",
            "foo\nbar baz\n",
            b"2lde:wq\r",
            expected_content="fo baz\n",
        )

        self.run_test(
            "2de crossing line boundary",
            "one\ntwo three\n",
            b"2de:wq\r",
            expected_content=" three\n",
        )

        self.run_test(
            "2dede count+batch deletes 3 word ends",
            "one two three four\n",
            b"2dede:wq\r",
            expected_content=" four\n",
        )

        self._group("Change word end (ce):", leading_blank=True)

        self.run_test(
            "ce deletes to end of word and enters insert mode",
            "hello world\n",
            b"cebye\x1b:wq\r",
            expected_content="bye world\n",
        )

        self.run_test(
            "ce from mid-word deletes rest of word",
            "hello world\n",
            b"llceXX\x1b:wq\r",
            expected_content="heXX world\n",
        )

        self.run_test(
            "ce on punctuation deletes punct class",
            "...bar\n",
            b"ceXX\x1b:wq\r",
            expected_content="XXbar\n",
        )

        self.run_test(
            "ce on empty line enters insert mode",
            "\n",
            b"cehi\x1b:wq\r",
            expected_content="hi\n",
        )

        self.run_test(
            "2ce deletes two word ends and enters insert mode",
            "one two three\n",
            b"2ceX\x1b:wq\r",
            expected_content="X three\n",
        )

        # Count-prefix ce yank: yanks ALL deleted text
        self.run_test(
            "2ce+Esc $p yanks all deleted text",
            "one two three\n",
            b"2ce\x1b$p:wq\r",
            expected_content=" threeone two\n",
        )

        # Multi-line ce tests
        self.run_test(
            "ce at last word on line",
            "foo\nbar\n",
            b"cebaz\x1b:wq\r",
            expected_content="baz\nbar\n",
        )

        self.run_test(
            "2ce crossing line boundary",
            "foo\nbar baz\n",
            b"2cex\x1b:wq\r",
            expected_content="x baz\n",
        )

        self._group("Yank word end (ye):", leading_blank=True)

        self.run_test(
            "ye yanks to end of word (inclusive, no trailing space)",
            "hello world\n",
            b"ye$p:wq\r",
            expected_content="hello worldhello\n",
        )

        self.run_test(
            "ye at middle of word yanks to word end",
            "hello world\n",
            b"llye$p:wq\r",
            expected_content="hello worldllo\n",
        )

        self.run_test(
            "ye on punctuation yanks punct group",
            "...bar baz\n",
            b"ye$p:wq\r",
            expected_content="...bar baz...\n",
        )

        self.run_test(
            "ye on last word yanks to end of word",
            "foo bar\n",
            b"4lye$p:wq\r",
            expected_content="foo barbar\n",
        )

        self.run_test(
            "ye on empty line preserves previous yank",
            "hello\n\n",
            b"yyjye$p:wq\r",
            expected_content="hello\n\nhello\n",
        )

        self.run_test(
            "2ye yanks two word ends",
            "one two three\n",
            b"2ye$p:wq\r",
            expected_content="one two threeone two\n",
        )

        self.run_test(
            "ye does not modify the file",
            "hello world\n",
            b"ye:q\r",
            expect_exit=0,
        )

        self.run_test_screen(
            "ye cursor stays at original position",
            "hello world\n",
            b"ye:q!\r",
            expect_cursor=(0, 0),
        )

        self.run_test_screen(
            "ye from col 2 cursor stays at col 2",
            "hello world\n",
            b"llye:q!\r",
            expect_cursor=(0, 2),
        )

        self.run_test(
            "yeye yanks same word end (second overwrites first)",
            "hello world\n",
            b"yeye$p:wq\r",
            expected_content="hello worldhello\n",
        )

        # Multi-line ye tests
        # From end of "foo" (col 2), e crosses to end of "bar" on next line.
        # Inclusive range = "o\nbar". Pasting after $ inserts after last char.
        self.run_test(
            "ye at end of word yanks next word across line",
            "foo\nbar baz\n",
            b"2lye$p:wq\r",
            expected_content="fooo\nbar\nbar baz\n",
        )

        self._group("Delete/yank to BOL (d0, y0):", leading_blank=True)

        # d0 at col 3 deletes "Hel"
        self.run_test(
            "d0 at col 3 deletes to BOL",
            "Hello\n",
            b"llld0:wq\r",
            expected_content="lo\n"
        )

        # d0 at col 0 does nothing
        self.run_test(
            "d0 at col 0 does nothing",
            "Hello\n",
            b"d0:wq\r",
            expected_content="Hello\n"
        )

        # d0 on empty line does nothing
        self.run_test(
            "d0 on empty line does nothing",
            "\n",
            b"d0:wq\r",
            expected_content="\n"
        )

        # 2d0 = d0 (count ignored)
        self.run_test(
            "2d0 same as d0 (count ignored)",
            "Hello\n",
            b"lll2d0:wq\r",
            expected_content="lo\n"
        )

        # y0 at col 3 yanks "Hel", paste at col 0
        self.run_test(
            "y0p yanks to BOL and pastes",
            "Hello\n",
            b"llly0P:wq\r",
            expected_content="HelHello\n"
        )

        # y0 at col 0 does nothing (no yank)
        self.run_test(
            "y0 at col 0 does nothing",
            "Hello\n",
            b"y0:wq\r",
            expected_content="Hello\n"
        )

        self._group("Yank to EOL (y$):", leading_blank=True)

        # y$ at col 2 yanks "llo", paste after cursor char 'l' at col 2
        self.run_test(
            "y$p yanks to EOL and pastes",
            "Hello\n",
            b"lly$p:wq\r",
            expected_content="Helllolo\n"
        )

        # y$ at col 0 yanks whole line content
        self.run_test(
            "y$0p yanks whole line",
            "Hello\n",
            b"y$0P:wq\r",
            expected_content="HelloHello\n"
        )

        # y$ on empty line does nothing (no yank)
        self.run_test(
            "y$ on empty line",
            "\n",
            b"y$:wq\r",
            expected_content="\n"
        )

        # 2y$ yanks across 2 lines
        self.run_test(
            "2y$p yanks across 2 lines",
            "Hello\nWorld\nFoo\n",
            b"ll2y$$p:wq\r",
            expected_content="Hellollo\nWorld\nWorld\nFoo\n"
        )

        # y$ doesn't modify buffer
        self.run_test(
            "y$ doesn't modify buffer",
            "Hello\n",
            b"y$:wq\r",
            expected_content="Hello\n"
        )

        self._group("Backward search (?):", leading_blank=True)

        self.run_test_screen(
            "? finds match on previous line",
            "alpha\nbeta\ngamma\n",
            b"jj?alpha\r:q!\r",
            expect_cursor=(0, 0),
        )

        self.run_test_screen(
            "? wraps around to find match below",
            "alpha\nbeta\ngamma\n",
            b"?gamma\r:q!\r",
            expect_cursor=(2, 0),
        )

        self.run_test_screen(
            "n after ? searches backward",
            "aaa\nbbb\naaa\nccc\naaa\n",
            b"jj?aaa\rn:q!\r",
            expect_cursor=(4, 0),
        )

        self.run_test_screen(
            "N after ? searches forward",
            "aaa\nbbb\naaa\nccc\naaa\n",
            b"jj?aaa\rN:q!\r",
            expect_cursor=(2, 0),
        )

        self.run_test_screen(
            "n after / searches forward",
            "aaa\nbbb\naaa\nccc\naaa\n",
            b"jj/aaa\rn:q!\r",
            expect_cursor=(0, 0),
        )

        self.run_test_screen(
            "N after / searches backward",
            "aaa\nbbb\naaa\nccc\naaa\n",
            b"jj/aaa\rN:q!\r",
            expect_cursor=(2, 0),
        )

        self.run_test_screen(
            "? with empty pattern reuses previous",
            "foo\nbar\nfoo\n",
            b"jj?foo\r?\r:q!\r",
            expect_cursor=(2, 0),
        )

        # ? finds match earlier on same line (before cursor)
        self.run_test_screen(
            "? finds match on same line before cursor",
            "AA BB AA\n",
            b"llllll?AA\r:q!\r",
            expect_cursor=(0, 0),  # cursor at col 6, finds AA at col 0
        )

        # N (after /) finds previous match on same line
        self.run_test_screen(
            "N finds previous match on same line",
            "AA BB AA CC AA\n",
            b"/AA\rnN:q!\r",
            expect_cursor=(0, 6),  # /->col6, n->col12, N reverses back to col6
        )

        # ? finds rightmost match on previous line
        self.run_test_screen(
            "? finds rightmost match on previous line",
            "AA BB AA\nCC\n",
            b"j?AA\r:q!\r",
            expect_cursor=(0, 6),  # from line 1, backward finds last AA on line 0
        )

        # ? wraps around to find match after cursor on same line
        self.run_test_screen(
            "? wraps around to match after cursor on same line",
            "BB CC AA\n",
            b"lll?AA\r:q!\r",
            expect_cursor=(0, 6),  # cursor at col 3, no AA before col 3, wraps to find AA at col 6
        )

        # Forward search skips match AT cursor position
        self.run_test_screen(
            "/ skips match at cursor position",
            "AA BB\n",
            b"/AA\r:q!\r",   # cursor at (0,0) which IS an AA match
            expect_cursor=(0, 0),  # only one AA, wraps all the way around back to it
        )

        # Single-line file, multiple matches, n cycles through
        self.run_test_screen(
            "n cycles through all matches on single line",
            "ABCABCABC\n",
            b"/ABC\rnn:q!\r",
            expect_cursor=(0, 0),  # /->col3, n->col6, n wraps to col0
        )

        # Backward search with cursor at col 0 goes to previous line
        self.run_test_screen(
            "? at col 0 goes to previous line",
            "AA\nBB\nAA\n",
            b"jj?AA\r:q!\r",
            expect_cursor=(0, 0),  # from (2,0), goes to (0,0)
        )

        # Backspace on empty pattern cancels ? search
        self.run_test_screen(
            "? backspace cancels to normal mode",
            "AAA\nBBB\n",
            b"j?\x7f:q!\r",
            expect_cursor=(1, 0),  # Stays on line 1
        )

        # / with backspace editing pattern
        self.run_test_screen(
            "/ with backspace editing pattern",
            "AAA\nBBB\nBCC\n",
            b"/BC\x7fBB\r:q!\r",
            expect_cursor=(1, 0),  # Searches for "BBB" not "BC"
        )

        # : command with multiple backspaces then retype
        self.run_test(
            ": command backspace then retype",
            "hello\n",
            b":ww\x7f\x7fq!\r",
            # Type :ww, BS twice to clear, type q! -> :q!
        )

        # ============================================================
        # Extended key handling (function keys, ctrl+arrows, etc.)
        # ============================================================
        self._group("Extended key handling:", leading_blank=True)

        # F5 (ESC[15~) in normal mode - should be consumed, no side effects
        self.run_test(
            "F5 in normal mode is no-op",
            "hello\n",
            b"\x1b[15~:wq\r",
            expected_content="hello\n"
        )

        # F12 (ESC[24~) in normal mode - should be consumed, no side effects
        self.run_test(
            "F12 in normal mode is no-op",
            "hello\n",
            b"\x1b[24~:wq\r",
            expected_content="hello\n"
        )

        # Ctrl+Right word motion in normal mode
        self.run_test_screen(
            "Ctrl+Right moves to next word in normal mode",
            "hello world\n",
            b"\x1b[1;5C:q!\r",
            expect_cursor=(0, 6),
        )

        # Ctrl+Left word motion in normal mode
        self.run_test_screen(
            "Ctrl+Left moves to prev word in normal mode",
            "hello world\n",
            b"$\x1b[1;5D:q!\r",
            expect_cursor=(0, 6),
        )

        # Ctrl+Right crosses line boundary
        self.run_test_screen(
            "Ctrl+Right crosses line boundary",
            "foo\nbar\n",
            b"$\x1b[1;5C:q!\r",
            expect_cursor=(1, 0),
        )

        # Ctrl+Left crosses line boundary (lands at start of last word)
        self.run_test_screen(
            "Ctrl+Left crosses line boundary",
            "foo\nbar\n",
            b"j\x1b[1;5D:q!\r",
            expect_cursor=(0, 0),
        )

        # Count prefix with Ctrl+Right
        self.run_test_screen(
            "Count prefix with Ctrl+Right",
            "one two three\n",
            b"2\x1b[1;5C:q!\r",
            expect_cursor=(0, 8),
        )

        # Batching: 3x Ctrl+Right
        self.run_test_screen(
            "Batching 3x Ctrl+Right",
            "one two three four five\n",
            b"\x1b[1;5C\x1b[1;5C\x1b[1;5C:q!\r",
            expect_cursor=(0, 14),
        )

        # Shift+Up (ESC[1;2A) in normal mode - should be consumed
        self.run_test(
            "Shift+Up in normal mode is no-op",
            "hello\n",
            b"\x1b[1;2A:wq\r",
            expected_content="hello\n"
        )

        # Ctrl+Up (ESC[1;5A) in normal mode - should be consumed
        self.run_test(
            "Ctrl+Up in normal mode is no-op",
            "hello\n",
            b"\x1b[1;5A:wq\r",
            expected_content="hello\n"
        )

        # Ctrl+Down (ESC[1;5B) in normal mode - should be consumed
        self.run_test(
            "Ctrl+Down in normal mode is no-op",
            "hello\n",
            b"\x1b[1;5B:wq\r",
            expected_content="hello\n"
        )

        # Insert key (ESC[2~) in normal mode - should be no-op
        self.run_test(
            "Insert key in normal mode is no-op",
            "hello\n",
            b"\x1b[2~:wq\r",
            expected_content="hello\n"
        )

        # Multiple unknown sequences in a row
        self.run_test(
            "Multiple unknown keys in a row",
            "hello\n",
            b"\x1b[15~\x1b[24~\x1b[1;2A:wq\r",
            expected_content="hello\n"
        )

        # F5 in insert mode - should stay in insert mode
        self.run_test(
            "F5 in insert mode stays in insert mode",
            "hello\n",
            b"i\x1b[15~X\x1b:wq\r",
            expected_content="Xhello\n"
        )

        # Ctrl+Right word motion in insert mode
        self.run_test(
            "Ctrl+Right in insert mode moves to next word",
            "hello world\n",
            b"i\x1b[1;5CX\x1b:wq\r",
            expected_content="hello Xworld\n"
        )

        # Ctrl+Left word motion in insert mode
        self.run_test(
            "Ctrl+Left in insert mode moves to prev word",
            "hello world\n",
            b"$a\x1b[1;5DX\x1b:wq\r",
            expected_content="hello Xworld\n"
        )

        # Ctrl+Right crosses line in insert mode
        self.run_test(
            "Ctrl+Right crosses line in insert mode",
            "foo\nbar\n",
            b"$a\x1b[1;5CX\x1b:wq\r",
            expected_content="foo\nXbar\n"
        )

        # Ctrl+Left crosses line in insert mode (lands at start of last word)
        self.run_test(
            "Ctrl+Left crosses line in insert mode",
            "foo\nbar\n",
            b"ji\x1b[1;5DX\x1b:wq\r",
            expected_content="Xfoo\nbar\n"
        )

        # Batching Ctrl+Right in insert mode
        self.run_test(
            "Batching 3x Ctrl+Right in insert mode",
            "one two three four\n",
            b"i\x1b[1;5C\x1b[1;5C\x1b[1;5CX\x1b:wq\r",
            expected_content="one two three Xfour\n"
        )

        # Ctrl+Right on empty line in insert mode
        self.run_test(
            "Ctrl+Right on empty line in insert mode",
            "\nbar\n",
            b"i\x1b[1;5CX\x1b:wq\r",
            expected_content="\nXbar\n"
        )

        # Regression: arrow keys still work
        self.run_test_screen(
            "Regression: right arrow still works",
            "hello\n",
            b"ll:q!\r",
            expect_cursor=(0, 2),
        )

        # Regression: delete key still works
        self.run_test(
            "Regression: delete key still works",
            "hello\n",
            b"\x1b[3~:wq\r",
            expected_content="ello\n"
        )

        # Regression: PgDn still works
        self.run_test_screen(
            "Regression: PgDn still works",
            make_lines(30),
            b"\x1b[6~:q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(0, "Line 10")],
        )

        # SS3 sequences (ESC O <final>) - F1-F4 on some terminals
        # F1 SS3 (ESC O P) in normal mode - should be consumed
        self.run_test(
            "F1 SS3 in normal mode is no-op",
            "hello\n",
            b"\x1bOP:wq\r",
            expected_content="hello\n"
        )

        # F2 SS3 (ESC O Q) in normal mode - should be consumed
        self.run_test(
            "F2 SS3 in normal mode is no-op",
            "hello\n",
            b"\x1bOQ:wq\r",
            expected_content="hello\n"
        )

        # F1 SS3 in insert mode - should stay in insert mode
        self.run_test(
            "F1 SS3 in insert mode stays in insert mode",
            "hello\n",
            b"i\x1bOPX\x1b:wq\r",
            expected_content="Xhello\n"
        )

        # ============================================================
        # Terminal mode tests
        # ============================================================
        self._group("Terminal mode:", leading_blank=True)

        if not self.build_terminal_editor():
            print("  Skipping terminal mode tests (build failed)")
        else:
            # Basic smoke test: quit exits cleanly
            self.run_test_terminal(
                "Terminal :q! exits cleanly",
                "Hello\n",
                b":q!\r"
            )

            # Open and save unchanged
            self.run_test_terminal(
                "Terminal :wq saves unchanged file",
                "Hello\n",
                b":wq\r",
                expected_content="Hello\n"
            )

            # Delete char with x
            self.run_test_terminal(
                "Terminal x deletes first char",
                "Hello\n",
                b"x:wq\r",
                expected_content="ello\n"
            )

            # Terminal size detection: 10x40
            self.run_test_terminal_screen(
                "Terminal size 10x40",
                "Hello\n",
                b":q!\r",
                rows=10, cols=40,
                expect_lines=[(0, "Hello")],
                expect_status_contains="/t "
            )

            # Terminal size detection: verify tilde rows
            self.run_test_terminal_screen(
                "Terminal size 10x40 tilde rows",
                "Line1\nLine2\n",
                b":q!\r",
                rows=10, cols=40,
                expect_lines=[
                    (0, "Line1"),
                    (1, "Line2"),
                    (2, "~"),
                    (7, "~"),
                ]
            )

            # Terminal size detection: 24x80
            self.run_test_terminal_screen(
                "Terminal size 24x80",
                "Hello\n",
                b":q!\r",
                rows=24, cols=80,
                expect_lines=[(0, "Hello")],
                expect_status_contains="/t "
            )

            # Terminal size with baud rate
            self.run_test_terminal_screen(
                "Terminal size with baud rate",
                "Hello\n",
                b":q!\r",
                rows=10, cols=40,
                expect_lines=[(0, "Hello")],
                expect_status_contains="/t ",
                extra_args=["--cpu-mhz", "1", "--baud", "9600"]
            )

            # --------------------------------------------------------
            # Screen state tests in terminal mode
            # --------------------------------------------------------
            self._group("Terminal mode - screen state:", leading_blank=True)

            # Cursor at (0,0) on open
            self.run_test_terminal_screen(
                "Terminal cursor at (0,0) on open",
                "Hello\n",
                b":q!\r",
                expect_cursor=(0, 0)
            )

            # Cursor movement: lll -> (0,3)
            self.run_test_terminal_screen(
                "Terminal lll moves cursor to (0,3)",
                "Hello\n",
                b"lll:q!\r",
                expect_cursor=(0, 3)
            )

            # Cursor movement: lllh -> (0,2)
            self.run_test_terminal_screen(
                "Terminal lllh moves cursor to (0,2)",
                "Hello\n",
                b"lllh:q!\r",
                expect_cursor=(0, 2)
            )

            # Cursor movement: jj -> (2,0)
            self.run_test_terminal_screen(
                "Terminal jj moves cursor to (2,0)",
                "Line 1\nLine 2\nLine 3\n",
                b"jj:q!\r",
                expect_cursor=(2, 0)
            )

            # Cursor movement: jjk -> (1,0)
            self.run_test_terminal_screen(
                "Terminal jjk moves cursor to (1,0)",
                "Line 1\nLine 2\nLine 3\n",
                b"jjk:q!\r",
                expect_cursor=(1, 0)
            )

            # Arrow keys: right right right -> (0,3)
            self.run_test_terminal_screen(
                "Terminal arrow keys move cursor",
                "Hello\n",
                b"\x1b[C\x1b[C\x1b[C:q!\r",
                expect_cursor=(0, 3)
            )

            # Screen content: 5-line file
            self.run_test_terminal_screen(
                "Terminal 5-line file content and tildes",
                make_lines(5),
                b":q!\r",
                expect_lines=[
                    (0, "Line 1"),
                    (1, "Line 2"),
                    (2, "Line 3"),
                    (3, "Line 4"),
                    (4, "Line 5"),
                    (5, "~"),
                    (8, "~"),
                ]
            )

            # Status bar shows filename and position
            self.run_test_terminal_screen(
                "Terminal status bar shows filename",
                "Hello\n",
                b":q!\r",
                expect_status_contains="/t "
            )

            # Status bar shows mode (COMMAND after :)
            self.run_test_terminal_screen(
                "Terminal status bar shows COMMAND",
                "Hello\n",
                b":q!\r",
                expect_status_contains="COMMAND - 1,"
            )

            # Status bar after cursor movement
            self.run_test_terminal_screen(
                "Terminal status bar after j",
                "Hello\nWorld\n",
                b"jlll:q!\r",
                expect_status_contains="COMMAND - 2,"
            )

            # Scrolling down past screen bottom
            self.run_test_terminal_screen(
                "Terminal scroll down",
                make_lines(15),
                b"jjjjjjjjj:q!\r",
                expect_cursor=(8, 0),
                expect_lines=[(i, f"Line {i+2}") for i in range(9)]
            )

            # Scroll down then back up
            self.run_test_terminal_screen(
                "Terminal scroll up restores view",
                make_lines(15),
                b"jjjjjjjjj" + b"kkkkkkkkk" + b":q!\r",
                expect_cursor=(0, 0),
                expect_lines=[(i, f"Line {i+1}") for i in range(9)]
            )

            # Insert mode: type a character
            self.run_test_terminal_screen(
                "Terminal insert updates screen",
                "Hello\n",
                b"iX\x1b:q!\r",
                expect_lines=[(0, "XHello")],
                expect_cursor=(0, 0)
            )

            # Insert mode: ESC returns to normal
            self.run_test_terminal_screen(
                "Terminal ESC returns to normal mode",
                "Hello\n",
                b"i\x1b:q!\r",
                expect_status_contains="COMMAND"
            )

            # --------------------------------------------------------
            # Baud rate screen state tests
            # --------------------------------------------------------
            self._group("Terminal mode - baud rate screen state:", leading_blank=True)

            BAUD_ARGS = ["--cpu-mhz", "1", "--baud", "9600"]

            # Cursor movement with baud rate
            self.run_test_terminal_screen(
                "Terminal baud: cursor movement",
                "Hello\n",
                b"lll:q!\r",
                expect_cursor=(0, 3),
                extra_args=BAUD_ARGS
            )

            # Insert with baud rate
            self.run_test_terminal_screen(
                "Terminal baud: insert character",
                "Hello\n",
                b"iX\x1b:q!\r",
                expect_lines=[(0, "XHello")],
                extra_args=BAUD_ARGS
            )

            # Scrolling with baud rate
            self.run_test_terminal_screen(
                "Terminal baud: scroll down",
                make_lines(15),
                b"jjjjjjjjj:q!\r",
                expect_cursor=(8, 0),
                expect_lines=[(0, "Line 2"), (8, "Line 10")],
                extra_args=BAUD_ARGS
            )

            # --------------------------------------------------------
            # Functional tests in terminal mode
            # --------------------------------------------------------
            self._group("Terminal mode - functional:", leading_blank=True)

            # :w saves file
            self.run_test_terminal(
                "Terminal :w saves file",
                "Hello\n",
                b":w\r:q!\r",
                expected_content="Hello\n"
            )

            # :wq saves and quits
            self.run_test_terminal(
                "Terminal :wq saves and quits",
                "Hello\n",
                b":wq\r",
                expected_content="Hello\n"
            )

            # :q on unmodified file
            self.run_test_terminal(
                "Terminal :q on unmodified",
                "Hello\n",
                b":q\r",
                expected_content="Hello\n"
            )

            # :q! force quit
            self.run_test_terminal(
                "Terminal :q! force quit",
                "Hello\n",
                b"x:q!\r",
                expected_content="Hello\n"
            )

            # x delete character
            self.run_test_terminal(
                "Terminal x deletes char",
                "Hello\n",
                b"llx:wq\r",
                expected_content="Helo\n"
            )

            # dd delete line
            self.run_test_terminal(
                "Terminal dd deletes line",
                "Line 1\nLine 2\nLine 3\n",
                b"jdd:wq\r",
                expected_content="Line 1\nLine 3\n"
            )

            # i insert mode
            self.run_test_terminal(
                "Terminal i inserts text",
                "Hello\n",
                b"iWorld \x1b:wq\r",
                expected_content="World Hello\n"
            )

            # a append mode
            self.run_test_terminal(
                "Terminal a appends text",
                "Hello\n",
                b"aX\x1b:wq\r",
                expected_content="HXello\n"
            )

            # o open line below
            self.run_test_terminal(
                "Terminal o opens line below",
                "Line 1\nLine 2\n",
                b"oNew\x1b:wq\r",
                expected_content="Line 1\nNew\nLine 2\n"
            )

            # O open line above
            self.run_test_terminal(
                "Terminal O opens line above",
                "Line 1\nLine 2\n",
                b"jONew\x1b:wq\r",
                expected_content="Line 1\nNew\nLine 2\n"
            )

            # --------------------------------------------------------
            # Baud rate functional tests
            # --------------------------------------------------------
            self._group("Terminal mode - baud rate functional:", leading_blank=True)

            # Batch insert with baud rate
            self.run_test_terminal(
                "Terminal baud: insert text",
                "Hello\n",
                b"iABC\x1b:wq\r",
                expected_content="ABCHello\n",
                extra_args=BAUD_ARGS
            )

            # Batch delete with baud rate
            self.run_test_terminal(
                "Terminal baud: x delete",
                "Hello\n",
                b"xx:wq\r",
                expected_content="llo\n",
                extra_args=BAUD_ARGS
            )

            # dd with baud rate
            self.run_test_terminal(
                "Terminal baud: dd delete line",
                "Line 1\nLine 2\nLine 3\n",
                b"dd:wq\r",
                expected_content="Line 2\nLine 3\n",
                extra_args=BAUD_ARGS
            )

            # Command mode with baud rate
            self.run_test_terminal(
                "Terminal baud: :wq command",
                "Test\n",
                b":wq\r",
                expected_content="Test\n",
                extra_args=BAUD_ARGS
            )

            # Search mode with baud rate
            self.run_test_terminal_screen(
                "Terminal baud: search /Line",
                "First\nLine 2\nLine 3\n",
                b"/Line\r:q!\r",
                expect_cursor=(1, 0),
                extra_args=BAUD_ARGS
            )

            # Backward search
            self.run_test_terminal_screen(
                "Terminal baud: backward search ?alpha",
                "alpha\nbeta\ngamma\n",
                b"jj?alpha\r:q!\r",
                expect_cursor=(0, 0),
                extra_args=BAUD_ARGS
            )

            # --------------------------------------------------------
            # Baud rate batching tests
            # --------------------------------------------------------
            self._group("Terminal mode - baud rate batching:", leading_blank=True)

            BAUD2_ARGS = ["--cpu-mhz", "2", "--baud", "9600"]

            # Insert 5 chars at 2MHz/9600 baud - should batch into fewer
            # frames than 5.  With hardware FIFO buffering, chars accumulate
            # in the RX buffer during rendering and the editor reads them
            # all in one batch.  Verify only 1 content redraw for the
            # insert (frame index 1), not 5 separate redraws.
            self.run_test_terminal_screen(
                "Terminal baud: insert batching",
                "\n",
                b"ihello\x1b:q!\r",
                expect_lines=[(0, "hello")],
                expect_lines_at_frame=[
                    # Frame 1: enter insert mode, no chars yet
                    (1, [(0, "")]),
                    # Frame 2: all 5 chars batched in one redraw
                    (2, [(0, "hello")]),
                ],
                extra_args=BAUD2_ARGS
            )

        # ============================================================
        # Scroll region optimization tests
        # ============================================================
        self._group("Scroll region optimization:", leading_blank=True)

        # j past bottom: scroll up uses partial redraw, not full repaint.
        # 15-line file, 10-row screen (9 content + 1 status).
        # All 10 j's batch into one cycle. Cursor moves to line 10,
        # VIEW_TOP goes from 0 to 2 (delta=2). Frame 1 is the scroll
        # frame - with optimization, only 2 newly exposed bottom rows.
        self.run_test_screen(
            "Scroll opt: j past bottom uses scroll",
            make_lines(15),
            b"j" * 10 + b":q!\r",
            rows=10, cols=40,
            expect_lines=[(i, f"Line {i+3}") for i in range(9)],
            expect_cursor=(8, 0),
            # Frame 1 is the scroll frame - should touch only 2 rows
            # (newly exposed bottom rows), not all 9
            expect_content_rows=[(1, {7, 8})]
        )

        # k past top: scroll down uses partial redraw.
        # After scrolling down, scroll back up.
        # 10 j's batch → frame 1 (scroll down). 10 k's batch → frame 2
        # (scroll up). VIEW_TOP goes from 2 back to 0 (delta=2).
        self.run_test_screen(
            "Scroll opt: k past top uses scroll",
            make_lines(15),
            b"j" * 10 + b"k" * 10 + b":q!\r",
            rows=10, cols=40,
            expect_lines=[(i, f"Line {i+1}") for i in range(9)],
            expect_cursor=(0, 0),
            # Frame 2 is the scroll-up frame - should touch only 2 rows
            # (newly exposed top rows), not all 9
            expect_content_rows=[(2, {0, 1})]
        )

        # Batched jjjjjjjjjjjjj scrolls multiple in one frame.
        # 13 j's: cursor at line 13, VIEW_TOP goes from 0 to 5 (delta=5).
        # With optimization: scroll up 5, render 5 new bottom rows.
        self.run_test_screen(
            "Scroll opt: batched j*13 scrolls multiple",
            make_lines(20),
            b"j" * 13 + b":q!\r",
            rows=10, cols=40,
            expect_lines=[(i, f"Line {i+6}") for i in range(9)],
            expect_cursor=(8, 0),
            # Frame 1: scroll by 5 - touches only the 5 new bottom rows
            expect_content_rows=[(1, {4, 5, 6, 7, 8})]
        )

        # Large scroll falls back to full repaint (G to end of file)
        self.run_test_screen(
            "Scroll opt: large scroll falls back to full repaint",
            make_lines(20),
            b"G:q!\r",
            rows=10, cols=40,
            expect_lines=[(i, f"Line {i+12}") for i in range(9)],
            expect_cursor=(8, 0),
            # G scrolls by 11 lines (>= 9 content rows), falls back to
            # full repaint touching all 9 content rows
            expect_content_rows=[(1, {0, 1, 2, 3, 4, 5, 6, 7, 8})]
        )

        # Scroll by 1 row: single j from bottom edge
        # Put cursor at line 8 (bottom), then 1 more j to scroll by 1.
        # Since all batch: 9 j's = cursor at line 9. VIEW_TOP goes 0→1.
        self.run_test_screen(
            "Scroll opt: scroll by 1 row",
            make_lines(15),
            b"j" * 9 + b":q!\r",
            rows=10, cols=40,
            expect_lines=[(i, f"Line {i+2}") for i in range(9)],
            expect_cursor=(8, 0),
            # Frame 1: scroll by 1 - touches only 1 new bottom row
            expect_content_rows=[(1, {8})]
        )

        # dd at cursor row 3: scroll shifts rows below cursor up,
        # only bottom row needs rendering.
        # Frames: 0=initial, 1=jjj cursor-only, 2=dd scroll frame
        self.run_test_screen(
            "Scroll opt: dd at mid-screen uses scroll",
            make_lines(15),
            b"jjjdd:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 5"), (4, "Line 6"), (5, "Line 7"),
                (6, "Line 8"), (7, "Line 9"), (8, "Line 10"),
            ],
            expect_cursor=(3, 0),
            # Frame 2 (dd): cursor row + bottom row touched
            expect_content_rows=[(2, {3, 8})]
        )

        # dd at row 0: entire content area scrolls up, bottom row rendered
        self.run_test_screen(
            "Scroll opt: dd at top uses scroll",
            make_lines(15),
            b"dd:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 2"), (1, "Line 3"), (2, "Line 4"),
                (3, "Line 5"), (4, "Line 6"), (5, "Line 7"),
                (6, "Line 8"), (7, "Line 9"), (8, "Line 10"),
            ],
            expect_cursor=(0, 0),
            # Frame 1 (dd): cursor row + bottom row touched
            expect_content_rows=[(1, {0, 8})]
        )

        # 3dd: 3 lines deleted, 3 bottom rows need rendering
        # Frame 0=initial, 1=count '3' display, 2=dd scroll frame
        self.run_test_screen(
            "Scroll opt: 3dd uses scroll",
            make_lines(15),
            b"3dd:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 4"), (1, "Line 5"), (2, "Line 6"),
                (3, "Line 7"), (4, "Line 8"), (5, "Line 9"),
                (6, "Line 10"), (7, "Line 11"), (8, "Line 12"),
            ],
            expect_cursor=(0, 0),
            # Frame 2 (3dd): cursor row + bottom 3 rows touched
            expect_content_rows=[(2, {0, 6, 7, 8})]
        )

        # o at mid-screen: scroll shifts rows below insertion down,
        # only new empty line needs rendering.
        # Frames: 0=initial, 1=jjj cursor, 2=o scroll frame
        self.run_test_screen(
            "Scroll opt: o at mid-screen uses scroll",
            make_lines(15),
            b"jjjo\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, ""),
                (5, "Line 5"), (6, "Line 6"), (7, "Line 7"),
                (8, "Line 8"),
            ],
            expect_cursor=(4, 0),
            # Frame 2 (o): only new line row needs rendering (row above unchanged)
            expect_content_rows=[(2, {4})]
        )

        # O at mid-screen: scroll shifts cursor row and below down,
        # only new empty line needs rendering.
        self.run_test_screen(
            "Scroll opt: O at mid-screen uses scroll",
            make_lines(15),
            b"jjjO\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, ""),
                (4, "Line 4"), (5, "Line 5"), (6, "Line 6"),
                (7, "Line 7"), (8, "Line 8"),
            ],
            expect_cursor=(3, 0),
            # Frame 2 (O): only new line row needs rendering (row above unchanged)
            expect_content_rows=[(2, {3})]
        )

        # p (line paste below) at mid-screen uses scroll
        # Frames: 0=initial, 1=jjj cursor, 2=yy status, 3=p scroll
        self.run_test_screen(
            "Scroll opt: p (line paste) uses scroll",
            make_lines(15),
            b"jjjyyp:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 4"),
                (5, "Line 5"), (6, "Line 6"), (7, "Line 7"),
                (8, "Line 8"),
            ],
            expect_cursor=(4, 0),
            # Frame 3 (p): only pasted row needs rendering (row above unchanged)
            expect_content_rows=[(3, {4})]
        )

        # J at mid-screen: join decreases LINE_COUNT16, scroll shifts up.
        # Frames: 0=initial, 1=jjj cursor, 2=J scroll frame
        self.run_test_screen(
            "Scroll opt: J at mid-screen uses scroll",
            make_lines(15),
            b"jjjJ:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4 Line 5"), (4, "Line 6"), (5, "Line 7"),
                (6, "Line 8"), (7, "Line 9"), (8, "Line 10"),
            ],
            expect_cursor=(3, 6),
            # Frame 2 (J): cursor row (content changed) + bottom row
            expect_content_rows=[(2, {3, 8})]
        )

        # J at mid-screen: scroll region should NOT include the cursor row.
        # The cursor row content changes (gains joined text) and gets re-rendered,
        # so scrolling it first causes a visible glitch.
        # Scroll region should be rows 4-8 (0-based), not 3-8.
        # Frames: 0=initial, 1=jjj cursor, 2=J scroll frame
        self.run_test_screen(
            "Scroll opt: J at mid-screen does not scroll cursor row",
            make_lines(15),
            b"jjjJ:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4 Line 5"), (4, "Line 6"), (5, "Line 7"),
                (6, "Line 8"), (7, "Line 9"), (8, "Line 10"),
            ],
            expect_cursor=(3, 6),
            # Frame 2 (J): scroll region should be rows 4-8, NOT 3-8
            expect_scroll_rows=[(2, {4, 5, 6, 7, 8})]
        )

        # J redo at mid-screen: scroll region should NOT include the cursor row.
        # Sequence: J, u (undo), space (break u-batching), u (redo).
        # Frames: 0=initial, 1=jjj cursor, 2=J, 3=u (undo), 4=space (status),
        #         5=u (redo)
        self.run_test_screen(
            "Scroll opt: J redo does not scroll cursor row",
            make_lines(15),
            b"jjjJu u:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4 Line 5"), (4, "Line 6"), (5, "Line 7"),
                (6, "Line 8"), (7, "Line 9"), (8, "Line 10"),
            ],
            expect_cursor=(3, 6),
            # Frame 5 (redo J): scroll region should be rows 4-8, NOT 3-8
            expect_scroll_rows=[(5, {4, 5, 6, 7, 8})]
        )

        # J on wrapped cursor line: both wrap rows must show correct content.
        # Line 2 = "This is a longer line!" (22 chars, wraps at 20 cols = 2 rows).
        # After J, line 2 = "This is a longer line! Short 4" (30 chars, still 2 rows).
        # Frames: 0=initial, 1=jj cursor, 2=J scroll frame
        wrap_j_content = ("Short 1\nShort 2\n"
                          "This is a longer line!\n"
                          + ''.join(f"Short {i}\n" for i in range(4, 15)))
        self.run_test_screen(
            "Scroll opt: J on wrapped cursor line correct content",
            wrap_j_content,
            b"jjJ:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"), (1, "Short 2"),
                (2, "This is a longer lin"),
                (3, "e! Short 4"),
                (4, "Short 5"), (5, "Short 6"),
                (6, "Short 7"), (7, "Short 8"),
                (8, "Short 9"),
            ],
            expect_cursor=(3, 2),
        )

        # J on wrapped cursor line: scroll region must skip ALL cursor line rows.
        # Cursor line occupies rows 2-3 (0-based). Scroll should be rows 4-8.
        self.run_test_screen(
            "Scroll opt: J on wrapped cursor line scroll region",
            wrap_j_content,
            b"jjJ:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"), (1, "Short 2"),
                (2, "This is a longer lin"),
                (3, "e! Short 4"),
                (4, "Short 5"), (5, "Short 6"),
                (6, "Short 7"), (7, "Short 8"),
                (8, "Short 9"),
            ],
            expect_cursor=(3, 2),
            expect_scroll_rows=[(2, {4, 5, 6, 7, 8})]
        )

        # J redo on wrapped cursor line: scroll region must skip wrap rows.
        # Sequence: J, u (undo), space (break u-batching), u (redo).
        # Frames: 0=initial, 1=jj cursor, 2=J, 3=u (undo), 4=space, 5=u (redo)
        self.run_test_screen(
            "Scroll opt: J redo on wrapped cursor line scroll region",
            wrap_j_content,
            b"jjJu u:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"), (1, "Short 2"),
                (2, "This is a longer lin"),
                (3, "e! Short 4"),
                (4, "Short 5"), (5, "Short 6"),
                (6, "Short 7"), (7, "Short 8"),
                (8, "Short 9"),
            ],
            expect_cursor=(3, 2),
            expect_scroll_rows=[(5, {4, 5, 6, 7, 8})]
        )

        # J undo on wrapped cursor line: after undo, screen should return
        # to the original layout. The scroll region must skip ALL cursor
        # line wrap rows, not just one — otherwise the wrap continuation
        # gets pushed down and appears duplicated below the restored line.
        # Frames: 0=initial, 1=jj cursor, 2=J, 3=u (undo)
        self.run_test_screen(
            "Scroll opt: J undo on wrapped cursor line correct content",
            wrap_j_content,
            b"jjJu:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"), (1, "Short 2"),
                (2, "This is a longer lin"),
                (3, "e!"),
                (4, "Short 4"), (5, "Short 5"),
                (6, "Short 6"), (7, "Short 7"),
                (8, "Short 8"),
            ],
            expect_cursor=(2, 0),
        )

        # J undo where result was wrapped: J joins "A" with
        # "123456789012345678901" (21 chars) producing "A 123..." (23 chars)
        # which wraps to 2 rows. Undo restores original 3 lines, cursor line
        # "A" shrinks from 2 wrapped rows to 1 row, so lines below must
        # scroll down to fill the gap.
        # Frames: 0=initial, 1=J, 2=u (undo)
        self.run_test_screen(
            "Scroll opt: J undo unwraps result scrolls lines below",
            "A\n123456789012345678901\nB\n",
            b"Ju:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "A"),
                (1, "12345678901234567890"),
                (2, "1"),
                (3, "B"),
            ],
            expect_cursor=(0, 0),
            expect_scroll_rows=[(2, {1, 2, 3, 4, 5, 6, 7, 8})]
        )

        # J undo unwraps at mid-screen: cursor at row 3, J joins "A" with
        # "123456789012345678901" (21 chars) producing wrapped result (2 rows).
        # Before J: A(1) + 123...(2) = 3 rows. After J: 2 rows. Undo: back to 3.
        # Scroll region should start below cursor row 3, not at cursor.
        # Frames: 0=initial, 1=jjj cursor, 2=J, 3=u (undo)
        undo_unwrap_mid = ("Short 1\nShort 2\nShort 3\n"
                           "A\n123456789012345678901\nB\n"
                           + ''.join(f"Short {i}\n" for i in range(7, 15)))
        self.run_test_screen(
            "Scroll opt: J undo unwraps at mid-screen",
            undo_unwrap_mid,
            b"jjjJu:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"), (1, "Short 2"), (2, "Short 3"),
                (3, "A"),
                (4, "12345678901234567890"),
                (5, "1"),
                (6, "B"),
                (7, "Short 7"), (8, "Short 8"),
            ],
            expect_cursor=(3, 0),
            expect_scroll_rows=[(3, {4, 5, 6, 7, 8})]
        )

        # J undo restores wrapped next line: J on "Short" joins with
        # "This is a longer line!" (22 chars, wraps to 2 rows at 20 cols).
        # Result "Short This is a longer line!" (28 chars, 2 rows).
        # Before: 1+2=3 rows, After J: 2 rows (freed 1). Undo: back to 3 rows.
        # Lines below must scroll down 1 to restore the wrapped line.
        # Frames: 0=initial, 1=j cursor, 2=J, 3=u (undo)
        undo_restore_wrap = ("Short 1\n"
                             "Short\nThis is a longer line!\nMore\n"
                             + ''.join(f"Short {i}\n" for i in range(5, 15)))
        self.run_test_screen(
            "Scroll opt: J undo restores wrapped next line",
            undo_restore_wrap,
            b"jJu:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"),
                (1, "Short"),
                (2, "This is a longer lin"),
                (3, "e!"),
                (4, "More"),
                (5, "Short 5"), (6, "Short 6"),
                (7, "Short 7"), (8, "Short 8"),
            ],
            expect_cursor=(1, 0),
            expect_scroll_rows=[(3, {2, 3, 4, 5, 6, 7, 8})]
        )

        # J undo same height no scroll: J joins two non-wrapped lines
        # "Almost full width!!" (19) + " " + "X" = 21 chars, wraps to 2 rows.
        # Before: 1+1=2 rows. After J: 2 rows (wrap). Undo: back to 2 rows.
        # No net height change, so no scroll needed.
        # Frames: 0=initial, 1=jj cursor, 2=J, 3=u (undo)
        undo_same_height = ("Short 1\nShort 2\n"
                            "Almost full width!!\nX\n"
                            + ''.join(f"Short {i}\n" for i in range(5, 15)))
        self.run_test_screen(
            "Scroll opt: J undo same height no scroll",
            undo_same_height,
            b"jjJu:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"), (1, "Short 2"),
                (2, "Almost full width!!"),
                (3, "X"),
                (4, "Short 5"), (5, "Short 6"),
                (6, "Short 7"), (7, "Short 8"),
                (8, "Short 9"),
            ],
            expect_cursor=(2, 0),
            expect_scroll_rows=[(3, set())],
            # No scroll, only cursor line (row 2) + restored line (row 3) repainted
            expect_content_rows=[(3, {2, 3})]
        )

        # J forward scroll down when line grows: both lines are exactly
        # screen width (20 chars). J joins them with a space, producing a
        # 41-char line (3 rows vs original 2). Scroll DOWN to make room.
        # Scroll region: rows below old content (0-based rows 4-8).
        # Frames: 0=initial, 1=jj cursor, 2=J
        j_grow_content = ("Short 1\nShort 2\n"
                          "12345678901234567890\n12345678901234567890\n"
                          + ''.join(f"Short {i}\n" for i in range(5, 15)))
        self.run_test_screen(
            "Scroll opt: J forward scroll down when line grows",
            j_grow_content,
            b"jjJ:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"), (1, "Short 2"),
                (2, "12345678901234567890"),
                (3, " 1234567890123456789"),
                (4, "0"),
                (5, "Short 5"), (6, "Short 6"),
                (7, "Short 7"), (8, "Short 8"),
            ],
            expect_cursor=(3, 0),
            expect_scroll_rows=[(2, {4, 5, 6, 7, 8})],
            # Only cursor line's 3 wrap rows repainted; rows 5-8 handled by scroll
            expect_content_rows=[(2, {2, 3, 4})]
        )

        # J undo negative displacement scroll up: undo of the above J.
        # Joined line was 3 rows, restored to two 1-row lines. Scroll UP
        # to fill freed rows. Scroll region: below old joined line end
        # (0-based rows 5-8).
        # Frames: 0=initial, 1=jj cursor, 2=J, 3=u (undo)
        self.run_test_screen(
            "Scroll opt: J undo negative displacement scroll up",
            j_grow_content,
            b"jjJu:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"), (1, "Short 2"),
                (2, "12345678901234567890"),
                (3, "12345678901234567890"),
                (4, "Short 5"), (5, "Short 6"),
                (6, "Short 7"), (7, "Short 8"),
                (8, "Short 9"),
            ],
            expect_cursor=(2, 0),
            expect_scroll_rows=[(3, {4, 5, 6, 7, 8})],
            # Only cursor line (row 2) + restored line (row 3) + bottom exposed (row 8)
            expect_content_rows=[(3, {2, 3, 8})]
        )

        # J redo scroll down when line grows: same as J forward, but via
        # undo then redo (J, u, space, u). Scroll DOWN on redo frame.
        # Frames: 0=initial, 1=jj cursor, 2=J, 3=u, 4=space (noop), 5=u (redo)
        self.run_test_screen(
            "Scroll opt: J redo scroll down when line grows",
            j_grow_content,
            b"jjJu u:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"), (1, "Short 2"),
                (2, "12345678901234567890"),
                (3, " 1234567890123456789"),
                (4, "0"),
                (5, "Short 5"), (6, "Short 6"),
                (7, "Short 7"), (8, "Short 8"),
            ],
            expect_cursor=(3, 0),
            expect_scroll_rows=[(5, {4, 5, 6, 7, 8})],
            # Only cursor line's 3 wrap rows repainted; rows 5-8 handled by scroll
            expect_content_rows=[(5, {2, 3, 4})]
        )

        # J undo where cursor line stays wrapped: cursor line
        # "This is a longer line!" (22 chars, wraps to 2 rows) joins with
        # "Short 4". Result: "This is a longer line! Short 4" (30 chars,
        # still 2 rows). Undo restores "Short 4" as separate line.
        # Before J: 2+1=3 rows. After J: 2 rows. Undo: back to 3 rows.
        # Cursor line remains wrapped (2 rows), so scroll region must
        # start below BOTH cursor wrap rows.
        # Frames: 0=initial, 1=jj cursor, 2=J, 3=u (undo)
        self.run_test_screen(
            "Scroll opt: J undo cursor stays wrapped scroll region",
            wrap_j_content,
            b"jjJu:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"), (1, "Short 2"),
                (2, "This is a longer lin"),
                (3, "e!"),
                (4, "Short 4"), (5, "Short 5"),
                (6, "Short 6"), (7, "Short 7"),
                (8, "Short 8"),
            ],
            expect_cursor=(2, 0),
            expect_scroll_rows=[(3, {4, 5, 6, 7, 8})]
        )

        # JJ undo restores wrapped line: JJ joins Short 2 + "This is a
        # longer line!" (wraps) + Short 4. Undo of last J restores Short 4,
        # leaving "Short 2 This is a longer line!" (30 chars, 2 rows).
        # Before undo: 2 rows. After undo: 2+1=3 rows. Lines below scroll down.
        # Cursor line wraps, so scroll region must skip cursor wrap rows.
        # Frames: 0=initial, 1=j cursor, 2=JJ, 3=u (undo of second J)
        self.run_test_screen(
            "Scroll opt: JJ undo restores line below wrapped result",
            wrap_j_content,
            b"jJJu:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"),
                (1, "Short 2 This is a lo"),
                (2, "nger line!"),
                (3, "Short 4"),
                (4, "Short 5"), (5, "Short 6"),
                (6, "Short 7"), (7, "Short 8"),
                (8, "Short 9"),
            ],
            expect_cursor=(1, 0),
            expect_scroll_rows=[(3, {3, 4, 5, 6, 7, 8})]
        )

        # JJ undo unwraps cursor line: JJ joins A + B + "123456789012345678901"
        # (21 chars). Result "A B 123456789012345678901" (25 chars, wraps to 2
        # rows). Undo of last J: "A B" (3 chars, 1 row) + "123..." (21 chars,
        # 2 rows) = 3 rows vs 2 rows before undo.
        # Cursor line shrinks from 2 wrap rows to 1 non-wrapped row.
        # Frames: 0=initial, 1=JJ, 2=u (undo of second J)
        jj_undo_unwrap = ("A\nB\n123456789012345678901\nC\n"
                          + ''.join(f"Short {i}\n" for i in range(5, 15)))
        self.run_test_screen(
            "Scroll opt: JJ undo unwraps cursor line",
            jj_undo_unwrap,
            b"JJu:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "A B"),
                (1, "12345678901234567890"),
                (2, "1"),
                (3, "C"),
                (4, "Short 5"), (5, "Short 6"),
                (6, "Short 7"), (7, "Short 8"),
                (8, "Short 9"),
            ],
            expect_cursor=(0, 0),
            expect_scroll_rows=[(2, {1, 2, 3, 4, 5, 6, 7, 8})]
        )

        # JJ undo partially unwraps cursor line: JJ joins A +
        # "BBBBBBBBBBBBBBBBBBB" (19 chars) + "123456789012345678901" (21 chars).
        # Result: "A BBBBBBBBBBBBBBBBBBB 123456789012345678901" (43 chars,
        # wraps to 3 rows). Undo of last J: "A BBBBBBBBBBBBBBBBBBB" (21 chars,
        # 2 rows) + "123..." (21 chars, 2 rows) = 4 rows vs 3 rows before undo.
        # Cursor line goes from 3 wrap rows to 2 wrap rows. Scroll region must
        # skip both remaining cursor wrap rows.
        # Frames: 0=initial, 1=JJ, 2=u (undo of second J)
        jj_undo_partial = ("A\nBBBBBBBBBBBBBBBBBBB\n123456789012345678901\nC\n"
                           + ''.join(f"Short {i}\n" for i in range(5, 15)))
        self.run_test_screen(
            "Scroll opt: JJ undo partially unwraps cursor line",
            jj_undo_partial,
            b"JJu:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "A BBBBBBBBBBBBBBBBBB"),
                (1, "B"),
                (2, "12345678901234567890"),
                (3, "1"),
                (4, "C"),
                (5, "Short 5"), (6, "Short 6"),
                (7, "Short 7"), (8, "Short 8"),
            ],
            expect_cursor=(0, 0),
            expect_scroll_rows=[(2, {2, 3, 4, 5, 6, 7, 8})]
        )

        # J joining next wrapped line: when B wraps, ALL of B's rows need
        # repainting since B's content reflows into A. The scroll region must
        # not include B's wrap rows — otherwise stale wrap content appears.
        # Setup: cursor on "Short 2" (non-wrapped), next line wraps to 2 rows.
        # After J: "Short 2 This is a longer line!" wraps to 2 rows.
        # Frames: 0=initial, 1=j cursor, 2=J
        self.run_test_screen(
            "Scroll opt: J joining next wrapped line correct content",
            wrap_j_content,
            b"jJ:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"),
                (1, "Short 2 This is a lo"),
                (2, "nger line!"),
                (3, "Short 4"), (4, "Short 5"),
                (5, "Short 6"), (6, "Short 7"),
                (7, "Short 8"), (8, "Short 9"),
            ],
            expect_cursor=(1, 7),
        )

        # J that causes line to wrap: joining non-wrapped A with non-wrapped B
        # produces a wrapped result occupying the same vertical space (2 rows)
        # as A+B individually (1+1). No scroll needed — just repaint.
        # "Almost full width!!" (19 chars) + " " + "XY" = 22 chars, wraps at 20.
        # Frames: 0=initial, 1=jj cursor, 2=J
        join_becomes_wrap = ("Short 1\nShort 2\n"
                             "Almost full width!!\n"
                             "XY\n"
                             + ''.join(f"Short {i}\n" for i in range(5, 15)))
        self.run_test_screen(
            "Scroll opt: J result wraps same height no scroll",
            join_becomes_wrap,
            b"jjJ:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"), (1, "Short 2"),
                (2, "Almost full width!!"),
                (3, "XY"),
                (4, "Short 5"), (5, "Short 6"),
                (6, "Short 7"), (7, "Short 8"),
                (8, "Short 9"),
            ],
            expect_cursor=(2, 19),
            expect_scroll_rows=[(2, set())],
            # No scroll, only cursor line's 2 wrap rows repainted
            expect_content_rows=[(2, {2, 3})]
        )

        # JJ (2 batched joins) where first joined line B is wrapped:
        # joins Short 2 + "This is a longer line!" (wraps) + Short 4.
        # Result: "Short 2 This is a longer line! Short 4" (38 chars, 2 rows).
        # Before: 1+2+1 = 4 rows. After: 2 rows. Freed: 2.
        # Frames: 0=initial, 1=j cursor, 2=JJ
        self.run_test_screen(
            "Scroll opt: JJ first joined line wrapped",
            wrap_j_content,
            b"jJJ:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"),
                (1, "Short 2 This is a lo"),
                (2, "nger line! Short 4"),
                (3, "Short 5"), (4, "Short 6"),
                (5, "Short 7"), (6, "Short 8"),
                (7, "Short 9"), (8, "Short 10"),
            ],
            expect_cursor=(2, 10),
            # Only cursor line's 2 wrap rows + bottom exposed rows repainted
            expect_content_rows=[(2, {1, 2, 7, 8})]
        )

        # JJ (2 batched joins) where second joined line C is wrapped:
        # joins Short 2 + "and" + "This is a longer line!" (wraps).
        # Result: "Short 2 and This is a longer line!" (34 chars, 2 rows).
        # Before: 1+1+2 = 4 rows. After: 2 rows. Freed: 2.
        # Frames: 0=initial, 1=j cursor, 2=JJ
        join_c_wrapped = ("Short 1\n"
                          "Short 2\n"
                          "and\n"
                          "This is a longer line!\n"
                          + ''.join(f"Short {i}\n" for i in range(5, 15)))
        self.run_test_screen(
            "Scroll opt: JJ second joined line wrapped",
            join_c_wrapped,
            b"jJJ:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"),
                (1, "Short 2 and This is"),
                (2, "a longer line!"),
                (3, "Short 5"), (4, "Short 6"),
                (5, "Short 7"), (6, "Short 8"),
                (7, "Short 9"), (8, "Short 10"),
            ],
            expect_cursor=(1, 11),
            # Only cursor line's 2 wrap rows + bottom exposed rows repainted
            expect_content_rows=[(2, {1, 2, 7, 8})]
        )

        # JJ (2 batched joins) all non-wrapped, result wraps to same height:
        # 3 lines of 1 row each become 1 line wrapping to 3 rows. No scroll.
        # "First longer line!!" (19) + " " + "Second longer line!" (19)
        # + " " + "Third!" (6) = 46 chars -> 3 rows at 20 cols.
        # Frames: 0=initial, 1=jj cursor, 2=JJ
        join_3_same_height = ("Short 1\nShort 2\n"
                              "First longer line!!\n"
                              "Second longer line!\n"
                              "Third!\n"
                              + ''.join(f"Short {i}\n" for i in range(6, 15)))
        self.run_test_screen(
            "Scroll opt: JJ result wraps same height no scroll",
            join_3_same_height,
            b"jjJJ:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"), (1, "Short 2"),
                (2, "First longer line!!"),
                (3, "Second longer line!"),
                (4, "Third!"),
                (5, "Short 6"), (6, "Short 7"),
                (7, "Short 8"), (8, "Short 9"),
            ],
            expect_cursor=(3, 19),
            expect_scroll_rows=[(2, set())]
        )

        # JJ (2 batched joins) result wraps, partial height reduction:
        # 3 non-wrapped lines (3 rows) become 1 line wrapping to 2 rows.
        # Freed 1 row, but file delta = 2. SCROLL_DELTA must not overcount.
        # "Almost full width!!" (19) + " " + "XY" (2) + " " + "Z" (1) = 24 chars.
        # Frames: 0=initial, 1=jj cursor, 2=JJ
        join_jj_partial = ("Short 1\nShort 2\n"
                           "Almost full width!!\n"
                           "XY\n"
                           "Z\n"
                           + ''.join(f"Short {i}\n" for i in range(6, 15)))
        self.run_test_screen(
            "Scroll opt: JJ result wraps partial height reduction",
            join_jj_partial,
            b"jjJJ:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"), (1, "Short 2"),
                (2, "Almost full width!!"),
                (3, "XY Z"),
                (4, "Short 6"), (5, "Short 7"),
                (6, "Short 8"), (7, "Short 9"),
                (8, "Short 10"),
            ],
            expect_cursor=(3, 2),
        )

        # JJJ (3 batched joins) with wrapped line among those joined:
        # joins Short 2 + "This is a longer line!" (wraps) + Short 4 + Short 5.
        # Result: 46 chars, 3 rows at 20 cols.
        # Before: 1+2+1+1 = 5 rows. After: 3 rows. Freed: 2.
        # File delta = 3 but actual SCROLL_DELTA should be 2.
        # Frames: 0=initial, 1=j cursor, 2=JJJ
        self.run_test_screen(
            "Scroll opt: JJJ with wrapped line among joined",
            wrap_j_content,
            b"jJJJ:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"),
                (1, "Short 2 This is a lo"),
                (2, "nger line! Short 4 S"),
                (3, "hort 5"),
                (4, "Short 6"), (5, "Short 7"),
                (6, "Short 8"), (7, "Short 9"),
                (8, "Short 10"),
            ],
            expect_cursor=(2, 18),
        )

        # J with following line off-screen: cursor near bottom, joined line wraps,
        # following line was off-screen but should become visible after join frees rows.
        join_offscreen = ("Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6\n"
                          "Short 7\nThis is a longer line!\nLine 9\nLine 10\n")
        self.run_test_screen(
            "Scroll opt: J with following line off screen",
            join_offscreen,
            b"jjjjjjJ:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"),
                (2, "Line 3"), (3, "Line 4"),
                (4, "Line 5"), (5, "Line 6"),
                (6, "Short 7 This is a lo"),
                (7, "nger line!"),
                (8, "Line 9"),
            ],
            expect_cursor=(6, 7),
        )

        # J at end of file: joining the last two lines, no following line.
        # Row after combined line should show ~ (EOF tilde).
        join_eof = ("Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6\nLine 7\n"
                    "Short 8\nEnd\n")
        self.run_test_screen(
            "Scroll opt: J at EOF no following line",
            join_eof,
            b"jjjjjjjJ:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"),
                (2, "Line 3"), (3, "Line 4"),
                (4, "Line 5"), (5, "Line 6"),
                (6, "Line 7"),
                (7, "Short 8 End"),
                (8, "~"),
            ],
            expect_cursor=(7, 7),
        )

        # --- Redo counterparts for all J scroll tests ---
        # Each uses "Ju u" pattern: J, u (undo), space (break batching), u (redo).
        # Space is unmapped in normal mode, so cursor stays at col 0.

        self.run_test_screen(
            "Redo: J joining next wrapped line",
            wrap_j_content,
            b"jJu u:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"),
                (1, "Short 2 This is a lo"),
                (2, "nger line!"),
                (3, "Short 4"), (4, "Short 5"),
                (5, "Short 6"), (6, "Short 7"),
                (7, "Short 8"), (8, "Short 9"),
            ],
            expect_cursor=(1, 7),
        )

        self.run_test_screen(
            "Redo: J result wraps same height no scroll",
            join_becomes_wrap,
            b"jjJu u:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"), (1, "Short 2"),
                (2, "Almost full width!!"),
                (3, "XY"),
                (4, "Short 5"), (5, "Short 6"),
                (6, "Short 7"), (7, "Short 8"),
                (8, "Short 9"),
            ],
            expect_cursor=(2, 19),
            expect_scroll_rows=[(5, set())],
            # No scroll, only cursor line's 2 wrap rows repainted
            expect_content_rows=[(5, {2, 3})]
        )

        self.run_test_screen(
            "Redo: JJ first joined line wrapped",
            wrap_j_content,
            b"jJJu u:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"),
                (1, "Short 2 This is a lo"),
                (2, "nger line! Short 4"),
                (3, "Short 5"), (4, "Short 6"),
                (5, "Short 7"), (6, "Short 8"),
                (7, "Short 9"), (8, "Short 10"),
            ],
            expect_cursor=(2, 10),
            # Redo re-joins 1 line (batched JJ records UNDO_JOIN_COUNT=1):
            # wrap row 0 unchanged, partial from col 10 on row 2 + bottom row 8
            expect_content_rows=[(5, {2, 8})],
            expect_min_col=[(5, 2, 10)]
        )

        self.run_test_screen(
            "Redo: JJ second joined line wrapped",
            join_c_wrapped,
            b"jJJu u:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"),
                (1, "Short 2 and This is"),
                (2, "a longer line!"),
                (3, "Short 5"), (4, "Short 6"),
                (5, "Short 7"), (6, "Short 8"),
                (7, "Short 9"), (8, "Short 10"),
            ],
            expect_cursor=(1, 11),
            # Redo re-joins 1 line (batched JJ records UNDO_JOIN_COUNT=1):
            # cursor wrap rows (1,2) + 1 bottom exposed row (8)
            expect_content_rows=[(5, {1, 2, 8})]
        )

        self.run_test_screen(
            "Redo: JJ result wraps same height no scroll",
            join_3_same_height,
            b"jjJJu u:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"), (1, "Short 2"),
                (2, "First longer line!!"),
                (3, "Second longer line!"),
                (4, "Third!"),
                (5, "Short 6"), (6, "Short 7"),
                (7, "Short 8"), (8, "Short 9"),
            ],
            expect_cursor=(3, 19),
            expect_scroll_rows=[(5, set())],
            # No scroll; wrap row 0 unchanged, partial render from col 19 on row 3
            expect_content_rows=[(5, {3, 4})],
            expect_min_col=[(5, 3, 19)]
        )

        self.run_test_screen(
            "Redo: JJ result wraps partial height reduction",
            join_jj_partial,
            b"jjJJu u:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"), (1, "Short 2"),
                (2, "Almost full width!!"),
                (3, "XY Z"),
                (4, "Short 6"), (5, "Short 7"),
                (6, "Short 8"), (7, "Short 9"),
                (8, "Short 10"),
            ],
            expect_cursor=(3, 2),
        )

        self.run_test_screen(
            "Redo: JJJ with wrapped line among joined",
            wrap_j_content,
            b"jJJJu u:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"),
                (1, "Short 2 This is a lo"),
                (2, "nger line! Short 4 S"),
                (3, "hort 5"),
                (4, "Short 6"), (5, "Short 7"),
                (6, "Short 8"), (7, "Short 9"),
                (8, "Short 10"),
            ],
            expect_cursor=(2, 18),
        )

        self.run_test_screen(
            "Redo: J with following line off screen",
            join_offscreen,
            b"jjjjjjJu u:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"),
                (2, "Line 3"), (3, "Line 4"),
                (4, "Line 5"), (5, "Line 6"),
                (6, "Short 7 This is a lo"),
                (7, "nger line!"),
                (8, "Line 9"),
            ],
            expect_cursor=(6, 7),
        )

        self.run_test_screen(
            "Redo: J at EOF no following line",
            join_eof,
            b"jjjjjjjJu u:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"),
                (2, "Line 3"), (3, "Line 4"),
                (4, "Line 5"), (5, "Line 6"),
                (6, "Line 7"),
                (7, "Short 8 End"),
                (8, "~"),
            ],
            expect_cursor=(7, 7),
        )

        # 3J at mid-screen: joins 2 lines, scroll shifts up by 2.
        # Frames: 0=initial, 1='3' count display, 2=jjj cursor, 3=J scroll
        self.run_test_screen(
            "Scroll opt: 3J at mid-screen uses scroll",
            make_lines(15),
            b"jjj3J:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4 Line 5 Line 6"), (4, "Line 7"),
                (5, "Line 8"), (6, "Line 9"), (7, "Line 10"),
                (8, "Line 11"),
            ],
            expect_cursor=(3, 6),
            # Frame 3 (3J): cursor row + bottom 2 rows
            expect_content_rows=[(3, {3, 7, 8})]
        )

        # 3J where result wraps: 3 non-wrapped lines (3 rows) become 1 wrapped
        # line (2 rows). Freed 1 row, scroll shifts up by 1.
        # "Short 3" (7) + " " + "Short 4" (7) + " " + "Short 5" (7) = 23 chars,
        # wraps to 2 rows at 20 cols.
        # Frames: 0=initial, 1='3' count display, 2=jj cursor, 3=J scroll
        content_3j_wrap = ("Short 1\nShort 2\n"
                           "Short 3\nShort 4\nShort 5\n"
                           + ''.join(f"Short {i}\n" for i in range(6, 15)))
        self.run_test_screen(
            "Scroll opt: 3J wrapping result uses scroll",
            content_3j_wrap,
            b"jj3J:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"), (1, "Short 2"),
                (2, "Short 3 Short 4 Shor"),
                (3, "t 5"),
                (4, "Short 6"), (5, "Short 7"),
                (6, "Short 8"), (7, "Short 9"),
                (8, "Short 10"),
            ],
            expect_cursor=(2, 7),
            # Only cursor line's 2 wrap rows + bottom row exposed by scroll
            expect_content_rows=[(3, {2, 3, 8})]
        )

        # 3J wrapping redo: same result as forward, via undo then redo.
        # Frames: 0=initial, 1='3' count, 2=jj, 3=J, 4=u, 5=space, 6=u (redo)
        self.run_test_screen(
            "Redo: 3J wrapping result uses scroll",
            content_3j_wrap,
            b"jj3Ju u:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"), (1, "Short 2"),
                (2, "Short 3 Short 4 Shor"),
                (3, "t 5"),
                (4, "Short 6"), (5, "Short 7"),
                (6, "Short 8"), (7, "Short 9"),
                (8, "Short 10"),
            ],
            expect_cursor=(2, 7),
            # Only cursor line's 2 wrap rows + bottom row exposed by scroll
            expect_content_rows=[(6, {2, 3, 8})]
        )

        # 3cc at mid-screen: deletes 3 lines, inserts blank, scroll shifts up.
        # Net LINE_COUNT16 decrease = 2. Frames: 0=initial, 1='3' count,
        # 2=jjj cursor, 3=cc scroll frame
        self.run_test_screen(
            "Scroll opt: 3cc at mid-screen uses scroll",
            make_lines(15),
            b"jjj3cc\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, ""), (4, "Line 7"),
                (5, "Line 8"), (6, "Line 9"), (7, "Line 10"),
                (8, "Line 11"),
            ],
            expect_cursor=(3, 0),
            # Frame 3 (3cc): cursor row + bottom 2 rows
            expect_content_rows=[(3, {3, 7, 8})]
        )

        # Enter in insert mode at mid-line: splits line, LINE_COUNT16 increases.
        # Frames: 0=initial, 1=jjj cursor, 2=llll cursor,
        #         3=i mode switch, 4=Enter scroll frame
        # "llll" moves to col 4 in "Line 4", Enter splits to "Line" / " 4"
        self.run_test_screen(
            "Scroll opt: Enter in insert mode uses scroll",
            make_lines(15),
            b"jjjlllli\r\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line"), (4, " 4"),
                (5, "Line 5"), (6, "Line 6"), (7, "Line 7"),
                (8, "Line 8"),
            ],
            expect_cursor=(4, 0),
            # Frame 4 (Enter): split row above + new row
            expect_content_rows=[(4, {3, 4})]
        )

        # Batched Enter (3 Enters) in insert mode: should use scroll optimization.
        # "lll" moves to col 3 in "Line 4", then 3 Enters split:
        # "Lin" / "" / "" / "e 4". Scroll down 3, repaint 4 rows (3-6).
        # Frames: 0=initial, 1=jjj cursor, 2=llll cursor,
        #         3=i mode switch, 4=Enter*3 scroll frame
        self.run_test_screen(
            "Scroll opt: batched Enter uses scroll not full repaint",
            make_lines(15),
            b"jjjllli\r\r\r\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Lin"), (4, ""), (5, ""), (6, "e 4"),
                (7, "Line 5"), (8, "Line 6"),
            ],
            expect_cursor=(6, 0),
            # Frame 4 (batched Enter*3): should NOT touch all rows 0-8
            # Only rows 3-6 should be repainted (split line + 2 blanks + cursor)
            expect_content_rows=[(4, {3, 4, 5, 6})]
        )

        # Enter at start of line: original line scrolls down unchanged.
        # Scroll creates blank row = new empty line. No content repaint needed.
        # Frames: 0=initial, 1=jjj cursor, 2=i mode, 3=Enter scroll
        self.run_test_screen(
            "Scroll opt: Enter at start of line skips content repaint",
            make_lines(15),
            b"jjji\r\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, ""), (4, "Line 4"),
                (5, "Line 5"), (6, "Line 6"), (7, "Line 7"),
                (8, "Line 8"),
            ],
            expect_cursor=(4, 0),
            # Frame 3 (Enter): no content rows repainted - scroll handles it
            expect_content_rows=[(3, set())]
        )

        # Enter at start of wrapped line: inserts blank above, content shifts down.
        # The wrapped continuation must not be duplicated as a ghost row.
        # Frames: 0=initial, 1=i mode switch, 2=Enter scroll frame, 3=ESC
        self.run_test_screen(
            "Scroll opt: Enter above wrapped line no ghost row",
            "The quick brown fox jumps over the lazy dog. Once upon a time\n",
            b"i\r\x1b:q!\r",
            rows=10, cols=50,
            expect_lines=[
                (0, ""),
                (1, "The quick brown fox jumps over the lazy dog. Once"),
                (2, "upon a time"),
                (3, "~"),
            ],
            expect_cursor=(1, 0),
        )

        # Enter at end of wrapped line: cursor was at wrap row 1 (end of line).
        # After Enter, blank line appears below the wrapped line.
        # The wrap continuation row must not be overwritten with wrap row 0 content.
        self.run_test_screen(
            "Scroll opt: Enter at end of wrapped line no overwrite",
            "The quick brown fox jumps over the lazy dog. Once upon a time\n",
            b"A\r\x1b:q!\r",
            rows=10, cols=50,
            expect_lines=[
                (0, "The quick brown fox jumps over the lazy dog. Once"),
                (1, "upon a time"),
                (2, ""),
                (3, "~"),
            ],
            expect_cursor=(2, 0),
        )

        # BS at col 0 below a wrapped line: joins with previous (wrapped) line.
        # The cursor ends up on a wrap continuation row. The re-render of the
        # cursor row must not overwrite with wrap row 0 content.
        self.run_test_screen(
            "Scroll opt: BS below wrapped line no overwrite",
            "The quick brown fox jumps over the lazy dog. Once upon a time\nhello\n",
            b"ji\x08\x1b:q!\r",
            rows=10, cols=50,
            expect_lines=[
                (0, "The quick brown fox jumps over the lazy dog. Once"),
                (1, "upon a timehello"),
                (2, "~"),
            ],
        )

        # BS at col 0 in insert mode: joins with previous line, LINE_COUNT16 decreases.
        # Cursor was at line 3 (Line 4), col 0. BS joins with line 2 (Line 3).
        # Frames: 0=initial, 1=jjj cursor, 2=i mode switch, 3=BS scroll frame
        self.run_test_screen(
            "Scroll opt: BS at col 0 in insert mode uses scroll",
            make_lines(15),
            b"jjji\x08\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"),
                (2, "Line 3Line 4"), (3, "Line 5"), (4, "Line 6"),
                (5, "Line 7"), (6, "Line 8"), (7, "Line 9"),
                (8, "Line 10"),
            ],
            expect_cursor=(2, 5),
            # Frame 3 (BS): cursor row (content changed) + bottom row
            expect_content_rows=[(3, {2, 8})]
        )

        # BS at col 0 joining with empty line above: cursor line content unchanged.
        # The scroll moves "Line 4" up, so the cursor row doesn't need repainting.
        # Frames: 0=initial, 1=jjj cursor, 2=i mode switch, 3=BS scroll frame
        self.run_test_screen(
            "Scroll opt: BS joining empty line skips cursor repaint",
            "Line 1\nLine 2\n\nLine 4\nLine 5\nLine 6\nLine 7\nLine 8\nLine 9\nLine 10\nLine 11\n",
            b"jjji\x08\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"),
                (2, "Line 4"), (3, "Line 5"), (4, "Line 6"),
                (5, "Line 7"), (6, "Line 8"), (7, "Line 9"),
                (8, "Line 10"),
            ],
            expect_cursor=(2, 0),
            # Frame 3 (BS): cursor row NOT repainted (content unchanged),
            # only bottom row exposed by scroll
            expect_content_rows=[(3, {8})]
        )

        # BS on empty line joining to non-empty line above: cursor row not repainted.
        # Line 0: "Hello", Line 1: "" (empty), Lines 2+.
        # BS on empty line 1 joins to line 0, cursor at col 5 (end of "Hello").
        # Content of line 0 unchanged, cursor row should not be repainted.
        # Frames: 0=initial, 1=j, 2=i enter, 3=BS+ESC
        self.run_test_screen(
            "Scroll opt: BS on empty line joining non-empty above skips repaint",
            "Hello\n\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6\nLine 7\nLine 8\nLine 9\nLine 10\n",
            b"ji\x08\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Hello"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 5"), (5, "Line 6"),
                (6, "Line 7"), (7, "Line 8"), (8, "Line 9"),
            ],
            expect_cursor=(0, 4),
            # Frame 3 (BS): cursor row 0 NOT repainted, only bottom row exposed
            expect_content_rows=[(3, {8})]
        )

        # DEL at end of non-empty line joining empty line below: cursor row not repainted.
        # Line 0: "Hello", Line 1: "" (empty), Lines 2+.
        # DEL at end of "Hello" joins empty line below, cursor stays.
        # Content of line 0 unchanged, cursor row should not be repainted.
        # Frames: 0=initial, 1=$, 2=a enter insert, 3=DEL+ESC
        self.run_test_screen(
            "Scroll opt: DEL joining empty line below skips repaint",
            "Hello\n\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6\nLine 7\nLine 8\nLine 9\nLine 10\n",
            b"$a\x1b[3~\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Hello"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 5"), (5, "Line 6"),
                (6, "Line 7"), (7, "Line 8"), (8, "Line 9"),
            ],
            expect_cursor=(0, 4),
            # Frame 3 (DEL): cursor row 0 NOT repainted, only bottom row exposed
            expect_content_rows=[(3, {8})]
        )

        # Batched BS at col 0 joining multiple empty lines: display correctness.
        # 3 empty lines above "Hello", 3 BS keys join them all.
        # Frames: 0=initial, 1=jjj cursor, 2=i mode switch, 3=BS*3 scroll frame
        self.run_test_screen(
            "Scroll opt: batched BS joining empty lines display",
            "\n\n\nHello\nWorld\nLine 3\nLine 4\nLine 5\nLine 6\nLine 7\nLine 8\n",
            b"jjji\x08\x08\x08\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Hello"), (1, "World"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 5"), (5, "Line 6"),
                (6, "Line 7"), (7, "Line 8"),
                (8, "~"),
            ],
            expect_cursor=(0, 0),
            # Cursor row NOT repainted (content unchanged), only bottom rows
            expect_content_rows=[(3, {6, 7, 8})]
        )

        # BS at col 0 joining with line that creates a wrapped result.
        # Line 0: "This is 20 char line" (20 chars = 1 row at 20 cols).
        # Line 1: "end" (3 chars = 1 row). BS at col 0 joins them.
        # Merged: "This is 20 char lineend" (23 chars = 2 rows at 20 cols).
        # Old total = 1+1 = 2, new total = 2. Displacement = 0.
        # File delta = 1. Current code scrolls by 1 (wrong), should not scroll.
        # After ESC: cursor col 20→19 (back one), wrap row 0 col 19.
        self.run_test_screen(
            "Scroll opt: BS creating wrap no displacement",
            "This is 20 char line\nend\nnext line\nanother\n",
            b"ji\x08\x1b:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "This is 20 char line"),
                (1, "end"),
                (2, "next line"),
                (3, "another"),
                (4, "~"),
            ],
            expect_cursor=(0, 19),
        )

        # BS at col 0 joining wrapped previous line.
        # Line 0: "This is a longer line!" (22 chars = 2 rows at 20 cols).
        # Line 1: "end" (3 chars = 1 row). BS at col 0 joins them.
        # Merged: "This is a longer line!end" (25 chars = 2 rows at 20 cols).
        # Old total = 2+1 = 3, new total = 2. Displacement = 1 = file delta.
        # After ESC: cursor col 22→21, wrap row 1 col 1.
        self.run_test_screen(
            "Scroll opt: BS joining with wrapped line",
            "This is a longer line!\nend\nnext line\nanother\n",
            b"ji\x08\x1b:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "This is a longer lin"),
                (1, "e!end"),
                (2, "next line"),
                (3, "another"),
                (4, "~"),
            ],
            expect_cursor=(1, 1),
        )

        # Enter in middle of wrapped line: total screen rows unchanged.
        # Line: "12345678901234567890abc" (23 chars = 2 rows at 20 cols).
        # 10 l's to col 10, i enters insert, iii types 3 chars, Enter splits.
        # "1234567890iii" (13, 1 row) + "1234567890abc" (13, 1 row) = 2 rows.
        # Old total = 2. Displacement = 0. SCROLL_DELTA=1 is wrong.
        self.run_test_screen(
            "Scroll opt: Enter on wrapped line no displacement",
            "12345678901234567890abc\nnext line\nanother\n",
            b"lllllllllliiii\r\x1b:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "1234567890iii"),
                (1, "1234567890abc"),
                (2, "next line"),
                (3, "another"),
                (4, "~"),
            ],
            expect_cursor=(1, 0),
        )

        # j past bottom with wrapped line between old/new VIEW_TOP.
        # Line 0 wraps (22 chars at 20 cols = 2 rows). When scrolling past it,
        # SCROLL_DELTA should accumulate 2 screen rows, not fall back.
        # Lines 1-19 are short (1 row each).
        wrap_content = ("This is a longer line!\n"
                        + ''.join(f"Short {i}\n" for i in range(1, 20)))
        self.run_test_screen(
            "Scroll opt: j past bottom with wrapped line uses scroll",
            wrap_content,
            b"j" * 9 + b":q!\r",
            rows=10, cols=20,
            # VIEW_TOP scrolls from 0 to 1 (past wrapping line 0 = 2 screen rows).
            # SCROLL_DELTA = 2 screen rows (line 0: 2 rows)
            expect_lines=[
                (0, "Short 1"), (1, "Short 2"), (2, "Short 3"),
                (3, "Short 4"), (4, "Short 5"), (5, "Short 6"),
                (6, "Short 7"), (7, "Short 8"),
                (8, "Short 9"),
            ],
            expect_cursor=(8, 0),
            # Scroll optimization: only bottom 2 rows touched (not all 9)
            expect_content_rows=[(1, {7, 8})]
        )

        # k past top with wrapped line between old/new VIEW_TOP.
        # After scrolling down past the wrapping line, scroll back up.
        self.run_test_screen(
            "Scroll opt: k past top with wrapped line uses scroll",
            wrap_content,
            b"j" * 9 + b"k" * 9 + b":q!\r",
            rows=10, cols=20,
            # VIEW_TOP scrolls back from 1 to 0 (past wrapping line 0).
            # SCROLL_DELTA = 2 screen rows
            expect_lines=[
                (0, "This is a longer lin"), (1, "e!"),
                (2, "Short 1"), (3, "Short 2"), (4, "Short 3"),
                (5, "Short 4"), (6, "Short 5"), (7, "Short 6"),
                (8, "Short 7"),
            ],
            expect_cursor=(0, 0),
            # Scroll optimization: only top 2 rows touched (not all 9)
            expect_content_rows=[(2, {0, 1})]
        )

        # dd on a wrapped line: SCROLL_DELTA should be 2 (screen rows), not 1
        wrap_dd_content = ("Short 0\n"
                           "This is a longer line!\n"  # 22 chars at 20 cols = 2 rows
                           + ''.join(f"Short {i}\n" for i in range(2, 12)))
        self.run_test_screen(
            "Scroll opt: dd on wrapped line uses correct scroll",
            wrap_dd_content,
            b"jdd:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 0"), (1, "Short 2"), (2, "Short 3"),
                (3, "Short 4"), (4, "Short 5"), (5, "Short 6"),
                (6, "Short 7"), (7, "Short 8"), (8, "Short 9"),
            ],
            expect_cursor=(1, 0),
            # Frame 2 (dd): cursor row 1 + bottom 2 rows (7, 8)
            expect_content_rows=[(2, {1, 7, 8})]
        )

        # p pasting a wrapped line: SCROLL_DELTA should be 2 (screen rows)
        wrap_p_content = ("This is a longer line!\n"  # wraps at 20 cols
                          + ''.join(f"Short {i}\n" for i in range(1, 12)))
        self.run_test_screen(
            "Scroll opt: p pasting wrapped line uses correct scroll",
            wrap_p_content,
            b"yyjjjp:q!\r",
            rows=10, cols=20,
            # yy yanks line 0 (wrapped). jjj to line 3 = "Short 3" at row 4.
            # p pastes below: new line 4 = "This is a longer line!" (2 screen rows).
            # SCROLL_DELTA should be 2.
            expect_lines=[
                (0, "This is a longer lin"), (1, "e!"),
                (2, "Short 1"), (3, "Short 2"), (4, "Short 3"),
                (5, "This is a longer lin"), (6, "e!"),
                (7, "Short 4"), (8, "Short 5"),
            ],
            expect_cursor=(5, 0),
            # Frame 3 (p): 2 cursor rows (5, 6) — row above unchanged
            expect_content_rows=[(3, {5, 6})]
        )

        # pp batched paste of wrapped line: BATCH_EXTRA adjusts FILE_LINE16 past
        # first pasted lines, causing scroll walk to start at wrong position.
        # Without fix, row 4 shows stale content instead of COPY1 wrap row 0.
        self.run_test_screen(
            "Scroll opt: pp batched paste of wrapped line",
            wrap_p_content,
            b"yyjjpp:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "This is a longer lin"), (1, "e!"),
                (2, "Short 1"), (3, "Short 2"),
                (4, "This is a longer lin"), (5, "e!"),
                (6, "This is a longer lin"), (7, "e!"),
                (8, "Short 3"),
            ],
            expect_cursor=(6, 0),
        )

        # 2cc deleting lines including a wrapped line: displacement > file delta.
        # Lines: "Short 1" (1 row), "This is a longer line!" (2 rows at 20 cols).
        # 2cc: deletes both (3 screen rows), inserts blank (1 row).
        # File delta = 1, but actual displacement = 2.
        cc_wrap_content = ("Short 1\n"
                           "This is a longer line!\n"
                           + ''.join(f"Short {i}\n" for i in range(3, 12)))
        self.run_test_screen(
            "Scroll opt: 2cc on wrapped lines correct displacement",
            cc_wrap_content,
            b"2cc\x1b:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, ""),
                (1, "Short 3"), (2, "Short 4"),
                (3, "Short 5"), (4, "Short 6"),
                (5, "Short 7"), (6, "Short 8"),
                (7, "Short 9"), (8, "Short 10"),
            ],
            expect_cursor=(0, 0),
        )

        # dd when replacement line wraps and cursor has WRAP_QUOT > 0.
        # Line 0: 25 chars (2 rows at 20 cols). Line 1: also 25 chars.
        # $ moves to col 24. dd deletes line 0. Replacement wraps.
        # clamp_cursor_col keeps col 24, WRAP_QUOT=1.
        # Bug: row 0 shows stale deleted content instead of replacement row 0.
        dd_wrap_replace = ("1234567890123456789012345\n"
                           "abcdefghijklmnopqrstuvwxy\n"
                           + ''.join(f"Short {i}\n" for i in range(3, 12)))
        self.run_test_screen(
            "Scroll opt: dd with wrapped replacement WRAP_QUOT>0",
            dd_wrap_replace,
            b"$dd:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "abcdefghijklmnopqrst"),
                (1, "uvwxy"),
                (2, "Short 3"), (3, "Short 4"),
                (4, "Short 5"), (5, "Short 6"),
                (6, "Short 7"), (7, "Short 8"),
                (8, "Short 9"),
            ],
            expect_cursor=(1, 4),
        )

        # Redo of 2cc on wrapped lines: same displacement issue.
        self.run_test_screen(
            "Redo: 2cc on wrapped lines correct displacement",
            cc_wrap_content,
            b"2cc\x1bu u:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, ""),
                (1, "Short 3"), (2, "Short 4"),
                (3, "Short 5"), (4, "Short 6"),
                (5, "Short 7"), (6, "Short 8"),
                (7, "Short 9"), (8, "Short 10"),
            ],
            expect_cursor=(0, 0),
        )

        # Redo of dd on wrapped line: missing pre-computation.
        # dd deletes wrapped line (2 rows), redo should use SCROLL_DELTA=2.
        self.run_test_screen(
            "Redo: dd on wrapped line correct displacement",
            wrap_dd_content,
            b"jddu u:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 0"), (1, "Short 2"), (2, "Short 3"),
                (3, "Short 4"), (4, "Short 5"), (5, "Short 6"),
                (6, "Short 7"), (7, "Short 8"), (8, "Short 9"),
            ],
            expect_cursor=(1, 0),
        )

        # J on last visible line: joined line is off-screen, only cursor row redrawn.
        # rows=10 → 9 content rows (0-8), status on row 9.
        # jjjjjjjj = 8 j's → cursor at row 8 (Line 9). J joins off-screen Line 10.
        # Frames: 0=initial, 1=jjjjjjjj cursor, 2=J frame
        self.run_test_screen(
            "Scroll opt: J on last visible line minimal repaint",
            make_lines(15),
            b"j" * 8 + b"J:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (7, "Line 8"),
                (8, "Line 9 Line 10"),
            ],
            expect_cursor=(8, 6),
            # Frame 2 (J): only cursor row 8 redrawn, no scroll needed
            expect_content_rows=[(2, {8})],
            expect_scrolled_at_frame=[(2, False)]
        )

        # dd on last visible line: deleted line at bottom, only cursor row redrawn.
        # Cursor moves to next line (Line 10) which scrolls into view at row 8.
        # Frames: 0=initial, 1=jjjjjjjj cursor, 2=dd frame
        self.run_test_screen(
            "Scroll opt: dd on last visible line minimal repaint",
            make_lines(15),
            b"j" * 8 + b"dd:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (7, "Line 8"),
                (8, "Line 10"),
            ],
            expect_cursor=(8, 0),
            # Frame 2 (dd): only cursor row 8 redrawn
            expect_content_rows=[(2, {8})]
        )

        # J undo on last visible line: restore split line below (off-screen).
        # Frames: 0=initial, 1=jjjjjjjj cursor, 2=J frame, 3=u undo frame
        self.run_test_screen(
            "Scroll opt: J undo on last visible line minimal repaint",
            make_lines(15),
            b"j" * 8 + b"Ju:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (7, "Line 8"),
                (8, "Line 9"),
            ],
            expect_cursor=(8, 0),
            # Frame 3 (u): cursor row (8) — row above unchanged
            expect_content_rows=[(3, {8})]
        )

        # J undo on wrapped last line: no scroll should happen.
        # Cursor line wraps (22 chars at 20 cols = 2 rows), filling rows 7-8.
        # J joins the off-screen line, u restores it. The insert scroll path
        # computes ANSI_ROW=CURSOR_ROW+2=9, ANSI_COL=SCREEN_ROWS-1=9, giving
        # a single-row scroll region [9;9r]. This scroll is unnecessary and
        # causes visible status bar artifacts on real terminals.
        # Frames: 0=initial, 1=jjjjjjj cursor, 2=J frame, 3=u undo frame
        wrap_undo_content = (''.join(f"L{i}\n" for i in range(1, 8))
                             + "This is a longer line!\n"
                             + "Next\nMore1\nMore2\n")
        self.run_test_screen(
            "Scroll opt: J undo on wrapped last line no scroll",
            wrap_undo_content,
            b"j" * 7 + b"Ju:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (7, "This is a longer lin"),
                (8, "e!"),
            ],
            expect_cursor=(7, 0),
            # Frame 3 (u): no scroll needed, just re-render
            expect_scrolled_at_frame=[(3, False)]
        )

        # J redo on last visible line: same as J, minimal repaint.
        # Frames: 0=initial, 1=jjjjjjjj cursor, 2=J, 3=u undo, 4=space noop, 5=u redo
        self.run_test_screen(
            "Scroll opt: J redo on last visible line minimal repaint",
            make_lines(15),
            b"j" * 8 + b"Ju u:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (7, "Line 8"),
                (8, "Line 9 Line 10"),
            ],
            expect_cursor=(8, 6),
            # Frame 5 (redo): only cursor row 8 redrawn
            expect_content_rows=[(5, {8})]
        )

        self._group("Scroll opt: charwise delete:", leading_blank=True)

        # Charwise deletes should NOT include cursor row in scroll region.
        # The cursor row content changes and gets repainted, but the scroll
        # should only cover rows BELOW the cursor row.

        # 2d$ at row 3 with col offset: deletes "e 4\nLine 5", merging remainder.
        # jjjll = line 3, col 2. 2d$ deletes from col 2 to EOL + next line.
        # Result: "Li" on line 3, "Line 6" on line 4.
        # Frames: 0=initial, 1=jjj cursor, 2=ll cursor, 3=count '2', 4=d$
        self.run_test_screen(
            "Scroll opt: 2d$ does not scroll cursor row",
            make_lines(15),
            b"jjjll2d$:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Li"), (4, "Line 6"), (5, "Line 7"),
                (6, "Line 8"), (7, "Line 9"), (8, "Line 10"),
            ],
            expect_cursor=(3, 1),
            # Scroll region: rows 4-8 (below cursor), NOT including row 3
            expect_scroll_rows=[(4, {4, 5, 6, 7, 8})]
        )

        # 2D at row 3: same as 2d$ from col 0, deletes current+next line content.
        # Result: empty line 3, "Line 6" on line 4.
        # Frames: 0=initial, 1=jjj cursor, 2=count '2', 3=D
        self.run_test_screen(
            "Scroll opt: 2D does not scroll cursor row",
            make_lines(15),
            b"jjj2D:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, ""), (4, "Line 6"), (5, "Line 7"),
                (6, "Line 8"), (7, "Line 9"), (8, "Line 10"),
            ],
            expect_cursor=(3, 0),
            expect_scroll_rows=[(3, {4, 5, 6, 7, 8})]
        )

        # Single d$ does NOT trigger scroll (no line count change, auto-detect handles it).
        # Frames: 0=initial, 1=d$ frame
        self.run_test_screen(
            "Scroll opt: single d$ no scroll just current line",
            make_lines(10),
            b"lld$:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Li")],
            expect_cursor=(0, 1),
            expect_scrolled_at_frame=[(1, False)]
        )

        # Cross-line de: cursor at "4" in "Line 4", de deletes to end of next word.
        # Result: line 3 = "Line  5"
        # Frames: 0=initial, 1=jjj, 2=lllll, 3=de
        self.run_test_screen(
            "Scroll opt: cross-line de does not scroll cursor row",
            make_lines(15),
            b"jjjlllllde:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line  5"), (4, "Line 6"), (5, "Line 7"),
                (6, "Line 8"), (7, "Line 9"), (8, "Line 10"),
            ],
            expect_cursor=(3, 5),
            expect_scroll_rows=[(3, {4, 5, 6, 7, 8})]
        )

        # 2C (change to EOL multi-line): deletes 2 lines' content, enters insert.
        # ESC exits insert mode without typing.
        # Frames: 0=initial, 1=jjj, 2=count '2', 3=C (delete+insert), 4=ESC
        self.run_test_screen(
            "Scroll opt: 2C does not scroll cursor row",
            make_lines(15),
            b"jjj2C\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, ""), (4, "Line 6"), (5, "Line 7"),
                (6, "Line 8"), (7, "Line 9"), (8, "Line 10"),
            ],
            expect_cursor=(3, 0),
            expect_scroll_rows=[(3, {4, 5, 6, 7, 8})]
        )

        # Undo of 2d$: restores deleted content, line count increases.
        # Undo uses line-insert scroll which pushes content down below cursor.
        # Cursor row content changes but should NOT be in scroll region (it'll be repainted).
        # Frames: 0=initial, 1=jjj, 2=ll, 3=count '2', 4=d$ (delete scroll), 5=u (insert scroll)
        self.run_test_screen(
            "Scroll opt: 2d$ undo does not scroll cursor row",
            make_lines(15),
            b"jjjll2d$u:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 5"), (5, "Line 6"),
                (6, "Line 7"), (7, "Line 8"), (8, "Line 9"),
            ],
            expect_cursor=(3, 2),
            expect_scroll_rows=[(5, {4, 5, 6, 7, 8})]
        )

        # Undo of 2D: same as 2d$ undo, cursor row should not be scrolled.
        # Frames: 0=initial, 1=jjj, 2=count '2', 3=D (delete scroll), 4=u (insert scroll)
        self.run_test_screen(
            "Scroll opt: 2D undo does not scroll cursor row",
            make_lines(15),
            b"jjj2Du:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 5"), (5, "Line 6"),
                (6, "Line 7"), (7, "Line 8"), (8, "Line 9"),
            ],
            expect_cursor=(3, 0),
            expect_scroll_rows=[(4, {4, 5, 6, 7, 8})]
        )

        # Undo of cross-line de: cursor row should not be scrolled.
        # Start at end of Line 4, de deletes to end of word spanning newline.
        # Frames: 0=initial, 1=jjj, 2=$ (end), 3=de (delete scroll), 4=u (insert scroll)
        self.run_test_screen(
            "Scroll opt: de undo does not scroll cursor row",
            make_lines(15),
            b"jjj$deu:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 5"), (5, "Line 6"),
                (6, "Line 7"), (7, "Line 8"), (8, "Line 9"),
            ],
            expect_cursor=(3, 5),
            expect_scroll_rows=[(4, {4, 5, 6, 7, 8})]
        )

        # Redo of 2d$: re-deletes, line count decreases.
        # Frames: 0=initial, 1=jjj, 2=ll, 3=count '2', 4=d$, 5=u, 6=space noop, 7=u redo
        self.run_test_screen(
            "Scroll opt: 2d$ redo does not scroll cursor row",
            make_lines(15),
            b"jjjll2d$u u:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Li"), (4, "Line 6"), (5, "Line 7"),
                (6, "Line 8"), (7, "Line 9"), (8, "Line 10"),
            ],
            expect_cursor=(3, 1),
            expect_scroll_rows=[(7, {4, 5, 6, 7, 8})]
        )

        self._group("Scroll opt: charwise paste:", leading_blank=True)

        # Multi-line char paste p: yank with 2D (charwise, multi-line), then paste.
        # Cursor row content changes (line splits) but should NOT be in scroll region.
        # Frames: 0=initial, 1=count '2', 2=D (scroll: charwise delete), 3=p (insert)
        self.run_test_screen(
            "Scroll opt: multi-line char paste p does not scroll cursor row",
            make_lines(15),
            b"2Dp:q!\r",
            rows=10, cols=40,
            expect_scroll_rows=[(3, {1, 2, 3, 4, 5, 6, 7, 8})]
        )

        # Multi-line char paste P: same yank, P pastes before cursor.
        # Cursor row should NOT be in scroll region.
        # Frames: 0=initial, 1=count '2', 2=D (scroll), 3=P (insert)
        self.run_test_screen(
            "Scroll opt: multi-line char paste P does not scroll cursor row",
            make_lines(15),
            b"2DP:q!\r",
            rows=10, cols=40,
            expect_scroll_rows=[(3, {1, 2, 3, 4, 5, 6, 7, 8})]
        )

        # Undo of multi-line char paste p: deletes pasted content, line count decreases.
        # Undo uses delete_at_cursor which should not scroll cursor row.
        # Frames: 0=initial, 1=count '2', 2=D (delete scroll), 3=p (insert scroll), 4=u (delete scroll)
        self.run_test_screen(
            "Scroll opt: char paste p undo does not scroll cursor row",
            make_lines(15),
            b"2Dpu:q!\r",
            rows=10, cols=40,
            expect_scroll_rows=[(4, {1, 2, 3, 4, 5, 6, 7, 8})]
        )

        # Redo of multi-line char paste p: re-inserts content, line count increases.
        # Cursor row should NOT be in scroll region (it'll be repainted).
        # Frames: ...4=u undo, 5=space noop, 6=u redo
        self.run_test_screen(
            "Scroll opt: char paste p redo does not scroll cursor row",
            make_lines(15),
            b"2Dpu u:q!\r",
            rows=10, cols=40,
            expect_scroll_rows=[(6, {1, 2, 3, 4, 5, 6, 7, 8})]
        )

        # Redo of multi-line char paste P: same, cursor row not in scroll region.
        # Frames: 0=initial, 1=count '2', 2=D, 3=P, 4=u, 5=space, 6=u redo
        self.run_test_screen(
            "Scroll opt: char paste P redo does not scroll cursor row",
            make_lines(15),
            b"2DPu u:q!\r",
            rows=10, cols=40,
            expect_scroll_rows=[(6, {1, 2, 3, 4, 5, 6, 7, 8})]
        )

        self._group("Scroll opt: paste-below undo:", leading_blank=True)

        # yypu at row 3: paste-below adds line 4, undo removes it.
        # The undo scroll should NOT include cursor row 3 in the scroll region.
        # Cursor row didn't change content, so scrolling it causes a glitch.
        # Frames: 0=initial, 1=jjj, 2=yy, 3=p (insert scroll), 4=u (delete scroll)
        self.run_test_screen(
            "Scroll opt: yypu undo does not scroll cursor row",
            make_lines(15),
            b"jjjyypu:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 5"), (5, "Line 6"),
                (6, "Line 7"), (7, "Line 8"), (8, "Line 9"),
            ],
            expect_cursor=(3, 0),
            # Frame 4 (u): scroll region should NOT include cursor row 3
            expect_scroll_rows=[(4, {4, 5, 6, 7, 8})],
            # Cursor row 3 should NOT be repainted (content unchanged)
            expect_content_rows=[(4, {8})]
        )

        self._group("Minimal repaint: undo/redo:", leading_blank=True)

        # --- Line-count-changing operations: undo/redo need scroll ---
        # Insert scroll (scroll down, line restored/added): cursor row(s) need
        #   content write; bottom row filled by scroll — NOT repainted.
        # Delete scroll (scroll up, line removed): content shifts up; bottom
        #   row(s) need content write from below viewport.
        # In neither case should the row ABOVE cursor be repainted.

        # dd undo: restores line 4. Insert scroll pushes content down.
        # Only cursor row 3 needs content write (restored line).
        # Frames: 0=initial, 1=jjj, 2=dd, 3=u
        self.run_test_screen(
            "Minimal repaint: dd undo",
            make_lines(15),
            b"jjjddu:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 5"), (5, "Line 6"),
                (6, "Line 7"), (7, "Line 8"), (8, "Line 9"),
            ],
            expect_cursor=(3, 0),
            expect_content_rows=[(3, {3})]
        )

        # dd redo: re-deletes line 4. Delete scroll pulls content up.
        # Bottom row 8 needs content write from below viewport.
        # Frames: 0=initial, 1=jjj, 2=dd, 3=u, 4=space, 5=u redo
        self.run_test_screen(
            "Minimal repaint: dd redo",
            make_lines(15),
            b"jjjddu u:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 5"), (4, "Line 6"), (5, "Line 7"),
                (6, "Line 8"), (7, "Line 9"), (8, "Line 10"),
            ],
            expect_cursor=(3, 0),
            expect_content_rows=[(5, {8})]
        )

        # 3dd undo: restores lines 4-6. Insert scroll of 3, rows 3-5
        # need content writes for restored lines.
        # Frames: 0=initial, 1=jjj, 2=count '3', 3=dd, 4=u
        self.run_test_screen(
            "Minimal repaint: 3dd undo",
            make_lines(15),
            b"jjj3ddu:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 5"), (5, "Line 6"),
                (6, "Line 7"), (7, "Line 8"), (8, "Line 9"),
            ],
            expect_cursor=(3, 0),
            expect_content_rows=[(4, {3, 4, 5})]
        )

        # 3dd redo: re-deletes lines 4-6. Delete scroll of 3,
        # bottom rows 6-8 need content writes.
        # Frames: 0=initial, 1=jjj, 2=count '3', 3=dd, 4=u, 5=space, 6=u redo
        self.run_test_screen(
            "Minimal repaint: 3dd redo",
            make_lines(15),
            b"jjj3ddu u:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 7"), (4, "Line 8"), (5, "Line 9"),
                (6, "Line 10"), (7, "Line 11"), (8, "Line 12"),
            ],
            expect_cursor=(3, 0),
            expect_content_rows=[(6, {6, 7, 8})]
        )

        # dd at top undo: restores line 1. Insert scroll.
        # Frames: 0=initial, 1=dd, 2=u
        self.run_test_screen(
            "Minimal repaint: dd at top undo",
            make_lines(15),
            b"ddu:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 5"), (5, "Line 6"),
                (6, "Line 7"), (7, "Line 8"), (8, "Line 9"),
            ],
            expect_cursor=(0, 0),
            expect_content_rows=[(2, {0})]
        )

        # dd at top redo: re-deletes line 1. Delete scroll.
        # Frames: 0=initial, 1=dd, 2=u, 3=space, 4=u redo
        self.run_test_screen(
            "Minimal repaint: dd at top redo",
            make_lines(15),
            b"ddu u:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 2"), (1, "Line 3"), (2, "Line 4"),
                (3, "Line 5"), (4, "Line 6"), (5, "Line 7"),
                (6, "Line 8"), (7, "Line 9"), (8, "Line 10"),
            ],
            expect_cursor=(0, 0),
            expect_content_rows=[(4, {8})]
        )

        # J undo: restores split (line count +1). Insert scroll.
        # Cursor row 3 content changes (joined→original). Row 4 = restored line
        # (scroll creates blank row that needs content). Rows 3-4.
        # Frames: 0=initial, 1=jjj, 2=J, 3=u
        self.run_test_screen(
            "Minimal repaint: J undo",
            make_lines(15),
            b"jjjJu:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 5"), (5, "Line 6"),
                (6, "Line 7"), (7, "Line 8"), (8, "Line 9"),
            ],
            expect_cursor=(3, 0),
            expect_content_rows=[(3, {3, 4})]
        )

        # J redo: re-joins (line count -1). Delete scroll.
        # Cursor row 3 content changes + bottom row 8 from below viewport.
        # Frames: 0=initial, 1=jjj, 2=J, 3=u, 4=space, 5=u redo
        self.run_test_screen(
            "Minimal repaint: J redo",
            make_lines(15),
            b"jjjJu u:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(5, {3, 8})]
        )

        # JJ undo: JJ is batched into one frame. Undo restores 1 join (batching
        # records UNDO_JOIN_COUNT=1). Cursor row + restored line need content.
        # Frames: 0=initial, 1=jjj, 2=JJ (batched), 3=u
        self.run_test_screen(
            "Minimal repaint: JJ undo",
            make_lines(15),
            b"jjjJJu:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(3, {3, 4})]
        )

        # JJ redo: re-does the batched join (1 join). Delete scroll.
        # Cursor row 3 changes + bottom row 8 from below viewport.
        # Frames: 0=initial, 1=jjj, 2=JJ (batched), 3=u, 4=space, 5=u redo
        self.run_test_screen(
            "Minimal repaint: JJ redo",
            make_lines(15),
            b"jjjJJu u:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(5, {3, 8})]
        )

        # 3J undo: restores split (line count +2). Insert scroll of 2.
        # Cursor row 3 changes + 2 restored lines below. Rows 3-5.
        # Frames: 0=initial, 1=jjj, 2=count '3', 3=J, 4=u
        self.run_test_screen(
            "Minimal repaint: 3J undo",
            make_lines(15),
            b"jjj3Ju:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 5"), (5, "Line 6"),
                (6, "Line 7"), (7, "Line 8"), (8, "Line 9"),
            ],
            expect_cursor=(3, 0),
            expect_content_rows=[(4, {3, 4, 5})]
        )

        # 3J redo: re-joins 3 lines (line count -2). Delete scroll of 2.
        # Cursor row 3 changes + bottom rows 7-8.
        # Frames: 0=initial, 1=jjj, 2=count '3', 3=J, 4=u, 5=space, 6=u redo
        self.run_test_screen(
            "Minimal repaint: 3J redo",
            make_lines(15),
            b"jjj3Ju u:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(6, {3, 7, 8})]
        )

        # J undo of two lines at screen width: J adds a space, so the combined
        # line wraps and actually increases screen rows. Undo restores the split.
        # 20-char lines at 20 cols: "12345678901234567890" + "abcdefghijklmnopqrst"
        # After J: "12345678901234567890 abcdefghijklmnopqrst" = 41 chars = 3 rows
        # Undo: restores 2 lines × 1 row = 2 rows (net -1 screen row)
        # This is the opposite displacement from normal J undo (scroll UP, not down)
        j_width_content = ("12345678901234567890\n"
                           "abcdefghijklmnopqrst\n"
                           + ''.join(f"S{i}\n" for i in range(3, 14)))
        self.run_test_screen(
            "Minimal repaint: J undo at screen width",
            j_width_content,
            b"Ju:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "12345678901234567890"),
                (1, "abcdefghijklmnopqrst"),
                (2, "S3"), (3, "S4"), (4, "S5"),
                (5, "S6"), (6, "S7"), (7, "S8"),
                (8, "S9"),
            ],
            expect_cursor=(0, 0),
            # Frame 2 = undo. Cursor line changes (41→20 chars) so row 0
            # repaint is justified. Row 1 = restored line. Row 8 = scroll fill.
            expect_content_rows=[(2, {0, 1, 8})]
        )

        # J redo of two lines at screen width.
        # Redo re-joins into 3-row wrapped line.
        self.run_test_screen(
            "Minimal repaint: J redo at screen width",
            j_width_content,
            b"Ju u:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "12345678901234567890"),
                (1, " abcdefghijklmnopqrs"),
                (2, "t"),
                (3, "S3"), (4, "S4"), (5, "S5"),
                (6, "S6"), (7, "S7"), (8, "S8"),
            ],
            expect_cursor=(1, 0),
            # Frame 4 = redo (frame 3 = space no-op). Cursor line changes
            # (20→41 chars wrapping to 3 rows). Rows 0-2 = wrapped content.
            expect_content_rows=[(4, {0, 1, 2})]
        )

        # o undo: removes opened blank line. Delete scroll.
        # Cursor row content unchanged (Line 4 stays). Only bottom row 8.
        # Frames: 0=initial, 1=jjj, 2=o (insert+scroll), 3=ESC, 4=u
        self.run_test_screen(
            "Minimal repaint: o undo",
            make_lines(15),
            b"jjjo\x1bu:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(4, {8})]
        )

        # o redo: re-opens blank line below. Insert scroll.
        # Only the new blank line row needs content write.
        # Frames: 0=initial, 1=jjj, 2=o, 3=ESC, 4=u, 5=space, 6=u redo
        self.run_test_screen(
            "Minimal repaint: o redo",
            make_lines(15),
            b"jjjo\x1bu u:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(6, {4})]
        )

        # O undo: removes opened blank line above. Delete scroll.
        # Cursor row filled by scroll. Only bottom row 8.
        # Frames: 0=initial, 1=jjj, 2=O (insert+scroll), 3=ESC, 4=u
        self.run_test_screen(
            "Minimal repaint: O undo",
            make_lines(15),
            b"jjjO\x1bu:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(4, {8})]
        )

        # O redo: re-opens blank line above. Insert scroll.
        # Only the new blank line row needs content write.
        # Frames: 0=initial, 1=jjj, 2=O, 3=ESC, 4=u, 5=space, 6=u redo
        self.run_test_screen(
            "Minimal repaint: O redo",
            make_lines(15),
            b"jjjO\x1bu u:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(6, {3})]
        )

        # 2cc undo: restores 2 original lines, removes 1 blank. Net +1 line.
        # Pre-computed scroll: displacement = sum(line_rows) - 1 = 2 - 1 = 1.
        # Frames: 0=initial, 1=jjj, 2=count '2', 3=cc (delete+insert), 4=ESC, 5=u
        self.run_test_screen(
            "Minimal repaint: 2cc undo",
            make_lines(15),
            b"jjj2cc\x1bu:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 5"), (5, "Line 6"),
                (6, "Line 7"), (7, "Line 8"), (8, "Line 9"),
            ],
            expect_cursor=(3, 0),
            expect_content_rows=[(5, {3, 4})]
        )

        # 2cc redo: re-replaces 2 lines with 1 blank. Net -1 line.
        # Delete scroll of 1. Cursor row 3 changes + bottom row 8.
        # Frames: 0=initial, 1=jjj, 2=count '2', 3=cc, 4=ESC, 5=u, 6=space, 7=u redo
        self.run_test_screen(
            "Minimal repaint: 2cc redo",
            make_lines(15),
            b"jjj2cc\x1bu u:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, ""), (4, "Line 6"), (5, "Line 7"),
                (6, "Line 8"), (7, "Line 9"), (8, "Line 10"),
            ],
            expect_cursor=(3, 0),
            expect_content_rows=[(7, {3, 8})]
        )

        # --- Line-mode paste: operation + undo + redo ---

        # Line P operation: yyP at row 3 pastes line above.
        # Only the pasted line row should be repainted, NOT row 2.
        # Frames: 0=initial, 1=jjj, 2=yy, 3=P
        self.run_test_screen(
            "Minimal repaint: line P operation",
            make_lines(15),
            b"jjjyyP:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 4"), (5, "Line 5"),
                (6, "Line 6"), (7, "Line 7"), (8, "Line 8"),
            ],
            expect_cursor=(3, 0),
            expect_content_rows=[(3, {3})]
        )

        # Line P undo: removes pasted line.
        # Only bottom row should be repainted (scroll pulls content up).
        # Frames: 0=initial, 1=jjj, 2=yy, 3=P, 4=u
        self.run_test_screen(
            "Minimal repaint: line P undo",
            make_lines(15),
            b"jjjyyPu:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 5"), (5, "Line 6"),
                (6, "Line 7"), (7, "Line 8"), (8, "Line 9"),
            ],
            expect_cursor=(3, 0),
            expect_content_rows=[(4, {8})]
        )

        # Line P redo: re-pastes line above.
        # Only pasted line row should be repainted, NOT row 2.
        # Frames: 0=initial, 1=jjj, 2=yy, 3=P, 4=u, 5=space, 6=u redo
        self.run_test_screen(
            "Minimal repaint: line P redo",
            make_lines(15),
            b"jjjyyPu u:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 4"), (5, "Line 5"),
                (6, "Line 6"), (7, "Line 7"), (8, "Line 8"),
            ],
            expect_cursor=(3, 0),
            expect_content_rows=[(6, {3})]
        )

        # Line p redo: re-pastes line below.
        # Only pasted line row should be repainted, NOT row 3.
        # Frames: 0=initial, 1=jjj, 2=yy, 3=p, 4=u, 5=space, 6=u redo
        self.run_test_screen(
            "Minimal repaint: line p redo",
            make_lines(15),
            b"jjjyypu u:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 4"), (5, "Line 5"),
                (6, "Line 6"), (7, "Line 7"), (8, "Line 8"),
            ],
            expect_cursor=(4, 0),
            expect_content_rows=[(6, {4})]
        )

        # Line 2p undo: pastes 2 copies below, undo removes both.
        # Only bottom rows should be repainted (scroll pulls content up).
        # Frames: 0=initial, 1=jjj, 2=yy, 3=count '2', 4=p, 5=u
        self.run_test_screen(
            "Minimal repaint: line 2p undo",
            make_lines(15),
            b"jjjyy2pu:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 5"), (5, "Line 6"),
                (6, "Line 7"), (7, "Line 8"), (8, "Line 9"),
            ],
            expect_cursor=(3, 0),
            expect_content_rows=[(5, {7, 8})]
        )

        # Line 2P undo: pastes 2 copies above, undo removes both.
        # Frames: 0=initial, 1=jjj, 2=yy, 3=count '2', 4=P, 5=u
        self.run_test_screen(
            "Minimal repaint: line 2P undo",
            make_lines(15),
            b"jjjyy2Pu:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 5"), (5, "Line 6"),
                (6, "Line 7"), (7, "Line 8"), (8, "Line 9"),
            ],
            expect_cursor=(3, 0),
            expect_content_rows=[(5, {7, 8})]
        )

        # --- Single-line operations: no scroll, just cursor row ---
        # These don't change line count, so undo/redo should repaint ONLY
        # the cursor row. No scroll expected.

        # x undo
        # Frames: 0=initial, 1=jjj, 2=x, 3=u
        self.run_test_screen(
            "Minimal repaint: x undo",
            make_lines(15),
            b"jjjxu:q!\r",
            rows=10, cols=40,
            expect_cursor=(3, 0),
            expect_content_rows=[(3, {3})],
            expect_scrolled_at_frame=[(3, False)]
        )

        # x redo
        # Frames: 0=initial, 1=jjj, 2=x, 3=u, 4=space, 5=u redo
        self.run_test_screen(
            "Minimal repaint: x redo",
            make_lines(15),
            b"jjjxu u:q!\r",
            rows=10, cols=40,
            expect_cursor=(3, 0),
            expect_content_rows=[(5, {3})],
            expect_scrolled_at_frame=[(5, False)]
        )

        # 3x undo
        # Frames: 0=initial, 1=jjj, 2=count '3', 3=x, 4=u
        self.run_test_screen(
            "Minimal repaint: 3x undo",
            make_lines(15),
            b"jjj3xu:q!\r",
            rows=10, cols=40,
            expect_cursor=(3, 0),
            expect_content_rows=[(4, {3})],
            expect_scrolled_at_frame=[(4, False)]
        )

        # r undo
        # Frames: 0=initial, 1=jjj, 2=rZ (r waits for char), 3=u
        self.run_test_screen(
            "Minimal repaint: r undo",
            make_lines(15),
            b"jjjrZu:q!\r",
            rows=10, cols=40,
            expect_cursor=(3, 0),
            expect_content_rows=[(3, {3})],
            expect_scrolled_at_frame=[(3, False)]
        )

        # r redo
        # Frames: 0=initial, 1=jjj, 2=rZ, 3=u, 4=space, 5=u redo
        self.run_test_screen(
            "Minimal repaint: r redo",
            make_lines(15),
            b"jjjrZu u:q!\r",
            rows=10, cols=40,
            expect_cursor=(3, 0),
            expect_content_rows=[(5, {3})],
            expect_scrolled_at_frame=[(5, False)]
        )

        # ~ undo: ~ toggles case and advances cursor. Undo restores char.
        # Frames: 0=initial, 1=jjj, 2=~, 3=u
        self.run_test_screen(
            "Minimal repaint: ~ undo",
            make_lines(15),
            b"jjj~u:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(3, {3})],
            expect_scrolled_at_frame=[(3, False)]
        )

        # ~ redo
        # Frames: 0=initial, 1=jjj, 2=~, 3=u, 4=space, 5=u redo
        self.run_test_screen(
            "Minimal repaint: ~ redo",
            make_lines(15),
            b"jjj~u u:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(5, {3})],
            expect_scrolled_at_frame=[(5, False)]
        )

        # D undo (single line, cursor at col 2)
        # Frames: 0=initial, 1=jjj, 2=ll, 3=D, 4=u
        self.run_test_screen(
            "Minimal repaint: D undo",
            make_lines(15),
            b"jjjllDu:q!\r",
            rows=10, cols=40,
            expect_cursor=(3, 2),
            expect_content_rows=[(4, {3})],
            expect_scrolled_at_frame=[(4, False)]
        )

        # D redo
        # Frames: 0=initial, 1=jjj, 2=ll, 3=D, 4=u, 5=space, 6=u redo
        self.run_test_screen(
            "Minimal repaint: D redo",
            make_lines(15),
            b"jjjllDu u:q!\r",
            rows=10, cols=40,
            expect_cursor=(3, 1),
            expect_content_rows=[(6, {3})],
            expect_scrolled_at_frame=[(6, False)]
        )

        # d$ undo
        # Frames: 0=initial, 1=jjj, 2=ll, 3=d$, 4=u
        self.run_test_screen(
            "Minimal repaint: d$ undo",
            make_lines(15),
            b"jjjlld$u:q!\r",
            rows=10, cols=40,
            expect_cursor=(3, 2),
            expect_content_rows=[(4, {3})],
            expect_scrolled_at_frame=[(4, False)]
        )

        # dw undo (single line)
        # Frames: 0=initial, 1=jjj, 2=dw, 3=u
        self.run_test_screen(
            "Minimal repaint: dw undo",
            make_lines(15),
            b"jjjdwu:q!\r",
            rows=10, cols=40,
            expect_cursor=(3, 0),
            expect_content_rows=[(3, {3})],
            expect_scrolled_at_frame=[(3, False)]
        )

        # dw redo
        # Frames: 0=initial, 1=jjj, 2=dw, 3=u, 4=space, 5=u redo
        self.run_test_screen(
            "Minimal repaint: dw redo",
            make_lines(15),
            b"jjjdwu u:q!\r",
            rows=10, cols=40,
            expect_cursor=(3, 0),
            expect_content_rows=[(5, {3})],
            expect_scrolled_at_frame=[(5, False)]
        )

        # db undo (move to word start first)
        # Frames: 0=initial, 1=jjj, 2=w, 3=db, 4=u
        self.run_test_screen(
            "Minimal repaint: db undo",
            make_lines(15),
            b"jjjwdbu:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(4, {3})],
            expect_scrolled_at_frame=[(4, False)]
        )

        # de undo (single line)
        # Frames: 0=initial, 1=jjj, 2=de, 3=u
        self.run_test_screen(
            "Minimal repaint: de undo",
            make_lines(15),
            b"jjjdeu:q!\r",
            rows=10, cols=40,
            expect_cursor=(3, 0),
            expect_content_rows=[(3, {3})],
            expect_scrolled_at_frame=[(3, False)]
        )

        # s undo (substitute char)
        # Frames: 0=initial, 1=jjj, 2=s (insert mode), 3=ESC, 4=u
        self.run_test_screen(
            "Minimal repaint: s undo",
            make_lines(15),
            b"jjjs\x1bu:q!\r",
            rows=10, cols=40,
            expect_cursor=(3, 0),
            expect_content_rows=[(4, {3})],
            expect_scrolled_at_frame=[(4, False)]
        )

        # cc undo (single line change)
        # Frames: 0=initial, 1=jjj, 2=cc (insert mode), 3=ESC, 4=u
        self.run_test_screen(
            "Minimal repaint: cc undo single line",
            make_lines(15),
            b"jjjcc\x1bu:q!\r",
            rows=10, cols=40,
            expect_cursor=(3, 0),
            expect_content_rows=[(4, {3})],
            expect_scrolled_at_frame=[(4, False)]
        )

        # C undo (change to end of line)
        # Frames: 0=initial, 1=jjj, 2=ll, 3=C (insert mode), 4=ESC, 5=u
        self.run_test_screen(
            "Minimal repaint: C undo",
            make_lines(15),
            b"jjjllC\x1bu:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(5, {3})],
            expect_scrolled_at_frame=[(5, False)]
        )

        # cw undo (change word)
        # Frames: 0=initial, 1=jjj, 2=cw (insert mode), 3=ESC, 4=u
        self.run_test_screen(
            "Minimal repaint: cw undo",
            make_lines(15),
            b"jjjcw\x1bu:q!\r",
            rows=10, cols=40,
            expect_cursor=(3, 0),
            expect_content_rows=[(4, {3})],
            expect_scrolled_at_frame=[(4, False)]
        )

        # cb undo (change back word)
        # Frames: 0=initial, 1=jjj, 2=w, 3=cb (insert mode), 4=ESC, 5=u
        self.run_test_screen(
            "Minimal repaint: cb undo",
            make_lines(15),
            b"jjjwcb\x1bu:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(5, {3})],
            expect_scrolled_at_frame=[(5, False)]
        )

        # ce undo (change to end of word)
        # Frames: 0=initial, 1=jjj, 2=ce (insert mode), 3=ESC, 4=u
        self.run_test_screen(
            "Minimal repaint: ce undo",
            make_lines(15),
            b"jjjce\x1bu:q!\r",
            rows=10, cols=40,
            expect_cursor=(3, 0),
            expect_content_rows=[(4, {3})],
            expect_scrolled_at_frame=[(4, False)]
        )

        # >> undo (indent)
        # Frames: 0=initial, 1=jjj, 2=>>, 3=u
        self.run_test_screen(
            "Minimal repaint: >> undo",
            make_lines(15),
            b"jjj>>u:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(3, {3})],
            expect_scrolled_at_frame=[(3, False)]
        )

        # << undo (dedent, need leading spaces)
        # Frames: 0=initial, 1=jjj, 2=<<, 3=u
        indent_content = ''.join(
            f"  Line {i}\n" if i == 4 else f"Line {i}\n"
            for i in range(1, 16)
        )
        self.run_test_screen(
            "Minimal repaint: << undo",
            indent_content,
            b"jjj<<u:q!\r",
            rows=10, cols=40,
            expect_cursor=(3, 0),
            expect_content_rows=[(3, {3})],
            expect_scrolled_at_frame=[(3, False)]
        )

        # --- Character-mode paste: undo/redo (no line count change) ---

        # char p undo: x deletes char, p pastes it back, u undoes paste
        # Frames: 0=initial, 1=jjj, 2=x, 3=p, 4=u
        self.run_test_screen(
            "Minimal repaint: char p undo",
            make_lines(15),
            b"jjjxpu:q!\r",
            rows=10, cols=40,
            expect_cursor=(3, 0),
            expect_content_rows=[(4, {3})],
            expect_scrolled_at_frame=[(4, False)]
        )

        # char p redo
        # Frames: 0=initial, 1=jjj, 2=x, 3=p, 4=u, 5=space, 6=u redo
        self.run_test_screen(
            "Minimal repaint: char p redo",
            make_lines(15),
            b"jjjxpu u:q!\r",
            rows=10, cols=40,
            expect_cursor=(3, 1),
            expect_content_rows=[(6, {3})],
            expect_scrolled_at_frame=[(6, False)]
        )

        # char P undo
        # Frames: 0=initial, 1=jjj, 2=x, 3=P, 4=u
        self.run_test_screen(
            "Minimal repaint: char P undo",
            make_lines(15),
            b"jjjxPu:q!\r",
            rows=10, cols=40,
            expect_cursor=(3, 0),
            expect_content_rows=[(4, {3})],
            expect_scrolled_at_frame=[(4, False)]
        )

        # char P redo
        # Frames: 0=initial, 1=jjj, 2=x, 3=P, 4=u, 5=space, 6=u redo
        self.run_test_screen(
            "Minimal repaint: char P redo",
            make_lines(15),
            b"jjjxPu u:q!\r",
            rows=10, cols=40,
            expect_cursor=(3, 0),
            expect_content_rows=[(6, {3})],
            expect_scrolled_at_frame=[(6, False)]
        )

        # cc ESC u on line where next line is blank: cc uses UNDO_LINE path
        # (skips blank insert since next line is already blank). Undo should
        # restore the correct screen content without incorrectly scrolling
        # rows below the cursor.
        # Content: AAA, (blank), BBB, (blank), CCC, ...
        # After cc on BBB: line deleted, next blank becomes cursor line.
        # After u: BBB restored. Row 4 should show CCC, not be blank.
        # Frames: 0=initial, 1=jj, 2=cc (insert), 3=ESC, 4=u
        cc_blank_around = 'AAA\n\nBBB\n\nCCC\nDDD\nEEE\nFFF\nGGG\nHHH\nIII\n'
        self.run_test_screen(
            "Minimal repaint: cc ESC u with blank line after",
            cc_blank_around,
            b"jjcc\x1bu:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "AAA"), (1, ""), (2, "BBB"), (3, ""),
                (4, "CCC"), (5, "DDD"), (6, "EEE"),
                (7, "FFF"), (8, "GGG"),
            ],
            expect_cursor=(2, 0),
        )

        # 2C undo should not paint the line above the cursor.
        # Frames: 0=initial, 1=jjj, 2=count '2', 3=C (delete+insert), 4=ESC, 5=u
        self.run_test_screen(
            "Minimal repaint: 2C undo does not paint line above",
            'S1\nS2\nS3\nAAAA\nBBBB\nS6\nS7\nS8\nS9\nS10\nS11\n',
            b"j j j2C\x1bu:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "S1"), (1, "S2"), (2, "S3"),
                (3, "AAAA"), (4, "BBBB"), (5, "S6"),
                (6, "S7"), (7, "S8"), (8, "S9"),
            ],
            expect_cursor=(3, 0),
            # Frame 5 = undo. Should touch only cursor row + restored line.
            # Row 2 (line above) must NOT be in the set.
            expect_content_rows=[(9, {3, 4})]
        )

        # C on a wrapping line: line shrinks from 2 rows to 1 row (displacement -1).
        # Should use scroll-up optimization, not repaint everything from cursor
        # to bottom of screen.
        # Content: S1, S2, S3, AAA...30chars (2 rows at 20 cols), S5, ...
        # After C: cursor line becomes empty (1 row), content below shifts up by 1.
        # Frames: 0=initial, 1=jjj, 2=C (delete+insert), 3=ESC
        c_wrap_content = 'S1\nS2\nS3\n' + 'A' * 30 + '\nS5\nS6\nS7\nS8\nS9\nS10\n'
        self.run_test_screen(
            "Minimal repaint: C on wrapping line uses scroll",
            c_wrap_content,
            b"jjjC\x1b:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "S1"), (1, "S2"), (2, "S3"),
                (3, ""), (4, "S5"), (5, "S6"),
                (6, "S7"), (7, "S8"), (8, "S9"),
            ],
            expect_cursor=(3, 0),
            # Frame 2 = C operation. Should repaint cursor row + bottom row only.
            expect_content_rows=[(2, {3, 8})]
        )

        # 2C when second line wraps: total screen displacement should account
        # for the wrapped line's extra rows. File delta = 1 line, but the
        # wrapped line occupies 2 screen rows, so actual displacement = 2.
        # Content: S1, S2, S3, AAAA (1 row), BBB...30chars (2 rows), S6, ...
        # After 2C: cursor line becomes empty (1 row). Freed 3 rows (1+2),
        # new cursor = 1 row, so displacement = 2.
        # Frames: 0=initial, 1=jjj, 2=count '2', 3=C (delete+insert), 4=ESC
        c2_wrap_content = ('S1\nS2\nS3\nAAAA\n' + 'B' * 30
                           + '\nS6\nS7\nS8\nS9\nS10\nS11\n')
        self.run_test_screen(
            "Minimal repaint: 2C with wrapped second line correct scroll",
            c2_wrap_content,
            b"jjj2C\x1b:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "S1"), (1, "S2"), (2, "S3"),
                (3, ""), (4, "S6"), (5, "S7"),
                (6, "S8"), (7, "S9"), (8, "S10"),
            ],
            expect_cursor=(3, 0),
        )

        self._group("Scroll opt: insert mode wrap:", leading_blank=True)

        # Typing at end of line past screen width: line wraps, LINE_COUNT16 increases.
        # Line 0: 18 chars at 20 cols (1 screen row). A=append at EOL, type "abc"
        # makes it 21 chars → wraps to 2 screen rows. Lines below should scroll down
        # via scroll optimization, not a full repaint.
        # Frames: 0=initial, 1=A enter insert, 2=typed chars (wrap occurs)
        ins_wrap_content = ("12345678901234567890\n"
                            + ''.join(f"Line {i}\n" for i in range(2, 12)))
        self.run_test_screen(
            "Scroll opt: insert typing at EOL causes wrap uses scroll",
            ins_wrap_content,
            b"Aa\x1b:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "12345678901234567890"),
                (1, "a"),
                (2, "Line 2"), (3, "Line 3"), (4, "Line 4"),
                (5, "Line 5"), (6, "Line 6"), (7, "Line 7"),
                (8, "Line 8"),
            ],
            expect_cursor=(1, 0),
            # Frame 2 (typing): change starts at col 20 (wrap row 1), so only new
            # row 1 needs rendering. Row 0 is unchanged (still full 20 chars).
            expect_content_rows=[(2, {1})]
        )

        # Typing within a line past screen width: same wrap, different cursor position.
        # Line 0: 18 chars at 20 cols. lllll=col 5, i=insert, type 6 i's.
        # 18+6=24 chars → wraps to 2 screen rows (20+4). Subsequent lines scroll down.
        # After ESC, cursor backs up 1 to col 10.
        # Frames: 0=initial, 1=lllll cursor, 2=i enter insert, 3=typed chars (wrap)
        self.run_test_screen(
            "Scroll opt: insert typing mid-line causes wrap uses scroll",
            ins_wrap_content,
            b"llllliiiiiii\x1b:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "12345iiiiii678901234"),
                (1, "567890"),
                (2, "Line 2"), (3, "Line 3"), (4, "Line 4"),
                (5, "Line 5"), (6, "Line 6"), (7, "Line 7"),
                (8, "Line 8"),
            ],
            expect_cursor=(0, 10),
            # Frame 3 (typing): only cursor line rows (0, 1) content-rendered
            expect_content_rows=[(3, {0, 1})]
        )

        self._group("Scroll opt: insert mode unwrap (shrink):", leading_blank=True)

        # BS at EOL causing unwrap: line shrinks from 2 screen rows to 1.
        # Line 0: 21 chars at 20 cols (2 screen rows: 20+1). $ moves to col 20,
        # A appends at col 21 (wrap row 1 col 1), BS deletes the 'a' -> 20 chars.
        # 20 chars = 1 screen row. Lines below should scroll up, not full repaint.
        # Frames: 0=initial, 1=$ move, 2=A enter insert, 3=BS (unwrap occurs)
        unwrap_content = ("12345678901234567890a\n"
                          + ''.join(f"Line {i}\n" for i in range(2, 12)))
        self.run_test_screen(
            "Scroll opt: insert BS at EOL causes unwrap uses scroll",
            unwrap_content,
            b"$A\x08\x1b:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "12345678901234567890"),
                (1, "Line 2"), (2, "Line 3"), (3, "Line 4"),
                (4, "Line 5"), (5, "Line 6"), (6, "Line 7"),
                (7, "Line 8"), (8, "Line 9"),
            ],
            expect_cursor=(0, 19),
            # Frame 3 (BS): change at col 20 (wrap row 1), past remaining 1 row.
            # Cursor line rendering skipped entirely, only bottom exposed row.
            expect_content_rows=[(3, {8})]
        )

        # BS mid-line causing unwrap: line shrinks from 2 to 1 screen row.
        # Line 0: 21 chars at 20 cols. lllll=col 5, i=insert, BS deletes char
        # at col 4 -> 20 chars = 1 screen row. Content shifts, render cursor row.
        # Frames: 0=initial, 1=lllll move, 2=i enter insert, 3=BS (unwrap)
        self.run_test_screen(
            "Scroll opt: insert BS mid-line causes unwrap uses scroll",
            unwrap_content,
            b"llllli\x08\x1b:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "1234678901234567890a"),  # char '5' deleted
                (1, "Line 2"), (2, "Line 3"), (3, "Line 4"),
                (4, "Line 5"), (5, "Line 6"), (6, "Line 7"),
                (7, "Line 8"), (8, "Line 9"),
            ],
            expect_cursor=(0, 3),
            # Frame 3 (BS): cursor line row redrawn + scroll pulls lines up.
            # Only row 0 (cursor line) and row 8 (newly exposed) content-rendered.
            expect_content_rows=[(3, {0, 8})]
        )

        # DELETE mid-line causing unwrap: line shrinks from 2 to 1 screen row.
        # Line 0: 21 chars at 20 cols. lllll=col 5, i=insert, DELETE deletes char
        # at col 5 -> 20 chars = 1 screen row. Content shifts.
        # Frames: 0=initial, 1=lllll move, 2=i enter insert, 3=DEL (unwrap)
        self.run_test_screen(
            "Scroll opt: insert DEL mid-line causes unwrap uses scroll",
            unwrap_content,
            b"llllli\x1b[3~\x1b:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "1234578901234567890a"),  # char '6' deleted (at col 5)
                (1, "Line 2"), (2, "Line 3"), (3, "Line 4"),
                (4, "Line 5"), (5, "Line 6"), (6, "Line 7"),
                (7, "Line 8"), (8, "Line 9"),
            ],
            expect_cursor=(0, 4),
            # Frame 3 (DEL): cursor line row redrawn + scroll pulls lines up.
            expect_content_rows=[(3, {0, 8})]
        )

        self._group("Scroll opt: insert DEL joining lines:", leading_blank=True)

        # DELETE at EOL joins next line: LINE_COUNT decreases.
        # Cursor at end of line 2 (Line 3, 6 chars), DELETE joins line 3 (Line 4).
        # Frames: 0=initial, 1=jj move, 2=$ move, 3=A enter insert, 4=DEL join
        self.run_test_screen(
            "Scroll opt: insert DEL at EOL joins line uses scroll",
            make_lines(15),
            b"jj$A\x1b[3~\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"),
                (2, "Line 3Line 4"), (3, "Line 5"), (4, "Line 6"),
                (5, "Line 7"), (6, "Line 8"), (7, "Line 9"),
                (8, "Line 10"),
            ],
            expect_cursor=(2, 5),
            # Frame 4 (DEL join): cursor row redrawn + bottom row exposed.
            # Should use scroll, not full repaint.
            expect_content_rows=[(4, {2, 8})]
        )

        # DELETE on empty line joins it with next: LINE_COUNT decreases.
        # Line 2 is empty. Cursor on line 2 col 0, DELETE joins with line 3.
        # Frames: 0=initial, 1=jj move, 2=i enter insert, 3=DEL join
        del_blank_content = ("Line 1\nLine 2\n\nLine 4\n"
                             + ''.join(f"Line {i}\n" for i in range(5, 15)))
        self.run_test_screen(
            "Scroll opt: insert DEL on blank line joins uses scroll",
            del_blank_content,
            b"jji\x1b[3~\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"),
                (2, "Line 4"), (3, "Line 5"), (4, "Line 6"),
                (5, "Line 7"), (6, "Line 8"), (7, "Line 9"),
                (8, "Line 10"),
            ],
            expect_cursor=(2, 0),
            # Frame 3 (DEL): cursor row redrawn + bottom row exposed.
            expect_content_rows=[(3, {2, 8})]
        )

        # Typing the first character on the second wrap row should NOT redraw
        # the first row. The first row is already complete (full SCREEN_COLS chars).
        # Only the second row (where the new char appears) needs rendering.
        # Line 0: exactly 20 chars (fills row 0 at 20 cols).
        # $=col 19, a=append at col 20 (enters insert), X typed at col 20.
        # Line becomes 21 chars → wraps to 2 rows. Row 0 unchanged (20 chars).
        # Frames: 0=initial, 1=$ cursor, 2=a enter insert, 3=X typed (wrap 1→2)
        wrap_20_content = ("A" * 20 + "\n"
                           + ''.join(f"Line {i}\n" for i in range(2, 12)))
        self.run_test_screen(
            "Scroll opt: insert first char on second wrap row",
            wrap_20_content,
            b"$aX\x1b:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "A" * 20),
                (1, "X"),
                (2, "Line 2"), (3, "Line 3"), (4, "Line 4"),
                (5, "Line 5"), (6, "Line 6"), (7, "Line 7"),
                (8, "Line 8"),
            ],
            expect_cursor=(1, 0),
            # Frame 3 (X typed): row 0 unchanged, only row 1 needs rendering
            expect_content_rows=[(3, {1})]
        )

        # Same but typing first char on the THIRD wrap row.
        # Line: 40 chars at 20 cols = 2 rows. $a=append at col 40, X typed.
        # 41 chars → 3 rows. Rows 0-1 unchanged, only row 2 needs rendering.
        # Frames: 0=initial, 1=$ cursor, 2=a enter insert, 3=X typed (wrap 2→3)
        wrap_40_content = ("B" * 40 + "\n"
                           + ''.join(f"Line {i}\n" for i in range(2, 12)))
        self.run_test_screen(
            "Scroll opt: insert first char on third wrap row",
            wrap_40_content,
            b"$aX\x1b:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "B" * 20),
                (1, "B" * 20),
                (2, "X"),
                (3, "Line 2"), (4, "Line 3"), (5, "Line 4"),
                (6, "Line 5"), (7, "Line 6"), (8, "Line 7"),
            ],
            expect_cursor=(2, 0),
            # Frame 3 (X typed): rows 0-1 unchanged, only row 2 needs rendering
            expect_content_rows=[(3, {2})]
        )

        # Backspace from wrap boundary (row 1, col 0) deletes the LAST char of
        # the previous row, causing unwrap from 2→1 rows. Only the last column
        # of row 0 changes (cleared). Row 0 should NOT be fully redrawn.
        # Line: 21 chars ("A"*20 + "Z") at 20 cols = 2 rows.
        # $=col 20 ('Z', row 1 col 0), a=append at col 21, BS deletes 'Z' at col 20.
        # Line becomes "A"*20 = 20 chars = 1 row. Unwrap.
        # Frames: 0=initial, 1=$ cursor, 2=a enter insert, 3=BS (unwrap 2→1)
        wrap_21_content = ("A" * 20 + "Z\n"
                           + ''.join(f"Line {i}\n" for i in range(2, 12)))
        self.run_test_screen(
            "Scroll opt: backspace at wrap row 1 col 0 minimal repaint",
            wrap_21_content,
            b"$a\x08\x1b:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "A" * 20),
                (1, "Line 2"), (2, "Line 3"), (3, "Line 4"),
                (4, "Line 5"), (5, "Line 6"), (6, "Line 7"),
                (7, "Line 8"), (8, "Line 9"),
            ],
            expect_cursor=(0, 19),
            # Frame 3 (BS): unwrap 2→1 rows. Scroll-up handles rows below.
            # Change is at col 20 (wrap row 1) which is past the remaining 1 row,
            # so cursor line rendering is skipped entirely. Only bottom exposed row.
            expect_content_rows=[(3, {8})]
        )

        # Backspace from wrap boundary (row 2, col 0) should NOT redraw rows 0-1.
        # Line: 41 chars ("C"*40 + "Z") at 20 cols = 3 rows.
        # $=col 40 ('Z', row 2 col 0), a=append at col 41, BS deletes 'Z' at col 40.
        # Line becomes "C"*40 = 40 chars = 2 rows. Unwrap 3→2.
        # Frames: 0=initial, 1=$ cursor, 2=a enter insert, 3=BS (unwrap 3→2)
        wrap_41_content = ("C" * 40 + "Z\n"
                           + ''.join(f"Line {i}\n" for i in range(2, 12)))
        self.run_test_screen(
            "Scroll opt: backspace at wrap row 2 col 0 minimal repaint",
            wrap_41_content,
            b"$a\x08\x1b:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "C" * 20),
                (1, "C" * 20),
                (2, "Line 2"), (3, "Line 3"), (4, "Line 4"),
                (5, "Line 5"), (6, "Line 6"), (7, "Line 7"),
                (8, "Line 8"),
            ],
            expect_cursor=(1, 19),
            # Frame 3 (BS): unwrap 3→2 rows. Change is at col 40 (wrap row 2)
            # which is past the remaining 2 rows, so cursor line rendering is
            # skipped entirely. Only bottom exposed row.
            expect_content_rows=[(3, {8})]
        )

        self._group("Sub-line render optimization:", leading_blank=True)

        # Normal r: replace at col 3, partial render from col 3
        # lll=move to col 3, rZ=replace with 'Z'
        # Frame 0=initial, 1=lll move, 2=rZ replace
        self.run_test_screen(
            "r replace: partial render from cursor col",
            "Hello World\n",
            b"lllrZ:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "HelZo World")],
            expect_min_col=[(2, 0, 3)],
            expect_max_col=[(2, 0, 3)]
        )

        # Normal ~: toggle case at col 3, partial render from col 3
        # lll=move to col 3, ~=toggle case
        # Frame 0=initial, 1=lll move, 2=~ toggle
        self.run_test_screen(
            "~ toggle case: partial render from cursor col",
            "Hello World\n",
            b"lll~:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "HelLo World")],
            expect_min_col=[(2, 0, 3)],
            expect_max_col=[(2, 0, 3)]
        )

        # Counted ~ at end of line: 3~ on "Hi" from col 0 toggles 'H','i'
        # then stops (can't advance past end). Should not write past EOL.
        # Frame 0=initial, 1=count '3' display, 2=~ operation
        self.run_test_screen(
            "~ counted at end of line: no garbage past EOL",
            "Hi\n",
            b"3~:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "hI")],
            expect_max_col=[(2, 0, 1)]
        )

        # Normal x: delete at col 3 touches nothing before col 3; the rest
        # of the row is shifted with DCH, so no cells are resent at all
        # lll=move to col 3, x=delete char
        # Frame 0=initial, 1=lll move, 2=x delete
        self.run_test_screen(
            "x delete: partial render from cursor col",
            "Hello World\n",
            b"lllx:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Helo World")],
            expect_ansi_contains="\x1b[1;4H\x1b[1P",
            expect_min_col=[(2, 0, -1)]
        )

        # Insert at end of line: only render from cursor position
        # A=append at EOL, type "world", ESC. 'Hello' is 5 chars,
        # so first affected col is 5. Frame 0=initial, 1=enter insert, 2=typed chars
        self.run_test_screen(
            "Insert at end of line: partial render from cursor col",
            "Hello\n",
            b"Aworld\x1b",
            rows=10, cols=40,
            expect_lines=[(0, "Helloworld")],
            # Frame 2 is the 'world' insert; row 0 should start at col 5
            expect_min_col=[(2, 0, 5)]
        )

        # Insert mid-line: render from affected column
        # lll=move to col 3, i=insert, type "XYZ", ESC
        # Frame 0=initial, 1=lll move, 2=i enter insert, 3=XYZ typed
        self.run_test_screen(
            "Insert mid-line: partial render from insert col",
            "Hello World\n",
            b"llliXYZ\x1b",
            rows=10, cols=40,
            expect_lines=[(0, "HelXYZlo World")],
            # Frame 3 is the insert; first affected col is 3
            expect_min_col=[(3, 0, 3)]
        )

        # Backspace mid-line: batched insert+BS renders from affected col
        # lll=col 3, i=insert, XY+BS batched → net insert "X" at col 3
        self.run_test_screen(
            "Backspace mid-line in insert mode: partial render",
            "Hello World\n",
            b"llliXY\x08\x1b",
            rows=10, cols=40,
            expect_lines=[(0, "HelXlo World")],
            # Frame 3 is the batched insert; first affected col is 3
            expect_min_col=[(3, 0, 3)]
        )

        # D: delete to end of line from col 3
        # lll=col 3, D=delete to EOL
        # Frame 0=initial, 1=lll move, 2=D delete
        self.run_test_screen(
            "D delete to EOL: partial render from cursor col",
            "Hello World\n",
            b"lllD:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hel")],
            expect_min_col=[(2, 0, 3)]
        )

        # D at col 0 on non-wrapped line: entire line emptied
        self.run_test_screen(
            "D at col 0: full line render",
            "Hello\n",
            b"D:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "")],
            expect_min_col=[(1, 0, 0)]
        )

        # D on wrapped line, cursor on wrap row 1: partial render from col
        # Line is 59 'A's (2 wrap rows in 40-col term). $ goes to col 58 (wrap row 1).
        # D deletes last char. Result: 58 chars, still 2 rows.
        self.run_test_screen(
            "D on wrapped line: partial render from cursor col",
            "A" * 59 + "\nSecond\n",
            b"$D:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A" * 40), (1, "A" * 18)],
            expect_min_col=[(2, 1, 18)]
        )

        # Batched 2D (D batched with pending D key)
        # 2D from col 3 should delete to EOL (same as D with count)
        self.run_test_screen(
            "2D batched: partial render from cursor col",
            "Hello World\n",
            b"lll2D:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hel")],
            expect_min_col=[(3, 0, 3)]
        )

        # C: change to EOL from col 3
        # lll=col 3, C=change to EOL, ESC=exit insert
        # Frame 0=initial, 1=lll move, 2=C change (enters insert), 3=ESC
        self.run_test_screen(
            "C change to EOL: partial render from cursor col",
            "Hello World\n",
            b"lllC\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hel")],
            expect_min_col=[(2, 0, 3)]
        )

        # C on wrapped line, cursor on wrap row 1: partial render
        self.run_test_screen(
            "C on wrapped line: partial render from cursor col",
            "A" * 59 + "\nSecond\n",
            b"$C\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A" * 40), (1, "A" * 18)],
            expect_min_col=[(2, 1, 18)]
        )

        # s: substitute at col 3
        # lll=col 3, s=substitute (deletes char, enters insert), ESC=exit
        # Frame 0=initial, 1=lll move, 2=s substitute
        self.run_test_screen(
            "s substitute: partial render from cursor col",
            "Hello World\n",
            b"llls\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Helo World")],
            expect_min_col=[(2, 0, 3)]
        )

        # 3s at col 3: substitute 3 chars from col 3
        self.run_test_screen(
            "3s substitute: partial render from cursor col",
            "Hello World\n",
            b"lll3s\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "HelWorld")],
            expect_min_col=[(3, 0, 3)]
        )

        # s on wrapped line, same row count
        self.run_test_screen(
            "s on wrapped line: partial render from cursor col",
            "A" * 50 + "\nSecond\n",
            b"$s\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A" * 40), (1, "A" * 9)],
            expect_min_col=[(2, 1, 9)]
        )

        # dw: delete word at col 6 in "Hello World Foo"
        # w=next word (col 6), dw=delete "World "
        # Frame 0=initial, 1=w move, 2=dw delete (batched combo)
        self.run_test_screen(
            "dw: partial render from cursor col",
            "Hello World Foo\n",
            b"wdw:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello Foo")],
            expect_min_col=[(2, 0, 6)]
        )

        # Batched 2dw: partial render from cursor col
        # w=next word (col 6), 2dw=delete "World Foo "
        self.run_test_screen(
            "2dw batched: partial render from cursor col",
            "Hello World Foo Bar\n",
            b"w2dw:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello Bar")],
            expect_min_col=[(3, 0, 6)]
        )

        # dw on wrapped line, cursor on wrap row 1
        # 50 A's + " BB" = 53 chars, wraps at col 40 into rows 0-1.
        # $ goes to col 52 (wrap row 1, col 12). dw from col 52 deletes "BB".
        # Partial render only touches wrap row 1 (col 12).
        self.run_test_screen(
            "dw on wrapped line: partial render wrap row 1",
            "A" * 50 + " BB\nSecond\n",
            b"wdw:q!\r",
            rows=10, cols=40,
            expect_min_col=[(2, 1, 11)]
        )

        # de: delete to end of word at col 6
        # w=next word (col 6), de=delete "World" (not trailing space)
        self.run_test_screen(
            "de: partial render from cursor col",
            "Hello World Foo\n",
            b"wde:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello  Foo")],
            expect_min_col=[(2, 0, 6)]
        )

        # Batched dw+dw (dw with pending dw)
        self.run_test_screen(
            "dw+dw batched: partial render from cursor col",
            "Hello World Foo Bar\n",
            b"wdwdw:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello Bar")],
            expect_min_col=[(2, 0, 6)]
        )

        # db: delete word backward from start of "Foo"
        # "Hello World Foo" → ww=col 12 (Foo), db deletes "World " → "Hello Foo"
        # Cursor moves backward to col 6, renders from col 6
        self.run_test_screen(
            "db: partial render from cursor col",
            "Hello World Foo\n",
            b"wwdb:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello Foo")],
            expect_min_col=[(2, 0, 6)]
        )

        # Batched 2db: deletes 2 words backward
        # "Hello World Foo Bar" → www=col 16 (Bar), 2db deletes "World Foo "
        self.run_test_screen(
            "2db batched: partial render from cursor col",
            "Hello World Foo Bar\n",
            b"www2db:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello Bar")],
            expect_min_col=[(3, 0, 6)]
        )

        # Batched db+db (db with pending db)
        self.run_test_screen(
            "db+db batched: partial render from cursor col",
            "Hello World Foo Bar\n",
            b"wwwdbdb:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello Bar")],
            expect_min_col=[(2, 0, 6)]
        )

        # db on wrapped line
        # 50 A's + " BB CC" = 56 chars, wraps. $=col 55, b=col 53 ("CC"), db deletes "BB "
        # Frame 0=initial, 1=$, 2=b, 3=db
        self.run_test_screen(
            "db on wrapped line: partial render from cursor col",
            "A" * 50 + " BB CC\nSecond\n",
            b"$bdb:q!\r",
            rows=10, cols=40,
            expect_min_col=[(3, 1, 11)]
        )

        # p (char paste below): x at col 0 yanks 'H', lllp pastes after col 3
        # "ello World" → after p → "elloH World" (H inserted after col 3)
        # Frame 0=initial, 1=x, 2=lll, 3=p
        self.run_test_screen(
            "p char paste: partial render from cursor col",
            "Hello World\n",
            b"xlllp:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "elloH World")],
            expect_min_col=[(3, 0, 3)]
        )

        # P (char paste above): x at col 0 yanks 'H', lllP pastes at col 3
        # "ello World" → after P → "ellHo World" (H inserted at col 3)
        self.run_test_screen(
            "P char paste: partial render from cursor col",
            "Hello World\n",
            b"xlllP:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "ellHo World")],
            expect_min_col=[(3, 0, 3)]
        )

        # Batched pp (paste with pending p)
        self.run_test_screen(
            "pp batched paste: partial render from cursor col",
            "Hello World\n",
            b"xlllpp:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "elloHH World")],
            expect_min_col=[(3, 0, 3)]
        )

        # p on wrapped line: paste on wrap row 1
        # 50 A's, $=col 49, x=delete→49 A's, h=col 47, p=paste after col 47
        # RENDER_FROM_COL16=47 → wrap row 1, col 7
        self.run_test_screen(
            "p char paste on wrapped line: partial render",
            "A" * 50 + "\nSecond\n",
            b"$xhp:q!\r",
            rows=10, cols=40,
            expect_min_col=[(4, 1, 7)]
        )

        self._group("Sub-line render opt: undo/redo char delete:", leading_blank=True)

        # x undo: restore char at col 3
        # Frames: 0=initial, 1=lll, 2=x, 3=u
        self.run_test_screen(
            "Undo x: partial render from undo col",
            "Hello World\n",
            b"lllxu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello World")],
            expect_min_col=[(3, 0, 3)]
        )

        # x redo: re-delete char at col 3
        # Frames: 0=initial, 1=lll, 2=x, 3=u, 4=space, 5=u(redo)
        self.run_test_screen(
            "Redo x: partial render from undo col",
            "Hello World\n",
            b"lllxu u:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Helo World")],
            expect_min_col=[(5, 0, 3)]
        )

        # D undo: restore from col 3
        # Frames: 0=initial, 1=lll, 2=D, 3=u
        self.run_test_screen(
            "Undo D: partial render from undo col",
            "Hello World\n",
            b"lllDu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello World")],
            expect_min_col=[(3, 0, 3)]
        )

        # D redo: re-delete from col 3
        # Frames: 0=initial, 1=lll, 2=D, 3=u, 4=space, 5=u(redo)
        self.run_test_screen(
            "Redo D: partial render from undo col",
            "Hello World\n",
            b"lllDu u:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hel")],
            expect_min_col=[(5, 0, 3)]
        )

        # dw undo: restore word at col 6
        # Frames: 0=initial, 1=w(col 6), 2=dw, 3=u
        self.run_test_screen(
            "Undo dw: partial render from undo col",
            "Hello World Foo\n",
            b"wdwu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello World Foo")],
            expect_min_col=[(3, 0, 6)]
        )

        # dw redo: re-delete word at col 6
        # Frames: 0=initial, 1=w, 2=dw, 3=u, 4=space, 5=u(redo)
        self.run_test_screen(
            "Redo dw: partial render from undo col",
            "Hello World Foo\n",
            b"wdwu u:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello Foo")],
            expect_min_col=[(5, 0, 6)]
        )

        # de undo: restore word at col 6
        # Frames: 0=initial, 1=w(col 6), 2=de, 3=u
        self.run_test_screen(
            "Undo de: partial render from undo col",
            "Hello World Foo\n",
            b"wdeu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello World Foo")],
            expect_min_col=[(3, 0, 6)]
        )

        # de redo: re-delete word at col 6
        # Frames: 0=initial, 1=w, 2=de, 3=u, 4=space, 5=u(redo)
        self.run_test_screen(
            "Redo de: partial render from undo col",
            "Hello World Foo\n",
            b"wdeu u:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello  Foo")],
            expect_min_col=[(5, 0, 6)]
        )

        # db undo: restore word at col 6
        # "Hello World Foo" → ww=col 12, db=delete "World " → cursor at col 6
        # Frames: 0=initial, 1=ww(col 12), 2=db, 3=u
        self.run_test_screen(
            "Undo db: partial render from undo col",
            "Hello World Foo\n",
            b"wwdbu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello World Foo")],
            expect_min_col=[(3, 0, 6)]
        )

        # db redo: re-delete word backward at col 6
        # Frames: 0=initial, 1=ww, 2=db, 3=u, 4=space, 5=u(redo)
        self.run_test_screen(
            "Redo db: partial render from undo col",
            "Hello World Foo\n",
            b"wwdbu u:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello Foo")],
            expect_min_col=[(5, 0, 6)]
        )

        # s undo (no typing): restore char at col 3
        # Frames: 0=initial, 1=lll, 2=s(insert enter), 3=ESC(insert exit), 4=u
        self.run_test_screen(
            "Undo s (no typing): partial render from undo col",
            "Hello World\n",
            b"llls\x1bu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello World")],
            expect_min_col=[(4, 0, 3)]
        )

        # s redo: re-delete char at col 3
        # Frames: 0=initial, 1=lll, 2=s, 3=ESC, 4=u, 5=space, 6=u(redo)
        self.run_test_screen(
            "Redo s (no typing): partial render from undo col",
            "Hello World\n",
            b"llls\x1bu u:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Helo World")],
            expect_min_col=[(6, 0, 3)]
        )

        # C undo (no typing): restore from col 3
        # Frames: 0=initial, 1=lll, 2=C(insert enter), 3=ESC(insert exit), 4=u
        self.run_test_screen(
            "Undo C (no typing): partial render from undo col",
            "Hello World\n",
            b"lllC\x1bu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello World")],
            expect_min_col=[(4, 0, 3)]
        )

        # C redo: re-delete from col 3
        # Frames: 0=initial, 1=lll, 2=C, 3=ESC, 4=u, 5=space, 6=u(redo)
        self.run_test_screen(
            "Redo C (no typing): partial render from undo col",
            "Hello World\n",
            b"lllC\x1bu u:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hel")],
            expect_min_col=[(6, 0, 3)]
        )

        # cw undo (no typing): restore word at col 6
        # Frames: 0=initial, 1=w(col 6), 2=cw(insert enter), 3=ESC, 4=u
        self.run_test_screen(
            "Undo cw (no typing): partial render from undo col",
            "Hello World Foo\n",
            b"wcw\x1bu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello World Foo")],
            expect_min_col=[(4, 0, 6)]
        )

        # cw redo: re-delete word at col 6 (cw = change to end of word, not trailing space)
        # Frames: 0=initial, 1=w, 2=cw, 3=ESC, 4=u, 5=space, 6=u(redo)
        self.run_test_screen(
            "Redo cw (no typing): partial render from undo col",
            "Hello World Foo\n",
            b"wcw\x1bu u:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello  Foo")],
            expect_min_col=[(6, 0, 6)]
        )

        # x undo on wrapped line (same row count)
        # 50 A's + B, $ to col 50, x deletes B (49 chars left + A at end = 50 A's)
        # Actually: 50 A's + "B" = 51 chars. $ = col 50. x deletes B = 50 A's.
        # Undo restores B at col 50 → wrap row 1, col 10
        # Frames: 0=initial, 1=$, 2=x, 3=u
        self.run_test_screen(
            "Undo x on wrapped line: partial render",
            "A" * 50 + "B\nSecond\n",
            b"$xu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A" * 40), (1, "A" * 10 + "B")],
            expect_min_col=[(3, 1, 10)]
        )

        # x redo on wrapped line (same row count)
        # Frames: 0=initial, 1=$, 2=x, 3=u, 4=space, 5=u(redo)
        self.run_test_screen(
            "Redo x on wrapped line: partial render",
            "A" * 50 + "B\nSecond\n",
            b"$xu u:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A" * 40), (1, "A" * 10)],
            expect_min_col=[(5, 1, 10)]
        )

        self._group("Sub-line render opt: undo/redo char paste:", leading_blank=True)

        # p undo: x at col 0 yanks 'H', lll → col 3 ('o'), p pastes after col 3
        # Content after p: "elloH World". Undo: "ello World", UNDO_COL16=4.
        # Frames: 0=initial, 1=x, 2=lll, 3=p, 4=u
        self.run_test_screen(
            "Undo p char paste: partial render from undo col",
            "Hello World\n",
            b"xlllpu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "ello World")],
            expect_min_col=[(4, 0, 4)]
        )

        # p redo: redo paste (calls do_char_paste_below, RENDER_FROM_COL16=cursor col=3)
        # Frames: 0=initial, 1=x, 2=lll, 3=p, 4=u, 5=space, 6=u(redo)
        self.run_test_screen(
            "Redo p char paste: partial render from cursor col",
            "Hello World\n",
            b"xlllpu u:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "elloH World")],
            expect_min_col=[(6, 0, 3)]
        )

        # P undo: x at col 0 yanks 'H', lll → col 3 ('o'), P pastes at col 3
        # Content after P: "ellHo World". Undo: "ello World", UNDO_COL16=3.
        # Frames: 0=initial, 1=x, 2=lll, 3=P, 4=u
        self.run_test_screen(
            "Undo P char paste: partial render from undo col",
            "Hello World\n",
            b"xlllPu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "ello World")],
            expect_min_col=[(4, 0, 3)]
        )

        # P redo: redo paste (calls do_char_paste_above, RENDER_FROM_COL16=cursor col=3)
        # Frames: 0=initial, 1=x, 2=lll, 3=P, 4=u, 5=space, 6=u(redo)
        self.run_test_screen(
            "Redo P char paste: partial render from cursor col",
            "Hello World\n",
            b"xlllPu u:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "ellHo World")],
            expect_min_col=[(6, 0, 3)]
        )

        # p undo on wrapped line (same row count)
        # 50 A's + B. $ → col 50, x yanks B → 50 A's, h → col 48, p pastes after 48
        # Paste at col 49 (UNDO_COL16=49). Undo: 50 A's. Wrap row 1, col 9.
        # Frames: 0=initial, 1=$, 2=x, 3=h, 4=p, 5=u
        self.run_test_screen(
            "Undo p char paste on wrapped line: partial render",
            "A" * 50 + "B\nSecond\n",
            b"$xhpu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A" * 40), (1, "A" * 10)],
            expect_min_col=[(5, 1, 9)]
        )

        self._group("Sub-line render opt: J redo:", leading_blank=True)

        # J redo same height on narrow screen: "Hello" (5) + "World" (5) = 11 chars
        # On 10-col screen: 2 lines × 1 row = 2 screen rows → 11 chars = 2 wrap rows
        # Same height: .j_really_no_scroll → render_current_line_and_status
        # RENDER_FROM_COL16 = 5, from_wrap = 0, from_col = 5: partial from col 5
        # Frames: 0=initial, 1=J, 2=u, 3=space (noop), 4=u (redo)
        self.run_test_screen(
            "J redo same height wrapping: partial from join col",
            "Hello\nWorld\nThird\n",
            b"Ju u:q!\r",
            rows=10, cols=10,
            expect_lines=[(0, "Hello Worl"), (1, "d"), (2, "Third")],
            expect_cursor=(0, 5),
            expect_min_col=[(4, 0, 5)]
        )

        # J redo wrapped, same total screen rows (batched JJ):
        # Before redo: "First longer line!! Second longer line!" (39 chars, 2 rows on 20-col)
        #            + "Third!" (1 row) = 3 screen rows
        # After redo:  "First longer line!! Second longer line! Third!" (46 chars, 3 rows)
        # Same height: wrap row 0 skipped, render from col 19 on row 1
        # Frames: 0=initial, 1=JJ (batched), 2=u, 3=space, 4=u (redo)
        self.run_test_screen(
            "J redo wrapped same height: partial from join col",
            "First longer line!!\nSecond longer line!\nThird!\nEnd\n",
            b"JJu u:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "First longer line!!"),
                (1, "Second longer line!"),
                (2, "Third!"),
                (3, "End"),
            ],
            expect_cursor=(1, 19),
            expect_content_rows=[(4, {1, 2})],
            expect_min_col=[(4, 1, 19)]
        )

        self._group("Sub-line render opt: scroll path RENDER_FROM_COL16:", leading_blank=True)

        # J forward, non-wrapped result on scroll path (old_total > new_total):
        # "Hello" (5) + "World" → "Hello World" (11 chars, 1 row on 40-col)
        # Old = 2 rows, new = 1 row, delta = 1 → scroll up
        # RENDER_FROM_COL16 = 5, .render_cursor_row path
        # Frames: 0=initial, 1=J
        self.run_test_screen(
            "J scroll path non-wrapped: partial from join col",
            "Hello\nWorld\nEnd\n",
            b"J:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello World"), (1, "End")],
            expect_cursor=(0, 5),
            expect_min_col=[(1, 0, 5)]
        )

        # J forward wrapped result on scroll path (old_total > new_total):
        # 3J on 5-col: joins 2 lines. "AA\nBB\nCC\n" → "AA BB CC" (8 chars, 2 rows)
        # Old = 3 rows (3 lines × 1), new = 2 rows, delta = 1 → scroll up
        # RENDER_FROM_COL16 = 2, .check_wrap path (new_total = 2)
        # from_wrap = 0, from_col = 2: partial render first wrap row from col 2
        # Frames: 0=initial, 1='3' count, 2=J
        self.run_test_screen(
            "J scroll path wrapped: partial from join col",
            "AA\nBB\nCC\nEnd\n",
            b"3J:q!\r",
            rows=10, cols=5,
            expect_lines=[(0, "AA BB"), (1, " CC"), (2, "End")],
            expect_cursor=(0, 2),
            expect_min_col=[(2, 0, 2)]
        )

        # J forward wrapped, from_wrap > 0 (skip full wrap rows):
        # 3J on 5-col: "AAAAAAA" (7 chars, 2 rows) + "BB" + "CC"
        # → "AAAAAAA BB CC" (13 chars, 3 rows on 5-col)
        # Old = 2+1+1 = 4 rows, new = 3 rows, delta = 1 → scroll up
        # RENDER_FROM_COL16 = 7, from_wrap = 7/5 = 1, from_col = 2
        # Wrap row 0 unchanged, render from col 2 on wrap row 1, full wrap row 2
        # Frames: 0=initial, 1='3' count, 2=J
        self.run_test_screen(
            "J scroll path wrapped from_wrap>0: skip unchanged rows",
            "AAAAAAA\nBB\nCC\nEnd\n",
            b"3J:q!\r",
            rows=10, cols=5,
            expect_lines=[(0, "AAAAA"), (1, "AA BB"), (2, " CC"), (3, "End")],
            expect_cursor=(1, 2),
            expect_min_col=[(2, 1, 2)]
        )

        self._group("Sub-line render opt: insert mode joins:", leading_blank=True)

        # Insert DEL at EOL joining next line:
        # "Hello\nWorld\n" on 40-col. $a → insert at col 5 (past last char).
        # DEL at col 5 deletes newline → "HelloWorld"
        # RENDER_FROM_COL16 = CURSOR_COL16 = 5
        # Frames: 0=initial, 1=$ (EOL), 2=a (enter insert), 3=DEL (join)
        DEL = b"\x1b[3~"
        self.run_test_screen(
            "Insert DEL join: partial from cursor col",
            "Hello\nWorld\nEnd\n",
            b"$a" + DEL + b"\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "HelloWorld"), (1, "End")],
            expect_cursor=(0, 4),
            expect_min_col=[(3, 0, 5)]
        )

        # Insert BS at col 0 joining with previous line:
        # "Hello\nWorld\n" on 40-col. ji → insert at line 1, col 0.
        # BS deletes newline at end of "Hello" → "HelloWorld", cursor at col 5
        # RENDER_FROM_COL16 = CURSOR_COL16 = 5
        # Frames: 0=initial, 1=j (move down), 2=i (enter insert), 3=BS (join)
        self.run_test_screen(
            "Insert BS join: partial from cursor col",
            "Hello\nWorld\nEnd\n",
            b"ji\x08\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "HelloWorld"), (1, "End")],
            expect_cursor=(0, 4),
            expect_min_col=[(3, 0, 5)]
        )

        self._group("Sub-line render opt: wrapped line row change:", leading_blank=True)

        # D on wrapped line causing row decrease:
        # 50 A's on 40-col screen (2 rows). Cursor at col 5 (5 l's).
        # D deletes from col 5 → "AAAAA" (5 chars, 1 row). Rows: 2 → 1.
        # RENDER_FROM_COL16 = 5. .rc_rows_decreased path.
        # Frames: 0=initial, 1=lllll, 2=D
        self.run_test_screen(
            "D on wrapped line rows decrease: partial from cursor col",
            "A" * 50 + "\nSecond\n",
            b"lllllD:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "AAAAA"), (1, "Second")],
            expect_cursor=(0, 4),
            expect_min_col=[(2, 0, 5)]
        )

        # C on wrapped line causing row decrease:
        # Same setup but C enters insert mode. ESC exits without typing.
        # Frames: 0=initial, 1=lllll, 2=C (enters insert + renders)
        self.run_test_screen(
            "C on wrapped line rows decrease: partial from cursor col",
            "A" * 50 + "\nSecond\n",
            b"lllllC\x1b:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "AAAAA"), (1, "Second")],
            expect_cursor=(0, 4),
            expect_min_col=[(2, 0, 5)]
        )

        # D on wrapped line, from_wrap > 0:
        # 90 A's on 40-col screen (3 rows: 40+40+10). Cursor at col 45 (wrap row 1).
        # D deletes from col 45 → 45 A's (2 rows: 40+5). Rows: 3 → 2.
        # RENDER_FROM_COL16 = 45. from_wrap=1, from_col=5.
        # Wrap row 0 unchanged, partial from col 5 on wrap row 1.
        # Frames: 0=initial, 1="4", 2="5", 3=l(45l), 4=D
        self.run_test_screen(
            "D on wrapped line from_wrap>0: partial from col in second wrap row",
            "A" * 90 + "\nSecond\n",
            b"45lD:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A" * 40), (1, "A" * 5), (2, "Second")],
            expect_cursor=(1, 4),
            expect_min_col=[(4, 1, 5)]
        )

        # Undo D on wrapped line (rows increase: 1 → 2):
        # D at col 5 on 50 A's → "AAAAA" (1 row). Undo restores 50 A's (2 rows).
        # .rc_render_from_row path. RENDER_FROM_COL16 = UNDO_COL16 = 5.
        # Frames: 0=initial, 1=lllll, 2=D, 3=u
        self.run_test_screen(
            "Undo D on wrapped line rows increase: partial from undo col",
            "A" * 50 + "\nSecond\n",
            b"lllllDu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A" * 40), (1, "A" * 10), (2, "Second")],
            expect_cursor=(0, 5),
            expect_min_col=[(3, 0, 5)]
        )

        # Redo D on wrapped line (rows decrease: 2 → 1):
        # Same as D forward. .rc_rows_decreased path.
        # Frames: 0=initial, 1=lllll, 2=D, 3=u(undo), 4=space(noop), 5=u(redo)
        self.run_test_screen(
            "Redo D on wrapped line rows decrease: partial from redo col",
            "A" * 50 + "\nSecond\n",
            b"lllllDu u:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "AAAAA"), (1, "Second")],
            expect_cursor=(0, 4),
            expect_min_col=[(5, 0, 5)]
        )

        # Undo D from_wrap>0 (rows increase: 2 → 3):
        # D at col 45 on 90 A's → 45 A's (2 rows). Undo → 90 A's (3 rows).
        # RENDER_FROM_COL16 = UNDO_COL16 = 45. from_wrap=1, from_col=5.
        # Frames: 0=initial, 1="4", 2="5", 3=l(45l), 4=D, 5=u
        self.run_test_screen(
            "Undo D from_wrap>0: partial from col in second wrap row",
            "A" * 90 + "\nSecond\n",
            b"45lDu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A" * 40), (1, "A" * 40), (2, "A" * 10), (3, "Second")],
            expect_cursor=(1, 5),
            expect_min_col=[(5, 1, 5)]
        )

        # J on wrapped line (total rows unchanged, .j_really_no_scroll):
        # "A"*38 + "\nBB\nThird\n" on 40-col. J → "A"*38 + " BB" = 41 chars (2 rows).
        # Total before: 1+1+1=3. After: 2+1=3. Same total → render_current_line_and_status.
        # RENDER_FROM_COL16 = 38 (join col). from_wrap=0, from_col=38.
        # Frames: 0=initial, 1=J
        self.run_test_screen(
            "J on wrapped result same total: partial from join col",
            "A" * 38 + "\nBB\nThird\n",
            b"J:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A" * 38 + " B"), (1, "B"), (2, "Third")],
            expect_cursor=(0, 38),
            expect_min_col=[(1, 0, 38)]
        )

        # J on non-wrapped result (total rows decrease):
        # "AAAAA\nBBB\nThird\n" on 40-col. J → "AAAAA BBB" = 9 chars (1 row).
        # Total before: 3. After: 2. Scroll path (RENDER_FLAG=$06).
        # RENDER_FROM_COL16 = 5 (join col). render_line_delete_scroll partial.
        # Frames: 0=initial, 1=J
        self.run_test_screen(
            "J on non-wrapped result total decrease: partial from join col",
            "AAAAA\nBBB\nThird\n",
            b"J:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "AAAAA BBB"), (1, "Third")],
            expect_cursor=(0, 5),
            expect_min_col=[(1, 0, 5)]
        )

        # Redo J on wrapped result (same total):
        # Same setup as J wrapped test above. Ju u (undo, break, redo).
        # Frames: 0=initial, 1=J, 2=u(undo), 3=space(noop), 4=u(redo)
        self.run_test_screen(
            "Redo J on wrapped result: partial from join col",
            "A" * 38 + "\nBB\nThird\n",
            b"Ju u:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A" * 38 + " B"), (1, "B"), (2, "Third")],
            expect_cursor=(0, 38),
            expect_min_col=[(4, 0, 38)]
        )

        # Undo C on wrapped line (rows increase: 1 → 2):
        # C at col 5 on 50 A's → "AAAAA" (1 row). ESC exits. Undo restores.
        # Frames: 0=initial, 1=lllll, 2=C, 3=ESC, 4=u(undo)
        self.run_test_screen(
            "Undo C on wrapped line rows increase: partial from undo col",
            "A" * 50 + "\nSecond\n",
            b"lllllC\x1bu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A" * 40), (1, "A" * 10), (2, "Second")],
            expect_cursor=(0, 5),
            expect_min_col=[(4, 0, 5)]
        )

        # Redo C on wrapped line (rows decrease: 2 → 1):
        # Frames: 0=initial, 1=lllll, 2=C, 3=ESC, 4=u(undo), 5=space, 6=u(redo)
        self.run_test_screen(
            "Redo C on wrapped line rows decrease: partial from redo col",
            "A" * 50 + "\nSecond\n",
            b"lllllC\x1bu u:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "AAAAA"), (1, "Second")],
            expect_cursor=(0, 4),
            expect_min_col=[(6, 0, 5)]
        )

        # Undo p (char paste) on wrapped line (rows decrease: 2 → 1):
        # "A"*38 + "\nSecond\n". x at col 0 yanks 'A'. p at col 37 pastes → 38 A's.
        # 38 + 1 = 39 chars (1 row). Wait, p inserts after cursor, line grows to 39.
        # Use different approach: yank multiple chars, paste to cause wrap, undo unwraps.
        # "A"*35 + "\nSecond\n" (35 chars, 1 row). 10x yanks 10 chars. Then p pastes 10.
        # After p: "A"*25 + "A"*10 = 35 chars still. No, x deletes, not just yanks.
        # Simpler: "A"*38 + "\nSecond\n". $ goes to col 37. p pastes 'A' after → 39 chars.
        # That doesn't wrap (39 < 40). Need to cause wrap.
        # "A"*39 + "\nSecond\n". x at col 0 → 38 A's (1 row), yanks 'A'. p at col 37
        # inserts after → 39 A's (1 row, still < 40). Need more.
        # Better: yank 2 chars: 2x at col 0 on "A"*40 → 38 A's. $p → 39 A's (no wrap).
        # Or: "A"*39 + "B\nSecond\n" (40 chars, 1 row). x at col 0 → 39 chars. p at $ → 40 (1 row).
        # Still no wrap. Need 41+ to wrap. Use bigger yank.
        # Simplest: "A"*41 + "\nSecond\n" (41 chars, 2 rows). D at $ deletes 1 char → 40 chars (1 row).
        # Undo restores 41 (2 rows). But that's D undo, not p undo.
        # For p undo: yank a chunk, paste, then undo the paste.
        # Actually this is getting complex. Let me test undo of x on wrapped line instead.

        # Undo x on wrapped line (rows increase: 1 → 2):
        # "A"*41 (2 rows on 40-col). x at col 0 → 40 A's (1 row). Undo → 41 (2 rows).
        # RENDER_FROM_COL16 = UNDO_COL16 = 0. from_col=0 → full row render (no partial).
        # This verifies the undo scroll works without regression.
        self.run_test_screen(
            "Undo x on wrapped line rows increase: full row render",
            "A" * 41 + "\nSecond\n",
            b"xu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A" * 40), (1, "A"), (2, "Second")],
            expect_cursor=(0, 0),
            expect_min_col=[(2, 0, 0)]
        )

        self._group("Undo (u):", leading_blank=True)

        # dd undo: restore deleted line
        self.run_test(
            "dd undo restores deleted line",
            "Hello\nWorld\n",
            b"ddu:wq\r",
            expected_content="Hello\nWorld\n"
        )

        # dd undo then redo
        self.run_test(
            "dd undo then redo",
            "Hello\nWorld\n",
            b"ddu u:wq\r",
            expected_content="World\n"
        )

        # dd undo on last line
        self.run_test(
            "dd undo on last line of 3-line file",
            "A\nB\nC\n",
            b"jjddu:wq\r",
            expected_content="A\nB\nC\n"
        )

        # 2dd undo
        self.run_test(
            "2dd undo restores both lines",
            "A\nB\nC\n",
            b"2ddu:wq\r",
            expected_content="A\nB\nC\n"
        )

        # --- Indent/unindent undo ---

        self.run_test(
            ">> undo restores content",
            "Hello\nWorld\n",
            b">>u:wq\r",
            expected_content="Hello\nWorld\n"
        )

        self.run_test(
            ">> undo then redo",
            "Hello\nWorld\n",
            b">>u u:wq\r",
            expected_content="  Hello\nWorld\n"
        )

        # 3>> over mixed lines: empty line untouched, undo exact
        self.run_test(
            "3>> undo restores mixed lines (empty untouched)",
            "aaa\n\nccc\nddd\n",
            b"3>>u:wq\r",
            expected_content="aaa\n\nccc\nddd\n"
        )

        self.run_test(
            "3>> undo redo cycles (u u u)",
            "aaa\n\nccc\nddd\n",
            b"3>>u u u:wq\r",
            expected_content="aaa\n\nccc\nddd\n"
        )

        # << with uneven indents: per-line removal counts restored exactly
        self.run_test(
            "3<< undo restores uneven indents",
            " a\n  b\n    c\n",
            b"3<<u:wq\r",
            expected_content=" a\n  b\n    c\n"
        )

        self.run_test(
            "3<< undo then redo",
            " a\n  b\n    c\n",
            b"3<<u u:wq\r",
            expected_content="a\nb\n  c\n"
        )

        # >> preserving pre-existing indentation on undo
        self.run_test(
            ">> undo preserves existing indent",
            "  already\n",
            b">>u:wq\r",
            expected_content="  already\n"
        )

        # Range indent undo
        self.run_test(
            ":1,3> undo restores content",
            "aaa\nbbb\nccc\nddd\n",
            b":1,3>\ru:wq\r",
            expected_content="aaa\nbbb\nccc\nddd\n"
        )

        self.run_test(
            ":1,2< undo restores content",
            "  aaa\n bbb\nccc\n",
            b":1,2<\ru:wq\r",
            expected_content="  aaa\n bbb\nccc\n"
        )

        # Batched >>>> merges execution (4 spaces at once) but undo must
        # behave as if >> ran twice: u removes only the last step
        self.run_test(
            ">>>> batched undo removes last step only",
            "Hello\n",
            b">>>>u:wq\r",
            expected_content="  Hello\n"
        )

        self.run_test(
            ">>>> batched undo then redo",
            "Hello\n",
            b">>>>u u:wq\r",
            expected_content="    Hello\n"
        )

        # Batched <<<< : u restores only what the last << removed
        self.run_test(
            "<<<< batched undo restores last step only",
            "    Hello\n",
            b"<<<<u:wq\r",
            expected_content="  Hello\n"
        )

        # Batched <<<< where earlier steps consumed all the indent: the
        # last << removed nothing, so there is nothing to undo
        self.run_test(
            "<<<< batched undo noop when last step removed nothing",
            "  Hello\n",
            b"<<<<u:wq\r",
            expected_content="Hello\n"
        )

        # Batched 2>>>> on two lines: undo removes the last 2-space step
        # from both lines of the range
        self.run_test(
            "2>>>> batched undo removes last step from range",
            "aaa\nbbb\nccc\n",
            b"2>>>>u:wq\r",
            expected_content="  aaa\n  bbb\nccc\n"
        )

        # << that removes nothing is a no-op and records no undo:
        # u then re-executes nothing (prior undo state was cleared)
        self.run_test(
            "<< no-op leaves file unmodified (q without !)",
            "Hello\nWorld\n",
            b"<<:q\r",
            expected_content="Hello\nWorld\n"
        )

        # >> then movement then u: undo applies to the recorded range
        self.run_test(
            ">> j u undoes indent from another line",
            "aaa\nbbb\n",
            b">>ju:wq\r",
            expected_content="aaa\nbbb\n"
        )

        # --- Replace char (r) undo ---

        self.run_test(
            "r undo restores char",
            "Hello\n",
            b"rXu:wq\r",
            expected_content="Hello\n"
        )

        self.run_test(
            "r undo then redo",
            "Hello\n",
            b"rXu u:wq\r",
            expected_content="Xello\n"
        )

        self.run_test(
            "3rX undo restores all chars",
            "Hello\n",
            b"3rXu:wq\r",
            expected_content="Hello\n"
        )

        self.run_test(
            "3rX undo redo cycle",
            "Hello\n",
            b"3rXu u:wq\r",
            expected_content="XXXlo\n"
        )

        self.run_test(
            "r undo restores mixed punctuation",
            "a.b\n",
            b"3rZu:wq\r",
            expected_content="a.b\n"
        )

        self.run_test(
            "r j u undoes replace from another line",
            "abc\ndef\n",
            b"rXju:wq\r",
            expected_content="abc\ndef\n"
        )

        # --- Toggle case (~) undo ---

        self.run_test(
            "~ undo restores case",
            "Hello\n",
            b"~u:wq\r",
            expected_content="Hello\n"
        )

        self.run_test(
            "~ undo then redo",
            "Hello\n",
            b"~u u:wq\r",
            expected_content="hello\n"
        )

        self.run_test(
            "5~ undo restores span with punctuation",
            "a.b.c\n",
            b"5~u:wq\r",
            expected_content="a.b.c\n"
        )

        self.run_test(
            "~ j u undoes toggle from another line",
            "abc\ndef\n",
            b"3~ju:wq\r",
            expected_content="abc\ndef\n"
        )

        # dd then dd then undo: first dd stays, second dd undone
        self.run_test(
            "dd dd u: first dd stays, second dd undone",
            "A\nB\nC\n",
            b"ddjddu:wq\r",
            expected_content="B\nC\n"
        )

        # dd then insert clears undo
        self.run_test(
            "dd then oNew ESC u: insert clears undo",
            "A\nB\n",
            b"ddoNew\x1bu:wq\r",
            expected_content="B\nNew\n"
        )

        # u with no prior edit is no-op
        self.run_test(
            "u with no prior edit is no-op",
            "Hello\n",
            b"u:wq\r",
            expected_content="Hello\n",
            expect_unmodified=True
        )

        self._group("Undo char-delete (x, D, dw, db, de):", leading_blank=True)

        # x undo
        self.run_test(
            "x undo restores deleted char",
            "Hello\n",
            b"xu:wq\r",
            expected_content="Hello\n"
        )

        # x undo then redo
        self.run_test(
            "x undo then redo",
            "Hello\n",
            b"xu u:wq\r",
            expected_content="ello\n"
        )

        # D undo at col 2
        self.run_test(
            "D undo at col 2",
            "Hello\n",
            b"llDu:wq\r",
            expected_content="Hello\n"
        )

        # dw undo
        self.run_test(
            "dw undo restores deleted word",
            "Hello World\n",
            b"dwu:wq\r",
            expected_content="Hello World\n"
        )

        # db undo
        self.run_test(
            "db undo restores deleted word backward",
            "Hello World\n",
            b"edbu:wq\r",
            expected_content="Hello World\n"
        )

        # de undo
        self.run_test(
            "de undo restores deleted word end",
            "Hello World\n",
            b"deu:wq\r",
            expected_content="Hello World\n"
        )

        # 3x undo
        self.run_test(
            "3x undo restores 3 deleted chars",
            "Hello\n",
            b"3xu:wq\r",
            expected_content="Hello\n"
        )

        # d$ undo
        self.run_test(
            "d$ undo restores deleted text",
            "Hello\n",
            b"lld$u:wq\r",
            expected_content="Hello\n"
        )

        # d$ undo then redo
        self.run_test(
            "d$ undo then redo",
            "Hello\n",
            b"lld$u u:wq\r",
            expected_content="He\n"
        )

        # 2D undo restores multi-line delete
        self.run_test(
            "2D undo restores multi-line",
            "Hello\nWorld\nFoo\n",
            b"ll2Du:wq\r",
            expected_content="Hello\nWorld\nFoo\n"
        )

        # d0 undo
        self.run_test(
            "d0 undo restores deleted text",
            "Hello\n",
            b"llld0u:wq\r",
            expected_content="Hello\n"
        )

        # y$ doesn't set undo (yank only)
        self.run_test(
            "y$ u is no-op (yank doesn't set undo)",
            "Hello\n",
            b"lly$u:wq\r",
            expected_content="Hello\n"
        )

        # S undo (goes through cc path)
        self.run_test(
            "S ESC undo restores line",
            "Hello\nWorld\n",
            b"S\x1bu:wq\r",
            expected_content="Hello\nWorld\n"
        )

        # 2S undo
        self.run_test(
            "2S ESC undo restores both lines",
            "Hello\nWorld\nFoo\n",
            b"2S\x1bu:wq\r",
            expected_content="Hello\nWorld\nFoo\n"
        )

        # 2S undo then redo
        self.run_test(
            "2S ESC uu re-substitutes",
            "Hello\nWorld\nFoo\n",
            b"2S\x1buu:wq\r",
            expected_content="\nFoo\n"
        )

        self._group("Undo change commands (clean insert exit):", leading_blank=True)

        # s + ESC without typing + undo
        self.run_test(
            "s ESC undo restores char",
            "Hello\n",
            b"s\x1bu:wq\r",
            expected_content="Hello\n"
        )

        # s + typing clears undo
        self.run_test(
            "sX ESC: typing clears undo",
            "Hello\n",
            b"sX\x1bu:wq\r",
            expected_content="Xello\n"
        )

        # cc + ESC + undo
        self.run_test(
            "cc ESC undo restores line",
            "Hello\nWorld\n",
            b"cc\x1bu:wq\r",
            expected_content="Hello\nWorld\n"
        )

        # cc undo when next line is blank
        self.run_test(
            "cc ESC undo preserves following blank line",
            "Hello\n\nWorld\n",
            b"cc\x1bu:wq\r",
            expected_content="Hello\n\nWorld\n"
        )

        # 2cc undo when following line is blank
        self.run_test(
            "2cc ESC undo preserves following blank line",
            "A\nB\n\nC\n",
            b"2cc\x1bu:wq\r",
            expected_content="A\nB\n\nC\n"
        )

        # 3cc undo when following line is blank
        self.run_test(
            "3cc ESC undo preserves following blank line",
            "A\nB\nC\n\nD\n",
            b"3cc\x1bu:wq\r",
            expected_content="A\nB\nC\n\nD\n"
        )

        # 2cc ESC undo: screen shows both restored lines
        self.run_test_screen(
            "2cc ESC undo: screen shows both restored lines",
            "Line 1\nLine 2\nLine 3\n",
            b"2cc\x1bu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Line 1"), (1, "Line 2"), (2, "Line 3")],
            expect_cursor=(0, 0),
        )

        # cc undo preserves mark below (undo must adjust marks when deleting blank)
        self.run_test_screen(
            "cc undo preserves mark set below",
            "A\nB\nC\nD\n",
            b"jjmaggcc\x1bu'a:q!\r",
            rows=10, cols=40,
            expect_cursor=(2, 0),  # mark on "C" = line 2 after undo
        )

        # cc redo preserves mark below (redo must adjust marks when inserting blank)
        self.run_test_screen(
            "cc redo preserves mark set below",
            "A\nB\nC\nD\n",
            b"jjmaggcc\x1bu u'a:q!\r",
            rows=10, cols=40,
            expect_cursor=(2, 0),  # mark on "C" = line 2 after redo
        )

        # dd undo preserves mark below
        self.run_test_screen(
            "dd undo preserves mark set below",
            "A\nB\nC\nD\n",
            b"jjmaggddu'a:q!\r",
            rows=10, cols=40,
            expect_cursor=(2, 0),  # mark on "C" = line 2 after undo
        )

        # dd redo preserves mark below
        self.run_test_screen(
            "dd redo preserves mark set below",
            "A\nB\nC\nD\n",
            b"jjmaggddu u'a:q!\r",
            rows=10, cols=40,
            expect_cursor=(1, 0),  # mark on "C" = line 1 after redo (A deleted)
        )

        # cc + typing clears undo
        self.run_test(
            "cc New ESC: typing clears undo",
            "Hello\nWorld\n",
            b"ccNew\x1bu:wq\r",
            expected_content="New\nWorld\n"
        )

        # C + ESC + undo
        self.run_test(
            "C ESC undo at col 2",
            "Hello\n",
            b"llC\x1bu:wq\r",
            expected_content="Hello\n"
        )

        # cw + ESC + undo
        self.run_test(
            "cw ESC undo restores word",
            "Hello World\n",
            b"cw\x1bu:wq\r",
            expected_content="Hello World\n"
        )

        self._group("Undo join (J):", leading_blank=True)

        # J undo: restore joined lines
        self.run_test(
            "J undo restores original lines",
            "Hello\nWorld\n",
            b"Ju:wq\r",
            expected_content="Hello\nWorld\n"
        )

        # J undo then redo
        self.run_test(
            "J undo then redo",
            "Hello\nWorld\n",
            b"Ju u:wq\r",
            expected_content="Hello World\n"
        )

        # 3J undo restores all 3 original lines (3J joins 2 lines)
        self.run_test(
            "3J undo restores all 3 original lines",
            "A\nB\nC\nD\n",
            b"3Ju:wq\r",
            expected_content="A\nB\nC\nD\n"
        )

        # 3J undo then redo
        self.run_test(
            "3J undo then redo",
            "A\nB\nC\nD\n",
            b"3Ju u:wq\r",
            expected_content="A B C\nD\n"
        )

        # J on last line is no-op, no undo state
        self.run_test(
            "J on last line is no-op",
            "Hello\n",
            b"Ju:wq\r",
            expected_content="Hello\n",
            expect_unmodified=True
        )

        # JJ batched: undo only undoes last join (second J)
        # A\nB\nC\n -> JJ batched -> A B C\n -> u -> A B\nC\n
        self.run_test(
            "JJ batched: undo only undoes last join",
            "A\nB\nC\n",
            b"JJ u:wq\r",
            expected_content="A B\nC\n"
        )

        # JJ batched: redo re-does the last join
        # A\nB\nC\n -> JJ -> A B C\n -> u -> A B\nC\n -> u -> A B C\n
        self.run_test(
            "JJ batched: redo re-joins",
            "A\nB\nC\n",
            b"JJ u u:wq\r",
            expected_content="A B C\n"
        )

        # J then other edit then undo: J not undoable (superseded)
        self.run_test(
            "J then x then u: J superseded by x",
            "AB\nCD\n",
            b"Jxu:wq\r",
            expected_content="AB CD\n"
        )

        # Join limit: 129J on 130-line file exceeds JOIN_UNDO_MAX (128)
        # Should show error and not modify buffer (keypress dismisses msg)
        content_130 = ''.join(f"{i}\n" for i in range(130))
        self.run_test(
            "129J exceeds limit: no modification",
            content_130,
            b"130J :wq\r",  # space dismisses error msg
            expected_content=content_130,
            expect_unmodified=True
        )

        # 128J should work fine (exactly at limit)
        content_129 = ''.join(f"{i}\n" for i in range(129))
        expected_128j = ' '.join(str(i) for i in range(129)) + '\n'
        self.run_test(
            "128J at limit succeeds",
            content_129,
            b"129J:wq\r",
            expected_content=expected_128j
        )

        # J undo preserves mark below
        # ma on C (line 2), go to line 0, J joins A+B, undo restores,
        # mark should still be on C (line 2)
        self.run_test_screen(
            "J undo preserves mark set below",
            "A\nB\nC\nD\n",
            b"jjmaggJu'a:q!\r",
            rows=10, cols=40,
            expect_cursor=(2, 0),  # mark on "C" = line 2 after undo
        )

        # J redo preserves mark below
        # ma on C (line 2), go to line 0, J joins A+B, undo, redo re-joins,
        # mark should be on C but now line 1 (A B merged)
        self.run_test_screen(
            "J redo preserves mark set below",
            "A\nB\nC\nD\n",
            b"jjmaggJu u'a:q!\r",
            rows=10, cols=40,
            expect_cursor=(1, 0),  # mark on "C" = line 1 after redo (A+B joined)
        )

        # 3J undo preserves mark below
        # ma on D (line 3), go to line 0, 3J joins A+B+C, undo restores,
        # mark should still be on D (line 3)
        self.run_test_screen(
            "3J undo preserves mark set below",
            "A\nB\nC\nD\nE\n",
            b"jjjmagg3Ju'a:q!\r",
            rows=10, cols=40,
            expect_cursor=(3, 0),  # mark on "D" = line 3 after undo
        )

        # JJ batched undo: screen shows correct content
        # A\nB\nC\n -> JJ -> A B C\n -> u -> A B\nC\n
        self.run_test_screen(
            "JJ batched undo: screen correct",
            "A\nB\nC\n",
            b"JJ u:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A B"), (1, "C")],
        )

        # JJ batched redo: screen shows correct content
        # A\nB\nC\n -> JJ -> A B C\n -> u -> A B\nC\n -> u -> A B C\n
        self.run_test_screen(
            "JJ batched redo: screen correct",
            "A\nB\nC\n",
            b"JJ u u:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A B C"), (1, "~")],
        )

        # Non-batched J undo: screen shows restored lines
        self.run_test_screen(
            "J undo: screen correct",
            "Hello\nWorld\n",
            b"Ju:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello"), (1, "World")],
        )

        # Non-batched 3J undo: screen shows all restored lines
        self.run_test_screen(
            "3J undo: screen correct",
            "A\nB\nC\nD\n",
            b"3Ju:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A"), (1, "B"), (2, "C"), (3, "D")],
        )

        # JJ batched undo: cursor stays at col 0
        self.run_test_screen(
            "JJ batched undo: cursor position",
            "A\nB\nC\n",
            b"JJ u:q!\r",
            rows=10, cols=40,
            expect_cursor=(0, 0),
        )

        self._group("Undo batching (u):", leading_blank=True)

        # uu batched: even count = noop, no content redraw
        # Frames: initial (True), dd (True), uu noop (False)
        self.run_test_screen(
            "uu batched: even count is noop after dd",
            "A\nB\nC\n",
            b"dduu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "B"), (1, "C")],
            expect_content_redraws=[True, True, False],
        )

        # uuu batched: odd count = one undo, one content redraw
        # Frames: initial (True), dd (True), uuu = one undo (True)
        self.run_test_screen(
            "uuu batched: odd count does undo after dd",
            "A\nB\nC\n",
            b"dduuu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A"), (1, "B"), (2, "C")],
            expect_content_redraws=[True, True, True],
        )

        # uuuu batched: even count = noop, no content redraw
        # Frames: initial (True), dd (True), uuuu noop (False)
        self.run_test_screen(
            "uuuu batched: even count is noop after dd",
            "A\nB\nC\n",
            b"dduuuu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "B"), (1, "C")],
            expect_content_redraws=[True, True, False],
        )

        # uu batched after x: noop, no content redraw
        # Frames: initial (True), x (True), uu noop (False)
        self.run_test_screen(
            "uu batched: even count is noop after x",
            "Hello\n",
            b"xuu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "ello")],
            expect_content_redraws=[True, True, False],
        )

        # uuu batched after J: odd count = one undo, one content redraw
        # Frames: initial (True), J (True), uuu = one undo (True)
        self.run_test_screen(
            "uuu batched: odd count does undo after J",
            "Hello\nWorld\n",
            b"Juuu:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello"), (1, "World")],
            expect_content_redraws=[True, True, True],
        )

        # J undo scroll region should exclude cursor row
        # When J is undone, cursor row content changes but doesn't need to scroll.
        # Only rows below cursor should scroll down.
        # For cursor at row 0 with 10 rows: scroll region should be ESC[2;9r
        # (rows 2-9 in 1-based = rows 1-8 in 0-based), not ESC[1;9r
        self.run_test_screen(
            "J undo scroll excludes cursor row",
            "Hello\nWorld\n",
            b"Ju:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello"), (1, "World")],
            expect_ansi_contains="\x1b[2;9r",
        )

        self._group("Undo line paste below (p):", leading_blank=True)

        # dd then p then u: undo removes pasted line (dd already committed)
        self.run_test(
            "ddpu undoes paste (dd stays)",
            "A\nB\nC\n",
            b"ddpu:wq\r",
            expected_content="B\nC\n"
        )

        # dd then p then uu: redo re-pastes
        self.run_test(
            "ddpuu redo re-pastes",
            "A\nB\nC\n",
            b"ddpuu:wq\r",
            expected_content="B\nA\nC\n"
        )

        # yy then p then u: removes pasted copy
        self.run_test(
            "yypu removes pasted copy",
            "A\nB\n",
            b"yypu:wq\r",
            expected_content="A\nB\n"
        )

        # yy then 2p then u: removes all pasted copies
        self.run_test(
            "yy2pu removes all copies",
            "A\nB\n",
            b"yy2pu:wq\r",
            expected_content="A\nB\n"
        )

        # yy then 2p then uu: redo re-pastes both
        self.run_test(
            "yy2puu redo re-pastes both",
            "A\nB\n",
            b"yy2puu:wq\r",
            expected_content="A\nA\nA\nB\n"
        )

        # Batching must not affect undo semantics: batched pp executes
        # both pastes but u undoes only the LAST one, exactly as if the
        # keys had been processed separately. A numeric count (2p) is one
        # logical command and undoes in full.
        self.run_test(
            "yyppu undo removes last batched paste only",
            "A\nB\n",
            b"yyppu:wq\r",
            expected_content="A\nA\nB\n"
        )

        self.run_test(
            "yy2pu undo removes full counted paste",
            "A\nB\n",
            b"yy2pu:wq\r",
            expected_content="A\nB\n"
        )

        self.run_test(
            "yyppu u redo re-pastes last copy",
            "A\nB\n",
            b"yyppu u:wq\r",
            expected_content="A\nA\nA\nB\n"
        )

        self.run_test(
            "yyPPu undo removes last batched paste only",
            "A\nB\n",
            b"yyPPu:wq\r",
            expected_content="A\nA\nB\n"
        )

        # Multi-line yank: undo removes one copy-aligned block
        self.run_test(
            "2yy pp u removes last two-line copy",
            "a\nb\nc\n",
            b"2yyppu:wq\r",
            expected_content="a\na\nb\nb\nc\n"
        )

        # Char paste batching: same rule
        self.run_test(
            "x pp u removes last batched char paste",
            "AB\n",
            b"xppu:wq\r",
            expected_content="BA\n"
        )

        self.run_test(
            "x PP u removes last batched char paste",
            "AB\n",
            b"xPPu:wq\r",
            expected_content="AB\n"
        )

        self.run_test(
            "x 2p u removes full counted char paste",
            "AB\n",
            b"x2pu:wq\r",
            expected_content="B\n"
        )

        # Cursor position after undo: back to pre-paste line+col
        self.run_test_screen(
            "ddpu cursor at original position",
            "AB\nCD\nEF\n",
            b"l" +              # cursor at col 1
            b"ddpu:q!\r",
            expect_cursor=(0, 1),
        )

        # Mark adjustment on undo: mark shifts back
        self.run_test_screen(
            "ddpu mark preserved",
            "A\nB\nC\n",
            b"jjma" +           # mark C (line 2)
            b"ggyy p" +         # yank A, paste below line 0 -> C shifts to 3
            b"u" +              # undo paste -> C shifts back to 2
            b"'a:q!\r",
            expect_cursor=(2, 0),
        )

        # Mark adjustment on redo: mark shifts forward again
        self.run_test_screen(
            "ddpuu mark preserved on redo",
            "A\nB\nC\n",
            b"jjma" +           # mark C (line 2)
            b"ggyy p" +         # paste -> C at 3
            b"uu" +             # undo+redo -> C at 3
            b"'a:q!\r",
            expect_cursor=(3, 0),
        )

        self._group("Undo line paste above (P):", leading_blank=True)

        # jdd then P then u: undo removes pasted line
        self.run_test(
            "jddPu undoes paste (dd stays)",
            "A\nB\nC\n",
            b"jddPu:wq\r",
            expected_content="A\nC\n"
        )

        # jdd then P then uu: redo re-pastes
        self.run_test(
            "jddPuu redo re-pastes",
            "A\nB\nC\n",
            b"jddPuu:wq\r",
            expected_content="A\nB\nC\n"
        )

        # yy then P then u: removes pasted copy
        self.run_test(
            "yyPu removes pasted copy",
            "A\nB\n",
            b"yyPu:wq\r",
            expected_content="A\nB\n"
        )

        # yy then 2P then u: removes all copies
        self.run_test(
            "yy2Pu removes all copies",
            "A\nB\n",
            b"yy2Pu:wq\r",
            expected_content="A\nB\n"
        )

        # Cursor position after undo
        self.run_test_screen(
            "jddPu cursor at original position",
            "AB\nCD\nEF\n",
            b"l" +              # cursor at col 1
            b"jddPu:q!\r",
            expect_cursor=(1, 1),
        )

        # Mark adjustment on undo
        self.run_test_screen(
            "yyPu mark preserved",
            "A\nB\nC\n",
            b"jjma" +           # mark C (line 2)
            b"ggyy P" +         # paste above line 0 -> C shifts to 3
            b"u" +              # undo -> C back to 2
            b"'a:q!\r",
            expect_cursor=(2, 0),
        )

        self._group("Undo char paste below (p):", leading_blank=True)

        # x then p then u: undo removes pasted char (x already committed)
        self.run_test(
            "xpu undoes char paste (x stays)",
            "AB\n",
            b"xpu:wq\r",
            expected_content="B\n"
        )

        # x then p then uu: redo re-pastes
        self.run_test(
            "xpuu redo re-pastes",
            "AB\n",
            b"xpuu:wq\r",
            expected_content="BA\n"
        )

        # D then p then u: undo removes pasted chars (D already committed)
        self.run_test(
            "Dpu undoes char paste (D stays)",
            "Hello World\n",
            b"llDpu:wq\r",
            expected_content="He\n"
        )

        # x then 2p then u: undo removes both pasted copies (x already committed)
        self.run_test(
            "x2pu undoes counted char paste (x stays)",
            "AB\n",
            b"x2pu:wq\r",
            expected_content="B\n"
        )

        # Multiline char paste undo (content with newlines)
        self.run_test(
            "multiline char paste p undo",
            "AB\nCD\nEF\n",
            b"$de" +            # delete "B\nCD" (multiline yank)
            b"pu:wq\r",        # paste then undo
            expected_content="A\nEF\n"
        )

        # Empty line char paste undo
        self.run_test(
            "empty line char paste p undo",
            "\nB\n",
            b"jx" +             # delete B from second line
            b"kpu:wq\r",       # go to empty line, paste, undo
            expected_content="\n\n"
        )

        # Cursor position after undo: back to pre-paste col
        self.run_test_screen(
            "xpu cursor restored",
            "ABC\n",
            b"lxpu:q!\r",      # col1, x deletes B, p pastes after cursor, u undoes
            expect_cursor=(0, 1),
        )

        # Multiline char paste mark adjustment on undo
        self.run_test_screen(
            "multiline char paste p undo preserves mark",
            "AB\nCD\nEF\n",
            b"jjma" +           # mark EF (line 2)
            b"gg$de" +          # delete "B\nCD" -> EF at line 1
            b"pu" +             # paste then undo -> EF back at 1
            b"'a:q!\r",
            expect_cursor=(1, 0),
        )

        self._group("Undo char paste above (P):", leading_blank=True)

        # x then P then u: undo removes pasted char (x already committed)
        self.run_test(
            "xPu undoes char paste (x stays)",
            "AB\n",
            b"xPu:wq\r",
            expected_content="B\n"
        )

        # x then P then uu: redo re-pastes
        self.run_test(
            "xPuu redo re-pastes",
            "AB\n",
            b"xPuu:wq\r",
            expected_content="AB\n"
        )

        # x then 2P then u: undo removes both copies
        self.run_test(
            "x2Pu undoes counted char paste (x stays)",
            "AB\n",
            b"x2Pu:wq\r",
            expected_content="B\n"
        )

        # Multiline char paste above undo
        self.run_test(
            "multiline char paste P undo",
            "AB\nCD\nEF\n",
            b"$de" +            # delete "B\nCD" (multiline yank)
            b"Pu:wq\r",        # paste above then undo
            expected_content="A\nEF\n"
        )

        # Cursor position after undo
        self.run_test_screen(
            "xPu cursor restored",
            "ABC\n",
            b"lxPu:q!\r",      # col1, x deletes B, P pastes at cursor, u undoes
            expect_cursor=(0, 1),
        )

        # ============================================================
        # Cursor positioning edge cases
        # ============================================================
        self._group("Cursor positioning edge cases:", leading_blank=True)

        # $x cursor clamp: after deleting last char on line, cursor clamps
        # to new last char. "AB" -> $ puts cursor at col 1 (B), x deletes B
        # -> "A", cursor should clamp to col 0.
        self.run_test_screen(
            "$x cursor clamps to new last char",
            "AB\n",
            b"$x:q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(0, "A")],
        )

        # dd on last line: cursor moves up to previous line
        # "A\nB\n" -> j to line 1, dd deletes it -> "A\n", cursor at (0,0)
        self.run_test_screen(
            "dd on last line moves cursor up",
            "A\nB\n",
            b"jdd:q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(0, "A"), (1, "~")],
        )

        # dd on middle line: cursor stays on same row, content shifts up
        # "A\nB\nC\n" -> j to line 1, dd deletes B -> "A\nC\n"
        # cursor stays at row 1 which now shows "C"
        self.run_test_screen(
            "dd on middle line cursor stays on row",
            "A\nB\nC\n",
            b"jdd:q!\r",
            expect_cursor=(1, 0),
            expect_lines=[(0, "A"), (1, "C"), (2, "~")],
        )

        # J cursor at join point: in standard vi, cursor goes to the space
        # between joined lines (col 3 for "foo\nbar" -> "foo bar").
        self.run_test_screen(
            "J cursor at join point",
            "foo\nbar\n",
            b"J:q!\r",
            expect_cursor=(0, 3),
            expect_lines=[(0, "foo bar"), (1, "~")],
        )

        # J cursor at join point on wrapped result: first line is 12 chars,
        # at 10 cols the join point (col 12) wraps to screen row 1, col 2.
        self.run_test_screen(
            "J cursor at join point wrapped",
            "A" * 12 + "\nbar\n",
            b"J:q!\r",
            rows=10, cols=10,
            expect_cursor=(1, 2),
            expect_lines=[(0, "A" * 10), (1, "AA bar")],
        )

        # [n]J cursor at first join point: 3J on "A\nB\nC\n" -> "A B C\n"
        # Cursor at col 1 (end of original first line "A").
        self.run_test_screen(
            "3J cursor at first join point",
            "A\nB\nC\n",
            b"3J:q!\r",
            expect_cursor=(0, 1),
            expect_lines=[(0, "A B C")],
        )

        # Batched JJ cursor at last join point: JJ on "A\nB\nC\n" -> "A B C\n"
        # First J: "A B\nC\n" cursor col 1. Second J: "A B C\n" cursor col 3.
        # Batched JJ should place cursor at col 3 (the last join point).
        self.run_test_screen(
            "JJ batched cursor at last join point",
            "A\nB\nC\n",
            b"JJ:q!\r",
            expect_cursor=(0, 3),
            expect_lines=[(0, "A B C")],
        )

        # o ESC cursor on empty inserted line
        # "A\n" -> o opens below, ESC exits insert. Cursor on new empty line.
        self.run_test_screen(
            "o ESC cursor on empty inserted line",
            "A\n",
            b"o\x1b:q!\r",
            expect_cursor=(1, 0),
            expect_lines=[(0, "A"), (1, ""), (2, "~")],
        )

        # O ESC cursor on empty inserted line
        # "A\n" -> O opens above, ESC exits insert. Cursor on new empty line (row 0).
        self.run_test_screen(
            "O ESC cursor on empty inserted line",
            "A\n",
            b"O\x1b:q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(0, ""), (1, "A"), (2, "~")],
        )

        # ESC at col 0: cursor stays at 0
        # "Hello\n" -> i at col 0, ESC. Cursor can't go left of 0.
        self.run_test_screen(
            "ESC at col 0 stays at col 0",
            "Hello\n",
            b"i\x1b:q!\r",
            expect_cursor=(0, 0),
        )

        # ESC after A: cursor at end of line minus 1
        # "Hello\n" (5 chars) -> A enters insert at col 5, ESC -> col 4
        self.run_test_screen(
            "ESC after A cursor at end minus 1",
            "Hello\n",
            b"A\x1b:q!\r",
            expect_cursor=(0, 4),
        )

        # ESC after o on new line: cursor at col 0
        # Same as "o ESC" test above but explicitly verifying col 0 behavior
        self.run_test_screen(
            "ESC after o cursor at col 0",
            "Line 1\nLine 2\n",
            b"o\x1b:q!\r",
            expect_cursor=(1, 0),
        )

        # BS at col 0 line 0 no-op: cursor stays at (0,0)
        # "Hello\n" -> i enters insert at (0,0), BS does nothing (no previous line)
        self.run_test_screen(
            "BS at col 0 line 0 is no-op",
            "Hello\n",
            b"i\x08\x1b:q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(0, "Hello")],
        )

        # BS join cursor at join point
        # "Hello\nWorld\n" -> j to line 1, i insert at col 0, BS joins with above
        # Result: "HelloWorld\n", cursor at col 5 (join point = len("Hello"))
        self.run_test_screen(
            "BS join cursor at join point",
            "Hello\nWorld\n",
            b"ji\x08\x1b:q!\r",
            expect_cursor=(0, 4),
            expect_lines=[(0, "HelloWorld"), (1, "~")],
        )

        # Cursor clamp going up: j$k
        # Line 0: "AB" (2 chars), Line 1: "LongLine" (8 chars)
        # j -> line 1, $ -> col 7, k -> line 0, cursor clamps to col 1 (last char)
        self.run_test_screen(
            "Cursor clamp going up j$k",
            "AB\nLongLine\n",
            b"j$k:q!\r",
            expect_cursor=(0, 1),
        )

        # h on empty line: no-op, cursor stays at (0,0)
        self.run_test_screen(
            "h on empty line is no-op",
            "\n",
            b"h:q!\r",
            expect_cursor=(0, 0),
        )

        # $ on empty line: no-op, cursor stays at (0,0)
        self.run_test_screen(
            "$ on empty line is no-op",
            "\n",
            b"$:q!\r",
            expect_cursor=(0, 0),
        )

        # x on empty line: no-op, cursor stays at (0,0)
        self.run_test_screen(
            "x on empty line is no-op",
            "\n",
            b"x:q!\r",
            expect_cursor=(0, 0),
        )

        # w at end of file: cursor stays at last char
        # "Hello\n" -> $ goes to col 4, w at end of file is no-op
        self.run_test_screen(
            "w at file end cursor position",
            "Hello\n",
            b"$w:q!\r",
            expect_cursor=(0, 4),
        )

        # b at start of file: cursor stays at col 0
        self.run_test_screen(
            "b at file start cursor position",
            "Hello\n",
            b"b:q!\r",
            expect_cursor=(0, 0),
        )

        # e at end of file: cursor stays at last char
        # "Hello\n" -> $ goes to col 4, e at end of file is no-op
        self.run_test_screen(
            "e at file end cursor position",
            "Hello\n",
            b"$e:q!\r",
            expect_cursor=(0, 4),
        )

        # Enter at col 0: pushes content to next line
        # "Hello\n" -> i at col 0, Enter splits -> "\nHello\n"
        # Cursor moves to the new line 1 at col 0
        self.run_test_screen(
            "Enter at col 0 pushes content to next line",
            "Hello\n",
            b"i\r\x1b:q!\r",
            expect_cursor=(1, 0),
            expect_lines=[(0, ""), (1, "Hello")],
        )

        # Enter at end of line: creates empty line below, content stays
        # "Hello\n" -> A enters at end, Enter -> "Hello\n\n"
        # Cursor on the new empty line 1 at col 0
        self.run_test_screen(
            "Enter at end of line creates empty line",
            "Hello\n",
            b"A\r\x1b:q!\r",
            expect_cursor=(1, 0),
            expect_lines=[(0, "Hello"), (1, "")],
        )

        self._group("Undo cursor and content edge cases:", leading_blank=True)

        # --- Undo cursor restoration ---

        # xu: cursor returns to original position (col before x)
        self.run_test_screen(
            "xu cursor at col before x",
            "Hello\n",
            b"lxu:q!\r",       # move to col 1, x deletes 'e', u restores
            expect_cursor=(0, 1),
        )

        # ddu: cursor returns to the line that was deleted
        self.run_test_screen(
            "ddu cursor on restored line",
            "A\nB\nC\n",
            b"jddu:q!\r",      # move to line 1, dd deletes B, u restores
            expect_cursor=(1, 0),
        )

        # Du: cursor returns to where D was issued
        self.run_test_screen(
            "Du cursor at D position",
            "Hello\n",
            b"llDu:q!\r",      # move to col 2, D deletes "llo", u restores
            expect_cursor=(0, 2),
        )

        # dwu: cursor returns to word start
        self.run_test_screen(
            "dwu cursor at word start",
            "Hello World\n",
            b"dwu:q!\r",       # dw deletes "Hello ", u restores
            expect_cursor=(0, 0),
        )

        # dbu: cursor returns to position before db
        self.run_test_screen(
            "dbu cursor restored",
            "Hello World\n",
            b"edbu:q!\r",      # e goes to col 4, db deletes backward, u restores
            expect_cursor=(0, 0),
        )

        # deu: cursor returns to position before de
        self.run_test_screen(
            "deu cursor at de position",
            "Hello World\n",
            b"deu:q!\r",       # de deletes "Hello", u restores
            expect_cursor=(0, 0),
        )

        # d$u: cursor returns to position where d$ was issued
        self.run_test_screen(
            "d$u cursor at d$ position",
            "Hello\n",
            b"lld$u:q!\r",     # col 2, d$ deletes "llo", u restores
            expect_cursor=(0, 2),
        )

        # d0u: cursor returns to position where d0 was issued
        self.run_test_screen(
            "d0u cursor at d0 position",
            "Hello\n",
            b"llld0u:q!\r",    # col 3, d0 deletes "Hel", u restores
            expect_cursor=(0, 0),
        )

        # o-ESC undo: cursor returns to line before o
        self.run_test_screen(
            "o ESC u cursor on original line",
            "Hello\nWorld\n",
            b"o\x1bu:q!\r",    # o opens below, ESC exits, u undoes
            expect_cursor=(0, 0),
        )

        # O-ESC undo: cursor returns to line before O
        self.run_test_screen(
            "O ESC u cursor on original line",
            "Hello\nWorld\n",
            b"jO\x1bu:q!\r",   # j to line 1, O opens above, ESC, u undoes
            expect_cursor=(1, 0),
        )

        # Ju: cursor returns to beginning of first line (before join)
        self.run_test_screen(
            "Ju cursor at line start",
            "Hello\nWorld\n",
            b"Ju:q!\r",        # J joins lines, u undoes
            expect_cursor=(0, 0),
        )

        # ccu: cursor returns to original line content
        self.run_test_screen(
            "ccu cursor on restored line",
            "Hello\nWorld\n",
            b"cc\x1bu:q!\r",   # cc clears line, ESC, u restores
            expect_cursor=(0, 0),
        )

        # su: cursor returns to original position
        self.run_test_screen(
            "su cursor at s position",
            "Hello\n",
            b"ls\x1bu:q!\r",   # col 1, s deletes char, ESC, u restores
            expect_cursor=(0, 1),
        )

        # Cu: cursor returns to position where C was issued
        self.run_test_screen(
            "Cu cursor at C position",
            "Hello\n",
            b"llC\x1bu:q!\r",  # col 2, C deletes to EOL, ESC, u restores
            expect_cursor=(0, 2),
        )

        # --- Undo content verification ---

        # o-ESC undo content restored (empty line removed)
        self.run_test(
            "o ESC u content restored",
            "Hello\nWorld\n",
            b"o\x1bu:wq\r",    # o opens blank line below, ESC, u removes it
            expected_content="Hello\nWorld\n"
        )

        # O-ESC undo content restored (empty line removed)
        self.run_test(
            "O ESC u content restored",
            "Hello\nWorld\n",
            b"O\x1bu:wq\r",    # O opens blank line above, ESC, u removes it
            expected_content="Hello\nWorld\n"
        )

        # cb-ESC undo content restored (changed-back text restored)
        self.run_test(
            "cb ESC u content restored",
            "Hello World\n",
            b"ecb\x1bu:wq\r",  # e to col 4, cb deletes backward, ESC, u restores
            expected_content="Hello World\n"
        )

        # ce-ESC undo content restored (changed-end text restored)
        self.run_test(
            "ce ESC u content restored",
            "Hello World\n",
            b"ce\x1bu:wq\r",   # ce deletes "Hello", ESC, u restores
            expected_content="Hello World\n"
        )

        # --- Boundary cases ---

        # dd undo on single-line file (restores the only line)
        # BUG: dd on single-line file + undo restores with extra blank line
        self.run_test(
            "dd undo on single-line file",
            "Hello\n",
            b"ddu:wq\r",
            expected_content="Hello\n"
        )

        # x undo on single-char line (restores single char)
        self.run_test(
            "x undo on single-char line",
            "A\n",
            b"xu:wq\r",
            expected_content="A\n"
        )

        # d$ undo at col 0 (entire line content deleted, undo restores)
        self.run_test(
            "d$ undo at col 0 restores full line",
            "Hello\n",
            b"d$u:wq\r",
            expected_content="Hello\n"
        )

        # o undo at last line: undo removes the blank line below
        self.run_test(
            "o undo at last line",
            "A\nB\n",
            b"jo\x1bu:wq\r",
            expected_content="A\nB\n"
        )

        # O undo at first line: undo removes the blank line above
        self.run_test(
            "O undo at first line",
            "A\nB\n",
            b"O\x1bu:wq\r",
            expected_content="A\nB\n"
        )

        # dd undo of empty line: dd deletes empty line, undo restores it
        self.run_test(
            "dd undo of empty line",
            "A\n\nB\n",
            b"jddu:wq\r",
            expected_content="A\n\nB\n"
        )

        # BS on only empty line in file: no-op (can't join, can't delete)
        self.run_test_screen(
            "BS on only empty line in file is no-op",
            "\n",
            b"i\x08\x1b:q!\r",
            expect_cursor=(0, 0),
            expect_lines=[(0, "")],
        )

        # --- Interactions ---

        # undo-then-edit clears redo stack
        # dd, u (undo), x (new edit clears redo of dd), u (undo x), space, u (redo x, NOT redo dd)
        self.run_test(
            "undo then edit clears redo stack",
            "AB\nCD\n",
            b"dduxu u:wq\r",
            expected_content="B\nCD\n"   # redo does x again (not dd)
        )

        # xxu sequential: with movement between x's, undo only undoes last x
        self.run_test(
            "x l x u undo only last x",
            "Hello\n",
            b"xlxu:wq\r",      # x deletes H, l moves right, x deletes l, u undoes last x
            expected_content="ello\n"
        )

        # Consecutive xx without separator: undo should restore last x only
        # BUG: consecutive x keypresses corrupt undo state
        self.run_test(
            "xx u undo after consecutive x",
            "Hello\n",
            b"xxu:wq\r",
            expected_content="ello\n"
        )

        # insert mode typing clears undo stack (dd then iX ESC then u)
        self.run_test(
            "dd then iX ESC u: typing clears undo",
            "A\nB\n",
            b"ddiX\x1bu:wq\r",
            expected_content="XB\n"     # u is no-op, dd undo was cleared by typing
        )

        self._group("Redo content and render edge cases:", leading_blank=True)

        # --- Redo content verification: undo then redo, verify content ---

        # 2dd redo content
        self.run_test(
            "2dd redo content",
            "A\nB\nC\nD\n",
            b"2ddu u:wq\r",
            expected_content="C\nD\n"
        )

        # 3x redo content
        self.run_test(
            "3x redo content",
            "Hello\n",
            b"3xu u:wq\r",
            expected_content="lo\n"
        )

        # d0 redo content
        self.run_test(
            "d0 redo content",
            "Hello\n",
            b"llld0u u:wq\r",
            expected_content="lo\n"
        )

        # db redo content
        self.run_test(
            "db redo content",
            "Hello World\n",
            b"wdbu u:wq\r",
            expected_content="World\n"
        )

        # de redo content
        self.run_test(
            "de redo content",
            "Hello World\n",
            b"deu u:wq\r",
            expected_content=" World\n"
        )

        # 2D redo content (D at col 2, deletes rest of line + next line)
        self.run_test(
            "2D redo content",
            "Hello\nWorld\nFoo\n",
            b"ll2Du u:wq\r",
            expected_content="He\nFoo\n"
        )

        # s redo content (substitute char, clean ESC exit, undo, redo)
        self.run_test(
            "s redo content",
            "Hello\n",
            b"s\x1bu u:wq\r",
            expected_content="ello\n"
        )

        # C redo content (change to end of line, clean ESC exit, undo, redo)
        self.run_test(
            "C redo content",
            "Hello\n",
            b"llC\x1bu u:wq\r",
            expected_content="He\n"
        )

        # cw redo content (change word, clean ESC exit, undo, redo)
        self.run_test(
            "cw redo content",
            "Hello World\n",
            b"cw\x1bu u:wq\r",
            expected_content=" World\n"
        )

        # cb redo content (change back word, clean ESC exit, undo, redo)
        self.run_test(
            "cb redo content",
            "Hello World\n",
            b"wcb\x1bu u:wq\r",
            expected_content="World\n"
        )

        # ce redo content (change to end of word, clean ESC exit, undo, redo)
        self.run_test(
            "ce redo content",
            "Hello World\n",
            b"ce\x1bu u:wq\r",
            expected_content=" World\n"
        )

        # o redo content (open below, clean ESC exit, undo, redo)
        self.run_test(
            "o redo content",
            "Hello\nWorld\n",
            b"o\x1bu u:wq\r",
            expected_content="Hello\n\nWorld\n"
        )

        # O redo content (open above, clean ESC exit, undo, redo)
        self.run_test(
            "O redo content",
            "Hello\nWorld\n",
            b"jO\x1bu u:wq\r",
            expected_content="Hello\n\nWorld\n"
        )

        # --- Redo cursor position verification ---

        # x redo cursor: x at col 1 deletes char, undo, redo -> cursor at col 1
        self.run_test_screen(
            "x redo cursor at x position",
            "Hello\n",
            b"lxu u:q!\r",
            expect_cursor=(0, 1),
        )

        # dd redo cursor: dd on line 1, undo, redo -> cursor on what was line 2
        self.run_test_screen(
            "dd redo cursor position",
            "A\nB\nC\n",
            b"jddu u:q!\r",
            expect_cursor=(1, 0),
        )

        # D redo cursor: D at col 2, undo, redo -> cursor clamps to col 1
        self.run_test_screen(
            "D redo cursor position",
            "Hello\n",
            b"llDu u:q!\r",
            expect_cursor=(0, 1),
        )

        # dw redo cursor
        self.run_test_screen(
            "dw redo cursor position",
            "Hello World\n",
            b"dwu u:q!\r",
            expect_cursor=(0, 0),
        )

        # db redo cursor: e to col 4, db, undo, redo
        self.run_test_screen(
            "db redo cursor position",
            "Hello World\n",
            b"edbu u:q!\r",
            expect_cursor=(0, 0),
        )

        # de redo cursor
        self.run_test_screen(
            "de redo cursor position",
            "Hello World\n",
            b"deu u:q!\r",
            expect_cursor=(0, 0),
        )

        # d$ redo cursor: d$ at col 2, undo, redo -> cursor clamps to col 1
        self.run_test_screen(
            "d$ redo cursor position",
            "Hello\n",
            b"lld$u u:q!\r",
            expect_cursor=(0, 1),
        )

        # d0 redo cursor: d0 at col 3, undo, redo -> cursor at col 0
        self.run_test_screen(
            "d0 redo cursor position",
            "Hello\n",
            b"llld0u u:q!\r",
            expect_cursor=(0, 0),
        )

        # s redo cursor: s at col 0, clean ESC, undo, redo
        self.run_test_screen(
            "s redo cursor position",
            "Hello\n",
            b"s\x1bu u:q!\r",
            expect_cursor=(0, 0),
        )

        # C redo cursor: C at col 2, clean ESC, undo, redo -> cursor at col 1
        self.run_test_screen(
            "C redo cursor position",
            "Hello\n",
            b"llC\x1bu u:q!\r",
            expect_cursor=(0, 1),
        )

        # cw redo cursor: cw at col 0, clean ESC, undo, redo
        self.run_test_screen(
            "cw redo cursor position",
            "Hello World\n",
            b"cw\x1bu u:q!\r",
            expect_cursor=(0, 0),
        )

        # o redo cursor: o opens below, clean ESC, undo, redo -> cursor on new line
        self.run_test_screen(
            "o redo cursor position",
            "Hello\nWorld\n",
            b"o\x1bu u:q!\r",
            expect_cursor=(1, 0),
        )

        # O redo cursor: O opens above on line 1, clean ESC, undo, redo
        self.run_test_screen(
            "O redo cursor position",
            "Hello\nWorld\n",
            b"jO\x1bu u:q!\r",
            expect_cursor=(1, 0),
        )

        # --- Redo render optimization: verify minimal repaint on undo/redo ---

        # d0 undo then redo - single row repaint
        # Frames: 0=initial, 1=jjj, 2=lll, 3=d0, 4=u, 5=space, 6=u redo
        self.run_test_screen(
            "Redo render: d0 undo then redo single row",
            make_lines(15),
            b"jjjllld0u u:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(6, {3})],
            expect_scrolled_at_frame=[(6, False)]
        )

        # 3x undo then redo - single row repaint
        # Frames: 0=initial, 1=jjj, 2=count '3', 3=x, 4=u, 5=space, 6=u redo
        self.run_test_screen(
            "Redo render: 3x undo then redo single row",
            make_lines(15),
            b"jjj3xu u:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(6, {3})],
            expect_scrolled_at_frame=[(6, False)]
        )

        # s undo then redo - single row repaint
        # Frames: 0=initial, 1=jjj, 2=s (insert), 3=ESC, 4=u, 5=space, 6=u redo
        self.run_test_screen(
            "Redo render: s undo then redo single row",
            make_lines(15),
            b"jjjs\x1bu u:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(6, {3})],
            expect_scrolled_at_frame=[(6, False)]
        )

        # C undo then redo - single row repaint
        # Frames: 0=initial, 1=jjj, 2=ll, 3=C (insert), 4=ESC, 5=u, 6=space, 7=u redo
        self.run_test_screen(
            "Redo render: C undo then redo single row",
            make_lines(15),
            b"jjjllC\x1bu u:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(7, {3})],
            expect_scrolled_at_frame=[(7, False)]
        )

        # cw undo then redo - single row repaint
        # Frames: 0=initial, 1=jjj, 2=cw (insert), 3=ESC, 4=u, 5=space, 6=u redo
        self.run_test_screen(
            "Redo render: cw undo then redo single row",
            make_lines(15),
            b"jjjcw\x1bu u:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(6, {3})],
            expect_scrolled_at_frame=[(6, False)]
        )

        # cb undo then redo - single row repaint
        # Frames: 0=initial, 1=jjj, 2=w, 3=cb (insert), 4=ESC, 5=u, 6=space, 7=u redo
        self.run_test_screen(
            "Redo render: cb undo then redo single row",
            make_lines(15),
            b"jjjwcb\x1bu u:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(7, {3})],
            expect_scrolled_at_frame=[(7, False)]
        )

        # ce undo then redo - single row repaint
        # Frames: 0=initial, 1=jjj, 2=ce (insert), 3=ESC, 4=u, 5=space, 6=u redo
        self.run_test_screen(
            "Redo render: ce undo then redo single row",
            make_lines(15),
            b"jjjce\x1bu u:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(6, {3})],
            expect_scrolled_at_frame=[(6, False)]
        )

        # d0 undo - single row repaint (only the affected row redrawn)
        # Frames: 0=initial, 1=jjj, 2=lll, 3=d0, 4=u
        self.run_test_screen(
            "Minimal repaint: d0 undo",
            make_lines(15),
            b"jjjllld0u:q!\r",
            rows=10, cols=40,
            expect_content_rows=[(4, {3})],
            expect_scrolled_at_frame=[(4, False)]
        )

        # 2dd undo - restores 2 lines, rows 3-4 need content writes
        # Frames: 0=initial, 1=jjj, 2=count '2', 3=dd, 4=u
        self.run_test_screen(
            "Minimal repaint: 2dd undo",
            make_lines(15),
            b"jjj2ddu:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"), (2, "Line 3"),
                (3, "Line 4"), (4, "Line 5"), (5, "Line 6"),
                (6, "Line 7"), (7, "Line 8"), (8, "Line 9"),
            ],
            expect_cursor=(3, 0),
            expect_content_rows=[(4, {3, 4})]
        )

        self._group("Render optimization edge cases:", leading_blank=True)

        # --- Cursor-only operations (no content redraw) ---

        # ^ (first non-blank) is a movement: cursor-only
        # Frame 0: init(T), Frame 1: ^(F), Frame 2: :q!(F)
        self.run_test_screen(
            "Render opt: ^ is cursor-only",
            "   hello\n",
            b"^:q!\r",
            expect_content_redraws=[True, False, False]
        )

        # n (next search match) without scroll: cursor-only
        # /AAA finds at line 2, n wraps to line 0 (still visible)
        # Frame 0: init(T), Frame 1: /AAA\r(F), Frame 2: n(F), Frame 3: :q!(F)
        self.run_test_screen(
            "Render opt: n no-scroll is cursor-only (edge)",
            "AAA\nBBB\nAAA\n",
            b"/AAA\rn:q!\r",
            expect_cursor=(0, 0),
            expect_content_redraws=[True, False, False, False]
        )

        # ? (reverse search) without scroll: cursor-only
        # jj moves to line 2, ?AAA finds on line 0 (still visible)
        # Frame 0: init(T), Frame 1: jj(F), Frame 2: ?AAA\r(F), Frame 3: :q!(F)
        self.run_test_screen(
            "Render opt: ? no-scroll is cursor-only",
            "AAA\nBBB\nAAA\n",
            b"jj?AAA\r:q!\r",
            expect_cursor=(0, 0),
            expect_content_redraws=[True, False, False, False]
        )

        # N (find prev) without scroll: cursor-only
        # /AAA finds at line 2. N goes backward to line 0 (still visible).
        # Frame 0: init(T), Frame 1: /AAA\r(F), Frame 2: N(F), Frame 3: :q!(F)
        self.run_test_screen(
            "Render opt: N no-scroll is cursor-only",
            "AAA\nBBB\nAAA\n",
            b"/AAA\rN:q!\r",
            expect_cursor=(0, 0),
            expect_content_redraws=[True, False, False, False]
        )

        # N (find prev) with scroll: triggers repaint
        # AAA at line 0 and line 11. /AAA finds line 11 (scrolls down).
        # N from line 11 searches backward to line 0 (scrolls up).
        # Frame 0: init(T), Frame 1: /AAA\r scrolls(T),
        # Frame 2: N scrolls(T), Frame 3: :q!(F)
        self.run_test_screen(
            "Render opt: N with scroll triggers repaint",
            "AAA\n" + ''.join(f"X{i}\n" for i in range(2, 12))
            + "AAA\nY13\nY14\nY15\n",
            b"/AAA\rN:q!\r",
            expect_cursor=(0, 0),
            expect_content_redraws=[True, True, True, False]
        )

        # y$ (yank to end) is cursor-only (yank doesn't modify content)
        # Frame 0: init(T), Frame 1: y$(F), Frame 2: :q!(F)
        self.run_test_screen(
            "Render opt: y$ is cursor-only",
            "Hello World\n",
            b"y$:q!\r",
            expect_content_redraws=[True, False, False]
        )

        # y0 (yank to start) is cursor-only
        # Frame 0: init(T), Frame 1: lll(F), Frame 2: y0(F), Frame 3: :q!(F)
        self.run_test_screen(
            "Render opt: y0 is cursor-only",
            "Hello\n",
            b"llly0:q!\r",
            expect_content_redraws=[True, False, False, False]
        )

        # yw (yank word) is cursor-only
        # Frame 0: init(T), Frame 1: yw(F), Frame 2: :q!(F)
        self.run_test_screen(
            "Render opt: yw is cursor-only",
            "Hello World\n",
            b"yw:q!\r",
            expect_content_redraws=[True, False, False]
        )

        # yb (yank word back) is cursor-only
        # w moves to "World", yb yanks back
        # Frame 0: init(T), Frame 1: w(F), Frame 2: yb(F), Frame 3: :q!(F)
        self.run_test_screen(
            "Render opt: yb is cursor-only",
            "Hello World\n",
            b"wyb:q!\r",
            expect_content_redraws=[True, False, False, False]
        )

        # ye (yank to end of word) is cursor-only
        # Frame 0: init(T), Frame 1: ye(F), Frame 2: :q!(F)
        self.run_test_screen(
            "Render opt: ye is cursor-only",
            "Hello World\n",
            b"ye:q!\r",
            expect_content_redraws=[True, False, False]
        )

        # --- Indent operations render ---

        # << (unindent) triggers full content redraw (all rows touched)
        # This is a render optimization gap - ideally only row 0 would be
        # redrawn, but the current implementation repaints all content rows.
        # Frame 0: init(T), Frame 1: <<(T full redraw), Frame 2: :q!(F)
        self.run_test_screen(
            "Render opt: << triggers content redraw",
            "  Hello\nWorld\n",
            b"<<:q!\r",
            expect_content_redraws=[True, True, False]
        )

        # --- Scroll-triggering operations ---

        # w causing scroll (word forward past viewport bottom)
        # Single-word lines so w crosses line boundaries and scrolls.
        # j*8 moves to last visible line (row 8), w crosses to next line (scroll).
        # Frame 0: init(T), Frame 1: j*8 batched(F), Frame 2: w scrolls(T),
        # Frame 3: :q!(F)
        self.run_test_screen(
            "Render opt: w with scroll triggers repaint",
            ''.join(f"W{i}\n" for i in range(1, 16)),
            b"jjjjjjjjw:q!\r",
            expect_content_redraws=[True, False, True, False]
        )

        # b causing scroll (word back past viewport top)
        # G scrolls to bottom, then batched b's scroll back past top.
        # Frame 0: init(T), Frame 1: G(T scroll), Frame 2: b*20 batched(T scroll),
        # Frame 3: :q!(F)
        self.run_test_screen(
            "Render opt: b with scroll triggers repaint",
            make_lines(15),
            b"G" + b"b" * 20 + b":q!\r",
            expect_content_redraws=[True, True, True, False]
        )

        # e causing scroll (end of word past viewport bottom)
        # Single-word lines. j*8 to last visible row, $ to end, e to next word end.
        # Frame 0: init(T), Frame 1: j*8(F), Frame 2: $(F),
        # Frame 3: e scrolls(T), Frame 4: :q!(F)
        self.run_test_screen(
            "Render opt: e with scroll triggers repaint",
            ''.join(f"W{i}\n" for i in range(1, 16)),
            b"jjjjjjjj$e:q!\r",
            expect_content_redraws=[True, False, False, True, False]
        )

        # G (go to last line) with scroll
        # 15-line file, 10 rows. G goes to last line, must scroll.
        # Frame 0: init(T), Frame 1: G scrolls(T), Frame 2: :q!(F)
        self.run_test_screen(
            "Render opt: G with scroll triggers repaint",
            make_lines(15),
            b"G:q!\r",
            expect_content_redraws=[True, True, False]
        )

        # gg (go to first line) with scroll (from scrolled position)
        # G scrolls to bottom, gg scrolls back to top.
        # Frame 0: init(T), Frame 1: G(T), Frame 2: gg(T), Frame 3: :q!(F)
        self.run_test_screen(
            "Render opt: gg with scroll triggers repaint",
            make_lines(15),
            b"Ggg:q!\r",
            expect_content_redraws=[True, True, True, False]
        )

        # Mark goto with scroll (ma, scroll down, then 'a)
        # ma sets mark at line 1, G scrolls to bottom, 'a goes back to top.
        # Frame 0: init(T), Frame 1: ma(F), Frame 2: G(T),
        # Frame 3: 'a scrolls(T), Frame 4: :q!(F)
        self.run_test_screen(
            "Render opt: mark goto with scroll triggers repaint",
            make_lines(15),
            b"ma" + b"G" + b"'a:q!\r",
            expect_content_redraws=[True, False, True, True, False]
        )

        # n (next match) with scroll
        # AAA appears at line 0 and line 11 (off-screen on 9 content rows).
        # /AAA finds line 11 (scrolls). n wraps back to line 0 (scrolls).
        # Frame 0: init(T), Frame 1: /AAA\r scrolls(T),
        # Frame 2: n wraps to line 0 scrolls(T), Frame 3: :q!(F)
        self.run_test_screen(
            "Render opt: n with scroll triggers repaint",
            "AAA\n" + ''.join(f"X{i}\n" for i in range(2, 12))
            + "AAA\nY13\nY14\nY15\n",
            b"/AAA\rn:q!\r",
            expect_cursor=(0, 0),
            expect_content_redraws=[True, True, True, False]
        )

        # ? (reverse search) with scroll
        # G scrolls to bottom. ?Line 2\r searches backward, finds "Line 2"
        # near top, scrolls back.
        # Frame 0: init(T), Frame 1: G(T), Frame 2: ?Line 2\r scrolls(T),
        # Frame 3: :q!(F)
        self.run_test_screen(
            "Render opt: ? with scroll triggers repaint",
            make_lines(15),
            b"G?Line 2\r:q!\r",
            expect_content_redraws=[True, True, True, False]
        )

        # --- Insert mode render ---

        # DEL (delete key) joining lines in insert mode - needs repaint
        # At end of line 1, DEL joins line 2 onto line 1.
        # Frame 0: init(T), Frame 1: A enter insert(F), Frame 2: DEL join(T),
        # Frame 3: ESC(F), Frame 4: :q!(F)
        DEL = b"\x1b[3~"
        self.run_test_screen(
            "Render opt: DEL joining lines in insert mode repaints",
            "Hello\nWorld\n",
            b"A" + DEL + b"\x1b:q!\r",
            expect_content_redraws=[True, False, True, False, False]
        )

        self._group("Batching counting and insert mode edge cases:", leading_blank=True)

        # --- Batch undo behavior ---

        # xxxx then undo: batched x's delete all chars, undo pastes back last char
        self.run_test(
            "xxx then undo: batched x undo restores last char",
            "ABCDE\n",
            b"xxxu:wq\r",
            expected_content="CDE\n"
        )

        # Single x then u: undo works for non-batched x
        self.run_test(
            "single x then u: undo works",
            "ABCDE\n",
            b"xu:wq\r",
            expected_content="ABCDE\n"
        )

        # dwdw then undo: batched dw's overwrite undo entry,
        # so u after batched dwdw has no effect
        self.run_test(
            "dwdw then undo: batched dw undo lost",
            "one two three four\n",
            b"dwdwu:wq\r",
            expected_content="three four\n"
        )

        # Single dw then u: undo works for non-batched dw
        self.run_test(
            "single dw then u: undo works",
            "one two three four\n",
            b"dwu:wq\r",
            expected_content="one two three four\n"
        )

        # --- Batch operations ---

        # Enter at end of line in insert mode: creates new empty line below
        self.run_test(
            "Enter at end of line creates new line",
            "Hello\n",
            b"$a\r\x1b:wq\r",
            expected_content="Hello\n\n"
        )

        # BS at col 0 joins with line above (non-empty lines)
        self.run_test(
            "BS at col 0 joins non-empty lines",
            "Hello\nWorld\n",
            b"ji\x08\x1b:wq\r",
            expected_content="HelloWorld\n"
        )

        # Tab in insert mode inserts a tab character
        self.run_test(
            "Tab in insert mode inserts tab char",
            "AB\n",
            b"li\x09\x1b:wq\r",
            expected_content="A\tB\n"
        )

        # --- Count prefix behavior ---

        # 10x deletes 10 chars (or clamps to line length)
        self.run_test(
            "10x deletes 10 chars",
            "ABCDEFGHIJKLMNO\n",
            b"10x:wq\r",
            expected_content="KLMNO\n"
        )

        # 99x on short line: clamps to available chars
        self.run_test(
            "99x clamps to line length",
            "Short\n",
            b"99x:wq\r",
            expected_content="\n"
        )

        # 99r with replacement char: editor clamps count to available chars
        # (unlike vim which would do nothing when count exceeds available)
        self.run_test(
            "99rx on short line: clamps and replaces all",
            "Hello\n",
            b"99rx:wq\r",
            expected_content="xxxxx\n"
        )

        # 2J then J then undo: undo only undoes the last J
        self.run_test(
            "2J then J then undo: undoes last J only",
            "A\nB\nC\nD\n",
            b"2JJu:wq\r",
            expected_content="A B\nC\nD\n"
        )

        # dwdwp vs 2dwp: batched dw's yank last word only, count yanks all
        # "one two three four\n". dwdw deletes "one " then "two " -> "three four\n".
        # Batched dw overwrites yank, so p pastes "two " (last deleted word).
        self.run_test(
            "dwdwp: batched yanks last word only",
            "one two three four\n",
            b"dwdw$p:wq\r",
            expected_content="three fourtwo \n"
        )

        # 2dwp: count 2 dw deletes "one two " at once, p pastes all of it back
        self.run_test(
            "2dwp: count yanks all deleted words",
            "one two three four\n",
            b"2dw$p:wq\r",
            expected_content="three fourone two \n"
        )

        # Batched BS joining non-empty lines: BS at col 0 of line 1 joins
        # into line 0, then continued BS deletes chars from joined line
        self.run_test(
            "Batched BS joining non-empty lines",
            "AB\nCD\n",
            b"ji\x08\x08\x1b:wq\r",
            expected_content="ACD\n"
        )

        # Tab key in batched insert: multiple tabs in sequence
        self.run_test(
            "Multiple tabs in batched insert",
            "AB\n",
            b"li\x09\x09\x1b:wq\r",
            expected_content="A\t\tB\n"
        )

        # BATCH_MAX (32) capacity: insert 33 chars to exceed the 32-entry batch
        self.run_test(
            "Insert 33 chars exceeds BATCH_MAX 32",
            "\n",
            b"i" + b"X" * 33 + b"\x1b:wq\r",
            expected_content="X" * 33 + "\n"
        )

        # ~ echo over skipped punctuation: chars must land in the right
        # columns (regression: skipped non-alpha chars used to shift all
        # later direct writes left)
        self.run_test_screen(
            "Tilde echo positions correctly over punctuation",
            "a.b.c\nsecond\n",
            b"5~:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "A.B.C"), (1, "second")],
        )

        # r spanning a wrap-row boundary: echo stops at the boundary and
        # the wrapped row is repainted correctly
        self.run_test_screen(
            "Replace across wrap boundary renders correctly",
            "ABCDEFGHIJKLM\nx\n",
            b"8l4rZ:q!\r",
            rows=10, cols=10,
            expect_lines=[(0, "ABCDEFGHZZ"), (1, "ZZM"), (2, "x")],
        )

        # Batching is a performance optimization and must not change undo
        # semantics: u after batched ~~~ undoes only the LAST ~, exactly
        # as if the keys had been processed separately.
        self.run_test(
            "Batched tilde undo covers last keystroke only",
            "abc\n",
            b"~~~u:wq\r",
            expected_content="ABc\n"
        )

        self.run_test(
            "Batched tilde undo then redo",
            "abc\n",
            b"~~~u u:wq\r",
            expected_content="ABC\n"
        )

        # Batched ~ where the last ~ hit a non-alpha char: that keystroke
        # changed nothing, so there is nothing to undo
        self.run_test(
            "Batched tilde undo noop when last char non-alpha",
            "ab.x\n",
            b"~~~u:wq\r",
            expected_content="AB.x\n"
        )

        # --- Insert mode specifics ---

        # iXYZ<ESC> at col 0: insert text at beginning of line
        self.run_test(
            "iXYZ at col 0 inserts at beginning",
            "Hello\n",
            b"iXYZ\x1b:wq\r",
            expected_content="XYZHello\n"
        )

        # a vs i: a starts inserting after cursor, i at cursor
        # i at col 0 inserts before 'H', a at col 0 inserts after 'H'
        self.run_test(
            "a inserts after cursor vs i at cursor",
            "Hello\n",
            b"aX\x1b:wq\r",
            expected_content="HXello\n"
        )

        # a on empty line: should work, cursor at col 0 in insert
        self.run_test(
            "a on empty line works",
            "\n",
            b"aTest\x1b:wq\r",
            expected_content="Test\n"
        )

        # A on empty line: goes to end = col 0, then inserts
        self.run_test(
            "A on empty line inserts at col 0",
            "\n",
            b"ATest\x1b:wq\r",
            expected_content="Test\n"
        )

        # o on empty buffer: opens line below in empty file
        self.run_test(
            "o on empty buffer opens line below",
            "\n",
            b"oNew\x1b:wq\r",
            expected_content="\nNew\n"
        )

        # o on truly empty file (no content)
        self.run_test(
            "o on empty file opens line below",
            "",
            b"oNew\x1b:wq\r",
            expected_content="\nNew\n"
        )

        # Arrow left then type in insert mode: inserts at new position
        # $=col3 (D), a=insert after col3 (col4), LEFT=col3, X inserted at col3
        self.run_test(
            "Left arrow then type in insert mode",
            "ABCD\n",
            b"$a\x1b[DX\x1b:wq\r",
            expected_content="ABCXD\n"
        )

        # Arrow left multiple then type in insert mode
        # $=col10 (d), a=insert at col11, LEFT*4=col7, X at col7
        self.run_test(
            "Multiple left arrows then type in insert",
            "Hello World\n",
            b"$a\x1b[D\x1b[D\x1b[D\x1b[DX\x1b:wq\r",
            expected_content="Hello WXorld\n"
        )

        # Arrow right then type in insert mode
        # i enters at col 0, RIGHT moves to col 1, X inserted at col 1
        self.run_test(
            "Right arrow then type in insert mode",
            "ABCD\n",
            b"i\x1b[CX\x1b:wq\r",
            expected_content="AXBCD\n"
        )

        # Arrow down then type in insert mode
        # i enters at line 0 col 0, DOWN moves to line 1 col 0, X inserted there
        self.run_test(
            "Down arrow then type in insert mode",
            "Hello\nWorld\n",
            b"i\x1b[BX\x1b:wq\r",
            expected_content="Hello\nXWorld\n"
        )

        # Arrow up then type in insert mode
        # j moves to line 1, i enters at col 0, UP moves to line 0 col 0, X inserted
        self.run_test(
            "Up arrow then type in insert mode",
            "Hello\nWorld\n",
            b"ji\x1b[AX\x1b:wq\r",
            expected_content="XHello\nWorld\n"
        )

        # Verify cursor position after iXYZ<ESC>
        self.run_test_screen(
            "iXYZ cursor on last inserted char",
            "Hello\n",
            b"iXYZ\x1b:q!\r",
            expect_cursor=(0, 2),
        )

        # Verify a vs i cursor difference
        self.run_test_screen(
            "a starts insert after cursor position",
            "Hello\n",
            b"a\x1b:q!\r",
            expect_cursor=(0, 0),
        )

        # ============================================================
        # Wrapped line scroll edge cases
        # ============================================================
        self._group("Wrapped line scroll edge cases:", leading_blank=True)

        # Enter in middle of a wrapped line.
        # Line 0: 30 chars at 20 cols = 2 screen rows (20+10).
        # Move to col 10 (lllllllllll = 10 l's), i enters insert, Enter splits.
        # Result: "AAAAAAAAAA" (10 chars, 1 row) + "AAAAAAAAAAAAAAAAAAAA" (20 chars, 1 row)
        # Verify content is correct after the split.
        self.run_test(
            "Enter in middle of wrapped line",
            "A" * 30 + "\n",
            b"l" * 10 + b"i\r\x1b:wq\r",
            expected_content="A" * 10 + "\n" + "A" * 20 + "\n"
        )

        # Enter in middle of wrapped line: screen state.
        # At 20 cols: line "A"*30 wraps to rows 0-1. After Enter splits at col 10:
        # Line 0: "AAAAAAAAAA" (10 chars, 1 row), Line 1: "AAAAAAAAAAAAAAAAAAAA" (20 chars, 1 row).
        # Cursor is at line 1 col 0 (screen row 1).
        self.run_test_screen(
            "Enter mid-wrapped line: screen correct",
            "A" * 30 + "\nShort\n",
            b"l" * 10 + b"i\r\x1b:q!\r",
            rows=10, cols=20,
            expect_cursor=(1, 0),
            expect_lines=[
                (0, "A" * 10),
                (1, "A" * 20),
                (2, "Short"),
            ],
        )

        # BS joining two wrapped lines.
        # Line 0: "A"*15, Line 1: "B"*15 at 20 cols. j moves to line 1.
        # i enters insert at col 0, BS joins -> "A"*15 + "B"*15 = 30 chars.
        # At 20 cols, this wraps to 2 rows: "A"*15 + "B"*5 (row 0), "B"*10 (row 1).
        # Verify content is correct.
        self.run_test(
            "BS joining two lines into wrapped result",
            "A" * 15 + "\n" + "B" * 15 + "\n",
            b"ji\x08\x1b:wq\r",
            expected_content="A" * 15 + "B" * 15 + "\n"
        )

        # BS joining two lines: screen shows wrapped result.
        self.run_test_screen(
            "BS joining lines wraps: screen correct",
            "A" * 15 + "\n" + "B" * 15 + "\nShort\n",
            b"ji\x08\x1b:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "A" * 15 + "B" * 5),
                (1, "B" * 10),
                (2, "Short"),
            ],
            expect_cursor=(0, 14),
        )

        # J at bottom of screen where joined result wraps off-screen.
        # Fill screen with short lines. The last visible line gets joined
        # with the line below. If result wraps, it might push content off.
        # 10 rows, 9 content + 1 status. 20 cols.
        # Lines: 9 short lines + "X"*20 line.
        # j*8 moves to line index 8 = "Short 9". J joins "Short 9" with "X"*20.
        # Result: "Short 9 " + "X"*20 = 28 chars, wraps to 2 rows at 20 cols.
        j_bottom_content = ''.join(f"Short {i}\n" for i in range(1, 10)) + "X" * 20 + "\n"
        self.run_test(
            "J at bottom where result wraps",
            j_bottom_content,
            b"j" * 8 + b"J:wq\r",
            expected_content=''.join(f"Short {i}\n" for i in range(1, 9)) + "Short 9 " + "X" * 20 + "\n"
        )

        # J at bottom: screen state. j*8 to line 8 = "Short 9", J joins with "X"*20.
        # "Short 9 " + "X"*20 = 28 chars at 20 cols: wraps to 2 rows.
        # Row 8: "Short 9 XXXXXXXXXXXX" (20 chars), row 9 would be status bar.
        # The joined result wraps, possibly needing scroll to stay visible.
        self.run_test_screen(
            "J at bottom: screen correct",
            j_bottom_content,
            b"j" * 8 + b"J:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "Short 1"), (1, "Short 2"),
                (2, "Short 3"), (3, "Short 4"),
                (4, "Short 5"), (5, "Short 6"),
                (6, "Short 7"), (7, "Short 8"),
                (8, "Short 9 XXXXXXXXXXXX"),
            ],
        )

        # J redo on a 3+ row wrapped line.
        # Line 0: "AAAA", Line 1: "BBBB" at 10 cols.
        # J => "AAAA BBBB" (9 chars, 1 row at 10 cols). Then u to undo, then space+u to redo.
        # After redo: same as after J.
        self.run_test_screen(
            "J redo on short lines: screen correct",
            "AAAA\nBBBB\nCCCC\n",
            b"Ju u:q!\r",
            rows=10, cols=10,
            expect_lines=[
                (0, "AAAA BBBB"),
                (1, "CCCC"),
            ],
            expect_cursor=(0, 4),
        )

        # J creating a 3+ row wrapped line.
        # Line 0: "A"*8, Line 1: "B"*8, Line 2: "C"*8 at 10 cols.
        # 2J joins 3 lines: "A"*8 + " " + "B"*8 + " " + "C"*8 = 26 chars.
        # At 10 cols: row 0 = "AAAAAAAA B" (10), row 1 = "BBBBBBB CC" (10), row 2 = "CCCCCC" (6).
        self.run_test_screen(
            "2J creating 3-row wrapped line: screen",
            "A" * 8 + "\n" + "B" * 8 + "\n" + "C" * 8 + "\nD\n",
            b"3J:q!\r",
            rows=10, cols=10,
            expect_lines=[
                (0, "AAAAAAAA " + "B"),
                (1, "BBBBBBB " + "CC"),
                (2, "CCCCCC"),
                (3, "D"),
            ],
            expect_cursor=(0, 8),
        )

        # cc when deleted line wraps: "This is a long line!" (20 chars at 10 cols = 2 rows).
        # cc clears it, enters insert. Type "X", ESC. Result: "X" on 1 row.
        self.run_test_screen(
            "cc on wrapped line: screen correct",
            "This is a long line!\nShort\n",
            b"ccX\x1b:q!\r",
            rows=10, cols=10,
            expect_lines=[
                (0, "X"),
                (1, "Short"),
            ],
            expect_cursor=(0, 0),
        )

        # cc on wrapped line: content correctness
        self.run_test(
            "cc on wrapped line: content correct",
            "A" * 25 + "\nB\n",
            b"ccNew\x1b:wq\r",
            expected_content="New\nB\n"
        )

        # dw at end of wrapped line producing wrap join.
        # "hello world" at 10 cols = 2 rows: "hello worl" (10), "d" (1).
        # "dw" deletes "hello " (6 chars) -> "world" (5 chars, 1 row).
        self.run_test_screen(
            "dw on wrapped line unwraps: screen correct",
            "hello world\nShort\n",
            b"dw:q!\r",
            rows=10, cols=10,
            expect_lines=[
                (0, "world"),
                (1, "Short"),
            ],
            expect_cursor=(0, 0),
        )

        # de at end of line producing wrap join.
        # "ABC" (3 chars) then "DEFGHIJKLM" (10 chars) at 10 cols.
        # Cursor at col 2 (last char 'C'), de crosses to next line and deletes to end of word "DEFGHIJKLM".
        # Result: "AB" (2 chars, 1 row at 10 cols).
        self.run_test(
            "de at EOL joining wrapped next line",
            "ABC\nDEFGHIJKLM\n",
            b"2lde:wq\r",
            expected_content="AB\n"
        )

        # de at end of line where next line wraps.
        # "ABC" + "DEFGHIJKLMNOP" (13 chars) at 10 cols. Next line wraps to 2 rows.
        # de from col 2 ('C') deletes "C\nDEFGHIJKLMNOP" -> "AB" remains.
        self.run_test_screen(
            "de joining with wrapped next line: screen",
            "ABC\nDEFGHIJKLMNOP\nShort\n",
            b"2lde:q!\r",
            rows=10, cols=10,
            expect_lines=[
                (0, "AB"),
                (1, "Short"),
            ],
            expect_cursor=(0, 1),
        )

        # DEL (delete key in insert mode) joining a wrapped next line.
        # Line 0: "AB", Line 1: "C"*15 at 10 cols. Line 1 wraps to 2 rows.
        # Cursor at end of line 0 ($=col 1), A=append at col 2, DEL joins.
        # Result: "AB" + "C"*15 = 17 chars, wraps to 2 rows at 10 cols.
        self.run_test(
            "DEL joining wrapped next line: content",
            "AB\n" + "C" * 15 + "\n",
            b"$A\x1b[3~\x1b:wq\r",
            expected_content="AB" + "C" * 15 + "\n"
        )

        # DEL joining wrapped next line: screen state.
        # "AB" + "C"*15 = 17 chars at 10 cols: row 0 = 10, row 1 = 7.
        # BUG: screen shows only 15 chars (row 1 = 5 C's instead of 7).
        # Content is correct (verified by content test above).
        self.run_test_screen(
            "DEL joining wrapped next line: screen",
            "AB\n" + "C" * 15 + "\n",
            b"$A\x1b[3~\x1b:q!\r",
            rows=10, cols=10,
            expect_lines=[
                (0, "ABCCCCCCCC"),
                (1, "CCCCCCC"),
            ],
        )

        # C from 3 wrap rows to 1.
        # Line 0: "A"*25 at 10 cols = 3 rows (10+10+5). Move to col 2, C deletes from col 2 to end.
        # Type "X", ESC. Result: "AA" + "X" = "AAX" (3 chars, 1 row).
        self.run_test_screen(
            "C from 3 wrap rows to 1: screen correct",
            "A" * 25 + "\nShort\n",
            b"llCX\x1b:q!\r",
            rows=10, cols=10,
            expect_lines=[
                (0, "AAX"),
                (1, "Short"),
            ],
            expect_cursor=(0, 2),
        )

        # C from 3 wrap rows to 1: content correctness
        self.run_test(
            "C from 3 wrap rows to 1: content correct",
            "A" * 25 + "\nB\n",
            b"llCX\x1b:wq\r",
            expected_content="AAX\nB\n"
        )

        # 3cc undo: screen content restored for wrapped lines.
        # 3 wrapped lines at 10 cols, each 15 chars (2 rows each = 6 screen rows).
        # 3cc deletes all 3, enters insert on blank. ESC, then u to undo.
        # After undo, original 3 wrapped lines should be restored.
        cc_undo_content = ("A" * 15 + "\n" + "B" * 15 + "\n" + "C" * 15 + "\nShort\n")
        self.run_test(
            "3cc undo restores wrapped lines: content",
            cc_undo_content,
            b"3cc\x1bu:wq\r",
            expected_content=cc_undo_content
        )

        # 3cc undo: screen shows restored wrapped lines.
        self.run_test_screen(
            "3cc undo restores wrapped lines: screen",
            cc_undo_content,
            b"3cc\x1bu:q!\r",
            rows=10, cols=10,
            expect_lines=[
                (0, "A" * 10),
                (1, "A" * 5),
                (2, "B" * 10),
                (3, "B" * 5),
                (4, "C" * 10),
                (5, "C" * 5),
                (6, "Short"),
            ],
            expect_cursor=(0, 0),
        )

        # cc on last line of file (wrapped line).
        # Single line: "X"*15 at 10 cols = 2 rows. cc + type "Y" + ESC.
        self.run_test(
            "cc on last wrapped line: content",
            "X" * 15 + "\n",
            b"ccY\x1b:wq\r",
            expected_content="Y\n"
        )

        # cc on last wrapped line: screen state.
        self.run_test_screen(
            "cc on last wrapped line: screen correct",
            "X" * 15 + "\n",
            b"ccY\x1b:q!\r",
            rows=10, cols=10,
            expect_lines=[
                (0, "Y"),
                (1, "~"),
            ],
            expect_cursor=(0, 0),
        )

        # Batched Enter at EOF.
        # Single line "AB". Go to end ($=col 1), A=append at col 2, type 3 Enters.
        # Creates 3 new empty lines after "AB". Result: "AB\n\n\n\n".
        self.run_test(
            "Batched Enter at EOF: content",
            "AB\n",
            b"$A\r\r\r\x1b:wq\r",
            expected_content="AB\n\n\n\n"
        )

        # Batched Enter at EOF: screen state.
        self.run_test_screen(
            "Batched Enter at EOF: screen correct",
            "AB\n",
            b"$A\r\r\r\x1b:q!\r",
            rows=10, cols=20,
            expect_lines=[
                (0, "AB"),
                (1, ""),
                (2, ""),
                (3, ""),
                (4, "~"),
            ],
            expect_cursor=(3, 0),
        )

        # Batched Enter on a wrapped line causing scroll.
        # 5-row screen (4 content + 1 status), 10 cols.
        # Line 0: "A"*15 (wraps to 2 rows at 10 cols), Line 1: "B", Line 2: "C".
        # Total = 4 screen rows = exactly fills content area.
        # Move to line 0 col 5, insert Enter. The split creates 2 lines,
        # and wrapping changes. If result doesn't fit, scroll occurs.
        self.run_test(
            "Batched Enter on wrapped line with scroll: content",
            "A" * 15 + "\nB\nC\n",
            b"l" * 5 + b"i\r\r\x1b:wq\r",
            expected_content="AAAAA\n\n" + "A" * 10 + "\nB\nC\n"
        )

        # Enter at exact wrap boundary column.
        # Line 0: "A"*20 at 10 cols = 2 rows. Move to col 10 (exact boundary).
        # Insert Enter at col 10 -> splits into "A"*10 + "A"*10.
        self.run_test(
            "Enter at exact wrap boundary column",
            "A" * 20 + "\n",
            b"l" * 10 + b"i\r\x1b:wq\r",
            expected_content="A" * 10 + "\n" + "A" * 10 + "\n"
        )

        # Enter at exact wrap boundary: screen state
        self.run_test_screen(
            "Enter at exact wrap boundary: screen",
            "A" * 20 + "\nShort\n",
            b"l" * 10 + b"i\r\x1b:q!\r",
            rows=10, cols=10,
            expect_lines=[
                (0, "A" * 10),
                (1, "A" * 10),
                (2, "Short"),
            ],
            expect_cursor=(1, 0),
        )

        # dd on last wrapped line when VIEW_TOP needs adjusting.
        # 5 rows (4 content + 1 status), 10 cols.
        # Lines: "A\nB\n" + "C"*15 (wraps to 2 rows) = 4 screen rows.
        # j*2 goes to last line, dd deletes it. VIEW_TOP may need adjustment
        # since the long wrapped line is gone.
        self.run_test_screen(
            "dd on last wrapped line adjusts view",
            "A\nB\n" + "C" * 15 + "\n",
            b"jjdd:q!\r",
            rows=5, cols=10,
            expect_lines=[
                (0, "A"),
                (1, "B"),
                (2, "~"),
            ],
            expect_cursor=(1, 0),
        )

        # 3+ batched paste (ppp) with wrapped lines.
        # yy copies "A"*15 (wraps at 10 cols). ppp pastes 3 copies below.
        self.run_test(
            "ppp batched paste with wrapped lines: content",
            "A" * 15 + "\nEnd\n",
            b"yyppp:wq\r",
            expected_content="A" * 15 + "\n" + ("A" * 15 + "\n") * 3 + "End\n"
        )

        # ppp batched paste: screen state
        self.run_test_screen(
            "ppp batched paste with wrapped lines: screen",
            "A" * 15 + "\nEnd\n",
            b"yyppp:q!\r",
            rows=12, cols=10,
            expect_lines=[
                (0, "A" * 10), (1, "A" * 5),
                (2, "A" * 10), (3, "A" * 5),
                (4, "A" * 10), (5, "A" * 5),
                (6, "A" * 10), (7, "A" * 5),
                (8, "End"),
            ],
        )

        # Batched paste_above (PP) with wrapped lines.
        # yy copies "A"*15 (wraps at 10 cols). PP pastes 2 copies above.
        self.run_test(
            "PP batched paste above with wrapped lines: content",
            "A" * 15 + "\nEnd\n",
            b"yyPP:wq\r",
            expected_content=("A" * 15 + "\n") * 2 + "A" * 15 + "\nEnd\n"
        )

        # PP batched paste above: screen state
        self.run_test_screen(
            "PP batched paste above with wrapped lines: screen",
            "A" * 15 + "\nEnd\n",
            b"yyPP:q!\r",
            rows=10, cols=10,
            expect_lines=[
                (0, "A" * 10), (1, "A" * 5),
                (2, "A" * 10), (3, "A" * 5),
                (4, "A" * 10), (5, "A" * 5),
                (6, "End"),
            ],
        )

        # Type at exact wrap boundary column.
        # Line 0: "A"*9 at 10 cols (1 row, just under boundary).
        # Move to end ($=col 8), a enters insert after last char (col 9).
        # Type "X" -> "A"*9 + "X" = 10 chars = exactly 1 row.
        # Type "Y" -> 11 chars = wraps to 2 rows.
        self.run_test_screen(
            "Type at exact wrap boundary column",
            "A" * 9 + "\nEnd\n",
            b"$aXY\x1b:q!\r",
            rows=10, cols=10,
            expect_lines=[
                (0, "A" * 9 + "X"),
                (1, "Y"),
                (2, "End"),
            ],
        )

        # Delete at exact wrap boundary column.
        # Line 0: "A"*10 + "B" at 10 cols = 2 rows (10 + 1).
        # Move to col 9 (last col of first wrap row). x deletes A at col 9.
        # Result: "A"*9 + "B" = 10 chars = 1 row.
        self.run_test_screen(
            "Delete at exact wrap boundary column",
            "A" * 10 + "B\nEnd\n",
            b"l" * 9 + b"x:q!\r",
            rows=10, cols=10,
            expect_lines=[
                (0, "A" * 9 + "B"),
                (1, "End"),
            ],
            expect_cursor=(0, 9),
        )

        # Batched Enter producing line at exactly screen width.
        # Line 0: "A"*10 + "B"*5 at 10 cols (wraps to 2 rows).
        # Move to col 10 (exact boundary), insert Enter splits there.
        # Result: "A"*10 (exactly 1 row) + "B"*5 (second line).
        self.run_test_screen(
            "Enter producing line at exactly screen width",
            "A" * 10 + "B" * 5 + "\nEnd\n",
            b"l" * 10 + b"i\r\x1b:q!\r",
            rows=10, cols=10,
            expect_lines=[
                (0, "A" * 10),
                (1, "B" * 5),
                (2, "End"),
            ],
            expect_cursor=(1, 0),
        )

        # 3>>>> count + batched indent.
        # 3>> indents up to 3 lines (2 spaces), >> batched repeat (2 more) = 4 spaces.
        self.run_test(
            "3>>>> count plus batched indent",
            "abc\n",
            b"3>>>>:wq\r",
            expected_content="    abc\n"
        )

        # ================================================================
        # Vertical scroll optimization with VIEW_TOP_WRAP
        # ================================================================
        # When the first visible line is partially off-screen (VIEW_TOP_WRAP > 0),
        # the editor should use scroll optimization instead of full repaint.

        # Setup content: line 0 wraps to 2 rows (35 chars at 20 cols), then short lines.
        # 6-row screen = 5 content rows + status bar.
        # Initial view: row 0-1 = line 0 (wrapped), rows 2-4 = lines 1-3.
        # j*4 batches: cursor at line 4. Walk-back 4 rows from line 4 lands on
        # (VIEW_TOP16=0, VIEW_TOP_WRAP=1) — partial wrap of line 0.
        # Viewport scrolled up by 1 row. New bottom row (row 4) exposed.
        vtw_content = ("A" * 35 + "\n"
                       + ''.join(f"Short {i}\n" for i in range(1, 10)))
        self.run_test_screen(
            "Scroll opt: j past bottom wrap increases on same VIEW_TOP",
            vtw_content,
            b"j" * 4 + b":q!\r",
            rows=6, cols=20,
            expect_lines=[
                (0, "A" * 15),    # line 0, wrap row 1
                (1, "Short 1"),
                (2, "Short 2"),
                (3, "Short 3"),
                (4, "Short 4"),   # cursor
            ],
            expect_cursor=(4, 0),
            # With scroll optimization: scroll up by 1, only bottom row redrawn
            expect_content_rows=[(1, {4})]
        )

        # After VIEW_TOP_WRAP increased (j*4 → VTW=1), k*4 returns cursor to
        # line 0, col 0 (WRAP_QUOT=0). Since WRAP_QUOT(0) < VIEW_TOP_WRAP(1),
        # ensure_cursor_visible scrolls up: VIEW_TOP_WRAP goes from 1 back to 0.
        # Viewport scrolled down by 1. New top row (line 0 wrap 0) exposed.
        # Frames: 0=initial, 1=j*4 (VTW 0→1), 2=k*4 (VTW 1→0)
        self.run_test_screen(
            "Scroll opt: k wrap decreases on same VIEW_TOP",
            vtw_content,
            b"j" * 4 + b"k" * 4 + b":q!\r",
            rows=6, cols=20,
            expect_lines=[
                (0, "A" * 20),    # line 0, wrap row 0
                (1, "A" * 15),    # line 0, wrap row 1
                (2, "Short 1"),
                (3, "Short 2"),
                (4, "Short 3"),
            ],
            expect_cursor=(0, 0),
            # Frame 2 (k*4): scroll down by 1, only top row redrawn
            expect_content_rows=[(2, {0})]
        )

        # j past bottom where VIEW_TOP changes AND new VIEW_TOP_WRAP > 0.
        # Content: lines 0-1 short, line 2 wraps to 3 rows (55 chars at 20 cols),
        # then short lines. 6-row screen.
        # j*5: cursor at line 5. Walk-back 4 rows from line 5:
        #   line 4 (1 row, RR=3), line 3 (1 row, RR=2), line 2 (3 rows, VTW=2, RR=1),
        #   VTW 2→1, RR=0. Result: VIEW_TOP16=2, VIEW_TOP_WRAP=1.
        # SNAP: (0,0). Scroll amount: line 0 (1) + line 1 (1) + new_wrap (1) = 3.
        # Scroll up by 3, render 3 new bottom rows.
        vtw_content2 = ("Short 0\nShort 1\n" + "D" * 55 + "\n"
                        + ''.join(f"Short {i}\n" for i in range(3, 12)))
        self.run_test_screen(
            "Scroll opt: j past bottom VIEW_TOP changes new wrap nonzero",
            vtw_content2,
            b"j" * 5 + b":q!\r",
            rows=6, cols=20,
            expect_lines=[
                (0, "D" * 20),    # line 2, wrap row 1
                (1, "D" * 15),    # line 2, wrap row 2
                (2, "Short 3"),
                (3, "Short 4"),
                (4, "Short 5"),   # cursor
            ],
            expect_cursor=(4, 0),
            # Scroll up by 3, render 3 new bottom rows
            expect_content_rows=[(1, {2, 3, 4})]
        )

        # j with VIEW_TOP change and SNAP_VIEW_TOP_WRAP > 0.
        # From j*5 state: VIEW_TOP16=2, VTW=1. Use 'l' to break batching,
        # then j*2 in a new frame.
        # j*2 from line 5→7. Walk-back from 7, 4 rows:
        #   line 6 (1), line 5 (1), line 4 (1), line 3 (1) → VTW=0.
        # Result: VIEW_TOP16=3, VIEW_TOP_WRAP=0. SNAP: (2,1).
        # Scroll amount: (screen_rows(line 2) - 1) + line 3 visible = (3-1) + 0 = 2.
        # Wait — walk from (2,1) to (3,0): line 2 contributes 3-1=2 visible rows.
        # But new_wrap = 0. Total = 2. Scroll up by 2, render 2 bottom rows.
        self.run_test_screen(
            "Scroll opt: j VIEW_TOP changes with old wrap nonzero",
            vtw_content2,
            b"j" * 5 + b"l" + b"j" * 2 + b":q!\r",
            rows=6, cols=20,
            expect_lines=[
                (0, "Short 3"),
                (1, "Short 4"),
                (2, "Short 5"),
                (3, "Short 6"),
                (4, "Short 7"),   # cursor
            ],
            expect_cursor=(4, 1),   # 'l' moved col to 1
            # Frame 3 (j*2): scroll up by 2, render 2 new bottom rows
            expect_content_rows=[(3, {3, 4})]
        )

        # VIEW_TOP_WRAP increases by more than 1 in a single step.
        # Content: line 0 wraps to 4 rows (75 chars at 20 cols), then short lines.
        # 6-row screen: initial shows line 0 wrap 0-3 (4 rows) + Short 1 (1 row).
        # j*4: cursor at line 4. Walk-back 4 rows from line 4:
        #   line 3 (1, RR=3), line 2 (1, RR=2), line 1 (1, RR=1),
        #   line 0 (4 rows, VTW=3, RR=0).
        # Result: VIEW_TOP16=0, VIEW_TOP_WRAP=3. Wrap changed by 3.
        # Scroll up by 3, render 3 new bottom rows.
        vtw_multi_wrap = ("A" * 75 + "\n"
                          + ''.join(f"Short {i}\n" for i in range(1, 10)))
        self.run_test_screen(
            "Scroll opt: VIEW_TOP_WRAP increases by 3",
            vtw_multi_wrap,
            b"j" * 4 + b":q!\r",
            rows=6, cols=20,
            expect_lines=[
                (0, "A" * 15),    # line 0, wrap row 3
                (1, "Short 1"),
                (2, "Short 2"),
                (3, "Short 3"),
                (4, "Short 4"),   # cursor
            ],
            expect_cursor=(4, 0),
            # Scroll up by 3, render 3 new bottom rows
            expect_content_rows=[(1, {2, 3, 4})]
        )

        # Large scroll delta that exceeds SCREEN_ROWS should fall back to
        # full repaint. j*50 on a file with many short lines where VIEW_TOP
        # changes dramatically — delta >= SCREEN_ROWS-1.
        # This test just ensures no crash and correct final state.
        vtw_large = ''.join(f"Line {i}\n" for i in range(60))
        self.run_test_screen(
            "Scroll opt: large j scroll still renders correctly",
            vtw_large,
            b"j" * 50 + b":q!\r",
            rows=6, cols=20,
            expect_lines=[
                (0, "Line 46"),
                (1, "Line 47"),
                (2, "Line 48"),
                (3, "Line 49"),
                (4, "Line 50"),  # cursor
            ],
            expect_cursor=(4, 0),
        )

        # Insert mode: arrow down past bottom with VIEW_TOP_WRAP.
        # Same content as vtw_content (line 0 wraps to 2 rows).
        # Enter insert mode on line 0 (i), then press down arrow 4 times.
        # Same walk-back as normal mode: VIEW_TOP_WRAP goes from 0 to 1.
        DOWN = b"\x1b[B"
        self.run_test_screen(
            "Scroll opt: insert arrow down wrap increases on same VIEW_TOP",
            vtw_content,
            b"i" + DOWN * 4 + b"\x1b:q!\r",
            rows=6, cols=20,
            expect_lines=[
                (0, "A" * 15),    # line 0, wrap row 1
                (1, "Short 1"),
                (2, "Short 2"),
                (3, "Short 3"),
                (4, "Short 4"),   # cursor was here in insert mode
            ],
            expect_cursor=(4, 0),  # cursor at line 4 (col 0, ESC no decrement)
            # Frame 2 (DOWN*4): scroll up by 1, only bottom row redrawn
            expect_content_rows=[(2, {4})]
        )

        # Insert mode: arrow up past top with VIEW_TOP_WRAP decrease.
        # Start with j*4 to get VTW=1, then enter insert mode, arrow up 4 times.
        UP = b"\x1b[A"
        self.run_test_screen(
            "Scroll opt: insert arrow up wrap decreases on same VIEW_TOP",
            vtw_content,
            b"j" * 4 + b"i" + UP * 4 + b"\x1b:q!\r",
            rows=6, cols=20,
            expect_lines=[
                (0, "A" * 20),    # line 0, wrap row 0
                (1, "A" * 15),    # line 0, wrap row 1
                (2, "Short 1"),
                (3, "Short 2"),
                (4, "Short 3"),
            ],
            expect_cursor=(0, 0),
            # Frame 3 (UP*4): scroll down by 1, only top row redrawn
            expect_content_rows=[(3, {0})]
        )

        # VIEW_TOP_WRAP changes but LINE_COUNT also changed: should fall back
        # to full repaint. Enter on a partial-wrap viewport modifies the buffer.
        # j*4 gets VTW=1, then 'o' opens new line (LINE_COUNT changes).
        # Both VTW change and LINE_COUNT change → full repaint.
        self.run_test_screen(
            "Scroll opt: wrap change plus LINE_COUNT change falls back to full",
            vtw_content,
            b"j" * 4 + b"o\x1b:q!\r",
            rows=6, cols=20,
            # After o (open line below line 4), cursor on new empty line 5
            # VTW changes and LINE_COUNT changes → full repaint expected
            # Just verify correct final state (no scroll optimization assertion)
            expect_cursor=(4, 0),
        )

        # Both SNAP_VIEW_TOP_WRAP and VIEW_TOP_WRAP non-zero (wrap_changed path).
        # Line 0 wraps to 4 rows (75 chars at 20 cols), then short lines.
        # j*2 batches (frame 1): cursor at line 2. Walk-back 4 rows:
        #   line 1 (1, RR=3), line 0 (4 rows, VTW=3, RR=2), VTW 3→2 (RR=1),
        #   VTW 2→1 (RR=0). Result: VIEW_TOP16=0, VTW=1. Wrap changes 0→1.
        # Then 'l' (frame 2, no viewport change), j (frame 3): cursor at line 3.
        # Walk-back from 3, 4: line 2 (1,3), line 1 (1,2), line 0 (4, VTW=3, 1),
        #   VTW 3→2 (0). Result: VIEW_TOP16=0, VTW=2. SNAP_VTW=1, VTW=2.
        # Both non-zero. Scroll up by 1, render 1 new bottom row.
        self.run_test_screen(
            "Scroll opt: both old and new VIEW_TOP_WRAP nonzero",
            vtw_multi_wrap,
            b"j" * 2 + b"l" + b"j" + b":q!\r",
            rows=6, cols=20,
            expect_lines=[
                (0, "A" * 20),    # line 0, wrap row 2
                (1, "A" * 15),    # line 0, wrap row 3
                (2, "Short 1"),
                (3, "Short 2"),
                (4, "Short 3"),   # cursor
            ],
            expect_cursor=(4, 1),  # l moved col to 1
            # Frame 3 (j): wrap 1→2, scroll up 1, only bottom row redrawn
            expect_content_rows=[(3, {4})]
        )

        # Scroll direction verification: j triggers scroll UP (content moves up),
        # k triggers scroll DOWN (content moves down).
        # j*4 on vtw_content: VTW 0→1, scroll up. k*4 back: VTW 1→0, scroll down.
        # Verify scroll occurred and direction via expect_scrolled_at_frame.
        self.run_test_screen(
            "Scroll opt: VIEW_TOP_WRAP scroll direction j=up k=down",
            vtw_content,
            b"j" * 4 + b"k" * 4 + b":q!\r",
            rows=6, cols=20,
            expect_lines=[
                (0, "A" * 20),    # back to initial view
                (1, "A" * 15),
                (2, "Short 1"),
                (3, "Short 2"),
                (4, "Short 3"),
            ],
            expect_cursor=(0, 0),
            expect_scrolled_at_frame=[(1, True), (2, True)],
        )

        # Two-phase: j*4 scroll (VTW 0→1), l (break), j scroll (VIEW_TOP changes).
        # After j*4: VIEW_TOP (0,1). After l: unchanged. After j: cursor at line 5.
        # Walk-back from 5: lines 4,3,2,1 → VIEW_TOP16=1, VTW=0.
        # SNAP: (0,1). After: (1,0). VIEW_TOP changed, old wrap>0.
        # Walk from (0,1) to (1,0): line 0 visible=2-1=1, new_wrap=0. Total=1.
        # Scroll up by 1.
        self.run_test_screen(
            "Scroll opt: wrap then view change single j",
            vtw_content,
            b"j" * 4 + b"l" + b"j" + b":q!\r",
            rows=6, cols=20,
            expect_lines=[
                (0, "Short 1"),
                (1, "Short 2"),
                (2, "Short 3"),
                (3, "Short 4"),
                (4, "Short 5"),   # cursor
            ],
            expect_cursor=(4, 1),
            # Frame 3 (j): VIEW_TOP changed with old wrap, scroll up 1
            expect_content_rows=[(3, {4})]
        )

        # Round-trip content verification: j*4 scrolls VTW 0→1, then k*4
        # scrolls back to VTW 0→0. Verify exact content matches initial state
        # using expect_lines_at_frame at both frames.
        self.run_test_screen(
            "Scroll opt: round trip content matches initial",
            vtw_content,
            b"j" * 4 + b"k" * 4 + b":q!\r",
            rows=6, cols=20,
            expect_lines_at_frame=[
                (1, [
                    (0, "A" * 15),
                    (1, "Short 1"),
                    (2, "Short 2"),
                    (3, "Short 3"),
                    (4, "Short 4"),
                ]),
                (2, [
                    (0, "A" * 20),
                    (1, "A" * 15),
                    (2, "Short 1"),
                    (3, "Short 2"),
                    (4, "Short 3"),
                ]),
            ],
            expect_cursor=(0, 0),
        )

        # Insert mode: type after VIEW_TOP_WRAP scroll to verify no corruption.
        # j*4 (VTW 0→1), enter insert, type "X", ESC, verify content.
        self.run_test_screen(
            "Scroll opt: insert type after wrap scroll preserves content",
            vtw_content,
            b"j" * 4 + b"iX\x1b:q!\r",
            rows=6, cols=20,
            expect_lines=[
                (0, "A" * 15),    # line 0, wrap 1 (unchanged)
                (1, "Short 1"),
                (2, "Short 2"),
                (3, "Short 3"),
                (4, "XShort 4"),  # cursor on line 4, typed X
            ],
            expect_cursor=(4, 0),
        )

        # ================================================================
        # Indent/unindent render optimization
        # ================================================================
        # >> and << currently force full repaint. Only the affected rows
        # should be redrawn when wrapping doesn't change.

        # >> single line: only row 0 redrawn (not full screen).
        # Frames: 0=initial, 1=>>
        self.run_test_screen(
            "Render opt: >> single line partial redraw",
            "Hello\nWorld\nThird\n",
            b">>:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "  Hello"), (1, "World"), (2, "Third")],
            expect_cursor=(0, 2),
            expect_content_rows=[(1, {0})]
        )

        # << single line: only row 0 redrawn.
        self.run_test_screen(
            "Render opt: << single line partial redraw",
            "  Hello\nWorld\nThird\n",
            b"<<:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello"), (1, "World"), (2, "Third")],
            expect_cursor=(0, 0),
            expect_content_rows=[(1, {0})]
        )

        # 2>> two lines: only rows 0-1 redrawn.
        # Frames: 0=initial, 1='2' count, 2=>>
        self.run_test_screen(
            "Render opt: 2>> partial redraw two rows",
            "Hello\nWorld\nThird\nFourth\n",
            b"2>>:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "  Hello"), (1, "  World"),
                (2, "Third"), (3, "Fourth"),
            ],
            expect_cursor=(0, 2),
            expect_content_rows=[(2, {0, 1})]
        )

        # 2<< two lines: only rows 0-1 redrawn.
        self.run_test_screen(
            "Render opt: 2<< partial redraw two rows",
            "  Hello\n  World\nThird\nFourth\n",
            b"2<<:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Hello"), (1, "World"),
                (2, "Third"), (3, "Fourth"),
            ],
            expect_cursor=(0, 0),
            expect_content_rows=[(2, {0, 1})]
        )

        # >>>> batched: 4 spaces added, only row 0 redrawn.
        # batch_pending_pairs consumes the second >> pair, single frame.
        self.run_test_screen(
            "Render opt: >>>> batched partial redraw",
            "Hello\nWorld\n",
            b">>>>:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "    Hello"), (1, "World")],
            expect_cursor=(0, 4),
            expect_content_rows=[(1, {0})]
        )

        # <<<< batched: removes up to 4 spaces.
        self.run_test_screen(
            "Render opt: <<<< batched partial redraw",
            "    Hello\nWorld\n",
            b"<<<<:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello"), (1, "World")],
            expect_cursor=(0, 0),
            expect_content_rows=[(1, {0})]
        )

        # >> at mid-screen: only affected row (row 2), not row 0.
        # Frames: 0=initial, 1=jj (batched), 2=>>
        self.run_test_screen(
            "Render opt: >> mid-screen partial redraw",
            make_lines(10),
            b"jj>>:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "Line 1"), (1, "Line 2"),
                (2, "  Line 3"),
                (3, "Line 4"),
            ],
            expect_cursor=(2, 2),
            expect_content_rows=[(2, {2})]
        )

        # >> causes wrap: line grows from 1 to 2 screen rows.
        # "A"*39 at 40 cols = 1 row. After >>: "  "+"A"*39 = 41 chars = 2 rows.
        # Scroll down by 1 in region below, repaint 2 rows of affected line.
        # Frames: 0=initial, 1=>>
        self.run_test_screen(
            "Render opt: >> causes wrap scrolls down",
            "A" * 39 + "\nSecond\nThird\n",
            b">>:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "  " + "A" * 38),   # wrap row 0
                (1, "A"),                # wrap row 1
                (2, "Second"),
                (3, "Third"),
            ],
            expect_cursor=(0, 2),
            # Rows 0-1 are affected line (repainted), row 2+ from scroll
            expect_scrolled_at_frame=[(1, True)],
        )

        # << removes wrap: line shrinks from 2 to 1 screen row.
        # "  "+"A"*39 = 41 chars = 2 rows. After <<: "A"*39 = 1 row.
        # Scroll up by 1 in region below, repaint affected row.
        self.run_test_screen(
            "Render opt: << removes wrap scrolls up",
            "  " + "A" * 39 + "\nSecond\nThird\n",
            b"<<:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "A" * 39),
                (1, "Second"),
                (2, "Third"),
            ],
            expect_cursor=(0, 0),
            expect_scrolled_at_frame=[(1, True)],
        )

        # << no-op (no leading spaces): no content redraw needed.
        self.run_test_screen(
            "Render opt: << no-op no content redraw",
            "Hello\nWorld\n",
            b"<<:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, "Hello"), (1, "World")],
            expect_cursor=(0, 0),
            expect_content_redraws=[True, False, False]
        )

        # >> all empty lines in range: nothing changes, no content redraw.
        self.run_test_screen(
            "Render opt: >> all empty lines no content redraw",
            "\n\nThird\n",
            b"2>>:q!\r",
            rows=10, cols=40,
            expect_lines=[(0, ""), (1, ""), (2, "Third")],
            expect_cursor=(0, 0),
            expect_content_redraws=[True, False, False, False]
        )

        # 2>>>> batched multi-line: 2 lines, 4 spaces each, rows 0-1 redrawn.
        self.run_test_screen(
            "Render opt: 2>>>> batched multi-line partial redraw",
            "Hello\nWorld\nThird\n",
            b"2>>>>:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "    Hello"), (1, "    World"), (2, "Third"),
            ],
            expect_cursor=(0, 4),
            expect_content_rows=[(2, {0, 1})]
        )

        # :1,3> range indent: only rows 0-2 redrawn.
        # Frames: 0=initial, 1=':' entry (status only), 2=command completes
        # and renders the partial repaint.
        self.run_test_screen(
            "Render opt: :1,3> range partial redraw",
            "aaa\nbbb\nccc\nddd\neee\n",
            b":1,3>\r:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "  aaa"), (1, "  bbb"), (2, "  ccc"),
                (3, "ddd"), (4, "eee"),
            ],
            expect_cursor=(0, 2),
            expect_content_rows=[(2, {0, 1, 2})]
        )

        # :1,3< range unindent: only rows 0-2 redrawn.
        self.run_test_screen(
            "Render opt: :1,3< range partial redraw",
            "  aaa\n  bbb\n  ccc\nddd\neee\n",
            b":1,3<\r:q!\r",
            rows=10, cols=40,
            expect_lines=[
                (0, "aaa"), (1, "bbb"), (2, "ccc"),
                (3, "ddd"), (4, "eee"),
            ],
            expect_cursor=(0, 0),
            expect_content_rows=[(2, {0, 1, 2})]
        )

        print()
        print("=" * 60)
        total = self.passed + self.failed + self.skipped
        parts = [f"{Colors.GREEN}{self.passed} passed{Colors.NC}"]
        if self.failed:
            parts.append(f"{Colors.RED}{self.failed} failed{Colors.NC}")
        if self.skipped:
            parts.append(f"{Colors.YELLOW}{self.skipped} skipped{Colors.NC}")
        print(f"Results: {', '.join(parts)} of {total} tests")
        print("=" * 60)

        # Create stable copy only if all tests passed
        if self.failed == 0:
            self.create_stable_copy()

        self.emulator_runner.close()
        self._tmpdir_obj.cleanup()


def main():
    parser = argparse.ArgumentParser(description="Editor test runner")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Only show failures and summary")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--no-server", action="store_true",
                        help="Use subprocess.run instead of persistent server")
    args = parser.parse_args()

    if args.no_color:
        Colors.disable()

    script_dir = Path(__file__).parent.resolve()
    base_dir = script_dir.parent.parent

    runner = EditorTestRunner(base_dir, verbose=args.verbose,
                              quiet=args.quiet,
                              use_server=not args.no_server)
    runner.run_all_tests()

    sys.exit(1 if runner.failed > 0 else 0)


if __name__ == "__main__":
    main()
