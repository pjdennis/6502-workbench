"""Relative links in the repository's guide documents must point at files that exist.

Covers the root README/CLAUDE, docs/, and the README of each top-level area
(not attic/, and not historical plan/notes documents).
"""
import glob
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
LINK = re.compile(r'\[[^\]]*\]\(([^)\s]+)\)')

GUIDES = ['README.md', 'CLAUDE.md', 'docs/*.md', '*/README.md', '*/*/README.md',
          'asm/CLAUDE.md', 'editor/CLAUDE.md']


def guide_files():
    files = set()
    for pattern in GUIDES:
        files.update(glob.glob(os.path.join(ROOT, pattern)))
    return sorted(f for f in files if not os.path.relpath(f, ROOT).startswith('attic'))


class DocLinksTest(unittest.TestCase):
    def test_guides_exist(self):
        self.assertIn(os.path.join(ROOT, 'README.md'), guide_files())

    def test_relative_links_resolve(self):
        broken = []
        for path in guide_files():
            with open(path) as f:
                for target in LINK.findall(f.read()):
                    if re.match(r'^[a-z]+:', target) or target.startswith('#'):
                        continue
                    target = target.split('#')[0]
                    if not os.path.exists(os.path.join(os.path.dirname(path), target)):
                        broken.append(f'{os.path.relpath(path, ROOT)} -> {target}')
        self.assertEqual(broken, [])


if __name__ == '__main__':
    unittest.main()
