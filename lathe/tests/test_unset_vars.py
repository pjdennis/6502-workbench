"""lathe/tests/unset_vars.py: the variables a program reads that nothing assigns.

The tool on a small program (what it reports and what it passes over), and over the end-to-end
corpus, where nothing may be reported (each program it found before the corpus gave its
variables initial values failed on memory that is not 0).
"""
import os
import shutil
import tempfile
import unittest

import unset_vars
from unset_vars import build
from test_cases import cases, defines, _name

PROGRAM = '''\
module probe

import host

var never: byte                 ; read, never assigned: reported
var counted: byte               ; only INC: reported (INC reads first)
var stored: byte                ; assigned: not reported
var given: word = 5             ; an initial value is an assignment ($init)
var through: [4]byte            ; its address is taken: passed over
var unread: byte                ; never read: not reported

pub func main()
  var p: ^byte
  counted += 1
  stored = 1
  p = @through
  p[0] = 2
  host.put_byte(never + counted + stored + byte(given) + through[1])
end
'''


@unittest.skipUnless(os.path.isfile(build.COMPILER), 'compiler missing')
class UnsetVars(unittest.TestCase):

    def test_what_it_reports(self):
        d = tempfile.mkdtemp(prefix='lathe-unset-vars-test-')
        try:
            source = os.path.join(d, 'probe.lth')
            with open(source, 'w') as f:
                f.write(PROGRAM)
            self.assertEqual(unset_vars.check(source), ['probe.counted', 'probe.never'])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_nothing_in_the_corpus(self):
        for path in cases('e2e'):
            with self.subTest(program=_name(path)):
                self.assertEqual(unset_vars.check(path, defines=defines(path)), [])


if __name__ == '__main__':
    unittest.main()
