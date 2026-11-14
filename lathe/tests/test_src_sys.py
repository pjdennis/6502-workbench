"""lathe/src/sys.lth, the Lathe counterpart of env.py, through lathe/src/copytest.lth: arguments,
files read and written, the error output and the exit status."""
import os
import shutil
import tempfile
import unittest

import src_support as support


class SysTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-src-sys-')
        cls.image = support.build_program('copytest', cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_a_file_is_copied_byte_for_byte(self):
        data = bytes(range(256)) * 5 + b'end'
        source = os.path.join(self.dir, 'in.bin')
        target = os.path.join(self.dir, 'out.bin')
        with open(source, 'wb') as fh:
            fh.write(data)
        status, out, err, _ = support.run(self.image, [source, target])
        self.assertEqual(status, 0)
        self.assertEqual(err, b'!')
        with open(target, 'rb') as fh:
            self.assertEqual(fh.read(), data)
        self.assertEqual(out, b'2 %c %c\n' % (ord('0') + len(source), ord('0') + len(target)))

    def test_an_empty_file_copies_to_an_empty_file(self):
        source = os.path.join(self.dir, 'e')
        target = os.path.join(self.dir, 'f')
        open(source, 'wb').close()
        status, _, _, _ = support.run(self.image, [source, target])
        self.assertEqual(status, 0)
        self.assertEqual(os.path.getsize(target), 0)

    def test_arguments_are_counted_and_copied(self):
        status, out, _, _ = support.run(self.image, ['a', 'bcd', 'ef'])
        self.assertEqual(out, b'3 1 3 2\n')
        self.assertEqual(status, 2)         # no file called a

    def test_a_missing_input_is_status_2(self):
        status, _, err, _ = support.run(self.image, [os.path.join(self.dir, 'none'), 'x'])
        self.assertEqual((status, err), (2, b''))

    def test_an_output_that_cannot_be_created_is_status_3(self):
        source = os.path.join(self.dir, 'g')
        open(source, 'wb').close()
        status, _, _, _ = support.run(self.image, [source, os.path.join(self.dir, 'no', 'such')])
        self.assertEqual(status, 3)


if __name__ == '__main__':
    unittest.main()
