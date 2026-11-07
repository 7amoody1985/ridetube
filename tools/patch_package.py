#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Added in this fork (2026-11-07); not part of JustAnotherPU/ridetube.
"""Builds the app's OAP package without BMW's oap-sdk: takes a published upstream package (no SDK in it) and
puts this checkout's javascript in it, with app.json's version.

A package built by kit/tools/build.py ships the app's javascript as it is: javascript/app.js is main.js,
yt.js and speller.js as they are, javascript/kit/*.js the kit's runtime files. Only those change here, so
this covers fixes to the javascript alone. A change to app.json beyond its version (screens, buttons,
settings, texts) changes rhmiData too: that still needs the full build with an extracted SDK.

    python3 tools/patch_package.py <base package, e.g. jap_ridetube@0.3.7.tgz> [--out dist]

Writes <out>/jap_ridetube@<app.json version>.tgz, sorted, owner 0:0, mtime SOURCE_DATE_EPOCH (default 0).
"""
import argparse, gzip, io, json, os, re, sys, tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = 'jap_ridetube'
APP_DIR = os.path.join(ROOT, 'apps', APP)
KIT = os.path.join(ROOT, 'kit', 'runtime')
# app-spec.json's fields that come from app.json as they are (stateIds is the build's own)
SPEC_KEYS = ('id', 'title', 'screens', 'popups', 'settings', 'config', 'startWidget')
VERSION_FILES = ('package/package.json', 'package/javascript/kit/app-spec.json', 'package/rhmiData/application.json',
                 'package/npm-shrinkwrap.json')


def text(path):
    with open(path, 'rb') as f:
        return f.read().replace(b'\r\n', b'\n')      # (a Windows checkout's line ends)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('base')
    ap.add_argument('--out', default=os.path.join(ROOT, 'dist'))
    a = ap.parse_args()
    app = json.loads(text(os.path.join(APP_DIR, 'app.json')))
    version = app['version']
    mtime = int(os.environ.get('SOURCE_DATE_EPOCH', '0'))

    with tarfile.open(a.base, 'r:gz') as t:
        members = [(m, t.extractfile(m).read() if m.isfile() else None) for m in t.getmembers()]
    files = {m.name: d for m, d in members}
    if any('node_modules/oap-sdk' in n for n in files):
        sys.exit('patch_package.py: the base package holds BMW\'s oap-sdk; use a published one')
    spec = json.loads(files['package/javascript/kit/app-spec.json'])
    changed = [k for k in SPEC_KEYS if spec.get(k) != app.get(k)]
    if changed:
        sys.exit('patch_package.py: app.json differs from the base package in %s: rhmiData must be built again '
                 '(kit/tools/build.py with an extracted SDK)' % ', '.join(changed))
    old = spec['version']

    new = {'package/javascript/app.js': text(os.path.join(APP_DIR, 'main.js'))}
    for n in ('yt.js', 'speller.js'):
        new['package/javascript/' + n] = text(os.path.join(APP_DIR, n))
    for n in files:
        m = re.match(r'^package/javascript/kit/([\w-]+\.js)$', n)
        if m:
            new[n] = text(os.path.join(KIT, m.group(1)))
    missing = [n for n in new if n not in files]
    if missing:
        sys.exit('patch_package.py: not in the base package: %s' % ', '.join(missing))
    # the version, in the same places the build writes it
    for n in VERSION_FILES:
        s = files[n].decode('utf-8')
        s2 = re.sub(r'("version":\s*")%s(")' % re.escape(old), r'\g<1>%s\g<2>' % version, s, count=1)
        if s2 == s and old != version:
            sys.exit('patch_package.py: no version %s in %s' % (old, n))
        new[n] = s2.encode('utf-8')

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
    dst = os.path.join(a.out, '%s@%s.tgz' % (APP, version))
    with open(dst, 'wb') as f, gzip.GzipFile(fileobj=f, mode='wb', mtime=mtime, filename='') as g:
        g.write(buf.getvalue())
    changed = sorted(n for n in new if new[n] != files[n])
    print('%s (from %s %s): %d files changed' % (dst, os.path.basename(a.base), old, len(changed)))
    for n in changed:
        print('  ' + n)


if __name__ == '__main__':
    main()
