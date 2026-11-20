"""The linker's list of the places of dynamic regions ($places, lathe/host/lk_dyn.py) read back,
and a model of what the placer does with it: for the tests (test_lk_dynamic.py, the BBC's).

decode(image, code_lo, at) gives a Places; apply(image, code_lo, places, where, slots) gives the
image's bytes as the placer leaves them in memory when each dynamic region's block is moved to
where[number] (absent: where it is; a whole number of pages from it) and each region's blocks map
slots[number] (absent: the module's slot, for a region in main RAM, if it moved; else its own).
plan(places, page, himem, slots) is the model of the module's placer (lathe/rt/bbc/module.asm):
where each region goes on a machine, and the capacity it gets.
"""
from dataclasses import dataclass, field


@dataclass
class Region:
    value: int = 0                                  # the bank's value it is linked with
    first: int = 0                                  # its block as linked
    size: int = 0
    room: int = 0                                   # its capacity variable's address, or 0
    holds: int = 0                                  # with one: what it holds at the least,
    least: int = 0                                  # the least bytes of the block,
    unit: int = 0                                   # what each step of 256 adds to the block,
    steps: int = 0                                  # the steps to the most (255: no most)
    want: int = 0                                   # the steps to the want
    planed: bool = False                            # and whether the region is planes
    planes: list = field(default_factory=list)      # then the plane of each high byte's address
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

    def places(planes=None):
        before = 0
        out = []
        for _ in range(word()):
            d = byte()
            before = word() if d == 0 else before + d
            out.append(before)
            if planes is not None:
                planes.append(byte())
        return out

    p.code_lo, p.top = word(), word()
    p.areas = [(word(), word()) for _ in range(byte())]
    for _ in range(byte()):
        r = Region(byte(), word(), word())
        r.room = word()
        if r.room:
            r.holds, r.least, r.unit = word(), word(), word()
            r.steps, r.want, r.planed = byte(), byte(), byte() == 1
        r.highs = places(r.planes if r.planed else None)
        r.banks = places()
        p.regions.append(r)
    p.size = pos - (at - code_lo)
    return p


def apply(image, code_lo, places, where, slots, module_slot=4, steps=None):
    """The image as the placer leaves it (above); with `steps`, a region of planes given that many
    steps above its least moves each plane k by k pages a step more."""
    m = bytearray(image)
    for i, r in enumerate(places.regions):
        moved = (where.get(i, r.first) - r.first) & 0xFFFF
        assert moved & 0xFF == 0, 'a region moves by whole pages'
        for n, a in enumerate(r.highs):
            more = r.planes[n] * (steps or {}).get(i, 0) if r.planed else 0
            m[a - code_lo] = (m[a - code_lo] + (moved >> 8) + more) & 0xFF
        value = slots.get(i, module_slot if i in where else r.value)
        for a in r.banks:
            m[a - code_lo] = value
    return bytes(m)


def of_tool(resident, env_path, map_path):
    """The list of a BBC tool linked with `placer rt_place`: its resident part (from the code
    range's first byte), its environment and its map. (Places, the regions' names in the list's
    order.)"""
    import mapenv
    with open(map_path) as f:
        place = next(int(line.split()[1], 16) for line in f
                     if line.startswith('F ') and line.split()[3] == 'rt_place.place')
    env = mapenv.read_env(env_path)
    with open(resident, 'rb') as f:
        image = f.read()
    return find(image, env.code[0], place)[0], env.regions


def find(image, code_lo, place):
    """The list of a program whose $start calls `place` (its address): `LDA #<$places / LDX
    #>$places / JSR place` is in the first 32 bytes. A Places, and its address."""
    call = bytes((0x20, place & 0xFF, place >> 8))
    i = image.index(call, 0, 32)
    assert image[i - 4] == 0xA9 and image[i - 2] == 0xA2, image[:32].hex()
    at = image[i - 3] | image[i - 1] << 8
    return decode(image, code_lo, at), at


WINDOW = (0x8000, 0xBFDF)       # a slot of sideways RAM as the placer uses it
MAX_AREAS = 12                  # module.asm's p_max_areas


@dataclass
class Placed:
    where: int                  # the block's first byte
    slot: object                # the slot of sideways RAM it is in, or None in main RAM, where
                                # its blocks map the module's slot
    grant: int = 0              # with a capacity variable: the bytes the block is given
    room: int = 0               # and what the placer writes in the variable
    steps: int = 0              # the steps above its least it was given


def plan(places, page, himem, slots):
    """What the module's placer (lathe/rt/bbc/module.asm, `place`) does with the list at PAGE
    `page`, HIMEM `himem` and free sideways RAM in `slots` (the slots p_find finds): a Placed for
    each region that has a block and is not in a bank of the module, by its number; None if it
    is refused (`Too little sideways RAM`).

    Each region with a capacity and a most starts at its most; the regions are placed in the
    list's order, each in the first area that holds it (main RAM's first), one with no most in
    the area that gives it the most, all of it. If one does not fit, a region with steps left
    gives up half of them, the last such region first and then each before it in turn (round
    and round), but not below its want while any region is above its own; and all are placed
    again."""
    steps = {i: r.steps for i, r in enumerate(places.regions) if r.room and r.steps != 255}
    wants = {i: places.regions[i].want for i in steps}
    order = list(range(len(places.regions) - 1, -1, -1))
    turn = 0
    while True:
        done = attempt(places, page, himem, slots, steps)
        if done is not None:
            return done
        for tier in (0, 1):
            for _ in range(len(order)):
                i = order[turn % len(order)]
                turn += 1
                if i not in steps:
                    continue
                if tier == 0 and steps[i] > wants[i]:
                    steps[i] = wants[i] + (steps[i] - wants[i]) // 2
                    break
                if tier == 1 and steps[i] > 0:
                    steps[i] //= 2
                    break
            else:
                continue
            break
        else:
            return None


def attempt(places, page, himem, slots, steps):
    """One placing of every region with the steps given; None if one does not fit."""
    areas = [[page, places.code_lo - 1, None]] + [[a, b, None] for a, b in places.areas] + \
        [[places.top, himem - 1, None]]
    areas = [a for a in areas if a[1] >= a[0]]
    areas += [[WINDOW[0], WINDOW[1], s] for s in sorted(slots)]
    areas = areas[:MAX_AREAS]

    def fit(area, size, r):
        goes = (area[0] & 0xFF00) | (r.first & 0xFF)
        if goes < area[0]:
            goes += 0x100
        return goes if goes + size - 1 <= area[1] else None

    done = {}
    for i, r in enumerate(places.regions):
        if r.size == 0 or r.value >= 0x10:
            continue
        if r.room and r.steps == 255:
            assert not r.planed, 'a region of planes has a most (the linker refuses one without `to`)'
            best = None
            for a in areas:
                goes = fit(a, r.least, r)
                if goes is not None and (best is None or a[1] - goes > best[1][1] - best[0]):
                    best = (goes, a)
            if best is None:
                return None
            goes, a = best
            grant = a[1] - goes + 1
            a[0] = a[1] + 1
            done[i] = Placed(goes, a[2], grant, r.holds + grant - r.least)
            continue
        size = r.least + steps[i] * r.unit if r.room else r.size
        for a in areas:
            goes = fit(a, size, r)
            if goes is not None:
                a[0] = goes + size
                done[i] = Placed(goes, a[2], size, r.holds + 256 * steps[i], steps[i]) if r.room \
                    else Placed(goes, a[2])
                break
        else:
            return None
    return done
