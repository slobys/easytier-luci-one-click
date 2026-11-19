#!/usr/bin/env python3
"""Execute README download commands with isolated downloader fixtures."""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


class ReadmeEntrypoints(unittest.TestCase):
    def test_download_commands(self):
        blocks = re.findall(r'```sh\n(.*?)\n```', (PROJECT / 'README.md').read_text(), re.S)
        commands = [block for block in blocks if block.startswith(('wget ', 'curl '))]
        self.assertEqual(len(commands), 5)
        for command in commands:
            for mode in ['success', 'failure', 'empty', 'invalid-shell']:
                with self.subTest(command=command.split()[0], mode=mode), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    (root / 'bin').mkdir()
                    (root / 'usr/bin').mkdir(parents=True)
                    (root / 'tmp').mkdir()
                    downloader = root / 'bin/wget'
                    downloader.write_text('''#!/bin/sh
output=
while [ "$#" -gt 0 ]; do
    case "$1" in -O|-o) output=$2; shift 2;; *) shift;; esac
done
case "$ET_TRANSPORT_MODE" in
    failure) echo partial > "$output"; exit 22;;
    empty) : > "$output";;
    invalid-shell) printf 'if (\n' > "$output";;
    success) printf '#!/bin/sh\nprintf "%%s" "$*" > "$ET_EXECUTED"\n' > "$output";;
esac
''')
                    downloader.chmod(0o755)
                    (root / 'bin/curl').symlink_to(downloader)
                    rewritten = command.replace('/tmp/', str(root / 'tmp') + '/')
                    rewritten = rewritten.replace('/usr/bin/easytier-menu', str(root / 'usr/bin/easytier-menu'))
                    marker = root / 'executed'
                    env = dict(os.environ, PATH=f"{root}/bin:{root}/usr/bin:" + os.environ['PATH'],
                               ET_EXECUTED=str(marker), ET_TRANSPORT_MODE=mode)
                    result = subprocess.run(['/bin/sh', '-c', rewritten], env=env,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    if mode == 'success':
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertTrue(marker.exists())
                        self.assertEqual(marker.read_text(), '--install' if command.rstrip().endswith('--install') else '')
                    else:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertFalse(marker.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
