"""How small the texts of the tools' errors can be packed: each scheme measured, to the byte, on
the real texts (lathe/docs/spikes.md, "Error messages back in the ROM, measured").

    python3 lathe/tests/msg_pack_report.py

The texts are those the host tools print, lathe/host/err.py's and lathe/host/lk_err.py's
MESSAGES (lathe/host/driver/msgpack.py reads them). Each tool's texts are taken in number order
from 1, every number up to its last, a number with no text as an empty one; "both" is the
compiler's texts and then the linker's, in one table, sharing the packing's tables. Every scheme
ends a text with a code of its own (a zero byte, or a symbol), so that a reader finds text n by
passing n - 1 ends: no index. The bytes are the data alone (the packed texts and the scheme's
tables); the decoders are measured where they are built (spikes.md).

Schemes:

- raw: the bytes, each text ended by a zero.
- packed N-bit: the 2^N - 2 commonest characters as N-bit codes, one code for the end and one
  that escapes to a whole byte; the table of the characters.
- huffman: a Huffman code of the characters and the end; the table is canonical, a count for
  each length and the symbols in code order, a byte each.
- words N: a dictionary of at most N words (a word or the start of one, with or without the
  space after it) chosen greedily, each the one that saves most; a word is one byte, $80 + its number; the dictionary is the
  words one after another, the last byte of each marked by bit 7.
- words N + huffman: the same, then a Huffman code over the bytes.
- bpe N: byte pair encoding, at most N pairs: the commonest pair of codes takes the next code
  ($80 to $FF, then $01 to $1F), until none is used three times; two bytes of table a pair.
- bpe N + huffman: the same, then a Huffman code over the codes.

The last lines: what leaving out the texts of the linker's errors that are no longer reported
(38, 55 and 56) would save, packed.
"""
import collections
import heapq
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'host', 'driver'))
sys.path.insert(0, os.path.join(HERE, '..', 'host'))

import msgpack  # noqa: E402

LINKER_RETIRED = (38, 55, 56)       # lk_err.py: no longer reported


def texts(part, leave_out=()):
    """[bytes] of a tool's texts in number order from 1 ('c' the compiler, 'l' the linker)."""
    found = msgpack.compiler_texts() if part == 'c' else msgpack.linker_texts()
    return [b'' if n in leave_out else found.get(n, b'') for n in range(1, max(found) + 1)]


# ---- Huffman ---------------------------------------------------------------------------------

def huffman_lengths(freq):
    """The code length of each symbol of {symbol: count}."""
    heap = [(c, i, (s,)) for i, (s, c) in enumerate(sorted(freq.items()))]
    heapq.heapify(heap)
    lengths = collections.Counter()
    k = len(heap)
    while len(heap) > 1:
        c1, _, a = heapq.heappop(heap)
        c2, _, b = heapq.heappop(heap)
        for s in a + b:
            lengths[s] += 1
        heapq.heappush(heap, (c1 + c2, k, a + b))
        k += 1
    return dict(lengths)


def huffman(seqs):
    """Bytes of a Huffman code of the sequences, each ended by an end symbol: (stream, table)."""
    freq = collections.Counter()
    for s in seqs:
        freq.update(s)
        freq[-1] += 1                   # the end
    lengths = huffman_lengths(freq)
    bits = sum(freq[s] * lengths[s] for s in freq)
    return (bits + 7) // 8, max(lengths.values()) + len(lengths)


# ---- Packed alphabets ------------------------------------------------------------------------

def packed(seqs, bits):
    """(stream, table) of a packed alphabet of 2^bits codes."""
    freq = collections.Counter(c for s in seqs for c in s)
    common = {c for c, _ in freq.most_common(2 ** bits - 2)}
    total = sum((bits if c in common else bits + 8) for s in seqs for c in s) + bits * len(seqs)
    return (total + 7) // 8, len(common)


# ---- A dictionary of words -------------------------------------------------------------------

def words(seqs, most):
    """Greedy word dictionary: ([word], the sequences with each word a code from 128). A word is
    letters from the start of a word (a whole word or its start), with or without one space
    after; each step takes the one that saves most, counted without overlaps."""
    seqs = [list(s) for s in seqs]
    chosen = []
    while len(chosen) < most:
        count = collections.Counter()
        for s in seqs:
            seen = {}
            for i in range(len(s)):
                if s[i] >= 128 or not chr(s[i]).isalpha():
                    continue
                if i > 0 and s[i - 1] < 128 and chr(s[i - 1]).isalpha():
                    continue                # not the start of a word
                j = i
                while j < len(s) and s[j] < 128 and chr(s[j]).isalpha():
                    j += 1
                    if j - i >= 2:
                        count[bytes(s[i:j])] += 1
                if j < len(s) and s[j] == 32 and j - i >= 1:
                    count[bytes(s[i:j + 1])] += 1
        best, gain = None, 0
        for w, c in count.items():
            g = c * (len(w) - 1) - len(w)
            if g > gain:
                best, gain = w, g
        if best is None:
            break
        code = 128 + len(chosen)
        chosen.append(best)
        new = []
        for s in seqs:
            out, i = [], 0
            while i < len(s):
                n = len(best)
                if bytes(s[i:i + n]) == best and all(c < 128 for c in s[i:i + n]):
                    out.append(code)
                    i += n
                else:
                    out.append(s[i])
                    i += 1
            new.append(out)
        seqs = new
    return chosen, seqs


# ---- Byte pair encoding ----------------------------------------------------------------------

def bpe(seqs, most):
    """Byte pair encoding: (number of pairs, the sequences)."""
    seqs = [list(s) for s in seqs]
    pairs = 0
    while pairs < most:
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
        code = 0x80 + pairs if pairs < 128 else pairs - 127
        pairs += 1
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
    return pairs, seqs


def ended(seqs):
    return sum(len(s) + 1 for s in seqs)


def schemes(seqs):
    """[(scheme, data bytes)] for the sequences."""
    rows = [('raw', ended(seqs))]
    for bits in (5, 6):
        stream, table = packed(seqs, bits)
        rows.append((f'packed {bits}-bit', stream + table))
    stream, table = huffman(seqs)
    rows.append(('huffman', stream + table))
    for most in (64, 96, 128):
        chosen, coded = words(seqs, most)
        dictionary = sum(map(len, chosen))
        rows.append((f'words {most}', dictionary + ended(coded)))
        stream, table = huffman(coded)
        rows.append((f'words {most} + huffman', dictionary + stream + table))
    for most in (128, 159):
        pairs, coded = bpe(seqs, most)
        rows.append((f'bpe {most}', 2 * pairs + ended(coded)))
        stream, table = huffman(coded)
        rows.append((f'bpe {most} + huffman', 2 * pairs + stream + table))
    return rows


def main():
    c, l = texts('c'), texts('l')
    print('compiler: %d texts (numbers 1 to %d), %d bytes of text; linker: %d texts, %d bytes' % (
        sum(1 for t in c if t), len(c), sum(map(len, c)), len(l), sum(map(len, l))))
    print('%-22s %9s %9s %9s %9s' % ('scheme', 'compiler', 'linker', 'apart', 'both'))
    rows = zip(schemes(c), schemes(l), schemes(c + l))
    for (name, cn), (_, ln), (_, bn) in rows:
        print('%-22s %9d %9d %9d %9d' % (name, cn, ln, cn + ln, bn))
    lr = texts('l', LINKER_RETIRED)
    for name in ('bpe 159',):
        before = dict(schemes(c + l))[name]
        after = dict(schemes(c + lr))[name]
        print(f'{name}, both, without the texts of link errors {LINKER_RETIRED}: {after} ({before - after} less)')


if __name__ == '__main__':
    main()
