#!/usr/bin/env python3
"""Real x86_64 rootfs transactions; only GitHub transport uses verified cache.

Root filesystems and dependency feeds are official OpenWrt. Docker shares the
host kernel: results do not validate the firmware kernel, procd, or mesh traffic.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cache', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    cache = args.cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    release = json.loads((cache / 'release.json').read_bytes())
    tag = release['tag_name']
    results = []
    for pm, firmware, sdk in [('ipk', '24.10.8', '22.03.7'), ('apk', '25.12.6', 'SNAPSHOT')]:
        url = f'https://downloads.openwrt.org/releases/{firmware}/targets/x86/64/'
        index = urllib.request.urlopen(url).read().decode()
        filename = next(n for n in re.findall(r'href="([^"]+)"', index)
                        if n.endswith('-rootfs.tar.gz') and '-targz-' not in n)
        rootfs = cache / filename
        if not rootfs.exists():
            urllib.request.urlretrieve(url + filename, rootfs)
        digest = hashlib.sha256(rootfs.read_bytes()).hexdigest()
        checksums = urllib.request.urlopen(url + 'sha256sums').read().decode()
        assert any(line.split()[0] == digest and line.split()[-1].lstrip('*') == filename
                   for line in checksums.splitlines())
        build = cache / ('smoke-' + pm)
        build.mkdir(exist_ok=True)
        shutil.copyfile(rootfs, build / 'rootfs.tar.gz')
        shutil.copyfile(PROJECT / 'easytier.sh', build / 'easytier.sh')
        asset = next(a for a in release['assets'] if a['name'] == f'EasyTier-{tag}-x86_64-{sdk}.zip')
        artifact = cache / asset['name']
        assert 'sha256:' + hashlib.sha256(artifact.read_bytes()).hexdigest() == asset['digest']
        shutil.copyfile(artifact, build / 'release.zip')
        shutil.copyfile(cache / 'release.json', build / 'release.json')
        old = json.loads((cache / 'old-release.json').read_bytes())
        old_asset = next(a for a in old['assets'] if a['name'] == f"EasyTier-{old['tag_name']}-x86_64-{sdk}.zip")
        old_zip = cache / old_asset['name']
        assert 'sha256:' + hashlib.sha256(old_zip.read_bytes()).hexdigest() == old_asset['digest']
        shutil.copyfile(old_zip, build / 'old-release.zip')
        shutil.copyfile(cache / 'old-release.json', build / 'old-release.json')
        (build / 'wget-fixture').write_text('''#!/bin/sh
out=
while [ "$#" -gt 0 ]; do
    case "$1" in -T) shift 2;; -O) out=$2; shift 2;; *) url=$1; shift;; esac
done
case "$url" in
    https://api.github.com/repos/EasyTier/luci-app-easytier/releases/tags/v2.6.2) cp /fixtures/old-release.json "$out";;
    https://api.github.com/repos/EasyTier/luci-app-easytier/releases/*) cp /fixtures/release.json "$out";;
    https://github.com/EasyTier/luci-app-easytier/releases/download/v2.6.2/*) cp /fixtures/old-release.zip "$out";;
    https://github.com/EasyTier/luci-app-easytier/releases/download/*) cp /fixtures/release.zip "$out";;
    *) exec /bin/uclient-fetch -T 60 -O "$out" "$url";;
esac
''')
        (build / 'smoke.sh').write_text('''#!/bin/sh
set -eu
mode=$1
case "$mode" in
    full) set -- --install;;
    noweb) set -- --install --no-web;;
    luci-only) set -- --luci-only;;
esac
# The no-web variant did not exist in v2.6.2; other modes exercise a real upgrade.
if [ "$mode" = noweb ]; then sh /tmp/easytier.sh "$@"; else sh /tmp/easytier.sh "$@" --tag v2.6.2; fi
[ "$(uci -q get easytier.@easytier[0].enabled)" = 0 ]
[ "$(uci -q get easytier.@easytier[0].web_enabled)" = 0 ]
uci set easytier.@easytier[0].instance_name=installer-validation-marker
uci commit easytier
/etc/init.d/easytier disable
echo '# installer-validation-marker' >> /etc/easytier/config.toml
sha256sum /etc/config/easytier /etc/easytier/config.toml > /tmp/before.sha256
sh /tmp/easytier.sh "$@"
sha256sum -c /tmp/before.sha256
if /etc/init.d/easytier enabled; then echo 'Unexpected boot-state change'; exit 1; fi
sh /tmp/easytier.sh "$@"
sha256sum -c /tmp/before.sha256
sh /tmp/easytier.sh --status
[ "$(uci -q get easytier.@easytier[0].enabled)" = 0 ]
[ -z "$(find /tmp -maxdepth 1 -name 'et-luci-install.*' -print)" ]
echo 'SMOKE_PASSED: install, repeat, config retention, disabled config, package records'
''')
        (build / 'Dockerfile').write_text('''FROM scratch
ADD rootfs.tar.gz /
COPY easytier.sh /tmp/easytier.sh
COPY release.zip release.json old-release.zip old-release.json /fixtures/
COPY wget-fixture /usr/local/bin/wget
COPY smoke.sh /smoke.sh
RUN ["/bin/ash", "-c", "mkdir -p /var/lock /var/run; chmod 1777 /tmp; chmod +x /usr/local/bin/wget"]
ENV PATH=/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENTRYPOINT ["/bin/ash", "/smoke.sh"]
''')
        image = 'easytier-smoke:' + pm
        run(['docker', 'build', '-t', image, str(build)], stdout=subprocess.DEVNULL)
        for mode in ['full', 'noweb', 'luci-only']:
            logfile = cache / f'smoke-{pm}-{mode}.log'
            with logfile.open('w') as out:
                proc = subprocess.run(['docker', 'run', '--rm', '--name', f'easytier-smoke-{pm}-{mode}',
                                       image, mode], stdout=out, stderr=subprocess.STDOUT)
            record = {'firmware': firmware, 'arch': 'x86_64', 'rootfs_sha256': digest,
                      'format': pm, 'mode': mode, 'exit_code': proc.returncode,
                      'log': logfile.name, 'github_transport': 'verified-cache-fixture',
                      'firmware_kernel_service': 'not-tested', 'mesh_data_plane': 'not-tested'}
            results.append(record)
            print(json.dumps(record), flush=True)
    args.output.write_text(json.dumps({'records': results}, indent=2) + '\n')
    if any(r['exit_code'] for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
