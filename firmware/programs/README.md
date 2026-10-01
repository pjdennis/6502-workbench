# Programs

Assembly programs for the boards, grouped by the `base_config` they include. Assemble them with `firmware/vasm` (see [`../README.md`](../README.md)). Every one is in `firmware/manifest.txt`, which records the hash of each build, or `FAIL` for the 28 older programs that no longer assemble against the current libraries.

| Directory | Contents |
|---|---|
| [`wendy/`](wendy/README.md) | Wendy (v1) programs, 2020-21 |
| [`michael/`](michael/README.md) | Michael programs, including the graphic console and BBC BASIC |
| [`wendy2/`](wendy2/README.md) | Wendy 2 rev c programs and tests |
| [`common/`](common/README.md) | Board-independent experiments |
