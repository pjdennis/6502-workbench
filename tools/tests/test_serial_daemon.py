"""Tests for tools/upload/serial_daemon.py, using fake serial ports and a fake clock.

Run from the repo root:  python3 -m unittest discover -s tools/tests -v
"""
import io
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'upload'))

import serial_daemon  # noqa: E402
from upload_frame import send_duration  # noqa: E402

DEVICE = '/dev/ttyUSB0'


class FakeClock:
  def __init__(self):
    self.now = 100.0

  def clock(self):
    return self.now

  def sleep(self, seconds):
    self.now += seconds


class FakeSerial:
  def __init__(self, device, clock, log):
    self.device, self.clock, self.log = device, clock, log
    self.baudrate = 9600
    self.stopbits = 1
    self.closed = False
    self.fail_write = False

  @property
  def dtr(self):
    raise AssertionError('not read')

  @dtr.setter
  def dtr(self, value):
    self.log.append(('dtr', value, self.clock.now))

  def write(self, data):
    if self.fail_write:
      raise OSError(5, 'Input/output error')
    self.log.append(('write', bytes(data), self.clock.now, self.baudrate, self.stopbits))

  def flush(self):
    pass

  def close(self):
    self.closed = True

  def __enter__(self):
    return self

  def __exit__(self, *exc):
    self.close()


class FakeDevices:
  """Present devices, each with an identity that changes when it is replugged."""
  def __init__(self, clock):
    self.clock = clock
    self.present = {}
    self.opened = []
    self.log = []

  def plug(self, device=DEVICE):
    self.present[device] = object()

  def unplug(self, device=DEVICE):
    del self.present[device]

  def find_device(self):
    if not self.present:
      raise serial_daemon.NoDevice('no USB serial device found')
    return next(iter(self.present))

  def identify(self, device):
    if device not in self.present:
      raise FileNotFoundError(device)
    return self.present[device]

  def open_serial(self, device):
    ser = FakeSerial(device, self.clock, self.log)
    self.opened.append(ser)
    return ser

  def writes(self):
    return [event[1] for event in self.log if event[0] == 'write']


def send_header(length, reset=False, baudrate=115200, stopbits=1, wait=False, port=None):
  return {'protocol': serial_daemon.PROTOCOL, 'op': 'send', 'reset': reset, 'baudrate': baudrate,
          'stopbits': stopbits, 'wait': wait, 'port': port, 'length': length}


class DaemonTestCase(unittest.TestCase):
  def setUp(self):
    self.clock = FakeClock()
    self.devices = FakeDevices(self.clock)
    self.daemon = self.make_daemon()

  def make_daemon(self, configured_port=None):
    holder = serial_daemon.PortHolder(self.devices.find_device, self.devices.open_serial, self.devices.identify)
    return serial_daemon.Daemon(holder, configured_port=configured_port,
                                clock=self.clock.clock, sleep=self.clock.sleep)

  def send(self, payload, **options):
    return self.daemon.handle(send_header(len(payload), **options), payload)

  def open_and_acknowledge(self):
    """Open the port and use up the one-shot 'board was reset' refusal."""
    self.devices.plug()
    self.assertFalse(self.send(b'x')['ok'])


class SendTest(DaemonTestCase):
  def test_first_send_after_open_without_reset_is_refused_once(self):
    self.devices.plug()
    response = self.send(b'abc')
    self.assertFalse(response['ok'])
    self.assertIn('reset', response['error'])
    self.assertEqual(self.devices.writes(), [])

    self.assertEqual(self.send(b'abc'), {'ok': True})
    self.assertEqual(self.devices.writes(), [b'abc'])

  def test_first_send_after_open_with_reset_is_sent(self):
    self.devices.plug()
    self.assertEqual(self.send(b'abc', reset=True), {'ok': True})
    self.assertEqual(self.devices.writes(), [b'abc'])

  def test_reset_pulses_dtr_then_waits_before_writing(self):
    self.devices.plug()
    start = self.clock.now
    self.send(b'abc', reset=True)
    self.assertEqual(self.devices.log, [
      ('dtr', True, start),
      ('dtr', False, start + 0.1),
      ('write', b'abc', start + 0.3, 115200, 1),
    ])

  def test_no_reset_leaves_dtr_alone(self):
    self.open_and_acknowledge()
    self.send(b'abc')
    self.assertEqual([event[0] for event in self.devices.log], ['write'])

  def test_baudrate_and_stopbits_applied_before_writing(self):
    self.open_and_acknowledge()
    self.send(b'abc', baudrate=57600, stopbits=2)
    self.assertEqual(self.devices.log[-1][3:], (57600, 2))

  def test_without_wait_replies_straight_after_writing(self):
    self.open_and_acknowledge()
    start = self.clock.now
    self.send(bytes(1000))
    self.assertEqual(self.clock.now, start)

  def test_wait_replies_once_the_data_has_had_time_to_send(self):
    self.open_and_acknowledge()
    start = self.clock.now
    self.send(bytes(1000), baudrate=57600, stopbits=2, wait=True)
    self.assertAlmostEqual(self.clock.now, start + send_duration(1000, 57600, 2))

  def test_no_device_reports_and_stops(self):
    response = self.send(b'abc', reset=True)
    self.assertFalse(response['ok'])
    self.assertIn('no USB serial device', response['error'])
    self.assertTrue(self.daemon.stopping)

  def test_write_error_reports_and_stops(self):
    self.open_and_acknowledge()
    self.devices.opened[0].fail_write = True
    response = self.send(b'abc')
    self.assertFalse(response['ok'])
    self.assertIn('Input/output error', response['error'])
    self.assertTrue(self.daemon.stopping)


class DisconnectTest(DaemonTestCase):
  """The port is opened once: when the adapter goes away the daemon stops rather than wait to open
  whatever appears next."""

  def test_poll_never_opens_a_device(self):
    self.devices.plug()
    self.daemon.poll()
    self.assertEqual(self.devices.opened, [])
    self.assertFalse(self.daemon.stopping)

  def test_poll_keeps_an_open_device_open(self):
    self.open_and_acknowledge()
    self.daemon.poll()
    self.daemon.poll()
    self.assertEqual(len(self.devices.opened), 1)
    self.assertFalse(self.devices.opened[0].closed)
    self.assertFalse(self.daemon.stopping)

  def test_poll_stops_when_the_device_vanishes(self):
    self.open_and_acknowledge()
    self.devices.unplug()
    self.daemon.poll()
    self.assertTrue(self.daemon.stopping)

  def test_poll_stops_when_the_device_is_replugged(self):
    self.open_and_acknowledge()
    self.devices.plug()                               # same path, new device node
    self.daemon.poll()
    self.assertTrue(self.daemon.stopping)
    self.assertEqual(len(self.devices.opened), 1)

  def test_send_that_notices_a_replugged_device_before_poll_does_is_refused_and_stops(self):
    self.open_and_acknowledge()
    self.devices.plug()
    response = self.send(b'abc', reset=True)
    self.assertFalse(response['ok'])
    self.assertIn('disconnected', response['error'])
    self.assertTrue(self.daemon.stopping)
    self.assertEqual(len(self.devices.opened), 1)
    self.assertEqual(self.devices.writes(), [])


class RequestTest(DaemonTestCase):
  def test_protocol_mismatch(self):
    self.devices.plug()
    header = dict(send_header(3, reset=True), protocol=serial_daemon.PROTOCOL + 1)
    response = self.daemon.handle(header, b'abc')
    self.assertFalse(response['ok'])
    self.assertIn('--daemon stop', response['error'])
    self.assertEqual(self.devices.writes(), [])

  def test_status_and_stop_work_whatever_the_protocol(self):
    # so a client of any version can find and stop a daemon of any version
    for op in ('status', 'stop'):
      self.assertTrue(self.daemon.handle({'protocol': serial_daemon.PROTOCOL + 1, 'op': op}, b'')['ok'])
      self.assertTrue(self.daemon.handle({'op': op}, b'')['ok'])

  def test_unknown_op(self):
    response = self.daemon.handle({'protocol': serial_daemon.PROTOCOL, 'op': 'bogus'}, b'')
    self.assertFalse(response['ok'])

  def test_port_other_than_the_daemons_is_refused(self):
    self.devices.plug()
    response = self.send(b'abc', reset=True, port='/dev/other')
    self.assertFalse(response['ok'])
    self.assertIn('--daemon stop', response['error'])
    self.assertEqual(self.devices.writes(), [])

  def test_port_matching_the_daemons_is_accepted(self):
    self.daemon = self.make_daemon(configured_port=DEVICE)
    self.devices.plug()
    self.assertEqual(self.send(b'abc', reset=True, port=DEVICE), {'ok': True})

  def test_status(self):
    self.open_and_acknowledge()
    response = self.daemon.handle({'protocol': serial_daemon.PROTOCOL, 'op': 'status'}, b'')
    self.assertTrue(response['ok'])
    self.assertEqual(response['device'], DEVICE)
    self.assertEqual(response['pid'], os.getpid())

  def test_stop(self):
    self.assertFalse(self.daemon.stopping)
    response = self.daemon.handle({'protocol': serial_daemon.PROTOCOL, 'op': 'stop'}, b'')
    self.assertTrue(response['ok'])
    self.assertTrue(self.daemon.stopping)


class MessageTest(unittest.TestCase):
  def test_round_trip_with_payload(self):
    buffer = io.BytesIO()
    serial_daemon.write_message(buffer, {'op': 'send'}, b'\x00\n\xff')
    buffer.seek(0)
    self.assertEqual(serial_daemon.read_message(buffer), ({'op': 'send', 'length': 3}, b'\x00\n\xff'))

  def test_round_trip_without_payload(self):
    buffer = io.BytesIO()
    serial_daemon.write_message(buffer, {'ok': True})
    buffer.seek(0)
    self.assertEqual(serial_daemon.read_message(buffer), ({'ok': True, 'length': 0}, b''))

  def test_truncated_payload(self):
    buffer = io.BytesIO(b'{"length": 5}\nabc')
    with self.assertRaises(EOFError):
      serial_daemon.read_message(buffer)


class ServeTest(DaemonTestCase):
  def test_requests_over_the_socket_until_stopped(self):
    path = os.path.join(tempfile.mkdtemp(), 'daemon.sock')
    listener = serial_daemon.bind_listener(path)
    thread = threading.Thread(target=serial_daemon.serve, args=(listener, self.daemon, 0.01))
    thread.start()
    try:
      self.devices.plug()
      self.assertEqual(serial_daemon.request(path, send_header(3, reset=True), b'abc'), {'ok': True})
      self.assertTrue(serial_daemon.request(path, {'protocol': serial_daemon.PROTOCOL, 'op': 'stop'})['ok'])
    finally:
      thread.join(5)
    self.assertFalse(thread.is_alive())
    self.assertEqual(self.devices.writes(), [b'abc'])
    self.assertTrue(self.devices.opened[0].closed)
    self.assertFalse(os.path.exists(path))

  def test_exits_when_the_device_is_unplugged(self):
    path = os.path.join(tempfile.mkdtemp(), 'daemon.sock')
    listener = serial_daemon.bind_listener(path)
    thread = threading.Thread(target=serial_daemon.serve, args=(listener, self.daemon, 0.01))
    thread.start()
    try:
      self.devices.plug()
      self.assertEqual(serial_daemon.request(path, send_header(3, reset=True), b'abc'), {'ok': True})
      self.devices.unplug()
    finally:
      thread.join(5)
    self.assertFalse(thread.is_alive())
    self.assertTrue(self.devices.opened[0].closed)
    self.assertFalse(os.path.exists(path))

  def test_request_to_missing_daemon(self):
    path = os.path.join(tempfile.mkdtemp(), 'daemon.sock')
    with self.assertRaises(serial_daemon.NotRunning):
      serial_daemon.request(path, {'protocol': serial_daemon.PROTOCOL, 'op': 'status'})


def comport(device, vid=0x10C4, description='CP2102 USB to UART Bridge Controller', manufacturer='Silicon Labs',
            hwid='USB VID:PID=10C4:EA60 SER=0001 LOCATION=1-2'):
  """A stand-in for one of pyserial's list_ports.comports() entries."""
  return types.SimpleNamespace(device=device, vid=vid, description=description, manufacturer=manufacturer,
                               product=description, hwid=hwid)


DIGILENT = dict(vid=0x0403, description='Digilent Adept USB Device', manufacturer='Digilent',
                hwid='USB VID:PID=0403:6010 SER=210328B04676 LOCATION=1-1:1.0')


class FindUsbSerialPortTest(unittest.TestCase):
  def find(self, *ports, **options):
    return serial_daemon.find_usb_serial_port(comports=lambda: list(ports), **options)

  def test_the_only_usb_port_is_found(self):
    self.assertEqual(self.find(comport('/dev/ttyUSB0')), '/dev/ttyUSB0')

  def test_non_usb_ports_are_skipped(self):
    self.assertEqual(self.find(comport('/dev/ttyS0', vid=None), comport('/dev/ttyUSB0')), '/dev/ttyUSB0')

  def test_no_usb_port_is_refused(self):
    with self.assertRaisesRegex(serial_daemon.NoDevice, 'no USB serial device found'):
      self.find(comport('/dev/ttyS0', vid=None))

  def test_several_usb_ports_are_refused_and_listed(self):
    with self.assertRaisesRegex(serial_daemon.NoDevice, r'multiple .*/dev/ttyUSB0 .*/dev/ttyUSB1'):
      self.find(comport('/dev/ttyUSB0'), comport('/dev/ttyUSB1'))

  def test_a_given_port_is_used_without_looking(self):
    self.assertEqual(self.find(comport('/dev/ttyUSB0'), comport('/dev/ttyUSB1'), port=os.devnull), os.devnull)

  def test_a_given_port_that_does_not_exist_is_refused(self):
    with self.assertRaisesRegex(serial_daemon.NoDevice, 'not found'):
      self.find(port='/dev/no-such-port')

  def test_ignored_ports_are_skipped(self):
    self.assertEqual(self.find(comport('/dev/ttyUSB0', **DIGILENT), comport('/dev/ttyUSB1', **DIGILENT),
                               comport('/dev/ttyUSB2'), ignore=['*Digilent*']), '/dev/ttyUSB2')

  def test_ignore_patterns_ignore_case(self):
    self.assertEqual(self.find(comport('/dev/ttyUSB0', **DIGILENT), comport('/dev/ttyUSB2'), ignore=['*DIGILENT*']),
                     '/dev/ttyUSB2')

  def test_ignore_patterns_match_the_hardware_id(self):
    self.assertEqual(self.find(comport('/dev/ttyUSB0', **DIGILENT), comport('/dev/ttyUSB2'),
                               ignore=['*VID:PID=0403:6010 *']), '/dev/ttyUSB2')

  def test_ignore_patterns_match_whole_fields(self):
    with self.assertRaisesRegex(serial_daemon.NoDevice, 'multiple'):
      self.find(comport('/dev/ttyUSB0', **DIGILENT), comport('/dev/ttyUSB2'), ignore=['Digilent Adept'])

  def test_only_ignored_ports_is_refused_and_lists_them(self):
    with self.assertRaisesRegex(serial_daemon.NoDevice, r'no USB serial device found.*ignored.*/dev/ttyUSB0'):
      self.find(comport('/dev/ttyUSB0', **DIGILENT), ignore=['*Digilent*'])

  def test_a_given_port_is_used_even_if_ignored(self):
    self.assertEqual(self.find(comport(os.devnull, **DIGILENT), port=os.devnull, ignore=['*Digilent*']), os.devnull)

  def test_the_ignore_list_ignores_digilent_boards(self):
    self.assertEqual(self.find(comport('/dev/ttyUSB0', **DIGILENT), comport('/dev/ttyUSB2')), '/dev/ttyUSB2')


class ReadIgnorePatternsTest(unittest.TestCase):
  def read(self, text):
    path = os.path.join(tempfile.mkdtemp(), 'ignore.txt')
    with open(path, 'w') as f:
      f.write(text)
    return serial_daemon.read_ignore_patterns(path)

  def test_one_pattern_per_line_without_comments_or_blank_lines(self):
    self.assertEqual(self.read('# comment\n\n  *Digilent*  \n*VID:PID=0403:6010 *\n'),
                     ['*Digilent*', '*VID:PID=0403:6010 *'])

  def test_a_missing_file_ignores_nothing(self):
    self.assertEqual(serial_daemon.read_ignore_patterns('/no/such/file'), [])


try:
  import serial  # noqa: F401
  HAVE_PYSERIAL = True
except ImportError:
  HAVE_PYSERIAL = False


def open_pty(testcase):
  """A pseudo-terminal to stand in for a USB serial port: returns (master fd, slave path)."""
  master, slave = os.openpty()
  testcase.addCleanup(os.close, master)
  path = os.ttyname(slave)
  os.close(slave)
  return master, path


@unittest.skipUnless(HAVE_PYSERIAL, 'pyserial not installed')
class RealDaemonTest(unittest.TestCase):
  """The daemon process, holding a pseudo-terminal in place of a USB serial port."""

  def setUp(self):
    self.master, self.pty = open_pty(self)
    self.socket = os.path.join(tempfile.mkdtemp(), 'daemon.sock')
    self.process = self.start()
    self.addCleanup(self.process.wait, 5)
    self.addCleanup(self.stop)
    self.wait_for_socket()

  def start(self):
    return subprocess.Popen([sys.executable, serial_daemon.SCRIPT, '--socket', self.socket, '--port', self.pty],
                            stderr=subprocess.DEVNULL)

  def wait_for_socket(self):
    for _ in range(100):
      if os.path.exists(self.socket):
        return
      time.sleep(0.05)
    self.fail('daemon did not start')

  def request(self, header, payload=b''):
    return serial_daemon.request(self.socket, dict(header, protocol=serial_daemon.PROTOCOL), payload)

  def stop(self):
    try:
      self.request({'op': 'stop'})
    except serial_daemon.NotRunning:
      pass

  def send(self, payload):
    return self.request(send_header(len(payload), port=self.pty), payload)

  def test_sends_through_the_held_port(self):
    self.assertIn('reset', self.send(b'first')['error'])
    self.assertEqual(self.send(b'hello'), {'ok': True})
    self.assertEqual(os.read(self.master, 100), b'hello')

  def test_second_daemon_exits_leaving_the_first_running(self):
    second = self.start()
    self.assertEqual(second.wait(5), 0)
    self.assertEqual(self.request({'op': 'status'})['pid'], self.process.pid)

  def test_stop_ends_the_process_and_removes_the_socket(self):
    self.assertTrue(self.request({'op': 'stop'})['ok'])
    self.assertEqual(self.process.wait(5), 0)
    self.assertFalse(os.path.exists(self.socket))


if __name__ == '__main__':
  unittest.main()
