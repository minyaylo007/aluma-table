"""Наступний номер версії SemVer vX.Y.Z (research.md R5, contracts/workflows.md «release.yml»).

    python3 scripts/next_version.py --tags "<теги через пробіл або рядки>" --labels "<мітки PR>"

Береться найбільший тег виду vX.Y.Z (решта ігнорується: v0.4.0-box, 0.9.0, v1.0); мітка злитого PR
`release:major` > `release:minor` > інакше patch. Без жодного тегу — v0.5.0. Друкує лише номер. Лише stdlib.
"""

from __future__ import annotations

import argparse
import re
import sys

FIRST = "v0.5.0"
_TAG = re.compile(r"^(?:refs/tags/)?v(\d+)\.(\d+)\.(\d+)(?:\^\{\})?$")


def parse(tag: str):
    m = _TAG.match(tag.strip())
    return tuple(int(x) for x in m.groups()) if m else None


def next_version(tags, labels) -> str:
    versions = [v for v in (parse(t) for t in tags) if v]
    if not versions:
        return FIRST
    major, minor, patch = max(versions)
    labels = {label.strip() for label in labels}
    if "release:major" in labels:
        return f"v{major + 1}.0.0"
    if "release:minor" in labels:
        return f"v{major}.{minor + 1}.0"
    return f"v{major}.{minor}.{patch + 1}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tags", default="", help="теги через пробіл, кому або з нового рядка")
    ap.add_argument("--labels", default="", help="мітки злитого PR через пробіл, кому або з нового рядка")
    args = ap.parse_args(argv)
    split = re.compile(r"[\s,]+")
    print(next_version([t for t in split.split(args.tags) if t], [x for x in split.split(args.labels) if x]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
