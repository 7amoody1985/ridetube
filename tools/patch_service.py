#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Added in this fork (2026-11-07); not part of JustAnotherPU/ridetube.
"""Builds the service's tool kit without Docker: a published jap-ridetube-d package with this checkout's ytd.js,
ytfetch.py, thumb.js, check.sh and systemd unit, and native/jap-ridetube-d/component.json's version, title and
description. ytdec (the C++ decoder, built in Docker) and ytdlp.pyz (the pinned yt-dlp) stay the base package's.

    python3 tools/patch_service.py <base, e.g. jap-ridetube-d@0.3.8.tgz> [--out dist]

Writes <out>/jap-ridetube-d@<version>.tgz with the file list's sha256 updated, sorted, owner 0:0, mtime
SOURCE_DATE_EPOCH (default 0).
"""
import argparse, gzip, hashlib, io, json, os, sys, tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVC = os.path.join(ROOT, 'native', 'jap-ridetube-d')
TOOL = 'jap-ridetube-d'
# package path -> source in this checkout
SWAP = {'files/ytd.js': 'ytd.js', 'files/ytfetch.py': 'ytfetch.py', 'files/thumb.js': 'thumb.js', 'files/check.sh': 'check.sh',
        'units/jap-ridetube-d.service': 'systemd/jap-ridetube-d.service'}
KEEP = ('files/ytdec', 'files/ytdlp.pyz')   # built elsewhere: must be in the base


def text(path):
    with open(path, 'rb') as f:
        return f.read().replace(b'\r\n', b'\n')     # (a Windows checkout's line ends)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('base')
    ap.add_argument('--out', default=os.path.join(ROOT, 'dist'))
    a = ap.parse_args()
    src = json.loads(text(os.path.join(SVC, 'component.json')))
    mtime = int(os.environ.get('SOURCE_DATE_EPOCH', '0'))
    with tarfile.open(a.base, 'r:gz') as t:
        members = [(m, t.extractfile(m).read() if m.isfile() else None) for m in t.getmembers()]
    files = {m.name: d for m, d in members}
    missing = [n for n in list(SWAP) + list(KEEP) + ['component.json'] if n not in files]
    if missing:
        sys.exit('patch_service.py: not in the base package: %s' % ', '.join(missing))
    new = {n: text(os.path.join(SVC, s)) for n, s in SWAP.items()}
    comp = json.loads(files['component.json'])
    old = comp['version']
    comp['version'], comp['title'], comp['description'] = src['version'], src['title'], src['description']
    for f in comp['files']:
        n = 'files/' + f['path']
        f['sha256'] = hashlib.sha256(new.get(n, files.get(n, b''))).hexdigest()
    new['component.json'] = (json.dumps(comp, indent=2) + '\n').encode('utf-8')

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w', format=tarfile.USTAR_FORMAT) as out:
        for m, d in sorted(members, key=lambda x: x[0].name):
            if m.name in new:
                d = new[m.name]
                m.size = len(d)
            m.uid = m.gid = 0
            m.uname = m.gname = ''
            m.mtime = mtime
            out.addfile(m, io.BytesIO(d) if d is not None else None)
    os.makedirs(a.out, exist_ok=True)
    dst = os.path.join(a.out, '%s@%s.tgz' % (TOOL, comp['version']))
    with open(dst, 'wb') as f, gzip.GzipFile(fileobj=f, mode='wb', mtime=mtime, filename='') as g:
        g.write(buf.getvalue())
    changed = sorted(n for n in new if new[n] != files[n])
    print('%s (from %s %s): %d files changed' % (dst, os.path.basename(a.base), old, len(changed)))
    for n in changed:
        print('  ' + n)


if __name__ == '__main__':
    main()
