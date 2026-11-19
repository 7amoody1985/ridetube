#!/usr/bin/env python3
"""Lays out the MGU Store catalog of this repository in dist/release/: catalog.json, the app's OAP package
(without node_modules/oap-sdk: the head unit makes it from an app already on the car), the tool kits (the service, Full-width touch),
jap-node22 (which jap-ridetube-d requires) and the app icon. Upload every file of dist/release/ as an asset of a GitHub
release tagged `catalog`.

jap-node22 is the JustAnotherPU/mgu-apps artifact byte for byte (same id, version, file), so this catalog installs
RideTube on its own; it is never built here. It is taken from --node22 (a path or an https URL), by default the mgu-apps
clone next to this one (dist/, as its tools/jap-node22/build.sh leaves it), else the mgu-apps `catalog` release; either
way it must match the pinned size and sha256 (NODE22) or nothing is written.

Build first:  python3 kit/tools/build.py jap_ridetube                      (dist/jap_ridetube@<v>.tgz)
              (cd native/ytdec && make target)
              (cd native/jap-ridetube-d && MGU_STORE=... ./build.sh)      (its dist/)
Then:         python3 tools/release.py [--base URL] [--node22 PATH|URL]
--base: where the car downloads the assets from; default the public release download of the `catalog`
release. For a private repository, list the assets' API URLs instead (docs/PUBLISHING.md of the Store).
"""
import argparse, gzip, hashlib, io, json, os, re, shutil, sys, tarfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = 'JustAnotherPU/ridetube'
APP = 'jap_ridetube'
TOOLS = ('jap-ridetube-d', 'mgu-render-id7-touch')
OPTIONAL = ('mgu-render-id7-touch',)   # offered beside RideTube, never required (RideTube adapts without it)
# mgu-apps' published jap-node22 (its catalog release asset, 2026-11-04) and its catalog entry (release/catalog.js there)
NODE22 = {'version': '22.23.4', 'size': 49203293, 'sha256': 'c62a8e2a3803b858b4d1020cb19746c8bd9ae8b753145f80c5adf7d781692743',
          'url': 'https://github.com/JustAnotherPU/mgu-apps/releases/download/catalog/jap-node22%4022.23.4.tgz'}
NODE22_ENTRY = {'id': 'jap-node22', 'kind': 'tool', 'title': 'Node.js 22',
                'description': "Node.js 22 LTS for the background services of Moonride and RideTube (BMW's apps keep the system Node 8)",
                'requires': {'mgu-deploy': '0.7.0'}, 'uninstallable': True, 'mguHmi': ['ID7'], 'optional': True}


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def strip_sdk(src, dst, mtime):
    """The OAP package again, without node_modules/oap-sdk, sorted, owner 0:0, one mtime."""
    with tarfile.open(src, 'r:gz') as t:
        members = [(m, t.extractfile(m).read() if m.isfile() else None) for m in t.getmembers()]
    keep = [(m, d) for m, d in members if 'node_modules/oap-sdk' not in m.name]
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w', format=tarfile.USTAR_FORMAT) as out:
        for m, d in sorted(keep, key=lambda x: x[0].name):
            m.uid = m.gid = 0
            m.uname = m.gname = ''
            m.mtime = mtime
            out.addfile(m, io.BytesIO(d) if d is not None else None)
    with open(dst, 'wb') as f, gzip.GzipFile(fileobj=f, mode='wb', mtime=mtime, filename='') as g:
        g.write(buf.getvalue())
    with tarfile.open(dst, 'r:gz') as t:
        assert not any('oap-sdk' in n for n in t.getnames()), 'oap-sdk left in the package'


def node22(src, out):
    """jap-node22's artifact into out/, checked against NODE22 (a download goes to dist/ first); its file name."""
    name = 'jap-node22@%s.tgz' % NODE22['version']
    if src is None:
        local = os.path.join(ROOT, '..', 'mgu-apps', 'dist', name)
        src = local if os.path.isfile(local) else NODE22['url']
    if src.startswith('https://'):
        import urllib.request
        dl = os.path.join(ROOT, 'dist', name)
        print('jap-node22: downloading %s' % src)
        with urllib.request.urlopen(src, timeout=60) as r, open(dl + '.part', 'wb') as f:
            shutil.copyfileobj(r, f)
        os.replace(dl + '.part', dl)
        src = dl
    if not os.path.isfile(src):
        sys.exit('release.py: jap-node22: %s missing' % src)
    if os.path.getsize(src) != NODE22['size'] or sha256(src) != NODE22['sha256']:
        sys.exit('release.py: jap-node22: %s is not the mgu-apps artifact (size or sha256 differ)' % src)
    shutil.copy(src, os.path.join(out, name))
    return name


def artifact(path, base):
    name = os.path.basename(path)
    return {'name': name, 'size': os.path.getsize(path), 'sha256': sha256(path), 'url': base + name}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='https://github.com/%s/releases/download/catalog/' % REPO)
    ap.add_argument('--node22', help='jap-node22@%s.tgz: a path or an https URL (default: ../mgu-apps/dist, else NODE22 url)' % NODE22['version'])
    a = ap.parse_args()
    mtime = int(os.environ.get('SOURCE_DATE_EPOCH', '0'))
    out = os.path.join(ROOT, 'dist', 'release')
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)

    app = json.load(open(os.path.join(ROOT, 'apps', APP, 'app.json')))
    tools = {t: json.load(open(os.path.join(ROOT, 'native', t, 'component.json'))) for t in TOOLS}
    if tools['jap-ridetube-d']['requires'].get('jap-node22') != NODE22['version']:
        sys.exit('release.py: jap-ridetube-d requires jap-node22 %s, NODE22 pins %s'
                 % (tools['jap-ridetube-d']['requires'].get('jap-node22'), NODE22['version']))
    # ytd.js BUILT: a head unit clock before it skips the certificate dates, so a day still ahead would do that on a
    # car whose clock is right
    built = re.search(r"^const BUILT = '(\d{4}-\d\d-\d\d)';", open(os.path.join(ROOT, 'native', 'jap-ridetube-d', 'ytd.js')).read(), re.M)
    if not built or built.group(1) > time.strftime('%Y-%m-%d', time.gmtime()):
        sys.exit("release.py: ytd.js BUILT must be today's date (UTC) or earlier: %s" % (built and built.group(1)))
    pkg = os.path.join(ROOT, 'dist', '%s@%s.tgz' % (APP, app['version']))
    if not os.path.isfile(pkg):
        sys.exit('release.py: %s missing (python3 kit/tools/build.py %s)' % (pkg, APP))
    n22 = node22(a.node22, out)   # before the local package goes (below): a refused jap-node22 costs no rebuild
    strip_sdk(pkg, os.path.join(out, os.path.basename(pkg)), mtime)
    # the local build's packages hold BMW's oap-sdk: only dist/release/ is ever uploaded, so they go
    for f in (pkg, pkg[:-4] + '.mgu'):
        if os.path.exists(f):
            os.remove(f)
    for t, c in tools.items():
        kit = os.path.join(ROOT, 'native', t, 'dist', '%s@%s.tgz' % (t, c['version']))
        if not os.path.isfile(kit):
            sys.exit('release.py: %s missing (cd native/%s && ./build.sh)' % (kit, t))
        shutil.copy(kit, out)
    icon = APP + '.png'
    shutil.copy(os.path.join(ROOT, 'apps', APP, 'icon.png'), os.path.join(out, icon))
    assert os.path.getsize(os.path.join(out, icon)) <= 128 * 1024

    comps = [{
        'id': APP, 'kind': 'app', 'title': app['title'], 'description': app['description'], 'version': app['version'],
        'artifact': artifact(os.path.join(out, os.path.basename(pkg)), a.base),
        'requires': {'jap-ridetube-d': tools['jap-ridetube-d']['version'], 'mgu-render': '0.6.11', 'mgu-inputgate': '1.0.0'},
        'uninstallable': True, 'mguHmi': ['ID7'], 'icon': icon, 'iconSha256': sha256(os.path.join(out, icon)),
    }]
    for t, c in tools.items():
        e = {'id': t, 'kind': 'tool', 'title': c['title'], 'description': c['description'], 'version': c['version'],
             'artifact': artifact(os.path.join(out, '%s@%s.tgz' % (t, c['version'])), a.base),
             'requires': c.get('requires', {}), 'uninstallable': bool(c.get('uninstallable')), 'mguHmi': c.get('mguHmi', ['ID7'])}
        if t in OPTIONAL:
            e['optional'] = True
        comps.append(e)
    comps.append(dict(NODE22_ENTRY, version=NODE22['version'], artifact=artifact(os.path.join(out, n22), a.base)))
    with open(os.path.join(out, 'catalog.json'), 'w') as f:
        json.dump({'schema': 2, 'components': comps}, f, indent=2)
        f.write('\n')
    for n in sorted(os.listdir(out)):
        print('%10d  %s' % (os.path.getsize(os.path.join(out, n)), n))


if __name__ == '__main__':
    main()
