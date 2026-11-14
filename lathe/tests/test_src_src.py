"""lathe/src/src.lth against lathe/host/src.py: lathe/src/srctest.lth reads a file through the
source stack, with a source in memory pushed over it for a while; host_run() below does the
same with src.py, line for line, and the outputs and error reports must match."""
import io
import os
import shutil
import tempfile
import unittest

import src_support as support
import lathec_support  # noqa: F401  (puts lathe/host on the path)
import env
import err
import kernel
import src

HEX = b'0123456789ABCDEF'
TEXT = b'ab\ncd'
TEXT_AT = 0x9000


def put_hex(b):
    env.put_byte(HEX[b >> 4])
    env.put_byte(HEX[b & 15])


def put_word(w):
    put_hex((w >> 8) & 0xFF)
    put_hex(w & 0xFF)


def show():
    put_hex(src.ch)
    env.put_byte(0x20)
    put_word(src.line)
    env.put_byte(0x20)
    put_word(src.col)
    if src.eof:
        env.put_byte(ord('E'))
    env.put_byte(10)


def main():
    err.init()
    kernel.init()
    src.init()
    file = kernel.keep_argument(0)
    mode = kernel.keep_argument(1)
    if not src.open_file(file):
        err.fatal(err.E_OPEN_SOURCE)
    for _ in range(5):
        show()
        src.advance()
    if env.mem[mode] == ord('e'):
        for _ in range(5):
            src.advance()
        err.position(src.line, src.col)
        err.fatal(err.E_BAD_CHAR)
    text, _ = lathec_support.put_text(TEXT, TEXT_AT)
    src.open_memory(text, text + 5)
    if env.mem[mode] == ord('o'):
        while True:
            src.open_memory(text, text + 5)
    put_hex(src.depth)
    env.put_byte(10)
    while not src.eof:
        show()
        src.advance()
    show()
    src.advance()
    show()
    src.close()
    show()
    total = 0
    while not src.eof:
        total = (total + src.ch) & 0xFFFF
        total ^= src.line
        total = (total + src.col) & 0xFFFF
        src.advance()
    put_word(total)
    env.put_byte(10)
    show()
    src.close()
    put_hex(src.depth)
    env.put_byte(10)
    env.exit(0)


def host_run(args):
    lathec_support.fresh()
    env._out = io.BytesIO()
    env.start(args)
    try:
        main()
    except SystemExit as e:
        status = e.code
    return status, env._out.getvalue(), env._err.getvalue()


class SrcTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-src-src-')
        cls.image = support.build_program('srctest', cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def check(self, data, mode):
        path = os.path.join(self.dir, 'input.txt')
        with open(path, 'wb') as fh:
            fh.write(data)
        status, out, text, _ = support.run(self.image, [path, mode])
        self.assertEqual((status, out, text), host_run([path, mode]))
        return status

    def test_a_file_with_a_memory_source_over_it(self):
        self.assertEqual(self.check(b'line one\nline two\n\n\tthree\r\nfour', 'n'), 0)

    def test_a_file_ending_with_a_line_feed(self):
        self.assertEqual(self.check(b'x\ny\n' * 100, 'n'), 0)

    def test_a_file_shorter_than_five_characters(self):
        self.assertEqual(self.check(b'ab', 'n'), 0)

    def test_an_empty_file(self):
        self.assertEqual(self.check(b'', 'n'), 0)

    def test_too_many_sources(self):
        self.assertEqual(self.check(b'0123456789', 'o'), 1)

    def test_an_error_is_reported_in_the_file(self):
        self.assertEqual(self.check(b'abc\ndefghijkl', 'e'), 1)

    def test_a_missing_file(self):
        status, out, text, _ = support.run(self.image, [os.path.join(self.dir, 'none'), 'n'])
        expected = host_run([os.path.join(self.dir, 'none'), 'n'])
        self.assertEqual((status, out, text), expected)
        self.assertEqual(status, 1)


if __name__ == '__main__':
    unittest.main()
