"""The compiler's files use no Lathe keyword as a name.

Each file will be rewritten in Lathe with the same names for its functions, parameters and
variables. A name such as `end`, `type` or `word` could not be kept: Lathe reserves it.
"""
import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lathec_support as support  # noqa: E402
import test_layers  # noqa: E402

KEYWORDS = set(
    'and asm at bool break byte case const continue critical do downto elif else end enum '
    'extern for forward func if import in inline int interrupt loop mod module not nozp of or '
    'pub record recursive return rows sbyte static then to type until var while word zp '
    'long'.split())


MARKER = 'RECURSIVE'    # not a variable: the list of a file's recursive functions that
#                         lathe/host/README.md asks for, which become `recursive` functions


def names_made(source):
    """Every name a file defines, as (name, line): functions, parameters and variables."""
    made = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef):
            made.append((node.name, node.lineno))
            made.extend((a.arg, node.lineno) for a in node.args.args)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id != MARKER:
            made.append((node.id, node.lineno))
    return made


class NamesTest(unittest.TestCase):
    def test_the_check_sees_functions_parameters_and_variables(self):
        made = names_made('end = 1\ndef word(at):\n    to = at\n    return to\n')
        self.assertEqual(sorted(name for name, _ in made), ['at', 'end', 'to', 'word'])

    def test_the_list_of_recursive_functions_is_not_a_name(self):
        self.assertEqual(names_made('RECURSIVE = ["f"]\ndef f():\n    f()\n'), [('f', 2)])

    def test_no_name_is_a_lathe_keyword(self):
        problems = []
        for module in test_layers.LAYERS:
            if module == 'env':
                continue
            with open(os.path.join(support.HOST, module + '.py')) as f:
                source = f.read()
            problems += ['%s.py:%d: %s' % (module, line, name)
                         for name, line in names_made(source) if name.lower() in KEYWORDS]
        self.assertEqual(problems, [])

    def test_no_two_names_in_a_file_differ_only_in_case(self):
        # Lathe folds case, so `DIGITS` and `digits` would be one name.
        problems = []
        for module in test_layers.LAYERS:
            if module == 'env':
                continue
            with open(os.path.join(support.HOST, module + '.py')) as f:
                spellings = {name for name, _ in names_made(f.read())}
            folded = sorted(name.lower() for name in spellings)
            problems += ['%s.py: %s' % (module, name) for name in set(folded) if folded.count(name) > 1]
        self.assertEqual(problems, [])


if __name__ == '__main__':
    unittest.main()
