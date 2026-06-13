#!/usr/bin/env bash
# install-git-hooks.sh — copy the repo's git hooks into this checkout.
#
# Git hooks are not cloned with the repo, so run this once per checkout:
#   bash scripts/install-git-hooks.sh
#
# Currently ships one hook:
#   post-commit — prints a loud /ntp-prompt-sync reminder when a commit
#                 touches files the build-prompt series describes.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$HERE")"
HOOKS_DST="$(cd "$REPO_ROOT" && git rev-parse --git-path hooks)"
case "$HOOKS_DST" in
    /*) : ;;
    *) HOOKS_DST="$REPO_ROOT/$HOOKS_DST" ;;
esac

for hook in "$HERE"/git-hooks/*; do
    name="$(basename "$hook")"
    cp "$hook" "$HOOKS_DST/$name"
    chmod +x "$HOOKS_DST/$name"
    echo "installed: $HOOKS_DST/$name"
done
