"""lathe/host/driver/build.py: module discovery, and the whole build with a stand-in compiler.

The stand-in (written to a temporary directory) has lathec.py's command line and writes objects
with lo.Builder: an empty module for each source, except that a source whose first line is
`; prints TEXT` gets a main that prints TEXT and a newline. It logs each module it compiles.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
DRIVER = os.path.join(ROOT, 'lathe', 'host', 'driver')
sys.path.insert(0, DRIVER)

import build  # noqa: E402

FAKE_COMPILER = textwrap.dedent('''\
    import os, sys
    sys.path.insert(0, {driver!r})
    import lo
    src, outdir = sys.argv[1], sys.argv[2]
    name = os.path.splitext(os.path.basename(src))[0].lower()
    with open(os.path.join(outdir, 'compiled.log'), 'a') as fh:
        fh.write(name + '\\n')
    first = open(src).readline()
    b = lo.Builder(name)
    if first.startswith('; prints '):
        f = b.func(name + '.main')
        for ch in first[len('; prints '):].rstrip('\\n').encode() + b'\\n':
            f.op('LDA', '#', ch)
            f.op('JSR', 'abs', 0xF009)
        f.op('RTS')
    if first.startswith('; fails'):
        sys.stderr.write(src + ':1:1: error 1: stand-in error\\n')
        sys.exit(1)
    b.save(os.path.join(outdir, name + '.lo'))
    ''')


class Sources(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lathe-build-test-')
        self.saved = build.COMPILER, build.LINKER
        self.compiler = os.path.join(self.dir, 'fake_lathec.py')
        with open(self.compiler, 'w') as fh:
            fh.write(FAKE_COMPILER.format(driver=DRIVER))
        build.COMPILER = self.compiler
        build.LINKER = os.path.join(self.dir, 'no_linker.py')

    def tearDown(self):
        build.COMPILER, build.LINKER = self.saved
        shutil.rmtree(self.dir, ignore_errors=True)

    def source(self, name, text):
        p = os.path.join(self.dir, name)
        with open(p, 'w') as fh:
            fh.write(textwrap.dedent(text))
        return p


class TestDiscovery(Sources):
    def test_imports_of(self):
        p = self.source('a.lth', '''\
            module a
            import host
              import Strings   ; folded to lower case
            ; import commented
            import host
            var important: byte
            ''')
        self.assertEqual(build.imports_of(p), ['host', 'strings'])

    def test_dependency_order(self):
        self.source('b.lth', 'module b\nimport host\n')
        self.source('a.lth', 'module a\nimport b\nimport host\n')
        main = self.source('main.lth', 'module main\nimport a\nimport b\n')
        order = build.module_order(main)
        self.assertEqual([n for n, _ in order], ['host', 'b', 'a', 'main'])
        self.assertEqual(order[0][1], os.path.join(build.RT, 'host.lth'))
        self.assertEqual(order[1][1], os.path.join(self.dir, 'b.lth'))

    def test_beside_source_first(self):
        mine = self.source('host.lth', 'module host\n')
        main = self.source('main.lth', 'module main\nimport host\n')
        self.assertEqual(build.module_order(main)[0][1], mine)

    def test_cycle(self):
        self.source('a.lth', 'module a\nimport main\n')
        main = self.source('main.lth', 'module main\nimport a\n')
        with self.assertRaisesRegex(build.BuildError, 'cycle: main -> a -> main'):
            build.module_order(main)

    def test_missing(self):
        main = self.source('main.lth', 'module main\nimport nowhere\n')
        with self.assertRaisesRegex(build.BuildError, 'module nowhere not found'):
            build.module_order(main)

    def test_env_path(self):
        self.assertEqual(build.env_path('host'), os.path.join(build.ENVS, 'host.env'))
        with self.assertRaisesRegex(build.BuildError, 'environment nope not found'):
            build.env_path('nope')


@unittest.skipUnless(os.path.isfile(build.EMULATOR), 'emulator/emulator.out is not built (run make)')
class TestBuild(Sources):
    def test_build_and_run(self):
        main = self.source('hi.lth', '; prints HI\nmodule hi\nimport host\n')
        out = os.path.join(self.dir, 'hi.bin')
        keep = os.path.join(self.dir, 'keep')
        build.build(main, out, keep=keep)
        with open(os.path.join(keep, 'compiled.log')) as fh:
            self.assertEqual(fh.read(), 'host\nhi\n')
        for f in ('host.lo', 'hi.lo', 'hi.map', 'hi.asm'):
            self.assertTrue(os.path.isfile(os.path.join(keep, f)), f)
        self.assertEqual(os.path.getsize(out), 0x10000 - 0x0200)
        self.assertEqual(build.run_image(out), (0, b'HI\n', b''))

    def test_cli(self):
        main = self.source('ok.lth', '; prints OK\nmodule ok\nimport host\n')
        out = os.path.join(self.dir, 'ok.bin')
        env = dict(os.environ, LATHE_COMPILER=self.compiler, LATHE_LINKER=build.LINKER)
        r = subprocess.run([sys.executable, os.path.join(DRIVER, 'build.py'), main, '-o', out, '--run', '--asm'],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, b'OK\n', b''))

    def test_compile_error(self):
        main = self.source('bad.lth', '; fails\nmodule bad\n')
        env = dict(os.environ, LATHE_COMPILER=self.compiler, LATHE_LINKER=build.LINKER)
        r = subprocess.run([sys.executable, os.path.join(DRIVER, 'build.py'), main, '-o',
                            os.path.join(self.dir, 'x.bin')],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        self.assertEqual(r.returncode, 1)
        self.assertIn(b'error 1: stand-in error', r.stderr)
        self.assertIn(b'build: compiling', r.stderr)

    def test_no_compiler(self):
        build.COMPILER = os.path.join(self.dir, 'missing.py')
        main = self.source('m.lth', 'module m\n')
        with self.assertRaisesRegex(build.BuildError, 'does not exist yet'):
            build.build(main, os.path.join(self.dir, 'm.bin'))

    def test_linker_used_when_present(self):
        """With a linker, the default path copies its image and --asm renders its map."""
        linker = os.path.join(self.dir, 'fake_link.py')
        with open(linker, 'w') as fh:
            fh.write(textwrap.dedent(f'''\
                import sys
                sys.path.insert(0, {DRIVER!r})
                import build, lo, mapenv, naive
                env, main, out, mp = sys.argv[1:5]
                mapenv.write_map(mp, naive.allocate([lo.load(p) for p in sys.argv[5:]],
                                                    mapenv.read_env(env), main))
                build.assembler_image(sys.argv[5:], env, main, mp, out + '.asm', out)
                '''))
        build.LINKER = linker
        main = self.source('hi.lth', '; prints HI\nmodule hi\nimport host\n')
        a, b = os.path.join(self.dir, 'a.bin'), os.path.join(self.dir, 'b.bin')
        keep = os.path.join(self.dir, 'k')
        build.build(main, a, keep=keep)
        self.assertTrue(os.path.isfile(os.path.join(keep, 'hi.link.bin')))
        self.assertFalse(os.path.isfile(os.path.join(keep, 'hi.asm.bin')))
        build.build(main, b, use_asm=True, keep=keep)
        self.assertTrue(os.path.isfile(os.path.join(keep, 'hi.asm.bin')))
        with open(a, 'rb') as fa, open(b, 'rb') as fb:
            self.assertEqual(fa.read(), fb.read())


if __name__ == '__main__':
    unittest.main()
