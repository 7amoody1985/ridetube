#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Added in this fork (2026-11-09); not part of JustAnotherPU/ridetube.
# Builds dist/<app>@<version>.tgz with the kit's own build (kit/tools/build.py) without BMW's oap-sdk:
# build.py only copies oap-sdk/{index.js,package.json} into node_modules/oap-sdk, and a published package leaves
# that folder out (the head unit generates it from a BMW app, MGU Store PUBLISHING.md), as tools/release.py does.
# So a placeholder stands in for the build and is stripped from the package. With a real ./oap-sdk, that is used.
#
#   tools/build_app.sh [app id, default mdq_ridetube]
#
# Runs on a copy of the checkout with LF line ends and 0644 files (a Windows checkout has CRLF and 0755).
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
app=${1:-mdq_ridetube}
stage=$(mktemp -d "${TMPDIR:-/tmp}/app.XXXXXX")
trap 'rm -rf "$stage"' EXIT
(cd "$root" && tar --exclude=./.git --exclude=./dist --exclude=./build -cf - .) | tar -xf - -C "$stage"
find "$stage" -type d -exec chmod 0755 {} +
find "$stage" -type f -exec chmod 0644 {} +
find "$stage" -type f \( -name '*.js' -o -name '*.py' -o -name '*.sh' -o -name '*.json' -o -name '*.txt' -o -name '*.md' \
    -o -name 'LICENSE*' -o -name 'THIRD_PARTY_LICENSES' -o -name '*.tsv' -o -name '*.svg' \) -exec sed -i 's/\r$//' {} +
if [ ! -f "$stage/oap-sdk/index.js" ]; then
    mkdir -p "$stage/oap-sdk"
    echo '// placeholder for kit/tools/build.py: stripped from the package' > "$stage/oap-sdk/index.js"
    echo '{"name":"oap-sdk","version":"0.0.0-placeholder"}' > "$stage/oap-sdk/package.json"
fi
(cd "$stage" && python3 kit/tools/build.py "$app")
ver=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" "$stage/apps/$app/app.json")
mkdir -p "$root/dist"
python3 - "$stage/dist/$app@$ver.tgz" "$root/dist/$app@$ver.tgz" "${SOURCE_DATE_EPOCH:-0}" <<'PY'
import gzip, io, sys, tarfile
src, dst, mtime = sys.argv[1], sys.argv[2], int(sys.argv[3])
with tarfile.open(src) as t:
    ms = [(m, t.extractfile(m).read() if m.isfile() else None) for m in t.getmembers()]
keep = sorted(((m, d) for m, d in ms if 'node_modules/oap-sdk' not in m.name), key=lambda x: x[0].name)
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode='w', format=tarfile.USTAR_FORMAT) as out:
    for m, d in keep:
        m.uid = m.gid = 0
        m.uname = m.gname = ''
        m.mtime = mtime
        out.addfile(m, io.BytesIO(d) if d is not None else None)
with open(dst, 'wb') as f, gzip.GzipFile(fileobj=f, mode='wb', mtime=mtime, filename='') as g:
    g.write(buf.getvalue())
with tarfile.open(dst) as t:
    assert not any('oap-sdk' in n for n in t.getnames()), 'oap-sdk left in the package'
print(dst)
PY
