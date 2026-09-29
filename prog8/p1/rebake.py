#!/usr/bin/env python3
"""Re-lay-out the peek/poke "slab" arenas of a baked pipeline pass.

bake_slabs.py packs the >256 arenas just below $F000 in declaration order and
emits each as `const uword NAME = $BASE`; every access uses the raw $BASE
literal. This tool RE-packs them with new byte sizes (to grow the node arena so
the pipeline can parse its own slab-baked source, or shrink oversized pools),
rewriting every $BASE literal and the const decls in place.

Usage:  rebake.py <pass.p8> NAME=SIZE [NAME=SIZE ...]
SIZE is the new byte size for that slab; unlisted slabs keep their current size.
Packing order = current ascending base order (= declaration order).
"""
import re, sys

path = sys.argv[1]
tight = False
overrides = {}
for a in sys.argv[2:]:
    if a == "--tight":            # pack the bottom slab to $F000-total (no page-align)
        tight = True
        continue
    n, v = a.split("=")
    overrides[n] = int(v, 0)

s = open(path).read()
IO = 0xF000
consts = {n: int(h, 16) for n, h in re.findall(r'const uword (\w+) = \$([0-9a-fA-F]{4})', s)}
slabs = {n: b for n, b in consts.items() if b >= 0x8000}
order = sorted(slabs, key=lambda n: slabs[n])
bases = [slabs[n] for n in order]
size = {}
for i, n in enumerate(order):
    end = bases[i + 1] if i + 1 < len(order) else IO
    size[n] = end - bases[i]
for n, v in overrides.items():
    if n not in size:
        sys.exit("unknown slab: %s (have: %s)" % (n, ", ".join(order)))
    size[n] = v

total = sum(size[n] for n in order)
floor = (IO - total) if tight else ((IO - total) & 0xFF00)
newbase = {}
addr = floor
for n in order:
    newbase[n] = addr
    addr += size[n]
if addr > IO:
    sys.exit("ERROR: slab region overruns $F000 (top=$%04x)" % addr)

# two-phase rewrite of every $oldbase literal (4 hex, word-boundary terminated)
for i, n in enumerate(order):
    s = re.sub(r'\$%04x\b' % bases[i], '\x00PH%d\x00' % i, s, flags=re.IGNORECASE)
for i, n in enumerate(order):
    s = s.replace('\x00PH%d\x00' % i, '$%04x' % newbase[n])

# keep the upstream `%memtop $XXXX` directive in sync with the new slab floor
# (the lowest base) so `upstream prog8c` keeps its allocator below the slabs.
memtop_re = re.compile(r'(?m)^(%memtop[ \t]+)\$[0-9a-fA-F]{4}\b')
if memtop_re.search(s):
    s = memtop_re.sub(r'\g<1>$%04x' % floor, s)
    print("    %-14s $%04x  (memtop directive synced to floor)" % ("%memtop", floor))

open(path, "w").write(s)

# verify no stale base literals survived
stale = [("$%04x" % b) for b in bases if b not in newbase.values() and ("$%04x" % b) in s]
print("rebaked %s  floor $%04x..$f000  (%d B, %d B free below)" %
      (path, floor, total, floor - 0x0200))
for n in order:
    print("    %-14s $%04x  %5d B%s" % (n, newbase[n], size[n],
          "  <-- resized" if n in overrides else ""))
if stale:
    print("WARNING stale base literals remain:", stale)
