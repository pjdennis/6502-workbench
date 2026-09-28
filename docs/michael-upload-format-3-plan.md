# Plan: Michael upload format 3

Follows `docs/michael-rom-plan.md` (format 2, done). Format 3 replaces format 2 on Michael. The other boards keep format 1.

Goals:
- the start address comes from the program's source (a `start` label), sent as S-records;
- all the metadata comes first, in a small table, instead of a header before each block, which removes the loader's stack bookkeeping;
- blocks may move down as well as up, so the only layout rule left is that the stream fits;
- uploads to zero page;
- a single block can still fill `$0200-$3EFF`.

## Format

The loader stores the whole stream in order from `$01F3`. All fields are little-endian.

```
$01F3  version (1) = 3
$01F4  start address (2)       $FFFF = don't run
$01F6  count (1)               entries, 1 to the board's maximum (Michael: 32)
$01F7  header checksum (2)     BSD sum of the header's bytes in order, skipping these two
$01F9  data checksum (2)       BSD sum of all the data bytes in order
$01FB  entries: count x (address (2), length (2), flags (1))
         flags bit 0 = zero-fill: no data bytes in the stream; the loader clears length bytes
         other bits 0 (reserved)
then   the data of each entry that isn't zero-fill, in entry order
```

- With one entry the header ends at `$01FF`, so its data lands at `$0200` and can fill `$0200-$3EFF` with no move.
- Each further entry adds 5 bytes above `$0200` (the spill), so the data lands 5 x (count - 1) bytes higher and is moved down afterwards.
- The length is a full 16 bits, and zero-fill is a flag rather than the length's top bit. The format then suits machines with more than 32 KB of contiguous RAM without splitting blocks. An entry must still end by `$10000`.

**Rules**, which the sender enforces and the loader checks:
- entries ascend by address and don't overlap;
- each entry lies within zero page (`$0000-$00FF`) or within `$0200-$3EFF`, never page 1;
- the stream ends by `$3F00`: `$0200` + 5 x (count - 1) + the data bytes <= `$3F00`;
- no more entries than the board's maximum (Michael: 32).

Where the data sits in the stream no longer matters: blocks may move down or up.

**Writing 0 to a place the program didn't specify is harmless**, so the sender merges freely. It may do so anywhere except page 1 and `$3F00` and above.

## Sender (`tools/upload/upload_frame.py`, `transfer.py`, `compile_and_upload.sh`)

- **S-records:** read vasm's `-Fsrec -s19 -exec` output.
  - S1/S2/S3 records are data; the S7/S8/S9 record gives the start address, with 0 meaning none (then the lowest address is used).
  - S0 and S5 records are ignored.
  - Intel HEX support goes.
- **Packing**, with the board's maximum entries as a parameter (Michael: 32):
  - adjacent S-record data records join into one segment;
  - segments at most 5 bytes apart merge, with explicit zeros in the gap (never longer than a separate entry);
  - larger gaps merge, smallest first, until the count is within the maximum;
  - all zero-page segments merge into one entry;
  - runs of zeros of 64 bytes or more become zero-fill entries while entries remain;
  - errors for page 1, `$3F00` and above, overlaps, and a stream that doesn't fit. Merging always brings the count within the maximum, since in the worst case there is one entry for zero page and one for the rest.
- **Command lines:**
  - `transfer.py --format=3` replaces `--format=2`. An S-record file (`.s19`) gives its own addresses and start; a binary loads at `--load-address` (default `2000`) and runs at `--start` (default: its lowest address).
  - `compile_and_upload.sh --srec` replaces `--hex`: it assembles with `-Fsrec -s19 -exec` to `a.s19`. `compile_and_upload_michael.sh` passes `--format=3 --srec`.
  - `.gitignore`: `a.s19` in place of `a.hex`.
  - `upload_frame.py`'s own command line, `michael_image.write_upload` and `editor-michael-upload.sh` switch to format 3.
- Format 2 and Intel HEX go from the tools (they stay in the history).

## Programs

- Each program sent with `compile_and_upload_michael.sh` gets a `start` label at its entry, usually right after `.org PROGRAM_LOAD_ADDRESS` (or `BF_LOAD_ADDRESS`).
- The test programs in `tools/tests/michael/` get one too.
- A missing `start` is an assembly error (`-exec` needs the symbol), which is what we want.
- The binaries don't change; the firmware manifest checks this.

## Loader (`firmware/lib/serial/upload_v3.inc`, replacing `upload_v2.inc`)

**Page 1:**

| Address | Contents | Bytes |
|---|---|---|
| `$0100-$019F` | entry table, as five 32-byte arrays (address low and high, length low and high, flags), indexed by entry number | 160 |
| `$01A0-$01F2` | stack, starting at `$01F2`; today's loader uses 21 bytes at most | 83 |
| `$01F3-$01FF` | the fixed fields and entry 1, as received; never a destination | 13 |

**The `$3F00` page while loading:**

| Address | Contents | Bytes |
|---|---|---|
| `$3F00-$3F49` | the receive handler, copied from ROM | 74 |
| from `$3F4A` | the zero-page stash: values for the loader's own zero page (today `$00-$24`) and for `$FC` (`ROM_FLAGS`), zeroed at the start | 38 |

This page is free while loading: the ROM's services haven't started, and uploads can't reach above `$3EFF`. It's also free when the stash is copied into zero page, which comes after `services_reset` (`ROM_STARTED`, `$3F03`, is under the handler, not the stash).

**Compile-time checks** (`fail`, in `michael_rom.s` and `upload_v3.inc`):
- The loader's zero page is one block, from `UPLOAD_ZP_START` to `UPLOAD_ZP_END`. Each variable is allocated from the one before, and the last must end by `UPLOAD_ZP_END`.
- The stash starts at `INTERRUPT_ROUTINE + (interrupt_end - interrupt)`. It holds `UPLOAD_ZP_END - UPLOAD_ZP_START` bytes plus one for `DISPLAY_INTERRUPTS_FLAG`, and must end by `$4000`.
- `DISPLAY_INTERRUPTS_FLAG` must lie outside the loader's block, and `DISPLAY_STRING_PARAM` inside it.
- The entry table (`32 x 5` bytes from `$0100`) must end below the stack's lowest allowed point. The stream's start is worked out from the header's size, and the table must end at least 64 bytes below it.

**While receiving:** the checking task and the display task take turns, as now, with the display paced by timer 1.
- Once the fixed fields have arrived, check the version and the count.
- Once the whole header has arrived, check its checksum, copy the entries into the table, and check them against the rules. The entries in the spill are copied out before anything could overwrite them.
- Sum the data as it arrives. At its end, compare the sum with the data checksum.
- The display shows "Ready" until the first byte, then "Received $count". The top row shows "Block NN $addr", working out the current entry from the byte count, or "$----" while the header arrives.

**After receiving** (nothing is placed before this):
1. **Stop receiving.**
2. **Zero page:** the zero-page entry's bytes go straight to zero page, except those for the loader's own zero page and `$FC`, which go into the stash. A zero-fill zero-page entry is handled the same way.
3. **Blocks moving down:** lowest address first, each copied from the bottom up.
4. **Blocks moving up:** highest address first, each copied from the top down.
5. **Zero-fill** the other zero-fill entries.

   Steps 3 and 4 are safe because destinations ascend without overlapping. A block moving down stays clear of the data of every later block, and a block moving up stays clear of the data of every earlier block. Blocks moving the same way are placed in the order that keeps them clear of each other.
6. **With a start address:**
   - clear the LCD, then `services_reset` (clears `ROM_STARTED` and `$FC`);
   - copy the stash into the loader's zero page and `$FC` with an absolute,X loop that uses no zero page, so an uploaded `$FC` wins and unspecified bytes are 0;
   - `ldx #$ff`, `txs`, then `jmp ($01F4)`, the start address in page 1, since zero page now holds the program's values.

   With no start address (`$FFFF`): "Loaded." shows first, since the display routines use the loader's zero page. Then the stash is copied in the same way and the CPU stops.

**Errors** stay on the LCD with the LED lit until reset: "Bad version", "Bad header" (the checksum or the count), "Bad block NN" (an entry breaking the rules), "Bad checksum" (the data).

## Phases (each test-first, in the emulator before the board)

1. **Sender:**
   - the S-record reader, the packer and the format 3 builder, with unit tests: merging, zero page, zero-fill runs, the entry limit, every error, and the exact bytes of a single-entry upload filling `$0200-$3EFF`;
   - `transfer.py`, `compile_and_upload*.sh` and their tests.
2. **Programs:** `start` labels; the manifest shows the binaries unchanged.
3. **Loader and ROM:** `upload_v3.inc`, with the existing loader tests ported, plus new ones:
   - one entry filling `$0200-$3EFF`;
   - data landing in the spill area (moved down over the copied entries);
   - blocks moving down and blocks moving up in one upload;
   - alternating single bytes (merged by the sender);
   - zero page, including `$00-$24`, and an uploaded `$FC` winning over the ROM's 0;
   - 32 entries;
   - a corrupted header, a bad entry, bad data;
   - the start address taken from `start` in the source;
   - the loader's lowest stack point staying above the table.
4. **Editor and ROM image:** `michael_tests.py` on format 3, the ROM image rebuilt, the manifest, and the docs (`hardware/michael/README.md`, `tools/README.md`, `upload_frame.py`'s docstring).
5. **Hand over** the new image for programming. Uploads in format 2 stop working once it is on the board.

## Later, maybe

- **A zero-fill bitmap:** after the header checks out, fold the flags into a bitmap (4 bytes for 32 entries), freeing about 28 bytes of page 1 for more entries. It's not on the wire, so it can come later without changing the format.
