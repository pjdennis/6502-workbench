"""michael_timer2_test2.s on the emulator's CPU and VIA (via_t2_runner): its interrupt handler
restarts T2 so that the ticks stay evenly spaced however late the handler runs.

Run from the repo root after building emulator/tests/out/via_t2_runner.out (make timer2-cycles).
"""
import os
import subprocess
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
RUNNER = os.path.join(ROOT, 'emulator', 'tests', 'out', 'via_t2_runner.out')
VASM = os.path.join(ROOT, 'firmware', 'vasm')
PROGRAM = os.path.join(ROOT, 'firmware', 'programs', 'michael', 'michael_timer2_test2.s')
BASE_CONFIG = os.path.join(ROOT, 'firmware', 'boards', 'michael', 'base_config_v2.inc')
TICKS = 1000


def run(clock_khz=None):
    """The (T2 timeouts, T2CL reads) cycles over TICKS ticks of the program, assembled for
    clock_khz (by default the board's), from a base config in the working directory, which vasm
    finds before the include path's."""
    with tempfile.TemporaryDirectory() as tmp:
        if clock_khz is not None:
            with open(BASE_CONFIG) as f:
                config = [f'CLOCK_FREQ_KHZ = {clock_khz}\n' if line.startswith('CLOCK_FREQ_KHZ') else line
                          for line in f]
            with open(os.path.join(tmp, 'base_config_v2.inc'), 'w') as f:
                f.writelines(config)
        binary = os.path.join(tmp, 'program.bin')
        subprocess.run([VASM, '-quiet', '-wdc02', '-wfail', '-Fbin', '-dotdir', '-ignore-mult-inc', '-esc',
                        '-o', binary, PROGRAM], cwd=tmp, check=True)
        cycles = (clock_khz or 2000) * 2 * (TICKS + 1)
        output = subprocess.run([RUNNER, binary, '2000', str(cycles)], check=True, capture_output=True,
                                text=True).stdout.split('\n')
    events = [line.split() for line in output if line]
    return ([int(c) for e, c in events if e == 't2-timeout'], [int(c) for e, c in events if e == 't2cl-read'])


def intervals(cycles):
    return [b - a for a, b in zip(cycles, cycles[1:])]


class Timer2Cycles(unittest.TestCase):
    def test_the_ticks_are_evenly_spaced(self):
        timeouts, _ = run()
        self.assertGreaterEqual(len(timeouts), TICKS)
        # The first tick comes from the program's own load of T2, the rest from the handler's
        self.assertEqual(len(set(intervals(timeouts[1:]))), 1, sorted(set(intervals(timeouts[1:]))))

    def test_the_handler_runs_after_varying_delays(self):
        timeouts, reads = run()
        delays = {read - timeout for timeout, read in zip(timeouts, reads)}
        self.assertGreater(len(delays), 5, sorted(delays))


if __name__ == '__main__':
    unittest.main()
