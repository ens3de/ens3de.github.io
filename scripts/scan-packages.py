#!/usr/bin/env python3
"""Generate a flat Debian Packages index without dpkg-scanpackages."""

import hashlib
import io
import pathlib
import subprocess
import sys
import tarfile


def read_control(package_path):
    members = subprocess.check_output(["ar", "t", str(package_path)], text=True).splitlines()
    control_member = next((name for name in members if name.startswith("control.tar")), None)
    if not control_member:
        raise RuntimeError("control archive is missing")
    archive = subprocess.check_output(["ar", "p", str(package_path), control_member])
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as control_tar:
        member = next(
            (item for item in control_tar.getmembers() if item.name.lstrip("./") == "control"),
            None,
        )
        if not member:
            raise RuntimeError("control file is missing")
        extracted = control_tar.extractfile(member)
        if not extracted:
            raise RuntimeError("control file could not be read")
        return extracted.read().decode("utf-8").strip()


def parse_fields(control):
    fields = {}
    order = []
    current = None
    for line in control.splitlines():
        if line.startswith((" ", "\t")) and current:
            fields[current] += "\n" + line
            continue
        if ":" not in line:
            raise ValueError(f"invalid control line: {line}")
        current = line.split(":", 1)[0]
        fields[current] = line
        order.append(current)
    return fields, order


def digest(package_path, algorithm):
    value = hashlib.new(algorithm)
    with package_path.open("rb") as package_file:
        for chunk in iter(lambda: package_file.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: scan-packages.py REPO_DIR")
    repo_dir = pathlib.Path(sys.argv[1]).resolve()
    packages = sorted(repo_dir.glob("*.deb"), key=lambda path: path.name)
    paragraphs = []
    for package_path in packages:
        try:
            control = read_control(package_path)
        except Exception as error:
            raise SystemExit(f"error: could not inspect {package_path.name}: {error}")
        fields, original_order = parse_fields(control)
        required = ("Package", "Version", "Architecture")
        if not all(field in fields for field in required):
            raise SystemExit(f"error: required control field missing in {package_path.name}")
        front_order = (
            "Package", "Version", "Architecture", "Maintainer", "Installed-Size",
            "Depends", "Pre-Depends", "Conflicts", "Breaks", "Replaces", "Provides",
            "Recommends", "Suggests", "Enhances",
        )
        tail_order = ("Section", "Priority", "Description", "Homepage", "Author", "Name")
        emitted = set()
        metadata = []
        for field in front_order:
            if field in fields:
                metadata.append(fields[field])
                emitted.add(field)
        metadata.extend([
            f"Filename: ./{package_path.name}",
            f"Size: {package_path.stat().st_size}",
            f"MD5sum: {digest(package_path, 'md5')}",
            f"SHA1: {digest(package_path, 'sha1')}",
            f"SHA256: {digest(package_path, 'sha256')}",
        ])
        for field in original_order:
            if field not in emitted and field not in tail_order:
                metadata.append(fields[field])
                emitted.add(field)
        for field in tail_order:
            if field in fields and field not in emitted:
                metadata.append(fields[field])
                emitted.add(field)
        paragraphs.append("\n".join(metadata))
    if paragraphs:
        sys.stdout.write("\n\n".join(paragraphs) + "\n\n")


if __name__ == "__main__":
    main()
