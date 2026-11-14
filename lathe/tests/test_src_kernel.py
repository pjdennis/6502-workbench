"""lathe/src/kernel.lth against lathe/host/kernel.py: lathe/src/kerneltest.lth runs a fixed set
of operations and prints what they give; host_run() below does the same operations with
kernel.py, line for line, and the two outputs, files written and error reports must match."""
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

HEX = b'0123456789ABCDEF'
TEXT = b'Some text\n'
TEXT_AT = 0x9000            # where host_run puts the constant texts in env.mem


def put_hex(b):
    env.put_byte(HEX[b >> 4])
    env.put_byte(HEX[b & 15])


def put_word(w):
    put_hex((w >> 8) & 0xFF)
    put_hex(w & 0xFF)
    env.put_byte(0x20)


def nl():
    env.put_byte(10)


def name(text):
    kernel.name_begin()
    for c in text:
        kernel.name_add(c)
    return kernel.name_end()


def numbered(k):
    return name(bytes([ord('n'), ord('0') + (k >> 8), ord('0') + ((k >> 4) & 15),
                       ord('0') + (k & 15)]))


def names():
    a = name(b'count')
    put_word(a)
    put_word(name(b'put_byte'))
    put_word(name(b'count'))
    put_word(kernel.name_top)
    nl()
    total = sum(numbered(k) for k in range(300)) & 0xFFFF
    again = sum(numbered(k) for k in range(300)) & 0xFFFF
    put_word(total)
    put_word(again)
    put_word(kernel.name_top)
    a = name(b'a' * 31 + b'xyz')
    put_word(a)
    put_word(name(b'a' * 31 + b'q'))
    put_hex(kernel.name_length(a))
    env.put_byte(0x20)
    put_hex(kernel.name_char(a, 30))
    nl()
    kernel.name_set_token(name(b'while'), 77)
    put_hex(kernel.name_token(name(b'while')))
    put_hex(kernel.name_token(name(b'count')))
    nl()


def symbols():
    n = name(b'main')
    put_word(kernel.sym_add(kernel.SCOPE_MODULE, n, kernel.K_FUNC))
    put_word(kernel.sym_add(1, n, kernel.K_VAR))
    put_word(kernel.sym_find(1, n)[0])
    s, found = kernel.sym_find(2, n)
    put_word(s)
    if found:
        env.put_byte(ord('?'))
    put_word(kernel.sym_lookup(n)[0])
    put_word(kernel.member_add(3, 4))
    put_word(kernel.member_add(5, 6))
    nl()
    kernel.scope_begin()
    mark = kernel.name_top
    s = kernel.sym_add(kernel.SCOPE_LOCAL, n, kernel.K_LOCAL)
    t = kernel.sym_add(kernel.SCOPE_LOCAL, name(b'i'), kernel.K_LOCAL)
    put_word(s)
    put_word(t)
    put_word(kernel.sym_lookup(n)[0])
    put_word(kernel.name_top - mark)
    kernel.scope_end()
    put_word(kernel.sym_lookup(n)[0])
    put_word(kernel.name_top - mark)
    put_word(kernel.sym_count)
    put_hex(kernel.module_add(n))
    put_hex(kernel.module_add(name(b'other')))
    nl()


def streams(given, made):
    text, _ = lathec_support.put_text(TEXT, TEXT_AT)
    s = kernel.open_memory(text, text + 3)
    put_hex(s)
    put_word(kernel.get_word(s))
    b, at_end = kernel.get(s)
    put_hex(b)
    b, at_end = kernel.get(s)
    if at_end:
        env.put_byte(ord('E'))
    put_word(kernel.get_word(s))
    kernel.close(s)
    s, ok = kernel.open_in(given)
    put_hex(s)
    count = total = 0
    while True:
        b, at_end = kernel.get(s)
        if at_end:
            break
        count += 1
        total += b
    put_word(count & 0xFFFF)
    put_word(total & 0xFFFF)
    kernel.close(s)
    s, ok = kernel.open_out(made)
    put_hex(s)
    kernel.put(s, ord('A'))
    kernel.put_word(s, 0x1234)
    kernel.put_name(s, name(b'main'))
    kernel.close(s)
    s, ok = kernel.open_in(text)
    if not ok:
        env.put_byte(ord('N'))
    nl()


def paths(given):
    kernel.path_begin()
    kernel.path_add_text(given)
    kernel.path_add(ord('/'))
    kernel.path_add_name(name(b'module'))
    p = kernel.path_end()
    while env.mem[p] != 0:
        env.put_byte(env.mem[p])
        p += 1
    put_word(kernel.text_reserve(10) - kernel.path)
    nl()


def main():
    err.init()
    kernel.init()
    given = kernel.keep_argument(0)
    made = kernel.keep_argument(1)
    mode = kernel.keep_argument(2)
    put_word(made - given)
    put_word(mode - given)
    nl()
    if env.mem[mode] == ord('f'):
        k = 0
        while True:
            k += 1
            name(b'long_names_fill_the_heap_')
            name(bytes([ord('x'), k & 0xFF, (k >> 8) & 0xFF]))
    elif env.mem[mode] == ord('s'):
        k = 0
        while True:
            put_word(kernel.sym_add(0, numbered(k), kernel.K_VAR))
            k += 1
    elif env.mem[mode] == ord('d'):
        kernel.sym_add(0, name(b'twice'), kernel.K_VAR)
        kernel.sym_add(0, name(b'twice'), kernel.K_VAR)
    elif env.mem[mode] == ord('p'):
        kernel.path_begin()
        while True:
            kernel.path_add(ord('x'))
    names()
    symbols()
    streams(given, made)
    paths(given)
    env.exit(0)


def host_run(args):
    """main() on the host: (status, output, error output)."""
    lathec_support.fresh()
    env._out = io.BytesIO()
    env.start(args)
    try:
        main()
    except SystemExit as e:
        status = e.code
    return status, env._out.getvalue(), env._err.getvalue()


class KernelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-src-kernel-')
        cls.image = support.build_program('kerneltest', cls.dir)
        cls.input = os.path.join(cls.dir, 'input.txt')
        with open(cls.input, 'wb') as fh:
            fh.write(bytes(range(256)) * 3 + b'tail')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def check(self, mode):
        made = os.path.join(self.dir, 'made-' + mode)      # + L or P: names of one length
        status, out, text, _ = support.run(self.image, [self.input, made + 'L', mode])
        expected = host_run([self.input, made + 'P', mode])
        self.assertEqual((status, out, text), expected)
        self.assertEqual(os.path.exists(made + 'L'), os.path.exists(made + 'P'))
        if os.path.exists(made + 'P'):
            with open(made + 'L', 'rb') as a, open(made + 'P', 'rb') as b:
                self.assertEqual(a.read(), b.read())
        return status

    def test_the_normal_run(self):
        self.assertEqual(self.check('n'), 0)

    def test_a_full_name_heap(self):
        self.assertEqual(self.check('f'), 1)

    def test_a_full_symbol_table(self):
        self.assertEqual(self.check('s'), 1)

    def test_a_name_declared_twice(self):
        self.assertEqual(self.check('d'), 1)

    def test_a_path_too_long(self):
        self.assertEqual(self.check('p'), 1)


if __name__ == '__main__':
    unittest.main()
