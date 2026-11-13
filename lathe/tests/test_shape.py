"""The host tools must be written in the subset of Python that Lathe can express.

lathe/host/README.md states the rule and why: every file checked here will be rewritten in
Lathe function for function, and both versions must produce the same bytes. This test rejects
the Python constructs that have no Lathe equivalent.

Not checked: lathe/host/env.py (the host interface) and lathe/host/driver/ (build scripts).
"""
import ast
import glob
import os
import unittest

HOST = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'host'))
EXEMPT = ('env.py',)

BANNED_NODES = (
    ast.ClassDef, ast.Dict, ast.Set, ast.ListComp, ast.SetComp, ast.DictComp,
    ast.GeneratorExp, ast.Lambda, ast.Try, ast.Raise, ast.With, ast.Yield, ast.YieldFrom,
    ast.Await, ast.AsyncFunctionDef, ast.JoinedStr, ast.Starred, ast.Nonlocal,
    ast.Slice, ast.Delete, ast.Assert, ast.NamedExpr, ast.IfExp, ast.Match,
)
ALLOWED_CALLS = {'range', 'bytearray', 'len'}


def host_files():
    return sorted(f for f in glob.glob(os.path.join(HOST, '*.py'))
                  if os.path.basename(f) not in EXEMPT)


def check_source(source, name='<test>'):
    """Return a list of 'name:line: message' for every construct outside the subset."""
    tree = ast.parse(source, name)
    problems = []

    def bad(node, message):
        problems.append(f'{name}:{getattr(node, "lineno", 0)}: {message}')

    recursive = set()
    functions = {}
    modules = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'RECURSIVE':
            recursive = {e.value for e in ast.walk(node.value) if isinstance(e, ast.Constant)}
        if isinstance(node, ast.FunctionDef):
            functions[node.name] = node
        if isinstance(node, ast.Import):
            modules.update(a.asname or a.name for a in node.names)

    for node in ast.walk(tree):
        if isinstance(node, BANNED_NODES):
            bad(node, f'{type(node).__name__} is not in the Lathe subset')
        elif isinstance(node, ast.ImportFrom):
            bad(node, 'use "import module" and module.name, not "from ... import"')
        elif isinstance(node, ast.Constant) and isinstance(node.value, (str, float, complex)) \
                and not _is_docstring(node, tree) and not _in_recursive_list(node, tree):
            bad(node, f'{type(node.value).__name__} constant: use ints and b"..." byte strings')
        elif isinstance(node, ast.FunctionDef):
            a = node.args
            if a.defaults or a.kw_defaults or a.vararg or a.kwarg or a.kwonlyargs:
                bad(node, f'{node.name}: default, keyword or variable arguments')
            if node.decorator_list:
                bad(node, f'{node.name}: decorator')
            for inner in ast.walk(node):
                if inner is not node and isinstance(inner, ast.FunctionDef):
                    bad(inner, f'{inner.name}: nested function')
        elif isinstance(node, ast.Call):
            f = node.func
            if node.keywords:
                bad(node, 'keyword argument in a call')
            if isinstance(f, ast.Name):
                if f.id not in functions and f.id not in ALLOWED_CALLS:
                    bad(node, f'call of {f.id}(): not a function of this module')
            elif isinstance(f, ast.Attribute):
                if not (isinstance(f.value, ast.Name) and f.value.id in modules):
                    bad(node, f'method call .{f.attr}(): only module.function() is allowed')
            else:
                bad(node, 'call of a computed function')
        elif isinstance(node, ast.Tuple) and isinstance(node.ctx, ast.Load):
            if len(node.elts) != 2:
                bad(node, 'a function returns at most a value and a bool')
        elif isinstance(node, ast.For):
            it = node.iter
            if not (isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id == 'range'):
                bad(node, 'for loops iterate over range() only')
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.Pow, ast.MatMult)):
            bad(node, 'use // for division; no ** or @')

    # Recursion: a function may call itself, directly or through others, only if listed.
    calls = {name: {c.func.id for c in ast.walk(fn)
                    if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id in functions}
             for name, fn in functions.items()}
    for name in functions:
        if name in recursive:
            continue
        seen, todo = set(), list(calls[name])
        while todo:
            f = todo.pop()
            if f == name:
                bad(functions[name], f'{name} is recursive but is not listed in RECURSIVE')
                break
            if f not in seen and f not in recursive:
                seen.add(f)
                todo.extend(calls[f])
    return problems


def _is_docstring(node, tree):
    for owner in ast.walk(tree):
        if isinstance(owner, (ast.Module, ast.FunctionDef)) and owner.body:
            first = owner.body[0]
            if isinstance(first, ast.Expr) and first.value is node:
                return True
    return False


def _in_recursive_list(node, tree):
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name) \
                and stmt.targets[0].id == 'RECURSIVE':
            return any(n is node for n in ast.walk(stmt.value))
    return False


class ShapeRulesTest(unittest.TestCase):
    """The checker itself: each rule accepts what it should and rejects what it should."""

    def assertClean(self, source):
        self.assertEqual(check_source(source), [])

    def assertRejected(self, source, fragment):
        problems = check_source(source)
        self.assertTrue(any(fragment in p for p in problems), problems)

    def test_plain_functions_and_arrays_pass(self):
        self.assertClean(
            'import kernel\n'
            'N = 4\n'
            'tab = [0] * N\n'
            'buf = bytearray(16)\n'
            'MSG = b"hi"\n'
            'def f(a, b):\n'
            '    """Doc."""\n'
            '    for i in range(0, N):\n'
            '        tab[i] = (a + b) & 0xFF\n'
            '    return kernel.g(a), True\n')

    def test_class_dict_comprehension_and_try_are_rejected(self):
        self.assertRejected('class A:\n    pass\n', 'ClassDef')
        self.assertRejected('d = {}\n', 'Dict')
        self.assertRejected('x = [i for i in range(3)]\n', 'ListComp')
        self.assertRejected('def f():\n    try:\n        pass\n    except Exception:\n        pass\n', 'Try')

    def test_str_constants_are_rejected_but_docstrings_pass(self):
        self.assertRejected('x = "text"\n', 'str constant')
        self.assertClean('"""Module doc."""\ndef f():\n    """Doc."""\n    return 0\n')

    def test_method_calls_are_rejected(self):
        self.assertRejected('xs = [0] * 4\ndef f():\n    xs.append(1)\n', 'method call')

    def test_unlisted_recursion_is_rejected_and_listed_recursion_passes(self):
        self.assertRejected('def f(n):\n    return f(n - 1)\n', 'not listed in RECURSIVE')
        self.assertRejected('def f(n):\n    return g(n)\ndef g(n):\n    return f(n)\n', 'not listed in RECURSIVE')
        self.assertClean('RECURSIVE = ["f"]\ndef f(n):\n    return f(n - 1)\n')

    def test_slices_defaults_and_wide_tuples_are_rejected(self):
        self.assertRejected('b = bytearray(4)\ndef f():\n    return b[1:2]\n', 'Slice')
        self.assertRejected('def f(a=1):\n    return a\n', 'default')
        self.assertRejected('def f():\n    return 1, 2, 3\n', 'at most a value and a bool')


class HostShapeTest(unittest.TestCase):
    def test_host_files_stay_in_the_subset(self):
        problems = []
        for path in host_files():
            with open(path) as f:
                problems += check_source(f.read(), os.path.relpath(path, HOST))
        self.assertEqual(problems, [])


if __name__ == '__main__':
    unittest.main()
