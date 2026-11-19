#!/usr/bin/env python3
"""Isolated shell regressions; real jsonfilter is supplied with JSONFILTER_BIN.

Only target paths are redirected into a temporary root. Package transactions and
download transport are fixtures; these are not firmware compatibility evidence.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'easytier.sh'
SHELL = os.environ.get('TEST_SHELL', '/bin/sh').split()


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='easytier-regression-')
        self.root = Path(self.tmp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for p in ['etc/config', 'etc/easytier', 'etc/init.d', 'usr/bin',
                  'usr/lib/lua/luci/controller', 'tmp', 'root', 'lib/apk/db']:
            (self.root / p).mkdir(parents=True, exist_ok=True)
        source = SCRIPT.read_text().rsplit('\ndetect\n', 1)[0]
        source = re.sub(r'/(?:etc/|usr/|root/|lib/apk/|tmp/)',
                        lambda m: str(self.root) + m.group(), source)
        source = source.replace('-C /', '-C "' + str(self.root) + '"')
        # Commands, not fixture paths, remain target-native checks in real tests.
        self.lib = self.root / 'library.sh'
        self.lib.write_text(source)
        self.env = dict(os.environ, PATH=str(self.bin) + ':' + os.environ['PATH'])
        self.env.pop('EASYTIER_DOWNLOAD_PROXY', None)
        jf = os.environ.get('JSONFILTER_BIN') or shutil.which('jsonfilter')
        if not jf:
            self.skipTest('Set JSONFILTER_BIN to a real OpenWrt jsonfilter wrapper')
        self.executable('jsonfilter', '#!/bin/sh\nexec ' + jf + ' "$@"\n')
        self.package_mode('ipk')

    def tearDown(self):
        self.tmp.cleanup()

    def executable(self, name, text):
        p = self.bin / name
        p.write_text(text)
        p.chmod(0o755)

    def package_mode(self, ext):
        self.ext = ext
        self.sdk = '22.03.7' if ext == 'ipk' else 'SNAPSHOT'
        self.zip = self.root / 'fixture.zip'
        names = ['easytier', 'luci-app-easytier', 'luci-i18n-easytier-zh-cn']
        self.filenames = []
        with zipfile.ZipFile(self.zip, 'w') as z:
            for name in names:
                if ext == 'ipk':
                    filename = f'{name}_2.6.4_{"x86_64" if name == "easytier" else "all"}.ipk'
                else:
                    filename = f'{name}-2.6.4.apk'
                self.filenames.append(filename)
                z.writestr(filename, b'test-package-fixture')
        self.make_release()

    def make_release(self, **updates):
        name = f'EasyTier-v2.6.4-x86_64-{self.sdk}.zip'
        self.release = {'tag_name': 'v2.6.4', 'draft': False, 'prerelease': False,
                        'assets': [{'name': name, 'size': self.zip.stat().st_size,
                                    'digest': 'sha256:' + hashlib.sha256(self.zip.read_bytes()).hexdigest(),
                                    'browser_download_url': f'https://github.com/EasyTier/luci-app-easytier/releases/download/v2.6.4/{name}'}]}
        self.release.update(updates)
        self.save_release()

    def save_release(self):
        (self.root / 'release.json').write_text(json.dumps(self.release, separators=(',', ':')))

    def run_code(self, code, success=True):
        setup = f'''
PM={"opkg" if self.ext == "ipk" else "apk"}; EXT={self.ext}; ARCH=x86_64; SDK={self.sdk}
root_only() {{ :; }}
update_indexes() {{ :; }}
prepare_tools() {{ :; }}
pm_install() {{ :; }}
fetch() {{ case "$1" in *releases/latest|*releases/tags/*) cp '{self.root}/release.json' "$2";; *) cp '{self.zip}' "$2";; esac; }}
installed_version() {{ if [ -f '{self.root}/installed' ]; then printf '%s\\n' 2.6.4; fi; }}
opkg() {{ if [ "$1" = compare-versions ]; then return 1; fi; touch '{self.root}/installed'; }}
apk() {{ if [ "$1" = version ]; then echo '<'; else touch '{self.root}/installed'; fi; }}
'''
        svc = self.root / 'etc/init.d/easytier'
        svc.write_text('#!/bin/sh\nexit 0\n')
        svc.chmod(0o755)
        (self.root / 'usr/lib/lua/luci/controller/easytier.lua').write_text('-- fixture')
        core = self.root / 'usr/bin/easytier-core'
        core.write_text('#!/bin/sh\necho "easytier-core 2.6.4"\n')
        core.chmod(0o755)
        run = subprocess.run(SHELL + ['-c', f'. "{self.lib}"\n{setup}\n{code}'],
                             env=self.env, text=True, capture_output=True)
        if success:
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        else:
            self.assertNotEqual(run.returncode, 0, run.stdout + run.stderr)
        return run

    def test_full_ipk_transaction(self):
        self.run_code('CORE=easytier; install_packages')
        self.assertTrue((self.root / 'installed').exists())

    def test_full_apk_transaction(self):
        self.package_mode('apk')
        self.run_code('CORE=easytier; install_packages')

    def test_luci_only(self):
        out = self.run_code('CORE=none; install_packages')
        self.assertIn('此模式未安装核心', out.stdout)

    def test_busybox_zip_directory(self):
        self.executable('unzip', '#!/bin/sh\nexec busybox unzip "$@"\n')
        self.run_code('CORE=none; install_packages')

    def test_partial_feed_update_is_not_fatal(self):
        # Use the actual function rather than the normal fixture override.
        function = SCRIPT.read_text().split('update_indexes() {', 1)[1].split('\n}\n', 1)[0]
        self.run_code('update_indexes() {' + function + '\n}\nopkg() { return 1; }; update_indexes; echo survived')

    def test_compact_json_release(self):
        out = self.run_code('workspace; release_info')
        self.assertIn('v2.6.4', out.stdout)

    def test_all_upstream_release_selectors(self):
        snapshot = os.environ.get('EASYTIER_RELEASE_JSON') or str(
            Path(__file__).parent / 'fixtures/release-v2.6.4.json')
        release = json.loads(Path(snapshot).read_bytes())
        (self.root / 'release.json').write_text(json.dumps(release, separators=(',', ':')))
        for asset in release['assets']:
            m = re.fullmatch(r'EasyTier-v[0-9.]+-(.+)-(22\.03\.7|SNAPSHOT)\.zip', asset['name'])
            self.assertIsNotNone(m)
            arch, sdk = m.groups()
            self.ext = 'apk' if sdk == 'SNAPSHOT' else 'ipk'
            self.sdk = sdk
            (self.root / 'etc/openwrt_release').write_text(f"DISTRIB_ARCH='{arch}'\n")
            db = self.root / 'lib/apk/db/installed'
            if self.ext == 'apk':
                (self.root / 'etc/apk').mkdir(exist_ok=True)
                (self.root / 'etc/apk/arch').write_text(arch + '\n')
                db.touch()
            else:
                db.unlink(missing_ok=True)
            # Exercise detection too, not only a manually assigned ARCH.
            # The compiled architecture must not override the configured ABI.
            out = self.run_code(f'''uci() {{ :; }}
apk() {{ echo 'unexpected compiled-arch lookup' >&2; return 99; }}
opkg() {{ printf 'arch all 1\\narch noarch 1\\narch {arch} 10\\n'; }}
detect; workspace; release_info''')
            self.assertIn(asset['name'], out.stdout)

    def test_missing_architecture(self):
        out = self.run_code('ARCH=mips64_octeonplus; workspace; release_info', False)
        self.assertIn('没有匹配', out.stderr)

    def apk_system(self, configured='aarch64_generic', distro='aarch64_generic'):
        self.package_mode('apk')
        fixture = Path(__file__).parent / 'fixtures/release-v2.6.4.json'
        (self.root / 'release.json').write_bytes(fixture.read_bytes())
        (self.root / 'etc/openwrt_release').write_text(
            f"DISTRIB_ARCH='{distro}'\n" if distro is not None else '')
        (self.root / 'etc/apk').mkdir()
        if configured is not None:
            (self.root / 'etc/apk/arch').write_text(configured + '\n')
        (self.root / 'lib/apk/db/installed').touch()

    def test_apk_detect_uses_configured_package_architecture(self):
        self.apk_system()
        out = self.run_code('''uci() { :; }
apk() { [ "$1" = --print-arch ] && echo aarch64; }
detect; workspace; release_info''')
        self.assertIn('EasyTier-v2.6.4-aarch64_generic-SNAPSHOT.zip', out.stdout)

    def test_apk_arch_file_precedes_distribution_arch(self):
        self.apk_system(configured='aarch64_cortex-a53')
        out = self.run_code('uci() { :; }; detect; workspace; release_info')
        self.assertIn('EasyTier-v2.6.4-aarch64_cortex-a53-SNAPSHOT.zip', out.stdout)

    def test_apk_missing_arch_file_uses_distribution(self):
        self.apk_system(configured=None)
        out = self.run_code('uci() { :; }; detect; workspace; release_info')
        self.assertIn('EasyTier-v2.6.4-aarch64_generic-SNAPSHOT.zip', out.stdout)

    def test_apk_last_resort_compiled_arch_for_x86(self):
        self.apk_system(configured=None, distro=None)
        out = self.run_code('''uci() { :; }
apk() { [ "$1" = --print-arch ] && echo x86_64; }
detect; workspace; release_info''')
        self.assertIn('EasyTier-v2.6.4-x86_64-SNAPSHOT.zip', out.stdout)

    def test_apk_bare_arm_is_not_guessed(self):
        self.apk_system(configured=None, distro=None)
        out = self.run_code('''uci() { :; }
apk() { [ "$1" = --print-arch ] && echo aarch64; }
detect; workspace; release_info''', False)
        self.assertIn('没有匹配的 aarch64 / apk', out.stderr)

    def test_apk_unsupported_config_is_not_replaced(self):
        self.apk_system(configured='aarch64_cortex-a76')
        out = self.run_code('uci() { :; }; detect; workspace; release_info', False)
        self.assertIn('没有匹配的 aarch64_cortex-a76', out.stderr)

    def test_apk_arch_file_ignores_blank_comments_and_noarch(self):
        self.apk_system(configured='\n# package ABI\nall\nnoarch\n aarch64_generic\r')
        out = self.run_code('uci() { :; }; detect; workspace; release_info')
        self.assertIn('EasyTier-v2.6.4-aarch64_generic-SNAPSHOT.zip', out.stdout)

    def test_apk_invalid_config_is_rejected_without_shell_execution(self):
        marker = self.root / 'unsafe-marker'
        self.apk_system(configured=f'aarch64_generic; touch {marker}')
        self.run_code('uci() { :; }; detect; workspace; release_info', False)
        self.assertFalse(marker.exists())

    def test_reject_prerelease(self):
        self.make_release(prerelease=True)
        self.run_code('workspace; release_info', False)

    def test_missing_digest(self):
        del self.release['assets'][0]['digest']
        self.save_release()
        self.run_code('workspace; release_info', False)

    def test_wrong_digest(self):
        self.release['assets'][0]['digest'] = 'sha256:' + '0' * 64
        self.save_release()
        out = self.run_code('install_packages', False)
        self.assertIn('SHA-256', out.stderr)
        self.assertFalse((self.root / 'installed').exists())

    def test_wrong_size(self):
        self.release['assets'][0]['size'] += 1
        self.save_release()
        self.run_code('install_packages', False)
        self.assertFalse((self.root / 'installed').exists())

    def test_empty_zip(self):
        self.zip.write_bytes(b'')
        self.run_code('install_packages', False)

    def test_preserve_config_after_failed_transaction(self):
        config = self.root / 'etc/config/easytier'
        config.write_text('original network secret fixture\n')
        self.run_code(f'''opkg() {{ echo broken > '{config}'; return 1; }}
CORE=none; install_packages''', False)
        self.assertEqual(config.read_text(), 'original network secret fixture\n')
        self.assertTrue(list((self.root / 'root/easytier-backups').glob('*/config.tar.gz')))

    def test_detect_false_package_success(self):
        out = self.run_code('opkg() { :; }; CORE=none; install_packages', False)
        self.assertIn('安装核对失败', out.stderr)

    def test_reject_downgrade(self):
        out = self.run_code('''installed_version() { echo 9.0.0; }
opkg() { return 0; }; CORE=none; install_packages''', False)
        self.assertIn('拒绝降级', out.stderr)

    def test_refuse_conflicting_core(self):
        out = self.run_code('installed_version() { echo 2.6.4; }; install_packages', False)
        self.assertIn('不能覆盖安装', out.stderr)

    def test_reject_stale_upstream_config(self):
        (self.root / 'tmp/easytier_backup').write_text('stale')
        self.run_code('install_packages', False)

    def test_failed_download(self):
        self.run_code('fetch() { return 1; }; workspace; release_info', False)

    def test_empty_success_transport(self):
        body = SCRIPT.read_text().split('fetch() {', 1)[1].split('\n}\n', 1)[0]
        out = self.run_code('''fetch() {''' + body + '''
}
curl() { for arg in "$@"; do last=$arg; done; : > "$last"; }
wget() { return 1; }
workspace; fetch https://example.invalid "$WORK/empty"''', False)
        self.assertNotEqual(out.returncode, 0)

    def test_nonzero_partial_transport(self):
        body = SCRIPT.read_text().split('fetch() {', 1)[1].split('\n}\n', 1)[0]
        self.run_code('''fetch() {''' + body + '''
}
curl() { for arg in "$@"; do last=$arg; done; echo partial > "$last"; return 1; }
wget() { return 1; }
workspace; fetch https://example.invalid "$WORK/partial"''', False)

    def test_real_concurrent_lock_ownership(self):
        ready = self.root / 'ready'
        owner = subprocess.Popen(SHELL + ['-c', f'. "{self.lib}"; lock; workspace; touch "{ready}"; read -r done'],
                                 env=self.env, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        import time
        try:
            deadline = time.monotonic() + 3
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready.exists())
            self.run_code('install_packages', False)
            self.assertTrue((self.root / 'tmp/et-luci-install.lock/pid').exists())
        finally:
            owner.communicate('done\n', timeout=5)
        self.assertFalse((self.root / 'tmp/et-luci-install.lock').exists())

    def test_foreign_lock_is_not_removed(self):
        lock = self.root / 'tmp/et-luci-install.lock'
        lock.mkdir()
        (lock / 'pid').write_text('1234')
        self.run_code('install_packages', False)
        self.assertEqual((lock / 'pid').read_text(), '1234')

    def test_signal_exits_and_preserves_foreign_work(self):
        foreign = self.root / 'tmp/et-luci-install.foreign'
        foreign.mkdir()
        self.run_code('lock; workspace; kill -TERM $$; touch "' + str(self.root / 'bad') + '"', False)
        self.assertFalse((self.root / 'bad').exists())
        self.assertTrue(foreign.exists())
        self.assertFalse((self.root / 'tmp/et-luci-install.lock').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
