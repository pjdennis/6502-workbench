"""The compiler's files form layers: each imports only files below it.

Lathe forbids import cycles (docs/language.md, "Modules"), so the host compiler, which is to
be rewritten in Lathe file for file, must not have one either. Python would allow it.
"""
import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lathec_support as support  # noqa: E402

# Lowest first: the order of the table in lathe/host/README.md.
LAYERS = ['env', 'err', 'kernel', 'src', 'lex', 'typetab', 'fold', 'fbuf', 'out', 'reg', 'cond',
          'gen', 'asmblock', 'inline', 'expr', 'decl', 'lathec']


def imports(module):
    with open(os.path.join(support.HOST, module + '.py')) as f:
        tree = ast.parse(f.read())
    return [alias.name for node in tree.body if isinstance(node, ast.Import) for alias in node.names]


class LayersTest(unittest.TestCase):
    def test_each_file_imports_only_files_below_it(self):
        for level, module in enumerate(LAYERS):
            if module == 'env':
                continue                    # ordinary Python: it imports Python's own modules
            for imported in imports(module):
                self.assertIn(imported, LAYERS[:level], '%s imports %s' % (module, imported))


if __name__ == '__main__':
    unittest.main()
