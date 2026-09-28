"""The upload formats the boards' serial loaders expect. 2-byte fields are little-endian.

Format 1 (firmware/lib/serial/upload_and_run.inc): a 2-byte length, the payload, then its 2-byte
BSD checksum.

Format 3 (firmware/lib/serial/upload_v3.inc, Michael; docs/michael-upload-format-3-plan.md): all
the metadata first, then the data, stored from STREAM_START_3 so that one entry's data lands at
RAM_START:

  header:  version (1) = 3   start address (2; NO_START = don't run anything)   count (1)
           header checksum (2)   data checksum (2)
  entries: count x (address (2), length (2), flags (1; ENTRY_ZERO_FILL = no data: clear length
           bytes))
  data:    each entry's data, in entry order

The header checksum is the BSD sum of the header's bytes in order, less its own two; the data
checksum that of all the data. Entries ascend by address without overlapping, each within zero
page or RAM_START..LIMIT, and the stream must end by LIMIT. The loader moves each entry's data
down or up to its address once it has all arrived. On the wire every byte is bit-reversed, since
the 6522's shift register takes bits most-significant first.
"""
import argparse
import re
import sys
from typing import NamedTuple

MAX_PAYLOAD = 0xffff

NO_START = 0xffff
RAM_START = 0x0200          # Michael: from the end of the stack page...
LIMIT = 0x3f00              # ...to the receive handler's page
VERSION_3 = 3
ENTRY_ZERO_FILL = 0x01
HEADER_3_LENGTH = 8         # version, start address, count, header checksum, data checksum
ENTRY_LENGTH = 5            # address, length, flags
STREAM_START_3 = RAM_START - HEADER_3_LENGTH - ENTRY_LENGTH  # one entry's data lands at RAM_START
MAX_ENTRIES = 32            # Michael's loader's table
ZERO_RUN = 64               # zeros at least this long become a zero-fill entry
ZERO_PAGE = (0x0000, 0x0100)
LOAD_ADDRESS = 0x2000       # Where a binary loads unless told: Michael's programs' usual .org
                            # (base_config_v2.inc's PROGRAM_LOAD_ADDRESS)


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


def join_runs(runs):
  """(address, bytes) runs sorted, those that adjoin joined."""
  joined = []
  for address, data in sorted(runs):
    if joined and joined[-1][0] + len(joined[-1][1]) == address:
      joined[-1] = (joined[-1][0], joined[-1][1] + data)
    else:
      joined.append((address, data))
  return joined


def read_srec(text):
  """The data in S-record text (vasm -Fsrec -exec) as sorted (address, bytes) runs, adjacent
  records joined, and the start address (None if not given: vasm writes 0)."""
  widths = {1: 2, 2: 3, 3: 4, 7: 4, 8: 3, 9: 2}
  runs = []
  start = None
  for line in text.split():
    if len(line) < 4 or line[0] != 'S' or not line[1].isdigit():
      raise ValueError('not an S-record: {}'.format(line))
    kind, record = int(line[1]), bytes.fromhex(line[2:])
    if record[0] != len(record) - 1:
      raise ValueError('bad S-record length: {}'.format(line))
    if sum(record) & 0xff != 0xff:
      raise ValueError('bad S-record checksum: {}'.format(line))
    if kind in (0, 5, 6):
      continue
    if kind not in widths:
      raise ValueError('unsupported S-record type {}'.format(kind))
    width = widths[kind]
    address = int.from_bytes(record[1:1 + width], 'big')
    if kind <= 3:
      runs.append((address, record[1 + width:-1]))
    else:
      start = address or None
  return join_runs(runs), start


class Block(NamedTuple):
  address: int
  data: bytes = b''
  fill: int = 0             # for a zero-fill entry: how many bytes to clear

  @property
  def length(self):
    return self.fill or len(self.data)


def pack_entries(segments, max_entries=MAX_ENTRIES, areas=(ZERO_PAGE, (RAM_START, LIMIT)),
                 stream_start=STREAM_START_3, limit=LIMIT):
  """Format 3 entries for (address, bytes) segments. Writing zeros where nothing was asked for is
  harmless, so: zero page is one entry; segments no more than an entry apart merge, zeros
  between; runs of ZERO_RUN zeros or more are zero-filled; then, while there are more than
  max_entries, the neighbours whose merging sends the fewest extra bytes merge."""
  pieces = []  # (area, Block)
  for address, data in join_runs(segment for segment in segments if segment[1]):
    end = address + len(data)
    area = next((area for area in areas if area[0] <= address and end <= area[1]), None)
    if area is None:
      raise ValueError('${:04X}-${:04X} is outside {}'.format(
        address, end - 1, ', '.join('${:04X}-${:04X}'.format(start, stop - 1) for start, stop in areas)))
    if pieces:
      previous_area, previous = pieces[-1]
      gap = address - previous.address - previous.length
      if gap < 0:
        raise ValueError('segments overlap at ${:04X}'.format(address))
      if previous_area == area and (area == ZERO_PAGE or gap <= ENTRY_LENGTH):
        pieces[-1] = (area, merge_entries(previous, Block(address, data)))
        continue
    pieces.append((area, Block(address, data)))
  if not pieces:
    raise ValueError('nothing to upload')
  pieces = [(area, entry) for area, block in pieces
            for entry in ([block] if area == ZERO_PAGE else zero_fill_runs(block))]
  while len(pieces) > max_entries:
    pairs = [i for i in range(len(pieces) - 1) if pieces[i][0] == pieces[i + 1][0]]
    if not pairs:
      raise ValueError('more than {} entries'.format(max_entries))
    i = min(pairs, key=lambda i: merge_cost(pieces[i][1], pieces[i + 1][1]))
    pieces[i:i + 2] = [(pieces[i][0], merge_entries(pieces[i][1], pieces[i + 1][1]))]
  entries = [entry for area, entry in pieces]
  end = stream_start + HEADER_3_LENGTH + ENTRY_LENGTH * len(entries) + sum(len(e.data) for e in entries)
  if end > limit:
    raise ValueError('the upload would run to ${:04X}, past ${:04X}'.format(end - 1, limit - 1))
  return entries


def zero_fill_runs(block):
  """block as entries, its runs of ZERO_RUN zeros or more zero-filled."""
  entries = []
  done = 0
  for zeros in re.finditer(rb'\x00{%d,}' % ZERO_RUN, block.data):
    if zeros.start() > done:
      entries.append(Block(block.address + done, block.data[done:zeros.start()]))
    entries.append(Block(block.address + zeros.start(), fill=zeros.end() - zeros.start()))
    done = zeros.end()
  if done < len(block.data):
    entries.append(Block(block.address + done, block.data[done:]))
  return entries


def merge_entries(first, second):
  """One entry from first to the end of second, zeros between (zero-fill if both are)."""
  span = second.address + second.length - first.address
  if first.fill and second.fill:
    return Block(first.address, fill=span)
  data = (first.data or bytes(first.fill)) + bytes(second.address - first.address - first.length)
  return Block(first.address, data + (second.data or bytes(second.fill)))


def merge_cost(first, second):
  """The extra bytes sent when first and second merge."""
  return len(merge_entries(first, second).data) - len(first.data) - len(second.data)


def build_upload_3(entries, start):
  """A format 3 upload of entries (as it goes on the wire before bit reversal)."""
  data = b''.join(entry.data for entry in entries)
  table = b''.join(entry.address.to_bytes(2, 'little') + entry.length.to_bytes(2, 'little') +
                   bytes([ENTRY_ZERO_FILL if entry.fill else 0]) for entry in entries)
  fixed = bytes([VERSION_3]) + start.to_bytes(2, 'little') + bytes([len(entries)])
  rest = bsd_checksum(data).to_bytes(2, 'little') + table
  return fixed + bsd_checksum(fixed + rest).to_bytes(2, 'little') + rest + data


def format_3(segments, start=None, max_entries=MAX_ENTRIES):
  """(address, bytes) segments as a format 3 upload on the wire: packed, built and bit-reversed.
  The start address defaults to the lowest address outside zero page."""
  entries = pack_entries(segments, max_entries)
  if start is None:
    start = min((entry.address for entry in entries if entry.address >= ZERO_PAGE[1]), default=NO_START)
  return reverse_bits(build_upload_3(entries, start))


def read_upload(path, load_address):
  """A file's (address, bytes) segments and start address (None if it doesn't say): S-records
  (.s19, .srec) give their own addresses, a binary loads at load_address."""
  with open(path, 'rb') as f:
    contents = f.read()
  if path.endswith(('.s19', '.srec')):
    return read_srec(contents.decode('ascii'))
  return [(load_address, contents)], None


def main(argv):
  """Writes a file as a format 3 upload, as it goes on the wire (e.g. for the emulator's
  --serial-input)."""
  parser = argparse.ArgumentParser(description='Write a format 3 upload of a binary or S-record file.')
  parser.add_argument('file')
  parser.add_argument('output')
  parser.add_argument('--load-address', type=lambda text: int(text, 16), default=LOAD_ADDRESS,
                      help='where a binary loads, in hex (default %04x)' % LOAD_ADDRESS)
  parser.add_argument('--start', type=lambda text: int(text, 16),
                      help="where to run it, in hex (default: the file's start address, else its "
                           "lowest address; ffff: don't)")
  args = parser.parse_args(argv)
  with open(args.output, 'wb') as f:
    f.write(encode(args.file, args.load_address, args.start))


def encode(path, load_address, start):
  """A file as a format 3 upload on the wire; start, if not None, overrides the file's."""
  segments, file_start = read_upload(path, load_address)
  return format_3(segments, file_start if start is None else start)


if __name__ == '__main__':
  main(sys.argv[1:])
