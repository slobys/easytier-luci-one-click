#!/usr/bin/env python3
"""Audit every release ZIP; run IPK cores natively or with QEMU user emulation.

This is artifact/runtime evidence, NOT target firmware/kernel/network evidence.
Requires a native OpenWrt apk + musl loader, and optionally qemu-user-static.
"""
import argparse
import concurrent.futures
import hashlib
import io
import json
import re
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cache', type=Path, required=True)
    ap.add_argument('--openwrt-root', type=Path, required=True)
    ap.add_argument('--qemu-bin', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    api = 'https://api.github.com/repos/EasyTier/luci-app-easytier/releases/latest'
    snapshot = args.cache / 'release.json'
    if not snapshot.exists():
        snapshot.write_bytes(urllib.request.urlopen(api, timeout=60).read())
    release = json.loads(snapshot.read_bytes())
    root = args.openwrt_root.resolve()
    apk = [str(root / 'lib/ld-musl-x86_64.so.1'), '--library-path',
           f'{root}/lib:{root}/usr/lib', str(root / 'usr/bin/apk')]

    def audit(asset):
        name = asset['name']
        match = re.fullmatch(r'EasyTier-v[\d.]+-(.+)-(22\.03\.7|SNAPSHOT)\.zip', name)
        if not match:
            return {'asset': name, 'status': 'unrecognized-asset'}
        arch, sdk = match.groups()
        dest = args.cache / name
        if not dest.exists():
            urllib.request.urlretrieve(asset['browser_download_url'], dest)
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()
        assert 'sha256:' + digest == asset['digest'], name
        assert dest.stat().st_size == asset['size'], name
        record = {'asset': name, 'arch': arch, 'format': 'ipk' if sdk != 'SNAPSHOT' else 'apk',
                  'sha256': digest, 'packages': [], 'status': 'artifact-verified',
                  'firmware_install': 'not-tested', 'firmware_kernel_service': 'not-tested',
                  'mesh_data_plane': 'not-tested'}
        with zipfile.ZipFile(dest) as z:
            assert z.testzip() is None
            for entry in z.namelist():
                assert '/' not in entry and '..' not in entry
                if not entry.endswith(('.ipk', '.apk')):
                    continue
                data = z.read(entry)
                if entry.endswith('.ipk'):
                    with tarfile.open(fileobj=io.BytesIO(data)) as t:
                        ctl = t.extractfile('./control.tar.gz').read()
                        payload = t.extractfile('./data.tar.gz').read()
                    with tarfile.open(fileobj=io.BytesIO(ctl)) as t:
                        meta = dict(line.split(': ', 1) for line in
                                    t.extractfile('./control').read().decode().splitlines()
                                    if ': ' in line)
                    item = {'name': meta['Package'], 'version': meta['Version'],
                            'arch': meta['Architecture'], 'depends': meta.get('Depends', '')}
                    with tarfile.open(fileobj=io.BytesIO(payload)) as t:
                        cores = [m for m in t if m.name.lstrip('./') == 'usr/bin/easytier-core']
                        if cores:
                            core_data = t.extractfile(cores[0]).read()
                            item['core_sha256'] = hashlib.sha256(core_data).hexdigest()
                            if item['name'] == 'easytier':
                                binary = args.cache / ('core-' + arch)
                                binary.write_bytes(core_data)
                                binary.chmod(0o755)
                                machine = ('aarch64' if arch.startswith('aarch64') else
                                           'arm' if arch.startswith('arm_') else
                                           'mipsel' if arch.startswith('mipsel_') else
                                           'mips' if arch.startswith('mips_') else None)
                                cmd = [str(binary.resolve()), '--version']
                                if machine:
                                    cmd.insert(0, str((args.qemu_bin / f'qemu-{machine}-static').resolve()))
                                try:
                                    run = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
                                    record['core_execution'] = {'code': run.returncode,
                                        'output': (run.stdout + run.stderr).strip()[:1000],
                                        'method': 'qemu-user' if machine else 'native-host'}
                                except (OSError, subprocess.TimeoutExpired) as exc:
                                    record['core_execution'] = {'error': str(exc)}
                else:
                    pkgfile = args.cache / (arch + '-' + entry)
                    pkgfile.write_bytes(data)
                    dump = subprocess.check_output(apk + ['adbdump', str(pkgfile.resolve())], text=True)
                    fields = dict(re.findall(r'^  (name|version|arch): (.+)$', dump, re.M))
                    item = {k: fields[k] for k in ['name', 'version', 'arch']}
                    hashes = re.findall(r'- name: easytier-core\n.*?\n        hash: ([0-9a-f]+)', dump, re.S)
                    if hashes:
                        item['core_sha256'] = hashes[0]
                assert item['arch'] in (arch, 'all', 'noarch'), (name, item)
                record['packages'].append(item)
        assert {p['name'] for p in record['packages']} == {
            'easytier', 'easytier-noweb', 'luci-app-easytier', 'luci-i18n-easytier-zh-cn'}, name
        print(name, record['status'], record.get('core_execution', {}).get('output', ''), flush=True)
        return record

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(audit, release['assets']))
    result = {'release': release['tag_name'], 'release_api': api,
              'release_api_sha256': hashlib.sha256(snapshot.read_bytes()).hexdigest(),
              'scope': 'All upstream assets, package metadata and IPK core --version; not all-firmware validation',
              'records': records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
