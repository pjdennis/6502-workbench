#!/usr/bin/env python3
"""The texts of the compiler's and the linker's errors, packed, for the module image (lathe/docs/
bbc.md, "The texts in the module"): bbcrom.py puts them in the home bank, after the module's own
code, and the module writes one when a tool's ROM form asks for it (lathe/rt/bbc/module.asm, "An
error's text").

    python3 lathe/host/driver/msgpack.py [-o FILE]      the tables as asm text, and their size

The texts are those of lathe/host/err.py (MESSAGES, a line `number text` each) and
lathe/host/lk_err.py (MESSAGES, the text of error n on line n), the tables the host tools print
from, so the module always says what the host tools say.

Which text: the module is asked for text Y, a byte. Text n is the compiler's error n, and text
255 - n the linker's error n, so the two meet only if the compiler's numbers reach the linker's
from the top, which texts() refuses. Every text from 0 to 255 is in the table, a number with no
text as an empty one.

How they are packed: byte pair encoding. A text is its codes, ended by a zero. A code is a
character (the texts have only $20 to $7E) or, for the codes $80 to $FF and $01 to $1F, a pair
of codes, which the tables text_first and text_second give at the code plus $80 (a byte: $80 to
$FF are pairs 0 to 127, $01 to $1F pairs 129 to 159; entry 128, the code $00, is not used), each
a character or a pair again. The pairs are chosen by the texts: the commonest pair of codes in
all the texts takes the next code, until the codes run out or no pair is used three times (a
pair costs two bytes of the tables). The choice is deterministic, so every image holds the same
bytes for the same texts.
"""
import argparse
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOST = os.path.dirname(HERE)
if HOST not in sys.path:
    sys.path.insert(0, HOST)

import err  # noqa: E402
import lk_err  # noqa: E402

TEXTS = 256
PAIRS = 160                     # the tables' length: codes $80-$FF and $01-$1F at code + $80
DEPTH = 8                       # pairs nest at most this deep (the module's stack: 3 bytes a level)


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


def texts():
    """[bytes] of the 256 texts: the compiler's error n at n, the linker's at 255 - n. ValueError
    if the two meet or a text has a byte the packing cannot hold."""
    out = [b''] * TEXTS
    compiler, linker = compiler_texts(), linker_texts()
    if max(compiler) >= TEXTS - 1 - max(linker) or min(compiler) < 1 or min(linker) < 1:
        raise ValueError(f'the compiler\'s errors (to {max(compiler)}) meet the linker\'s (to '
                         f'{max(linker)}, texts {TEXTS - 1 - max(linker)} to {TEXTS - 2})')
    for n, t in compiler.items():
        out[n] = t
    for n, t in linker.items():
        out[TEXTS - 1 - n] = t
    for n, t in enumerate(out):
        if any(c < 0x20 or c > 0x7E for c in t):
            raise ValueError(f'text {n} has a byte outside $20-$7E')
    return out


def code_of(k):
    """The code of pair k: $80 + k for the first 128, then $01 to $1F."""
    return 0x80 + k if k < 128 else k - 127


def pack(items):
    """Byte pair encoding of the texts: (first, second, [codes of each text]); first and second
    have PAIRS entries, at code + $80."""
    seqs = [list(t) for t in items]
    first, second = [0] * PAIRS, [0] * PAIRS
    k = 0
    while k < PAIRS - 1:                # pairs 0 to 158: codes $80-$FF and $01-$1F
        count = collections.Counter()
        for s in seqs:
            i = 0
            while i < len(s) - 1:
                count[(s[i], s[i + 1])] += 1
                i += 2 if s[i] == s[i + 1] and i + 2 < len(s) and s[i + 2] == s[i] else 1
        if not count:
            break
        (a, b), uses = max(count.items(), key=lambda e: (e[1], -e[0][0], -e[0][1]))
        if uses < 3:
            break
        code = code_of(k)
        first[(code + 0x80) & 0xFF], second[(code + 0x80) & 0xFF] = a, b
        new = []
        for s in seqs:
            out, i = [], 0
            while i < len(s):
                if i + 1 < len(s) and s[i] == a and s[i + 1] == b:
                    out.append(code)
                    i += 2
                else:
                    out.append(s[i])
                    i += 1
            new.append(out)
        seqs = new
        k += 1
    for i in range(PAIRS):              # an unused entry: a pair of spaces, never reached
        if first[i] == 0:
            first[i] = second[i] = 0x20
    if depth(first, second) > DEPTH:
        raise ValueError('pairs nest too deeply for the module\'s stack')
    return first, second, seqs


def is_pair(c):
    return c != 0 and (c + 0x80) & 0xFF < PAIRS


def depth(first, second):
    """How deeply the pairs nest: 1 for a pair of two characters."""
    def d(c):
        if not is_pair(c):
            return 0
        i = (c + 0x80) & 0xFF
        return 1 + max(d(first[i]), d(second[i]))
    return max(d(code_of(k)) for k in range(PAIRS - 1))


def unpack(first, second, codes):
    """The text of codes, as the module writes it."""
    out = bytearray()

    def put(c):
        if is_pair(c):
            put(first[(c + 0x80) & 0xFF])
            put(second[(c + 0x80) & 0xFF])
        else:
            out.append(c)
    for c in codes:
        put(c)
    return bytes(out)


def tables(first_text=0, last_text=TEXTS - 1):
    """(the asm text of the tables of the texts first_text to last_text, packed by themselves,
    their bytes), for a part of the texts in a module image (lathe/rt/bbc/texts.asm)."""
    first, second, seqs = pack(texts()[first_text:last_text + 1])
    stream = []
    for s in seqs:
        stream += s + [0]
    lines = [f'; The texts {first_text} to {last_text} of the errors (lathe/host/driver/msgpack.py)',
             'text_first:']
    lines += _bytes(first) + ['text_second:'] + _bytes(second) + ['text_texts:'] + _bytes(stream)
    return '\n'.join(lines) + '\n', len(first) + len(second) + len(stream)


def split(parts):
    """The texts in `parts` parts of about the same length, each a run of numbers: [(first, last)],
    the first part's first 0 and the last part's last 255."""
    lengths = [len(t) + 1 for t in texts()]
    total, cuts, done = sum(lengths), [0], 0
    for n, length in enumerate(lengths):
        if done >= total * len(cuts) / parts and len(cuts) < parts:
            cuts.append(n)
        done += length
    return [(a, b - 1) for a, b in zip(cuts, cuts[1:] + [TEXTS])]


def _bytes(values):
    return ['  .byte ' + ', '.join('$%02X' % v for v in values[i:i + 16]) for i in range(0, len(values), 16)]


def main(argv):
    ap = argparse.ArgumentParser(prog='msgpack.py', description='The packed texts of the Lathe tools\' '
                                 'errors, as the module image holds them.')
    ap.add_argument('-o', dest='out', help='where to write the asm text of the tables (all the texts, one part)')
    a = ap.parse_args(argv)
    text, size = tables()
    if a.out:
        with open(a.out, 'w') as f:
            f.write(text)
    print(f'{size} bytes')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
