"""The linker's list of the places of dynamic regions ($places, lathe/host/lk_dyn.py) read back,
and a model of what the placer does with it: for the tests (test_lk_dynamic.py, the BBC's).

decode(image, code_lo, at) gives a Places; apply(image, code_lo, places, where, slots) gives the
image's bytes as the placer leaves them in memory when each dynamic region's block is moved to
where[number] (absent: where it is; a whole number of pages from it) and each region's blocks map
slots[number] (absent: the module's slot, for a region in main RAM, if it moved; else its own).
"""
from dataclasses import dataclass, field


@dataclass
class Region:
    value: int = 0                                  # the bank's value it is linked with
    first: int = 0                                  # its block as linked
    size: int = 0
    highs: list = field(default_factory=list)       # the places of high bytes
    banks: list = field(default_factory=list)       # the places of blocks' banks


@dataclass
class Places:
    code_lo: int = 0
    top: int = 0
    areas: list = field(default_factory=list)       # (first, last)
    regions: list = field(default_factory=list)     # Region
    size: int = 0                                   # bytes of the list


def decode(image, code_lo, at):
    p = Places()
    pos = at - code_lo

    def byte():
        nonlocal pos
        pos += 1
        return image[pos - 1]

    def word():
        lo = byte()
        return lo | (byte() << 8)

    def places():
        before = 0
        out = []
        for _ in range(word()):
            d = byte()
            before = word() if d == 0 else before + d
            out.append(before)
        return out

    p.code_lo, p.top = word(), word()
    p.areas = [(word(), word()) for _ in range(byte())]
    for _ in range(byte()):
        r = Region(byte(), word(), word())
        r.highs = places()
        r.banks = places()
        p.regions.append(r)
    p.size = pos - (at - code_lo)
    return p


def apply(image, code_lo, places, where, slots, module_slot=4):
    """The image as the placer leaves it (above)."""
    m = bytearray(image)
    for i, r in enumerate(places.regions):
        moved = (where.get(i, r.first) - r.first) & 0xFFFF
        assert moved & 0xFF == 0, 'a region moves by whole pages'
        for a in r.highs:
            m[a - code_lo] = (m[a - code_lo] + (moved >> 8)) & 0xFF
        value = slots.get(i, module_slot if i in where else r.value)
        for a in r.banks:
            m[a - code_lo] = value
    return bytes(m)
