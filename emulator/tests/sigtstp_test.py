#!/usr/bin/env python3
"""
Test that the emulator restores the screen after Ctrl+Z / fg in terminal mode.

The bug: In terminal mode, after SIGTSTP (Ctrl+Z) and SIGCONT (fg), the
emulator enters the alternate screen buffer (which is blank) but does NOT
redraw the screen from its internal buffer. Console mode correctly redraws.

This test:
1. Starts the emulator in terminal-interactive mode on a PTY
2. Waits for the 6502 program to output "HELLO"
3. Sends SIGTSTP to suspend the emulator
4. Sends SIGCONT to resume it
5. Verifies that "HELLO" appears in the output after resume (screen redrawn)

Usage:
    python3 tests/sigtstp_test.py [-v]
"""

import argparse
import fcntl
import os
import pty
import select
import signal
import subprocess
import sys
import time
from pathlib import Path


class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    NC = "\033[0m"

    @classmethod
    def disable(cls):
        cls.RED = cls.GREEN = cls.YELLOW = cls.NC = ""


def read_pty(master_fd, timeout=5.0):
    """Read all available data from PTY master, with timeout."""
    data = b""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        ready, _, _ = select.select([master_fd], [], [], min(remaining, 0.1))
        if ready:
            try:
                chunk = os.read(master_fd, 4096)
                if chunk:
                    data += chunk
                else:
                    break
            except OSError:
                break
        elif data:
            # Got some data and no more is coming
            break
    return data


def drain_pty(master_fd, timeout=0.2):
    """Drain any remaining data from PTY."""
    data = b""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        ready, _, _ = select.select([master_fd], [], [], min(remaining, 0.05))
        if ready:
            try:
                chunk = os.read(master_fd, 4096)
                if chunk:
                    data += chunk
                else:
                    break
            except OSError:
                break
    return data


def wait_for_content(master_fd, target, timeout=5.0):
    """Read from PTY until target bytes are found or timeout."""
    data = b""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        ready, _, _ = select.select([master_fd], [], [], min(remaining, 0.1))
        if ready:
            try:
                chunk = os.read(master_fd, 4096)
                if chunk:
                    data += chunk
                    if target in data:
                        return data
            except OSError:
                break
    return data


def set_nonblocking(fd):
    """Set a file descriptor to non-blocking mode."""
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)


def run_sigtstp_redraw_test(base_dir, verbose=False):
    """Test that screen is redrawn after SIGTSTP/SIGCONT in terminal mode."""
    emulator = base_dir / "emulator" / "emulator.out"
    assembler = base_dir / "asm" / "17" / "out" / "asm.out"
    test_asm = base_dir / "emulator" / "tests" / "sigtstp_test.asm"
    test_bin = base_dir / "emulator" / "tests" / "out" / "sigtstp_test.out"

    if not emulator.exists():
        print(f"Error: Emulator not found at {emulator}")
        return False
    if not assembler.exists():
        print(f"Error: Assembler not found at {assembler}")
        return False

    # Assemble the test program
    test_bin.parent.mkdir(exist_ok=True)
    result = subprocess.run(
        [str(emulator), str(assembler), "--no-dump",
         str(test_asm), str(test_bin)],
        capture_output=True, text=True, cwd=base_dir  # .include paths are root-relative
    )
    if result.returncode != 0:
        print(f"Error: Failed to assemble test program:")
        print(result.stderr)
        return False

    # Create a PTY for the emulator
    master_fd, slave_fd = pty.openpty()

    try:
        # Start emulator in terminal-interactive mode on the PTY
        # --terminal without --input/--output = terminal_interactive
        proc = subprocess.Popen(
            [str(emulator), str(test_bin), "--no-dump",
             "--load", "0400",
             "--terminal", "--rows", "24", "--cols", "80",
             "--cpu-mhz", "10", "--baud", "115200"],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid,  # New session so we can signal the group
        )
        os.close(slave_fd)
        slave_fd = -1

        # Wait for the 6502 program to output "HELLO"
        initial_output = wait_for_content(master_fd, b"HELLO", timeout=5.0)

        if b"HELLO" not in initial_output:
            print(f"  {Colors.RED}FAIL{Colors.NC} Screen redraw after SIGTSTP/SIGCONT: "
                  f"Program did not output HELLO")
            if verbose:
                print(f"    Got: {initial_output!r}")
            proc.kill()
            proc.wait()
            return False

        if verbose:
            print(f"    Initial output received ({len(initial_output)} bytes)")

        # Drain any remaining output
        drain_pty(master_fd, timeout=0.5)

        # Send SIGTSTP to the emulator (simulates Ctrl+Z)
        os.kill(proc.pid, signal.SIGTSTP)

        # Wait a moment for the emulator to handle the signal and suspend
        time.sleep(0.3)

        # Read any output from the SIGTSTP handling (restore_terminal sequences)
        tstp_output = drain_pty(master_fd, timeout=0.5)
        if verbose:
            print(f"    SIGTSTP output ({len(tstp_output)} bytes): {tstp_output!r}")

        # Send SIGCONT to resume the emulator
        os.kill(proc.pid, signal.SIGCONT)

        # Read output after SIGCONT - this should contain the redrawn screen
        # Wait for content to appear (the screen redraw)
        cont_output = read_pty(master_fd, timeout=3.0)

        if verbose:
            print(f"    SIGCONT output ({len(cont_output)} bytes): {cont_output!r}")

        # The screen should be redrawn after SIGCONT.
        # After setup_raw_terminal() sends \x1b[?1049h (enter alt buffer),
        # console_redraw() should repaint the screen content including "HELLO".
        #
        # Strip ANSI escape sequences to check for content
        # We look for "HELLO" in the post-SIGCONT output
        if b"HELLO" not in cont_output:
            print(f"  {Colors.RED}FAIL{Colors.NC} Screen redraw after SIGTSTP/SIGCONT: "
                  f"Screen was not redrawn after resume")
            if verbose:
                print(f"    Expected 'HELLO' in post-SIGCONT output")
                print(f"    Got: {cont_output!r}")
            else:
                print(f"    Post-SIGCONT output: {cont_output!r}")
            # Clean up: send Ctrl+D to exit
            try:
                os.write(master_fd, b"\x04")
            except OSError:
                pass
            proc.wait(timeout=5)
            return False

        print(f"  {Colors.GREEN}PASS{Colors.NC} Screen redraw after SIGTSTP/SIGCONT")

        # Clean up: send Ctrl+D to exit the program
        try:
            os.write(master_fd, b"\x04")
        except OSError:
            pass
        proc.wait(timeout=5)
        return True

    except Exception as e:
        print(f"  {Colors.RED}FAIL{Colors.NC} Screen redraw after SIGTSTP/SIGCONT: {e}")
        return False
    finally:
        if slave_fd >= 0:
            os.close(slave_fd)
        try:
            os.close(master_fd)
        except OSError:
            pass
        try:
            proc.kill()
            proc.wait(timeout=2)
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="SIGTSTP/SIGCONT screen restore test")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show detailed output")
    args = parser.parse_args()

    if not sys.stdout.isatty():
        Colors.disable()

    base_dir = Path(__file__).resolve().parent.parent.parent

    print("=" * 60)
    print("SIGTSTP/SIGCONT Screen Restore Test")
    print("=" * 60)

    success = run_sigtstp_redraw_test(base_dir, verbose=args.verbose)

    print()
    print("=" * 60)
    if success:
        print(f"Results: {Colors.GREEN}1 passed{Colors.NC} of 1 test")
    else:
        print(f"Results: {Colors.RED}1 failed{Colors.NC} of 1 test")
    print("=" * 60)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
