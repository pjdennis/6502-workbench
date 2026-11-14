"""What the linker knows about 6502 opcodes: how long an instruction is, which absolute
instructions have a zero page form and what it is, and which instructions are relative branches.

The linker finds instruction boundaries by decoding opcodes (object-format.md, "The size of an
instruction"), so OP_LEN covers all 256 values. Opcodes the NMOS 6502 does not define have the
length the 65C02 gives them, which is what an object file for either CPU can contain.
"""

CPU_6502 = 0
CPU_65C02 = 1

OP_LEN = (
    b"\x01\x02\x02\x01\x02\x02\x02\x02\x01\x02\x01\x01\x03\x03\x03\x03"
    b"\x02\x02\x02\x01\x02\x02\x02\x02\x01\x03\x01\x01\x03\x03\x03\x03"
    b"\x03\x02\x02\x01\x02\x02\x02\x02\x01\x02\x01\x01\x03\x03\x03\x03"
    b"\x02\x02\x02\x01\x02\x02\x02\x02\x01\x03\x01\x01\x03\x03\x03\x03"
    b"\x01\x02\x02\x01\x02\x02\x02\x02\x01\x02\x01\x01\x03\x03\x03\x03"
    b"\x02\x02\x02\x01\x02\x02\x02\x02\x01\x03\x01\x01\x03\x03\x03\x03"
    b"\x01\x02\x02\x01\x02\x02\x02\x02\x01\x02\x01\x01\x03\x03\x03\x03"
    b"\x02\x02\x02\x01\x02\x02\x02\x02\x01\x03\x01\x01\x03\x03\x03\x03"
    b"\x02\x02\x02\x01\x02\x02\x02\x02\x01\x02\x01\x01\x03\x03\x03\x03"
    b"\x02\x02\x02\x01\x02\x02\x02\x02\x01\x03\x01\x01\x03\x03\x03\x03"
    b"\x02\x02\x02\x01\x02\x02\x02\x02\x01\x02\x01\x01\x03\x03\x03\x03"
    b"\x02\x02\x02\x01\x02\x02\x02\x02\x01\x03\x01\x01\x03\x03\x03\x03"
    b"\x02\x02\x02\x01\x02\x02\x02\x02\x01\x02\x01\x01\x03\x03\x03\x03"
    b"\x02\x02\x02\x01\x02\x02\x02\x02\x01\x03\x01\x01\x03\x03\x03\x03"
    b"\x02\x02\x02\x01\x02\x02\x02\x02\x01\x02\x01\x01\x03\x03\x03\x03"
    b"\x02\x02\x02\x01\x02\x02\x02\x02\x01\x03\x01\x01\x03\x03\x03\x03"
)

OP_JSR = 0x20
OP_JMP = 0x4C


def length(op):
    """Bytes in the instruction that starts with this opcode."""
    return OP_LEN[op]


def can_shrink(op):
    """True if the instruction has a zero page form: an absolute or absolute,X instruction
    other than JMP, JSR and (on the 65C02) JMP (abs,X), or LDX abs,Y. A fix-up of kind 5 must
    be in one of these and a fix-up of kind 1 in none (object-format.md)."""
    low = op & 0x0F
    if low == 0x0D or low == 0x0E:
        return True
    if low != 0x0C:
        return False
    high = op >> 4
    return high != 0x04 and high != 0x05 and high != 0x06 and high != 0x07 and high != 0x0D \
        and high != 0x0F


def zp_opcode(op):
    """The zero page opcode of an instruction that can_shrink: 8 less, except STZ on the 65C02,
    whose absolute forms are $9C and $9E and zero page forms $64 and $74."""
    if op == 0x9C:
        return 0x64
    if op == 0x9E:
        return 0x74
    return op - 8


def is_branch(op, cpu):
    """True if the last byte of the instruction is a displacement relative to the next one."""
    if (op & 0x1F) == 0x10:
        return True
    if cpu == CPU_65C02:
        # BRA, and BBR/BBS whose third byte is the displacement.
        return op == 0x80 or (op & 0x0F) == 0x0F
    return False
