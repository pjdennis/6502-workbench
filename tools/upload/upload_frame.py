"""The upload formats the boards' serial loaders expect. 2-byte fields are little-endian.

Format 1 (firmware/lib/serial/upload_and_run.inc): a 2-byte length, the payload, then its 2-byte
BSD checksum.

Format 2 (firmware/lib/serial/upload_v2.inc, Michael): a header, then blocks, every control byte
ahead of the data it describes, so that the loader can store the whole stream from RAM_START - 10
and the first block's data lands at RAM_START:

  header:  version (1) = 2    start address (2; NO_START = don't run anything)
  block:   length (2)   load address (2)   checksum (2)   flags (1)   data (length bytes)
  flags:   MORE = more blocks follow; ZERO_FILL = no data bytes: clear length bytes

Blocks are in ascending address order, don't overlap, lie within RAM_START..LIMIT, and never move
down: each block's data goes to a load address at or above where it sits in the stream. A block's
checksum is the BSD sum of the stream from the end of the previous block (or the start of the
upload) to the end of its data, less its own two checksum bytes. On the wire every byte is
bit-reversed, since the 6522's shift register takes bits most-significant first.
"""
import argparse
import sys
from typing import NamedTuple

MAX_PAYLOAD = 0xffff

VERSION_2 = 2
NO_START = 0xffff
MORE = 0x01
ZERO_FILL = 0x02
HEADER_LENGTH = 3
BLOCK_HEADER_LENGTH = 7
RAM_START = 0x0200          # Michael: from the end of the stack page...
LIMIT = 0x3f00              # ...to the receive handler's page


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


def reverse_bits(data):
  return bytes(int('{:08b}'.format(byte)[::-1], 2) for byte in data)


def read_intel_hex(text):
  """The data in Intel HEX text (vasm -Fihex) as sorted (address, bytes) runs, adjacent records
  joined."""
  runs = []
  for line in text.split():
    if not line.startswith(':'):
      raise ValueError('not an Intel HEX record: {}'.format(line))
    record = bytes.fromhex(line[1:])
    if sum(record) & 0xff:
      raise ValueError('bad Intel HEX record checksum: {}'.format(line))
    length, address, kind, data = record[0], record[1] << 8 | record[2], record[3], record[4:-1]
    if len(data) != length:
      raise ValueError('bad Intel HEX record length: {}'.format(line))
    if kind == 1:
      break
    if kind != 0:
      raise ValueError('unsupported Intel HEX record type {}'.format(kind))
    runs.append((address, data))
  runs.sort()
  joined = []
  for address, data in runs:
    if joined and joined[-1][0] + len(joined[-1][1]) == address:
      joined[-1] = (joined[-1][0], joined[-1][1] + data)
    else:
      joined.append((address, data))
  return joined


class Block(NamedTuple):
  address: int
  data: bytes = b''
  fill: int = 0             # for a ZERO_FILL block: how many bytes to clear

  @property
  def length(self):
    return self.fill or len(self.data)


def pack_blocks(segments, ram_start=RAM_START, limit=LIMIT):
  """Format 2 blocks for (address, bytes) segments: a segment that would have to move down (too
  close to the one before for its block header) joins that one, the gap filled with zeros."""
  if not segments:
    raise ValueError('nothing to upload')
  blocks = []
  stream = ram_start - BLOCK_HEADER_LENGTH  # where the next block header goes in the stream
  for address, data in sorted(segments):
    if blocks and address < blocks[-1].address + blocks[-1].length:
      raise ValueError('segments overlap at ${:04X}'.format(address))
    if address < ram_start:
      raise ValueError('${:04X} is below ${:04X}'.format(address, ram_start))
    if address + len(data) > limit:
      raise ValueError('${:04X}-${:04X} runs past ${:04X}'.format(address, address + len(data) - 1, limit - 1))
    if blocks and address < stream + BLOCK_HEADER_LENGTH:
      previous = blocks.pop()
      gap = address - (previous.address + previous.length)
      stream -= BLOCK_HEADER_LENGTH + previous.length
      address, data = previous.address, previous.data + bytes(gap) + data
    blocks.append(Block(address, data))
    stream += BLOCK_HEADER_LENGTH + len(data)
  return blocks


def build_upload(blocks, start):
  """A format 2 upload of blocks (as they go on the wire before bit reversal)."""
  upload = bytearray([VERSION_2]) + start.to_bytes(2, 'little')
  covered_from = 0
  for i, block in enumerate(blocks):
    flags = (MORE if i < len(blocks) - 1 else 0) | (ZERO_FILL if block.fill else 0)
    fields = block.length.to_bytes(2, 'little') + block.address.to_bytes(2, 'little')
    covered = bytes(upload[covered_from:]) + fields + bytes([flags]) + block.data
    upload += fields + bsd_checksum(covered).to_bytes(2, 'little') + bytes([flags]) + block.data
    covered_from = len(upload)
  return bytes(upload)


def format_2(segments, start=None, ram_start=RAM_START, limit=LIMIT):
  """(address, bytes) segments as a format 2 upload on the wire: packed, built and bit-reversed.
  The start address defaults to the lowest address."""
  blocks = pack_blocks(segments, ram_start, limit)
  return reverse_bits(build_upload(blocks, blocks[0].address if start is None else start))


def read_segments(path, load_address):
  """A file's (address, bytes) segments: an Intel HEX file (.hex) gives its own addresses, a
  binary loads at load_address."""
  with open(path, 'rb') as f:
    contents = f.read()
  if path.endswith('.hex'):
    return read_intel_hex(contents.decode('ascii'))
  return [(load_address, contents)]


def main(argv):
  """Writes a file as a format 2 upload, as it goes on the wire (e.g. for the emulator's
  --serial-input)."""
  parser = argparse.ArgumentParser(description='Write a format 2 upload of a binary or Intel HEX file.')
  parser.add_argument('file')
  parser.add_argument('output')
  parser.add_argument('--load-address', type=lambda text: int(text, 16), default=RAM_START,
                      help='where a binary loads, in hex (default 0200)')
  parser.add_argument('--start', type=lambda text: int(text, 16),
                      help="where to run it, in hex (default: its lowest address; ffff: don't)")
  args = parser.parse_args(argv)
  with open(args.output, 'wb') as f:
    f.write(format_2(read_segments(args.file, args.load_address), args.start))


if __name__ == '__main__':
  main(sys.argv[1:])
