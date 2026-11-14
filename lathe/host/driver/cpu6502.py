"""Opcode tables for the 6502 family, shared by the object file tools.

Each CPU is a table from mnemonic to {mode: opcode}. `decode_table(cpu)` turns one into
opcode -> (mnemonic, mode). The NMOS 6502 is filled in; a 65C02 table is the NMOS one plus
its additions in `_C02_EXTRA`, of which only STP, WAI and the pushes and pulls of X and Y (the
entry and exit code of an interrupt function) are there so far (add the others, and their new
modes to the tables below, as they are needed).
"""

CPU_6502 = 0
CPU_65C02 = 1

# Addressing modes, by the name they are written with in builders and messages.
IMP = 'imp'          # no operand (including the accumulator forms: ASL, ROL, ...)
IMM = '#'
ZP = 'zp'
ZPX = 'zp,x'
ZPY = 'zp,y'
ABS = 'abs'
ABSX = 'abs,x'
ABSY = 'abs,y'
INDX = '(zp,x)'
INDY = '(zp),y'
REL = 'rel'
IND = '(abs)'

OPERAND_BYTES = {IMP: 0, IMM: 1, ZP: 1, ZPX: 1, ZPY: 1, INDX: 1, INDY: 1, REL: 1,
                 ABS: 2, ABSX: 2, ABSY: 2, IND: 2}

# The zero page form of each absolute mode (object-format.md, "The size of an instruction").
ZP_FORM = {ABS: ZP, ABSX: ZPX, ABSY: ZPY}

def _ALU(base):
    return {IMM: base + 0x09, ZP: base + 0x05, ZPX: base + 0x15, ABS: base + 0x0D,
            ABSX: base + 0x1D, ABSY: base + 0x19, INDX: base + 0x01, INDY: base + 0x11}


def _RMW(base):
    return {IMP: base + 0x0A, ZP: base + 0x06, ZPX: base + 0x16, ABS: base + 0x0E, ABSX: base + 0x1E}

NMOS = {
    'ORA': _ALU(0x00), 'AND': _ALU(0x20), 'EOR': _ALU(0x40), 'ADC': _ALU(0x60),
    'LDA': _ALU(0xA0), 'CMP': _ALU(0xC0), 'SBC': _ALU(0xE0),
    'STA': {ZP: 0x85, ZPX: 0x95, ABS: 0x8D, ABSX: 0x9D, ABSY: 0x99, INDX: 0x81, INDY: 0x91},
    'ASL': _RMW(0x00), 'ROL': _RMW(0x20), 'LSR': _RMW(0x40), 'ROR': _RMW(0x60),
    'LDX': {IMM: 0xA2, ZP: 0xA6, ZPY: 0xB6, ABS: 0xAE, ABSY: 0xBE},
    'LDY': {IMM: 0xA0, ZP: 0xA4, ZPX: 0xB4, ABS: 0xAC, ABSX: 0xBC},
    'STX': {ZP: 0x86, ZPY: 0x96, ABS: 0x8E},
    'STY': {ZP: 0x84, ZPX: 0x94, ABS: 0x8C},
    'CPX': {IMM: 0xE0, ZP: 0xE4, ABS: 0xEC},
    'CPY': {IMM: 0xC0, ZP: 0xC4, ABS: 0xCC},
    'BIT': {ZP: 0x24, ABS: 0x2C},
    'INC': {ZP: 0xE6, ZPX: 0xF6, ABS: 0xEE, ABSX: 0xFE},
    'DEC': {ZP: 0xC6, ZPX: 0xD6, ABS: 0xCE, ABSX: 0xDE},
    'BPL': {REL: 0x10}, 'BMI': {REL: 0x30}, 'BVC': {REL: 0x50}, 'BVS': {REL: 0x70},
    'BCC': {REL: 0x90}, 'BCS': {REL: 0xB0}, 'BNE': {REL: 0xD0}, 'BEQ': {REL: 0xF0},
    'JMP': {ABS: 0x4C, IND: 0x6C},
    'JSR': {ABS: 0x20},
}
for _m, _op in (('BRK', 0x00), ('PHP', 0x08), ('CLC', 0x18), ('PLP', 0x28), ('SEC', 0x38),
                ('RTI', 0x40), ('PHA', 0x48), ('CLI', 0x58), ('RTS', 0x60), ('PLA', 0x68),
                ('SEI', 0x78), ('DEY', 0x88), ('TXA', 0x8A), ('TYA', 0x98), ('TXS', 0x9A),
                ('TAY', 0xA8), ('TAX', 0xAA), ('CLV', 0xB8), ('TSX', 0xBA), ('INY', 0xC8),
                ('DEX', 0xCA), ('CLD', 0xD8), ('INX', 0xE8), ('NOP', 0xEA), ('SED', 0xF8)):
    NMOS[_m] = {IMP: _op}

# 65C02 additions (new mnemonics, and new modes of existing ones). asm17 knows none of them, so
# lo2asm writes them as .byte (lo2asm.py, "asm17_has").
_C02_EXTRA = {'STP': {IMP: 0xDB}, 'WAI': {IMP: 0xCB}, 'PHX': {IMP: 0xDA}, 'PHY': {IMP: 0x5A},
              'PLX': {IMP: 0xFA}, 'PLY': {IMP: 0x7A}}


def table(cpu):
    """Mnemonic -> {mode: opcode} for a CPU number (the MOD record's CPU field)."""
    if cpu == CPU_6502:
        return NMOS
    if cpu == CPU_65C02:
        t = {m: dict(modes) for m, modes in NMOS.items()}
        for m, modes in _C02_EXTRA.items():
            t.setdefault(m, {}).update(modes)
        return t
    raise ValueError(f'unknown CPU {cpu}')


_decode_cache = {}


def decode_table(cpu):
    """Opcode -> (mnemonic, mode) for a CPU number."""
    if cpu not in _decode_cache:
        d = {}
        for m, modes in table(cpu).items():
            for mode, op in modes.items():
                d[op] = (m, mode)
        _decode_cache[cpu] = d
    return _decode_cache[cpu]


def shrinks(cpu, mnemonic, mode):
    """The zero page mode an absolute-mode instruction takes, or None if it has none."""
    zp = ZP_FORM.get(mode)
    if zp is not None and zp in table(cpu)[mnemonic]:
        return zp
    return None


def decode(cpu, code, offset):
    """(mnemonic, mode, length) of the instruction at code[offset]; raises ValueError."""
    op = code[offset]
    entry = decode_table(cpu).get(op)
    if entry is None:
        raise ValueError(f'unknown opcode ${op:02X} at offset ${offset:04X}')
    m, mode = entry
    length = 1 + OPERAND_BYTES[mode]
    if offset + length > len(code):
        raise ValueError(f'{m} at offset ${offset:04X} runs past the end of the code')
    return m, mode, length
