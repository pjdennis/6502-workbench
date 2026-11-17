#!/usr/bin/env python3
"""The message file: the texts of the compiler's and the linker's errors, for the tools in the
BBC's ROM forms, which do not hold them (lathe/docs/bbc.md, "The message file").

    python3 lathe/host/driver/msgfile.py -o LATHERR

The texts are those of lathe/host/err.py (MESSAGES, a line `number text` each) and
lathe/host/lk_err.py (MESSAGES, the text of error n on line n), the tables the host tools print
from, so the file always says what the host tools say. One file serves both tools:

    0     the compiler's index, low bytes: byte n is the low byte of where the text of error n
          starts in the file
    256   the compiler's index, high bytes
    512   the linker's index, low bytes, for link error n
    768   the linker's index, high bytes
    1024  the texts: each what follows the number in the error's line (": " and the text), ended
          by a zero; first ": " alone, where every number with no text points; then the
          compiler's texts by number, then the linker's

So a tool finds a text by number with three seeks and nothing to work out: byte n of its index's
low bytes, byte n of its high bytes, then the text, which it writes up to its zero (the end of
the file reads as a zero too, so a file cut short ends the text). Every entry points into the
file, so the tool checks nothing. On a disc a seek costs nothing by itself: a filing system reads
the sector that holds the byte asked for, so an error's text costs three sectors read (the low
byte's, the high byte's and the text's, one more if the text runs into the next sector), not the
37 of the whole file. The tools open the file as NAME, in the current directory (and drive): a
name without a `.`, which the BBC's mapping of names (bbcfs.py) leaves as it is, so that it is
the same file on the DFS (`$.LATHERR`), on ADFS and in the emulator's directory, and the compiler
can open it without the mapping (lathe/src/err.lth).
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOST = os.path.dirname(HERE)
if HOST not in sys.path:
    sys.path.insert(0, HOST)

import err  # noqa: E402
import lk_err  # noqa: E402

NAME = 'LATHERR'
ENTRIES = 256                   # an entry for every byte, so that no number is outside
COMPILER, LINKER = 0, 1         # the parts: low bytes at 512 * part, high bytes 256 after them
TEXTS = 4 * ENTRIES
SEPARATOR = b': '               # between the number and the text, as the tools write it


def compiler_texts():
    """{number: text} of err.MESSAGES."""
    found = {}
    for line in err.MESSAGES.split(b'\n')[:-1]:
        number, text = line.split(b' ', 1)
        found[int(number)] = text
    return found


def linker_texts():
    """{number: text} of lk_err.MESSAGES, whose line n is the text of error n."""
    return {n: text for n, text in enumerate(lk_err.MESSAGES.split(b'\n')[:-1], 1)}


def contents():
    """The bytes of the message file."""
    places = [TEXTS] * (2 * ENTRIES)
    texts = bytearray(SEPARATOR + b'\0')
    for part, found in ((COMPILER, compiler_texts()), (LINKER, linker_texts())):
        for number in sorted(found):
            if number >= ENTRIES or 0 in found[number]:
                raise ValueError(f'part {part}: error {number} cannot be in the file')
            places[part * ENTRIES + number] = TEXTS + len(texts)
            texts += SEPARATOR + found[number] + b'\0'
    if TEXTS + len(texts) > 0x10000:
        raise ValueError('the texts are more than 64 KB')
    data = bytearray()
    for part in (COMPILER, LINKER):
        mine = places[part * ENTRIES:(part + 1) * ENTRIES]
        data += bytes(at & 0xFF for at in mine) + bytes(at >> 8 for at in mine)
    return bytes(data + texts)


def text(data, part, number):
    """What follows error `number` of `part` in its line, from the file `data`, read as the tools
    read it: b': text', or b': ' for a number with no text."""
    start = data[2 * ENTRIES * part + number] | data[2 * ENTRIES * part + ENTRIES + number] << 8
    end = start
    while end < len(data) and data[end] != 0:
        end += 1
    return data[start:end]


def write(path):
    with open(path, 'wb') as fh:
        fh.write(contents())


def main(argv):
    ap = argparse.ArgumentParser(prog='msgfile.py', description='Write the message file of the '
                                 'Lathe tools\' ROM forms on the BBC.')
    ap.add_argument('-o', dest='out', default=NAME, help='the file to write (%(default)s)')
    a = ap.parse_args(argv)
    write(a.out)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
