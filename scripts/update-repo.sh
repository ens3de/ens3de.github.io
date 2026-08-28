#!/bin/sh
set -eu

# Regenerate the Selio/APT metadata for this repository.
# Run from any directory: ./scripts/update-repo.sh
# The repository intentionally publishes only Packages. This avoids stale
# GitHub Pages cache problems with Packages.gz and keeps Release deterministic.

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR="$SCRIPT_DIR/../repo"
REPO_DIR=$(CDPATH= cd -- "$REPO_DIR" && pwd)

md5_file() {
    if command -v md5 >/dev/null 2>&1; then
        md5 -q "$1"
    else
        md5sum "$1" | awk '{print $1}'
    fi
}

sha256_file() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        sha256sum "$1" | awk '{print $1}'
    fi
}

PACKAGE_INDEX="$REPO_DIR/Packages"
RELEASE_FILE="$REPO_DIR/Release"
TMP_PACKAGES=$(mktemp "${TMPDIR:-/tmp}/ens3-packages.XXXXXX")
TMP_RELEASE=$(mktemp "${TMPDIR:-/tmp}/ens3-release.XXXXXX")
trap 'rm -f "$TMP_PACKAGES" "$TMP_RELEASE"' EXIT INT TERM

if command -v dpkg-scanpackages >/dev/null 2>&1; then
    (
        cd "$REPO_DIR"
        dpkg-scanpackages -m . /dev/null > "$TMP_PACKAGES"
    )
elif command -v python3 >/dev/null 2>&1; then
    python3 "$SCRIPT_DIR/scan-packages.py" "$REPO_DIR" > "$TMP_PACKAGES"
else
    echo "error: dpkg-scanpackages or python3 is required" >&2
    exit 1
fi
mv "$TMP_PACKAGES" "$PACKAGE_INDEX"

# Never leave an old compressed index behind. Release contains only Packages.
rm -f "$REPO_DIR/Packages.gz"

PACKAGE_SIZE=$(wc -c < "$PACKAGE_INDEX" | tr -d ' ')
PACKAGE_MD5=$(md5_file "$PACKAGE_INDEX")
PACKAGE_SHA256=$(sha256_file "$PACKAGE_INDEX")

{
    printf '%s\n' 'Origin: ens3 repo'
    printf '%s\n' 'Label: ens3 repo'
    printf '%s\n' 'Suite: stable'
    printf '%s\n' 'Version: 1.0'
    printf '%s\n' 'Codename: ios'
    printf '%s\n' 'Architectures: iphoneos-arm iphoneos-arm64 iphoneos-arm64e'
    printf '%s\n' 'Components: main'
    printf '%s\n' 'Description: ens3 repo'
    printf '%s\n' 'MD5Sum:'
    printf ' %s %s Packages\n' "$PACKAGE_MD5" "$PACKAGE_SIZE"
    printf '%s\n' 'SHA256:'
    printf ' %s %s Packages\n' "$PACKAGE_SHA256" "$PACKAGE_SIZE"
} > "$TMP_RELEASE"
mv "$TMP_RELEASE" "$RELEASE_FILE"

echo "Generated $PACKAGE_INDEX"
echo "Generated $RELEASE_FILE"
echo "Packages size: $PACKAGE_SIZE bytes"
echo "Packages MD5: $PACKAGE_MD5"
echo "Packages SHA256: $PACKAGE_SHA256"
