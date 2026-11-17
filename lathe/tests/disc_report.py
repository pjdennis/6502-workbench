"""Disc space of the tools' rebuild on Acorn DFS discs (lathe/docs/spikes.md, "Disc space for the
rebuild on two DFS discs, measured"). Measurement only: nothing here changes a tool.

    python3 lathe/tests/disc_report.py [OUT_DIR] [--linker]
    python3 lathe/tests/disc_report.py [OUT_DIR] --fit

Builds the files of test_bbc_dfs.Loop with the host's tools (which that test shows are the BBC's,
byte for byte): the compiler's modules as lathec-bbc.env with BBCFS 1 builds them, each compiled
in one directory, then linked with a command file. With --linker the same for the linker
(linker-bbc.env). Then reports, from the real files:

1. the inventory (source, object, interface per module; environment, command file, image, banks,
   map) and what each compile and the link need on line;
2. the sources: comments, blank lines, indentation, import lines, code; the "disc copy"
   (comments removed, every line kept) with indentation as is, as tabs or none; the sources
   coded with a fixed word table, with LZSS and with deflate (the first two decoded and compared);
3. the objects by record kind, and the object set re-encoded under each option (encode, decoded
   back to the same bytes by decode for every option that leaves nothing out); the interfaces by
   entry kind;
4. the map by line kind;
5. the disc copies compiled and linked again with the host's tools, and which files differ.

--fit builds both loops and fits each case's files to four 80-track sides (pack), the compiler's
loop, the linker's and both, in whole sectors.

OUT_DIR keeps the files (default: a temporary directory)."""
import collections
import os
import re
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'lathe', 'host', 'driver'))
sys.path.insert(0, HERE)

import bbcfs  # noqa: E402

SRC = os.path.join(ROOT, 'lathe', 'src')
SIDE = 800 * 256 - 2 * 256
CATALOGUE = 31

# ---- Making the files ---------------------------------------------------------------------------


def dfs_env(source, path):
    with open(source) as f:
        text = f.read()
    text, n = re.subn(r'(?m)^define\s+BBCFS\s+0\b', 'define    BBCFS 1', text)
    assert n == 1, source
    with open(path, 'w') as f:
        f.write(text)
    return path


def make(work, linker=False):
    """The loop's files, in work/flat: returns (compiles, link, {name: bytes} written, [source names])."""
    import test_bbc_toolchain as toolchain
    source, env = (('link.lth', 'linker-bbc.env') if linker else ('lathec.lth', 'lathec-bbc.env'))
    os.makedirs(work, exist_ok=True)
    env = dfs_env(os.path.join(SRC, env), os.path.join(work, env))
    steps = toolchain.recorded(os.path.join(SRC, source), env, os.path.join(work, 'build'))
    flat = os.path.join(work, 'flat')
    os.makedirs(flat)
    compiles, link = toolchain.lay_out(steps, flat)
    with open(os.path.join(flat, 'LINKARG'), 'w') as f:
        f.write(''.join(a + '\n' for a in link))
    inputs = {f: open(os.path.join(flat, f), 'rb').read() for f in os.listdir(flat)}
    files, said = toolchain.host_files(compiles, ['@LINKARG'], flat)
    assert said == [(0, b'')] * len(said), said
    files.update(inputs)
    return compiles, link, files


# ---- Sources ------------------------------------------------------------------------------------

def split_comment(line):
    """(code, comment) of a line of Lathe: `;` starts a comment outside a string or character."""
    q = None
    i = 0
    while i < len(line):
        c = line[i]
        if q:
            if c == '\\':
                i += 1
            elif c == q:
                q = None
        elif c in '"\'':
            q = c
        elif c == ';':
            return line[:i], line[i:]
        i += 1
    return line, ''


def source_parts(text):
    """Bytes of a source by kind: comment text (the `;` and what follows, and its line end on a
    line of only a comment), blank lines, indentation, trailing space, import lines, code, line ends."""
    parts = collections.Counter()
    in_import = False
    lines = text.split('\n')
    for n, line in enumerate(lines):
        end = 1 if n < len(lines) - 1 else 0
        code, comment = split_comment(line)
        stripped = code.strip()
        if not stripped and not comment:
            parts['blank'] += len(line) + end
            continue
        indent = len(code) - len(code.lstrip(' \t'))
        if not stripped:
            parts['indent of comment lines'] += indent
            parts['comment'] += len(comment) + end
            continue
        trailing = len(code) - len(code.rstrip(' \t'))
        parts['space before a comment' if comment else 'trailing space'] += trailing
        parts['comment'] += len(comment)
        body = len(code) - indent - trailing
        if in_import or re.match(r'\s*import\b', code):
            # an import line and the lines its open `(` continues onto, with their indentation and
            # line ends: what the import lists cost
            depth = (in_import or 0) + code.count('(') - code.count(')')
            parts['import lines'] += indent + body + end
            in_import = depth if depth > 0 else False
            continue
        parts['indent'] += indent
        parts['code'] += body
        parts['line ends'] += end
    return parts


def disc_copy(text, indent='keep', comments=False):
    """The source with comments (unless `comments`), trailing space and the indentation of blank
    lines removed; every line kept, so error positions' lines stay right (columns move with
    indent='tab' or 'none'). Indentation: as it is, a tab a level, or none."""
    out = []
    width = None
    for line in text.split('\n'):
        code, comment = split_comment(line)
        code = code.rstrip(' \t')
        if comments and comment:
            if code:
                code += line[len(code):len(line) - len(comment)]
            else:
                code = line[:len(line) - len(comment)]
            comment = comment.rstrip(' \t')
        else:
            comment = ''
        if indent == 'none':
            code = code.lstrip(' \t')
        elif indent != 'keep' and code:
            n = len(code) - len(code.lstrip(' '))
            if width is None and n:
                width = n
            level = n // (width or 4)
            code = ('\t' if indent == 'tab' else ' ') * level + code.lstrip(' ')
        out.append(code + comment)
    return '\n'.join(out)


def lead_comment(text):
    """Bytes of the comment lines before the module's first line of code."""
    n = 0
    for line in text.split('\n'):
        code, comment = split_comment(line)
        if code.strip():
            break
        n += len(line) + 1
    return n


WORD = re.compile(r'[A-Za-z_][A-Za-z0-9_]*| +|.', re.S)


def word_table(texts, codes=128, spaces=16):
    """A fixed table for sources, which are 7-bit: each byte $80-$FF stands for a word of the
    table, or for a run of 2 to spaces + 1 spaces. The table is the codes - spaces words (a word
    and the space after it counting as one) that save most over texts. Returns (the table's bytes
    as strings with a length byte, {name: bytes of the text so coded})."""
    cand = collections.Counter()
    for t in texts.values():
        toks = WORD.findall(t)
        for i, w in enumerate(toks):
            if len(w) > 1 and w[0] != ' ':
                cand[w] += 1
                if i + 1 < len(toks) and toks[i + 1] == ' ':
                    cand[w + ' '] += 1
    words = [w for w, n in sorted(cand.items(), key=lambda kv: (-kv[1] * (len(kv[0]) - 1), kv[0]))][:codes - spaces]
    index = {w: i for i, w in enumerate(words)}
    sizes = {}
    for name, t in texts.items():
        assert max(map(ord, t)) < 128
        toks = WORD.findall(t)
        out = bytearray()
        i = 0
        while i < len(toks):
            w = toks[i]
            if w[0] == ' ':
                left = len(w)
                while left > 0:
                    if left == 1:
                        out.append(32)
                        left = 0
                    else:
                        k = min(left, spaces + 1)
                        out.append(0x80 + len(words) + k - 2)
                        left -= k
                i += 1
            elif i + 1 < len(toks) and toks[i + 1] == ' ' and w + ' ' in index:
                out.append(0x80 + index[w + ' '])
                i += 2
            elif w in index:
                out.append(0x80 + index[w])
                i += 1
            else:
                out += w.encode('latin-1')
                i += 1
        # the expansion the compiler's reader would do
        back = ''.join(chr(b) if b < 0x80 else words[b - 0x80] if b - 0x80 < len(words)
                       else ' ' * (b - 0x80 - len(words) + 2) for b in out)
        assert back == t, name
        sizes[name] = len(out)
    return sum(len(w) + 1 for w in words), sizes


# A byte-oriented LZSS, for scale: a flag byte before each 8 items; a literal is a byte, a match
# two bytes (offset back into a window of 2**wbits bytes, length 3 to 3 + 2**(16 - wbits) - 1).
# Greedy, with hash chains; unlzss is the decoder, whose state is the window.

def lzss(data, wbits=10):
    lbits = 16 - wbits
    maxlen = 3 + (1 << lbits) - 1
    window = 1 << wbits
    out = bytearray()
    chains = collections.defaultdict(list)
    i = 0
    items = []
    while i < len(data):
        best = (0, 0)
        if i + 3 <= len(data):
            key = data[i:i + 3]
            for p in reversed(chains[key][-32:]):
                if i - p > window:
                    break
                n = 3
                while n < maxlen and i + n < len(data) and data[p + n] == data[i + n]:
                    n += 1
                if n > best[0]:
                    best = (n, i - p)
        n = best[0] if best[0] >= 3 else 1
        for j in range(i, min(i + n, len(data) - 2)):
            chains[data[j:j + 3]].append(j)
        if n >= 3:
            items.append((best[1], n))
        else:
            items.append(data[i])
        i += n
    for k in range(0, len(items), 8):
        group = items[k:k + 8]
        flag = 0
        body = bytearray()
        for b, it in enumerate(group):
            if isinstance(it, tuple):
                flag |= 1 << b
                off, n = it
                v = (off - 1) | ((n - 3) << wbits)
                body += bytes([v & 255, v >> 8])
            else:
                body.append(it)
        out.append(flag)
        out += body
    return bytes(out)


def unlzss(enc, wbits=10):
    out = bytearray()
    i = 0
    while i < len(enc):
        flag = enc[i]
        i += 1
        for b in range(8):
            if i >= len(enc):
                break
            if flag >> b & 1:
                v = enc[i] | enc[i + 1] << 8
                i += 2
                off = (v & ((1 << wbits) - 1)) + 1
                n = (v >> wbits) + 3
                for _ in range(n):
                    out.append(out[-off])
            else:
                out.append(enc[i])
                i += 1
    return bytes(out)


# ---- Objects ------------------------------------------------------------------------------------

NAMES = {0x00: 'END', 0x01: 'MOD', 0x02: 'IMP', 0x03: 'SYM', 0x04: 'VAR', 0x05: 'DATA', 0x06: 'DFIX',
         0x07: 'FUNC', 0x08: 'SLOT', 0x09: 'CALL', 0x0A: 'FIX', 0x0B: 'CODE', 0x0C: 'ENDF', 0x0D: 'CLAS',
         0x0E: 'MEMB', 0x0F: 'WGT', 0x10: 'RGN'}


def records(data):
    i = 0
    while i < len(data):
        t = data[i]
        n = data[i + 1] | data[i + 2] << 8
        yield t, data[i + 3:i + 3 + n]
        i += 3 + n
        if t == 0:
            break


def fixes(body):
    return [(body[i] | body[i + 1] << 8, body[i + 2], body[i + 3] | body[i + 4] << 8, body[i + 5],
             body[i + 6] | body[i + 7] << 8) for i in range(0, len(body), 8)]


def object_parts(data):
    """Bytes of an object file by what they hold: each record kind's headers (3 bytes), and its
    body, with the bytes of names apart."""
    parts = collections.Counter()
    for t, body in records(data):
        k = NAMES[t]
        parts[k + ' header'] += 3
        if t == 0x03:
            parts['SYM kind'] += 1
            parts['SYM name'] += len(body) - 1
        elif t == 0x08:
            parts['SLOT fields'] += 5
            parts['SLOT name'] += len(body) - 5
        elif t == 0x0B:
            parts['CODE bytes'] += len(body)
        elif t == 0x05:
            parts['DATA symbol'] += 2
            parts['DATA bytes'] += len(body) - 2
        elif t in (0x0A, 0x06):
            parts[k + ' entries'] += len(body)
        elif t == 0x0D:
            names = 0
            j = 4
            for _ in range(body[3]):
                j += 2
                names += 1 + body[j]
                j += 1 + body[j]
            parts['CLAS fields'] += len(body) - names
            parts['CLAS names'] += names
        else:
            parts[k + ' body'] += len(body)
    return parts


# The re-encodings. Each is a function of one object file's bytes to the bytes it would be, and
# each is decodable (`decode` checks the ones that are).

def uvar(n):
    """A variable-length number: 7 bits a byte, the top bit set on every byte but the last."""
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def short_header(t, body):
    """A record header of one byte of type and one of length when the body is below 255 bytes,
    else the type, 255 and two bytes."""
    if len(body) < 255:
        return bytes([t, len(body)]) + body
    return bytes([t, 255, len(body) & 255, len(body) >> 8]) + body


WIDTH = {1: 2, 2: 1, 3: 1, 4: 1, 5: 2, 6: 1, 7: 1, 8: 1}    # bytes a fix-up of each kind covers


def encode(data, opts):
    """data re-encoded with the options in opts (a set); decode(encode(data, opts), opts) gives
    data back for every option but 'noslotname' and 'nowgt', which leave something out:
    'hdr'    the short record header (short_header);
    'var'    numbers (symbols, sizes, offsets, addends) as variable-length numbers (uvar; a symbol
             as n + 1, $FFFF as 0; an addend zigzagged, so that -1 is one byte);
    'delta'  a FIX entry's offset as the distance from the one before it in the record;
    'fix4'   a FIX entry's fields packed: one byte of kind (4 bits) and flags, the slot only if not
             $FF, the addend only if not 0;
    'self'   (with fix4) a flag for "the symbol is the function being defined", which is then not
             written;
    'modref' a SYM name `m.name` written as the number of m among the MOD and IMP records so far
             and `name`, or $FF and the whole name;
    'noendf' ENDF left out: it always follows CODE;
    'slotrun' a function's SLOT records as one record: their count, then the entries;
    'callrun' a function's CALL records as one record likewise;
    'noslotname'  SLOT names left out (only the map's S lines and lo2asm use them);
    'nowgt'  WGT records left out (the linker's choice of zero page needs them: shown for scale);
    'holes'  CODE and DATA without the bytes their fix-ups cover, which the compiler writes as 0
             and the linker writes over: the reader puts the fix-up's bytes where they were."""
    out = bytearray()
    pending = {0x08: [], 0x09: []}
    mods = []
    cur = [None]

    def num(n, width=2):
        return uvar(n) if 'var' in opts else n.to_bytes(width, 'little')

    def sym(n):
        if 'var' in opts:
            return uvar(0 if n == 0xFFFF else n + 1)
        return n.to_bytes(2, 'little')

    def addend(a):
        if 'var' not in opts:
            return a.to_bytes(2, 'little')
        return uvar(a << 1 if a < 0x8000 else ((0x10000 - a) << 1) - 1)

    def emit(t, body):
        out.extend(short_header(t, body) if 'hdr' in opts else bytes([t]) + len(body).to_bytes(2, 'little') + body)

    held = []

    def holes(code):
        """code without the bytes the fix-ups held cover (all 0 as the compiler writes them)."""
        keep = bytearray(code)
        for off, kind, _, _, _ in reversed(held):
            n = WIDTH[kind]
            assert keep[off:off + n] == bytes(n)
            del keep[off:off + n]
        held.clear()
        return bytes(keep)

    def flush():
        for t in (0x08, 0x09):
            if pending[t]:
                emit(t, uvar(len(pending[t])) + b''.join(pending[t]))
                pending[t].clear()

    def fix_body(body, in_func):
        b = bytearray()
        last = 0
        for off, kind, s, slot, add in fixes(body):
            o = off - last if 'delta' in opts else off
            last = off
            if 'fix4' in opts:
                me = 'self' in opts and in_func and s == cur[0]
                b.append(kind | (0x10 if slot != 0xFF else 0) | (0x20 if add else 0) | (0x40 if me else 0))
                b += num(o)
                if not me:
                    b += sym(s)
                if slot != 0xFF:
                    b.append(slot)
                if add:
                    b += addend(add)
            else:
                b += num(o) + bytes([kind]) + sym(s) + bytes([slot]) + addend(add)
        return bytes(b)

    for t, body in records(data):
        if t == 0x08:
            name = body[5:] if 'noslotname' not in opts else b'\x00'
            b = num(body[0] | body[1] << 8) + body[2:5] + name
            if 'slotrun' in opts:
                pending[t].append(b)
            else:
                emit(t, b)
            continue
        if t == 0x09:
            b = sym(body[0] | body[1] << 8) + body[2:3] + sym(body[3] | body[4] << 8)
            if 'callrun' in opts:
                pending[t].append(b)
            else:
                emit(t, b)
            continue
        flush()
        if t == 0x0C:
            cur[0] = None
            if 'noendf' in opts:
                continue
        if t == 0x0F and 'nowgt' in opts:
            continue
        if t == 0x01:
            mods.append(body[2:])
        elif t == 0x02:
            mods.append(body)
        elif t == 0x03 and 'modref' in opts:
            name = body[2:]
            m, dot, rest = name.partition(b'.')
            key = bytes([len(m)]) + m
            if dot and key in mods:
                body = body[:1] + bytes([mods.index(key), len(rest)]) + rest
            else:
                body = body[:1] + b'\xff' + body[1:]
        elif t == 0x04:
            body = sym(body[0] | body[1] << 8) + num(body[2] | body[3] << 8) + body[4:]
        elif t == 0x05:
            body = sym(body[0] | body[1] << 8) + (holes(body[2:]) if 'holes' in opts else body[2:])
        elif t == 0x0B and 'holes' in opts:
            body = holes(body)
        elif t == 0x07:
            cur[0] = body[0] | body[1] << 8
            body = sym(cur[0]) + body[2:]
        elif t in (0x0A, 0x06):
            held[:] = fixes(body)
            body = fix_body(body, t == 0x0A)
        elif t == 0x0E:
            body = sym(body[0] | body[1] << 8) + sym(body[2] | body[3] << 8)
        elif t == 0x0F:
            body = b''.join(sym(body[i] | body[i + 1] << 8) + body[i + 2:i + 4] for i in range(0, len(body), 4))
        emit(t, body)
    return bytes(out)


class _Body:
    def __init__(self, b, opts):
        self.b, self.p, self.opts = b, 0, opts

    def byte(self):
        self.p += 1
        return self.b[self.p - 1]

    def uvar(self):
        n, shift = 0, 0
        while True:
            c = self.byte()
            n |= (c & 0x7F) << shift
            shift += 7
            if c < 0x80:
                return n

    def num(self):
        return self.uvar() if 'var' in self.opts else self.byte() | self.byte() << 8

    def sym(self):
        if 'var' in self.opts:
            n = self.uvar()
            return 0xFFFF if n == 0 else n - 1
        return self.byte() | self.byte() << 8

    def addend(self):
        if 'var' not in self.opts:
            return self.byte() | self.byte() << 8
        v = self.uvar()
        return v >> 1 if v & 1 == 0 else 0x10000 - ((v + 1) >> 1)

    def rest(self):
        r = self.b[self.p:]
        self.p = len(self.b)
        return r

    def more(self):
        return self.p < len(self.b)


def decode(data, opts):
    """The object file that encode(original, opts) was made from."""
    out = bytearray()
    mods = []
    cur = None
    i = 0

    def put(t, body):
        out.extend(bytes([t]) + len(body).to_bytes(2, 'little') + body)

    def w(n):
        return n.to_bytes(2, 'little')

    held = []

    def unholes(code):
        code = bytearray(code)
        for off, kind in held:
            code[off:off] = bytes(WIDTH[kind])
        held.clear()
        return bytes(code)

    while i < len(data):
        t = data[i]
        if 'hdr' in opts:
            n = data[i + 1]
            i += 2
            if n == 255:
                n = data[i] | data[i + 1] << 8
                i += 2
        else:
            n = data[i + 1] | data[i + 2] << 8
            i += 3
        r = _Body(data[i:i + n], opts)
        i += n
        if t == 0x08:
            for _ in range(r.uvar() if 'slotrun' in opts else 1):
                size = r.num()
                fields = bytes([r.byte(), r.byte(), r.byte()])
                ln = r.byte()
                put(t, w(size) + fields + bytes([ln]) + bytes(r.byte() for _ in range(ln)))
            continue
        if t == 0x09:
            for _ in range(r.uvar() if 'callrun' in opts else 1):
                callee = r.sym()
                flags = r.byte()
                put(t, w(callee) + bytes([flags]) + w(r.sym()))
            continue
        if t == 0x01:
            body = r.rest()
            mods.append(body[2:])
        elif t == 0x02:
            body = r.rest()
            mods.append(body)
        elif t == 0x03 and 'modref' in opts:
            kind = r.byte()
            m = r.byte()
            rest = r.rest()
            if m == 0xFF:
                body = bytes([kind]) + rest
            else:
                name = mods[m][1:] + b'.' + rest[1:]
                body = bytes([kind, len(name)]) + name
        elif t == 0x04:
            body = w(r.sym()) + w(r.num()) + r.rest()
        elif t == 0x05:
            body = w(r.sym()) + (unholes(r.rest()) if 'holes' in opts else r.rest())
        elif t == 0x0B and 'holes' in opts:
            body = unholes(r.rest())
        elif t == 0x07:
            cur = r.sym()
            body = w(cur) + r.rest()
        elif t in (0x0A, 0x06):
            body = bytearray()
            last = 0
            while r.more():
                if 'fix4' in opts:
                    flag = r.byte()
                    kind = flag & 0x0F
                    off = r.num()
                    s = cur if flag & 0x40 else r.sym()
                    slot = r.byte() if flag & 0x10 else 0xFF
                    add = r.addend() if flag & 0x20 else 0
                else:
                    off = r.num()
                    kind = r.byte()
                    s = r.sym()
                    slot = r.byte()
                    add = r.addend()
                if 'delta' in opts:
                    off += last
                last = off
                body += w(off) + bytes([kind]) + w(s) + bytes([slot]) + w(add)
                held.append((off, kind))
            body = bytes(body)
        elif t == 0x0E:
            body = w(r.sym()) + w(r.sym())
        elif t == 0x0F:
            body = bytearray()
            while r.more():
                body += w(r.sym()) + bytes([r.byte(), r.byte()])
            body = bytes(body)
        else:
            body = r.rest()
        put(t, body)
        if t == 0x0B and 'noendf' in opts:
            put(0x0C, b'')
        if t in (0x0B, 0x0C) and ('noendf' in opts or t == 0x0C):
            cur = None
    return bytes(out)


LI_KINDS = {1: 'function', 2: 'constant', 3: 'variable', 4: 'named type', 5: 'record', 6: 'enumeration',
            7: 'function type', 8: 'module', 9: 'constant in a region', 10: 'uses'}


def interface_parts(data):
    """Bytes of an interface by entry kind ('entry ...', 'header', 'end': these sum to the file),
    walked by the rules of lathe/host/README.md, "The interface file"; and, within them, the
    bytes of names (strings, 'in names ...') and of inline functions' saved tokens ('in tokens')."""
    parts = collections.Counter()
    pos = [3]

    def byte():
        b = data[pos[0]]
        pos[0] += 1
        return b

    def string(what):
        n = byte()
        pos[0] += n
        parts['in names: ' + what] += 1 + n

    def typ():
        t = byte()
        while t in (0x10, 0x11, 0x12):
            if t != 0x10:
                pos[0] += 2
            t = byte()
        if t == 0x13:
            string('type references')
            string('type references')

    def members():
        n = byte()
        for _ in range(n):
            typ()
            byte()
        return n

    n = data[3]
    parts['header'] += 4 + n
    pos[0] = 4 + n
    while True:
        start = pos[0]
        kind = byte()
        if kind == 0:
            parts['end'] += 1
            break
        if kind == 8:
            parts['module ' + data[pos[0] + 1:pos[0] + 1 + data[pos[0]]].decode()] = 0
        string('entries')
        if kind == 1:
            flags = byte()
            if flags & 1:
                pos[0] += 2
            params = members()
            members()
            if flags & 8:
                t0 = pos[0]
                string('inline: file')
                pos[0] += 3
                if byte():
                    string('inline: parameters and written')
                for _ in range(params):
                    string('inline: parameters and written')
                    byte()
                while True:
                    t = byte()
                    if t == 0:
                        break
                    byte()
                    if t == 2:
                        string('inline: tokens')
                    elif t == 3:
                        pos[0] += 2
                    elif t == 4:
                        pos[0] += byte()
                parts['in inline bodies'] += pos[0] - t0
        elif kind in (2, 9):
            typ()
            pos[0] += 2
            if kind == 9:
                string('regions')
        elif kind == 3:
            typ()
            p = byte()
            if p == 1:
                pos[0] += 2
            elif p == 8:
                string('regions')
        elif kind == 4:
            byte()
            typ()
        elif kind == 5:
            byte()
            for _ in range(byte()):
                string('fields')
                typ()
        elif kind == 6:
            byte()
        elif kind == 7:
            byte()
            members()
            members()
        elif kind == 10:
            for _ in range(byte()):
                string('uses')
                string('uses')
        parts['entry ' + LI_KINDS[kind]] += pos[0] - start
        parts['count ' + LI_KINDS[kind]] += 1
    assert pos[0] == len(data), (pos[0], len(data))
    return parts


# ---- Maps ---------------------------------------------------------------------------------------

def map_parts(text):
    parts = collections.Counter()
    count = collections.Counter()
    for line in text.splitlines(True):
        k = line[:1]
        parts[k] += len(line)
        count[k] += 1
    return parts, count


# ---- The report -----------------------------------------------------------------------------------

def report(work, linker=False):
    compiles, link, files = make(work, linker)
    stems = [os.path.splitext(a[-2])[0] for a in compiles]
    env = link[0]
    image = link[2]
    banks = sorted(f for f in files if f.upper().endswith('.BIN'))
    print('# %s: %d modules' % ('the linker' if linker else 'the compiler', len(stems)))
    print('\n## Inventory (bytes; DFS names)')
    print('| module | source | object | interface |')
    print('|---|---|---|---|')
    tot = collections.Counter()
    for s in stems:
        src, lo, li = len(files[s + '.lth']), len(files[s + '.lo']), len(files.get(s + '.li', b''))
        tot.update(src=src, lo=lo, li=li, nli=1 if s + '.li' in files else 0)
        print('| %s | %d | %d | %d |' % (s, src, lo, li))
    print('| **total** (%d, %d, %d files) | %d | %d | %d |' % (len(stems), len(stems), tot['nli'],
                                                             tot['src'], tot['lo'], tot['li']))
    other = [env, 'LINKARG', image] + banks + [link[3]]
    for f in other:
        print('| %s (%s) | %d |' % (f, bbcfs.dfs_name(f), len(files[f])))
    print('image and banks: %d bytes, %d files' % (sum(len(files[f]) for f in [image] + banks), 1 + len(banks)))

    # Steps: what each compile needs on line.
    print('\n## What each step needs on line')
    import_re = re.compile(rb'(?m)^\s*import\s+([a-z_0-9]+)')
    worst = (0, None)
    for s in stems:
        text = files[s + '.lth']
        # The interfaces the compile reads: its imports and, through LI_MODULE entries, theirs.
        need = set()
        todo = [m.decode() for m in import_re.findall(text)]
        while todo:
            m = todo.pop()
            if m in need or m + '.li' not in files:
                continue
            need.add(m)
            # the modules its kind 8 entries name, which the compile reads too
            todo += [k[7:] for k in interface_parts(files[m + '.li']) if k.startswith('module ')]
        on = len(text) + sum(len(files[m + '.li']) for m in need) + len(files[s + '.lo']) + len(files.get(s + '.li', b''))
        print('| %s | %s | %d files | %d bytes |' % (s, ' '.join(sorted(need)), 3 + len(need), on))
        if on > worst[0]:
            worst = (on, s)
    print('largest compile on line (source + interfaces it may read + its object and interface): %d bytes (%s)'
          % worst)
    objs = sum(len(files[s + '.lo']) for s in stems)
    print('the link: environment %d + command file %d + objects %d + image and banks %d + map %d = %d bytes, %d files'
          % (len(files[env]), len(files['LINKARG']), objs, sum(len(files[f]) for f in [image] + banks),
             len(files[link[3]]),
             len(files[env]) + len(files['LINKARG']) + objs + sum(len(files[f]) for f in [image] + banks) + len(files[link[3]]),
             3 + len(stems) + 1 + len(banks)))

    # Sources.
    print('\n## Sources by kind (bytes)')
    keys = ['comment', 'blank', 'indent', 'indent of comment lines', 'trailing space', 'space before a comment',
            'import lines', 'code', 'line ends']
    print('| module | ' + ' | '.join(keys) + ' | lead comment | disc copy | tabs | no indentation |')
    print('|' + '---|' * (len(keys) + 5))
    st = collections.Counter()
    for s in stems:
        text = files[s + '.lth'].decode('latin-1')
        p = source_parts(text)
        assert sum(p.values()) == len(text), (s, sum(p.values()), len(text))
        d = disc_copy(text)
        assert d.count('\n') == text.count('\n')
        dt = disc_copy(text, 'tab')
        d1 = disc_copy(text, 'none')
        p['lead'] = lead_comment(text)
        p['disc'], p['tab'], p['one'] = len(d), len(dt), len(d1)
        p['z'] = len(zlib.compress(text.encode('latin-1'), 9))
        p['zd'] = len(zlib.compress(dt.encode('latin-1'), 9))
        st.update(p)
        print('| %s | ' % s + ' | '.join(str(p[k]) for k in keys) + ' | %d | %d | %d | %d |'
              % (p['lead'], p['disc'], p['tab'], p['one']))
    print('| **total** | ' + ' | '.join(str(st[k]) for k in keys) + ' | %d | %d | %d | %d |'
          % (st['lead'], st['disc'], st['tab'], st['one']))
    print('deflate (zlib -9) of the sources: %d; of the tab disc copies: %d' % (st['z'], st['zd']))
    for wbits in (10, 12):
        n = 0
        for s in stems:
            z = zlib.compressobj(9, zlib.DEFLATED, -wbits)
            n += len(z.compress(files[s + '.lth']) + z.flush())
        print('raw deflate with a %d-byte window: %d' % (1 << wbits, n))
    for wbits in (10, 11):
        n = 0
        for s in stems:
            e = lzss(files[s + '.lth'], wbits)
            assert unlzss(e, wbits) == files[s + '.lth']
            n += len(e)
        print('LZSS with a %d-byte window, decoded and compared: %d' % (1 << wbits, n))
    tb, ws = word_table({s: files[s + '.lth'].decode('latin-1') for s in stems})
    print('word table (128 codes, 16 of them runs of spaces; the table %d bytes): the sources %d bytes, '
          'expanded back and compared' % (tb, sum(ws.values())))

    # Objects.
    print('\n## Objects by record kind (bytes, all modules)')
    op = collections.Counter()
    nrec = collections.Counter()
    for s in stems:
        data = files[s + '.lo']
        p = object_parts(data)
        assert sum(p.values()) == len(data), s
        op.update(p)
        for t, _ in records(data):
            nrec[NAMES[t]] += 1
    total = sum(op.values())
    for k, v in sorted(op.items(), key=lambda kv: -kv[1]):
        print('| %s | %d | %.1f %% |' % (k, v, 100 * v / total))
    print('records: ' + ', '.join('%s %d' % kv for kv in sorted(nrec.items(), key=lambda kv: -kv[1])))
    print('total %d' % total)
    fixstat = collections.Counter()
    for s in stems:
        for t, body in records(files[s + '.lo']):
            if t in (0x0A, 0x06):
                last = 0
                for off, kind, sy, slot, add in fixes(body):
                    fixstat['kind %d' % kind] += 1
                    fixstat['slot $FF' if slot == 0xFF else 'slot n'] += 1
                    fixstat['addend 0' if add == 0 else 'addend'] += 1
                    fixstat['delta<128' if off - last < 128 else 'delta>=128'] += 1
                    fixstat['sym<127' if sy < 127 else 'sym>=127'] += 1
                    last = off
    print('fix-up entries: ' + ', '.join('%s %d' % kv for kv in sorted(fixstat.items())))

    print('\n## The object set re-encoded')
    chosen = {'hdr', 'fix4', 'self', 'delta', 'var', 'noendf', 'slotrun', 'callrun', 'modref', 'holes'}
    options = [
        ('as written', set()),
        ('short headers', {'hdr'}),
        ('variable-length numbers', {'var'}),
        ('var + fix-up offsets as deltas', {'var', 'delta'}),
        ('packed fix-ups', {'fix4'}),
        ('packed fix-ups + "this function"', {'fix4', 'self'}),
        ('packed fix-ups + this function + deltas + var', {'fix4', 'self', 'delta', 'var'}),
        ('names of SYM by module number', {'modref'}),
        ('ENDF left out', {'noendf'}),
        ('SLOTs and CALLs as one record each', {'slotrun', 'callrun'}),
        ('no slot names', {'noslotname'}),
        ('CODE and DATA without the bytes under fix-ups', {'holes'}),
        ('no WGT (not an option: scale)', {'nowgt'}),
        ('chosen: all of the lossless ones', chosen),
        ('chosen, numbers fixed-width (no var, no delta)', chosen - {'var', 'delta'}),
        ('chosen, without modref', chosen - {'modref'}),
        ('chosen, without holes', chosen - {'holes'}),
        ('chosen + no slot names', chosen | {'noslotname'}),
    ]
    base = sum(len(files[s + '.lo']) for s in stems)
    for name, opts in options:
        n = 0
        for s in stems:
            e = encode(files[s + '.lo'], opts)
            if not opts & {'noslotname', 'nowgt'}:
                assert decode(e, opts) == files[s + '.lo'], (s, opts)
            n += len(e)
        print('| %s | %d | %+d |' % (name, n, n - base))
    z = sum(len(zlib.compress(files[s + '.lo'], 9)) for s in stems)
    print('| deflate -9 of each object | %d | %+d |' % (z, z - base))
    for wbits in (10,):
        for name, opts in (('as written', set()), ('chosen', chosen)):
            n = 0
            for s in stems:
                e = encode(files[s + '.lo'], opts)
                c = lzss(e, wbits)
                assert unlzss(c, wbits) == e
                n += len(c)
            print('| LZSS (%d-byte window) of the objects %s | %d | %+d |' % (1 << wbits, name, n, n - base))

    # Interfaces.
    li = [s for s in stems if s + '.li' in files]
    print('\n## Interfaces: %d files, %d bytes' % (len(li), sum(len(files[s + '.li']) for s in li)))
    ip = collections.Counter()
    for s in li:
        p = interface_parts(files[s + '.li'])
        assert sum(v for k, v in p.items() if k.startswith(('entry', 'header', 'end'))) == len(files[s + '.li'])
        ip.update(p)
    for k in sorted(ip, key=lambda k: (k[:2], -ip[k])):
        if k.startswith('module '):
            continue
        print('| %s | %d |' % (k, ip[k]))

    # The map.
    mtext = files[link[3]].decode('latin-1')
    mp, mc = map_parts(mtext)
    print('\n## The map: %d bytes, %d lines' % (len(mtext), sum(mc.values())))
    for k in sorted(mp, key=lambda k: -mp[k]):
        print('| %s | %d lines | %d bytes |' % (k, mc[k], mp[k]))
    return files, compiles, link


def check_disc_copies(work, compiles, files, indent, comments=False):
    """Compile and link the disc copies (disc_copy(indent)) of the sources with the host's tools
    as the loop does, and say which files differ from those of the readable sources."""
    import test_bbc_toolchain as toolchain
    d = os.path.join(work, 'copy-' + indent + ('-comments' if comments else ''))
    os.makedirs(d)
    names = [a[-2] for a in compiles]
    for f, data in files.items():
        if f in names:
            data = disc_copy(data.decode('latin-1'), indent, comments).encode('latin-1')
        if f in names or f.endswith('.env') or f == 'LINKARG':
            with open(os.path.join(d, f), 'wb') as fh:
                fh.write(data)
    got, said = toolchain.host_files(compiles, ['@LINKARG'], d)
    assert said == [(0, b'')] * len(said), said
    differ = sorted(f for f in got if got[f] != files.get(f))
    print('disc copies, indentation %s%s: %d files written, %s differ' % (indent, ', comments kept' if comments else '', len(got), ', '.join(differ) or 'none'))


# ---- Fitting the files to four sides ------------------------------------------------------------

SECTORS = SIDE // 256           # 798 sectors of a side beside the catalogue
SIDES = 4


def sectors(n):
    return (n + 255) // 256


def pack(groups, sides=SIDES, limit=2_000_000, margin=0):
    """Assign groups [(label, sectors, files, ...)] to sides, each at most SECTORS - margin sectors
    and CATALOGUE files; a group stays on one side. Returns ([[group...] per side], True), or
    (None, True) if there is no such assignment, or (None, False) if none was found in `limit`
    steps. Tries the emptiest side first for each group, largest first, then a search."""
    room = SECTORS - margin
    order = sorted(groups, key=lambda g: (-g[1], -g[2]))
    if sum(g[1] for g in order) > sides * room or sum(g[2] for g in order) > sides * CATALOGUE:
        return None, True
    out = [[] for _ in range(sides)]
    ok = True
    for g in order:
        free = [d for d in range(sides) if sum(x[1] for x in out[d]) + g[1] <= room
                and sum(x[2] for x in out[d]) + g[2] <= CATALOGUE]
        if not free:
            ok = False
            break
        out[min(free, key=lambda d: (sum(x[1] for x in out[d]), len(out[d])))].append(g)
    if ok:
        return out, True
    used = [[0, 0] for _ in range(sides)]
    where = [None] * len(order)
    steps = [0]

    def go(i):
        steps[0] += 1
        if steps[0] > limit:
            raise TimeoutError
        if i == len(order):
            return True
        g = order[i]
        tried_empty = False
        start = where[i - 1] if i and order[i - 1][1:] == g[1:] else 0
        for d in range(start, sides):
            if used[d] == [0, 0]:
                if tried_empty:
                    continue
                tried_empty = True
            if used[d][0] + g[1] <= room and used[d][1] + g[2] <= CATALOGUE:
                used[d][0] += g[1]
                used[d][1] += g[2]
                where[i] = d
                if go(i + 1):
                    return True
                used[d][0] -= g[1]
                used[d][1] -= g[2]
        return False

    try:
        if not go(0):
            return None, True
    except TimeoutError:
        return None, False
    out = [[] for _ in range(sides)]
    for g, d in zip(order, where):
        out[d].append(g)
    return out, True


def loop_groups(files, compiles, link, source='readable', objects='as written', maps='full',
                table=None, seen=None):
    """The groups of one loop's files: each module's source; its object and interface (one
    compile writes both in one directory); the environment; the command file; the image and its
    bank files (written beside it); the map. Modules in `seen` (a set, updated) are left out:
    their files are on the discs already, for the other tool's loop."""
    seen = set() if seen is None else seen
    out = []
    chosen = {'hdr', 'fix4', 'self', 'delta', 'var', 'noendf', 'slotrun', 'callrun', 'modref', 'holes'}
    for args in compiles:
        name = args[-2]
        stem = os.path.splitext(name)[0]
        if stem in seen:
            continue
        seen.add(stem)
        text = files[name].decode('latin-1')
        n = {'readable': len(text), 'disc copy': len(disc_copy(text)), 'tabs': len(disc_copy(text, 'tab')),
             'word table': table.get(name, 0) if table else 0,
             'LZSS 1 KB': len(lzss(files[name], 10)),
             'comments, tabs': len(disc_copy(text, 'tab', True)),
             'no header': len(text) - lead_comment(text),
             'no header, tabs': len(disc_copy(text, 'tab', True)) - lead_comment(text)}[source]
        out.append(('L.' + stem, sectors(n), 1, 'source', n))
        lo = files[stem + '.lo']
        m = {'as written': len(lo), 'chosen': len(encode(lo, chosen)),
             'chosen, no slot names': len(encode(lo, chosen | {'noslotname'}))}[objects]
        li = len(files.get(stem + '.li', b''))
        out.append(('O+I.' + stem, sectors(m) + sectors(li), 2, 'object and interface', m + li))
    env, image, mapname = link[0], link[2], link[3]
    out.append(('E', sectors(len(files[env])), 1, 'environment and command file', len(files[env])))
    out.append(('LINKARG', sectors(len(files['LINKARG'])), 1, 'environment and command file', len(files['LINKARG'])))
    banks = [f for f in files if f.upper().endswith('.BIN')] + [image]
    n = sum(len(files[f]) for f in banks)
    out.append(('B.' + image, sum(sectors(len(files[f])) for f in banks), len(banks), 'image and banks', n))
    text = files[mapname].decode('latin-1')
    m = {'full': len(text), 'no slot lines': sum(len(l) for l in text.splitlines(True) if l[:1] != 'S'),
         'W lines': sum(len(l) for l in text.splitlines(True) if l[:1] == 'W'), 'none': None}[maps]
    if m is not None:
        out.append(('M.' + image, sectors(m), 1, 'map', m))
    return out


RAM_FORM = [('MODULE and LOADMOD', 768 + 2, 2, 'module image (RAM form)', 196608 + 459)]


def fit_report(c, l):
    """c, l: (files, compiles, link) of the compiler's loop and the linker's."""
    texts = {}
    for files, compiles, _ in (c, l):
        for args in compiles:
            texts[args[-2]] = files[args[-2]].decode('latin-1')
    tbytes, table = word_table({k: v for k, v in texts.items()})
    print('\n## Fitting four sides (%d sectors and %d files a side; sizes in whole sectors)' % (SECTORS, CATALOGUE))
    print('word table: %d bytes (in ROM), the sources coded: %d of %d bytes' %
          (tbytes, sum(table.values()), sum(len(t) for t in texts.values())))
    scenarios = [
        ('readable sources, objects as written, full map', 'readable', 'as written', 'full'),
        ('readable, no map', 'readable', 'as written', 'none'),
        ('readable, objects re-encoded, no map', 'readable', 'chosen', 'none'),
        ('readable, objects re-encoded without slot names, no map', 'readable', 'chosen, no slot names', 'none'),
        ('readable with tabs, objects re-encoded, no map', 'comments, tabs', 'chosen', 'none'),
        ('header comments moved out, objects re-encoded, no map', 'no header', 'chosen', 'none'),
        ('header comments moved out, objects re-encoded, map without S lines', 'no header', 'chosen', 'no slot lines'),
        ('header comments moved out, tabs, objects re-encoded, no map', 'no header, tabs', 'chosen', 'none'),
        ('header comments moved out, tabs, objects re-encoded, map without S lines', 'no header, tabs', 'chosen',
         'no slot lines'),
        ('LZSS 1 KB, objects as written, no map', 'LZSS 1 KB', 'as written', 'none'),
        ('LZSS 1 KB, objects re-encoded, full map', 'LZSS 1 KB', 'chosen', 'full'),
        ('LZSS 1 KB, objects re-encoded, map without S lines', 'LZSS 1 KB', 'chosen', 'no slot lines'),
        ('LZSS 1 KB, objects re-encoded, no map', 'LZSS 1 KB', 'chosen', 'none'),
        ('word table, objects as written, no map', 'word table', 'as written', 'none'),
        ('word table, objects re-encoded, full map', 'word table', 'chosen', 'full'),
        ('word table, objects re-encoded, map without S lines', 'word table', 'chosen', 'no slot lines'),
        ('word table, objects re-encoded, no map', 'word table', 'chosen', 'none'),
        ('disc copy, objects as written, full map', 'disc copy', 'as written', 'full'),
        ('disc copy, objects as written, no map', 'disc copy', 'as written', 'none'),
        ('disc copy, objects re-encoded, full map', 'disc copy', 'chosen', 'full'),
        ('disc copy, objects re-encoded, map without S lines', 'disc copy', 'chosen', 'no slot lines'),
        ('disc copy, objects re-encoded, no map', 'disc copy', 'chosen', 'none'),
        ('tabs, objects re-encoded, map without S lines', 'tabs', 'chosen', 'no slot lines'),
        ('tabs, objects re-encoded, no map', 'tabs', 'chosen', 'none'),
    ]
    print('| case | loop | files | sectors | bytes | sectors over four sides | fits | fits, 64 sectors free a side | with the RAM form |')
    print('|---|---|---|---|---|---|---|---|---|')
    shown = []
    for title, source, objects, maps in scenarios:
        for which in ('compiler', 'linker', 'both'):
            seen = set()
            groups = []
            if which != 'linker':
                groups += loop_groups(*c, source, objects, maps, table, seen)
            if which != 'compiler':
                groups += loop_groups(*l, source, objects, maps, table, seen)
            res = [pack(groups), pack(groups, margin=64), pack(groups + RAM_FORM)]
            word = ['yes' if r[0] else ('no' if r[1] else 'not found') for r in res]
            tot = sum(g[1] for g in groups)
            print('| %s | %s | %d | %d | %d | %+d | %s | %s | %s |' % (
                title, which, sum(g[2] for g in groups), tot, sum(g[4] for g in groups), tot - SIDES * SECTORS,
                *word))
            if which == 'compiler' and (res[1][0] or res[0][0]):
                shown.append((title, res[1][0] or res[0][0], 64 if res[1][0] else 0))
    for title, sides, margin in shown:
        print('\n%s (%s):' % (title, 'at least 64 sectors free a side' if margin else 'packed full'))
        for d, gs in enumerate(sides):
            kinds = collections.Counter()
            for g in gs:
                kinds[g[3]] += g[2]
            print('  side %d: %d files, %d sectors, %d free: %s' % (
                d, sum(g[2] for g in gs), sum(g[1] for g in gs), SECTORS - sum(g[1] for g in gs),
                ', '.join('%s %d' % kv for kv in sorted(kinds.items()))))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    work = args[0] if args else tempfile.mkdtemp(prefix='lathe-disc-')
    if '--fit' in sys.argv:
        with open(os.devnull, 'w') as quiet:
            real, sys.stdout = sys.stdout, quiet
            try:
                c = report(os.path.join(work, 'compiler'))
                l = report(os.path.join(work, 'linker'), True)
            finally:
                sys.stdout = real
        fit_report((c[0], c[1], c[2]), (l[0], l[1], l[2]))
        return
    linker = '--linker' in sys.argv
    work = os.path.join(work, 'linker' if linker else 'compiler')
    files, compiles, link = report(work, linker)
    print()
    for indent, comments in (('keep', False), ('tab', False), ('none', False), ('tab', True)):
        check_disc_copies(work, compiles, files, indent, comments)


if __name__ == '__main__':
    main()
