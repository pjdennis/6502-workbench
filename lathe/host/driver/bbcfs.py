"""The names a Lathe program's files have on the BBC's filing system: the host's twin of
lathe/rt/bbc/bbcfs.lth's map() (lathe/docs/bbc.md, "File names on the BBC"), and where the
emulator's --bbc-fs dfs keeps a DFS file in its --disk directory, and --bbc-fs adfs an ADFS one.

    dfs_name('expr.lth')      -> 'L.EXPR'
    dfs_name('./err.lo')      -> 'O.ERR'
    dfs_name('2/asmblock.li') -> ':2.I.ASMBLOC'
    dfs_name('LATHE1.BIN')    -> 'B.LATHE1'
    dfs_name('HELLO')         -> 'HELLO'          (no ".": as it is)
    dfs_name('lib/k.li')      -> None             (no name: open gives 0)
    host_file('L.EXPR')       -> 'L.EXPR'         (the --disk directory's file)
    host_file('HELLO')        -> '$.HELLO'
    host_file(':2.I.ASMBLOC') -> ':2/I.ASMBLOC'

With BBCFS 2, ADFS:

    adfs_name('expr.lth')       -> 'lth.expr'
    adfs_name('./asmblock.lo')  -> 'lo.asmblock'
    adfs_name('1/kerneltest.li')-> ':1.li.kerneltest'
    adfs_name('LATHE1.BIN')     -> 'BIN.LATHE1'
    adfs_name('HELLO')          -> 'HELLO'
    adfs_name('2/x.lo')         -> None           (ADFS has drives 0 and 1)
    adfs_host_file(':1.li.x')   -> ':1/li/x'      (the --disk directory's file)

With BBCFS 3, the filing system asked of the MOS when a name is mapped (OSARGS's number):

    asked_name('expr.lth', 4)   -> 'L.EXPR'       (the DFS)
    asked_name('expr.lth', 8)   -> 'lth.expr'     (ADFS)
    asked_name('expr.lth', 5)   -> 'expr.lth'     (any other: as given)

The tests keep every mapping of a name through here, so that the host side of a test finds what
the BBC wrote.
"""
import os

# The directory of each extension (in small letters); any other is OTHER.
DIRECTORIES = {'lth': 'L', 'lo': 'O', 'li': 'I', 'map': 'M', 'env': 'E', 'bin': 'B'}
OTHER = 'X'
LONGEST = 7             # the DFS's longest name
OUT_SIZE = 13           # map()'s buffer: ":D.X.NAME" and the CR


def dfs_name(name):
    """The DFS name bbcfs.map() makes of `name`, or None if it makes none."""
    while name.startswith('./'):
        name = name[2:]
    drive = ''
    if len(name) >= 2 and name[0] in '0123' and name[1] == '/':
        drive, name = ':' + name[0] + '.', name[2:]
    if '/' in name:
        return None
    if '.' not in name:
        out = drive + name
        return out if len(out) <= OUT_SIZE - 1 else None
    stem, ext = name.rsplit('.', 1)
    if not stem or '.' in stem:
        return None
    directory = DIRECTORIES.get(''.join(chr(ord(c) + 32) if 'A' <= c <= 'Z' else c for c in ext), OTHER)
    return drive + directory + '.' + upper(stem)[:LONGEST]


def upper(text):
    """Small letters (ASCII) as capitals, nothing else changed, as map() does it."""
    return ''.join(chr(ord(c) - 32) if 'a' <= c <= 'z' else c for c in text)


def host_file(dfs):
    """Where the emulator's --bbc-fs dfs keeps the file of a DFS name, relative to --disk:
    drive 0 is the directory itself, drive N its subdirectory ':N'; the file is DIR.NAME, the
    directory $ if the name gives none."""
    folder = ''
    if dfs.startswith(':'):
        folder, dfs = ':' + dfs[1] + '/', dfs[3:]
        if folder == ':0/':
            folder = ''
    if len(dfs) < 2 or dfs[1] != '.':
        dfs = '$.' + dfs
    return folder + dfs


def host_path(disk, name):
    """The path in the --disk directory of the file the BBC opens as `name` (a name as the tools
    give it), under --bbc-fs dfs with BBCFS 1. ValueError if bbcfs makes no name of it."""
    dfs = dfs_name(name)
    if dfs is None:
        raise ValueError(f'bbcfs makes no DFS name of {name!r}')
    return os.path.join(disk, host_file(dfs))


ADFS_LONGEST = 10       # ADFS's longest name, and the longest extension bbcfs takes
ADFS_OUT_SIZE = 25      # map()'s buffer with BBCFS 2: ":D.EXT.STEM" and the CR


def adfs_name(name):
    """The ADFS name bbcfs.map() makes of `name` with BBCFS 2, or None if it makes none."""
    while name.startswith('./'):
        name = name[2:]
    drive = ''
    if len(name) >= 2 and name[0] in '01' and name[1] == '/':
        drive, name = ':' + name[0] + '.', name[2:]
    if '/' in name:
        return None
    if '.' not in name:
        out = drive + name
        return out if len(out) <= ADFS_OUT_SIZE - 1 else None
    stem, ext = name.rsplit('.', 1)
    if not stem or not ext or '.' in stem or len(ext) > ADFS_LONGEST:
        return None
    return drive + ext + '.' + stem[:ADFS_LONGEST]


def adfs_directory(adfs):
    """The directory a name adfs_name() made is in ('lth', ':1.lo'), or None for a root."""
    if '.' not in adfs:
        return None
    d = adfs.rsplit('.', 1)[0]
    return None if len(d) == 2 and d[0] == ':' else d


def adfs_host_file(adfs):
    """Where the emulator's --bbc-fs adfs keeps the file of an ADFS name (a path from the root:
    the names adfs_name makes), relative to --disk: drive 0 is the directory itself, drive 1
    its subdirectory ':1'; each directory a host directory."""
    folder = ''
    if adfs.startswith(':'):
        folder, adfs = ('' if adfs[1] == '0' else ':1/'), adfs[3:]
    return folder + adfs.replace('.', '/')


def adfs_host_path(disk, name):
    """The path in --disk of the file the BBC opens as `name` with BBCFS 2 under --bbc-fs adfs.
    ValueError if bbcfs makes no name of it."""
    adfs = adfs_name(name)
    if adfs is None:
        raise ValueError(f'bbcfs makes no ADFS name of {name!r}')
    return os.path.join(disk, adfs_host_file(adfs))


# With BBCFS 3 map() asks the MOS which filing system is current (OSARGS with A = 0 and Y = 0)
# and maps by the number it gives: these two, and any other number leaves the name as given.
DFS_NUMBER = 4
ADFS_NUMBER = 8


def asked_name(name, number):
    """The name bbcfs.map() makes of `name` with BBCFS 3 when OSARGS gives `number` for the
    filing system: the DFS's name (4), ADFS's (8), or for any other number the name as given."""
    if number == DFS_NUMBER:
        return dfs_name(name)
    if number == ADFS_NUMBER:
        return adfs_name(name)
    return name


def asked_host_file(name, number):
    """Where the emulator keeps the file the BBC opens as `name` with BBCFS 3, relative to
    --disk: under --bbc-fs dfs (4), --bbc-fs adfs (8), or --bbc-fs host with any other number
    (--bbc-fs-number), where the name as given is a path of the --disk directory."""
    if number == DFS_NUMBER:
        return host_file(dfs_name(name))
    if number == ADFS_NUMBER:
        return adfs_host_file(adfs_name(name))
    return os.path.normpath(name)


def find(disk, name):
    """The path of the file as the emulator's DFS matches it (upper and lower case alike), or None."""
    want = host_path(disk, name)
    folder, base = os.path.split(want)
    if not os.path.isdir(folder):
        return None
    for f in os.listdir(folder):
        if f.lower() == base.lower():
            return os.path.join(folder, f)
    return None
