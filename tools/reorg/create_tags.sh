#!/bin/bash
# Create and push the repository's annotated tags: the history milestones
# (milestones.txt) and the archive/<branch> tags recording every branch tip of
# the old 6502-experiments repository (archive-tips.txt).
#
#   tools/reorg/create_tags.sh            dry run: validate and print every step
#   tools/reorg/create_tags.sh --apply    create the tags and push them to origin
#
# Each line of a tag file is "<tag> <commit> <message>". Every commit is checked
# before anything is created; existing tags at the same commit are left alone.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
REMOTE=${REMOTE:-origin}
TAG_FILES=${TAG_FILES:-"$HERE/milestones.txt $HERE/archive-tips.txt"}
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

run() { echo "+ $*"; if [ "$APPLY" = 1 ]; then "$@"; fi; }
die() { echo "error: $*" >&2; exit 1; }

[ "$APPLY" = 1 ] || echo "DRY RUN: nothing will change. Re-run with --apply to create and push the tags."
git var GIT_COMMITTER_IDENT >/dev/null 2>&1 \
    || die "no git identity: set user.name and user.email (needed for annotated tags)"
git fetch -q "$REMOTE"

NAMES=(); COMMITS=(); MESSAGES=()
for file in $TAG_FILES; do
    while read -r name commit msg; do
        case "$name" in ''|'#'*) continue ;; esac
        git cat-file -e "$commit^{commit}" 2>/dev/null || die "tag $name: commit $commit not found (in $file)"
        NAMES+=("$name"); COMMITS+=("$commit"); MESSAGES+=("$msg")
    done < "$file"
done

REFS=()
for i in "${!NAMES[@]}"; do
    name=${NAMES[$i]} commit=${COMMITS[$i]}
    if existing=$(git rev-parse -q --verify "refs/tags/$name^{commit}"); then
        [ "$existing" = "$(git rev-parse "$commit^{commit}")" ] || die "tag $name already exists at another commit"
        echo "  (tag $name already exists)"
    else
        run git tag -a "$name" "$commit" -m "${MESSAGES[$i]}"
    fi
    REFS+=("refs/tags/$name")
done

run git push "$REMOTE" "${REFS[@]}"
[ "$APPLY" = 1 ] && echo "done: ${#REFS[@]} tags." || echo "DRY RUN complete: ${#REFS[@]} tags."
