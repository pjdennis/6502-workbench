"""Shared PersistentEmulator for running tests through a persistent emulator --server process."""

import os
import select
import subprocess


class PersistentEmulator:
    """Runs tests through a persistent emulator --server process."""

    def __init__(self, emulator_path):
        self.emulator_path = str(emulator_path)
        self.proc = None
        self.current_binary = None
        self.current_mode = None
        self.current_api = None
        self.current_load_addr = None
        self.current_cwd = None
        self._start()

    def _start(self):
        self.proc = subprocess.Popen(
            [self.emulator_path, '--server'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        self.current_binary = None
        self.current_mode = None
        self.current_api = None
        self.current_load_addr = None
        self.current_cwd = None
        self._stdout_fd = self.proc.stdout.fileno()
        self._read_buf = b''

    def _send(self, line):
        self.proc.stdin.write((line + '\n').encode())
        self.proc.stdin.flush()

    def _send_raw(self, data):
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def _fill_buf(self, timeout=10):
        ready, _, _ = select.select([self._stdout_fd], [], [], timeout)
        if not ready:
            raise subprocess.TimeoutExpired(self.emulator_path, timeout)
        chunk = os.read(self._stdout_fd, 65536)
        if not chunk:
            raise RuntimeError("Server process died")
        self._read_buf += chunk

    def _read_line(self, timeout=10):
        while b'\n' not in self._read_buf:
            self._fill_buf(timeout)
        idx = self._read_buf.index(b'\n')
        line = self._read_buf[:idx]
        self._read_buf = self._read_buf[idx + 1:]
        return line.decode('latin-1')

    def _read_bytes(self, count, timeout=10):
        while len(self._read_buf) < count:
            self._fill_buf(timeout)
        data = self._read_buf[:count]
        self._read_buf = self._read_buf[count:]
        return data

    def _read_response(self, inline_output, inline_stderr):
        """Read EXIT and optional OUTPUT/STDERR responses.

        Returns (exit_code, output_bytes_or_None, stderr_bytes_or_None).
        """
        response = self._read_line()
        if not response.startswith('EXIT '):
            raise RuntimeError(f"Unexpected server response: {response!r}")
        exit_code = int(response.split()[1])

        output = None
        stderr_data = None

        if inline_output:
            line = self._read_line()
            if line.startswith('OUTPUT '):
                output_len = int(line.split()[1])
                output = self._read_bytes(output_len) if output_len > 0 else b""
            else:
                output = b""
                # This line might be STDERR, handle below
                if inline_stderr and line.startswith('STDERR '):
                    stderr_len = int(line.split()[1])
                    stderr_data = self._read_bytes(stderr_len) if stderr_len > 0 else b""
                    return exit_code, output, stderr_data

        if inline_stderr and stderr_data is None:
            line = self._read_line()
            if line.startswith('STDERR '):
                stderr_len = int(line.split()[1])
                stderr_data = self._read_bytes(stderr_len) if stderr_len > 0 else b""
            else:
                stderr_data = b""

        return exit_code, output, stderr_data

    def run(self, binary, args=None, load_addr=-1, mode='standard',
            rows=0, cols=0, cwd=None,
            keys=None, inline_output=False, inline_stderr=False,
            strict_api=False):
        """Run a binary in the emulator server (strict_api: as --strict-api).

        Returns (exit_code, output_bytes_or_None, stderr_bytes_or_None).
        """
        # Check if server is still alive
        if self.proc.poll() is not None:
            self._start()

        binary_str = str(binary)
        mode_str = mode if mode in ('terminal', 'direct') else 'standard'

        # Send CWD if changed
        if cwd is not None:
            cwd_str = str(cwd)
            if cwd_str != self.current_cwd:
                self._send(f'CWD {cwd_str}')
                self.current_cwd = cwd_str

        # Send mode before binary if it changed
        if mode_str != self.current_mode:
            self._send(f'MODE {mode_str}')
            self.current_mode = mode_str
            self.current_binary = None

        api_str = 'strict' if strict_api else 'standard'
        if api_str != self.current_api:
            self._send(f'API {api_str}')
            self.current_api = api_str
            self.current_binary = None

        if load_addr != self.current_load_addr:
            if load_addr >= 0:
                self._send(f'LOAD {load_addr:04x}')
            else:
                self._send('LOAD auto')
            self.current_load_addr = load_addr
            self.current_binary = None

        if binary_str != self.current_binary:
            self._send(f'BINARY {binary_str}')
            self.current_binary = binary_str

        if rows > 0:
            self._send(f'ROWS {rows}')
        if cols > 0:
            self._send(f'COLS {cols}')

        if keys is not None:
            self._send(f'KEYS {len(keys)}')
            self._send_raw(keys)

        if inline_output:
            self._send('INLINE_OUTPUT')
        if inline_stderr:
            self._send('INLINE_STDERR')

        if args:
            for arg in args:
                self._send(f'ARG {arg}')
        self._send('RUN')

        return self._read_response(inline_output, inline_stderr)

    def close(self):
        if self.proc and self.proc.poll() is None:
            try:
                self._send('QUIT')
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
                self.proc.wait()
