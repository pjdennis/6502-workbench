"""A variable with no initial value is undefined until the program assigns it (language.md,
"Declarations"), and nothing clears memory at start-up: every run of a compiled program in the
suite starts with RAM that is not 0 (the emulator's --fill-ram, passed by the shared helpers,
boards.FILL), so that a program which relies on 0 fails here and not on a board.

This checks the helpers: a program that reads its unset variables, and a table, sees bytes that
are not 0 on the default machine, Wendy 2 with files and the BBC, through build.run_program (what
the corpus and `build.py --run` use) and src_support.run (the twins' test programs); and every
board's command line, and the BBC's module runs, carry the option.
"""
import os
import shutil
import tempfile
import unittest

import src_support as support

import boards
import build

PROGRAM = '''\
; Reads variables nothing assigns: memory as the program finds it.
module unset

import {io}

var flag: byte
var count: word
var table: [40]byte

pub func main()
  var zeros: byte = 0
  var i: byte = 0
  while i < 40 do
    if table[i] == 0 then
      zeros += 1
    end
    i += 1
  end
  if flag == 0 then
    zeros += 1
  end
  if count == 0 then
    zeros += 1
  end
  {io}.put_byte('0' + zeros)
  {io}.put_byte(10)
end
'''

HAVE_TOOLS = os.path.isfile(boards.EMULATOR) and os.path.isfile(build.COMPILER)


@unittest.skipUnless(HAVE_TOOLS, 'emulator or compiler missing')
class Unset(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lathe-unset-')
        self.source = os.path.join(self.dir, 'unset.lth')
        self.write('host')

    def write(self, io):
        with open(self.source, 'w') as f:
            f.write(PROGRAM.format(io=io))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_program_finds_memory_that_is_not_0(self):
        for env, io in (('host', 'host'), ('wendy2disk', 'disk'), ('bbc', 'host')):
            with self.subTest(env=env):
                self.write(io)
                image = os.path.join(self.dir, env, 'unset.bin')
                os.makedirs(os.path.dirname(image))
                build.build(self.source, image, env, keep=os.path.join(self.dir, env, 'work'))
                self.assertEqual(build.run_program(image, env), (0, b'0\n', b''))

    def test_the_twins_test_programs_run_so_too(self):
        image = os.path.join(self.dir, 'twin.bin')
        build.build(self.source, image, support.ENV, keep=os.path.join(self.dir, 'twin'))
        status, out, err, cycles = support.run(image)
        self.assertEqual((status, out), (0, b'0\n'))

    def test_every_run_carries_the_option(self):
        self.assertEqual(boards.FILL, ('--fill-ram',))
        for name, board in boards.BOARDS.items():
            with self.subTest(board=name):
                self.assertIn('--fill-ram', boards.command(board, 'x.bin', 0x4000, self.dir))


if __name__ == '__main__':
    unittest.main()
