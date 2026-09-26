"""Tests for tools/upload/compile_and_upload_<board>.sh, with python3 replaced by a stub that records
the arguments transfer.py would get.

Run from the repo root:  python3 -m unittest discover -s tools/tests -v
Requires vasm6502_oldstyle on PATH (tests skip otherwise).
"""
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
UPLOAD = os.path.normpath(os.path.join(HERE, '..', 'upload'))

HAVE_VASM = shutil.which('vasm6502_oldstyle') is not None

PYTHON_STUB = '#!/bin/sh\necho "$@" > "$STUB_LOG"\n'


@unittest.skipUnless(HAVE_VASM, 'vasm6502_oldstyle not on PATH')
class UploadScriptTest(unittest.TestCase):
  def setUp(self):
    self.dir = tempfile.mkdtemp()
    self.addCleanup(shutil.rmtree, self.dir)
    bin_dir = os.path.join(self.dir, 'bin')
    os.mkdir(bin_dir)
    stub = os.path.join(bin_dir, 'python3')
    with open(stub, 'w') as f:
      f.write(PYTHON_STUB)
    os.chmod(stub, 0o755)
    self.log = os.path.join(self.dir, 'transfer-args')
    self.env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ['PATH'], STUB_LOG=self.log)
    self.write('prog.s', '  .org $5000\n  nop\n')

  def write(self, name, text):
    with open(os.path.join(self.dir, name), 'w') as f:
      f.write(text)

  def run_script(self, board, *args):
    """Returns (exit status, transfer.py's arguments or None if it wasn't run)."""
    result = subprocess.run([os.path.join(UPLOAD, 'compile_and_upload_{}.sh'.format(board)), *args],
                            cwd=self.dir, env=self.env, capture_output=True, text=True)
    if not os.path.exists(self.log):
      return result.returncode, None
    with open(self.log) as f:
      script, *transfer_args = f.read().split()
    self.assertEqual(script, os.path.join(UPLOAD, 'transfer.py'))
    return result.returncode, transfer_args

  def test_wendy2(self):
    self.assertEqual(self.run_script('wendy2', 'prog.s'), (0, ['--baudrate=115200', 'a.out']))

  def test_wendy2_noreset(self):
    self.assertEqual(self.run_script('wendy2', '--noreset', 'prog.s'),
                     (0, ['--baudrate=115200', '--noreset', 'a.out']))

  def test_options_may_follow_the_program(self):
    self.assertEqual(self.run_script('wendy2', 'prog.s', '--noreset'),
                     (0, ['--baudrate=115200', '--noreset', 'a.out']))

  def test_other_transfer_options_are_passed_on(self):
    self.assertEqual(self.run_script('wendy2', '--wait', 'prog.s'),
                     (0, ['--baudrate=115200', '--wait', 'a.out']))

  def test_michael(self):
    self.assertEqual(self.run_script('michael', 'prog.s'), (0, ['--baudrate=57600', 'a.out']))

  def test_michael_noreset(self):
    self.assertEqual(self.run_script('michael', '--noreset', 'prog.s'),
                     (0, ['--baudrate=57600', '--noreset', 'a.out']))

  def test_wendy_opens_the_port_directly_without_a_reset(self):
    # Wendy has no DTR reset, so doesn't need the daemon; --direct always waits for the data to send
    self.assertEqual(self.run_script('wendy', 'prog.s'),
                     (0, ['--baudrate=115200', '--direct', '--noreset', 'a.out']))

  def test_assembles_to_a_out(self):
    self.run_script('wendy2', 'prog.s')
    with open(os.path.join(self.dir, 'a.out'), 'rb') as f:
      self.assertEqual(f.read(), b'\xea')

  def test_program_with_spaces_in_its_path(self):
    self.write('my prog.s', '  .org $5000\n  nop\n')
    self.assertEqual(self.run_script('wendy2', 'my prog.s'), (0, ['--baudrate=115200', 'a.out']))

  def test_assembly_error_skips_the_upload(self):
    self.write('bad.s', '  lda #UNDEFINED\n')
    status, transfer_args = self.run_script('wendy2', 'bad.s')
    self.assertNotEqual(status, 0)
    self.assertIsNone(transfer_args)

  def test_program_required(self):
    status, transfer_args = self.run_script('wendy2', '--noreset')
    self.assertNotEqual(status, 0)
    self.assertIsNone(transfer_args)

  def test_only_one_program(self):
    self.write('other.s', '  nop\n')
    status, transfer_args = self.run_script('wendy2', 'prog.s', 'other.s')
    self.assertNotEqual(status, 0)
    self.assertIsNone(transfer_args)

  def test_no_separate_noreset_script(self):
    self.assertFalse(os.path.exists(os.path.join(UPLOAD, 'compile_and_upload_wendy2_noreset.sh')))


if __name__ == '__main__':
  unittest.main()
