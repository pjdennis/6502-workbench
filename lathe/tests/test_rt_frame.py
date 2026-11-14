"""lathe/rt/rt_frame.lth, the frame stack of recursive functions: it holds 255 bytes, and a
push that would overflow it stops the program in the loop at rt_frame.overflow. (Each level of
a recursion also takes two bytes of the 6502's own stack for its JSR, so a frame of one byte
would run out of that first.)"""
import os
import re
import shutil
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'host', 'driver'))

import boards  # noqa: E402
import build  # noqa: E402
import mapenv  # noqa: E402

# Each level of count saves three bytes, its parameter and a word: count(n) pushes 3 * n.
COUNT = textwrap.dedent('''\
    module deep
    import host
    var result: byte
    recursive func count(n: byte): byte
      var spare: word = n
      if n == 0 then
        return 0
      end
      return count(n - 1) + lo(spare) - n + 1
    end
    pub func main()
      result = count(%d)
      host.put_byte(result)
    end
    ''')

# Each level of count saves two bytes; 200 levels is more than the stack holds.
TOO_DEEP = textwrap.dedent('''\
    module deep
    var result: word
    recursive func count(n: word): word
      if n == 0 then
        return 0
      end
      return count(n - 1) + 1
    end
    pub func main()
      result = count(200)
    end
    ''')


@unittest.skipUnless(os.path.isfile(build.COMPILER) and os.path.isfile(build.EMULATOR),
                     'needs the compiler and emulator/emulator.out')
class FrameStack(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lathe-rt-frame-')
        self.addCleanup(shutil.rmtree, self.dir, True)

    def program(self, text):
        path = os.path.join(self.dir, 'deep.lth')
        with open(path, 'w') as fh:
            fh.write(text)
        return path

    def test_the_stack_holds_255_bytes(self):
        image = os.path.join(self.dir, 'deep.bin')
        build.build(self.program(COUNT % 85), image, keep=os.path.join(self.dir, 'work'))
        self.assertEqual(build.run_program(image), (0, bytes([85]), b''))

    def test_a_push_too_many_stops_the_program_in_the_overflow_loop(self):
        image = os.path.join(self.dir, 'deep.bin')
        work = os.path.join(self.dir, 'work')
        build.build(self.program(TOO_DEEP), image, 'michael', keep=work)
        with self.assertRaises(boards.RunError) as caught:
            build.run_program(image, 'michael')
        pc = int(re.search(r'at \$([0-9A-F]{4})', str(caught.exception)).group(1), 16)
        loop = [e for e in mapenv.read_map(os.path.join(work, 'deep.map')) if e.name == 'rt_frame.overflow']
        self.assertEqual(len(loop), 1)
        self.assertTrue(loop[0].addr <= pc < loop[0].addr + loop[0].size, str(caught.exception))


if __name__ == '__main__':
    unittest.main()
