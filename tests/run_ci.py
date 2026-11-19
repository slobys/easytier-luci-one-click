#!/usr/bin/env python3
"""Run shell regressions with a checksum-pinned official OpenWrt jsonfilter.

Only downloads/extracts a rootfs in a temporary directory; no installation,
root privileges, Docker, router access or GitHub API token is required.
"""
import hashlib
import os
import shlex
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOTFS_URL = ('https://downloads.openwrt.org/releases/25.12.6/targets/x86/64/'
              'openwrt-25.12.6-x86-64-rootfs.tar.gz')
ROOTFS_SHA256 = '55e52bb34de582a1ebe56bd50f94ff54ac7c77f5bca9cae807656d1930456da4'
PROJECT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='et-luci-ci-') as temp:
        work = Path(temp)
        archive = work / 'rootfs.tar.gz'
        urllib.request.urlretrieve(ROOTFS_URL, archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != ROOTFS_SHA256:
            raise RuntimeError('Official rootfs checksum mismatch')
        root = work / 'rootfs'
        root.mkdir()
        with tarfile.open(archive) as tar:
            for member in tar:
                path = Path(member.name)
                if path.is_absolute() or '..' in path.parts:
                    raise RuntimeError('Unsafe rootfs archive path')
        subprocess.run(['tar', '-xzf', str(archive), '-C', str(root)], check=True)
        command = [str(root / 'lib/ld-musl-x86_64.so.1'), '--library-path',
                   f'{root}/lib:{root}/usr/lib', str(root / 'usr/bin/jsonfilter')]
        wrapper = work / 'jsonfilter'
        wrapper.write_text('#!/bin/sh\nexec ' + shlex.join(command) + ' "$@"\n')
        wrapper.chmod(0o755)
        for shell in ['/bin/sh', 'busybox ash']:
            env = dict(os.environ, JSONFILTER_BIN=str(wrapper), TEST_SHELL=shell)
            print('Testing:', shell, flush=True)
            subprocess.run([sys.executable, str(PROJECT / 'tests/test_installer.py')],
                           env=env, check=True)


if __name__ == '__main__':
    main()
