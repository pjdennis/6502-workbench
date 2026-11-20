"""The linker's list of the places of dynamic regions ($places, lathe/host/lk_dyn.py) read back,
and a model of what the placer does with it: for the tests (test_lk_dynamic.py, the BBC's).

decode(image, code_lo, at) gives a Places; apply(image, code_lo, places, where, slot) gives the
image's bytes as the placer leaves them in memory when each dynamic variable is moved to
where[number] (absent: where it is) and each region is in main RAM (slot None) or in the slot
given (a dict by region number).
"""
from dataclasses import dataclass, field


@dataclass
class Places:
    code_lo: int = 0
    top: int = 0
    areas: list = field(default_factory=list)       # (first, last)
    regions: list = field(default_factory=list)     # the bank's value each is linked with
    variables: list = field(default_factory=list)   # (address, size, region)
    addresses: list = field(default_factory=list)   # (type, variable, address, low byte or None)
    banks: list = field(default_factory=list)       # (region, address)
    groups: list = field(default_factory=list)      # (mask, [addresses])
    size: int = 0                                   # bytes of the list


WORD, LOW, HIGH = 1, 2, 3
KEEP = 0x8000


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

    def place(before):
        d = byte()
        return word() if d == 0 else before + d

    p.code_lo, p.top = word(), word()
    p.areas = [(word(), word()) for _ in range(byte())]
    p.regions = [byte() for _ in range(byte())]
    p.variables = [(word(), word(), byte()) for _ in range(byte())]
    before = 0
    while True:
        tag = byte()
        if tag == 0:
            break
        before = place(before)
        low = byte() if tag >> 6 == HIGH else None
        p.addresses.append((tag >> 6, tag & 0x3F, before, low))
    before = 0
    while True:
        r = byte()
        if r == 0:
            break
        before = place(before)
        p.banks.append((r - 1, before))
    before = 0
    while True:
        n = byte()
        if n == 0:
            break
        mask = word()
        calls = []
        for _ in range(n):
            before = place(before)
            calls.append(before)
        p.groups.append((mask, calls))
    p.size = pos - (at - code_lo)
    return p


def apply(image, code_lo, places, where, slots, module_slot=4):
    """The image as the placer leaves it (above). `slots`: {region: slot}, a region not in it
    being in main RAM."""
    m = bytearray(image)

    def get(a):
        return m[a - code_lo]

    def put(a, v):
        m[a - code_lo] = v & 0xFF

    deltas = [(where.get(i, a) - a) & 0xFFFF for i, (a, size, r) in enumerate(places.variables)]
    for t, v, a, low in places.addresses:
        d = deltas[v]
        if t == WORD:
            w = (get(a) | get(a + 1) << 8) + d
            put(a, w)
            put(a + 1, w >> 8)
        elif t == LOW:
            put(a, get(a) + d)
        else:
            put(a, get(a) + (d >> 8) + ((low + (d & 0xFF)) >> 8))
    for r, a in places.banks:
        put(a, slots[r] if r in slots else module_slot)
    for mask, calls in places.groups:
        regions = [r for r in range(15) if mask & (1 << r)]
        if mask & KEEP or not regions or any(r in slots for r in regions):
            continue
        for a in calls:
            if get(a - 1) == 0x20:
                put(a - 1, 0xEA)
                put(a, 0xEA)
                put(a + 1, 0xEA)
            else:
                put(a - 1, 0x60)
    return bytes(m)
