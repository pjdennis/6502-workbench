"""Tests for tools/reorg/create_tags.sh against a throwaway local 'origin'."""
import os
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'reorg', 'create_tags.sh'))


def git(cwd, *args):
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class CreateTagsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.remote = os.path.join(self.tmp, 'remote.git')
        seed = os.path.join(self.tmp, 'seed')
        git(self.tmp, 'init', '-q', '--bare', '-b', 'main', self.remote)
        git(self.tmp, 'init', '-q', '-b', 'main', seed)
        for k, v in (('user.email', 't@example.com'), ('user.name', 'T')):
            git(seed, 'config', k, v)
        shas = []
        for msg in ('one', 'two', 'three'):
            with open(os.path.join(seed, 'f'), 'a') as f:
                f.write(msg + '\n')
            git(seed, 'add', 'f'); git(seed, 'commit', '-q', '-m', msg)
            shas.append(git(seed, 'rev-parse', 'HEAD'))
        self.one, self.two, self.three = shas
        git(seed, 'push', '-q', self.remote, 'main')
        self.clone = os.path.join(self.tmp, 'clone')
        git(self.tmp, 'clone', '-q', self.remote, self.clone)
        for k, v in (('user.email', 't@example.com'), ('user.name', 'T')):
            git(self.clone, 'config', k, v)
        self.tags = os.path.join(self.tmp, 'tags.txt')
        with open(self.tags, 'w') as f:
            f.write(f'# tag commit message\nm/one {self.one} First\n\narchive/x {self.two} Tip of x\n')

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_script(self, *args):
        env = dict(os.environ, TAG_FILES=self.tags)
        return subprocess.run(['bash', SCRIPT, *args], cwd=self.clone, env=env,
                              capture_output=True, text=True)

    def remote_tags(self):
        out = git(self.remote, 'for-each-ref', '--format=%(refname:short) %(*objectname)', 'refs/tags')
        return dict(l.split() for l in out.splitlines())

    def test_dry_run_creates_nothing(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('DRY RUN', result.stdout)
        self.assertEqual(self.remote_tags(), {})
        self.assertEqual(git(self.clone, 'tag'), '')

    def test_apply_creates_and_pushes_annotated_tags(self):
        result = self.run_script('--apply')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.remote_tags(), {'m/one': self.one, 'archive/x': self.two})
        self.assertEqual(git(self.clone, 'cat-file', '-t', 'm/one'), 'tag')

    def test_rerun_is_harmless(self):
        self.run_script('--apply')
        result = self.run_script('--apply')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(self.remote_tags()), 2)

    def test_refuses_unknown_commit_before_creating_anything(self):
        with open(self.tags, 'a') as f:
            f.write('bad/tag ' + '0' * 40 + ' Missing\n')
        result = self.run_script('--apply')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.remote_tags(), {})
        self.assertEqual(git(self.clone, 'tag'), '')


if __name__ == '__main__':
    unittest.main()
