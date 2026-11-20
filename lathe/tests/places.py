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
    last: int = 0                                   # with one: where its last variable starts,
                                                    # from the block's first byte
    least: int = 0                                  # and the least and most bytes of the block
    most: int = 0                                   # (0: no limit)
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
        r.room = word()
        if r.room:
            r.last, r.least, r.most = word(), word(), word()
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


def plan(places, page, himem, slots):
    """What the module's placer (lathe/rt/bbc/module.asm, `place`) does with the list at PAGE
    `page`, HIMEM `himem` and free sideways RAM in `slots` (the slots p_find finds): a Placed for
    each region that has a block and is not in a bank of the module, by its number; None if it
    is refused (`Too little sideways RAM`)."""
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

    def given(a, goes):
        return a[1] - goes + 1

    def pick(r, size, which, fewest=False):
        """The area of `which` that holds `size` bytes and gives the most (or the fewest)."""
        best = None
        for a in areas:
            if not which(a):
                continue
            goes = fit(a, size, r)
            if goes is None:
                continue
            if best is None or (given(a, goes) < given(best[1], best[0]) if fewest
                                else given(a, goes) > given(best[1], best[0])):
                best = (goes, a)
        return best

    for i, r in enumerate(places.regions):
        if r.size == 0 or r.value >= 0x10:
            continue
        if r.room and not r.most:
            best = pick(r, r.least, lambda a: True)
            if best is None:
                return None
            goes, a = best
            grant = given(a, goes)
            a[0] = a[1] + 1
            done[i] = Placed(goes, a[2], grant, grant - r.last)
        elif r.room:
            best = pick(r, r.least, lambda a: a[2] is None) or pick(r, r.least, lambda a: a[2] is not None, True)
            if best is None:
                return None
            goes, a = best
            grant = min(given(a, goes), r.most)
            a[0] = goes + grant
            done[i] = Placed(goes, a[2], grant, grant - r.last)
        else:
            for a in areas:
                goes = fit(a, r.size, r)
                if goes is not None:
                    a[0] = goes + r.size
                    done[i] = Placed(goes, a[2])
                    break
            else:
                return None
    return done
