#!/usr/bin/env python3
"""Exercise interactive uninstall only in a task-owned Docker test image."""
import argparse
import errno
import os
import pty
import select
import subprocess
import time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--image', required=True, choices=['easytier-smoke:ipk', 'easytier-smoke:apk'])
    ap.add_argument('--log', type=Path, required=True)
    args = ap.parse_args()
    master, slave = pty.openpty()
    command = '''set -eu
sh /tmp/easytier.sh --luci-only
uci set easytier.@easytier[0].instance_name=uninstall-marker
uci commit easytier
sha256sum /etc/config/easytier /etc/easytier/config.toml > /tmp/before.sha256
sh /tmp/easytier.sh --uninstall
sha256sum -c /tmp/before.sha256
[ -n "$(find /root/easytier-backups -name config.tar.gz -print)" ]
if command -v opkg >/dev/null; then
    ! opkg list-installed | grep -q '^luci-app-easytier '
else
    ! apk info -e luci-app-easytier
fi
echo UNINSTALL_PASSED
'''
    proc = subprocess.Popen(['docker', 'run', '--rm', '-it', '--name',
                             args.image.replace(':', '-') + '-uninstall',
                             '--entrypoint', '/bin/ash', args.image, '-c', command],
                            stdin=slave, stdout=slave, stderr=slave, close_fds=True)
    os.close(slave)
    output = bytearray()
    sent = False
    deadline = time.monotonic() + 600
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], 1)
            if ready:
                try:
                    chunk = os.read(master, 65536)
                except OSError as exc:
                    if exc.errno == errno.EIO:
                        break
                    raise
                if not chunk:
                    break
                output.extend(chunk)
                if not sent and '输入 REMOVE 确认：'.encode() in output:
                    os.write(master, b'REMOVE\n')
                    sent = True
            elif proc.poll() is not None:
                break
        else:
            proc.terminate()
            raise TimeoutError('Uninstall smoke test timed out')
        code = proc.wait(timeout=10)
    finally:
        os.close(master)
        args.log.write_bytes(output)
    if code or not sent or b'UNINSTALL_PASSED' not in output:
        raise SystemExit(1)
    print(args.image, 'UNINSTALL_PASSED')


if __name__ == '__main__':
    main()
