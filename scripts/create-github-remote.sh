#!/usr/bin/env bash
# Create the GitHub repository for this project and push every branch and tag to it.
#
#   gh auth login                       # once, interactive
#   bash scripts/create-github-remote.sh [name] [--public]
#
# Historical bootstrap script: it created the first (private) remote of this project. Private by
# default, and it still refuses --public — the public repository is not created by this script but by
# the documented migration (docs/DELIVERY.md): a new repository with a clean history, because the old
# history carries identifiers that were only masked in the tree on 2026-09-12 (docs/AWS-TEARDOWN.md).
# infra/samconfig.toml itself has never been tracked (.gitignore).
set -euo pipefail

cd "$(dirname "$0")/.."

NAME="${1:-furniture-goren}"
VISIBILITY=--private
for a in "$@"; do [[ "$a" == "--public" ]] && VISIBILITY=--public; done

command -v gh >/dev/null || { echo "GitHub CLI not found. Install it (scoop install gh) and run: gh auth login"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "Not signed in. Run: gh auth login"; exit 1; }

if [[ "$VISIBILITY" == "--public" ]]; then
  echo "Refusing: a public repository is created by the migration in docs/DELIVERY.md, not by this script."
  echo "That procedure starts a new repository from a clean tree; this one would push the whole history."
  exit 1
fi

echo "Creating $NAME ($VISIBILITY) and pushing $(git rev-list --count HEAD) commits…"
gh repo create "$NAME" $VISIBILITY --source=. --remote=origin --description "ALUMA / GOREN — pre-launch enquiry landing page (Hebrew/English static site, AWS)" --push

git push origin --tags
echo
git remote -v
echo "Done. 'backup' still points at the local mirror in ~/git-remotes/furniture.git."
