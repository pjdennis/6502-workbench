# Differences from vim kept for now

The editor follows vim (8.2, default options) where it can. The
differences below were kept on purpose: each costs code, and so text
buffer, or reworks a part of the editor that works well as it is. Each
section says what vim does, what the editor does, and how the editor
could do what vim does: the data, the routines that change, memory, code
bytes, CPU and repaint, risks, and the tests to write first. Sections 4
and 6 have since been done, and so have the first two subsets of section
5; sections 1, 2 and 3, the rest of 5, 6's long lines and 7 are kept for
now.

Byte counts marked *measured* come from sandbox prototypes on the tree at
9d5cfd0 (console build 12,468 bytes, terminal build 12,541), with the
suite run; the others are estimates from the routines they would change.
`TEXT_BUF` starts at the page after the code, so code growth costs text
buffer a page at a time. When this file was added (the vim-compatibility
pass, part B) the console build was 12,720 bytes and the terminal build
12,793, 7 bytes below the page boundary at $3600 where its `TEXT_BUF`
starts, so every item left here costs the terminal build 256 bytes of
text buffer unless something else shrinks. Section 5's first subsets
(part C) moved it to $3700: the console build is now 12,941 bytes and
the terminal build 13,014, 42 bytes below $3700. Section 6 moved the
terminal build's to $3800 (the console build 12,992 bytes, the terminal
build 13,065). Section 7 was measured after the vim leftovers batch A
(the console build 13,083 bytes at $3800, the terminal build 13,159);
that batch ended with the console build at 13,056 bytes ($3700, none
spare) and the terminal build at 13,132 ($3800).

| # | Difference | Code bytes | Tests that change | State |
|---|---|---|---|---|
| 1 | `:w {file}`, E32, E13 and `:w!` | +136, and +74 for E13 and `!` (measured) | none | kept for now |
| 2 | J keeps the joined line's leading blanks | about +200, 150 to 250 (estimate) | one render test found | kept for now |
| 3 | No search wrap messages, no E486 | +108 (measured), about 90 with shared text | none | kept for now |
| 4 | Messages swallowed the next key | -5 (done) | 9 | done |
| 5 | Insert-mode typing is not undoable | +218 for subsets 1 and 2 with the redo (done); about +50 to 70 and +40 to 60 more for BS and DEL past the edges and the change commands (estimate) | 2 (done); 4 of part C, and 2 with the change commands | subsets 1 and 2 done |
| 6 | Ctrl-F and Ctrl-B move a page of `TEXT_ROWS` lines | +118 (done); about +50 to 70 more for vim's overlap over long lines (estimate) | 19 pagination, Ctrl-D/U and first non-blank tests' expected views, 4 frame sizes | done, but for long lines |
| 7 | Counts on i, a, A, o and O are ignored | +209 (measured) | none | kept for now |

Item 3 uses the message routine item 4 left (a message held until the
next key, which then runs), `show_message_ax`.

## 1. `:w {file}`, E32 and E13 (kept for now)

### What vim does

- In a buffer with no name (vim started without a file), `:w` and `:wq`
  say "E32: No file name" and do nothing; `:wq` does not quit.
- `:w {file}` and `:wq {file}` in an unnamed buffer write {file}, and the
  buffer takes that name ('cpoptions' flag F, in the default): it is no
  longer modified, the status line shows the name, and a later `:w`
  writes {file}. The name is taken before the write, so after a failed
  one ("E212: Can't open file for writing") the buffer has it all the
  same.
- In a named buffer `:w {file}` writes a copy. The buffer keeps its name
  and stays modified, so `:q` then says E37, and `:wq {file}` writes the
  copy but does not quit (E37, E162) unless the buffer had no changes.
- A {file} that exists, other than the buffer's own file, is not
  overwritten: "E13: File exists (add ! to override)". `:w! {file}` and
  `:wq! {file}` overwrite it; `:w!{file}` needs no space, while `:wfoo`
  is "E492: Not an editor command". `:w` followed by spaces is `:w`, and
  `:w a b` writes one file named 'a b'.
- vim also expands `%`, `#`, `~` and wildcards in the name, and has
  `:w >> {file}` and `:w !{cmd}`: not planned here.

### What the editor does

Started without a file name, `editor_main` points `FNAME_PTR16` at
`str_untitled` ("[No Name]"), loads `./[No Name]` if there is such a
file, and `:w` writes the text to a file of that name. `cmd_parse_w`
(command.asm) takes only `:w` and `:wq`: `:w foo`, `:w!` and `:wq!` say
"Unknown command". `command_write_file` opens `(FNAME_PTR16)` with
`openout`, writes, clears `MODIFIED` and holds '"name" written' on the
status row (`hold_message_ax`). A read-only (truncated) buffer refuses
every write with "Read-only (file truncated)".

Since 11401c7 `FNAME_PTR16` points at the name where the emulator keeps
it (its argument window, $FE00-$FFDF), and the `$0280`-`$02FF` half of
the `$0200` page is unused (the search pattern takes the other half since
the vim leftovers batch B).

The environment has no call that tests whether a file exists, but `open`
(17/environment.asm) returns handle 0 when the file cannot be opened for
reading, so `open` then `close` tests for a readable file. The emulator's
`open` is `fopen(name, "rb")`: a file that exists but cannot be read
counts as missing, and on Linux a directory opens, so `:w {dir}` would
say E13 where vim says "E502: is a directory" (`opendir` could tell).

### Plan

- Names. An unnamed buffer is one whose `FNAME_PTR16` is `str_untitled`
  (in the code, so its high byte is never `$02` or `$FE`-`$FF`: one
  compare tells). A name that `:w {file}` gives an unnamed buffer is
  copied from `CMD_BUF` into `$0280`-`$02FF` (`FNAME_BUF`; `CMD_BUF`
  holds 127 characters, so a name has at most 125), and `FNAME_PTR16`
  points there. A new zero-page word `W_NAME16` holds the name being
  written: `openout` and the report ('"{file}" written', through
  `print_string_ax`) take it, and `write_fname` stays for the status bar.
- `editor_main`: with no argument, point `FNAME_PTR16` at `str_untitled`
  and go straight to `buf_init`, loading nothing.
- `cmd_parse_w`: after `w`, an optional `q` (which decrements `CMD_QUIT`
  as now), an optional `!`, then spaces. A name must follow a space or the
  `!`, else "Unknown command". No name, or the buffer's own name (a byte
  compare with `(FNAME_PTR16)`): write the buffer's file, or "E32: No file
  name" if it has none. Another name: without `!`, `open` it, and if that
  gives a handle, `close` it and say "E13: File exists (add ! to
  override)"; then an unnamed buffer takes the name (before the write, as
  vim does) and writes its file, and a named one writes a copy.
- `command_write_file` takes `W_NAME16` and a flag for "the buffer's own
  file" (the carry): only that clears `MODIFIED`. A `:wq` whose copy
  leaves the buffer modified shows the `:q` message ("No write since last
  change") and does not quit, as vim's E37. One exit (clear `CMD_QUIT`,
  then `show_message_ax`) serves E32, E13, the failed open, the refused
  quit and an unknown suffix (`:wqx` must not quit either).
- A read-only buffer keeps refusing every write, a copy included: its
  text is cut short.
- Memory: 2 zero-page bytes and `$0280`-`$02FF`.
- Size, *measured* on a sandbox prototype of all of the above (suite
  green, the cases below checked): +136 bytes for `:w {file}`, `:wq
  {file}`, E32 and the startup change (18 of them the message), and +74
  more for E13 and `!` (37 of them the message), +210 in all. This is
  more than the earlier estimate (a prototype on an older tree measured
  +95, E13 and `!` guessed at 50-60 more): that prototype had none of
  vim's copy rules (a named buffer's `:w {file}` stays modified, its `:wq
  {file}` refuses to quit, the report names the file written), no
  own-name compare, no `:wfoo` check and no startup change. Trims: taking
  vim's E37 wording, "No write since last change (add ! to override)",
  lets the two messages share " (add ! to override)" (about 15 bytes
  less); without the own-name compare (13 bytes) `:w {its own name}`
  would need `!`.
- CPU and repaint: nothing outside `:w`; E13 costs an `open` and a
  `close` per `:w {file}`.
- Risks: the own-name compare is a string compare where vim compares full
  paths (`:w ./t` in buffer `t` says E13); the name is taken as typed (no
  `~`); the status bar still shows at most 32 characters of the name.
- Tests first. The harness needs a test-infrastructure commit first:
  `run_test` with no file argument (`run_test_screen` has `no_file`) and a
  check of other files in the test directory. Then:
  - no argument, `ihi<Esc>:w<CR>`: "E32: No file name", no file written
    (today a file '[No Name]' holds 'hi');
  - no argument, `ihi<Esc>:wq<CR>x:w foo<CR>`: E32, no quit, then foo
    holds 'h';
  - no argument, `ihi<Esc>:w foo<CR>x:w<CR>`: foo holds 'h', and the
    status bar says foo;
  - no argument with a file `ex`: `:w ex` says E13 and leaves it; `:w!
    ex` and `:w!ex` write it;
  - file `t`: `x:w other<CR>` writes other, leaves t, keeps `[+]`; then
    `:q` is refused; `x:wq other<CR>` does not quit; `:wq other` with no
    change quits;
  - `x:w t<CR>` (its own name) and `x:w   <CR>` write t; `:wfoo` and
    `:wqx` say "Unknown command" and do not quit;
  - no argument with a file `[No Name]` in the directory: the buffer
    starts empty.

## 2. J and the joined line's leading blanks (kept for now)

### What vim does

J (not gJ) joins lines by these rules (vim 8.2 defaults: 'joinspaces'
on, no j in 'cpoptions' or 'formatoptions'):

- Each joined line loses its leading blanks (spaces and tabs).
- One space goes in place of the line break, except:
  - none if the joined line is empty or all blanks, or starts (after its
    blanks) with ')';
  - none if the text so far ends in a tab, or is empty (the first line
    was empty and nothing has been added since);
  - none if the text so far ends in a space; but then, with 'joinspaces',
    one if the character before that space is '.', '!' or '?'.
- Two spaces after '.', '!' or '?' ('joinspaces'; with 'nojoinspaces'
  one).
- A joined line that was empty or all blanks leaves "the text so far
  ends in" unset for the next join: 'abc.', '', 'def' with 3J gives
  'abc. def', and 'abc ', '', 'def' gives 'abc  def'.
- The cursor goes to the last join: on the first space put in, or where
  the joined text starts if none was (clamped to the last character).
- u puts the lines back, with the cursor where J was typed. A count past
  the last line joins the lines there are.

For example 'abc' + '  def' = 'abc def', 'abc' + '' = 'abc', 'abc' +
'  )x' = 'abc)x', 'abc\t' + 'def' = 'abc\tdef', 'abc ' + 'def' = 'abc
def', '' + '  def' = 'def', 'abc.' + 'def' = 'abc.  def', 'abc. ' +
'def' = 'abc.  def'; 'a', ' b', '  c', '   d' with 4J gives 'a b c d'
with the cursor on column 5.

### What the editor does

`normal_join_lines` (normal_edit.asm) replaces each line break with a
space in place: the text keeps its length, a joined line keeps its
blanks ('abc' + '  def' = 'abc   def'), and an empty line leaves a
trailing space ('abc' + '' = 'abc '). The undo record in `UNDO_DATA_BUF`
is each join point's 16-bit offset in the joined line (`JOIN_UNDO_MAX`,
128 joins: 129 lines); `undo_join_apply` writes '\n' (undo) or ' '
(redo) back at the offsets, so neither undo nor redo moves any text. The
join limit is checked before anything changes, so a refused J keeps the
undo of the edit before. HELP and vi-compatibility-changes document it.

### Plan

- Pre-scan, before anything changes. Walk the N lines; for each join
  find L, the joined line's leading blanks, and S, the spaces to put in
  (0, 1 or 2) by the rules above, tracking the last two characters of the
  text so far (unset after a blank line) and whether it is empty. Sum the
  change in length (S - 1 - L per join, positive only for two spaces over
  a line with no blanks), the size of the undo record, and K, the joins
  that grow the text. Refuse, changing nothing, if the record does not
  fit ("Too many lines to join") or the growth does not fit the text
  buffer ("Buffer full"). The per-join test (L and S) is a subroutine the
  join pass calls again: there is nowhere to keep its results, since the
  undo page must stay as it is until the J is sure.
- The join. If K > 0, first `buf_shift_right_16` K bytes at the first
  join point, the room the growing joins need. Then one forward pass from
  the first join point copies the text down (the write never passes the
  read), putting S spaces where each line break and its blanks were and
  writing each join's record entry, and `buf_shift_left_16` closes what
  is left of the gap. Then `buf_rebuild_lines`, `mark_join_lines` and
  the cursor as now, and `RF_JOIN` from the first join point.
- The undo record, one entry per join: the join point's offset in the
  joined line (2 bytes, as now) and a byte for the blanks removed: bit 7
  set, that many spaces (up to 127); clear, that many bytes follow as they
  were (tabs). The entries are written from the top of `UNDO_DATA_BUF`
  down, so undo reads them from the last join to the first. S is not
  stored: the joined text never starts with a blank, so undo counts the
  spaces at the offset, at most 2 and not past the next join's offset (a
  blank line's join puts nothing in, and the next join then has the same
  offset). An entry takes 3 bytes, more with tabs, so the join limit
  falls from 128 joins to 85 (86 lines) for lines indented with spaces,
  and depends on the text. (Storing S takes a fourth byte and saves the
  counting: 64 joins.) Typed-ahead J's keep one entry, for the last join,
  as now.
- Undo: `buf_shift_right_16` the text after the joined line by the total
  growth back plus K, then one backward pass from the end of the joined
  line to the first join point puts back each line break and its blanks
  and drops its spaces, and a second shift takes the K bytes back. Then
  `buf_rebuild_lines`, `mark_adjust_insert`, and the cursor to
  `UNDO_JOIN_COL16` as now.
- Redo: join again from `UNDO_LINE16` with `UNDO_JOIN_COUNT` joins (the
  text is as it was before the J), which writes the same record;
  `undo_join_redo` and `undo_join_apply` go.
- Without 'joinspaces' no join grows the text: J needs no first shift and
  undo no second one, and the last-two-characters tracking shrinks, about
  40 bytes less.
- Size (not prototyped): about +200 bytes, 150 to 250, in line with the
  earlier estimate of about 190. New code: the pre-scan with its per-join
  subroutine about 100-120 bytes, the join pass 70-90, the undo pass about
  100, the shifts about 30, the redo about 15; gone: the in-place loop,
  `undo_join_apply` and `undo_join_redo`, about 150 bytes now.
- CPU: J and its undo move the text after the joined lines once (about 16
  cycles a byte; twice when a join grows), on top of the whole-buffer
  `buf_rebuild_lines` J already does. Repaint as now: the joined line from
  the first join point, the rows below scrolled up (`RF_JOIN`).
- Risks: the undo passes' pointer arithmetic around joins at one offset;
  the join limit now depends on the text; the record of typed-ahead J's.
  Run the render oracle and a J/undo fuzz against vim (`vimh`-style, each
  key its own undo step).
- Tests first: the examples above as content and cursor tests; `3J` on
  'abc.', '', 'def'; `u` and `u u` after joining a line indented with a
  tab and spaces ('abc', '\t def'), with the cursor; a count at the new
  limit and one past it; with the small-buffer build, a J that would grow
  a full buffer says "Buffer full", changes nothing and keeps the previous
  undo; typed-ahead `JJJ` against the same keys one at a time. Of the
  current tests, 'J redo wrapped same height: partial from join col'
  joins a line ending in '!!', which now takes two spaces, so its rows
  change; no test pins the kept blanks.

## 3. Search messages (kept for now)

### What vim does

- A search that goes on past the end of the file from the top says
  "search hit BOTTOM, continuing at TOP"; past the start, from the bottom
  (?, or N after /), "search hit TOP, continuing at BOTTOM". This holds
  for /, ?, n and N, for any step of a count (3n that wraps on its second
  step), and for a match found only on the cursor's own line (the only
  match in the file). vim shows it in the WarningMsg colors.
- A pattern found nowhere: "E486: Pattern not found: {pattern}". n or N
  before any search: "E35: No previous regular expression".
- A search that finds a match without wrapping shows the search itself
  ('/foo') on the command row.
- None of these waits for a key: the next key works as usual. The message
  stays on the command row until something writes there (another message,
  the next search's echo, "-- INSERT --", a ':' or '/' prompt) or a redraw
  clears it; j and k leave it. ('shortmess' flag s would drop the wrap
  messages; it is not in the default.)

### What the editor does

`search_forward` and `search_backward` (search.asm) wrap silently
(`SEARCH_LINE16` goes back to line 0, or on to the last line). With no
match, `search_show_not_found` shows "Pattern not found: {pattern}"
(`show_message_ax`, then the pattern), which stays on the status row
until the next key, and that key runs (item 4). n and N before any
search do nothing. After a search the status bar comes back.

The `:w` and range reports show how a message can stay: they end in
`hold_message_ax`, which sets `STATUS_HOLD`, and `status_build` then
leaves the status row alone for one frame, the one that ends the command
(bc7b5d8). The next key's frame draws the whole status bar again
(`status_line_clear` left `ST_LEN` at 0). Text on the status row stops a
column short of the edge (`text_putc`, a844953).

### Plan

- A zero-page flag, `SEARCH_WRAP`: `search_find` (normal_move.asm) clears
  its bit 7 (`LSR`) before the count loop, and the wrap branches of
  `search_forward` (`ROR`, the carry is set there) and `search_backward`
  (`SEC`, `ROR`) set it. When the loop ends with a match and bit 7 set,
  `search_find` shows "search hit BOTTOM, continuing at TOP" (direction
  0 in `BUF_TEMP`) or "search hit TOP, continuing at BOTTOM" with
  `show_message_ax` as item 4 leaves it (cleared row, message, held).
  A search that finds nothing shows only the not-found message.
- `str_not_found` becomes "E486: Pattern not found: " (the message
  already holds, since item 4).
- Display: the message goes on the status row in the handler, before the
  frame. The frame draws only text rows, by scroll or full redraw
  (`render_screen` does not clear the screen), and `status_build` skips
  the status bar once, so the message shows however far the cursor went;
  the next key's frame puts the status bar back. So the message lasts
  until the next key, where vim's lasts until something writes the row:
  the editor's status row is also its ruler.
- Size, *measured* on a sandbox prototype on top of item 4: +108 bytes,
  74 of them the two messages and 6 the "E486: ", 28 of code (the earlier
  estimate was 80-100). Printing the messages in pieces ("search hit ",
  then the two words around ", continuing at ") saves about 18. E35 would
  add about 45, most of it the message. Echoing '/foo' after every search
  is not planned.
- CPU and repaint: a wrapping search's frame sends the message (about 45
  bytes with the cursor move and the row clear) instead of the changed
  columns of the status bar, and the next key's frame sends the whole
  status bar (about 40 bytes at 40 columns).
- Risks: none found: it is the reports' hold, which the per-frame fuzz
  covered. On screens narrower than 37 columns the message is cut off, as
  other messages are.
- Tests first (10x40; the message checks fail on 9d5cfd0, and all pass
  on the prototype):
  - 'foo', 'bar', 'foo' with `jj/foo<CR>`: "search hit BOTTOM, continuing
    at TOP" on the status row, cursor (0,0); with a `j` after it, the
    cursor on row 1 and the status bar back;
  - the same file, `?foo<CR>`: "search hit TOP, continuing at BOTTOM",
    cursor (2,0); `/foo<CR>n`: the BOTTOM message; `/foo<CR>3n`: the
    BOTTOM message, cursor (0,0); `/foo<CR>` alone: the status bar;
  - 'foo' with `/foo<CR>`: the BOTTOM message (the match wraps to
    itself);
  - a wrap that scrolls the view, and one that redraws the screen, keep
    the message;
  - 'foo', 'bar' with `/zz<CR>`: "E486: Pattern not found: zz"; with a
    `j` after it the cursor moves (as it does since item 4).

## 4. Messages (done)

Every message but the reports of `:w` and range commands used to wait
for a key and throw it away, even a key typed ahead. Since the
vim-compatibility pass, part B, `show_message_ax` holds its message on
the status row as the reports do (`hold_message_ax`: the frame that ends
the key leaves the status bar alone) and the next key runs as usual, as
in vim; the not-found message of a search does the same. `:marks` keeps
its waits, as vim's more-prompt and hit-enter prompt do. It measured 5
bytes less; nine tests that pinned the swallowed key now expect vim's
behaviour.

## 5. Undo of insert-mode typing (subsets 1 and 2 done)

Subsets 1 and 2 below were done in the vim-compatibility pass, part C:
u takes back the typing of i, a and A (the editor has no I), and of o
and O with the line they opened, a stretch between cursor moves at a
time, and u again redoes it. Left: subset 3, a BS or DEL past the
stretch's edges, and subset 4, the typing after c, s, C, S and cc; both
still clear the undo, as all typing did before. The analysis follows as
it was written, after a summary of what was built.

### What was built (part C)

- The record (`UNDO_INSERT`) is as planned: the segment's start
  (`UNDO_LINE16`, `UNDO_COL16`) and the length of its text before the
  cursor (`UNDO_INS_LEN16`). `insert_segment` keeps it for each batch
  that goes in (a refused batch, and one that changes nothing, leave it
  alone). `INSERT_SEG` (was `INSERT_CHANGED`) is the segment's state: 0
  none (the next change starts one, `insert_seg_start`), $FF kept, $7F
  not kept (after a change command, `enter_insert_change`, or a BS or DEL
  past the edges: its changes clear the undo). `insert_exit` no longer
  clears the undo.
- Moves: a key that `insert_keys` dispatches ends the segment when the
  cursor moved (the line and column against `SNAP_LINE16` and
  `SNAP_COL16`), and Home and End always do, as vim's `start_arrow`
  calls go; a key that fails (Right at the line end, Up on the first
  line, Left at column 0, and since section 6 PgUp with the first line
  on top) does not, in vim either (it beeps).
- u deletes the text (`delete_at_cursor`) and puts the cursor at the
  start, clamped, where vim's u and Ctrl-R put it. The text is kept in
  `UNDO_DATA_BUF` for the redo when it is at most 255 bytes; a longer
  one is undone once and its record ends (vim redoes it), and a
  typed-ahead uu then draws the undo. The redo puts the text back and
  draws a split as the undo of a char delete over line breaks does
  (`RF_SPLIT`).
- o and O record the segment themselves, and `UNDO_OPEN` is gone. The
  segment starts at column 0 of the opened line and its line break
  follows the text (`UNDO_INS_OPEN`: 1 for O, 2 for o), so it is always
  whole lines: u deletes them as lines (`RF_DEL`, drawn as the undo of o
  always was) and returns to the line and column o or O was typed at
  (`UNDO_RET_COL16`), and the redo puts them back as lines (`RF_INS`),
  with the cursor on the first. For O that is where vim goes; after o
  vim goes to the line o was typed on, which a line insert cannot draw
  from (vi-compatibility-changes). Unlike the plan below, o's line break
  is not before the typing, so a BS at the start of o's line deletes text
  from before the segment and clears the undo, as a DEL at its end does.
- Measured: 93 bytes for the record and the undo (`TEXT_BUF` moved to
  $3700), 21 for the moves, 90 for the redo, 18 for o and O (the
  `UNDO_OPEN` code it replaced was 53 bytes), 4 less with the segment
  start shared: 218 bytes. A key typed alone costs 56 cycles more, a
  typed-ahead batch about 130, a cursor key in insert mode about 56 (86
  when it fails); the undo of 5 chars about 200 more for the copy, of
  255 chars about 4,500.

### What vim does

With 'backspace' at indent,eol,start (defaults.vim; the editor's BS
behaves so), checked by typing into vim 8.2 in a terminal (keys fed as
one `normal!` command do not break at the arrow keys):

- What is typed from entering insert mode (i, a, A, I, o, O, and the
  change commands c, s, C, S, cc) to ESC is one change: u takes it all
  back, line breaks typed, BS over line breaks and over text that was
  there before, and DEL included. For o, O and the change commands the
  opened line or the changed text comes back in the same step.
- A cursor move in insert mode (arrow keys, Home, End, PgUp, PgDn,
  Ctrl-Left and Ctrl-Right) starts a new change: each stretch of typing
  between moves is its own undo step, and u takes the last one back
  first. A move with nothing typed after it adds no step. A key that
  cannot move (Right at the line end, Up on line 1, Left at column 0,
  PgUp at the top) beeps and starts no new change; Home and End always
  start one.
- u puts the cursor where that stretch of typing began (in normal mode:
  on the last char when that is past the line end), and redo (Ctrl-R)
  there too; after o and O, where o or O was typed (the line o was
  typed on, the column too).
- An insert that typed and erased again is still a change: u undoes it
  (nothing to see), and the edit before stays done.

For example: 'abc' with `Ahello<Left><Left>XY<Esc>` gives 'abchelXYlo';
u gives 'abchello' (cursor column 6), u again 'abc'. `ihello<Left><Esc>u`
gives 'abc'. `ofoo<CR>bar<Esc>u` gives 'abc'. 'abc', 'def' with
`ji<BS><BS>X<Esc>` gives 'abXdef', and u both lines, the cursor on
(1,0). 'abcdef' with `3liXY<Left><BS><BS><Esc>` gives 'abYdef'; u gives
'abcXYdef' (cursor column 4), u again 'abcdef'. 'abc def' with
`wcwfoo`, five BS and `X<Esc>` gives 'abX'; u gives 'abc def' (cursor
column 4). 'abc' with `x`, `ia<BS><Esc>`, `u` gives 'bc'.

### What the editor did before part C

`enter_insert_mode` (normal_util.asm) clears `INSERT_CHANGED`, every
insert batch that changes the text sets it (`insert_handle_key`), and
`insert_exit` then calls `undo_clear`. So after typing u does nothing,
and the undo of the edit before the insert is lost. o, O and the change
commands record their own undo (`UNDO_OPEN`, `UNDO_CHAR`, `UNDO_CC`) and
keep it only when ESC follows with nothing typed. Moves in insert mode
change nothing here. 2c0f8a0 settled that a batch counts as a change
when one of its keys would change the text on its own, a char typed and
erased again included, and kept "typed text clears the undo".
HELP and the README document this.

### Why single-level undo keeps it small

With multi-level undo, each stretch between moves would need a record of
its own. The editor keeps one record, so only the last stretch (a
*segment*) needs one: a segment starts at the first change after
entering insert mode or after a move, and its record replaces the old
one then; a move ends it, and its record stays for u. That is what vim's
first u undoes. (vim's second u would undo the stretch before; the
editor's second u redoes, as it does after every command.)

Within a segment the cursor moves only by typing, Enter, BS and DEL, so
the segment's effect always has one shape: the bytes from its start to
the cursor are new; bytes BS deleted before the start and bytes DEL
deleted after the cursor are old text gone. That is the record.

### The record

- `UNDO_TYPE` = a new `UNDO_INSERT` (14), with handlers in `undo_step`'s
  undo and redo tables.
- `UNDO_LINE16`/`UNDO_COL16`: where the new text starts (it moves left
  when a BS passes it).
- `UNDO_PASTE_COUNT16` (an alias, `UNDO_INS_LEN16`): the new text's
  length, 16 bits.
- `UNDO_DATA_BUF`: the old bytes the segment deleted, BS deletions from
  the top of the page down (each BS takes the byte before the start, so
  they land in text order) and DEL deletions from the bottom up.
  `UNDO_JOIN_COUNT` (an alias) and a new zero-page byte count them. They
  take at most 256 bytes between them; a segment that deletes more is
  not undoable (its record is cleared, as every insert's is now).
- `INSERT_CHANGED` comes to mean "a segment is open". The first batch of
  a segment that changes the text writes the record (the type, the
  cursor as the start, zero counts). A move ends the segment: one store
  in `insert_handle_key` before it dispatches a non-editing key through
  `insert_keys`. `insert_exit` no longer calls `undo_clear`.

### Keeping the record

The batch's execution phase (`insert_handle_key`) already has what the
record needs: `back` (the BS's past the batch's own chars, clamped at the
buffer start), `fwd_actual` (the DEL's, stopped at the final newline),
`insert_len` and `delete_start`. A refused batch must change neither the
text nor the record, so the record is updated once the batch is sure to
go in:

- erased = min(`back`, the new text's length); the other `back - erased`
  bytes at `delete_start` were old text: copy them to the page, and the
  start moves to `delete_start` (its line is the batch's first merged
  line, its column the distance from that line's start);
- the `fwd_actual` bytes at the cursor were old text: copy them to the
  page;
- the new text's length becomes length - erased + `insert_len`.

The copies go before `buf_shift_left_16` when the batch shrinks the text
(that shift overwrites them, and it cannot fail), and after
`buf_shift_right_16` when it grows the text (the old bytes stay in place
until the batch's own copy, and a shift that fails must leave the page
alone: the record before may keep data there).

A batch never runs past a move (a non-editing key ends it), so keys typed
ahead give the same record as keys typed one at a time, and "undo behaves
as if the keys were processed one at a time" holds with no extra work.

### Undo and redo

- Undo: the cursor to the start; save the new text in the page for redo
  if it fits beside the old bytes (at most 256 in all); replace the new
  text with the old bytes (one shift by the difference and a copy, then
  `buf_adjust_lines_apply`, or `buf_rebuild_lines` and `mark_adjust_*`
  when either holds a line break); the cursor to where the typing began
  (the start plus the bytes BS deleted); `undo_set_done_flags`.
- Redo: the same the other way round, the cursor to the start (as vim's
  Ctrl-R). A segment whose new text did not fit the page is undone once,
  and its record is then cleared, so u after it does nothing. (The top of
  the free text space could hold a longer text, since nothing writes
  there before the next edit and that replaces the record anyway, but
  only while the free space after the redo is at least the text's
  length: not worth it at first.)
- Repaint: a one-line segment repaints its line from the start column
  (`RF_LINE`, with the ICH/DCH hint when the difference is at most 128),
  as the undo of x or p does; one with line breaks takes the paths of the
  undo of a multi-line char paste or delete (`RF_JOIN`, `RF_SPLIT`),
  and a full redraw when it both adds and removes line breaks (rare).
- CPU: a few dozen cycles per batch for the record, and about 15 per old
  byte copied to the page. u moves the text after the start once, as the
  undo of x or p does.

### o, O and the change commands

- o and O: vim's u takes the opened line and its text back in one step.
  Make o and O open a segment whose new text is the new line: start
  (M, 0) with M the new line, length 1 (its line break, which is after
  the cursor), and typing lengthens it. The record also keeps the line o
  or O was typed on, where vim's u returns, as `UNDO_OPEN` does now (in
  `UNDO_COL16`; with subset 3 below, a start moved by BS needs that
  field, and the line moves to a new zero-page word). Undo deletes the
  new text (for length 1, the line, as `undo_open_undo` does now) and
  returns there; redo puts the text back from the page. The one wrinkle:
  the new line's break is after the cursor, so a DEL at the end of that
  line takes it from the segment instead of recording an old byte (a
  flag).
- c, s, C, S and cc: their records (`UNDO_CHAR`, `UNDO_CC`) keep the
  changed text in the yank buffer. The first segment after them extends
  that record instead of replacing it: undo first deletes the typed text
  at the record's position, then undoes the change as now; redo redoes
  the change, then puts the typed text back. BS past the start of such a
  segment deletes text before the change: for `UNDO_CHAR` the page holds
  it as above; for `UNDO_CC`, whose undo expects one empty line, it can
  end the undo as now. (A new yank already ends these records.)

### Subsets and sizes (estimates made before part C)

Subsets 1 and 2 measured 218 bytes with the redo in part C (see What was
built); 3 and 4 are left, at the estimates below. The redo of part C
keeps the typed text in `UNDO_DATA_BUF`, so subset 3's old bytes need
room beside it: the page shared (the redo only when both fit), or the
free `$0280`-`$02FF` for one of them. o's segment starts at the opened
line's column 0, so subset 3 also covers a BS at the start of o's line.

1. The simplest useful subset: segments of i, a and A that only type
   (chars, Tab, Enter, BS over their own text), with undo and redo within
   the page; a BS or DEL that reaches old text, and the change commands,
   clear the undo as now (and the segment stays closed until the next
   move). It covers `ihello<Esc>u` and
   `Ahello<Left><Left>XY<Esc>u`. About 120-160 bytes: opening the record
   and counting in the batch (about 45), ending segments at moves (about
   5), the undo handler with the redo save (about 45), the redo handler
   (about 40), the table entries, less `insert_exit`'s `undo_clear`.
2. o and O as segments: about 25 more (the `UNDO_OPEN` handlers take the
   segment's length).
3. BS and DEL past the segment's edges, kept in the page: about 50-70
   more.
4. The change commands: about 40-60 more.

All four: about 250-300 bytes, so one or two pages of text buffer. An
undo with no redo (u after the undo does nothing) would save about 40
bytes but break u's toggle.

### Risks

The batch's execution path is dense and has its own fuzzers (batch
against paced, the render oracle): the record must follow exactly what
the batch deletes, `back` clamped at the buffer start and `fwd_actual`
stopped at the final newline included. u of a segment with line breaks
moves marks with `mark_adjust_delete` and `mark_adjust_insert`, which
unset the marks of removed lines where vim puts them back (the undo
records of a char delete and of cc keep the marks in `UNDO_DATA_BUF`
since part B, `mark_save` and `mark_restore`; a segment needs that page
for its old bytes, and extending a change command's record, subset 4,
would have to fit both). `MODIFIED` after u stays set, as for every
undo.

### Tests first

- 'abc': `ihello<Esc>u` gives 'abc' with the cursor on (0,0);
  `lihello<Esc>u` puts it on (0,1); `ihello<Esc>uu` gives 'helloabc'
  (the redo).
- 'abc': `Ahello<Left><Left>XY<Esc>u` gives 'abchello'; with `u u`,
  'abchelXYlo'; `ihello<Left><Esc>u` gives 'abc'.
- 'abc': `ofoo<CR>bar<Esc>u` gives 'abc' (subset 2).
- 'A', 'B' with `ddiX<Esc>u` gives 'B': the test "dd then iX ESC u:
  typing clears undo" (today 'XB') changes, and so does "dd then oNew ESC
  u: insert clears undo" with subset 2. 'ab', 'cd' with `ddix<BS><Esc>u`
  still gives 'cd' (the empty segment is undone).
- A segment with Enter and BS typed ahead against the same keys one at a
  time.
- Later subsets: `ji<BS><BS>X<Esc>u`, `Axy<Del><Del><Esc>u`,
  `3liXY<Left><BS><BS><Esc>u`, `o<BS>x<Esc>u`, `ofoo<Del><Esc>u`, and
  part C's four tests that pin the undo cleared by a BS or DEL past the
  edges ("Insert undo: BS of text from before the insert clears undo",
  its DEL test and the two for o), which change with subset 3;
  `cwfoo<Esc>u`, then "sX ESC: typing clears undo" and "cc New ESC:
  typing clears undo", which change with subset 4. (Part C tests the
  segments of 255 and 256 bytes: the second is undone once, then u does
  nothing.)

## 6. Ctrl-F and Ctrl-B (done, but for long lines)

Done after part C, from part A's patch: Ctrl-F, Ctrl-B, PgDn and PgUp
(PgDn and PgUp in insert mode too, where vim types Ctrl-F and Ctrl-B
into the text, as the editor does since leftovers batch A) page as
below, for lines that fit a row exactly as vim does (the part-A paging
differential against vim 8.2: 0 of 400 Ctrl-F sessions differ, and of
1,000 mixed page sessions the 25 left are two older differences: vim
centres the cursor line after a jump of more than half a screen (20),
and writes an emptied buffer as no bytes (5), as the editor does since
leftovers batch A). What is left is the overlap over long lines (below).

### What vim does

vim keeps two lines of the page on the screen (one with 4 text rows,
none with 3 or fewer) and counts the page from the first line it did
not show in full (its botline), so a page moves by screen rows, wrapped
lines included. Ctrl-F puts the cursor on the new top line and Ctrl-B
on the new bottom line; when the page would show the last line, Ctrl-F
puts it on top, and with the last line on top (Ctrl-F) or the first
line (Ctrl-B) it beeps and does not move. A count that runs out keeps
the remembered column where typed-ahead presses go to the first
non-blank. When the new bottom line would start just below a screen of
the file's first lines, Ctrl-B leaves them on top and its
`cursor_correct` puts the cursor on the line above. 30 lines at 10x40:
Ctrl-F puts line 8 on top with the cursor there.

The lines kept depend on their rows (`get_scroll_overlap`): two when
the two lines and the longer of the lines next to them (the line below
them and the line above them) take at most `TEXT_ROWS` - 2 rows, else
one when that line and the longer of its neighbours do, else none. So
at 10x40 with lines of three rows vim keeps one line, and none next to
a line of six or more rows. After Ctrl-B vim shows whole lines from the
top line down (its view), the new bottom line where they end.

### What the editor does

`normal_page_down` finds the line below the page with
`find_line_from_top_a` (the line at row `TEXT_ROWS`, walking from the
top of the view, so a range repaint's `WRAP_QUOT` does not matter),
backs over the lines kept (`page_setup`: 2, 1 or 0 by `TEXT_ROWS`),
puts the last line on top when the page reaches it, and moves at least
one line; `normal_page_up` puts the cursor on the line above the last
line kept and scrolls its first row to the bottom row through a new
`ensure_row_visible` entry of `ensure_cursor_visible` (`page_view`),
with vim's `cursor_correct` case when that leaves line 2 on top. Both
stop at a page that cannot move (`page_fail`): a press of the count
keeps the column (and the remembered one), a typed-ahead press goes to
the first non-blank as the press before it did. `next_line` and
`dec_file_line` were split out of `advance_next_line` (and used in
`clamp_file_line` and `word_backward_x`). Measured: +118 bytes (the
terminal build's `TEXT_BUF` moved to $3800).

Left: the lines kept do not depend on their rows, and Ctrl-B puts the
new bottom line's first row on the bottom row (the top line may start
above the view, as after j, k and G). 10x40, 40 lines of 94 chars (3
rows each): Ctrl-F puts line 2 on top in vim (one line kept), line 1
here. Doing vim's overlap is a walk over four lines' rows and two sums
for each page, about 50 to 70 bytes (estimate); vim's whole-line view
after Ctrl-B is the display difference of j, k and G too.

## 7. Counts on i, a, A, o and O (kept for now)

### What vim does

Checked by typing into vim 8.2 in a terminal:

- ESC after i, a, A (or I) with a count types the text count - 1 times
  more at the cursor: 'abc' with `3ix<Esc>` gives 'xxxabc', the cursor
  on the third x; `3aab<Esc>` 'aabababbc', `3Aab<Esc>` 'abcababab'. An
  Enter typed goes in each time: `3ifoo<CR><Esc>` gives 'foo', 'foo',
  'foo', 'abc'.
- After o and O each copy goes on a line of its own: `3oab<Esc>` gives
  'abc', 'ab', 'ab', 'ab' (the cursor on the last 'ab'), `3Oab<Esc>`
  'ab', 'ab', 'ab', 'abc'; `3o<Esc>` opens three empty lines.
- u takes the typing and its copies back in one step.
- A cursor move in insert mode (an arrow key that moves, Home, End, the
  page keys) drops the count (vim's arrow_used): `3ia<Left>b<Esc>` gives
  'baabc'. A key that fails to move keeps it.
- The copies replay the keys typed, BS and DEL included: `3ixy<BS>z<Esc>`
  gives 'xzxzxzabc', `3A<BS>xy<Esc>` 'abxxxy' (each copy's BS takes the
  char before it), `3ix<Del><Esc>` 'xxx' (each copy's DEL takes a char of
  the text after it).
- The count of a change command (3s, 3cw, 3cc, 3C) is its own, not a
  repeat: `3sX<Esc>` on 'abcdef' gives 'Xdef'.

### What the editor does

The count is cleared on entering insert mode (enter_insert_mode ends in
clear_count), so `3ix<Esc>` gives 'xabc' and `3oab<Esc>` one line 'ab'.

### Plan

The typing to repeat is the insert segment of part C (section 5) when it
is all of the insert: its record holds where it starts (`UNDO_LINE16`,
`UNDO_COL16`) and its length (`UNDO_INS_LEN16`, and o's or O's line
break after it), and it ends at the cursor.

- A new zero-page word `INS_COUNT16` takes `COUNT16` in
  enter_insert_open (so for i, a, A, o, O and the change commands), and a
  move in insert mode clears it where it ends the segment
  (insert_handle_key's `.end_segment`). A change command's typing keeps
  no segment (`INSERT_SEG` $7F) until a move, which clears the count, so
  it never repeats, as in vim.
- insert_exit calls insert_repeat first, which does nothing unless a
  segment is kept (`INSERT_SEG` $FF) and the count is 2 or more:
  - the lines the copies add (the segment's line breaks, count_newlines
    after insert_undo_setup, times count - 1, mul_by_count) must fit the
    line table (check_line_room), and the bytes (the segment's length
    times count - 1) the text buffer (buf_shift_right_16), else "Buffer
    full" and nothing changes;
  - the copies go right after the segment (after o's line break), filled
    by one forward copy from the segment's start (mem_copy_down with the
    destination a segment's length on: each byte is read again a segment
    on);
  - `UNDO_INS_LEN16` grows by the copies, so u takes them back with the
    typing (and the redo puts them back when the whole fits the 255 bytes
    of `UNDO_DATA_BUF`);
  - the cursor goes back where ESC found it (`SNAP_LINE16`,
    `SNAP_COL16`) and on by the copies: a line for each line break they
    add, else a column for each byte; then `buf_rebuild_lines` and
    mark_adjust_insert (RF_FULL), or buf_adjust_lines_len (RF_LINE from
    the segment's start).
- Left as vim does otherwise: a BS or DEL past the segment's edges keeps
  no segment (subset 3 of section 5), so `3A<BS>xy<Esc>` and
  `3ix<Del><Esc>` type the text once (vim replays their BS and DEL too).
- Size, *measured* on a sandbox prototype of the above on top of the
  leftovers batch A (the suite green, and 16 tests of the cases above
  passing): +209 bytes, 2 more in zero page. Most of it is the two
  multiplications, the checks and the cursor arithmetic; a loop that
  re-runs the redo (undo_insert_redo) count - 1 times would be about 90
  to 110 bytes, but it shifts the text after the cursor once for each
  copy.
- CPU and repaint: one shift and one copy of the copies' bytes; a line
  rebuild when they have line breaks (a full redraw).
- Risks: the forward copy's overlap (the destination is the source plus
  the segment's length), the line check before the shift, and the
  cursor's line when o's line break is part of the segment.
- Tests first: the cases above (3ix, 3oab, 3Oab, 3aab, 3Aab, 3o, 3O,
  3ifoo<CR>, 3ixy<BS>z, 3i<Esc>, 3sX, 3ia<Left>b, 3oa<CR>b, u after 3ix
  and 3oab) with the cursor, and a typed-ahead 3o with typing against
  the same keys one at a time.

