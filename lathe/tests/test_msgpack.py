"""The packed texts of the errors (lathe/host/driver/msgpack.py; lathe/docs/bbc.md, "The texts
in the module"): what every module image holds and the module writes when a tool's ROM form asks.

- Every text of both tools, unpacked as the module unpacks it, is what the host tools print after
  the number: the compiler's error n is text n, the linker's error n text 255 - n, and every
  other number is an empty text.
- The two ranges of numbers cannot meet: the packer refuses texts where they would.
- The tables are as the module reads them: 160 entries of first and second codes, the texts each
  ended by a zero, every pair within the module's depth, no byte of a text outside $20-$7E.
- The asm text of the tables is what bbcrom.py appends to the module's code.
- The twins' own texts (lathe/src/err.lth, lk_err.lth, which every build but the BBC's ROM forms
  holds) are the host's tables too, so every form of a tool says the same.

The runs on the emulated BBC: every text the module writes in test_bbc_rom.py and
test_bbc_rom128.py, the tools' errors in test_bbc_texts.py.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import src_support as support  # noqa: E402
import msgpack  # noqa: E402
import err  # noqa: E402
import lk_err  # noqa: E402


def host_compiler_texts():
    """{number: text} as err.py prints them."""
    found = {}
    for line in err.MESSAGES.split(b'\n')[:-1]:
        number, text = line.split(b' ', 1)
        found[int(number)] = text
    return found


def host_linker_texts():
    """{number: text} as lk_err.py prints them: line n is error n."""
    return {n: t for n, t in enumerate(lk_err.MESSAGES.split(b'\n')[:-1], 1)}


def twin_texts(name, first):
    """The texts of the twin lathe/src/NAME.lth's tables: the lines of its string constants from
    the one named `first` to the end of the run of them."""
    with open(os.path.join(support.SRC, name)) as f:
        text = f.read()
    start = text.index('const ' + first)
    lines = []
    for line in text[start:].split('\n'):
        m = re.match(r'\s*(?:const \w+(?: in \w+)? = )?"(.*)\\n"\s*$', line)
        if not m:
            if lines and line.startswith('const MESSAGES'):
                continue
            break
        lines.append(m.group(1).replace('\\"', '"').encode('latin-1'))
    return lines


class Texts(unittest.TestCase):
    def test_the_texts_are_the_hosts(self):
        texts = msgpack.texts()
        self.assertEqual(len(texts), 256)
        compiler, linker = host_compiler_texts(), host_linker_texts()
        for n in range(256):
            if n in compiler:
                self.assertEqual(texts[n], compiler[n], n)
            elif 255 - n in linker:
                self.assertEqual(texts[n], linker[255 - n], n)
            else:
                self.assertEqual(texts[n], b'', n)

    def test_every_text_unpacks_to_the_hosts(self):
        first, second, codes = msgpack.pack(msgpack.texts())
        for n, (text, coded) in enumerate(zip(msgpack.texts(), codes)):
            self.assertEqual(msgpack.unpack(first, second, coded), text, n)
            self.assertNotIn(0, coded)

    def test_the_ranges_cannot_meet(self):
        saved = msgpack.compiler_texts
        try:
            msgpack.compiler_texts = lambda: {**saved(), 255 - max(msgpack.linker_texts()): b'x'}
            with self.assertRaises(ValueError):
                msgpack.texts()
        finally:
            msgpack.compiler_texts = saved

    def test_a_text_holds_only_printable_characters(self):
        saved = msgpack.linker_texts
        try:
            msgpack.linker_texts = lambda: {**saved(), 1: b'a\x80b'}
            with self.assertRaises(ValueError):
                msgpack.texts()
        finally:
            msgpack.linker_texts = saved


    def test_the_twins_hold_the_hosts_texts(self):
        self.assertEqual(b''.join(t + b'\n' for t in twin_texts('err.lth', 'MESSAGES_1')), err.MESSAGES)
        self.assertEqual(b''.join(t + b'\n' for t in twin_texts('lk_err.lth', 'MESSAGES')), lk_err.MESSAGES)


class Tables(unittest.TestCase):
    def test_the_tables_are_as_the_module_reads_them(self):
        first, second, codes = msgpack.pack(msgpack.texts())
        self.assertEqual((len(first), len(second)), (msgpack.PAIRS, msgpack.PAIRS))
        self.assertLessEqual(msgpack.depth(first, second), msgpack.DEPTH)
        for c in first + second:
            self.assertNotEqual(c, 0)       # a pair's codes are characters or pairs, never the end
        _, size = msgpack.tables()
        self.assertEqual(size, 2 * msgpack.PAIRS + sum(len(c) + 1 for c in codes))

    def test_the_asm_text_holds_the_tables(self):
        text, size = msgpack.tables()
        values = []
        for line in text.splitlines():
            if line.strip().startswith('.byte'):
                values += [int(v.strip().lstrip('$'), 16) for v in line.split('.byte', 1)[1].split(',')]
        self.assertEqual(len(values), size)
        for label in ('text_first:', 'text_second:', 'text_texts:'):
            self.assertIn(label + '\n', text)


if __name__ == '__main__':
    unittest.main()
