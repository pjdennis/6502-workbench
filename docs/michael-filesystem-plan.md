# Plan: a filesystem on an SD card for Michael

Goal: a very simple filesystem on an SD card, so Michael can keep its sources, binaries and tools on the
board, and the editor and, later, the assembler can work from it without a PC. It provides:
- a directory listing;
- reading and writing whole files;
- streaming to and from files, byte by byte, as the editor and the assembler already do through `open`,
  `openout`, `read`, `write` and `close`;
- random access within files (seek, and update in place);
- several files open at once, writers included: the assembler's nested includes beside its output, and the
  editor's working file (below) beside the file it saves.

It must be **flash-friendly**: no sector is rewritten more often than any other, so there are no hot spots
for the card to wear out. It may use the facts that files are small (the largest about the source of a
program that assembles to 32 KB) and that the card is huge by comparison, so space can be spent freely.

**Status (2026-10-07): proposed.** Nothing is built.

## What we have to work with

- **Michael:** a 65C02 at 2 MHz with 16 KB of RAM (`$0000`–`$3FFF`), a 32 KB EEPROM holding the loader and the
  services behind the asm17 environment's vectors (`michael_rom.inc`, `asm/17/environment.asm`), and the
  FPGA bus ([`michael-fpga-bus-plan.md`](michael-fpga-bus-plan.md)). RAM is the scarce resource: the editor
  already uses all of it.
- **The FPGA** (Cmod A7-35T) is reached through commands on the bus. Command codes `$4x` are reserved for
  storage, the `ID` reply has a capabilities bit for it (bit 2), and devices `$81`–`$FF` are free. A byte
  read over the bus takes about 6 µs, so about 160 KB/s at best. The A7-35T has about 225 KB of block RAM, of
  which text mode uses a small part.
- **The SD card** is wired to the FPGA, not to Michael: a Digilent Pmod MicroSD (or any 3.3 V SPI microSD
  breakout) on the Cmod's Pmod header, run in SPI mode by the FPGA. The FPGA does the card's protocol;
  Michael never sees SPI.
- **The programs' file calls.**
  - The assembler's source stack (`asm/17/source_stack.asm`) opens each `.include` while the including file
    stays open, so a nest of includes is a stack of open readers, limited only by the source stack's memory.
    Its output (`asm/17/asm.asm`) is open for writing all the while.
  - The editor writes with `openout`/`write`/`close` (`editor/command.asm`).
  - `opendir` streams entries as a metadata byte and a NUL-terminated name, sorted.
  - Michael's ROM answers all of these with "none" today.
- **The editor's next step** is a working file, in the spirit of the original vi's temporary file: the text
  lives on the card, and the editor keeps a table of line offsets in RAM, room for which comes from moving
  editor support routines into the EEPROM. So the editor will hold a working file open for writing and
  random reads for a whole session, and write the file being edited (`:w`) at the same time.
- **File sizes.** The editor assembles to about 12 KB from 331 KB of commented source in 27 files, the largest
  30 KB; asm17 is 237 KB of source in 29 files, the largest 28 KB. So a 32 KB program is roughly 1 MB of source
  in 70 or so files, none much over 64 KB.

## Design: two rings, one for data and one for commits

### Layout

The card (or a partition of it, below) holds a superblock and two rings, each written round and round:

```
 +------------+---------------------------------+------------------------------------------------+
 | superblock | commit ring: 4,096 slots of 32  | data ring: 1 MB slots (about 7,500 on 8 GB)    |
 |            | sectors (64 MB)                 |                                                |
 +------------+---------------------------------+------------------------------------------------+
                commit slot: hdr | dir (16) | spare        data slot: hdr | data (2047 sectors)
```

- **A data slot holds one version of one file**, up to about 1 MB, far beyond the sizes above. Sector 0 is a
  small header written when the slot is taken (magic, volume ID, the name and the sequence number of the
  commit it followed: for `fsck` only); the data follows. A data slot is never updated after its file is
  committed: each save writes the new version into a fresh data slot, and the old one becomes garbage.
- **A commit slot holds one commit:** a header (magic `MFS1`, the volume ID, a 32-bit **sequence number**, one
  more than the commit before and never 0, the data ring's **allocation pointer**, what the commit did, and a
  checksum) and a complete copy of the directory as of that commit, in 16 sectors.

The **directory** is 256 entries of 32 bytes, kept sorted by name (so `opendir` just streams it):

| Bytes | Field |
|---|---|
| 0–23 | name: up to 23 characters, NUL-padded. Flat: there are no subdirectories, but `/` is allowed in names, so `editor/input.asm` works as a convention |
| 24–25 | data slot of the current version |
| 26–28 | length in bytes |
| 29 | flags: bit 1 read-only (the environment's `DIR_ENTRY_READONLY`) |
| 30–31 | how many times it has been saved (diagnostic) |

The **superblock** holds the magic `MFSB`, the format version, the volume ID, where each ring starts, its slot
size and count, and a checksum. It is written once, by `format`, and only read after that.

### Writing a file, and committing it

- **Opening for writing takes a data slot** from the data ring's allocation pointer, writing its header. Any
  number of files can be open for writing at once; each has its own data slot.
- **Closing commits** into the next commit slot, writing the 16 directory sectors (the old directory with the
  file's entry pointing at its new data slot), then **the header, last**. Writing the header is the commit.
  Before it, everything the file wrote is flushed to the card.
- **Deleting and renaming** are commits with no data slot.

If the power fails before a commit's header is written, the commit slot's header is still the one from the
ring's previous lap (or nothing, or a torn sector that fails its checksum), so the commit didn't happen and the
previous directory stands. The data slot it would have used is garbage. A save is all or nothing, and the
directory is never torn, because it is never overwritten.

Readers see the version that was committed when they opened the file. The new version appears at `close`. Two
writers of the same name: the last to close wins.

### Mounting: finding the newest commit

Commit slots are only ever written in order, so the sequence numbers around the commit ring rise to the newest
commit and then drop to the oldest: a sorted list, rotated. Unwritten or torn slots count as 0, and can only
sit at the drop, so the order holds. Mounting reads the superblock, then binary-searches the commit ring's
headers for the last slot whose sequence number is at least slot 0's: 12 header reads for 4,096 slots. (If
slot 0's header is invalid, the newest is the last slot if its header is valid, and otherwise the card is
empty.) That commit's directory is the directory, and its allocation pointer says where the data ring carries
on. No sector records "where the newest is", because such a sector would be the hot spot this design avoids.

Commits happen in the order files are closed, whatever order they were opened in, and the data slots are found
through the directory, never by searching. That is what lets any number of writers be open at once.

### Allocating data slots

The data ring's allocation pointer moves forward, round and round, and **skips any slot that is live** (the
directory points at it) **or open** (a reader or writer has it). Every other slot it passes is garbage and is
reused. Skipping is safe because the data ring is never searched, so the order of its slots doesn't matter. At
most 256 files are live and a handful open, among thousands of slots, so a free slot is always close.

A data slot taken but never committed (a crash, or a scratch file) is garbage, and is reused the next time
round.

### Why there are no hot spots

- Every sector of the commit ring is written **once per lap of the commit ring** (4,096 commits), and every
  sector of the data ring at most **once per lap of the data ring** (about 7,500 files written, on an 8 GB
  card). The only exception is the superblock, written once at format.
- At 200 saves a day the commit ring laps every 3 weeks: about 180 writes per sector in ten years, against
  thousands of erase cycles for even cheap flash. The data ring sees fewer. Both rings' sizes are format
  options; a larger commit ring laps more slowly.
- This doesn't rely on the card's own wear levelling, which on cheap cards is often limited to zones, and is
  exactly what FAT's constantly rewritten table and directory sectors wear out.
- Writes are sequential through the card, in large runs, the pattern SD cards handle best. The partition and
  both rings start on 4 MB boundaries (the usual allocation unit).

### On the card: a partition, and a PC tool

The filesystem lives in an MBR partition of its own type (`$DA`, "non-FS data"), so a PC doesn't offer to
format it and a card can keep a FAT partition beside it. A host tool, `tools/mfs/mfs.py`, works on a card
(a block device) or an image file: `format`, `ls`, `get`, `put` (including whole directory trees, so the
editor's and the assembler's sources can be put on a card), `rm`, `mv`, `fsck` and `wear` (writes per sector,
on an image). It is also the reference model the other implementations are tested against.

### Handles: streaming and random access

A handle is a file's data slot, length and position. Up to 16 can be open at once, each with about 8 bytes of
state. The bytes themselves go through the FPGA's **sector cache** (below), so a handle needs no buffer of
its own, and switching between handles (the assembler going in and out of includes, the editor between its
working file and a save) costs one command to set the pointer.
- **Reading** returns the next byte, with C set at the end, as the environment's `read` does now.
- **Writing (`openout`)** creates or truncates: a new data slot, written from the start. `close` commits; the
  length is how far it got.
- **Updating (`openrw`)** opens an existing file for reading and writing anywhere in it: a new data slot, into
  which the FPGA copies the file's data from card to card (about 0.1 s for 30 KB). `close` commits; the
  length is the old length or the furthest write. Appending is updating with a seek to the end.
- **Scratch (`opentmp`)** is a data slot with no name, for reading and writing anywhere, never committed: it is
  garbage once closed, or after a crash. This is the editor's working file.
- **Seeking** moves the position, anywhere up to the length (and up to the slot's size, for a writer).
- **Errors** set a code that `fs_error` returns; `open` and friends return 0 on failure, as now.

### The editor's working file

The filesystem gives the vi-style editor what it needs, with no special cases:
- `opentmp` for the working file. Writing it append-only, as ex/vi did (a changed line is written again at the
  end, and its line table entry moved to point there), means each of its sectors is written once, as it fills.
  Random reads by offset (`seek`, then `read`) fetch lines for the screen, mostly from the cache.
- The line table is Michael's own: 3 bytes a line (an offset in the working file), so 2,000 lines are 6 KB. If
  that is too much RAM, the spare part of the FPGA's buffer memory could hold it, behind two more device
  operations; decide with the editor's plan.
- `:w` writes the file through `openout` while the working file stays open, and `:e` reads through `open`.
- **Recovery, later:** `keep` could name a scratch file, committing its data slot as a file without copying,
  like `vi -r`'s preserved files.

### Where the work is done: FPGA block device with a cache, filesystem on Michael

The FPGA provides a **block device with a write-back sector cache**; Michael's ROM runs the **filesystem**. The
FPGA's part is mechanical, the kind of thing Verilog does well, and keeps the bulk data out of Michael's RAM.
The filesystem's rules (names, the directory, commits, allocation, mounting) are 6502 code, tested in the
emulator like the rest of the ROM. Michael keeps about 150 bytes of state: the newest commit's slot and
sequence number, the allocation pointer, and the handles.

**The cache** is 64 sectors (32 KB of block RAM). Michael addresses the card as a pointer, a sector and an
offset within it, and reads and writes bytes at the pointer, which advances across sector boundaries by
itself. A sector is read from the card when the pointer first reaches it, and written back only when it is
evicted or flushed. So:
- updates that go back and forth over a sector change it in the cache, not on the card, which keeps
  `openrw` and the working file flash-friendly;
- the directory needs no special handling: it is read through the cache like everything else, and a new
  commit's directory is the old one copied with an entry moved, inserted or removed;
- the order of a commit is kept with `FLUSH`: write the new directory, flush, write the header, flush. The
  header is only changed after the first flush, so it can't be evicted early.

**The storage device** is a long-form device, `$81` (as the protocol asks of new peripherals), with two
one-byte commands from `$4x` for the busy paths:

| Operation | Name | Arguments | Data | Effect |
|---|---|---|---|---|
| `$00` | `INIT` | — | — | Initialise the card (CMD0, CMD8, ACMD41, CMD58). SDHC and SDXC only (block addressed). Replies a status byte |
| `$01` | `INFO` | — | — | Replies the card's size in sectors (4 bytes) and its status |
| `$02` | `POINTER` | sector (4), offset (2) | — | Sets the pointer |
| `$03` | `COPY` | from sector (4), to sector (4), count (2) | — | Card to card, coherent with the cache: `openrw` |
| `$04` | `MOVE` | to sector (4), offset (2), length (2) | — | Moves `length` bytes from the pointer to the given place, overlap-safe, through the cache: inserting and removing directory entries |
| `$05` | `FILL` | length (2), byte | — | From the pointer, advancing it |
| `$06` | `FLUSH` | — | — | Writes every dirty sector back, in sector order. Replies a status byte when done |
| `$07` | `DISCARD` | from sector (4), count (2) | — | Drops those sectors from the cache unwritten: a closed scratch file's |

| Code | Name | Arguments | Data | Effect |
|---|---|---|---|---|
| `$40` | `ST_READ` | count | — | Queues `count` bytes from the pointer onto the reply queue, advancing it |
| `$41` | `ST_WRITE` | — | streams | Stores each data byte at the pointer, advancing it |

`BUSY` is set while the card is working; status bytes report no card, a timeout, a CRC error, a rejected
write or a sector out of range. `ID`'s bit 2 says the device is there. The debug port carries it, so a PC can
drive the card through the FPGA without Michael, as it does the display.

### The programs' interface

The existing vectors keep their meaning and gain a filesystem: `open`, `openout`, `read`, `write`, `close`
(which now returns C set if the commit failed) and `opendir` (the name `.`, or empty, lists everything;
entries come sorted, read-only flagged). New vectors, after `scr_delete_lines` (`$6C`), in both
`asm/17/environment.asm` and `michael_rom.inc`:

| Offset | Name | Call |
|---|---|---|
| `$6F` | `openrw` | Opens the file named at A;X for reading and writing. Returns a handle in A (0 on failure) |
| `$72` | `opentmp` | Opens a new scratch file for reading and writing. Returns a handle in A (0 on failure) |
| `$75` | `seek` | Moves handle Y to the 3-byte position at A;X. C set if out of range |
| `$78` | `tell` | Stores handle Y's position in the 3 bytes at A;X |
| `$7B` | `remove` | Removes the file named at A;X. C set on failure |
| `$7E` | `rename` | Renames: A;X points at the old name's address and then the new name's. C set on failure |
| `$81` | `fs_error` | Returns the last error code in A |

The nmos-default emulator gets the same calls on the host's files (`emulator/file_io.c` has the rest
already; `opentmp` is a host temporary file), so a program using them is tested there too. The filesystem
mounts at its first call, so a program that never touches it pays nothing, and the loader's start-up stays as
it is.

## Alternatives considered

- **One ring, a file's data and its commit in the same slot** (this plan's first draft). Half the writes per
  save, but commits must land in the order their slots were taken, so only one file can be written at a time;
  and live files must be copied forward as the ring comes round to them.
- **FAT32.** A PC reads it, but its allocation table and directory sectors are rewritten on every save (the
  hot spots), it needs cluster chains, long names and more code and RAM than Michael has to spare. `mfs.py`
  covers moving files to and from a PC instead.
- **A fixed slot per file, rewritten in place.** The simplest of all, but the files saved most are worn most,
  and a power failure mid-save loses the file.
- **LittleFS** is the real thing for raw flash (metadata pairs, copy-on-write), but it is written in C, needs
  RAM for caches, and solves problems (bad blocks, tiny flash) that an SD card with space to spare doesn't
  have.
- **The filesystem in the FPGA.** Then Michael would only send names and bytes, but directory logic in Verilog
  is hard to write and test, or would need a soft CPU. Splitting at the block device keeps each side simple.

## Phases (each test-first: red, green, refactor)

1. **The reference model, `tools/mfs/`.** The filesystem in Python, on an image file, with `mfs.py`'s commands.
   Tests:
   - format, mount, save, read, `openrw`, `opentmp`, seek, remove, rename, the directory's order, the limits
     (256 files, 16 handles, names, the largest file);
   - **several open at once:** a nest of readers with a writer (the assembler's pattern); two writers closing in
     the other order from the one they opened in; a scratch file written and read at random beside a save (the
     editor's pattern); scratch files gone after a remount;
   - **all-or-nothing:** a model card that loses power after the k-th sector written, for every k through
     saves, deletes and renames; each time the mount finds the state before the operation or after it, never
     anything else;
   - **no hot spots:** 100,000 saves of a realistic mix (a few files saved often, many rarely, a working file
     appended to) on small rings; the most-written sector of each ring is written at most one more time than
     that ring's laps;
   - mounting at every position of the commit ring, and allocation skipping live and open data slots.
2. **The new calls in the nmos-default emulator** (`openrw`, `opentmp`, `seek`, `tell`, `remove`, `rename`,
   `fs_error`), with tests. The stable builds of the assembler and editor stay byte-identical.
3. **The storage device in the emulator**, at the level of its commands, as `fpga_text.c` models text mode:
   `emulator/chips/fpga_storage.c`, backed by a card image (`--sd IMAGE`), with the cache, a count of writes
   per sector, and a power cut after N writes for the tests. Checked against a Python model of the device.
4. **The filesystem in 6502 code,** `firmware/lib/fs/`, in the Michael emulator. Differential tests: the same
   scripts of operations through the 6502 code and through `mfs.py`, compared by reading the resulting image
   with `mfs.py`; the power-cut tests again; a card formatted and filled by `mfs.py` read by Michael, and the
   other way round.
5. **ROM 6:** the filesystem behind the vectors, with the ROM's tests in the emulator. The editor's `:w` and
   `:e` on Michael then work with no editor change: `editor/tests/michael_tests.py` saves, reloads and lists
   in the emulator. The assembler, built for the emulator's Michael machine, assembles a program with nested
   includes from an image.
6. **The FPGA:** an SD SPI controller (400 kHz to start, then 12 MHz or more), the cache and the device's
   operations, simulated against a behavioural model of an SD card in SPI mode. Then on the board through the
   debug port: a card formatted and filled by `mfs.py` on the PC, read and written by the FPGA, and checked by
   `mfs.py` again.
7. **On the board:** the Pmod MicroSD on the Cmod, the bus design and ROM 6 in place, and the editor loading and
   saving on the card.

## Later

- **The editor's working file** (its own plan): the line table, moving support routines into the EEPROM, and
  the editor on `opentmp`. This plan gives it the calls it needs.
- **The assembler on Michael** (its own plan: its memory). Its includes need nothing more from this one.
- **Speed:** a `FIND` operation for names; a small read-ahead in Michael's RAM.
- **`stat`** (a file's length and flags by name), for an `ls` with sizes; **`keep`** (above).
- **Booting from the card:** the loader running a named file (an autoexec), as the Wendy 2 monitor does
  ([`prog8/WENDY2_DISK_BOOT_DESIGN.md`](../prog8/WENDY2_DISK_BOOT_DESIGN.md)).

## Open points

- The Pmod MicroSD on the Cmod's Pmod header: check its pins against the Cmod's and the bus design's, and that
  the header's 3.3 V supply can feed the card's write current.
- The ring sizes: 1 MB data slots are generous (256 KB would do); a 64 MB commit ring could be larger to lap
  more slowly. Both are format options.
- 16 handles: enough for the deepest include nest we expect, with the output and the editor's two? The
  assembler reports a clean error when `open` fails.
- 23-character names: long enough for `editor/render_scroll.asm`? 32-byte entries could become 48 for 39
  characters, with 24 directory sectors.
- Where Michael's filesystem state goes in RAM: about 150 bytes, which competes with the editor's buffers; the
  handles could live in the FPGA's spare buffer memory instead, with only the current handle's in RAM.
- The volume ID at format: random on the PC; on Michael, from the VIA's timer at a key press.
