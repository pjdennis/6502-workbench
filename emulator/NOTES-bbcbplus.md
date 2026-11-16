# The facts behind `--machine bbcbplus`

Every fact about the real BBC Model B+128, its MOS and the module carrier
that the emulator's bbcbplus machine relies on. Each is marked:

- **checked**: read in the source named, on 2026-11-14;
- **memory**: from memory, not checked against anything. Treat these as
  likely, not certain.

Sources read: MAME's `src/devices/bus/bbc/rom/pal.cpp` and
`src/mame/acorn/bbcbp.cpp` (BSD-3-Clause; MAME is an emulator, so "checked"
against it means "as MAME models it", not as measured on hardware);
BeebWiki (beebwiki.mdfs.net) pages API, Paged ROM, Service calls, OSBYTE,
OSBYTE &00, &8E and &8F, OSWORD, OSWORD &00 and &01, OSFILE, OSFIND,
OSGBPB, OSARGS, OSBGET, OSRDCH, OSCLI, Machine types, System error
messages, INF file format; and the annotated MOS 1.20 reassembly at
tobylobster.github.io/mos (chapters 11, 12 and 24). No B+ MOS 2.00
listing was read: where a fact was checked against MOS 1.20 it is assumed
to hold for MOS 2.00, which is itself a **memory** assumption.

## The machine

| Fact | | Source |
|---|---|---|
| The CPU is a 6512 (an NMOS 6502 with a two-phase clock input) at 2 MHz, from a 16 MHz crystal divided by 8 | checked | MAME bbcbp.cpp: `M6512(config, m_maincpu, 16_MHz_XTAL / 8)` |
| Slow I/O stretches the clock to 1 MHz | memory | not modelled |
| `$0000-$7FFF` RAM, `$8000-$BFFF` paged ROM/RAM, `$C000-$FFFF` MOS with I/O at `$FC00-$FEFF` | checked | MAME bbcbp.cpp address map |
| ROMSEL is written in `$FE30-$FE3F`, decoded on the low three address bits: offset 0 (`$FE30`, `$FE38`) is ROMSEL, offset 4 (`$FE34`, `$FE3C`) the shadow screen select; bits 0-3 of ROMSEL the slot, bit 7 the 12 KB paged RAM at `$8000-$AFFF` | checked | MAME bbcbp.cpp `romsel_w` |
| ROMSEL is write only | memory | MAME maps only a write handler there |
| The B+ has 20 KB of shadow screen RAM at `$3000-$7FFF` | checked | MAME bbcbp.cpp comment; not modelled |
| Code running in the top 4 KB of the 12 KB RAM sees the shadow (video) RAM | checked | BeebWiki Paged ROM ("also 'sees' and can manipulate video RAM"); not modelled |
| The B+128's extra 64 KB is sideways RAM in slots 0, 1, 12 and 13 | checked | MAME bbcbp.cpp (`bbcbp128`: RAM slots `0x00` and `0x0c`, 32 KB each; "SWRAM (B+ 128K only)" on pages 0, 1, 12, 13) |
| An empty slot reads as the open bus, the last value on the data bus | memory | |
| HIMEM is `$7C00` in mode 7, `$8000` with shadow RAM | memory | |
| PAGE (OSHWM) is `$1900` on a B+ with the DFS | memory | |

## The module carrier

| Fact | | Source |
|---|---|---|
| Computer Concepts carriers switch banks on reads of preprogrammed zones (a PAL), as a ROM socket has no write line | checked | MAME pal.cpp, top comment |
| `bbc_ccispell_device::read`: offset `$3FE0` selects bank 0; else, only while the bank is 0, `offset & $3FE0` of `$3FC0` .. `$3F00` selects banks 1 .. 7; the byte comes from the bank selected after the switch | checked | MAME pal.cpp (the code, quoted in the emulator's README) |
| That device is the 128K carrier SpellMaster used, 1987 | partly | MAME's comment says "switching zones for SpellMaster"; the year is **memory** |
| The real latch powers up undefined | memory | |
| `direct16` | — | this project's own design; no real hardware |
| A real NMOS 6502 reads the byte after a one-byte opcode, and an indexed read first reads the unfixed address | memory | the emulator's core makes neither read |

## Paged ROMs and service calls

| Fact | | Source |
|---|---|---|
| Header: `$8000` language entry, `$8003` service entry, `$8006` type (bit 7 service entry, bit 6 language entry, bits 0-3 CPU type), `$8007` offset of the copyright string, `$8008` version, `$8009` title | checked | BeebWiki Paged ROM |
| The copyright string is `$00 "(C)"`, at `$8000` + the offset, and the MOS needs it to accept the ROM | checked | BeebWiki Paged ROM |
| The type table is at `$02A1`+slot | memory | (OSBYTE 170 returning its address is **memory** too) |
| Service calls: slots 15 down to 0, each valid ROM selected (number written to `$F4` first, then ROMSEL) and called at `$8003` with A the call, X the slot, Y the argument; A=0 on return claims it; an unclaimed call must return with registers preserved; A and Y pass on to the next ROM | checked | BeebWiki Paged ROM, Service calls |
| Service call 4 (unrecognised command): `($F2),Y` is the command | checked | BeebWiki Service calls |
| Service call 6 (BRK): the error block is at `($FD)` | checked | BeebWiki Service calls |
| Service call 7 (unrecognised OSBYTE): A, X, Y in `$EF`, `$F0`, `$F1`; a claiming ROM returns X in `$F0` and Y in Y | checked | BeebWiki Service calls |
| Service call 8 (unrecognised OSWORD): A in `$EF`, the block at `$F0/$F1` | checked | BeebWiki Service calls |
| A language is entered at `$8000` with A=1 | checked | BeebWiki Paged ROM |
| OSBYTE 142 (X the slot): the language resets the stack and does not return; an unplugged slot has no effect; a ROM that is not a language is the error "This is not a language" | checked | BeebWiki OSBYTE &8E |
| OSBYTE 142 records the language at `$028C` | memory | (the MOS 1.20 reassembly names `languageROMNumber`; its address was not read) |
| OSBYTE 142 prints the language's title | memory, not done | the emulator prints nothing |
| OSBYTE 143: X the call, Y the argument; X=0 on exit if claimed, Y the result | checked | BeebWiki OSBYTE &8F |
| `*HELP` offers service call 9 to every ROM, with `($F2),Y` its argument; no ROM claims it, and the MOS also prints its own version line | memory | the emulator issues the call and prints nothing |
| OSBYTE 252 (`&FC`) reads and writes the current language ROM: X the old value, the new (old AND Y) EOR X, Y the next variable's; the variable is the one at `$028C` | memory | |
| OSBYTE 170 (`&AA`) with X=0, Y=`$FF` gives the ROM type table's address in X and Y | memory | |
| At reset the MOS scans every slot's header and enters the highest language ROM | partly | the scan: BeebWiki Paged ROM; "the highest": **memory** |
| At reset the MOS also issues service calls (1, 2 workspace and others) and drops duplicate ROMs | memory, not done | |

## The MOS entry points, vectors and zero page

| Fact | | Source |
|---|---|---|
| Entry points: `$FFB9` OSRDRM, `$FFBC` VDUCHR, `$FFBF` OSEVEN, `$FFC2` GSINIT, `$FFC5` GSREAD, `$FFC8` NVRDCH, `$FFCB` NVWRCH, `$FFCE` OSFIND, `$FFD1` OSGBPB, `$FFD4` OSBPUT, `$FFD7` OSBGET, `$FFDA` OSARGS, `$FFDD` OSFILE, `$FFE0` OSRDCH, `$FFE3` OSASCI, `$FFE7` OSNEWL, `$FFEE` OSWRCH, `$FFF1` OSWORD, `$FFF4` OSBYTE, `$FFF7` OSCLI; each vectored one a `JMP (vector)` | checked | MOS 1.20 reassembly ch. 24 |
| OSASCI is `CMP #$0D; BNE OSWRCH`, falling into OSNEWL, which is `LDA #$0A; JSR OSWRCH; LDA #$0D`, falling into OSWRCH | checked | MOS 1.20 reassembly ch. 24 |
| `$FFB6` is the default vector table's length and `$FFB7` its address | partly | BeebWiki API lists DEFVEC at `$FFB6`; the layout is **memory** |
| Vectors: `$0200` USERV, `$0202` BRKV, `$0204` IRQ1V, `$0206` IRQ2V, `$0208` CLIV, `$020A` BYTEV, `$020C` WORDV, `$020E` WRCHV, `$0210` RDCHV, `$0212` FILEV, `$0214` ARGSV, `$0216` BGETV, `$0218` BPUTV, `$021A` GBPBV, `$021C` FINDV, `$021E` FSCV, `$0220` EVNTV, `$0222` UPTV, `$0224` NETV, `$0226` VDUV, `$0228` KEYV, `$022A` INSV, `$022C` REMV, `$022E` CNPV, `$0230`-`$0234` IND1V-IND3V | checked | BeebWiki API |
| `$F4` holds the copy of ROMSEL | checked | BeebWiki Paged ROM |
| `$FD/$FE` point to the last error; `$FF` is the Escape flag (bit 7) | checked | BeebWiki API (FAULT `&FD`, ESCFLG `&FF`); bit 7: **memory** |
| `$EF/$F0/$F1` hold OSBYTE's and OSWORD's A, X, Y | checked | BeebWiki Service calls (for the calls passed to ROMs) |
| OSCLI stores the line's address at `$F2/$F3` | partly | the reassembly stores XY there under a name; the address: from service call 4's `($F2),Y` |
| `$F6/$F7` is OSRDRM's address; Y its ROM | memory | |
| `$A8-$AF` is workspace for * commands; `$90-$FF` otherwise the MOS's and filing systems' | memory | |
| `$0200-$03FF` and `$0800` up to PAGE are the MOS's and the filing systems' workspace; `$0400-$07FF` the language's | memory | |

## Errors and BRK

| Fact | | Source |
|---|---|---|
| An error is a BRK followed by its number and a zero-terminated message | memory | |
| IRQ entry: `STA $FC; PLA; PHA; AND #$10; BNE brk; JMP (IRQ1V)`; BRK: `TXA; PHA; TSX`, stacked PC - 1 to the fault address, current ROM saved, stack pointer saved, service call 6, the language ROM selected, `PLA; TAX; LDA $FC; CLI; JMP (BRKV)`; IRQ2's default ends `LDA $FC; RTI` | checked | MOS 1.20 reassembly ch. 11 (symbolic names) |
| The addresses of those saved values: `$024A` the ROM, `$F0` the stack pointer, `$FC` A | memory | (`$FD/$FE`: checked above) |
| Numbers: Bad command 254, Bad address 252, This is not a language 0, OS version 247, File not found 214, Channel 222, EOF 223, Bad name 204, Too many open files 192, Read only 193, Disc fault 199 | checked | BeebWiki System error messages, OSBYTE &00 (247) |
| The B+'s OSBYTE 0,0 error text is "OS 2.00" | memory | BeebWiki says only "host and OS type" |
| OSBYTE 0 with X not 0 returns X=2 on a B+ | checked | BeebWiki Machine types |
| "No disk (--disk)" and 255 "Not in this emulator's MOS" | — | the emulator's own |

## OSBYTE, OSWORD, OSCLI, character I/O

| Fact | | Source |
|---|---|---|
| An unrecognised OSBYTE goes to the ROMs; unclaimed it returns X=`$FF` | checked | BeebWiki OSBYTE |
| ... and with V set | memory | |
| `*FX` with an unknown number is Bad command | checked | BeebWiki OSBYTE; `*FX` is not implemented |
| 126 acknowledges Escape (X=`$FF` if there was one), 127 is EOF#, 130 the high order address (`$FFFF` for the I/O processor), 131 PAGE, 132 HIMEM | partly | the purposes: BeebWiki OSBYTE; the return values: **memory** |
| OSWORD 0: block +0/+1 buffer, +2 the most characters (not counting the CR), +3/+4 the range stored; exit Y the length without CR, C set if ended by Escape; all characters are echoed; DEL deletes | checked | BeebWiki OSWORD &00 (the emulator does not echo) |
| OSWORD 1/2: a 5-byte clock | checked | BeebWiki OSWORD &01 |
| ... in centiseconds, low byte first | memory | |
| OSRDCH: A the byte; C set on an error, Escape with A=`$1B` | checked | BeebWiki OSRDCH |
| OSCLI: skips spaces and `*`, `|` is a comment, CR ends it; MOS commands (abbreviable with `.`), then service call 4 with Y the offset, then the filing system (FSCV A=3); `*RUN` goes to the filing system (A=4), `*/` too (A=2) | checked | MOS 1.20 reassembly ch. 12, BeebWiki OSCLI |
| The filing system raises Bad command for an unknown command that is no file | memory | |

## The filing system (as the DFS)

| Fact | | Source |
|---|---|---|
| OSFIND: `$40` input (0 if missing), `$80` output (truncates), `$C0` update (0 if missing); A=0 closes Y, Y=0 all; returns 0 if not opened; the DFS allows five open files | checked | BeebWiki OSFIND (the emulator allows 15) |
| DFS handles are `$11`-`$15` | memory | |
| OSBGET: C set and A=`$FE` at EOF; the next read is an error | checked | BeebWiki OSBGET |
| OSBPUT to a file open for input is an error (Read only) | memory | |
| OSARGS: Y=0 A=0 the filing system (DFS 4), A=1 the command line tail, A=`$FF` flush; Y a handle: 0 read PTR, 1 write PTR, 2 read EXT, `$FF` flush | checked | BeebWiki OSARGS |
| OSARGS 1 with a handle returns A=0 if the file was extended, else `$FF` | checked | BeebWiki OSARGS; not done (A is left) |
| OSGBPB: block +0 handle, +1 address, +5 count, +9 PTR; 1/3 use the PTR given, 2/4 the current; on exit address and PTR moved on, count what is left, C set if not 0, A=0 if supported | checked | BeebWiki OSGBPB |
| OSFILE: block +0 name, +2 load, +6 exec, +10 start/length, +14 end/attributes; `$FF` loads at +2 if exec's low byte is 0; 0 saves; 1-4 write information; 5 reads it; 6 deletes (A=0 if missing); A on exit 0 none, 1 file, 2 directory; only load raises an error for a missing file | checked | BeebWiki OSFILE |
| DFS names are up to seven characters with a directory (`$.NAME`) | checked | BeebWiki Acorn DFS disc format (below); the emulator uses names as given unless `--bbc-fs dfs` |
| `.inf` files: the data file's name plus `.inf`; `NAME LOAD EXEC`, hex of 1-8 digits, separated by spaces; an optional length after (bbcim) | checked | BeebWiki INF file format |

## The DFS's names and limits (`--bbc-fs dfs`)

Read on 2026-11-16: BeebWiki pages Acorn DFS disc format, OSFIND and System error messages;
Wikipedia, "Disc Filing System"; the HDFS manual (knackered.org/~angus/beeb/hdfs.html: HDFS for the BBC, a
hierarchical DFS that says its error numbers are those of Acorn's DNFS 1.20 "where possible").
Acorn's own Disc System User Guide could not be read: its host is not reachable from this
session. MMFS's source (a DFS-compatible filing system) could not be read: access to its
repository was refused. So the error numbers below are checked only against a third party's
manual and a table that does not say which filing system each message is from.

| Fact | | Source |
|---|---|---|
| A file name is one to seven characters, `$20`-`$7E` but `.` `:` `"` `#` `*` and space; the directory is one such character; name and directory together are unique on the side | checked | BeebWiki Acorn DFS disc format |
| The catalogue holds 31 files a side, whatever their directories | checked | BeebWiki Acorn DFS disc format; Wikipedia |
| A side has ten 256-byte sectors a track, 40 or 80 tracks; at most 800 sectors (204,800 bytes) | checked | BeebWiki Acorn DFS disc format |
| Case is kept but not significant | checked | Wikipedia ("case-preserving but not case-sensitive"); that the directory's case does not matter either is **memory** |
| Four drives, 0 to 3; the two sides of a double-sided drive are two drives (0 and 2 for the first drive, 1 and 3 for the second) | partly | Wikipedia (four volumes; sides as drives); which number is which side: **memory** |
| `:D.X.NAME`: the drive, then the directory, before the name | memory | |
| Five files open at once | checked | BeebWiki OSFIND |
| A new file opened for output is given 16 KB (`&4000`) of the disc; a file written over keeps its old space | checked | BeebWiki OSFIND |
| A file can be open for input several times if it is not open for output, and for output only if it is not open at all | checked | BeebWiki OSFIND; **not enforced** by the emulator |
| A file's data is one run of sectors; a file that grows to the start of the next is the error `Can't extend` | checked | Wikipedia; **not emulated** |
| Bad name 204 (`&CC`), Too many open 192 (`&C0`), Cat full 190 (`&BE`), Bad drive 205 (`&CD`), Can't extend 191 (`&BF`), Open 194 (`&C2`) | partly | the HDFS manual gives these messages with these numbers; BeebWiki System error messages gives the same numbers for these texts among others, without saying whose |
| A drive number out of range is `Bad drive` | partly | the HDFS manual; a forum post summarised in a search (not read: the forum refused the request) says Acorn's DFS gives `Bad name` there |
| Whether a new file goes into the first gap between files that holds 16 KB, or after the last file | not checked | (matters for `Can't extend`: bbc.md, "File names on the BBC") |

What the emulator does with them, and what it adds of its own: `emulator/README.md`, "bbcbplus",
`--bbc-fs dfs`. Its own: `/` is refused as `Bad name` (a real DFS takes it; the host directory
cannot hold it), and drive N is the subdirectory `:N` of `--disk`.
