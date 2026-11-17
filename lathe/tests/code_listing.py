"""The code of a linked Lathe program, instruction by instruction, from its object files and map.

    import code_listing
    prog = code_listing.Program(work_dir, map_path)
    for f in prog.functions:                  # every function the map keeps, in map order
        for ins in f.instructions:            # Instruction: offset, opcode, mnemonic, mode,
            ...                               # operand text, size as written, size as placed

A tool for measuring generated code (lathe/docs/spikes.md, "Size for a 128 KB ROM: the
generated code, measured"). The size as placed is the size as written less one byte for an
instruction with a fix-up of kind 5 (it has a zero page form) whose target the map puts in zero
page: what the linker's shrinking does. Each function's placed size is checked against its F
line.

An operand is described by `ins.target`: None for an operand that is not a fix-up; otherwise
(kind, name, slot, addend) with the name of the symbol (`module.function` for a slot, with the
slot's name in slot), `ins.zp` whether it is in zero page, `ins.temp` whether it is a
temporary of the function itself.

    python3 lathe/tests/code_listing.py WORK_DIR MAP [FUNCTION...]

prints the listing of each FUNCTION named (all with none)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'host', 'driver'))

import cpu6502      # noqa: E402
import lo           # noqa: E402

BRANCHES = ('BCC', 'BCS', 'BEQ', 'BNE', 'BMI', 'BPL', 'BVC', 'BVS', 'BRA')


class Instruction:
    __slots__ = ('offset', 'opcode', 'mnemonic', 'mode', 'operand', 'written', 'placed', 'target',
                 'zp', 'temp', 'slot_kind', 'function', 'kind', 'construct', 'chain')

    def text(self):
        if self.target is None:
            if self.mode == cpu6502.IMP:
                return self.mnemonic
            if self.mode == cpu6502.REL:
                d = self.operand - 256 if self.operand > 127 else self.operand
                return f'{self.mnemonic} *{d + 2:+d}'
            if self.mode == cpu6502.IMM:
                return f'{self.mnemonic} #${self.operand:02X}'
            return f'{self.mnemonic} ${self.operand:04X} ({self.mode})'
        kind, name, slot, addend = self.target
        where = name if slot is None else f'{name}.{slot}'
        if addend:
            where += f'+{addend}'
        mode = self.mode
        pre = {lo.FX_LO: '#<', lo.FX_REACH_LO: '#<', lo.FX_HI: '#>', lo.FX_REACH_HI: '#>',
               lo.FX_BANK: '#bank '}.get(kind, '')
        if pre:
            return f'{self.mnemonic} {pre}{where}'
        z = ' zp' if self.zp else ''
        if mode in (cpu6502.ABS, cpu6502.ZP):
            return f'{self.mnemonic} {where}{z}'
        return f'{self.mnemonic} {where},{mode.split(",")[-1]}{z}' if ',' in mode and '(' not in mode \
            else f'{self.mnemonic} {mode.replace("zp", where)}{z}'


class Function:
    def __init__(self, name, address, size, module, func):
        self.name = name
        self.address = address
        self.size = size
        self.module = module
        self.func = func
        self.instructions = []
        self.kept = False


class Program:
    def __init__(self, work_dir, map_path, check=True):
        self.addresses = {}        # (name, slot name or None) -> address
        self.slot_number = {}      # (function, slot number) -> address
        self.map_functions = []    # (name, address, size, rest)
        self.stubs = []
        self.data = []
        for line in open(map_path):
            p = line.split()
            if len(p) < 4:
                continue
            kind, address, size, name = p[0], int(p[1], 16), int(p[2], 16), p[3]
            if kind == 'F':
                self.map_functions.append((name, address, size, p[4:]))
                self.addresses[(name, None)] = address
            elif kind in ('V', 'D'):
                self.addresses[(name, None)] = address
                if kind == 'D':
                    self.data.append((name, address, size))
            elif kind == 'S' or kind == 'C':
                self.slot_number[(name, int(p[4]))] = address
            elif kind == 'T':
                self.stubs.append((name, address, size))
        self.modules = {}
        for f in os.listdir(work_dir):
            if f.endswith('.lo'):
                m = lo.load(os.path.join(work_dir, f))
                self.modules[m.name] = m
        self.functions = []
        by_name = {}
        for m in self.modules.values():
            for fn in m.functions():
                by_name[m.sym_name(fn.sym)] = (m, fn)
        for name, address, size, rest in self.map_functions:
            if name not in by_name:
                continue
            m, fn = by_name[name]
            f = Function(name, address, size, m, fn)
            f.kept = any(r.startswith('k=') for r in rest)
            self.decode(f)
            if check and sum(i.placed for i in f.instructions) != size:
                raise ValueError(f'{name}: placed {sum(i.placed for i in f.instructions)}, map {size}')
            self.functions.append(f)

    def where(self, m, fix):
        """(name, slot name or None, address or None) of a fix-up's target."""
        name = m.sym_name(fix.sym)
        if fix.slot == lo.NO_SLOT:
            return name, None, self.addresses.get((name, None))
        slot_name = None
        d = m.definition(fix.sym)
        if isinstance(d, lo.Func) and fix.slot < len(d.slots):
            slot_name = d.slots[fix.slot].name
        if slot_name is None:
            slot_name = str(fix.slot)
        return name, slot_name, self.slot_number.get((name, fix.slot))

    def decode(self, f):
        m, fn = f.module, f.func
        table = cpu6502.decode_table(m.cpu)
        fixes = {x.offset: x for x in fn.fixes}
        code = fn.code
        own = m.sym_name(fn.sym)
        i = 0
        while i < len(code):
            op = code[i]
            mn, mode = table.get(op, ('???', cpu6502.IMP))
            n = cpu6502.OPERAND_BYTES[mode]
            ins = Instruction()
            ins.function = f
            ins.offset, ins.opcode, ins.mnemonic, ins.mode = i, op, mn, mode
            ins.written = 1 + n
            ins.placed = ins.written
            ins.operand = int.from_bytes(code[i + 1:i + 1 + n], 'little') if n else None
            ins.target = None
            ins.zp = False
            ins.temp = False
            ins.slot_kind = None
            x = fixes.get(i + 1)
            if x is not None:
                name, slot, address = self.where(m, x)
                ins.target = (x.kind, name, slot, x.addend)
                ins.zp = address is not None and address + x.addend < 0x100
                if x.slot != lo.NO_SLOT and name == own:
                    d = fn.slots[x.slot] if x.slot < len(fn.slots) else None
                    ins.slot_kind = d.kind if d else None
                    ins.temp = d is not None and d.kind == lo.SK_TEMP
                if x.kind == lo.FX_SHRINK and ins.zp:
                    ins.placed -= 1
                    ins.mode = cpu6502.ZP_FORM.get(mode, mode)
                elif x.kind == lo.FX_ZP:
                    ins.zp = True
            f.instructions.append(ins)
            i += 1 + n


def main(argv):
    prog = Program(argv[0], argv[1])
    wanted = set(argv[2:])
    for f in prog.functions:
        if wanted and f.name not in wanted:
            continue
        print(f'{f.name}: {f.size} bytes at ${f.address:04X}')
        for ins in f.instructions:
            print(f'  {ins.offset:4d} {ins.placed} {ins.text()}')


if __name__ == '__main__':
    main(sys.argv[1:])
