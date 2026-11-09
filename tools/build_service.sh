#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Added in this fork (2026-11-09); not part of JustAnotherPU/ridetube.
# Packs dist/<tool>@<version>.tgz with the MGU Store's own packer (deploy/hu artifact), as native/*/build.sh does,
# without Docker or a Python 3.12: ytdec (the C++ decoder, built in Docker) and ytdlp.pyz (the pinned yt-dlp,
# precompiled for 3.12) are taken from a published RideTube service package and checked against that package's
# own sha256 list; every other file comes from this checkout (line ends made LF).
#
#   MGU_STORE=<a clone of the MGU Store> tools/build_service.sh <base.tgz> [tool dir, default native/mdq-ridetube-d]
#
# base.tgz: JustAnotherPU's jap-ridetube-d@0.3.8.tgz (its ytdec and ytdlp.pyz are the ones this fork ships).
# SOURCE_DATE_EPOCH: the last commit's time, as build.sh.
set -eu
: "${MGU_STORE:?set MGU_STORE to a clone of github.com/robertnisipeanu/mgu-store}"
base=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
root=$(cd "$(dirname "$0")/.." && pwd)
tool=${2:-native/mdq-ridetube-d}
SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-$(git -C "$root" log -1 --format=%ct 2>/dev/null || echo 0)}
export SOURCE_DATE_EPOCH

stage=$(mktemp -d "${TMPDIR:-/tmp}/svc.XXXXXX")
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/$tool"
cp "$root/LICENSE" "$root/THIRD_PARTY_LICENSES" "$stage/"
(cd "$root/$tool" && tar --exclude=./build --exclude=./dist --exclude=./test -cf - .) | tar -xf - -C "$stage/$tool"
# a Windows checkout's CRLF: the car runs these as they are
find "$stage" -type f \( -name '*.js' -o -name '*.py' -o -name '*.sh' -o -name '*.json' -o -name '*.service' \
    -o -name 'LICENSE*' -o -name 'THIRD_PARTY_LICENSES' -o -name '*.md' -o -name 'VERSION' \) -exec sed -i 's/\r$//' {} +

# ytdec and ytdlp.pyz from the base, as its component.json lists them
mkdir -p "$stage/base" "$stage/$tool/build"
tar -xzf "$base" -C "$stage/base" component.json files/ytdec files/ytdlp.pyz
for f in ytdec ytdlp.pyz; do
    want=$(python3 -c "import json,sys; print([x['sha256'] for x in json.load(open(sys.argv[1]))['files'] if x['path'] == sys.argv[2]][0])" \
        "$stage/base/component.json" "$f")
    got=$(sha256sum "$stage/base/files/$f" | cut -d' ' -f1)
    [ "$want" = "$got" ] || { echo "build_service.sh: $f does not match the base's sha256" >&2; exit 1; }
    cp "$stage/base/files/$f" "$stage/$tool/build/$f"
done
chmod 0755 "$stage/$tool/build/ytdec"
mkdir -p "$root/dist"
node "$MGU_STORE/deploy/hu" artifact "$stage/$tool" --out "$root/dist"
