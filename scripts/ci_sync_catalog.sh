#!/usr/bin/env bash
# Only run in a disposable Actions checkout, never a contributor's working tree.
set -euo pipefail
if [[ "${GITHUB_ACTIONS:-}" != "true" ]]; then
  echo 'This script is only for a disposable GitHub Actions checkout.' >&2
  exit 1
fi
git diff --quiet
git diff --cached --quiet
for attempt in 1 2 3; do
  git fetch origin main
  git switch --detach origin/main
  python3 scripts/catalog.py build
  python3 scripts/catalog.py check
  python3 -m unittest discover -s tests -v
  git add -- README.md templates/README.md templates/catalog.json
  if git diff --cached --quiet; then
    exit 0
  fi
  git -c user.name='github-actions[bot]' -c user.email='41898282+github-actions[bot]@users.noreply.github.com' commit -m 'docs(catalog): keep template discovery in sync' -m 'Regenerate the indexes and README count from template profiles.'
  if git push origin HEAD:main; then
    exit 0
  fi
  # Another main push may have won; rebuild, never force or replay stale indexes.
done
echo 'Catalog update could not be pushed after three attempts.' >&2
exit 1
