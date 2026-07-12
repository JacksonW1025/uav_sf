#!/usr/bin/env python3
"""Check repository-local inline Markdown links without network access."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote


LINK = re.compile(r"(?<!!)\[[^\]]*\]\((?P<target><[^>]+>|[^)\s]+)(?:\s+['\"][^'\"]*['\"])?\)")


def tracked_markdown(repo: Path) -> list[Path]:
    proc = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z", "*.md"],
        check=True,
        capture_output=True,
    )
    return [repo / item.decode("utf-8", errors="surrogateescape") for item in proc.stdout.split(b"\0") if item]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    repo = args.repo.resolve()
    failures: list[str] = []
    checked = 0
    for markdown in tracked_markdown(repo):
        text = markdown.read_text(encoding="utf-8", errors="replace")
        for match in LINK.finditer(text):
            target = match.group("target").strip("<>")
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = unquote(target.split("#", 1)[0])
            if not target:
                continue
            checked += 1
            candidate = Path(target)
            if not candidate.is_absolute():
                candidate = markdown.parent / candidate
            if not candidate.exists():
                line = text.count("\n", 0, match.start()) + 1
                failures.append(f"{markdown.relative_to(repo)}:{line}: {target}")
    print(f"checked_local_links={checked} broken_local_links={len(failures)}")
    for failure in failures:
        print(failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
