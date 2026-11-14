"""Spike L5: build and run the three-module far-call demonstration in each configuration.

This is the spike's stand-in for the linker of stage 11. The modules (main.s, mod_a.s,
mod_b.s) are the same text in every configuration. The configuration says where modules A
and B go: fixed memory, a bank of Wendy 2, or an overlay loaded from disk on the emulator's
default machine. From that the builder

- writes, for each function of a module in a window (the names on its `; far:` line), a stub
  in fixed memory, `STUB_f: JSR fc_call / .byte N / .word f-1`;
- defines every name an image uses and does not define: a function of another module in a
  window means its stub; anything else its address. `ADDR_f` (what `@f` gives) is the stub of
  a function in a window, and the function itself otherwise;
- assembles each image with asm/pyasm.py, again until no address changes (the images refer
  to each other's addresses);
- writes the fixed image and one file per bank or overlay.

The configurations in LATHE_CONFIGS (stage 11, step 3: lathe/tests/test_farcall.py) take the
far-call routine from lathe/rt/rt_bank.lth or rt_ovl.lth instead of rt_bank.s or rt_ovl.s:
lathe_part() compiles lathe/tests/spike_l5/l5main.lth with that module and links it with the
real linker at LATHE_ORG; the spike's fixed image then starts with JMP LATHE_ORG (the Lathe
start-up code, which sets the initial values and calls l5main.main), JMP m_main (which
l5main.main calls) and the address of the table that start() reads, and names the routine's
entry from the Lathe part's map. The table (`$banks` or `$overlays`, lathe/docs/configurations.md,
"The tables") is written here, by hand, as the stage 11 linker will write it.

Run as a program it prints the measurements: python3 lathe/tests/spike_l5/l5build.py
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
EMULATOR = os.path.join(ROOT, 'emulator', 'emulator.out')
sys.path.insert(0, os.path.join(ROOT, 'asm'))
sys.path.insert(0, os.path.join(ROOT, 'lathe', 'host', 'driver'))

import build as lathe_build  # noqa: E402
import pyasm  # noqa: E402

COMPILER = lathe_build.COMPILER
FIXED_ORG = 0x0400
WINDOW_ORG = 0x8000

# name -> (machine, placement of A and B, run-time file, defines)
CONFIGS = {
    'fixed-host': ('host', {'a': None, 'b': None}, 'rt_fixed.s', []),
    'ovl-host': ('host', {'a': 1, 'b': 2}, 'rt_ovl.s', []),
    'fixed-wendy2': ('wendy2', {'a': None, 'b': None}, 'rt_fixed.s', ['HAS_TIMER']),
    'bank-wendy2': ('wendy2', {'a': 0x11, 'b': 0x12}, 'rt_bank.s', ['HAS_TIMER']),
    'bankfast-wendy2': ('wendy2', {'a': 0x11, 'b': 0x12}, 'rt_bankf.s', ['HAS_TIMER']),
}
# The same, with the routine of a Lathe module (the "run-time file" is the module's name).
LATHE_CONFIGS = {
    'lbank-wendy2': ('wendy2', {'a': 0x11, 'b': 0x12}, 'rt_bank', ['HAS_TIMER']),
    'lovl-host': ('host', {'a': 1, 'b': 2}, 'rt_ovl', []),
}
ALL_CONFIGS = dict(CONFIGS, **LATHE_CONFIGS)
FAST_STUBS = {'rt_bankf.s'}     # the run-time files whose stubs make the call themselves

# The Lathe part: linked at LATHE_ORG, its variables at LATHE_DATA and on, its zero page from
# $40 (the spike's own variables are at $10-$2E and $0200, vars.s).
LATHE_ORG = 0x4000
LATHE_DATA = 0x3000
LATHE_ENV = {
    'wendy2': ('cpu 65c02\nzeropage $40 $FF\ncode $4000 $7FFF\ndata $3000 $3FFF\nstack $FF\n'
               'exit stop\noutput raw\n'),
    'host': ('cpu 6502\nzeropage $40 $FF\ncode $4000 $7FFF\ndata $3000 $3FFF\nstack $FF\n'
             'exit call $F00F\noutput image\n'),
}
_lathe_parts = {}
MODULE_FILES = {'a': 'mod_a.s', 'b': 'mod_b.s'}

LABEL_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)\s*(?:;.*)?$')
EQUATE_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=')
NAME_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')


def read(name):
    with open(os.path.join(HERE, name)) as f:
        return f.read()


def defined_names(text):
    names = set()
    for line in text.splitlines():
        m = LABEL_RE.match(line) or EQUATE_RE.match(line)
        if m:
            names.add(m.group(1))
    return names


def used_names(text):
    names = set()
    for line in text.splitlines():
        code = line.split(';', 1)[0]
        code = re.sub(r"'[^']*'|\"[^\"]*\"|\$[0-9A-Fa-f]+|\.[A-Za-z_]\w*", ' ', code)
        if not code[:1].isspace():
            continue                       # a label or an equate: what it defines
        parts = code.split(None, 1)
        if len(parts) == 2 and not parts[0].startswith('.'):
            names.update(NAME_RE.findall(parts[1]))
        elif len(parts) == 2 and parts[0] in ('.byte', '.word'):
            names.update(NAME_RE.findall(parts[1]))
    return {n for n in names if not re.fullmatch(r'[AXY]', n)}


def far_names(text):
    for line in text.splitlines():
        if line.startswith('; far:'):
            return line[len('; far:'):].split()
    return []


class Built:
    """The result of a build: the files and what the assembler said about each image."""

    def __init__(self, config, workdir):
        self.config = config
        self.workdir = workdir
        self.files = {}          # image name -> path of the file the machine reads
        self.symbols = {}        # image name -> {label: address}
        self.sizes = {}          # image name -> bytes


class LathePart:
    """The Lathe part of a LATHE_CONFIGS build: its image, and from its map each name's
    address and size (F, D and V lines)."""

    def __init__(self, image, addr, size):
        self.image, self.addr, self.size = image, addr, size


def lathe_part(config):
    """Compiles and links lathe/tests/spike_l5/l5main.lth for a LATHE_CONFIGS configuration
    (once for each). The overlay configuration defines OVERLAYS, which makes it use rt_ovl."""
    if config in _lathe_parts:
        return _lathe_parts[config]
    machine = LATHE_CONFIGS[config][0]
    with tempfile.TemporaryDirectory(prefix='l5lathe_') as d:
        env = os.path.join(d, 'l5%s.env' % machine)
        with open(env, 'w') as f:
            f.write(LATHE_ENV[machine])
        out = os.path.join(d, 'l5main.bin')
        work = os.path.join(d, 'work')
        lathe_build.build(os.path.join(HERE, 'l5main.lth'), out, env, keep=work,
                          defines=['OVERLAYS=%d' % (machine == 'host')])
        with open(out, 'rb') as f:
            image = f.read()
        addr, size = {}, {}
        with open(os.path.join(work, 'l5main.map')) as f:
            for line in f:
                words = line.split()
                if len(words) >= 4 and words[0] in ('F', 'D', 'V'):
                    addr[words[3]] = int(words[1], 16)
                    size[words[3]] = int(words[2], 16)
    _lathe_parts[config] = LathePart(image, addr, size)
    return _lathe_parts[config]


def lathe_rt(config):
    """For a LATHE_CONFIGS build: what the spike's main and env files need of a run-time file,
    in place of rt_bank.s or rt_ovl.s. The routine is the Lathe module's; start() has been called
    by l5main.main before the spike's main runs, so fc_init does nothing."""
    machine, _, module, _ = LATHE_CONFIGS[config]
    part = lathe_part(config)
    lines = ['fc_call = $%04X' % part.addr[module + '.call'],
             'fc_init', '    RTS',
             'fc_report']
    if machine == 'host':                           # carry set, A and X = the overlay loads
        count = part.addr['rt_ovl.count']
        lines += ['    LDA $%04X' % count, '    LDX $%04X' % (count + 1), '    SEC', '    RTS']
    else:
        lines += ['    CLC', '    RTS']
    return '\n'.join(lines) + '\n'


LATHE_HEADER = ('    JMP $%04X\n'       # FIXED_ORG: the Lathe part's start-up code
                '    JMP m_main\n'      # FIXED_ORG + 3: l5main's extern spike()
                '    .word fc_table\n'  # FIXED_ORG + 6: l5main's variable table
                % LATHE_ORG)


def lathe_table(machine, place):
    """The table start() reads, as the stage 11 linker is to write it: `$banks` (the window's
    first address, the number of banks with a file, and for each its register value and the
    address of its file name) or `$overlays` (the window's first address, the number of
    overlays, and the address of each one's file name, overlay 1 first)."""
    banks = [(mod, place[mod]) for mod in ('a', 'b') if place[mod] is not None]
    lines = ['fc_table', '    .word $%04X' % WINDOW_ORG, '    .byte $%02X' % len(banks)]
    for i, (_, where) in enumerate(banks, 1):
        if machine == 'wendy2':
            lines += ['    .byte $%02X' % where, '    .word fc_n%d' % i]
        else:
            lines += ['    .word fc_n%d' % where]
    return '\n'.join(lines) + '\n'


def generated_fixed(machine, place, values, fast, lathe=False):
    """The part of the fixed image the linker writes: stubs, overlay names, bank loading. With
    lathe, the table of a LATHE_CONFIGS build instead of the overlay names and bank loading."""
    lines = []
    banks = []
    for mod in ('a', 'b'):
        where = place[mod]
        if where is None:
            continue
        banks.append((mod, where))
        for f in far_names(read(MODULE_FILES[mod])):
            real = values.get('REAL_' + f, 0x4000)
            if fast:
                lines += ['STUB_%s' % f,
                          '    PHA',
                          '    LDA #$%02X' % (where & 0x1F),
                          '    JSR fc_enter',
                          '    JSR $%04X' % real,
                          '    JMP fc_leave']
            else:
                lines += ['STUB_%s' % f,
                          '    JSR fc_call',
                          '    .byte $%02X' % where,
                          '    .word $%04X' % ((real - 1) & 0xFFFF)]
    lines.append('STUBS_END')
    if lathe:
        lines.append(lathe_table(machine, place).rstrip('\n'))
    elif machine == 'host' and banks:               # overlays: file names
        lines.append('ov_nlo')
        lines.append('    .byte $00' + ''.join(',<fc_n%d' % n for _, n in banks))
        lines.append('ov_nhi')
        lines.append('    .byte $00' + ''.join(',>fc_n%d' % n for _, n in banks))
    if machine == 'wendy2' and banks and not lathe:     # banks: start-up code loads each file
        lines.append('fc_init')
        for i, (_, value) in enumerate(banks, 1):
            lines += ['    LDA #$%02X' % (value & 0x1F),
                      '    JSR fc_select',
                      '    LDA #<fc_n%d' % i, '    STA ld_s',
                      '    LDA #>fc_n%d' % i, '    STA ld_s+1',
                      '    LDA #$00', '    STA ld_p',
                      '    LDA #$80', '    STA ld_p+1',
                      '    JSR env_load']
        lines += ['    LDA #$01', '    JSR fc_select', '    RTS']
    for i, (mod, n) in enumerate(banks, 1):
        lines.append('fc_n%d' % (n if machine == 'host' else i))
        lines.append('    .asciiz "%s"' % file_name(machine, n if machine == 'host' else i))
    return '\n'.join(lines) + '\n'


def file_name(machine, n):
    return ('L5OV%d.BIN' if machine == 'host' else 'L5BANK%d.BIN') % n


def assemble(text, path, defines):
    src = path + '.s'
    with open(src, 'w') as f:
        f.write(text)
    a = pyasm.Assembler(src, path, defines=list(defines))
    a.run()
    labels = {k[1]: v for k, v in a.symbols.items() if k[0] == 'global'}
    with open(path, 'rb') as f:
        data = f.read()
    return labels, data


def build(config, workdir, defines=(), pad=0):
    """Builds a configuration into workdir. pad adds that many bytes to the end of each module
    in a window, to measure what a load costs per byte."""
    machine, place, rt, cdefines = ALL_CONFIGS[config]
    lathe = config in LATHE_CONFIGS
    defines = list(cdefines) + list(defines)
    out = Built(config, workdir)
    env = read('env_%s.s' % machine)
    vars_text = read('vars.s')
    if lathe:
        fixed_parts = [LATHE_HEADER + read('main.s'), env, lathe_rt(config)]
    else:
        fixed_parts = [read('main.s'), env, read(rt)]
    for mod in ('a', 'b'):
        if place[mod] is None:
            fixed_parts.append(read(MODULE_FILES[mod]))
    windows = [m for m in ('a', 'b') if place[m] is not None]
    far = {m: far_names(read(MODULE_FILES[m])) for m in ('a', 'b')}
    values = {}
    previous = None
    for _ in range(6):
        images = {}
        fixed_text = '\n'.join(fixed_parts) + generated_fixed(machine, place, values,
                                                             rt in FAST_STUBS, lathe)
        images['fixed'] = (FIXED_ORG, fixed_text)
        for m in windows:
            body = read(MODULE_FILES[m])
            if pad:
                body += '    .reserve $%04X\n' % pad
            images[m] = (WINDOW_ORG, body)
        results = {}
        for name, (org, body) in images.items():
            own = defined_names(body) | defined_names(vars_text)
            extern = sorted(n for n in used_names(body) if n not in own)
            equ = []
            for n in extern:
                equ.append('%s = $%04X' % (n, values.get(n, 0x4000)))
            text = vars_text + '\n'.join(equ) + '\n* = $%04X\n' % org + body
            results[name] = assemble(text, os.path.join(workdir, name + '.bin'), defines)
        # Every name's value as other images see it.
        new = {}
        for name, (labels, _) in results.items():
            for n, v in labels.items():
                if n not in defined_names(vars_text):
                    new.setdefault(n, v)
        for m in ('a', 'b'):
            for f in far[m]:
                if place[m] is None:
                    new['ADDR_' + f] = new[f]
                else:
                    new['REAL_' + f] = results[m][0][f]
                    new[f] = results['fixed'][0].get('STUB_' + f, 0x4000)
                    new['ADDR_' + f] = new[f]
        values = new
        if new == previous:
            break
        previous = new
    else:
        raise RuntimeError('addresses did not settle')
    for name, (labels, data) in results.items():
        out.symbols[name] = labels
        out.sizes[name] = len(data)
        if name == 'fixed' and lathe:
            if FIXED_ORG + len(data) > LATHE_DATA:
                raise RuntimeError('the spike\'s fixed image runs into the Lathe part\'s variables')
            part = lathe_part(config).image
            image = bytearray(LATHE_ORG - FIXED_ORG)
            image[:len(data)] = data
            data = bytes(image) + part      # host: the Lathe image runs to $FFFF, its vectors too
            path = os.path.join(workdir, 'L5FIXED.BIN')
        elif name == 'fixed':
            if machine == 'host':
                image = bytearray(0x10000 - FIXED_ORG)
                image[:len(data)] = data
                image[0xFFFC - FIXED_ORG] = FIXED_ORG & 0xFF
                image[0xFFFD - FIXED_ORG] = FIXED_ORG >> 8
                data = bytes(image)
            path = os.path.join(workdir, 'L5FIXED.BIN')
        else:
            n = place[name] if machine == 'host' else windows.index(name) + 1
            path = os.path.join(workdir, file_name(machine, n))
        with open(path, 'wb') as f:
            f.write(data)
        out.files[name] = path
    return out


CYCLES_HOST = re.compile(rb'[Ee]xecuted (\d+) cycles')
CYCLES_WENDY = re.compile(rb'cpu_cycles=(\d+)')


def run(built):
    """Runs a build. Returns (output text, CPU cycles)."""
    machine = ALL_CONFIGS[built.config][0]
    fixed = built.files['fixed']
    if machine == 'host':
        cmd = [EMULATOR, fixed, '--output', '-', '--no-dump', '--cycle-cap', '200000000']
        r = subprocess.run(cmd, cwd=built.workdir, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=120)
        m = CYCLES_HOST.search(r.stderr)
        if r.returncode != 0 or not m:
            raise RuntimeError('run failed: %r %r' % (r.returncode, r.stderr[-300:]))
        return r.stdout.decode('latin-1'), int(m.group(1))
    out = os.path.join(built.workdir, 'out.txt')
    if os.path.exists(out):
        os.unlink(out)
    cmd = [EMULATOR, fixed, '--machine', 'wendy2c', '--wendy2-prog', fixed,
           '--load', '%04X' % FIXED_ORG, '--disk', built.workdir,
           '--cycle-cap', '100000000', '--exit-report']
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    m = CYCLES_WENDY.search(r.stderr)
    if not m or b'(STP)' not in r.stderr:
        raise RuntimeError('run did not stop: %r' % r.stderr[-400:])
    text = ''
    if os.path.exists(out):
        with open(out, 'rb') as f:
            text = f.read().decode('latin-1')
    return text, int(m.group(1))


def run_config(config, defines=(), pad=0):
    with tempfile.TemporaryDirectory(prefix='l5_') as d:
        built = build(config, d, defines, pad)
        text, cycles = run(built)
        return built, text, cycles


LOOP = 256      # iterations of a timing loop
PAD = 0x0400    # bytes added to each window module to measure loading per byte


def measure(config):
    """The measurements of one configuration, in CPU cycles and bytes:
    leaf, mid, swap: cycles per iteration, once the loop runs, of the timing loops M_LEAF (M calls A.a_leaf),
    M_MID (M calls B.b_mid, which calls A.a_leaf) and M_SWAP (M calls A.a_leaf, then
    B.b_dbl), the loop's own cost included; base: a run with no loop (start-up, loading);
    per_byte: what one more byte in each window module adds to the start-up (banks, loaded
    once) or to an iteration of M_MID (overlays, loaded twice an iteration); routine, stub,
    stubs: bytes of the far-call routine, of one stub, the number of stubs."""
    built, _, base = run_config(config, ['MEASURE'])
    _, _, base_half = run_config(config, ['MEASURE', 'HALF'])
    empty = (base - base_half) / (LOOP // 2)        # the loop's own DEC and BNE
    r = {'base': base}
    for loop in ('M_LEAF', 'M_MID', 'M_SWAP'):
        _, _, full = run_config(config, ['MEASURE', loop])
        _, _, half = run_config(config, ['MEASURE', loop, 'HALF'])
        steady = (full - half) / (LOOP // 2) - empty
        r[loop[2:].lower()] = steady
        r[loop[2:].lower() + '_first'] = full - base - LOOP * steady
    s = built.symbols['fixed']
    if 'fc_end' in s:
        r['routine'] = s['fc_end'] - s['fc_call']
        if 'ov_load' in s:
            r['loader'] = s['ov_end'] - s['ov_load']
        n = sum(len(far_names(read(f))) for f in MODULE_FILES.values())
        r['stubs'] = n
        r['stub'] = (s['STUBS_END'] - s['STUB_a_leaf']) // n
        _, _, padded = run_config(config, ['MEASURE'], PAD)
        if ALL_CONFIGS[config][0] == 'host':
            _, _, padded_mid = run_config(config, ['MEASURE', 'M_MID'], PAD)
            _, _, padded_half = run_config(config, ['MEASURE', 'M_MID', 'HALF'], PAD)
            r['per_byte'] = ((padded_mid - padded_half) / (LOOP // 2) - empty
                             - r['mid']) / (2 * PAD)
        else:
            r['per_byte'] = (padded - base) / (2 * PAD)
    return r


def main():
    for config in CONFIGS:
        built, text, cycles = run_config(config)
        print('== %s: %d cycles, image sizes %s' % (config, cycles, built.sizes))
        print(text, end='')
        print(measure(config))


if __name__ == '__main__':
    main()
