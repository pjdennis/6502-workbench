"""What the banked linker costs (lathe/host/README.md, "The linker in Lathe"; lathe/docs/spikes.md,
"The whole linker in Lathe, banked on Wendy 2").

    python3 lathe/tests/lk_bank_report.py [OUT_DIR]

Builds lathe/src/link.lth with lathe/src/linker-bank.env (lk_banked.build_linker) and prints:

1. from its map: the resident code, stubs and constant data, the free fixed memory, and what
   each bank holds;
2. for each program linked (lextest; lk_synthetic's at the largest size the small build links;
   farcall banked): the CPU cycles of the banked run, and those of a run that stops at once (the
   usage error), which are the start-up's loading of the banks; the far calls, counted by a build
   with a copy of rt_bank whose call() adds to a counter (bank_report.COUNTING_CALL) and a copy of
   disk whose exit() writes it to the file `farcalls`; and the seconds the host linker takes at
   the same capacities;
3. where the far calls go, by the module called and the module calling: the calls of the host
   linker's run between modules that the environment puts in different banks (or from fixed
   memory into a bank), counted with sys.setprofile. The host modules are the twins' function
   for function, so these are the far calls of the Lathe run, which (2) checks in total.
"""
import collections
import os
import re
import shutil
import sys
import tempfile
import time

import src_support as support
import bank_report
import lk_banked
import lk_small
import link
import test_src_lk as lk

COUNTING_EXIT = '''  h = open_out("farcalls")            ; the far calls, for lathe/tests/lk_bank_report.py
  write(farcalls[2], h)
  write(farcalls[1], h)
  write(farcalls[0], h)
  close(h)
  for h = 1 to MAX_HANDLE do
'''


def placement(env_path):
    """{module: bank} of the environment's `place` entries; other modules are fixed (0)."""
    found = {}
    for _, p in lk_banked.mapenv.read_entries(env_path):
        if len(p) >= 4 and p[0].lower() == 'place':
            found[p[1].lower()] = int(p[3])
    return found


def counting_linker(out_dir):
    """The linker built from copies of lathe/src/ with the counting rt_bank and disk."""
    src = os.path.join(out_dir, 'src')
    os.makedirs(src)
    bank_report.counting_copies(src)
    with open(os.path.join(src, 'disk.lth')) as f:
        text = f.read()
    # bank_report's lines name the file by an argument; the linker's every argument is a file it
    # reads, so the counts go to a file of a fixed name instead.
    assert text.count(bank_report.COUNTING_EXIT % 2) == 1
    text = text.replace(bank_report.COUNTING_EXIT % 2, COUNTING_EXIT)
    with open(os.path.join(src, 'disk.lth'), 'w') as f:
        f.write(text)
    image = os.path.join(out_dir, 'link.bin')
    shutil.copyfile(lk_banked.ENV, os.path.join(out_dir, 'link.env'))
    support.build.build(os.path.join(src, 'link.lth'), image, env=os.path.join(out_dir, 'link.env'),
                        keep=os.path.join(out_dir, 'work'))
    return image


PHASES = ('lk_envf.read()', 'lk_scan.scan_all()', 'main_sym = find_main()', 'lk_graph.build(main_sym)',
          'lk_place.check_with()', 'lk_win.mark_stubs(lk_sym.row_of(main_sym))', 'lk_alloc.allocate()',
          'lk_place.place()', 'lk_emit.write(lk_sym.row_of(main_sym))')


def phase_linkers(out_dir):
    """[(phase, image)]: the linker built from copies of lathe/src/ whose main ends, with status 0,
    after each phase of PHASES; the cycles to the end of each, less those to the end of the one
    before, are what the phase costs."""
    found = []
    with open(os.path.join(support.SRC, 'link.lth')) as f:
        text = f.read()
    for phase in PHASES:
        where = os.path.join(out_dir, 'to-' + phase.split('(')[0].split()[-1])
        src = os.path.join(where, 'src')
        os.makedirs(src)
        for f in os.listdir(support.SRC):
            if f.endswith('.lth'):
                shutil.copy(os.path.join(support.SRC, f), src)
        line = '  %s\n' % phase
        assert text.count(line) == 1, phase
        with open(os.path.join(src, 'link.lth'), 'w') as f:
            f.write(text.replace(line, line + '  sys.exit(0)\n'))
        image = os.path.join(where, 'link.bin')
        shutil.copyfile(lk_banked.ENV, os.path.join(where, 'link.env'))
        support.build.build(os.path.join(src, 'link.lth'), image, env=os.path.join(where, 'link.env'),
                            keep=os.path.join(where, 'work'))
        found.append((phase, image))
    return found


def map_report(path):
    items = bank_report.read_map(path)
    fixed = [i for i in items if i[0] in 'FDT' and i[1] < 0x8000 and not any(r.startswith('b=') for r in i[4])]
    code = sum(i[2] for i in fixed if i[0] == 'F')
    stubs = [i for i in fixed if i[0] == 'T']
    data = sum(i[2] for i in fixed if i[0] == 'D')
    messages = sum(i[2] for i in fixed if i[0] == 'D' and i[3].startswith('lk_err.messages'))
    print('resident: code %d, %d stubs (%d bytes), constant data %d (%d of it lk_err\'s messages): %d bytes'
          % (code, len(stubs), 6 * len(stubs), data, messages, code + 6 * len(stubs) + data))
    by_module = collections.Counter()
    for i in fixed:
        if i[0] == 'F':
            by_module[i[3].split('.')[0]] += i[2]
    print('resident code by module: ' + ', '.join('%s %d' % kv for kv in by_module.most_common()))
    for i in items:
        if i[0] == 'W':
            b = i[3]
            inside = [j for j in items if 'b=' + b in j[4]]
            mods = collections.Counter()
            for j in inside:
                if j[0] == 'F':
                    mods[j[3].split('.')[0]] += j[2]
            print('bank %s (%s): file %d bytes; code %d, constants %d, variables %d; %s'
                  % (b, i[4][0], i[2], sum(j[2] for j in inside if j[0] == 'F'),
                     sum(j[2] for j in inside if j[0] == 'D'), sum(j[2] for j in inside if j[0] == 'V'),
                     ', '.join('%s %d' % kv for kv in sorted(mods.items()))))
    top = max(i[1] + i[2] for i in items if i[0] in 'VSC' and 0x200 <= i[1] < 0x8000)
    high = [i[1] + i[2] for i in items if i[0] in 'VSC' and i[1] >= 0xF810]
    variables = sum(i[2] for i in items if i[0] == 'V' and not any(r.startswith('b=') for r in i[4])
                    and i[1] >= 0x200)
    lo = min(i[1] for i in fixed)
    hi = max(i[1] + i[2] for i in fixed)
    print('fixed memory: variables and frames $0200-$%04X (%d bytes of variables), code $%04X-$%04X: '
          '%d bytes free below the code, %d above it; %d bytes at $F810 and up, %d free there'
          % (top - 1, variables, lo, hi - 1, lo - top, 0x8000 - hi, (max(high) - 0xF810) if high else 0,
             0xFFFA - (max(high) if high else 0xF810)))


def host_far_calls(case, banks):
    """The calls the host linker makes on the case, between modules in different banks or from
    fixed memory into a bank: {(caller, callee): count}, and the seconds the run takes."""
    host = os.path.join(support.LATHE, 'host')
    calls = collections.Counter()

    def module(frame):
        f = frame.f_code.co_filename
        if os.path.dirname(f) != host:
            return None
        return os.path.basename(f)[:-3]

    def profile(frame, event, arg):
        if event != 'call':
            return
        callee = module(frame)
        caller = module(frame.f_back) if frame.f_back else None
        if callee is None or caller is None or callee == caller:
            return
        if banks.get(callee, 0) != 0 and banks.get(callee, 0) != banks.get(caller, 0):
            calls[(caller, callee)] += 1

    d = tempfile.mkdtemp()
    try:
        for name, data in case.files.items():
            with open(os.path.join(d, name), 'wb') as f:
                f.write(data)
        start = time.time()
        lk.host_run(link.main, case.args, d)
        seconds = time.time() - start
        for name, data in case.files.items():
            with open(os.path.join(d, name), 'wb') as f:
                f.write(data)
        sys.setprofile(profile)
        try:
            lk.host_run(link.main, case.args, d)
        finally:
            sys.setprofile(None)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return calls, seconds


def main(argv):
    out_dir = argv[1] if len(argv) > 1 else tempfile.mkdtemp(prefix='lathe-lk-bank-')
    os.makedirs(out_dir, exist_ok=True)
    plain = os.path.join(out_dir, 'plain')
    counting = os.path.join(out_dir, 'counting')
    os.makedirs(plain, exist_ok=True)
    os.makedirs(counting, exist_ok=True)
    image = lk_banked.build_linker(plain)
    cimage = counting_linker(counting)
    map_report(os.path.join(plain, 'work', 'link.map'))
    banks = placement(lk_banked.ENV)
    work = tempfile.mkdtemp(dir=out_dir)
    status, _, _, startup = lk_banked.run(image, {}, [])
    print('a run that stops at the usage error (the start-up loads the banks): %d cycles, status %d'
          % (startup, status))
    cases = [lk.program_case('src/lextest.lth', 'src/compiler.env', work),
             lk.synthetic_case(lk.SYNTHETIC_FITS),
             lk.program_case('tests/cases/e2e-config/farcall.lth', 'tests/cases/e2e-config/farcall_banks.env', work)]
    for case in cases:
        status, err, written, cycles = lk_banked.run(image, case.files, case.args)
        cstatus, _, cwritten, _ = lk_banked.run(cimage, case.files, case.args)
        far = int.from_bytes(cwritten.get('farcalls', b''), 'big')
        calls, seconds = host_far_calls(case, banks)
        print()
        print('%s: status %d; %d cycles (%.1f s at 1 MHz), %d far calls (%.1f%% of the cycles at %d '
              'each); the host linker %.2f s' % (case.title, status, cycles, cycles / 1e6, far,
                                                 100.0 * far * bank_report.FAR_CALL / max(cycles, 1),
                                                 bank_report.FAR_CALL, seconds))
        print('  the host run\'s calls across banks: %d' % sum(calls.values()))
        by_callee = collections.Counter()
        for (caller, callee), n in calls.items():
            by_callee[callee] += n
        for callee, n in by_callee.most_common():
            callers = ', '.join('%s %d' % (c, m) for (c, e), m in sorted(calls.items(), key=lambda kv: -kv[1])
                                if e == callee)
            print('  into %-9s (bank %d) %7d: from %s' % (callee, banks[callee], n, callers))
    print()
    phases = phase_linkers(os.path.join(out_dir, 'phases'))
    for case in cases[:2]:
        before = startup
        parts = []
        for phase, pimage in phases:
            status, _, _, cycles = lk_banked.run(pimage, case.files, case.args)
            parts.append('%s %.1f' % (phase.split('(')[0].split()[-1], (cycles - before) / 1e6))
            before = cycles
        print('%s, million cycles by phase (after the start-up): %s' % (case.title, ', '.join(parts)))
    lk_small.load(False)


if __name__ == '__main__':
    main(sys.argv)
