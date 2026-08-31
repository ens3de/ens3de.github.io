#!/usr/bin/env python3
"""Verify published Packages, Release, and deb files over HTTP."""

from __future__ import annotations

import hashlib
import pathlib
import re
import sys
import urllib.parse
import urllib.request

FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._~-]*\.deb$")


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "ens3-repo-verifier/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}: {url}")
        return response.read()


def parse_paragraphs(content: str) -> list[dict[str, str]]:
    paragraphs: list[dict[str, str]] = []
    for raw_paragraph in content.strip().split("\n\n"):
        fields: dict[str, str] = {}
        current: str | None = None
        for line in raw_paragraph.splitlines():
            if line.startswith((" ", "\t")) and current:
                fields[current] += "\n" + line
                continue
            if ":" not in line:
                raise ValueError(f"invalid Packages line: {line}")
            current, value = line.split(":", 1)
            fields[current] = value.lstrip()
        if fields:
            paragraphs.append(fields)
    return paragraphs


def release_sha256(content: str) -> tuple[str, int]:
    in_sha256 = False
    for line in content.splitlines():
        if line == "SHA256:":
            in_sha256 = True
            continue
        if in_sha256 and not line.startswith(" "):
            break
        if in_sha256:
            parts = line.split()
            if len(parts) == 3 and parts[2] == "Packages":
                return parts[0], int(parts[1])
    raise ValueError("Release does not contain a SHA256 entry for Packages")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify-published-repo.py BASE_URL")
    repo_url = sys.argv[1].rstrip("/") + "/repo/"
    packages_data = download(urllib.parse.urljoin(repo_url, "Packages"))
    release_data = download(urllib.parse.urljoin(repo_url, "Release"))
    expected_hash, expected_size = release_sha256(release_data.decode("utf-8"))
    if len(packages_data) != expected_size:
        raise SystemExit("error: public Packages size does not match Release")
    if hashlib.sha256(packages_data).hexdigest() != expected_hash:
        raise SystemExit("error: public Packages SHA256 does not match Release")

    entries = parse_paragraphs(packages_data.decode("utf-8"))
    if not entries:
        raise SystemExit("error: public Packages contains no entries")
    seen: set[str] = set()
    for fields in entries:
        missing = [field for field in ("Filename", "Size", "SHA256") if not fields.get(field)]
        if missing:
            raise SystemExit(f"error: Packages entry missing fields: {', '.join(missing)}")
        filename = fields["Filename"]
        if not FILENAME_RE.fullmatch(filename) or pathlib.PurePosixPath(filename).name != filename:
            raise SystemExit(f"error: unsafe Filename: {filename}")
        if filename in seen:
            raise SystemExit(f"error: duplicate Filename: {filename}")
        seen.add(filename)
        package_data = download(urllib.parse.urljoin(repo_url, urllib.parse.quote(filename)))
        if len(package_data) != int(fields["Size"]):
            raise SystemExit(f"error: public deb size mismatch: {filename}")
        if hashlib.sha256(package_data).hexdigest() != fields["SHA256"]:
            raise SystemExit(f"error: public deb SHA256 mismatch: {filename}")
    print(f"Verified {len(entries)} public packages at {repo_url}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        raise SystemExit(f"error: public repository verification failed: {error}") from error
