#!/usr/bin/env bash
# Downloads the benchmark's raw transcripts and working files (runs/ and work/ of every result folder) and puts them
# back in bench/results/. Only needed to re-read a run or rescore it; the summaries and analyses are in the repo.
#
#   bench/fetch-raw.sh
#
# The archive is attached to a GitHub release. Its SHA-256 is checked before anything is unpacked.
set -euo pipefail

NAME="deskstack-bench-raw-2026-11-09.tar.gz"
URL="${DS_RAW_URL:-https://github.com/joaquimmj/deskstack/releases/download/bench-raw-2026-11-09/$NAME}"
SHA256="${DS_RAW_SHA256:-4efd0c0e44d2af040cebee6a3dea6c80ad2cbb9adb2bea2b8f61826edb321fc5}"

# Where to unpack: the repository root (tests point DS_RAW_DEST at a temporary folder).
cd "${DS_RAW_DEST:-$(dirname "$0")/..}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
echo "Downloading $URL (about 20 MB)"
curl -fsSL -o "$tmp/$NAME" "$URL"
got="$( (command -v sha256sum >/dev/null && sha256sum "$tmp/$NAME" || shasum -a 256 "$tmp/$NAME") | cut -d' ' -f1)"
if [ "$got" != "$SHA256" ]; then
  echo "Checksum mismatch: expected $SHA256, got $got. Nothing was unpacked." >&2
  exit 1
fi
# Only paths under bench/results/, only runs/ or work/ folders, no ".." anywhere, and only files and folders
# (no links, devices or fifos).
if tar -tzf "$tmp/$NAME" | grep -vqE '^bench/results/([^/]+/)+(runs|work)(/|$)' \
  || tar -tzf "$tmp/$NAME" | grep -qE '(^|/)\.\.(/|$)' \
  || tar -tvzf "$tmp/$NAME" | grep -qvE '^[-d]'; then
  echo "The archive holds something other than files and folders under bench/results/*/runs|work. Nothing was unpacked." >&2
  exit 1
fi
tar -xzf "$tmp/$NAME"
echo "Done: raw runs restored under bench/results/."
