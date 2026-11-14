"""A large synthetic program for the linker: the stand-in for linking the compiler.

    program(seed) -> [lo.Builder, ...]     30 modules in link order, the main module "p00" last

The shape follows a Lathe program of the compiler's size: about 700 functions, 3,500 slots and
3,000 calls in 30 modules. Functions are declared before use, so a function calls functions of
lower levels (earlier in its module or in modules it imports, which come earlier in the link),
and calls nest up to 20 deep from main. Frames are 0 to 20 bytes, of one- and two-byte slots
and a few small arrays, in all three zero page classes; arguments are stored into the callee's
parameter slots, which gives each call a cross-module weight when the callee is in another
module. There is a recursive group of four functions, an interrupt function that shares a
dozen functions with main (so they are copied), three pointer classes whose members are taken
by address in code and in a table, and constant data and module variables used across modules.
Main calls most functions nothing else calls; the rest, and some data, are dropped.

Everything is drawn from random.Random(seed), so a seed always gives the same program.
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'host', 'driver'))
import lo  # noqa: E402

MUST, EITHER, NEVER = 0, 1, 2
MODULES = 30
PER_MODULE = 23
LEVELS = 20


def program(seed=1):
    rnd = random.Random(seed)
    mods = ['p%02d' % i for i in range(MODULES)]
    # Module 0 is the main module, linked first; the others are libraries, low to high. A
    # function of level L calls only lower levels; main is the only function of the top level.
    funcs = []                                  # (module index, name, level, params)
    for mi in range(1, MODULES):
        for j in range(PER_MODULE):
            level = min(LEVELS - 1, ((MODULES - mi) * LEVELS) // MODULES + rnd.randrange(0, 2))
            params = [rnd.choice((1, 1, 2)) for _ in range(rnd.choice((0, 1, 1, 2, 3)))]
            funcs.append((mi, '%s.f%02d' % (mods[mi], j), level, params))
    by_level = {}
    for f in funcs:
        by_level.setdefault(f[2], []).append(f)
    # Pointer classes: members share their parameter sizes.
    classes = [('p01.visit', [1]), ('p02.emit', [2, 1]), ('p03.key', [])]
    members = {}
    for k, (cname, params) in enumerate(classes):
        cands = [f for f in funcs if f[3] == params and f[2] == 0]
        for f in rnd.sample(cands, min(4, len(cands))):
            members[f[1]] = k
    shared = set(f[1] for f in rnd.sample([f for f in funcs if f[2] < 4 and f[1] not in members], 12))
    builders = [lo.Builder(m) for m in mods]
    for mi in range(MODULES):
        builders[mi].var('%s.v' % mods[mi], rnd.choice((1, 2)), EITHER, rnd.randrange(0, 20))
        builders[mi].var('%s.w' % mods[mi], 2, rnd.choice((EITHER, NEVER)), rnd.randrange(0, 9))
        builders[mi].var('%s.buf' % mods[mi], 32, NEVER, 0)
        builders[mi].data('%s.$1' % mods[mi], bytes(rnd.randrange(4, 40)))
    used_classes = {}

    def use_class(b, k):
        if (b, k) not in used_classes:
            used_classes[(b, k)] = True
            b.clas(classes[k][0], classes[k][1])

    calls = 0
    called = set()

    def body(b, mi, name, level, params, callees, recursive_group=None):
        nonlocal calls
        fb = b.func(name, lo.F_RECURSIVE if recursive_group else 0)
        for i, size in enumerate(params):
            fb.slot('a%d' % i, size, rnd.choice((EITHER, EITHER, MUST)), rnd.randrange(0, 30), lo.SK_PARAM)
        frame = sum(params)
        while frame < 20 and rnd.random() < 0.82:
            size = rnd.choice((1, 1, 1, 2, 2, 4))
            cls = rnd.choice((EITHER, EITHER, EITHER, MUST, NEVER)) if size <= 2 else NEVER
            fb.slot('l%d' % len(fb.func.slots), size, cls, rnd.randrange(0, 60) if cls == EITHER else 0,
                    rnd.choice((lo.SK_LOCAL, lo.SK_TEMP)))
            frame += size
        slots = fb.func.slots
        for i, s in enumerate(slots):
            if s.cls != MUST:
                fb.op('LDA', 'abs', (name, i))
            else:
                fb.op('LDA', 'zp', (name, i))
        fb.label('top')
        if slots and slots[0].cls != MUST:
            fb.op('DEC', 'abs', (name, 0)).op('BNE', 'rel', 'in').op('JMP', 'abs', 'out').label('in')
        for target in callees:
            tname, tparams = target[1], target[3]
            for i in range(len(tparams)):
                fb.op('LDA', '#', i).op('STA', 'abs', (tname, i))
            flags = lo.C_SAVES if recursive_group and target[1] in recursive_group else 0
            fb.call(tname, flags).op('JSR', 'abs', tname)
            called.add(tname)
            calls += 1
        if rnd.random() < 0.3:
            v = '%s.v' % mods[rnd.randrange(mi, MODULES)]
            b.extern(v, lo.K_VAR)
            fb.op('LDA', 'abs', v).op('STA', 'abs', '%s.w' % mods[mi])
            b.extern('%s.w' % mods[mi], lo.K_VAR)
        if rnd.random() < 0.2:
            d = '%s.$1' % mods[rnd.randrange(mi, MODULES)]
            b.extern(d, lo.K_DATA)
            fb.op('LDA', 'abs,x', d)
        if rnd.random() < 0.15 and level > 8:
            k = rnd.randrange(0, len(classes))
            use_class(b, k)
            for i in range(len(classes[k][1])):
                fb.op('LDA', '#', i).op('STA', 'abs', (classes[k][0], i))
            fb.call(classes[k][0], lo.C_POINTER).op('JSR', 'abs', 'go').op('JMP', 'abs', 'past')
            fb.label('go').op('JMP', '(abs)', '%s.w' % mods[mi]).label('past')
            calls += 1
        if slots and slots[0].cls != MUST:
            fb.op('BEQ', 'rel', 'out').op('JMP', 'abs', 'top')
        fb.label('out').op('RTS')
        return fb

    # Library modules: p29 is the lowest, imported by all; p01 the highest. A call goes to a
    # module of a higher number, which is linked earlier, or to an earlier function of its own.
    weights = {}
    for mi in range(MODULES - 1, 0, -1):
        b = builders[mi]
        mine = [f for f in funcs if f[0] == mi]
        for f in sorted(mine, key=lambda f: f[2]):
            lower = [g for lvl in range(0, f[2]) for g in by_level.get(lvl, [])
                     if g[0] > mi or (g[0] == mi and g[1] < f[1])]
            n = min(len(lower), rnd.choice((2, 3, 4, 5, 6)))
            callees = rnd.sample(lower, n) if lower else []
            # the deepest chain: always call something one level down if there is one
            down = [g for g in lower if g[2] == f[2] - 1]
            if down and not any(g[2] == f[2] - 1 for g in callees):
                callees.append(rnd.choice(down))
            body(b, mi, f[1], f[2], f[3], callees)
            for g in callees:
                if g[0] != mi:
                    for i in range(len(g[3])):
                        weights[(mi, g[1], i)] = weights.get((mi, g[1], i), 0) + 1
        # members whose address this module takes, in a table of pointers
        mem = [f for f in mine if f[1] in members]
        if mem:
            d = b.data('%s.$2' % mods[mi], bytes(2 * len(mem)))
            for i, f in enumerate(mem):
                d.fix(2 * i, lo.FX_WORD, f[1])
                use_class(b, members[f[1]])
                b.memb(classes[members[f[1]]][0], f[1])
            fb = b.func('%s.tables' % mods[mi])
            fb.op('LDA', '#<', '%s.$2' % mods[mi]).op('LDX', '#>', '%s.$2' % mods[mi]).op('RTS')
            funcs.append((mi, '%s.tables' % mods[mi], 0, []))
        b.func('%s.unused' % mods[mi]).op('LDA', 'abs', '%s.buf' % mods[mi]).op('RTS')
    # The recursive group, in p01, and the interrupt function and main, in p00.
    b = builders[1]
    group = ['p01.r%d' % i for i in range(4)]
    leaves = [f for f in funcs if f[2] == 0][:3]
    for i, g in enumerate(group):
        nxt = [(1, group[(i + 1) % 4], 5, [1])]
        body(b, 1, g, 5, [1], nxt + [leaves[i % len(leaves)]], recursive_group=set(group))
    b = builders[0]
    tops = [f for f in funcs if f[2] >= LEVELS - 2 and f[0] != 0]
    callees = rnd.sample(tops, min(6, len(tops))) + [(1, group[0], 5, [1])]
    callees += [f for f in funcs if f[1] not in called and f not in callees and f[1] not in shared
                and rnd.random() < 0.9]
    body(b, 0, 'p00.main', LEVELS, [], callees)
    body(b, 0, 'p00.irq', 3, [], [f for f in funcs if f[1] in shared])
    b.module_.items[-1].flags |= lo.F_INTERRUPT
    for (mi, target, slot), w in sorted(weights.items()):
        builders[mi].wgt((target, slot), w)
    # Link order as build.py gives it: every module after those it imports, main last.
    return builders[::-1], calls
