# Plan: a filesystem on an SD card for Michael

Goal: a very simple filesystem on an SD card, so Michael can keep its sources, binaries and tools on the
board, and the editor and, later, the assembler can work from it without a PC. It provides:
- a directory listing;
- reading and writing whole files;
- streaming to and from files, byte by byte, as the editor and the assembler already do through `open`,
  `openout`, `read`, `write` and `close`;
- random access within files (seek, and update in place).

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
- **The programs' file calls.** The editor writes with `openout`/`write`/`close` (`editor/command.asm`) and the
  assembler reads its sources and writes one output (`asm/17/asm.asm`), one writer at a time. `opendir`
  streams entries as a metadata byte and a NUL-terminated name, sorted. Michael's ROM answers all of these
  with "none" today.
- **File sizes.** The editor assembles to about 12 KB from 331 KB of commented source in 27 files, the largest
  30 KB; asm17 is 237 KB of source in 29 files, the largest 28 KB. So a 32 KB program is roughly 1 MB of source
  in 70 or so files, none much over 64 KB.

## Design: a copy-on-write ring of slots

### Layout

The card (or a partition of it, below) is cut into a superblock and a ring of equal **slots**, 1 MB each by
default (2048 sectors; the size is chosen at format time). An 8 GB card has about 7,600 slots.

```
 sector 0          slot 0                slot 1                      slot N-1
 +------------+  +--------------------+--------------------+ ... +--------------------+
 | superblock |  | hdr | dir | data   | hdr | dir | data   |     | hdr | dir | data   |
 +------------+  +--------------------+--------------------+ ... +--------------------+
                    1     16    2031 sectors
```

Every slot is one **commit**, and holds:
- **sector 0, the header:** magic `MFS1`, the volume ID, a 32-bit **sequence number** (one more than the
  commit before, never 0), what the commit did (save, relocate, delete, rename), the name and length of the
  file it wrote (for recovery only), and a checksum of the header;
- **sectors 1–16, the directory:** a complete copy of the directory as of this commit;
- **sectors 17 onwards, the data** of the one file this commit wrote, if any. So a file can be up to about
  1 MB less 8.5 KB, far beyond the sizes above.

A file is one slot. Each save writes the whole new version into a fresh slot; the slot of the old version
becomes garbage. Nothing is ever updated in place.

The **directory** is 256 entries of 32 bytes, kept sorted by name (so `opendir` just streams it):

| Bytes | Field |
|---|---|
| 0–23 | name: up to 23 characters, NUL-padded. Flat: there are no subdirectories, but `/` is allowed in names, so `editor/input.asm` works as a convention |
| 24–25 | slot of the current version |
| 26–28 | length in bytes |
| 29 | flags: bit 1 read-only (the environment's `DIR_ENTRY_READONLY`) |
| 30–31 | how many times it has been saved (diagnostic) |

The **superblock** holds the magic `MFSB`, the format version, the volume ID, the slot size and count, the
first slot's sector and the checksum. It is written once, by `format`, and only read after that.

### Committing

The ring is written strictly in order: slot after slot, round and round. A commit (closing a file written
to, a delete or a rename) goes into the slot after the newest, writing:
1. the data sectors (while the file is being written: see *Handles*);
2. the 16 directory sectors (the old directory with the one entry changed);
3. **the header, last.** Writing it is the commit.

If the power fails before step 3 finishes, the slot's header is still the one from the ring's previous lap (or
nothing, or a torn sector that fails its checksum), so the commit didn't happen and the previous directory
stands. A save is all or nothing, and the directory is never torn because it is never overwritten.

Readers see the version that was committed when they opened the file. The new version appears at `close`.

### Mounting: finding the newest commit

Because the ring is written in order, the sequence numbers around it rise to the newest commit and then drop
to the oldest: a sorted list, rotated. Unwritten or torn slots count as 0, and can only sit at the drop, so the
order holds. Mounting reads the superblock, then binary-searches the headers for the newest commit: the last
slot whose sequence number is at least slot 0's. That is about 13 header reads for 7,600 slots. (If slot 0's
header is invalid, the newest is slot N−1 if its header is valid, and otherwise the card is empty.) Then it
loads the newest slot's 16 directory sectors. No sector records "where the newest is", because such a
sector would be the hot spot this design avoids.

### Keeping live files ahead of the ring: relocation

The ring would eventually come round to a slot that still holds a live file (one not saved since). So the
filesystem keeps an invariant: **the two slots after the newest commit hold no live file.** After each commit
it checks the slot two ahead of the newest. If a file lives there, it relocates it: a commit into the next
slot (free by the invariant) whose data is a copy of that file's, made by the FPGA from card to card, and
whose directory points the file at its new slot. That frees the slot it came from, and the check moves on.
It always ends, since at most 256 files are live among thousands of slots, and it costs at most 256
relocations a lap (about 3% of the writes on an 8 GB card).

### Why there are no hot spots

- Every sector is written **at most once per lap of the ring**, data, directory and header alike. The only
  exception is the superblock, written once at format.
- A lap is one commit per slot: about 7,600 saves on an 8 GB card. At 200 saves a day that is a lap every 5
  weeks, about 100 writes per sector in ten years, against thousands of erase cycles for even cheap flash.
- This doesn't rely on the card's own wear levelling, which on cheap cards is often limited to zones, and is
  exactly what FAT's constantly rewritten table and directory sectors wear out.
- Writes are sequential through the card, in large runs, the pattern SD cards handle best. The partition
  starts on a 4 MB boundary (the usual allocation unit).

### On the card: a partition, and a PC tool

The filesystem lives in an MBR partition of its own type (`$DA`, "non-FS data"), so a PC doesn't offer to
format it and a card can keep a FAT partition beside it. A host tool, `tools/mfs/mfs.py`, works on a card
(a block device) or an image file: `format`, `ls`, `get`, `put` (including whole directory trees, so the
editor's and the assembler's sources can be put on a card), `rm`, `mv`, `fsck` and `wear` (writes per sector,
on an image). It is also the reference model the other implementations are tested against.

### Handles: streaming and random access

A handle is a file's slot, length and position, and a **sector window**: one 512-byte buffer in the FPGA
holding the sector at the position.
- **Reading** loads each sector into the window as the position reaches it; `read` returns the next byte, with
  C set at the end, as the environment's `read` does now.
- **Writing (`openout`)** creates or truncates: it takes the next slot, and each sector is stored as the
  position leaves it. `close` stores the last one and commits; the length is how far it got.
- **Updating (`openrw`)** opens an existing file for reading and writing anywhere in it: it takes the next
  slot and has the FPGA copy the file's data sectors into it (about 0.1 s for 30 KB), then reads and writes go
  through the window, a sector stored only when it is dirty and the position leaves it. `close` commits, and
  the length is the old length or the furthest write. Appending is updating with a seek to the end.
- **Seeking** moves the position; the window follows on the next read or write.
- **One writer at a time** (`openout` or `openrw`); a second fails. That is all the editor and the assembler
  need, and it keeps the ring in commit order (see *Later* for more). Any number of readers (up to 8 handles),
  including of the file being written, who see its old version.
- **Errors** set a code that `fs_error` returns; `open` and friends return 0 on failure, as now.

Within one open session a sector of the uncommitted slot can be stored more than once, when updates seek back
and forth over it. That is bounded by the session and spread by the card's own levelling; the window means a
sector is only stored when the position leaves it dirty.

### Where the work is done: FPGA block device, filesystem on Michael

The FPGA provides a **block device with buffer memory**; Michael's ROM runs the **filesystem**. The FPGA's part
is mechanical, the kind of thing Verilog does well, and keeps the bulk data out of Michael's RAM. The
filesystem's rules (names, the directory, commits, relocation, mounting) are 6502 code, tested in the
emulator like the rest of the ROM. Michael keeps only a few dozen bytes of state: the newest slot and sequence
number, the writer's handle and each handle's slot, length and position.

**The storage device** is a long-form device, `$81` (as the protocol asks of new peripherals), with two
one-byte commands from `$4x` for the busy paths. Its **buffer memory** is 16 KB of block RAM: sectors 0–15
for the directory, 16–23 for the handles' windows, 24 for a header, the rest spare.

| Operation | Name | Arguments | Data | Effect |
|---|---|---|---|---|
| `$00` | `INIT` | — | — | Initialise the card (CMD0, CMD8, ACMD41, CMD58). SDHC and SDXC only (block addressed). Replies a status byte |
| `$01` | `INFO` | — | — | Replies the card's size in sectors (4 bytes) and its status |
| `$02` | `LOAD` | buffer sector, card sector (4), count | — | Reads sectors from the card into buffer memory. Replies a status byte when done |
| `$03` | `STORE` | buffer sector, card sector (4), count | — | Writes sectors from buffer memory to the card. Replies a status byte when done |
| `$04` | `COPY` | from sector (4), to sector (4), count (2) | — | Card to card, through a buffer of its own: relocation and `openrw` |
| `$05` | `POINTER` | address (2) | — | Sets the byte pointer into buffer memory |
| `$06` | `MOVE` | from (2), to (2), length (2) | — | Within buffer memory, overlap-safe: inserting and removing directory entries |
| `$07` | `FILL` | length (2), byte | — | From the pointer: a fresh sector's zeros |

| Code | Name | Arguments | Data | Effect |
|---|---|---|---|---|
| `$40` | `ST_READ` | count | — | Queues `count` bytes from the pointer onto the reply queue, advancing it |
| `$41` | `ST_WRITE` | — | streams | Stores each data byte at the pointer, advancing it |

`BUSY` is set while a card operation runs; status bytes report no card, a timeout, a CRC error, a rejected
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
| `$72` | `seek` | Moves handle Y to the 3-byte position at A;X. C set if past the end |
| `$75` | `tell` | Stores handle Y's position in the 3 bytes at A;X |
| `$78` | `remove` | Removes the file named at A;X. C set on failure |
| `$7B` | `rename` | Renames: A;X points at the old name's address and then the new name's. C set on failure |
| `$7E` | `fs_error` | Returns the last error code in A |

The nmos-default emulator gets the same calls on the host's files (`emulator/file_io.c` has the rest
already), so a program using them is tested there too. The filesystem mounts at its first call, so a
program that never touches it pays nothing, and the loader's start-up stays as it is.

## Alternatives considered

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
   - format, mount, save, read, `openrw`, seek, remove, rename, the directory's order, the limits (256 files,
     names, the largest file);
   - **all-or-nothing:** a model card that loses power after the k-th sector written, for every k through
     saves, deletes and relocations; each time the mount finds the state before the operation or after it,
     never anything else;
   - **no hot spots:** 100,000 saves of a realistic mix (a few files saved often, many rarely) on a small ring;
     the most-written sector is written at most one more time than the laps completed;
   - relocation, with the ring nearly full of live files, and mounting at every position of the ring.
2. **The new calls in the nmos-default emulator** (`openrw`, `seek`, `tell`, `remove`, `rename`, `fs_error`),
   with tests. The stable builds of the assembler and editor stay byte-identical.
3. **The storage device in the emulator**, at the level of its commands, as `fpga_text.c` models text mode:
   `emulator/chips/fpga_storage.c`, backed by a card image (`--sd IMAGE`), with a count of writes per sector
   and a power cut after N writes for the tests. Checked against the Python model of the device.
4. **The filesystem in 6502 code,** `firmware/lib/fs/`, in the Michael emulator. Differential tests: the same
   scripts of operations through the 6502 code and through `mfs.py`, compared by reading the resulting image
   with `mfs.py`; the power-cut tests again; a card formatted and filled by `mfs.py` read by Michael, and the
   other way round.
5. **ROM 6:** the filesystem behind the vectors, with the ROM's tests in the emulator. The editor's `:w` and
   `:e` on Michael then work with no editor change: `editor/tests/michael_tests.py` saves, reloads and lists
   in the emulator.
6. **The FPGA:** an SD SPI controller (400 kHz to start, then 12 MHz or more), the buffer memory and the
   device's operations, simulated against a behavioural model of an SD card in SPI mode. Then on the board
   through the debug port: a card formatted and filled by `mfs.py` on the PC, read and written by the FPGA, and
   checked by `mfs.py` again.
7. **On the board:** the Pmod MicroSD on the Cmod, the bus design and ROM 6 in place, and the editor loading and
   saving on the card.

## Later

- **The editor and the assembler self-contained.** This plan gives them a place to keep their files; it
  doesn't make them fit. The editor's text buffer on Michael is about 2.5 KB, so editing 30 KB sources needs
  the editor to page its text through a file, which `openrw` and `seek` make possible. Running the assembler
  on Michael needs its own plan (its memory, and its includes, which this filesystem serves as they are).
- **More than one writer**, if needed: a slot's header written when it is taken (its place in the ring) and a
  commit record in a sector of its own (the order of commits), with the mount looking back over the last few
  slots for the newest commit.
- **Speed:** the FPGA advancing a handle's window itself, so `read` is one bus transfer; a `FIND` operation
  for names; a small read-ahead in Michael's RAM.
- **`stat`** (a file's length and flags by name), for an `ls` with sizes.
- **Booting from the card:** the loader running a named file (an autoexec), as the Wendy 2 monitor does
  ([`prog8/WENDY2_DISK_BOOT_DESIGN.md`](../prog8/WENDY2_DISK_BOOT_DESIGN.md)).

## Open points

- The Pmod MicroSD on the Cmod's Pmod header: check its pins against the Cmod's and the bus design's, and that
  the header's 3.3 V supply can feed the card's write current.
- The slot size: 1 MB is generous; 256 KB would make laps shorter with no other effect. Kept a format option.
- 23-character names: long enough for `normal_edit.asm` and `editor/render_scroll.asm`? 32-byte entries
  could become 48 for 39 characters, with 24 directory sectors.
- Where Michael's filesystem state goes in RAM: about 40 bytes, beside the services' RAM at `$3F00`–`$3F80`,
  which the editor's buffers start above.
- The volume ID at format: random on the PC; on Michael, from the VIA's timer at a key press.
