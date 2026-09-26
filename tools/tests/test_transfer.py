"""Tests for tools/upload/transfer.py, the serial daemon's client, against an in-process daemon
with fake serial ports.

Run from the repo root:  python3 -m unittest discover -s tools/tests -v
"""
import contextlib
import io
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'upload'))

import serial_daemon  # noqa: E402
import transfer  # noqa: E402
from test_serial_daemon import DEVICE, HAVE_PYSERIAL, FakeClock, FakeDevices, open_pty  # noqa: E402
from upload_frame import build_frame, send_duration  # noqa: E402

PROGRAM = b'\x4c\x00\x50hello'


class TransferTestCase(unittest.TestCase):
  def setUp(self):
    self.dir = tempfile.mkdtemp()
    self.socket = os.path.join(self.dir, 'daemon.sock')
    self.program = os.path.join(self.dir, 'a.out')
    with open(self.program, 'wb') as f:
      f.write(PROGRAM)
    self.clock = FakeClock()
    self.devices = FakeDevices(self.clock)
    self.thread = None
    self.starts = 0
    self.addCleanup(self.stop_daemon)

  def start_daemon(self):
    self.starts += 1
    holder = serial_daemon.PortHolder(self.devices.find_device, self.devices.open_serial, self.devices.identify)
    daemon = serial_daemon.Daemon(holder, clock=self.clock.clock, sleep=self.clock.sleep)
    listener = serial_daemon.bind_listener(self.socket)
    self.thread = threading.Thread(target=serial_daemon.serve, args=(listener, daemon, 0.01))
    self.thread.start()

  def stop_daemon(self):
    if self.thread is not None and self.thread.is_alive():
      serial_daemon.request(self.socket, {'op': 'stop'})
      self.thread.join(5)

  def run_transfer(self, *args, start_daemon=None):
    """Returns (exit status, stderr)."""
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stderr):
      status = transfer.main(list(args), socket_path=self.socket,
                             start_daemon=start_daemon or self.fail_to_start)
    return status, stderr.getvalue()

  def fail_to_start(self):
    self.fail('daemon started unexpectedly')

  def upload(self, *args, start_daemon=None):
    return self.run_transfer('--baudrate=115200', *args, self.program, start_daemon=start_daemon)


class UploadTest(TransferTestCase):
  def setUp(self):
    super().setUp()
    self.devices.plug()
    self.start_daemon()

  def test_sends_the_framed_file_after_a_reset(self):
    self.assertEqual(self.upload(), (0, ''))
    self.assertEqual(self.devices.writes(), [build_frame(PROGRAM)])
    self.assertEqual([event[:2] for event in self.devices.log[:2]], [('dtr', True), ('dtr', False)])

  def test_noreset_sends_without_a_reset(self):
    self.upload()
    self.devices.log.clear()
    self.assertEqual(self.upload('--noreset'), (0, ''))
    self.assertEqual([event[0] for event in self.devices.log], ['write'])

  def test_noreset_just_after_the_port_opens_is_refused(self):
    status, output = self.upload('--noreset')
    self.assertEqual(status, 1)
    self.assertIn('resets the board', output)
    self.assertEqual(self.devices.writes(), [])

  def test_baudrate_and_stopbits(self):
    self.run_transfer('--baudrate=57600', '--stopbits=2', self.program)
    self.assertEqual(self.devices.log[-1][3:], (57600, 2))

  def test_returns_without_waiting_for_the_data_to_send(self):
    self.upload()
    start = self.clock.now
    self.upload('--noreset')
    self.assertEqual(self.clock.now, start)

  def test_wait(self):
    self.upload()
    start = self.clock.now
    self.upload('--noreset', '--wait')
    self.assertAlmostEqual(self.clock.now, start + send_duration(len(build_frame(PROGRAM)), 115200, 1))

  def test_port_other_than_the_daemons(self):
    status, output = self.upload('--port=/dev/other')
    self.assertEqual(status, 1)
    self.assertIn('--daemon stop', output)

  def test_file_too_large(self):
    with open(self.program, 'wb') as f:
      f.write(bytes(0x10000))
    status, output = self.upload()
    self.assertEqual(status, 1)
    self.assertIn('0xffff', output)
    self.assertEqual(self.devices.writes(), [])

  def test_status(self):
    status, output = self.run_transfer('--daemon', 'status')
    self.assertEqual(status, 0)
    self.assertIn(str(os.getpid()), output)
    self.assertIn(DEVICE, output)

  def test_stop(self):
    self.assertEqual(self.run_transfer('--daemon', 'stop')[0], 0)
    self.thread.join(5)
    self.assertFalse(self.thread.is_alive())
    self.assertFalse(os.path.exists(self.socket))


class AutostartTest(TransferTestCase):
  def test_starts_the_daemon_when_none_is_running(self):
    self.devices.plug()
    self.assertEqual(self.upload(start_daemon=self.start_daemon), (0, ''))
    self.assertEqual(self.starts, 1)
    self.assertEqual(self.devices.writes(), [build_frame(PROGRAM)])

  def test_daemon_that_does_not_start(self):
    with mock.patch.object(transfer, 'AUTOSTART_TIMEOUT', 0.2):
      status, output = self.upload(start_daemon=lambda: None)
    self.assertEqual(status, 1)
    self.assertIn('did not start', output)
    self.assertIn(self.socket + '.log', output)

  def test_status_and_stop_do_not_start_a_daemon(self):
    for command in ('status', 'stop'):
      status, output = self.run_transfer('--daemon', command)
      self.assertEqual(status, 0)
      self.assertIn('not running', output)


class ArgumentsTest(TransferTestCase):
  def test_baudrate_required(self):
    with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
      transfer.main([self.program], socket_path=self.socket, start_daemon=self.fail_to_start)

  def test_file_required(self):
    with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
      transfer.main(['--baudrate=115200'], socket_path=self.socket, start_daemon=self.fail_to_start)


@unittest.skipUnless(HAVE_PYSERIAL, 'pyserial not installed')
class RealPortTest(TransferTestCase):
  """A pseudo-terminal in place of a USB serial port."""

  def setUp(self):
    super().setUp()
    self.master, self.pty = open_pty(self)

  def test_direct_opens_the_port_itself(self):
    self.assertEqual(self.upload('--direct', '--noreset', '--port=' + self.pty), (0, ''))
    self.assertEqual(os.read(self.master, 100), build_frame(PROGRAM))

  def test_starts_the_real_daemon(self):
    self.addCleanup(self.run_transfer, '--daemon', 'stop')
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
      first = transfer.main(['--baudrate=115200', '--noreset', '--port=' + self.pty, self.program],
                            socket_path=self.socket)
      second = transfer.main(['--baudrate=115200', '--noreset', '--port=' + self.pty, self.program],
                             socket_path=self.socket)
    self.assertEqual((first, second), (1, 0))       # the first is refused: the port had just opened
    self.assertIn('Started the serial daemon', stderr.getvalue())
    self.assertEqual(os.read(self.master, 100), build_frame(PROGRAM))


if __name__ == '__main__':
  unittest.main()
