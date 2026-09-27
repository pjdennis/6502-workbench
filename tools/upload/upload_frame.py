"""The upload format the boards' serial loaders expect (firmware/lib/serial/upload_and_run.inc):
a 2-byte little-endian length, the payload, then its 2-byte little-endian BSD checksum."""

MAX_PAYLOAD = 0xffff


# BSD checksum as calculated by cksum -o 1 (sum -r)
def bsd_checksum(data):
  checksum = 0
  for byte in data:
    checksum = (checksum >> 1) | (checksum << 15)
    checksum = (checksum + byte) & 0xffff
  return checksum


def build_frame(payload):
  if len(payload) > MAX_PAYLOAD:
    raise ValueError("cannot transfer more than 0x{:x} bytes".format(MAX_PAYLOAD))
  return len(payload).to_bytes(2, 'little') + bytes(payload) + bsd_checksum(payload).to_bytes(2, 'little')


# Time on the wire for nbytes (start + 8 data + stop bits each), allowing for 2% transfer speed loss
def send_duration(nbytes, baudrate, stopbits):
  return nbytes * (1 + 8 + stopbits) / baudrate * 1.02
