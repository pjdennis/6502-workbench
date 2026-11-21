"""Regions placed by the program as it starts: `region NAME WIN N dynamic` and `placer MODULE`
(lathe/host/lk_dyn.py; configurations.md, "Regions placed at run time").

The objects are made by hand (test_lk_support), with the environment of test_lk_windows's
regions: `work` in bank 4, dynamic here, and `text` in bank 5, which is not. The list the linker
writes after the code is read back by places.py, and its places are checked against the code
the linker wrote: every byte it names is what it says, and moving a variable by the list gives
the bytes a link with the variable there gives.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_lk_support import Obj, link, string, EITHER, NEVER, NOBODY  # noqa: E402
from test_lk_windows import ENV, WINDOW, REGION_BANKS, farcall_with  # noqa: E402
import places  # noqa: E402

DYNAMIC = (ENV + WINDOW + REGION_BANKS + 'region work WIN 4 dynamic\nregion text WIN 5\nfarcall fc\n'
           'placer p\n')
STATIC = ENV + WINDOW + REGION_BANKS + 'region work WIN 4\nregion text WIN 5\nfarcall fc\n'
PLANES = DYNAMIC.replace('region work WIN 4 dynamic\n', 'region work WIN 4 dynamic t.room rows 256 to 768\n')
FIXED = DYNAMIC.replace('region work WIN 4 dynamic\n',
                        'region work WIN 4 dynamic t.room rows 256 planes 3 to 768\n')
ROOM = DYNAMIC.replace('region work WIN 4 dynamic\n', 'region work WIN 4 dynamic t.room\n')
MAIN = DYNAMIC.replace('region work WIN 4 dynamic\n', 'region work WIN 4 dynamic main\n')
MAIN_ROOM = DYNAMIC.replace('region work WIN 4 dynamic\n', 'region work WIN 4 dynamic main t.room\n')
TOP = DYNAMIC.replace('region work WIN 4 dynamic\n', 'top WIN 4 $9EFF\nregion work WIN 4 dynamic\n')
# A dynamic region beside a region in no bank (`fixed`), with the environment's sixteen banks all
# given (lk_envf.MAX_BANKS), the last a value no region has.
NO_BANK = DYNAMIC.replace('region text WIN 5\n', 'region text fixed\n').replace(
    REGION_BANKS, REGION_BANKS + ''.join('bank WIN %d $%02X\n' % (n, 0x10 + n) for n in range(6, 19)))
CODE_LO = 0x0200


def placer():
    p = Obj('p')
    p.func('place', b'\x60')
    return p


def user(other=True, room=False):
    """Module t: v (300 bytes) and w (4) in region work, k (2) in text. main maps work's bank,
    stores into v and w, forms v's address and an element's high byte, and puts the bank back;
    other maps text's and work's banks, so its blocks map a bank of no dynamic region. With
    `room`, a word room in fixed memory too, which main reads first."""
    t = Obj('t')
    t.v('v')
    t.v('w')
    t.v('k')
    if room:
        t.v('room')
        t.var('room', 2, NEVER)
    t.raw(16, string('work'))
    t.var('v', 300, NEVER)
    t.raw(16, string('work'))
    t.var('w', 4, NEVER)
    t.raw(16, string('text'))
    t.var('k', 2, NEVER)
    c = t.code()
    if room:
        c.abs(0xAD, t.v('room'))            # LDA room
    c.byte(0xA9, 6, t.v('v'))               # LDA #bank(work)
    c.abs(0x20, t.f('rt_with.map'))
    c.abs(0x8D, t.v('v'), add=5)            # STA v+5
    c.abs(0x8D, t.v('w'))                   # STA w
    c.byte(0xA9, 2, t.v('v'), add=0x1F0)    # LDA #<(v+$1F0)
    c.byte(0xA9, 3, t.v('v'), add=0x1F0)    # LDA #>(v+$1F0)
    c.abs(0x20, t.f('rt_with.unmap'))
    c.raw(0x60)
    calls = [(t.f('rt_with.map'), 0, NOBODY), (t.f('rt_with.unmap'), 0, NOBODY)]
    if other:
        calls.append((t.f('other'), 0, NOBODY))
    t.func('main', c, calls=calls)
    if other:
        c = t.code()
        c.byte(0xA9, 6, t.v('k'))           # LDA #bank(text)
        c.abs(0x20, t.f('rt_with.map'))
        c.abs(0x8D, t.v('k'))
        c.byte(0xA9, 6, t.v('w'))           # LDA #bank(work), inside
        c.abs(0x20, t.f('rt_with.map'))
        c.abs(0x8D, t.v('w'))
        c.abs(0x20, t.f('rt_with.unmap'))
        c.abs(0x4C, t.f('rt_with.unmap'))   # the block's end as a tail call
        t.func('other', c, calls=[(t.f('rt_with.map'), 0, NOBODY), (t.f('rt_with.unmap'), 0, NOBODY)] * 2)
    return t


def unmapped_user(room=False):
    """Module t as compiled with -fwork (lathe/host/README.md, "Command lines"): v (300 bytes) and w
    (4) in region work, k (2) in text; main stores into v and w with no block, as their region were
    fixed memory, and into k in a block of text's. With `room`, a word room in fixed memory too."""
    t = Obj('t')
    t.v('v')
    t.v('w')
    t.v('k')
    if room:
        t.v('room')
        t.var('room', 2, NEVER)
    t.raw(16, string('work'))
    t.var('v', 300, NEVER)
    t.raw(16, string('work'))
    t.var('w', 4, NEVER)
    t.raw(16, string('text'))
    t.var('k', 2, NEVER)
    c = t.code()
    c.abs(0x8D, t.v('v'), add=5)            # STA v+5
    c.abs(0x8D, t.v('w'))                   # STA w
    c.byte(0xA9, 3, t.v('v'), add=0x1F0)    # LDA #>(v+$1F0)
    if room:
        c.abs(0xAD, t.v('room'))
    c.byte(0xA9, 6, t.v('k'))               # LDA #bank(text)
    c.abs(0x20, t.f('rt_with.map'))
    c.abs(0x8D, t.v('k'))
    c.abs(0x20, t.f('rt_with.unmap'))
    c.raw(0x60)
    t.func('main', c, calls=[(t.f('rt_with.map'), 0, NOBODY), (t.f('rt_with.unmap'), 0, NOBODY)])
    return t


def two_byte():
    """Module u: a two-byte variable p in region work, used in a block."""
    u = Obj('u')
    u.v('p')
    u.raw(16, string('work'))
    u.var('p', 2, NEVER)
    c = u.code()
    c.byte(0xA9, 6, u.v('p'))
    c.abs(0x20, u.f('rt_with.map'))
    c.abs(0xAD, u.v('p'))
    c.raw(0x60)
    u.func('main', c, calls=[(u.f('rt_with.map'), 0, NOBODY)])
    return u


def one_byte_room():
    """Module t, as user(other=False) with a capacity variable `room` of one byte."""
    t = Obj('t')
    t.v('v')
    t.v('room')
    t.raw(16, string('work'))
    t.var('v', 300, NEVER)
    t.var('room', 1, NEVER)
    c = t.code()
    c.abs(0xAD, t.v('room'))
    c.byte(0xA9, 6, t.v('v'))
    c.abs(0x20, t.f('rt_with.map'))
    c.abs(0x8D, t.v('v'))
    c.abs(0x20, t.f('rt_with.unmap'))
    c.raw(0x60)
    t.func('main', c, calls=[(t.f('rt_with.map'), 0, NOBODY), (t.f('rt_with.unmap'), 0, NOBODY)])
    return t


def planes_user():
    """Module t: p (512 bytes, two planes of 256) and q (256, one) in region work, and a word room;
    main names p, p's second plane, q, q + 5 and the end of q."""
    t = Obj('t')
    t.v('p')
    t.v('q')
    t.v('room')
    t.var('room', 2, NEVER)
    t.raw(16, string('work'))
    t.var('q', 256, NEVER)
    t.raw(16, string('work'))
    t.var('p', 512, NEVER)
    c = t.code()
    c.abs(0xAD, t.v('room'))
    c.byte(0xA9, 6, t.v('p'))
    c.abs(0x20, t.f('rt_with.map'))
    c.abs(0x8D, t.v('p'))
    c.abs(0x8D, t.v('p'), add=0x107)
    c.abs(0x8D, t.v('q'))
    c.abs(0x8D, t.v('q'), add=5)
    c.byte(0xA9, 3, t.v('q'), add=0x100)    # LDA #>(q+256), the end of the block
    c.abs(0x20, t.f('rt_with.unmap'))
    c.raw(0x60)
    t.func('main', c, calls=[(t.f('rt_with.map'), 0, NOBODY), (t.f('rt_with.unmap'), 0, NOBODY)])
    return t


def planes_and_fixed_user():
    """Module t as planes_user, with f (300 bytes, not whole planes) between q and p in region
    work; main names f and f + 299 too."""
    t = Obj('t')
    t.v('p')
    t.v('q')
    t.v('f')
    t.v('room')
    t.var('room', 2, NEVER)
    t.raw(16, string('work'))
    t.var('q', 256, NEVER)
    t.raw(16, string('work'))
    t.var('f', 300, NEVER)
    t.raw(16, string('work'))
    t.var('p', 512, NEVER)
    c = t.code()
    c.abs(0xAD, t.v('room'))
    c.byte(0xA9, 6, t.v('p'))
    c.abs(0x20, t.f('rt_with.map'))
    c.abs(0x8D, t.v('p'))
    c.abs(0x8D, t.v('p'), add=0x107)
    c.abs(0x8D, t.v('f'))
    c.abs(0x8D, t.v('f'), add=299)
    c.abs(0x8D, t.v('q'))
    c.abs(0x8D, t.v('q'), add=5)
    c.byte(0xA9, 3, t.v('q'), add=0x100)    # LDA #>(q+256)
    c.abs(0x20, t.f('rt_with.unmap'))
    c.raw(0x60)
    t.func('main', c, calls=[(t.f('rt_with.map'), 0, NOBODY), (t.f('rt_with.unmap'), 0, NOBODY)])
    return t


def at_user():
    """Module t as compiled with -fwork -ftext: a (2 bytes), b (1) and c (300) in region work, x (2,
    either class and weighty) in no region and k (2) in text; main names them all, with no block.
    A variable in a region is never in zero page (lk_scan: class 2, or the object is damaged)."""
    t = Obj('t')
    for name in ('a', 'b', 'c', 'x', 'k'):
        t.v(name)
    t.raw(16, string('work'))
    t.var('a', 2, NEVER)
    t.raw(16, string('work'))
    t.var('b', 1, NEVER)
    t.var('x', 2, EITHER, weight=200)
    t.raw(16, string('work'))
    t.var('c', 300, NEVER)
    t.raw(16, string('text'))
    t.var('k', 2, NEVER)
    c = t.code()
    for name in ('a', 'b', 'c', 'x', 'k'):
        c.abs(0xAD, t.v(name))              # LDA name
    c.abs(0x8D, t.v('c'), add=299)          # STA c+299
    c.raw(0x60)
    t.func('main', c)
    return t


# `region NAME fixed ADDR`: the region's variables from ADDR, outside the ranges.
AT = ENV + 'region work fixed $F100\nregion text fixed\n'


def places_of(r):
    """The list, from the address $start gives the placer."""
    image = r.image
    # $start: CLD; LDA #<$banks / LDX #>$banks / JSR fc.start; LDA #<$places / LDX #>$places / JSR
    self_at = 8
    assert image[self_at] == 0xA9 and image[self_at + 2] == 0xA2 and image[self_at + 4] == 0x20, image[:16].hex()
    at = image[self_at + 1] | image[self_at + 3] << 8
    return places.decode(image, CODE_LO, at), at


class Dynamic(unittest.TestCase):
    def link(self, objects, env=DYNAMIC):
        return link(objects, env)

    def test_a_dynamic_region_needs_a_placer(self):
        r = link([user(), farcall_with()], DYNAMIC.replace('placer p\n', ''))
        self.assertEqual(r.status, 1)
        self.assertIn('link error 63: environment file: a dynamic region needs a placer', r.errors)
        r = link([user(), farcall_with()], DYNAMIC)
        self.assertIn('link error 63', r.errors)        # the module that defines place is missing

    def test_start_up_calls_the_placer_with_the_list_after_the_code(self):
        r = self.link([user(), farcall_with(), placer()])
        self.assertEqual((r.status, r.errors), (0, ''))
        p, at = places_of(r)
        self.assertEqual(r.image[13:15], r.addr('F', 'p.place').to_bytes(2, 'little'))
        end = at + p.size - CODE_LO                                 # the last thing in the image
        self.assertEqual(r.image[end:0xFFFC - CODE_LO], bytes(0xFFFC - CODE_LO - end))
        self.assertEqual((p.code_lo, p.top), (CODE_LO, 0xF000))
        self.assertEqual(p.areas, [(at, 0x7FFF), (0xC000, 0xEFFF)])
        v, w = r.addr('V', 't.v'), r.addr('V', 't.w')
        self.assertEqual(len(p.regions), 2)                             # work, and text, not dynamic
        text = p.regions[1]
        self.assertEqual((text.value, text.first, text.size, text.highs, text.banks), (0x15, 0, 0, [], []))
        self.assertEqual((p.regions[0].value, p.regions[0].first, p.regions[0].size),
                         (0x14, w, v + 300 - w))                        # w below v, at the top

    def test_every_place_is_what_it_says(self):
        """The high bytes: of each word (its second byte) and each `#>`; no low byte. The banks:
        each block's LDA #bank of the dynamic region, not of `text`."""
        r = self.link([user(), farcall_with(), placer()])
        p, at = places_of(r)
        v, w, main, other = r.addr('V', 't.v'), r.addr('V', 't.w'), r.addr('F', 't.main'), r.addr('F', 't.other')
        image = r.image

        def at_(a):
            return image[a - CODE_LO]

        self.assertEqual(p.regions[0].highs, [main + 7, main + 10, main + 14, other + 15])
        self.assertEqual([at_(a) for a in p.regions[0].highs],
                         [(v + 5) >> 8, w >> 8, (v + 0x1F0) >> 8, w >> 8])
        self.assertEqual(p.regions[0].banks, [main + 1, other + 9])
        self.assertEqual(at_(main + 1), 0x14)

    def test_moving_the_region_by_the_list_moves_every_address_of_it(self):
        """With work's block moved by the list two pages up and more to $C0xx (the model of the
        placer, places.apply), each address of v and w in main's code is moved by as much, the
        low bytes as they were; the bank's value is the module's slot; no other byte changes. In
        its slot where it is linked nothing changes."""
        r = self.link([user(other=False), farcall_with(), placer()])
        p, at = places_of(r)
        v, w, main = r.addr('V', 't.v'), r.addr('V', 't.w'), r.addr('F', 't.main')
        first = p.regions[0].first
        to = 0xC000 | (first & 0xFF)
        delta = to - first
        moved = bytearray(places.apply(r.image, CODE_LO, p, {0: to}, {}))
        expected = bytearray(r.image)
        m = main - CODE_LO
        expected[m + 1] = 4                                             # the module's slot
        expected[m + 6:m + 8] = (v + 5 + delta).to_bytes(2, 'little')
        expected[m + 9:m + 11] = (w + delta).to_bytes(2, 'little')
        expected[m + 14] = ((v + 0x1F0 + delta) >> 8) & 0xFF
        self.assertEqual(moved[m + 12], (v + 0x1F0) & 0xFF)             # the low byte as it was
        self.assertEqual(moved, expected)
        self.assertEqual(places.apply(r.image, CODE_LO, p, {}, {}), r.image)

    def test_a_dynamic_region_named_from_a_bank_is_refused(self):
        """Constant data of a module in a bank that holds a dynamic variable's address: the ROM's
        bytes cannot be moved with it. (Code that names one is in fixed memory, since only code
        with a block can, and the linker keeps that fixed.)"""
        a = Obj('a')
        a.d('tab')
        a.data('tab', b'\x00\x00', fixes=[(0, 1, a.v('t.v'), 0xFF, 0)])
        c = a.code()
        c.abs(0xAD, a.d('tab'))
        c.raw(0x60)
        a.func('main', c)
        r = link([a, user(other=False), farcall_with(), placer()], DYNAMIC + 'place a WIN 1\n')
        self.assertEqual(r.status, 1, r.errors)
        self.assertIn('link error 64: a dynamic region is used where it cannot move: t.v', r.errors)

    def test_constant_data_in_a_dynamic_region_is_refused(self):
        u = Obj('u')
        u.d('c')
        u.raw(16, string('work'))
        u.data('c', b'\x01\x02')
        c = u.code()
        c.byte(0xA9, 6, u.d('c'))
        c.abs(0x20, u.f('rt_with.map'))
        c.abs(0xAD, u.d('c'))
        c.raw(0x60)
        u.func('main', c, calls=[(u.f('rt_with.map'), 0, NOBODY)])
        r = link([u, farcall_with(), placer()], DYNAMIC.replace('bank WIN 4 $14\n', 'bank WIN 4 $14 D4.BIN\n'))
        self.assertEqual(r.status, 1)
        self.assertIn('link error 64: a dynamic region is used where it cannot move', r.errors)

    def test_a_two_byte_variable_in_a_dynamic_region_moves_too(self):
        """Moved by whole pages, a two-byte variable stays off a page's end, where the linker put
        it."""
        r = link([two_byte(), farcall_with(), placer()], DYNAMIC)
        self.assertEqual((r.status, r.errors), (0, ''))

    def test_a_region_names_its_capacity_variable(self):
        """`region work WIN 4 dynamic t.room`: the list gives room's address, what it holds at the
        least (v's 300 bytes as linked), the least bytes of the block (as linked), a step of 256
        bytes and no most (255); a region that names none has 0."""
        r = self.link([user(room=True), farcall_with(), placer()], ROOM)
        self.assertEqual((r.status, r.errors), (0, ''))
        p, at = places_of(r)
        v, w, room = r.addr('V', 't.v'), r.addr('V', 't.w'), r.addr('V', 't.room')
        self.assertFalse(0x8000 <= room <= 0xBFFF)                     # not in the window
        work = p.regions[0]
        self.assertEqual((work.first, work.size, work.room, work.holds), (w, v + 300 - w, room, 300))
        self.assertEqual((p.regions[1].room, p.regions[1].size), (0, 0))
        plain = self.link([user(room=True), farcall_with(), placer()])
        self.assertEqual(places_of(plain)[0].regions[0].room, 0)
        self.assertEqual((work.least, work.unit, work.steps, work.planed), (v + 300 - w, 256, 255, False))

    def test_a_capacity_may_have_a_floor_and_a_ceiling(self):
        """`from N` and `to N`, each optional, in that order: the variable holds the floor at the
        least, and the block is then where the last variable starts plus the floor; the steps of
        256 bytes to the ceiling; a ceiling below the floor, or any other word after them, is a
        bad entry."""
        cases = (('from 200', 200, None), ('to 1000', None, 1000), ('from 100 to 400', 100, 400))
        for words, floor, ceiling in cases:
            with self.subTest(words=words):
                r = self.link([user(room=True), farcall_with(), placer()],
                              ROOM.replace('t.room\n', 't.room ' + words + '\n'))
                self.assertEqual((r.status, r.errors), (0, ''))
                work = places_of(r)[0].regions[0]
                self.assertEqual(work.holds, floor or 300)
                self.assertEqual(work.least, work.size - 300 + (floor or 300))
                self.assertEqual(work.steps, (ceiling - (floor or 300)) >> 8 if ceiling else 255)
        for words in ('to 100 from 50', 'from 400 to 100', 'from 100 more', 'from'):
            with self.subTest(words=words):
                r = self.link([user(room=True), farcall_with(), placer()],
                              ROOM.replace('t.room\n', 't.room ' + words + '\n'))
                self.assertEqual(r.status, 1)
                self.assertIn('link error 3: environment file: bad entry', r.errors)

    def test_a_capacity_variable_must_be_a_linked_word_in_main_memory(self):
        """A bad entry (error 3, with the name) for a name nothing defines, a function, a variable
        of one byte and one in a region."""
        cases = [ROOM.replace('t.room', 't.nothing'), ROOM.replace('t.room', 't.main'),
                 ROOM.replace('t.room', 't.k')]
        for env in cases:
            with self.subTest(env=env.splitlines()[-4]):
                r = self.link([user(room=True), farcall_with(), placer()], env)
                self.assertEqual(r.status, 1)
                self.assertIn('link error 3: environment file: bad entry: t.', r.errors)
        r = self.link([one_byte_room(), farcall_with(), placer()], ROOM)
        self.assertIn('link error 3: environment file: bad entry: t.room', r.errors)

    def test_a_region_of_planes(self):
        """`rows 256 to 768`: every variable of the region is planes of 256 bytes (p two, q one),
        the variable holds rows (256 at the least), the block grows by its three planes' 768
        bytes a step, two steps to 768 rows; each high byte has its address's plane, so that
        with R rows a plane k moves k * (R - 256) / 256 pages more than the block, and every
        address of p and q in main's code is then where the planes are (places.apply)."""
        r = self.link([planes_user(), farcall_with(), placer()], PLANES)
        self.assertEqual((r.status, r.errors), (0, ''))
        p, at = places_of(r)
        work = p.regions[0]
        pa, qa, main = r.addr('V', 't.p'), r.addr('V', 't.q'), r.addr('F', 't.main')
        first = min(pa, qa)
        self.assertEqual((work.holds, work.least, work.unit, work.steps, work.planed),
                         (256, 768, 768, 2, True))
        targets = [pa, pa + 0x100 + 7, qa, qa + 5, qa + 0x100]          # as main names them
        self.assertEqual(work.planes, [(t - first) // 256 for t in targets])
        to = 0xC000 | (first & 0xFF)
        for steps in (0, 1, 2):
            with self.subTest(steps=steps):
                rows = 256 * (1 + steps)
                moved = places.apply(r.image, CODE_LO, p, {0: to}, {}, steps={0: steps})
                for k, t in enumerate(targets):
                    plane, offset = divmod(t - first, 256)
                    expect = to + plane * rows + offset
                    at_ = work.highs[k]
                    self.assertEqual(moved[at_ - CODE_LO], expect >> 8, hex(t))

    def test_a_region_of_planes_must_be_whole_planes(self):
        """`rows` a whole number of pages, the block whole planes of it, no `from` with it, and a
        most (`to`): the placer gives planes steps of rows, never all of an area."""
        for env in (PLANES.replace('rows 256', 'rows 200'), PLANES.replace('rows 256', 'rows 512'),
                    PLANES.replace('rows 256', 'rows 256 from 256'), PLANES.replace(' to 768', ''),
                    PLANES.replace(' to 768', ' want 512')):
            with self.subTest(env=env.splitlines()[-4]):
                r = self.link([planes_user(), farcall_with(), placer()], env)
                self.assertEqual(r.status, 1)
                self.assertIn('link error 3: environment file: bad entry', r.errors)

    def test_a_region_of_planes_may_hold_variables_of_a_fixed_size(self):
        """`rows 256 planes 3 to 768`: the variables of whole planes are the region's planes, three
        in all (p two, q one); f, of 300 bytes, keeps its size, and each high byte's plane is the
        planes below its address, so that f moves with the planes below it and every address of
        p, f and q in main's code is where they are with R rows."""
        r = self.link([planes_and_fixed_user(), farcall_with(), placer()], FIXED)
        self.assertEqual((r.status, r.errors), (0, ''))
        p, at = places_of(r)
        work = p.regions[0]
        pa, qa, fa = r.addr('V', 't.p'), r.addr('V', 't.q'), r.addr('V', 't.f')
        first = min(pa, qa, fa)
        self.assertEqual((work.holds, work.least, work.unit, work.steps, work.planed),
                         (256, 1068, 768, 2, True))
        targets = [pa, pa + 0x100 + 7, fa, fa + 299, qa, qa + 5, qa + 0x100]     # as main names them

        def below(t):
            n = 0
            for a, size in ((pa, 512), (qa, 256)):
                n += size // 256 if a + size <= t else (t - a) // 256 if a <= t else 0
            return n
        self.assertEqual(work.planes, [below(t) for t in targets])
        self.assertNotEqual(work.planes, [(t - first) // 256 for t in targets])
        to = 0xC000 | (first & 0xFF)
        for steps in (0, 1, 2):
            with self.subTest(steps=steps):
                moved = places.apply(r.image, CODE_LO, p, {0: to}, {}, steps={0: steps})
                for k, t in enumerate(targets):
                    expect = to + (t - first) + below(t) * 256 * steps
                    self.assertEqual(moved[work.highs[k] - CODE_LO], expect >> 8, hex(t))

    def test_planes_must_count_the_variables_of_whole_planes(self):
        """With a variable that is not whole planes the region needs `planes`, and their count must
        be the planes of its other variables; `planes` needs `rows`."""
        for env in (PLANES, FIXED.replace('planes 3', 'planes 2'), FIXED.replace('planes 3', 'planes 4'),
                    FIXED.replace('rows 256 planes 3', 'planes 3')):
            with self.subTest(env=env.splitlines()[-4]):
                r = self.link([planes_and_fixed_user(), farcall_with(), placer()], env)
                self.assertEqual(r.status, 1)
                self.assertIn('link error 3: environment file: bad entry', r.errors)
        r = self.link([planes_user(), farcall_with(), placer()], PLANES.replace('rows 256', 'rows 256 planes 3'))
        self.assertEqual((r.status, r.errors), (0, ''))

    def test_a_region_in_main_ram_may_be_named_without_a_block(self):
        """`dynamic main`: the placer puts the region in main RAM alone, never in a slot of sideways
        RAM, so code compiled with the region told fixed (-fwork: its blocks their bodies alone)
        names it without mapping its bank, which is link error 62 for any other region in a bank;
        its places are listed as any dynamic region's, and it has no block's bank to list. A
        region in a bank that is not `main` is still refused so."""
        from test_lk_unmapped import ERROR
        r = self.link([unmapped_user(), farcall_with(), placer()])
        self.assertEqual((r.status, r.errors.strip()), (1, ERROR + 't.v, t.main'))
        r = self.link([unmapped_user(), farcall_with(), placer()], MAIN)
        self.assertEqual((r.status, r.errors), (0, ''))
        p, at = places_of(r)
        v, w, main = r.addr('V', 't.v'), r.addr('V', 't.w'), r.addr('F', 't.main')
        self.assertEqual(p.regions[0].highs, [main + 2, main + 5, main + 7])
        self.assertEqual([r.image[a - CODE_LO] for a in p.regions[0].highs],
                         [(v + 5) >> 8, w >> 8, (v + 0x1F0) >> 8])
        self.assertEqual(p.regions[0].banks, [])
        r = self.link([unmapped_user(room=True), farcall_with(), placer()], MAIN_ROOM)
        self.assertEqual((r.status, r.errors), (0, ''))
        self.assertEqual(places_of(r)[0].regions[0].room, r.addr('V', 't.room'))
        r = self.link([unmapped_user(), farcall_with(), placer()],
                      MAIN.replace('region text WIN 5', 'region text WIN 5 dynamic main'))
        self.assertEqual((r.status, r.errors), (0, ''))     # text's block maps it all the same

    def test_a_region_in_no_bank_has_the_bank_byte_0(self):
        """A region that is not dynamic and in no bank (`fixed`) has no block, no places and the
        bank byte 0 in the list, whatever banks the environment has."""
        r = self.link([user(other=False), farcall_with(), placer()], NO_BANK)
        self.assertEqual((r.status, r.errors), (0, ''))
        p, at = places_of(r)
        text = p.regions[1]
        self.assertEqual((text.value, text.first, text.size, text.highs, text.banks), (0, 0, 0, [], []))
        self.assertEqual(p.regions[0].value, 0x14)

    def test_a_banks_variables_may_end_below_the_window(self):
        """`top WIN 4 $9EFF`: bank 4's variables go down from $9EFF and not from the window's end,
        so that a block of whole pages there starts on a page (for a region the placer puts in
        main RAM, whose areas are pages: lathe/docs/bbc.md, "The image for machines with no
        sideways RAM"). The image is the other's moved by the list a page down."""
        a = self.link([user(other=False), farcall_with(), placer()])
        b = self.link([user(other=False), farcall_with(), placer()], TOP)
        self.assertEqual((a.status, a.errors, b.status, b.errors), (0, '', 0, ''))
        (pa, at), (pb, _) = places_of(a), places_of(b)
        self.assertEqual(pa.regions[0].first + pa.regions[0].size - 1, 0x9FFF)
        self.assertEqual(pb.regions[0].first + pb.regions[0].size - 1, 0x9EFF)
        self.assertEqual(pb.regions[0].size, pa.regions[0].size)
        moved = places.apply(a.image, CODE_LO, pa, {0: pb.regions[0].first}, {0: 0x14})
        self.assertEqual(moved[:at - CODE_LO], b.image[:at - CODE_LO])

    def test_a_banks_top_is_in_its_window_and_counts_for_its_fit(self):
        from test_lk_errors import ErrorTest
        check = ErrorTest.assertError
        for extra, n, text in (('top WIN 9 $9EFF\n', 42, 'environment file: no such'),
                               ('top OTHER 4 $9EFF\n', 42, 'environment file: no such'),
                               ('top WIN 4 $9EFF\ntop WIN 4 $9EFF\n', 43, 'environment file'),
                               ('top WIN 4 $A000\n', 3, 'environment file: bad entry'),
                               ('top WIN 4 $7FFF\n', 3, 'environment file: bad entry'),
                               ('top WIN 4\n', 3, 'environment file: bad entry'),
                               ('top WIN 4 $9EFF X\n', 3, 'environment file: bad entry')):
            with self.subTest(extra=extra):
                check(self, link([user(other=False), farcall_with(), placer()],
                                 DYNAMIC.replace('region work', extra + 'region work', 1)), n, text)
        r = link([user(other=False), farcall_with(), placer()],
                 DYNAMIC.replace('region work', 'top WIN 4 $8100\nregion work', 1))
        check(self, r, 45, 'code and data do not fit in a bank: win 4, 47 bytes over')

    def test_nothing_changes_without_a_dynamic_region(self):
        a = link([user(), farcall_with(), placer()], STATIC + 'placer p\n')
        b = link([user(), farcall_with(), placer()], STATIC)
        self.assertEqual((a.status, b.status), (0, 0))
        self.assertEqual(a.image, b.image)
        self.assertEqual(a.map_text, b.map_text)


class FixedAt(unittest.TestCase):
    """`region NAME fixed ADDR` (lathe/host/README.md, "The environment file"): the region is fixed
    memory, and its variables go from ADDR upward in the order they are defined, outside the code,
    data and more ranges; one that runs into a range or into another such
    region is link error 32. Built for Image B's compiler, whose name heap is lowest in main RAM
    (lathe/docs/bbc.md, "The image for machines with no sideways RAM")."""

    def test_a_regions_variables_go_from_its_address_in_order(self):
        r = link([at_user()], AT)
        self.assertEqual((r.status, r.errors), (0, ''))
        self.assertEqual([r.addr('V', 't.' + n) for n in 'abc'], [0xF100, 0xF102, 0xF103])
        self.assertLess(r.addr('V', 't.x'), 0x100)          # in no region, in zero page
        self.assertEqual(r.addr('V', 't.k'), 0xC000)        # a fixed region with no address
        main = r.addr('F', 't.main')
        self.assertEqual(r.at(main + 15, 2), (0xF103 + 299).to_bytes(2, 'little'))

    def test_a_two_byte_variable_does_not_cross_a_page(self):
        r = link([at_user()], AT.replace('$F100', '$F1FF'))
        self.assertEqual((r.status, r.errors), (0, ''))
        self.assertEqual([r.addr('V', 't.' + n) for n in 'abc'], [0xF200, 0xF202, 0xF203])

    def test_without_its_address_the_region_is_in_the_data_range(self):
        r = link([at_user()], AT.replace(' $F100', ''))
        self.assertEqual((r.status, r.errors), (0, ''))
        self.assertTrue(all(0xC000 <= r.addr('V', 't.' + n) or r.addr('V', 't.' + n) < 0x100
                            for n in 'abck'))

    def test_a_region_that_runs_into_a_range_or_another_is_refused(self):
        from test_lk_errors import ErrorTest
        check = ErrorTest.assertError
        for env in (AT.replace('$F100', '$7F00'),                        # in the code range
                    AT.replace('$F100', '$BF00'),                        # runs into the data range
                    AT.replace('$F100', '$0100').replace('code $0200', 'code $0180'),
                    AT + 'more data $F200 $F2FF\n',                      # runs into more
                    AT.replace('region text fixed', 'region text fixed $F220'),  # into work
                    AT.replace('region text fixed', 'region text fixed $F0FF'),  # work into it
                    AT.replace('$F100', '$FF00')):                       # past $FFFF
            with self.subTest(env=env):
                check(self, link([at_user()], env), 32, 'parts of the image overlap')
        r = link([at_user()], AT.replace('region text fixed', 'region text fixed $F22F'))
        self.assertEqual((r.status, r.errors), (0, ''))
        self.assertEqual(r.addr('V', 't.k'), 0xF22F)

    def test_its_address_is_a_number_above_zero_page_and_the_stack(self):
        from test_lk_errors import ErrorTest
        check = ErrorTest.assertError
        for entry in ('region work fixed $00F0', 'region work fixed X', 'region work fixed $F100 X',
                      'region work fixed $1FFFF'):
            with self.subTest(entry=entry):
                check(self, link([at_user()], AT.replace('region work fixed $F100', entry)), 3,
                      'environment file: bad entry')


def cases():
    """(name, objects, environment) of every link above, for the Lathe-written linker."""
    a = Obj('a')
    a.d('tab')
    a.data('tab', b'\x00\x00', fixes=[(0, 1, a.v('t.v'), 0xFF, 0)])
    c = a.code()
    c.abs(0xAD, a.d('tab'))
    c.raw(0x60)
    a.func('main', c)
    return [('placed', [user(), farcall_with(), placer()], DYNAMIC),
            ('one function', [user(other=False), farcall_with(), placer()], DYNAMIC),
            ('no placer entry', [user(), farcall_with()], DYNAMIC.replace('placer p\n', '')),
            ('no place', [user(), farcall_with()], DYNAMIC),
            ('from a bank', [a, user(other=False), farcall_with(), placer()], DYNAMIC + 'place a WIN 1\n'),
            ('not dynamic', [user(), farcall_with(), placer()], STATIC + 'placer p\n'),
            ('a two-byte variable', [two_byte(), farcall_with(), placer()], DYNAMIC),
            ('a capacity variable', [user(room=True), farcall_with(), placer()], ROOM),
            ('no such capacity variable', [user(room=True), farcall_with(), placer()],
             ROOM.replace('t.room', 't.nothing')),
            ('a function as capacity', [user(room=True), farcall_with(), placer()], ROOM.replace('t.room', 't.main')),
            ('a capacity in a region', [user(room=True), farcall_with(), placer()], ROOM.replace('t.room', 't.k')),
            ('a capacity of one byte', [one_byte_room(), farcall_with(), placer()], ROOM),
            ('a floor and a ceiling', [user(room=True), farcall_with(), placer()],
             ROOM.replace('t.room\n', 't.room from 100 to 400\n')),
            ('a ceiling', [user(room=True), farcall_with(), placer()], ROOM.replace('t.room\n', 't.room to 1000\n')),
            ('a ceiling below the floor', [user(room=True), farcall_with(), placer()],
             ROOM.replace('t.room\n', 't.room from 400 to 100\n')),
            ('planes', [planes_user(), farcall_with(), placer()], PLANES),
            ('planes without a most', [planes_user(), farcall_with(), placer()], PLANES.replace(' to 768', '')),
            ('planes of a size the block is not', [planes_user(), farcall_with(), placer()],
             PLANES.replace('rows 256', 'rows 512')),
            ('planes and a fixed variable', [planes_and_fixed_user(), farcall_with(), placer()], FIXED),
            ('planes miscounted', [planes_and_fixed_user(), farcall_with(), placer()],
             FIXED.replace('planes 3', 'planes 2')),
            ('a fixed variable without planes', [planes_and_fixed_user(), farcall_with(), placer()], PLANES),
            ('a region in main RAM unmapped, not main', [unmapped_user(), farcall_with(), placer()], DYNAMIC),
            ('a region in main RAM', [unmapped_user(), farcall_with(), placer()], MAIN),
            ('a region in main RAM with a capacity', [unmapped_user(room=True), farcall_with(), placer()],
             MAIN_ROOM),
            ('a bank\'s top', [user(other=False), farcall_with(), placer()], TOP),
            ('a bank\'s top twice', [user(other=False), farcall_with(), placer()],
             TOP.replace('top WIN 4 $9EFF\n', 'top WIN 4 $9EFF\ntop WIN 4 $9EFF\n')),
            ('a bank\'s top outside its window', [user(other=False), farcall_with(), placer()],
             TOP.replace('$9EFF', '$A000')),
            ('a bank\'s top of an unknown bank', [user(other=False), farcall_with(), placer()],
             TOP.replace('WIN 4 $9EFF', 'WIN 9 $9EFF')),
            ('a bank too full for its top', [user(other=False), farcall_with(), placer()],
             TOP.replace('$9EFF', '$8100')),
            ('a region in no bank', [user(other=False), farcall_with(), placer()], NO_BANK),
            ('a fixed region at its address', [at_user()], AT),
            ('a fixed region at the end of a page', [at_user()], AT.replace('$F100', '$F1FF')),
            ('two fixed regions at their addresses', [at_user()],
             AT.replace('region text fixed', 'region text fixed $F22F')),
            ('a fixed region into the data range', [at_user()], AT.replace('$F100', '$BF00')),
            ('a fixed region into another', [at_user()], AT.replace('region text fixed', 'region text fixed $F220')),
            ('a fixed region past the end', [at_user()], AT.replace('$F100', '$FF00')),
            ('a fixed region below the stack', [at_user()], AT.replace('$F100', '$00F0'))]


class Twin(unittest.TestCase):
    """The Lathe-written linker (lk_banked, Wendy 2) gives every link above as the host does: the
    same status and errors, the same image and map."""

    @classmethod
    def setUpClass(cls):
        import lk_banked
        cls.dir = tempfile.mkdtemp(prefix='lathe-lk-dynamic-')
        cls.image = lk_banked.build_linker(cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_the_lathe_written_linker_links_as_the_host_does(self):
        import lk_banked
        for name, objects, env in cases():
            with self.subTest(case=name):
                files = {'env': env.encode()}
                names = []
                for i, o in enumerate(objects):
                    files['o%d.lo' % i] = o.to_bytes()
                    names.append('o%d.lo' % i)
                main = objects[0].name
                status, errors, written, cycles = lk_banked.run(self.image, files,
                                                                ['env', main, 'o.bin', 'o.map'] + names)
                d = tempfile.mkdtemp(dir=self.dir)
                for n, data in files.items():
                    with open(os.path.join(d, n), 'wb') as f:
                        f.write(data)
                r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__))), 'host', 'link.py'), 'env', main, 'o.bin', 'o.map'] + names,
                    capture_output=True, cwd=d)
                self.assertEqual((status, errors), (r.returncode, r.stderr))
                for out in ('o.bin', 'o.map'):
                    if r.returncode == 0:
                        with open(os.path.join(d, out), 'rb') as f:
                            self.assertTrue(written.get(out) == f.read(), out + ' differs')


if __name__ == '__main__':
    unittest.main()
