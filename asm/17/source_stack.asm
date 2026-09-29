; Requires:
;   SOURCE_STACK       - 1 past the highest address; stack grows down (asm.asm)
;   SS_NAME            - buffer holding the source's name; alias to TOKEN
;                        (asm.asm / source_stack_test.asm)
;   MEMORY_POP_HANDLER - compile-time equate naming the routine
;                        pop_source should JSR when a memory frame is
;                        popped. The assembler points it at
;                        pop_label_scope_from_frame; the test program
;                        points it at a local RTS-only stub. Replaces
;                        the runtime-patched ss_on_pop_table that
;                        existed before.
;   SS_ERR_NO_FILE     - error handler for read_char when no source is
;                        open (errors.asm; only referenced under
;                        enable_debug)
;   err_file_not_found - error handler for when open returns 0 (errors.asm)
;   open, close, read  - source I/O syscalls (environment.asm)

; The source stack grows downwards. Each frame is laid out from low to
; high address (low address is closer to the top of the stack):
;
;   frame_size     - Total frame size in bytes (1-byte; offset 0)
;   curr_type      - Type of THIS source: 0=file, 1=memory (offset 1)
;   prev_type      - Type we're RETURNING to: 0=file, 1=memory (offset 2)
;   prev_line_L    - Line number in parent (low byte, offset 3)
;   prev_line_H    - Line number in parent (high byte, offset 4)
;   prev_data      - Parent state to restore on pop. Fixed 2-byte slot
;                    at offsets 5..6, regardless of prev_type:
;                      prev_type=0 (file):   offset 5 = prev_handle;
;                                            offset 6 unused
;                      prev_type=1 (memory): offsets 5..6 = prev_ptr_L,
;                                            prev_ptr_H (parent's
;                                            SS_MEM_PTR16 at the moment
;                                            of this push)
;   name\0         - Source name (null-terminated; starts at offset 7,
;                    variable length up to 127+null = 128 bytes)
;   <payload>      - Optional bytes reserved for memory frames via
;                    push_memory_source_reserve_payload (caller writes
;                    them after the push; the source stack itself never
;                    inspects payload contents). Used by expand_macro
;                    to carry per-invocation activation state; consumed
;                    by the memory-pop handler the host program wires
;                    in via the MEMORY_POP_HANDLER equate.
;
; Frame size: name_len + 8 + payload_size (1 frame_size + 1 curr_type
;   + 1 prev_type + 2 prev_line + 2 prev_data + name + 1 null + payload).
;   No parent-type branch: prev_data is always 2 bytes.
;
; Putting curr_type / prev_type / prev_line / prev_data at fixed
; offsets 1..6 makes pop_source O(1) end-to-end -- the pre-reorg
; version paid an O(name_len) skip-name walk to find prev_data on
; every pop. With prev_data at fixed offset 5, that walk is gone.
; File parents waste 1 byte at offset 6 in exchange for a constant
; frame-size formula and a fixed name offset that consumers (e.g.
; SHOW_FRAME_NAME) can use without scanning.
;
; SS_TEMP16 contract across the public push/reserve API:
;   check_source_frame_room   writes SS_TEMP16 := proposed pending base
;                             (= SS_PEND_P16 - frame_size).
;   ss_alloc_frame            reads SS_TEMP16 as the new base; doesn't
;                             write it. After return SS_TEMP16 still
;                             equals SS_P16 (the new top).
;   ss_alloc_pending_frame    same as alloc_frame but updates only
;                             SS_PEND_P16; SS_TEMP16 still equals the
;                             pending base after return.
;   ss_write_pending_header_and_name
;                             reads SS_TEMP16 as the frame base; ADVANCES
;                             it by 7 (so the name-copy loop can use Y
;                             as a direct SS_NAME index without needing
;                             X). After return SS_TEMP16 is no longer
;                             the frame base -- callers don't reuse it.
; In short: SS_TEMP16 is a transient "where am I writing" pointer
; threaded through a single push or reserve; outside one of those calls
; it's free for any caller to reuse.

  .zeropage

SS_CURR_CHAR:    .byte       ; The last character read
SS_CURR_FILE:    .byte       ; The current file handle
SS_CURR_LINE16:  .word       ; The current line number
SS_P16:          .word       ; Pointer to the current location in the source stack
SS_PEND_P16:     .word       ; Pending top of the source stack. Equal to
                             ; SS_P16 outside a reserve/commit window;
                             ; less than SS_P16 (lower address; stack
                             ; grows down) when a frame is reserved but
                             ; not yet committed. Heap-vs-stack OOM
                             ; check is performed against this pointer
                             ; so the pending region is structurally
                             ; protected from heap write-ahead.
SS_TEMP16:       .word       ; Temporary location for use in calculations
SS_PAYLOAD_SIZE: .byte       ; Number of payload bytes to reserve for the
                             ; next push_memory_source_reserve_payload
                             ; call. Always 0 outside of that path.

; Memory source support (zero-terminated buffers)
SS_SRC_TYPE:    .byte       ; Source type: 0=file, 1=memory
SS_MEM_PTR16:   .word       ; Current read position in memory

  .code

SS_SRC_TYPE_FILE   = 0
SS_SRC_TYPE_MEMORY = 1


source_stack_init:
  SET16 SOURCE_STACK, SS_P16
  SET16 SOURCE_STACK, SS_PEND_P16
  LDA #SS_SRC_TYPE_FILE
  STA SS_SRC_TYPE
  STA SS_CURR_FILE
  ; SS_SRC_TYPE_FILE is 0; reuse A for SS_PAYLOAD_SIZE init.
  STA SS_PAYLOAD_SIZE
  RTS


; Verify there's room on the source stack for the next frame. Reads the
; same inputs push_source_frame uses (SS_NAME, SS_SRC_TYPE) so callers
; can pre-check before any irreversible side effects (e.g. opening a
; file). Side-effect free on success; jumps to err_out_of_memory on
; failure.
;
; On exit (success): SS_TEMP16 = proposed new SS_P16. push_source_frame
;                    consumes this directly (it's the only place the
;                    frame size is computed), so a successful return
;                    here must be followed by push_source_frame before
;                    any other routine clobbers SS_TEMP16.
;                    A, Y clobbered. X preserved.
check_source_frame_room:
  ; Compute name length
  LDY #$FF
.len_loop:
  INY
  LDA SS_NAME,Y
  BNE .len_loop
  ; Frame size = name_len + 8 + payload_size. The 8 covers the fixed
  ; header (frame_size, curr_type, prev_type, prev_line lo/hi,
  ; prev_data lo/hi) plus the name's null terminator. prev_data is a
  ; fixed 2-byte slot regardless of parent type, so no SS_SRC_TYPE
  ; branch is needed here.
  TYA
  CLC
  ADC #$08
  CLC
  ADC SS_PAYLOAD_SIZE
  STA SS_TEMP16         ; total size in low byte; high byte is scratch below
  ; Compute proposed new lowest-extent = SS_PEND_P16 - size. For atomic
  ; pushes SS_PEND_P16 == SS_P16, so this matches the pre-reserve
  ; behaviour. For a reserve (when ss_reserve_frame lands) the same
  ; computation still represents the correct lowest extent because
  ; SS_PEND_P16 already reflects any in-flight reservation.
  SEC
  LDA SS_PEND_P16
  SBC SS_TEMP16
  STA SS_TEMP16
  LDA SS_PEND_P16 + 1
  SBC #$00
  STA SS_TEMP16 + 1
  CHECK_FOR_OUT_OF_MEMORY SS_TEMP16
  RTS


; Generic stack mechanic: commit a pre-checked frame allocation.
;
; Reads SS_TEMP16 (the proposed new SS_P16, set by
; check_source_frame_room), commits it, recovers the frame size as the
; one-byte difference (frames are always < 256 bytes), and writes that
; size at offset 0 of the new frame. Layout-agnostic past offset 0.
;
; PRECONDITION: caller has just called check_source_frame_room and the
; OOM check passed. ss_alloc_frame has no failure path.
;
; On exit:  SS_P16 = pre-call SS_TEMP16; (SS_P16),0 = frame_size;
;           Y = 0; A and X clobbered.
ss_alloc_frame:
  ; Recover size as low byte of (SS_P16 - SS_TEMP16).
  LDA SS_P16
  SEC
  SBC SS_TEMP16
  PHA                       ; Save size for the offset-0 write
  ; Commit new stack pointer. SS_PEND_P16 follows SS_P16 in lockstep
  ; for atomic pushes (no reserve/commit window in flight).
  CP16 SS_TEMP16, SS_P16
  CP16 SS_TEMP16, SS_PEND_P16
  ; Write frame_size at offset 0
  LDY #0
  PLA
  STA (SS_P16),Y
  RTS


; Generic stack mechanic: free the top frame.
;
; Reads the frame_size byte at offset 0 of the current top frame and
; advances SS_P16 past it, exposing the previous frame. Layout-agnostic.
;
; On exit:  SS_P16 advanced upward by the freed frame's size;
;           A = freed size; Y = 0; X preserved.
ss_free_frame:
  LDY #0
  LDA (SS_P16),Y
  CLC
  ADCA16 SS_P16, SS_P16
  ; SS_PEND_P16 follows SS_P16 in lockstep when no reserve/commit
  ; window is in flight (the steady state).
  CP16 SS_P16, SS_PEND_P16
  RTS


; Sibling of ss_alloc_frame for the reserve path: commits a
; pre-checked allocation to the PENDING pointer only, leaving SS_P16
; (the committed top) unchanged. Writes frame_size at offset 0 of the
; new pending region.
;
; PRECONDITION: caller has just called check_source_frame_room and the
; OOM check passed. Steady-state precondition: SS_P16 == SS_PEND_P16
; (no other reservation in flight) -- enforced by usage in the
; assembler today (only expand_macro reserves, and never re-enters
; while a reservation is pending).
;
; On exit:  SS_PEND_P16 = pre-call SS_TEMP16; (SS_PEND_P16),0 = frame_size;
;           SS_P16 unchanged; SS_TEMP16 still holds the pending base
;           (read but not written); Y = 0; A and X clobbered.
ss_alloc_pending_frame:
  ; Recover size as low byte of (SS_PEND_P16 - SS_TEMP16). At entry
  ; SS_PEND_P16 == SS_P16 (steady state), so the diff fits in a byte
  ; (frames are always < 256).
  LDA SS_PEND_P16
  SEC
  SBC SS_TEMP16
  PHA                       ; Save size for the offset-0 write
  ; Move the pending pointer; SS_P16 stays where it was.
  CP16 SS_TEMP16, SS_PEND_P16
  ; Write frame_size at offset 0 of the new pending region.
  LDY #0
  PLA
  STA (SS_TEMP16),Y         ; SS_TEMP16 == SS_PEND_P16 here
  RTS


; Reserve a pending frame. SS_P16 does NOT advance -- only SS_PEND_P16
; does. The frame's header (offsets 1..4) and name (offsets 7..) are
; written into the pending region; the prev_data slot at offsets 5..6
; is left UNINITIALIZED. Commit captures prev_data after the reserved
; window closes -- parent's SS_MEM_PTR16 typically advances during
; that window (e.g. expand_macro's arg parsing), so eager prev_data
; capture would record a stale cursor.
;
; Until commit, parent's source remains active for read_char and
; visible to all stack consumers. Tracebacks for errors during the
; reserved window report parent's location.
;
; OOM is checked here against (SS_PEND_P16 - frame_size), so the
; pending region is structurally protected from heap collision. On
; OOM the routine jumps to err_out_of_memory with no state to roll
; back (SS_PEND_P16 hasn't moved at the point of check).
;
; On entry: A             = curr_type for the new frame
;           SS_NAME       = new frame's name (null-terminated)
;           SS_SRC_TYPE / SS_CURR_LINE16 / SS_CURR_FILE / SS_MEM_PTR16
;                         = parent's state (consumed for prev_type and
;                           prev_line; prev_data deferred to commit)
;           SS_PAYLOAD_SIZE = trailing payload bytes to reserve
; On exit:  SS_PEND_P16   = pending frame base
;           SS_PAYLOAD_SIZE reset to 0
;           SS_P16 unchanged; SS_SRC_TYPE / SS_CURR_LINE16 /
;             SS_CURR_FILE / SS_MEM_PTR16 unchanged
;           A, Y clobbered. X preserved.
ss_reserve_frame:
  PHA                       ; Save curr_type across check / alloc
  ; OOM check: SS_TEMP16 = SS_PEND_P16 - frame_size = pending base.
  JSR check_source_frame_room
  ; Move SS_PEND_P16 to the pending base; write frame_size at offset 0.
  ; SS_P16 untouched. SS_TEMP16 still holds the pending base on return.
  JSR ss_alloc_pending_frame
  PLA                       ; A = curr_type
  ; Helper writes header (offsets 1..4) + name (offsets 7..) via
  ; SS_TEMP16 (= pending base). prev_data slot at offsets 5..6 is
  ; deliberately skipped.
  JSR ss_write_pending_header_and_name
  ; Reset payload size for the next caller (matches the atomic push
  ; routine's contract).
  LDA #$00
  STA SS_PAYLOAD_SIZE
  RTS


; Commit a pending frame:
;   1. Write prev_data at fixed offsets 5..6 of the pending frame,
;      using parent's CURRENT SS_CURR_FILE (file parent: 1 byte at 5;
;      offset 6 unused) or SS_MEM_PTR16 (memory parent: lo at 5, hi at
;      6). prev_type at offset 2 selects which.
;   2. Advance SS_P16 := SS_PEND_P16 (pending frame becomes committed
;      top).
;   3. Set SS_SRC_TYPE := the frame's curr_type byte at offset 1.
;   4. Reset SS_CURR_LINE16 := 0.
;
; Caller is still responsible for installing SS_MEM_PTR16 (memory
; frames -- new buffer pointer) or SS_CURR_FILE (file frames -- new
; handle), since the source-stack module doesn't know what those
; should be.
;
; A, Y clobbered. X preserved.
ss_commit_pending_frame:
  ; Read prev_type from the pending frame's offset 2.
  LDY #2
  LDA (SS_PEND_P16),Y
  BNE .commit_memory
  ; prev_type=0 (file): file handle at offset 5; offset 6 unused.
  LDY #5
  LDA SS_CURR_FILE
  STA (SS_PEND_P16),Y
  JMP .install_top
.commit_memory:
  ; prev_type=1 (memory): SS_MEM_PTR16 lo at offset 5, hi at offset 6.
  LDY #5
  LDA SS_MEM_PTR16
  STA (SS_PEND_P16),Y
  INY                       ; Y = 6
  LDA SS_MEM_PTR16 + 1
  STA (SS_PEND_P16),Y
.install_top:
  ; SS_P16 := SS_PEND_P16 (pending frame becomes committed top).
  CP16 SS_PEND_P16, SS_P16
  ; Set SS_SRC_TYPE from the frame's curr_type at offset 1.
  LDY #1
  LDA (SS_P16),Y
  STA SS_SRC_TYPE
  ; Reset line number for the new source.
  LDA #$00
  STA_LH16 SS_CURR_LINE16
  RTS


; Default memory pop handler: no-op. Host programs that don't need to
; restore any per-frame state (e.g. the source-stack component test
; program) equate MEMORY_POP_HANDLER to this label.
ss_pop_memory_noop:
  RTS

; Memory-frame pop dispatch is compile-time linked rather than
; runtime-patched: the host program defines MEMORY_POP_HANDLER as an
; equate before including this file. The assembler equates it to
; pop_label_scope_from_frame (label_scope.asm); the source-stack test
; program equates it to ss_pop_memory_noop above. pop_source's
; memory-pop branch becomes a direct JSR to that address -- no table,
; no indirect-jump thunk, no install routine. Same code path on every
; build, just a different jump target.


; On exit Z is set if source stack empty, clear otherwise
source_stack_empty:
  CMPI16 SS_P16, SOURCE_STACK
  RTS


; INTERNAL helper -- callers should use push_file_source or
; push_memory_source_reserve_payload rather than calling this directly.
; Those two routines own the calling-convention details (saving X,
; opening the file, ordering of SS_MEM_PTR16 updates, etc.).
;
; Builds a stack frame for a new source. Frame size is name_len + 8 +
; payload (fixed-size prev_data slot regardless of parent type). On
; exit installs the new frame's curr_type as SS_SRC_TYPE and resets
; SS_PAYLOAD_SIZE to 0, so callers don't need to do that themselves.
;
; PRECONDITION: caller has called check_source_frame_room, which leaves
; the proposed new SS_P16 in SS_TEMP16 and verified the OOM check. That
; result is consumed here; together the pair calculates the frame size
; exactly once. Because the OOM check has already passed, this routine
; has no failure path -- it never jumps to err_out_of_memory -- so it's
; safe to call after acquiring resources (e.g. a freshly-opened file
; handle) that would otherwise need cleanup on OOM.
;
; On entry: A          = curr_type (0=file, 1=memory) for the new frame
;           SS_TEMP16  = proposed new SS_P16 (from check_source_frame_room)
;           SS_NAME    = source name (null-terminated)
;           SS_SRC_TYPE = parent's source type (becomes prev_type)
;           SS_CURR_FILE / SS_MEM_PTR16 = parent's read state, captured
;                        into prev_data. SS_MEM_PTR16 must still hold
;                        the parent's value when prev_type=memory.
; On exit:  Frame written with curr_type, prev_type, prev_line,
;           prev_data, name; SS_P16 advanced past it.
;           SS_SRC_TYPE = new frame's curr_type.
;           SS_CURR_LINE16 reset to 0.
;           SS_PAYLOAD_SIZE reset to 0.
;           A, Y clobbered. X preserved.
push_source_frame:
  PHA                   ; Save curr_type across ss_alloc_frame
  ; Allocate the frame and write its size byte at offset 0. Pure stack
  ; mechanics live in ss_alloc_frame; everything below is layout.
  JSR ss_alloc_frame    ; SS_P16 advanced; (SS_P16),0 = frame_size; Y = 0
  PLA                   ; A = curr_type
  ; Header (offsets 1..4) + name (offsets 7..) live in the helper;
  ; prev_data at offsets 5..6 is filled in below from parent's current
  ; state. The helper preserves A; we reuse it after as the new
  ; SS_SRC_TYPE value below.
  PHA                   ; Save curr_type across the helper (which
                        ; clobbers A)
  JSR ss_write_pending_header_and_name
  ; prev_data at offsets 5..6. prev_type selects 1 vs 2 bytes;
  ; offset 6 is unused (left undefined) for file parents.
  LDA SS_SRC_TYPE
  BNE .save_memory_state
  ; prev_type=0 (file): handle at offset 5; offset 6 unused.
  LDY #5
  LDA SS_CURR_FILE
  STA (SS_P16),Y
  JMP .install_src_type
.save_memory_state:
  ; prev_type=1 (memory): SS_MEM_PTR16 lo at offset 5, hi at offset 6.
  LDY #5
  LDA SS_MEM_PTR16
  STA (SS_P16),Y
  INY                   ; Y = 6
  LDA SS_MEM_PTR16 + 1
  STA (SS_P16),Y
.install_src_type:
  ; Install new frame's curr_type as the active SS_SRC_TYPE. Saves
  ; the wrappers from doing this themselves.
  PLA                   ; A = curr_type
  STA SS_SRC_TYPE
  ; SS_PAYLOAD_SIZE bytes of payload trail the name; the frame_size
  ; byte at offset 0 already accounts for them. Bytes are reserved
  ; but not initialized here -- push_memory_source_reserve_payload's
  ; caller pre-writes them at (SS_P16 - SS_PAYLOAD_SIZE) before the push,
  ; so they are already in place by the time SS_P16 advances over them.
  ; Reset SS_PAYLOAD_SIZE so the next plain push starts from a clean
  ; slate (matches ss_reserve_frame's contract).
  LDA #$00
  STA SS_PAYLOAD_SIZE
  ; Reset line number for new source.
  STA_LH16 SS_CURR_LINE16
  RTS


; INTERNAL helper. Writes the layout fields that are identical between
; an atomic push and a deferred (reserve) push: the fixed header at
; offsets 1..4 (curr_type, prev_type, prev_line lo/hi) plus the name
; (and null terminator) at offsets 7..(7+name_len). Skips the
; prev_data slot at offsets 5..6 -- the caller is responsible for
; those, either inline (atomic push captures parent state immediately)
; or deferred to commit (reserve, where parent's read cursor still
; advances during arg parsing).
;
; PRECONDITION: SS_TEMP16 holds the frame's base address and offset 0
; (frame_size) has already been written. For atomic pushes that's the
; state ss_alloc_frame leaves behind (SS_TEMP16 still equals SS_P16
; from the check_source_frame_room call). For reserves the same is
; true after ss_alloc_pending_frame (SS_TEMP16 equals SS_PEND_P16).
;
; On entry: A             = curr_type for the new frame
;           SS_TEMP16     = frame base
;           SS_NAME       = source name (null-terminated)
;           SS_SRC_TYPE   = parent's source type (becomes prev_type)
;           SS_CURR_LINE16 = parent's line number (becomes prev_line)
; On exit:  SS_TEMP16 has been advanced by 7 (no longer the frame
;           base; callers that depend on the frame base after this
;           routine should restore it themselves).
;           Y = name_len (the index at which the null terminator was
;           copied). A clobbered. X preserved.
ss_write_pending_header_and_name:
  LDY #1                ; curr_type offset
  STA (SS_TEMP16),Y
  INY                   ; Y = 2 (prev_type)
  LDA SS_SRC_TYPE
  STA (SS_TEMP16),Y
  INY                   ; Y = 3 (prev_line low)
  LDA SS_CURR_LINE16
  STA (SS_TEMP16),Y
  INY                   ; Y = 4 (prev_line high)
  LDA SS_CURR_LINE16 + 1
  STA (SS_TEMP16),Y
  ; Advance SS_TEMP16 by 7 so the name-copy loop below can use Y as a
  ; direct SS_NAME index (SS_NAME[i] lands at frame_base + 7 + i =
  ; (SS_TEMP16 after add) + i). Lets the loop avoid X entirely, so the
  ; helper preserves X for callers. SS_TEMP16 is no longer needed as
  ; the frame base by the time we return.
  CLC
  LDA SS_TEMP16
  ADC #7
  STA SS_TEMP16
  BCC .copy_init
  INC SS_TEMP16 + 1
.copy_init:
  LDY #$FF
.copy_loop:
  INY
  LDA SS_NAME,Y
  STA (SS_TEMP16),Y
  BNE .copy_loop
  RTS


; Push a file source onto the stack
; On entry: SS_NAME contains the file name to open
;           SS_CURR_LINE16 contains the current line number
;           SS_CURR_FILE contains the current file handle
; On exit: X is preserved, new file is open and ready to read
;
; Order of operations is: pre-check OOM, then open the file, then push
; the frame. Each error exits with no resources to clean up: OOM happens
; before open so no file is leaked; file-not-found happens before push
; so no orphan frame is left behind.
push_file_source:
  TXA
  PHA                   ; Save X
  ; Pre-check: confirm the new frame will fit before we open the file,
  ; so an OOM here can't leak a freshly-opened handle.
  JSR check_source_frame_room
  ; Open file
  LDA #<SS_NAME
  LDX #>SS_NAME
  JSR open
  CMP #0
  BNE .file_ok
  JMP err_file_not_found
.file_ok:
  PHA                   ; Stash new handle on the 6502 stack across the
                        ; push (push_source_frame can't fail now).
  LDA #SS_SRC_TYPE_FILE
  JSR push_source_frame ; installs SS_SRC_TYPE := FILE for us
  PLA
  STA SS_CURR_FILE      ; Install new file handle
  PLA
  TAX                   ; Restore X
  RTS


; Push a memory source carrying a trailing payload region whose bytes
; are RESERVED only -- the source stack does not copy any data into
; them. The caller is expected to have written the payload contents
; into (SS_P16 - SS_PAYLOAD_SIZE) BEFORE calling, since the push
; advances SS_P16 over those bytes and they become the new frame's
; payload region in place. expand_macro uses this to parse argument
; expressions one at a time and write each parsed slot straight into
; the soon-to-be-frame, avoiding a staging buffer entirely.
;
; On entry: SS_NAME       = name for this memory source
;           SS_MEM_PTR16  = parent's read position. Saved into the new
;                           frame as prev_data when prev_type=memory.
;                           Do NOT preload this with the new buffer
;                           pointer -- that overwrites the value
;                           push_source_frame is about to copy into the
;                           parent's prev_data slot, which silently
;                           breaks memory-above-memory pop. The new
;                           buffer pointer must be installed by the
;                           caller AFTER this routine returns.
;           A             = payload size (0..N) to reserve. 0 is fine
;                           too -- the test program calls this from
;                           setup_memory_source with A=0 to push a
;                           plain (payload-less) memory frame.
; On exit:  X preserved. SS_SRC_TYPE = MEMORY. SS_PAYLOAD_SIZE reset
;           to 0. Caller must assign the new buffer pointer to
;           SS_MEM_PTR16; reads will then proceed from the new buffer.
push_memory_source_reserve_payload:
  STA SS_PAYLOAD_SIZE
  JSR check_source_frame_room
  LDA #SS_SRC_TYPE_MEMORY
  JMP push_source_frame ; tail call; both check_source_frame_room
                        ; and push_source_frame preserve X, and
                        ; push_source_frame installs SS_SRC_TYPE :=
                        ; MEMORY and resets SS_PAYLOAD_SIZE := 0 for
                        ; us


; Unified pop function -- handles both file and memory sources. File
; pops are inline (close the current handle if any); memory pops jump
; to MEMORY_POP_HANDLER, a compile-time equate the host program
; supplies. The assembler points it at pop_label_scope_from_frame; the
; test program points it at ss_pop_memory_noop.
;
; On entry: top frame's curr_type at offset 1 selects the path.
; On exit:  Previous state restored (SS_CURR_FILE or SS_MEM_PTR16);
;           SS_SRC_TYPE restored to prev_type; SS_CURR_LINE16
;           restored to prev_line. X preserved by external contract
;           (read_char's X preservation flows through here).
pop_source:
  ; All header fields (curr_type/prev_type/prev_line/prev_data) live at
  ; fixed offsets 1..6 -- no name scan anywhere on this path.
  TXA
  PHA                   ; Save X across both dispatch arms (close and
                        ; the memory handler may both clobber it).
  LDY #1                ; curr_type offset
  LDA (SS_P16),Y
  BEQ .pop_file
  ; Memory: direct call to the compile-time-linked handler.
  JSR MEMORY_POP_HANDLER
  JMP .dispatch_done
.pop_file:
  ; Inline file pop: close the current handle if open. close itself
  ; preserves X but we already saved it above to keep the two arms
  ; symmetric.
  LDA SS_CURR_FILE
  BEQ .dispatch_done
  JSR close
.dispatch_done:
  PLA
  TAX
  ; Read prev_type at offset 2. Y is unspecified after the dispatch
  ; (the handler may have clobbered it); reload explicitly.
  LDY #2
  LDA (SS_P16),Y
  STA SS_SRC_TYPE       ; Restore source type
  PHA                   ; Save for the prev_data branch below
  ; Read prev_line at offsets 3..4.
  INY
  LDA (SS_P16),Y
  STA SS_CURR_LINE16
  INY
  LDA (SS_P16),Y
  STA SS_CURR_LINE16 + 1
  ; prev_data at fixed offset 5 (and offset 6 for memory parents).
  INY                   ; Y = 5
  PLA
  BNE .restore_memory
  ; prev_type=0: restore file handle (offset 5; offset 6 unused).
  LDA (SS_P16),Y
  STA SS_CURR_FILE
  JMP ss_free_frame     ; Tail call: deallocate via offset-0 frame_size
.restore_memory:
  ; prev_type=1: restore memory pointer lo/hi at offsets 5..6.
  LDA (SS_P16),Y
  STA SS_MEM_PTR16
  INY
  LDA (SS_P16),Y
  STA SS_MEM_PTR16 + 1
  JMP ss_free_frame     ; Tail call: deallocate via offset-0 frame_size

; Read character from current source (file or memory)
; On exit: A = character (also stored in SS_CURR_CHAR)
;          C = 0 if char read, C = 1 if all sources exhausted
;          X is preserved
;          Y is not preserved
source_stack_read_char:
  LDA SS_SRC_TYPE
  BNE .read_memory
  ; Type 0 = file source
  LDA SS_CURR_FILE
  .ifdef enable_debug 
  BEQ .no_source
  .endif
  JSR read
  BCS .source_exhausted
  ; Got character
  STA SS_CURR_CHAR
  ; Carry is clear
  RTS
.read_memory:
  ; Type 1 = memory source (zero-terminated)
  ; Read byte from memory pointer
  LDY #0
  LDA (SS_MEM_PTR16),Y
  BEQ .source_exhausted     ; $00 = end of memory source
  ; Increment memory pointer
  INC16 SS_MEM_PTR16     ; Preserves A
  STA SS_CURR_CHAR
  CLC
  RTS
.source_exhausted:
  ; Source exhausted - pop and try previous source
  JSR pop_source
  ; Check if stack is empty
  JSR source_stack_empty
  ; Continue reading from previous source
  BNE source_stack_read_char
.all_done:
  SEC
  RTS
  .ifdef enable_debug
.no_source:
  JMP SS_ERR_NO_FILE
  .endif
