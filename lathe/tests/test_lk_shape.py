"""The linker's files follow the rules for host files that test_names.py and test_layers.py
check for the compiler's: no Lathe keyword as a name, no two names in a file that differ only
in case, and no import cycles (each file imports only files above it in LAYERS).
"""
import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_names  # noqa: E402

HOST = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'host'))

# Lowest first.
LAYERS = ['env', 'lk_err', 'lk_op', 'lk_file', 'lk_rec', 'lk_sym', 'lk_envf', 'lk_tab', 'lk_scan',
          'lk_out', 'lk_boot', 'lk_graph', 'lk_alloc', 'lk_fix', 'lk_place', 'lk_map', 'lk_emit', 'link']


def source(module):
    with open(os.path.join(HOST, module + '.py')) as f:
        return f.read()


class LinkerShape(unittest.TestCase):
    def test_every_linker_file_is_in_the_list(self):
        files = sorted(f[:-3] for f in os.listdir(HOST) if f.startswith('lk_') and f.endswith('.py'))
        self.assertEqual(files, sorted(m for m in LAYERS if m.startswith('lk_')))

    def test_each_file_imports_only_files_below_it(self):
        for level, module in enumerate(LAYERS[1:], 1):
            tree = ast.parse(source(module))
            for node in tree.body:
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertIn(alias.name, LAYERS[:level], '%s imports %s' % (module, alias.name))

    def test_no_name_is_a_lathe_keyword(self):
        problems = []
        for module in LAYERS[1:]:
            problems += ['%s.py:%d: %s' % (module, line, name)
                         for name, line in test_names.names_made(source(module))
                         if name.lower() in test_names.KEYWORDS]
        self.assertEqual(problems, [])

    def test_no_two_names_in_a_file_differ_only_in_case(self):
        problems = []
        for module in LAYERS[1:]:
            spellings = {name for name, _ in test_names.names_made(source(module))}
            folded = sorted(name.lower() for name in spellings)
            problems += ['%s.py: %s' % (module, name) for name in set(folded) if folded.count(name) > 1]
        self.assertEqual(problems, [])

    def test_every_file_says_what_it_owns(self):
        for module in LAYERS[1:]:
            tree = ast.parse(source(module))
            self.assertIsNotNone(ast.get_docstring(tree), module)


if __name__ == '__main__':
    unittest.main()
