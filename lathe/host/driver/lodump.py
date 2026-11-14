#!/usr/bin/env python3
"""Print every record of a Lathe object file (lathe/docs/object-format.md).

    python3 lathe/host/driver/lodump.py FILE.lo

Each line starts with the record's offset in the file. CODE is shown as bytes and instructions.
After the dump the file is validated with lo.read; a problem is printed and the exit status is 1.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cpu6502  # noqa: E402
import lo  # noqa: E402

CPU_NAMES = {0: '6502', 1: '65c02'}
FIX_KIND_NAMES = {1: 'word', 2: 'low', 3: 'high', 4: 'zp'}


def records(data):
    """(offset, type, body) for each record, stopping quietly where the file is damaged."""
    pos = 0
    while pos + 3 <= len(data):
        t = data[pos]
        n = struct.unpack('<H', data[pos + 1:pos + 3])[0]
        yield pos, t, data[pos + 3:pos + 3 + n]
        pos += 3 + n


def _flags(value, names):
    s = [n for bit, n in names if value & bit]
    return ', '.join(s) if s else '-'


def _str(body, i):
    n = body[i]
    return body[i + 1:i + 1 + n].decode('latin-1'), i + 1 + n


def dump(data, out):
    syms = []
    slots_of = {}          # symbol -> slot names, for functions defined so far
    cur = None
    cpu = 0

    def name(i):
        return syms[i][1] if i < len(syms) else f'?{i}'

    def target(sym, slot):
        if slot == lo.NO_SLOT:
            return name(sym)
        names = slots_of.get(sym, [])
        sname = f' ({names[slot]})' if slot < len(names) else ''
        what = 'param' if sym < len(syms) and syms[sym][0] == lo.K_CLASS else 'slot'
        return f'{name(sym)} {what} {slot}{sname}'

    def fixes(body, indent):
        for i in range(0, len(body) - 7, 8):
            off, kind, sym, slot, addend = struct.unpack('<HBHBH', body[i:i + 8])
            add = f' +${addend:04X}' if addend else ''
            out.write(f'{indent}{off:04X}  kind {kind} {FIX_KIND_NAMES.get(kind, "?"):4}  '
                      f'{target(sym, slot)}{add}\n')

    for pos, t, body in records(data):
        rname = lo.RECORD_NAMES.get(t, f'${t:02X}?')
        head = f'{pos:04X}  {rname:<5} '
        pad = ' ' * len(head)
        try:
            if t == lo.R_MOD:
                cpu = body[1]
                out.write(f'{head}version {body[0]}, cpu {CPU_NAMES.get(cpu, cpu)}, '
                          f'module {_str(body, 2)[0]}\n')
            elif t == lo.R_IMP:
                out.write(f'{head}{_str(body, 0)[0]}\n')
            elif t == lo.R_SYM:
                s = _str(body, 1)[0]
                out.write(f'{head}#{len(syms)} {lo.KIND_NAMES.get(body[0], "?")} {s}\n')
                syms.append((body[0], s))
            elif t == lo.R_VAR:
                sym, size, cls, weight, flags = struct.unpack('<HHBBB', body[:7])
                out.write(f'{head}{name(sym)}: size {size}, class {cls}, weight {weight}'
                          f'{", initialised" if flags & 1 else ""}\n')
                if flags & 1:
                    _hex(body[7:], pad, out)
            elif t == lo.R_DATA:
                sym = struct.unpack('<H', body[:2])[0]
                out.write(f'{head}{name(sym)}: {len(body) - 2} bytes\n')
                _hex(body[2:], pad, out)
            elif t in (lo.R_DFIX, lo.R_FIX):
                out.write(f'{head}{len(body) // 8} entries\n')
                fixes(body, pad)
            elif t == lo.R_FUNC:
                sym, flags = struct.unpack('<HB', body[:3])
                cur = sym
                slots_of[sym] = []
                out.write(f'{head}{name(sym)}  flags: {_flags(flags, lo.FUNC_FLAG_NAMES)}\n')
            elif t == lo.R_SLOT:
                size, cls, weight, kind = struct.unpack('<HBBB', body[:5])
                s = _str(body, 5)[0]
                n = len(slots_of.get(cur, []))
                slots_of.setdefault(cur, []).append(s)
                out.write(f'{head}{n} {s}: size {size}, class {cls}, weight {weight}, '
                          f'{lo.SLOT_KIND_NAMES.get(kind, "?")}\n')
            elif t == lo.R_CALL:
                callee, flags, outer = struct.unpack('<HBH', body[:5])
                o = '-' if outer == lo.NO_OUTER else name(outer)
                f = _flags(flags, ((lo.C_SAVES, 'saves frame'), (lo.C_POINTER, 'through pointer')))
                out.write(f'{head}{name(callee)}  flags: {f}  outer: {o}\n')
            elif t == lo.R_CODE:
                out.write(f'{head}{len(body)} bytes\n')
                _disassemble(body, cpu, pad, out)
            elif t == lo.R_CLAS:
                sym, flags, n = struct.unpack('<HBB', body[:4])
                sizes = struct.unpack(f'<{n}H', body[4:4 + 2 * n])
                rec = ', recursive' if flags & lo.CLAS_RECURSIVE else ''
                out.write(f'{head}{name(sym)}: parameter sizes {list(sizes)}{rec}\n')
            elif t == lo.R_MEMB:
                c, f = struct.unpack('<HH', body[:4])
                out.write(f'{head}{name(f)} in class {name(c)}\n')
            else:
                out.write(f'{head}{len(body)} bytes\n' if body else f'{head}\n'.rstrip() + '\n')
        except (IndexError, struct.error):
            out.write(f'{head}(damaged: {len(body)} bytes)\n')


def _hex(data, pad, out):
    for i in range(0, len(data), 16):
        out.write(f'{pad}{i:04X}  {" ".join(f"{b:02X}" for b in data[i:i + 16])}\n')


def _disassemble(code, cpu, pad, out):
    i = 0
    while i < len(code):
        try:
            m, mode, n = cpu6502.decode(cpu, code, i)
        except ValueError:
            out.write(f'{pad}{i:04X}  {code[i]:02X}        ???\n')
            i += 1
            continue
        raw = ' '.join(f'{b:02X}' for b in code[i:i + n])
        operand = int.from_bytes(code[i + 1:i + n], 'little')
        if mode == cpu6502.REL:
            disp = operand - 256 if operand > 127 else operand
            text = f'{m} ${i + 2 + disp:04X}'
        elif mode == cpu6502.IMP:
            text = m
        else:
            width = 4 if n == 3 else 2
            text = f'{m} ' + mode.replace('zp', 'abs').replace('abs', f'${operand:0{width}X}') \
                .replace('#', f'#${operand:02X}').replace(',x', ',X').replace(',y', ',Y')
        out.write(f'{pad}{i:04X}  {raw:<9} {text}\n')
        i += n


def main(argv):
    if len(argv) != 1:
        sys.stderr.write('usage: lodump.py FILE.lo\n')
        return 2
    with open(argv[0], 'rb') as fh:
        data = fh.read()
    dump(data, sys.stdout)
    try:
        lo.read(data, argv[0])
    except lo.LoError as e:
        sys.stdout.flush()
        sys.stderr.write(f'{e}\n')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
