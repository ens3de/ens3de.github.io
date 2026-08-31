#!/usr/bin/env python3
"""Validate a flat rootless repository and rebuild Packages and Release."""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]+$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
ARCHITECTURE = "iphoneos-arm64"


def control_fields(package: pathlib.Path) -> dict[str, str]:
    output = subprocess.check_output(
        ["dpkg-deb", "-f", str(package)], text=True, stderr=subprocess.STDOUT
    )
    fields: dict[str, str] = {}
    current: str | None = None
    for line in output.splitlines():
        if line.startswith((" ", "\t")) and current:
            fields[current] += "\n" + line
            continue
        if ":" not in line:
            raise ValueError(f"invalid control line: {line}")
        current, value = line.split(":", 1)
        fields[current] = value.lstrip()
    return fields


def version_key(version: str) -> tuple[int, int, int]:
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"non-stable version is not publishable: {version}")
    return tuple(int(part) for part in version.split("."))


def digest(path: pathlib.Path, algorithm: str) -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def atomic_write(path: pathlib.Path, content: str) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(content)
        os.replace(temporary, path)
    except BaseException:
        pathlib.Path(temporary).unlink(missing_ok=True)
        raise


def parse_index(content: str) -> list[dict[str, str]]:
    paragraphs: list[dict[str, str]] = []
    for raw_paragraph in content.strip().split("\n\n"):
        if not raw_paragraph:
            continue
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
        paragraphs.append(fields)
    return paragraphs


def validate_index(content: str, repo: pathlib.Path, expected: set[pathlib.Path]) -> None:
    paragraphs = parse_index(content)
    if len(paragraphs) != len(expected):
        raise ValueError(
            f"Packages contains {len(paragraphs)} entries; expected {len(expected)}"
        )
    indexed: set[pathlib.Path] = set()
    for fields in paragraphs:
        missing = [
            field
            for field in ("Package", "Version", "Architecture", "Filename", "Size", "SHA256")
            if not fields.get(field)
        ]
        if missing:
            raise ValueError(f"Packages entry missing fields: {', '.join(missing)}")
        filename = fields["Filename"]
        if pathlib.PurePosixPath(filename).name != filename:
            raise ValueError(f"non-canonical Filename in Packages: {filename}")
        package = (repo / filename).resolve()
        if package.parent != repo or package not in expected:
            raise ValueError(f"unexpected Filename in Packages: {filename}")
        if package in indexed:
            raise ValueError(f"duplicate Filename in Packages: {filename}")
        indexed.add(package)
        control = control_fields(package)
        for field in ("Package", "Version", "Architecture"):
            if fields[field] != control[field]:
                raise ValueError(f"{field} mismatch for {filename}")
        if fields["Size"] != str(package.stat().st_size):
            raise ValueError(f"Size mismatch for {filename}")
        if fields["SHA256"] != digest(package, "sha256"):
            raise ValueError(f"SHA256 mismatch for {filename}")
    if indexed != expected:
        raise ValueError("Packages does not reference the complete package set")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: rebuild-repo.py REPO_DIR")
    repo = pathlib.Path(sys.argv[1]).resolve()
    packages = sorted(repo.glob("*.deb"))
    if not packages:
        raise SystemExit("error: repository contains no deb packages")

    latest: dict[str, tuple[tuple[int, int, int], pathlib.Path]] = {}
    seen: set[tuple[str, str]] = set()
    for package in packages:
        try:
            fields = control_fields(package)
        except (OSError, subprocess.CalledProcessError, ValueError) as error:
            raise SystemExit(f"error: could not inspect {package.name}: {error}") from error
        missing = [
            field
            for field in ("Package", "Version", "Architecture", "Maintainer", "Description")
            if not fields.get(field)
        ]
        if missing:
            raise SystemExit(f"error: {package.name} missing fields: {', '.join(missing)}")
        package_id = fields["Package"]
        version = fields["Version"]
        architecture = fields["Architecture"]
        if not PACKAGE_RE.fullmatch(package_id):
            raise SystemExit(f"error: invalid Package in {package.name}: {package_id}")
        if architecture != ARCHITECTURE:
            raise SystemExit(f"error: unsupported Architecture in {package.name}: {architecture}")
        try:
            key = version_key(version)
        except ValueError as error:
            raise SystemExit(f"error: {package.name}: {error}") from error
        expected = f"{package_id}_{version}_{architecture}.deb"
        if package.name != expected:
            raise SystemExit(f"error: expected filename {expected}, got {package.name}")
        identity = (package_id, version)
        if identity in seen:
            raise SystemExit(f"error: duplicate package version: {package_id} {version}")
        seen.add(identity)
        if package_id not in latest or key > latest[package_id][0]:
            latest[package_id] = (key, package)

    keep = {entry[1] for entry in latest.values()}
    for package in packages:
        if package not in keep:
            print(f"Removing superseded package: {package.name}")
            package.unlink()

    scan = subprocess.run(
        ["dpkg-scanpackages", ".", "/dev/null"],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    scan = scan.replace("Filename: ./", "Filename: ")
    if not scan.endswith("\n"):
        scan += "\n"
    try:
        validate_index(scan, repo, keep)
    except ValueError as error:
        raise SystemExit(f"error: generated Packages failed validation: {error}") from error
    atomic_write(repo / "Packages", scan)
    (repo / "Packages.gz").unlink(missing_ok=True)

    index = repo / "Packages"
    size = index.stat().st_size
    date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    release = "\n".join(
        [
            "Origin: ens3 repo",
            "Label: ens3 repo",
            "Suite: stable",
            "Version: 1.0",
            "Codename: ios",
            f"Date: {date}",
            f"Architectures: {ARCHITECTURE}",
            "Components: main",
            "Description: ens3 rootless package repository",
            "MD5Sum:",
            f" {digest(index, 'md5')} {size} Packages",
            "SHA256:",
            f" {digest(index, 'sha256')} {size} Packages",
            "",
        ]
    )
    atomic_write(repo / "Release", release)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
