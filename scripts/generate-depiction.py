#!/usr/bin/env python3
"""Generate a minimal Sileo Native Depiction from a project's CHANGELOG."""

from __future__ import annotations

import json
import pathlib
import re
import sys


def changelog_section(path: pathlib.Path, version: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"(?ms)^##\s+\[?{re.escape(version)}\]?[^\n]*\n(.*?)(?=^##\s+|\Z)", text)
    if not match:
        raise SystemExit(f"changelog has no section for {version}")
    return match.group(1).strip()


def main() -> int:
    if len(sys.argv) != 5:
        raise SystemExit("usage: generate-depiction.py PACKAGE VERSION CHANGELOG OUTPUT")
    package, version, changelog, output = sys.argv[1:]
    body = changelog_section(pathlib.Path(changelog), version)
    depiction = {
        "minVersion": "0.4",
        "class": "DepictionTabView",
        "tabs": [
            {"class": "DepictionStackView", "tabname": "概览", "views": [
                {"class": "DepictionHeaderView", "title": package},
                {"class": "DepictionTableTextView", "title": "版本", "text": version},
            ]},
            {"class": "DepictionStackView", "tabname": "更新日志", "views": [
                {"class": "DepictionMarkdownView", "markdown": body},
            ]},
        ],
    }
    destination = pathlib.Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(depiction, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
