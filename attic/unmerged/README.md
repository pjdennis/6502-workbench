# unmerged: branch work that was never merged

`git format-patch` exports of commits that exist only on branches that were not merged, so they can be read in the tree. The branches themselves are kept as `archive/<branch>` tags (`archive/asm-unified-parsing`, `archive/claude/install-hexdump-5CahY`). Patches touch old paths (`assembler2/...`, stage `23`), so they will not apply to the current tree as they are. See the README in each directory.
