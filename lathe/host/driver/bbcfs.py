"""The names a Lathe program's files have on the BBC's filing system: the host's twin of
lathe/rt/bbc/bbcfs.lth's map() (lathe/docs/bbc.md, "File names on the BBC"), and where the
emulator's --bbc-fs dfs keeps a DFS file in its --disk directory.

    dfs_name('expr.lth')      -> 'L.EXPR'
    dfs_name('./err.lo')      -> 'O.ERR'
    dfs_name('2/asmblock.li') -> ':2.I.ASMBLOC'
    dfs_name('LATHE1.BIN')    -> 'B.LATHE1'
    dfs_name('HELLO')         -> 'HELLO'          (no ".": as it is)
    dfs_name('lib/k.li')      -> None             (no name: open gives 0)
    host_file('L.EXPR')       -> 'L.EXPR'         (the --disk directory's file)
    host_file('HELLO')        -> '$.HELLO'
    host_file(':2.I.ASMBLOC') -> ':2/I.ASMBLOC'

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
