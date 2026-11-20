#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# LAB ONLY (7amoody1985's branch lab-ram, never for a pull request): the test copy for 7amoody1985/mgu-apps-lab, under
# the fork's own ids so it installs beside JustAnotherPU's RideTube and never over it: the app mdq_ridetube ("RideTube
# (fork)", logging id OAB1), the service mdq-ridetube-d (/var/opt/mdq-ridetube-d, /run/mdq-ridetube-d, the RAM disk
# /run/mdq-ridetube-media, mdq-ridetube-d.service). The tree keeps JustAnotherPU's ids; this renames a copy, then builds:
# - the app with the kit's own build (kit/tools/build.py) and a placeholder oap-sdk, stripped from the package as
#   tools/release.py does;
# - the service with the MGU Store's own packer (deploy/hu artifact), ytdec and ytdlp.pyz taken from JustAnotherPU's
#   published service package (checked against its own sha256 list).
#
#   MGU_STORE=<a clone of the MGU Store> tools/lab_build.sh <his jap-ridetube-d@X.tgz> <app version> <service version>
#
# Writes dist/lab/mdq_ridetube@<app version>.tgz and dist/lab/mdq-ridetube-d@<service version>.tgz. Linux (WSL): the
# copy gets LF line ends and 0644 files whatever the checkout has.
set -eu
: "${MGU_STORE:?set MGU_STORE to a clone of github.com/robertnisipeanu/mgu-store}"
base=$(cd "$(dirname "$1")" && pwd)/$(basename "$1"); appv=$2; svcv=$3
root=$(cd "$(dirname "$0")/.." && pwd)
stage=$(mktemp -d "${TMPDIR:-/tmp}/lab.XXXXXX")
trap 'rm -rf "$stage"' EXIT
(cd "$root" && tar --exclude=./.git --exclude=./dist --exclude=./build --exclude=./oap-sdk --exclude=__pycache__ -cf - .) | tar -xf - -C "$stage"
find "$stage" -type d -exec chmod 0755 {} +
find "$stage" -type f -exec chmod 0644 {} +
find "$stage" -type f \( -name '*.js' -o -name '*.py' -o -name '*.sh' -o -name '*.json' -o -name '*.txt' -o -name '*.md' -o -name '*.html' \
    -o -name '*.service' -o -name 'LICENSE*' -o -name 'THIRD_PARTY_LICENSES' -o -name '*.tsv' -o -name '*.svg' \) -exec sed -i 's/\r$//' {} +

# the rename (jap-node22, JustAnotherPU's Node.js 22, stays his)
cd "$stage"
mv apps/jap_ridetube apps/mdq_ridetube
mv native/jap-ridetube-d native/mdq-ridetube-d
mv native/mdq-ridetube-d/systemd/jap-ridetube-d.service native/mdq-ridetube-d/systemd/mdq-ridetube-d.service
grep -rlI -e 'jap_ridetube' -e 'jap-ridetube-d' -e 'jap-ridetube-media' . | xargs -r sed -i \
    -e 's/jap_ridetube/mdq_ridetube/g' -e 's/jap-ridetube-d/mdq-ridetube-d/g' -e 's/jap-ridetube-media/mdq-ridetube-media/g'
python3 - "$appv" "$svcv" <<'PY'
import json, sys
appv, svcv = sys.argv[1:]
p = 'apps/mdq_ridetube/app.json'
a = json.load(open(p, encoding='utf-8'))
a['title'], a['loggingId'], a['version'] = 'RideTube (fork)', 'OAB1', appv   # (the tile; the screens keep "RideTube")
open(p, 'w', encoding='utf-8').write(json.dumps(a, indent=2, ensure_ascii=False) + '\n')
p = 'native/mdq-ridetube-d/component.json'
c = json.load(open(p))
c['version'] = svcv
c['title'] = 'RideTube service (fork by 7amoody1985)'
open(p, 'w').write(json.dumps(c, indent=2) + '\n')
left = []
import os
for d, _, fs in os.walk('.'):
    for f in fs:
        try:
            if 'jap_ridetube' in open(os.path.join(d, f), encoding='utf-8').read():
                left.append(os.path.join(d, f))
        except (UnicodeDecodeError, OSError):
            pass
if left:
    sys.exit('lab_build.sh: jap_ridetube left in ' + ', '.join(left))
PY

# the app: the kit's build, a placeholder oap-sdk (build.py only copies it in), stripped from the package
mkdir -p oap-sdk
echo '// placeholder for kit/tools/build.py: stripped from the package' > oap-sdk/index.js
echo '{"name":"oap-sdk","version":"0.0.0-placeholder"}' > oap-sdk/package.json
python3 kit/tools/build.py mdq_ridetube | tail -1
mkdir -p "$root/dist/lab"
python3 - "dist/mdq_ridetube@$appv.tgz" "$root/dist/lab/mdq_ridetube@$appv.tgz" <<'PY'
import gzip, io, sys, tarfile
src, dst = sys.argv[1:]
with tarfile.open(src) as t:
    ms = [(m, t.extractfile(m).read() if m.isfile() else None) for m in t.getmembers()]
keep = sorted(((m, d) for m, d in ms if 'node_modules/oap-sdk' not in m.name), key=lambda x: x[0].name)
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode='w', format=tarfile.USTAR_FORMAT) as out:
    for m, d in keep:
        m.uid = m.gid = 0; m.uname = m.gname = ''; m.mtime = 0
        out.addfile(m, io.BytesIO(d) if d is not None else None)
with open(dst, 'wb') as f, gzip.GzipFile(fileobj=f, mode='wb', mtime=0, filename='') as g:
    g.write(buf.getvalue())
with tarfile.open(dst) as t:
    assert not any('oap-sdk' in n for n in t.getnames()), 'oap-sdk left in the package'
print(dst)
PY

# the service: ytdec and ytdlp.pyz from his published package, the MGU Store's packer
svc=native/mdq-ridetube-d
mkdir -p "$svc/build" base
tar -xzf "$base" -C base component.json files/ytdec files/ytdlp.pyz
for f in ytdec ytdlp.pyz; do
    want=$(python3 -c "import json,sys; print([x['sha256'] for x in json.load(open(sys.argv[1]))['files'] if x['path'] == sys.argv[2]][0])" base/component.json "$f")
    [ "$(sha256sum "base/files/$f" | cut -d' ' -f1)" = "$want" ] || { echo "lab_build.sh: $f does not match the base's sha256" >&2; exit 1; }
    cp "base/files/$f" "$svc/build/$f"
done
chmod 0755 "$svc/build/ytdec"
SOURCE_DATE_EPOCH=0 node "$MGU_STORE/deploy/hu" artifact "$svc" --out "$root/dist/lab" | head -1
