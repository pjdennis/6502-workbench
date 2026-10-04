"""Helpers for the bring-up checks that run a program on Michael and listen to the FPGA on the Cmod's USB
serial port (input-check/check.py, bus-check/check.py).

  board.py idle [--michael-port DEV]   leaves Michael quiet on the FPGA bus (michael_fpga_bus_idle.s), as the
                                      bus check does before loading its design
"""
import argparse
import os
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
UPLOAD = os.path.join(REPO, "tools", "upload", "compile_and_upload_michael.sh")
IDLE = os.path.join(REPO, "firmware", "programs", "michael", "michael_fpga_bus_idle.s")
IDLE_START = 0.5   # seconds for the ROM to start a program once its upload has gone


def serial_module():
    """The kit's uart_check module (FPGA_KIT, or the kit checked out beside this repository)."""
    kit = os.environ.get("FPGA_KIT") or os.path.join(REPO, "..", "fpga-toolchain-research")
    sys.path.insert(0, os.path.join(kit, "scripts"))
    import uart_check
    return uart_check


def upload(program, michael_port=None, wait=False):
    """Assembles a Michael program and uploads it; returns the upload script's exit code. With wait, returns
    only once the upload has had time to send."""
    print(f"Uploading {os.path.relpath(program, REPO)} to Michael ...")
    options = ([f"--port={michael_port}"] if michael_port else []) + (["--wait"] if wait else [])
    with tempfile.TemporaryDirectory() as tmp:  # the upload script writes a.s19 in its working directory
        return subprocess.run([UPLOAD, *options, program], cwd=tmp).returncode


def idle(michael_port=None):
    """Runs michael_fpga_bus_idle.s on Michael, so that nothing it does reaches the FPGA bus: E held low.
    Returns the upload's exit code."""
    rc = upload(IDLE, michael_port, wait=True)
    if not rc:
        time.sleep(IDLE_START)
    return rc


class LineReader:
    """Collects the lines arriving on a serial port, in a background thread. Junk can precede a line (the
    serial line settling as the FPGA starts up), so each line starts at the first of `starts` in it."""

    def __init__(self, ser, starts):
        self.ser, self.starts = ser, starts
        self.lines, self.raw, self.lock = [], [], threading.Lock()   # raw: each line's bytes as they came
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        while True:
            data = self.ser.readline(deadline=None)
            raw = data.decode(errors="replace")
            found = [raw.find(c) for c in self.starts if c in raw]
            line = raw[min(found):].strip() if found else raw.strip()
            with self.lock:
                self.lines.append(line)
                self.raw.append(data)

    def snapshot(self):
        with self.lock:
            return list(self.lines)

    def save_raw(self, path):
        """Writes every line's bytes as they came, one per line, with non-printing bytes as escapes."""
        with self.lock, open(path, "w") as f:
            f.writelines(repr(data)[2:-1] + "\n" for data in self.raw)

    def wait_for(self, predicate, timeout):
        """Waits until predicate(lines) is true; returns whether it became true in time."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate(self.snapshot()):
                return True
            time.sleep(0.1)
        return predicate(self.snapshot())


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Michael helpers for the FPGA bring-up checks")
    ap.add_argument("command", choices=["idle"])
    ap.add_argument("--michael-port", help="Michael's serial port (default: as the upload tools choose it)")
    sys.exit(idle(ap.parse_args().michael_port))
