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
from test_lk_support import Obj, link, string, NEVER, NOBODY  # noqa: E402
from test_lk_windows import ENV, WINDOW, REGION_BANKS, farcall_with  # noqa: E402
import places  # noqa: E402

DYNAMIC = (ENV + WINDOW + REGION_BANKS + 'region work WIN 4 dynamic\nregion text WIN 5\nfarcall fc\n'
           'placer p\n')
STATIC = ENV + WINDOW + REGION_BANKS + 'region work WIN 4\nregion text WIN 5\nfarcall fc\n'
ROOM = DYNAMIC.replace('region work WIN 4 dynamic\n', 'region work WIN 4 dynamic t.room\n')
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
        """`region work WIN 4 dynamic t.room`: the list gives room's address and where work's last
        variable, v, starts in its block, so that the placer can write there the room it gives
        v; a region that names none has 0."""
        r = self.link([user(room=True), farcall_with(), placer()], ROOM)
        self.assertEqual((r.status, r.errors), (0, ''))
        p, at = places_of(r)
        v, w, room = r.addr('V', 't.v'), r.addr('V', 't.w'), r.addr('V', 't.room')
        self.assertFalse(0x8000 <= room <= 0xBFFF)                     # not in the window
        work = p.regions[0]
        self.assertEqual((work.first, work.size, work.room, work.last), (w, v + 300 - w, room, v - w))
        self.assertEqual((p.regions[1].room, p.regions[1].size), (0, 0))
        plain = self.link([user(room=True), farcall_with(), placer()])
        self.assertEqual(places_of(plain)[0].regions[0].room, 0)
        self.assertEqual((work.least, work.most), (v + 300 - w, 0))     # as linked, no limit

    def test_a_capacity_may_have_a_floor_and_a_ceiling(self):
        """`from N` and `to N`, each optional, in that order: the least and most bytes of the
        block are where the last variable starts plus N; a ceiling below the floor, or any other
        word after them, is a bad entry."""
        cases = (('from 200', 200, None), ('to 1000', None, 1000), ('from 100 to 400', 100, 400))
        for words, floor, ceiling in cases:
            with self.subTest(words=words):
                r = self.link([user(room=True), farcall_with(), placer()],
                              ROOM.replace('t.room\n', 't.room ' + words + '\n'))
                self.assertEqual((r.status, r.errors), (0, ''))
                work = places_of(r)[0].regions[0]
                self.assertEqual(work.least, work.last + floor if floor else work.size)
                self.assertEqual(work.most, work.last + ceiling if ceiling else 0)
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

    def test_nothing_changes_without_a_dynamic_region(self):
        a = link([user(), farcall_with(), placer()], STATIC + 'placer p\n')
        b = link([user(), farcall_with(), placer()], STATIC)
        self.assertEqual((a.status, b.status), (0, 0))
        self.assertEqual(a.image, b.image)
        self.assertEqual(a.map_text, b.map_text)


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
             ROOM.replace('t.room\n', 't.room from 400 to 100\n'))]


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
