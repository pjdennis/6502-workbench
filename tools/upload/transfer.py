"""Sends a binary to a board's serial loader: length, payload and checksum (see upload_frame.py).

Uploads go through serial_daemon.py, which holds the port open so that opening it doesn't reset
the board; the daemon is started on first use. See tools/README.md.

Usage: transfer.py --baudrate=N [--stopbits=1|2] [--port=DEVICE] [--noreset] [--wait] [--direct] FILE
       transfer.py --daemon status|stop
"""
import argparse
import os
import subprocess
import sys
import time

import serial_daemon
from upload_frame import build_frame

AUTOSTART_TIMEOUT = 5  # seconds allowed for a newly started daemon to accept connections


class Failure(Exception):
  pass


def parse_args(argv):
  parser = argparse.ArgumentParser(description="Send a binary to a board's serial loader.")
  parser.add_argument('file', nargs='?')
  parser.add_argument('--baudrate', type=int)
  parser.add_argument('--stopbits', type=int, choices=[1, 2], default=1)
  parser.add_argument('--port', help='serial device (default: the only USB serial device)')
  parser.add_argument('--noreset', action='store_true', help="don't pulse DTR to reset the board first")
  parser.add_argument('--wait', action='store_true', help='return only once the upload has had time to send')
  parser.add_argument('--direct', action='store_true',
                      help='open the port here instead of using the daemon (on Linux, opening the port '
                           'resets the board); always waits, since closing the port straight after '
                           'writing can lose data')
  parser.add_argument('--daemon', choices=['status', 'stop'], help='report on or stop the serial daemon')
  args = parser.parse_args(argv)
  if args.daemon is None and (args.file is None or args.baudrate is None):
    parser.error('a file and --baudrate are required')
  return args


def spawn_daemon(socket_path, port):
  log_path = socket_path + '.log'
  with open(log_path, 'a') as log:
    subprocess.Popen([sys.executable, serial_daemon.SCRIPT, '--socket', socket_path] +
                     (['--port', port] if port else []),
                     stdin=subprocess.DEVNULL, stdout=log, stderr=log, cwd='/', start_new_session=True)
  print('Started the serial daemon (log: {})'.format(log_path), file=sys.stderr)


def request_starting_daemon(socket_path, header, payload, start_daemon):
  try:
    return serial_daemon.request(socket_path, header, payload)
  except serial_daemon.NotRunning:
    start_daemon()
  deadline = time.monotonic() + AUTOSTART_TIMEOUT
  while True:
    try:
      return serial_daemon.request(socket_path, header, payload)
    except serial_daemon.NotRunning:
      if time.monotonic() > deadline:
        raise Failure('the serial daemon did not start; see {}.log'.format(socket_path))
      time.sleep(0.05)


def daemon_command(command, socket_path):
  try:
    response = serial_daemon.request(socket_path, {'op': command})
  except serial_daemon.NotRunning:
    print('The serial daemon is not running ({})'.format(socket_path))
    return
  if command == 'status':
    print('The serial daemon is running: pid {pid}, protocol {protocol}, {script}'.format(**response))
    print('  port: {}; open device: {}'.format(response['configured_port'] or 'auto-detect',
                                               response['device'] or 'none'))
  else:
    deadline = time.monotonic() + AUTOSTART_TIMEOUT
    while os.path.exists(socket_path) and time.monotonic() < deadline:
      time.sleep(0.05)
    print('Stopped the serial daemon')


def send_direct(args, frame):
  with serial_daemon.open_serial(serial_daemon.find_usb_serial_port(args.port)) as ser:
    # Always wait: closing the port straight after writing can lose data
    serial_daemon.transmit(ser, frame, not args.noreset, args.baudrate, args.stopbits, wait=True)


def main(argv, socket_path=None, start_daemon=None):
  args = parse_args(argv)
  socket_path = socket_path or serial_daemon.default_socket_path()
  try:
    if args.daemon:
      daemon_command(args.daemon, socket_path)
      return 0
    with open(args.file, 'rb') as f:
      frame = build_frame(f.read())
    if args.direct:
      send_direct(args, frame)
      return 0
    header = {'protocol': serial_daemon.PROTOCOL, 'op': 'send', 'reset': not args.noreset,
              'baudrate': args.baudrate, 'stopbits': args.stopbits, 'wait': args.wait, 'port': args.port}
    response = request_starting_daemon(socket_path, header, frame,
                                       start_daemon or (lambda: spawn_daemon(socket_path, args.port)))
    if not response['ok']:
      raise Failure(response['error'])
    return 0
  except (Failure, serial_daemon.NoDevice, OSError, ValueError, EOFError) as e:
    print('Error: {}'.format(e), file=sys.stderr)
    return 1


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
