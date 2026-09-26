"""Holds the USB serial port open so that uploads don't reset the board.

On Linux, opening a USB serial port asserts DTR, which resets a board whose reset is wired to DTR
(the cp210x driver also asserts it when the speed changes from B0). This daemon opens the port once
and keeps it; transfer.py sends uploads through it over a Unix socket. It reopens the port when the
adapter is unplugged and plugged back in.

Usually started on demand by transfer.py. Log: the socket path + '.log'.
Usage: serial_daemon.py [--socket PATH] [--port DEVICE]

Protocol: each message is a JSON header line followed by header['length'] payload bytes.
Requests carry 'op' ('send', 'status' or 'stop'), and a send carries 'protocol'; replies carry
'ok' and, on failure, 'error'. Keep status and stop working unchanged across protocol versions.
"""
import argparse
import fcntl
import json
import logging
import os
import select
import signal
import socket
import sys
import tempfile
import time

from upload_frame import send_duration

PROTOCOL = 1
POLL_INTERVAL = 0.5    # seconds between checks for the adapter appearing or disappearing
CLIENT_TIMEOUT = 10    # seconds allowed for a client to deliver its request
RESET_PULSE = 0.1      # seconds DTR is held for a reset
RESET_SETTLE = 0.2     # seconds allowed for the board to start up after a reset
OPEN_BAUDRATE = 115200

SCRIPT = os.path.abspath(__file__)

REOPENED = ("the serial port has just been opened, which resets the board, so nothing was sent. "
            "The board is now running its ROM loader: do a reset upload (e.g. of the RAM uploader), "
            "or re-run to send to the ROM loader anyway")

log = logging.getLogger('serial_daemon')


class NoDevice(Exception):
  pass


class NotRunning(Exception):
  pass


def default_socket_path():
  if os.environ.get('SERIAL_DAEMON_SOCKET'):
    return os.environ['SERIAL_DAEMON_SOCKET']
  runtime = os.environ.get('XDG_RUNTIME_DIR')
  if runtime and os.path.isdir(runtime):
    return os.path.join(runtime, '6502-serial-daemon.sock')
  return os.path.join(tempfile.gettempdir(), '6502-serial-daemon-{}.sock'.format(os.getuid()))


def find_usb_serial_port(port=None):
  if port is not None:
    if not os.path.exists(port):
      raise NoDevice('{} not found'.format(port))
    return port
  from serial.tools import list_ports
  usb_ports = [p for p in list_ports.comports() if p.vid is not None]
  if not usb_ports:
    raise NoDevice('no USB serial device found; specify --port')
  if len(usb_ports) > 1:
    raise NoDevice('multiple USB serial devices found; specify --port. Found: ' +
                   ', '.join('{} ({})'.format(p.device, p.description) for p in usb_ports))
  return usb_ports[0].device


def open_serial(device):
  import serial
  ser = serial.Serial(baudrate=OPEN_BAUDRATE)
  ser.port = device
  ser.dtr = False
  ser.open()
  return ser


# Changes when the adapter is replugged, even if it comes back at the same path
def device_identity(device):
  st = os.stat(device)
  return (st.st_ino, st.st_rdev)


def transmit(ser, payload, reset, baudrate, stopbits, wait, clock=time.monotonic, sleep=time.sleep):
  """Send payload, after a DTR reset pulse if asked. With wait, return only once it has had time to
  leave the adapter."""
  ser.baudrate = baudrate
  ser.stopbits = stopbits
  if reset:
    ser.dtr = True
    sleep(RESET_PULSE)
    ser.dtr = False
    sleep(RESET_SETTLE)
  start = clock()
  ser.write(payload)
  ser.flush()
  if wait:
    sleep(max(0, start + send_duration(len(payload), baudrate, stopbits) - clock()))


class PortHolder:
  """The serial port, opened when the adapter is present and closed when it goes away. fresh is set
  when the port is opened (which resets the board) and cleared by the daemon."""

  def __init__(self, find_device, open_serial, identify):
    self._find_device, self._open_serial, self._identify = find_device, open_serial, identify
    self.serial = self.device = self._identity = None
    self.fresh = False
    self._problem = None

  def poll(self):
    try:
      self.ensure_open()
    except (NoDevice, OSError) as e:
      if str(e) != self._problem:
        log.info('%s', e)
      self._problem = str(e)

  def ensure_open(self):
    if self.serial is not None and self._present():
      return self.serial
    self.close()
    device = self._find_device()
    identity = self._identify(device)
    self.serial = self._open_serial(device)
    self.device, self._identity, self.fresh, self._problem = device, identity, True, None
    log.info('opened %s', device)
    return self.serial

  def close(self):
    if self.serial is None:
      return
    try:
      self.serial.close()
    except OSError:
      pass
    log.info('closed %s', self.device)
    self.serial = self.device = self._identity = None

  def _present(self):
    try:
      return self._identify(self.device) == self._identity
    except OSError:
      return False


def error(message):
  return {'ok': False, 'error': message}


class Daemon:
  def __init__(self, port, configured_port=None, clock=time.monotonic, sleep=time.sleep):
    self.port, self.configured_port, self.clock, self.sleep = port, configured_port, clock, sleep
    self.stopping = False

  def poll(self):
    self.port.poll()

  def handle(self, header, payload):
    handler = {'send': self.send, 'status': self.status, 'stop': self.stop}.get(header.get('op'))
    if handler is None:
      return error('unknown op {!r}'.format(header.get('op')))
    return handler(header, payload)

  # Only send checks the protocol, so that any client can find and stop any daemon
  def send(self, header, payload):
    if header.get('protocol') != PROTOCOL:
      return error('the serial daemon (pid {}, {}) speaks protocol {}, not {}; run transfer.py --daemon stop '
                   'and retry'.format(os.getpid(), SCRIPT, PROTOCOL, header.get('protocol')))
    port = header.get('port')
    if port is not None and port != self.configured_port:
      return error('the serial daemon is using {}, not {}; run transfer.py --daemon stop to switch'.format(
        self.configured_port or 'the auto-detected USB serial port', port))
    try:
      ser = self.port.ensure_open()
    except (NoDevice, OSError) as e:
      return error(str(e))
    if self.port.fresh and not header['reset']:
      self.port.fresh = False
      return error(REOPENED)
    try:
      transmit(ser, payload, header['reset'], header['baudrate'], header['stopbits'], header.get('wait'),
               self.clock, self.sleep)
    except (OSError, ValueError) as e:
      self.port.close()
      return error('serial port error: {}'.format(e))
    self.port.fresh = False
    log.info('sent %d bytes%s', len(payload), ' after reset' if header['reset'] else '')
    return {'ok': True}

  def status(self, header, payload):
    return {'ok': True, 'pid': os.getpid(), 'protocol': PROTOCOL, 'script': SCRIPT,
            'configured_port': self.configured_port, 'device': self.port.device}

  def stop(self, header, payload):
    self.stopping = True
    return {'ok': True}


def write_message(wfile, header, payload=b''):
  wfile.write(json.dumps(dict(header, length=len(payload))).encode() + b'\n' + payload)
  wfile.flush()


def read_message(rfile):
  line = rfile.readline()
  if not line:
    raise EOFError('connection closed')
  header = json.loads(line)
  payload = rfile.read(header.get('length', 0))
  if len(payload) < header.get('length', 0):
    raise EOFError('message truncated')
  return header, payload


def request(socket_path, header, payload=b''):
  """Send one request to the daemon and return its reply. Raises NotRunning if nothing is listening."""
  sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
  try:
    sock.connect(socket_path)
  except (FileNotFoundError, ConnectionRefusedError) as e:
    sock.close()
    raise NotRunning(socket_path) from e
  with sock, sock.makefile('rwb') as f:
    write_message(f, header, payload)
    response, _ = read_message(f)
  del response['length']
  return response


def bind_listener(socket_path):
  listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
  listener.bind(socket_path)
  os.chmod(socket_path, 0o600)
  listener.listen()
  return listener


def handle_connection(listener, daemon):
  conn, _ = listener.accept()
  with conn:
    conn.settimeout(CLIENT_TIMEOUT)
    try:
      with conn.makefile('rwb') as f:
        header, payload = read_message(f)
        write_message(f, daemon.handle(header, payload))
    except (OSError, EOFError, ValueError) as e:
      log.info('bad request: %s', e)


def serve(listener, daemon, poll_interval=POLL_INTERVAL):
  socket_path = listener.getsockname()
  try:
    while not daemon.stopping:
      daemon.poll()
      ready, _, _ = select.select([listener], [], [], poll_interval)
      if ready:
        handle_connection(listener, daemon)
  finally:
    daemon.port.close()
    listener.close()
    os.unlink(socket_path)


def main(argv):
  parser = argparse.ArgumentParser(description='Hold a USB serial port open for transfer.py.')
  parser.add_argument('--socket', default=default_socket_path())
  parser.add_argument('--port', help='serial device (default: the only USB serial device)')
  args = parser.parse_args(argv)

  logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', stream=sys.stderr)

  lock = open(args.socket + '.lock', 'w')
  try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
  except BlockingIOError:
    log.info('another serial daemon holds %s; exiting', args.socket)
    return 0
  if os.path.exists(args.socket):
    os.unlink(args.socket)    # stale: its daemon no longer holds the lock
  listener = bind_listener(args.socket)
  signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

  log.info('started: pid %d, protocol %d, %s, socket %s', os.getpid(), PROTOCOL, SCRIPT, args.socket)
  holder = PortHolder(lambda: find_usb_serial_port(args.port), open_serial, device_identity)
  serve(listener, Daemon(holder, args.port))
  log.info('stopped')
  return 0


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
