"""TXTPACK, the packer of the tools' error texts in Lathe (lathe/src/txtpack.lth; lathe/docs/bbc.md,
"The texts' packer on the BBC"), against its host twin, lathe/host/driver/msgpack.py.

On the emulated BBC (bbc.env's machine, txtpack-bbc.env), `*RUN TXTPACK [-pK/N] err.lth lk_err.lth
OUT` reads the texts from the twins' sources and writes the tables of part K of N:

- On the real texts: every part of every split msgpack.split makes (one to four parts), byte for
  byte the tables msgpack.py makes of it (text_first, text_second, text_texts).
- On texts changed in copies of the sources, each with msgpack.py given the same texts: a text
  added to each tool packs as msgpack packs it; refused as msgpack refuses them, with Exit 2 and
  `txtpack: ...`: the compiler's numbers reaching the linker's, a byte outside $20-$7E, pairs
  nesting deeper than eight levels.
- With LATHE_TXTPACK_REPORT=1, its time for the real texts and its memory.
"""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import src_support as support  # noqa: E402
import boards  # noqa: E402
import build  # noqa: E402
import msgpack  # noqa: E402

HAVE_TOOLS = os.path.isfile(support.EMULATOR) and os.path.isfile(build.COMPILER)
REPORT = os.environ.get('LATHE_TXTPACK_REPORT') == '1'
ENV = os.path.join(support.SRC, 'txtpack-bbc.env')
CAP = 2_000_000_000


def host_tables(first_text, last_text, texts=None):
    """The bytes of msgpack.py's tables of the texts first_text to last_text."""
    first, second, seqs = msgpack.pack((texts or msgpack.texts())[first_text:last_text + 1])
    return bytes(first) + bytes(second) + b''.join(bytes(s) + b'\0' for s in seqs)


class Patched:
    """msgpack.py with texts added, {number: text}, to the compiler's and the linker's (with
    alone, those texts only)."""
    def __init__(self, compiler=None, linker=None, alone=False):
        self.compiler, self.linker, self.alone = compiler or {}, linker or {}, alone

    def __enter__(self):
        self.saved = msgpack.compiler_texts, msgpack.linker_texts
        c, k = self.saved
        if self.alone:
            c = k = dict
        msgpack.compiler_texts = lambda: {**c(), **self.compiler}
        msgpack.linker_texts = lambda: {**k(), **self.linker}
        return self

    def __exit__(self, *exc):
        msgpack.compiler_texts, msgpack.linker_texts = self.saved


def lathe_string(text):
    """text as the lines of a Lathe string constant's pieces, 60 characters a line."""
    out = ''
    for c in text.decode('latin-1'):
        out += '\\x%02X' % ord(c) if ord(c) < 0x20 or ord(c) > 0x7E else ('\\' + c if c in '"\\' else c)
    pieces = [out[i:i + 60] for i in range(0, len(out), 60)] or ['']
    pieces[-1] += '\\n'
    return '\n  '.join('"%s"' % p for p in pieces)


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class OnTheBBC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-txtpack-')
        cls.image = os.path.join(cls.dir, 'TXTPACK')
        build.build(os.path.join(support.SRC, 'txtpack.lth'), cls.image, env=ENV,
                    keep=os.path.join(cls.dir, 'work'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def disc(self, compiler=None, linker=None, alone=False):
        """A disc with err.lth and lk_err.lth, each with the texts given added at its end, as a
        constant of its own (`const MESSAGES_X`, `const MESSAGESX`); with alone, files that hold
        those texts only."""
        disk = tempfile.mkdtemp(dir=self.dir)
        for name, added, form in (('err.lth', compiler, '%d '), ('lk_err.lth', linker, '')):
            text = ''
            if not alone:
                with open(os.path.join(support.SRC, name)) as f:
                    text = f.read()
            for n, t in sorted((added or {}).items()):
                head = (form % n).encode() if form else b''
                text += '\nconst MESSAGES%s_X%d = %s\n' % ('' if form else 'L', n, lathe_string(head + t))
            with open(os.path.join(disk, name), 'w') as f:
                f.write(text)
        return disk

    def pack(self, disk, part=None):
        args = (['-p%d/%d' % part] if part else []) + ['err.lth', 'lk_err.lth', 'OUT']
        status, out, said, cycles = boards.run_mos(boards.BOARDS['bbc'], self.image, disk, args, cap=CAP)
        data = None
        if os.path.exists(os.path.join(disk, 'OUT')):
            with open(os.path.join(disk, 'OUT'), 'rb') as f:
                data = f.read()
        return status, out, data, cycles

    def test_every_part_of_every_split_is_msgpacks(self):
        disk = self.disc()
        for n in range(1, 5):
            for k, (first, last) in enumerate(msgpack.split(n), 1):
                with self.subTest(part='%d/%d' % (k, n)):
                    status, out, data, cycles = self.pack(disk, None if n == 1 else (k, n))
                    self.assertEqual((status, out), (0, b''))
                    self.assertEqual(data, host_tables(first, last))
                    if REPORT and n == 1:
                        print('\nTXTPACK, all the texts: %d cycles, %.1f s at 2 MHz' % (cycles, cycles / 2e6))

    def test_texts_added_pack_as_msgpack_packs_them(self):
        compiler = {185: b'a new "text" of the compiler'}
        linker = {len(msgpack.linker_texts()) + 1: b'and one of the linker\\s'}
        with Patched(compiler, linker):
            want = host_tables(0, 255)
        status, out, data, cycles = self.pack(self.disc(compiler, linker))
        self.assertEqual((status, out), (0, b''))
        self.assertEqual(data, want)

    def refused(self, message, compiler=None, linker=None, alone=False):
        with Patched(compiler, linker, alone):
            with self.assertRaises(ValueError):
                msgpack.pack(msgpack.texts())
        status, out, data, cycles = self.pack(self.disc(compiler, linker, alone))
        self.assertEqual(status, 2)
        self.assertTrue(out.startswith(b'txtpack: ' + message.encode()), out)
        self.assertIsNone(data)

    def test_the_compilers_numbers_may_not_reach_the_linkers(self):
        top = 255 - len(msgpack.linker_texts())
        self.refused("the compiler's errors meet the linker's", compiler={top: b'too far'})

    def test_a_byte_outside_the_printable_ones_is_refused(self):
        self.refused('a text has a byte outside $20-$7E',
                     linker={len(msgpack.linker_texts()) + 1: b'a\x80b'})

    def test_pairs_nested_deeper_than_eight_are_refused(self):
        """Three texts of 512 x's alone: xx, then that twice, and so on, nine levels; of 255 x's,
        eight levels, packed as msgpack packs them."""
        texts = {1: b'x' * 512, 2: b'x' * 512, 3: b'x' * 512}
        self.refused('pairs nest too deeply', compiler={1: b'a'}, linker=texts, alone=True)
        texts = {n: b'x' * 255 for n in texts}
        with Patched({1: b'a'}, texts, alone=True):
            want = host_tables(0, 255)
        status, out, data, cycles = self.pack(self.disc({1: b'a'}, texts, alone=True))
        self.assertEqual((status, out), (0, b''))
        self.assertEqual(data, want)

    @unittest.skipUnless(REPORT, 'LATHE_TXTPACK_REPORT=1 prints it')
    def test_its_memory(self):
        import test_bbc_selfhost as selfhost
        items = selfhost.read_map(os.path.join(self.dir, 'work', 'txtpack.map'))
        fixed = [i for i in items if i[4] is None]
        code = max(i[1] + i[2] for i in fixed if i[0] in 'FTD' and 0x0800 <= i[1] < 0x8000)
        data = [i for i in fixed if i[0] in 'VS' and 0x0800 <= i[1] < 0x8000]
        lo, hi = min(i[1] for i in data), max(i[1] + i[2] for i in data)
        print('\nTXTPACK: code to $%04X, data $%04X-$%04X (%d bytes)' % (code, lo, hi - 1, hi - lo))


if __name__ == '__main__':
    unittest.main()
