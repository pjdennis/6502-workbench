# asm/docs

Design notes and plans from the development of stage 17. They are design records: the narrative is kept even after the work is done, so line numbers and memory maps inside them may be out of date. The current layout is in [`../17/README`](../17/README).

| File | Status |
|---|---|
| [`source_stack_unification_plan.md`](source_stack_unification_plan.md) | Done. Merged the scope stack into the source stack and moved macro parameters into activation frames. |
| [`macro_frame_reservation_plan.md`](macro_frame_reservation_plan.md) | Done. `ss_reserve_frame` / `ss_commit_pending_frame`. |
| [`macro_param_lookup_caching_plan.md`](macro_param_lookup_caching_plan.md) | Done. `MACRO_LOOKUP_SLOTS16` / `MACRO_LOOKUP_PARAMS16`. |
| [`macro_local_design_notes.md`](macro_local_design_notes.md) | Deferred, not started. Pre-scan design for macro-local labels. |
| [`TODOS`](TODOS) | Open and done items for the assembler; `[X]` marks done. |
