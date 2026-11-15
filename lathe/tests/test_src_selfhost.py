"""Stage 11, step 11, the gate of stage 7: the compiler written in Lathe (lathe/src/lathec.lth with
the twins of the seventeen host modules), built banked on Wendy 2 at its full capacities
(lathe/src/compiler-bank.env, SMALL 0: the big tables in data banks), compiles its own modules,
err kernel src lex typetab fold fbuf out reg cond gen asmblock inlines parts expr decl lathec
and sys, each as lathe/src/compiler.env's options compile it, to object and interface files
byte-identical to those of the host compiler (lathe/host/lathec.py) at the same capacities.

Each module is compiled in a directory of its own that holds its source and the interfaces of
the modules it imports, made by the host compiler: `lathec OPTIONS NAME.lth .` on Wendy 2 with
--disk, and the same command with the host. Status, output, error output and the files written
must be the same. By default the five smallest (QUICK) run, about 9 s; LATHE_SELFHOST=1 runs all
eighteen, about a minute (815 million CPU cycles of Wendy 2 in all, 2026-11-15).
LATHE_SELFHOST_REPORT=1 prints the cycles of each compile."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import src_support as support
import memory_report

ALL = os.environ.get('LATHE_SELFHOST') == '1'
REPORT = os.environ.get('LATHE_SELFHOST_REPORT') == '1'
MODULES = ('err', 'kernel', 'src', 'lex', 'typetab', 'fold', 'fbuf', 'out', 'reg', 'cond', 'gen',
           'asmblock', 'inlines', 'parts', 'expr', 'decl', 'lathec', 'sys')
QUICK = ('err', 'src', 'fold', 'typetab', 'sys')     # run by default: the smallest
CYCLE_CAP = 40000000000     # oscillator ticks, 2 a CPU cycle: 20 G cycles a compile


def read(path):
    with open(path, 'rb') as f:
        return f.read()


def prepare(name, work, options):
    """A directory with lathe/src/NAME.lth and the host's interfaces of what it imports; the
    host's own compile of it in a second directory. Returns (directory, host result)."""
    sys.path.insert(0, os.path.join(support.LATHE, 'host', 'driver'))
    import build
    src = os.path.join(support.SRC, name + '.lth')
    lis = os.path.join(work, 'li')
    os.makedirs(lis, exist_ok=True)
    order = build.module_order(src)
    for _, dep in order[:-1]:
        if not os.path.exists(os.path.join(lis, build.module_name(dep) + '.li')):
            subprocess.run([sys.executable, build.COMPILER] + list(options) + [dep, lis], check=True,
                           capture_output=True)
    results = []
    for side in ('lathe', 'host'):
        d = os.path.join(work, '%s-%s' % (name, side))
        os.makedirs(d)
        shutil.copy(src, d)
        for _, dep in order[:-1]:
            shutil.copy(os.path.join(lis, build.module_name(dep) + '.li'), d)
        results.append(d)
    host_dir = results[1]
    before = set(os.listdir(host_dir))
    done = subprocess.run([sys.executable, build.COMPILER] + list(options) + [name + '.lth', '.'],
                          cwd=host_dir, capture_output=True)
    files = {f: read(os.path.join(host_dir, f)) for f in sorted(os.listdir(host_dir))
             if f not in before}
    return results[0], (done.returncode, done.stdout, done.stderr, files)


def run_lathe(image, disk, args):
    """(status, output, error output, {file: bytes}, CPU cycles) of the banked compiler run on
    Wendy 2 in the directory `disk`, with the arguments `args`."""
    import boards
    import dataclasses
    import mapenv
    sys.path.insert(0, os.path.join(support.LATHE, 'host', 'driver'))
    import build
    env = mapenv.read_env(os.path.splitext(image)[0] + '.env')
    board = dataclasses.replace(boards.BOARDS['wendy2disk'], cycle_cap=CYCLE_CAP)
    build.window_files(env, os.path.dirname(os.path.abspath(image)), disk)
    before = set(os.listdir(disk))
    with open(os.path.join(disk, boards.ARGS_FILE), 'wb') as f:
        f.write(b''.join(a.encode('latin-1') + b'\n' for a in args))
    report = boards.emulate(board, image, env, disk)
    boards.read_report(board, report)
    files = {}
    for f in sorted(os.listdir(disk)):
        if f not in before and f not in (boards.ARGS_FILE, boards.OUT_FILE, boards.ERRORS_FILE,
                                         boards.STATUS_FILE):
            files[f] = read(os.path.join(disk, f))
    m = re.search(r'cpu_cycles=(\d+)', report)
    return (boards.read_status(disk), boards.read_file(disk, boards.OUT_FILE),
            boards.read_file(disk, boards.ERRORS_FILE), files, int(m.group(1)) if m else 0)


class SelfHost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lathe-selfhost-')
        os.makedirs(os.path.join(cls.dir, 'build'))
        cls.image = support.build_program('lathec', os.path.join(cls.dir, 'build'), banked=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_the_compiler_compiles_itself_as_the_host_does(self):
        cycles = {}
        for name in MODULES if ALL else QUICK:
            options = tuple(memory_report.options_of(os.path.join(support.SRC, name + '.lth')))
            disk, host = prepare(name, os.path.join(self.dir, 'work'), options)
            got = run_lathe(self.image, disk, list(options) + [name + '.lth', '.'])
            cycles[name] = got[4]
            with self.subTest(module=name):
                self.assertEqual(got[:3], host[:3])
                self.assertEqual(sorted(got[3]), sorted(host[3]))
                for f in host[3]:
                    self.assertTrue(got[3][f] == host[3][f], f + ' differs')
        if REPORT:
            print()
            for name, c in cycles.items():
                print('%-9s %13d cycles' % (name, c))
            print('%-9s %13d cycles' % ('total', sum(cycles.values())))


if __name__ == '__main__':
    unittest.main()
