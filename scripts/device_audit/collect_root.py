#!/usr/bin/env python3
"""Read-only root boot diagnostics. All raw evidence must stay outside Git."""
import argparse
import hashlib
import json
import pathlib
import shlex
import subprocess


CAPTURES = {
    'live-fdt.dtb': 'cat /sys/firmware/fdt',
    'cmdline.txt': 'cat /proc/cmdline',
    'dmesg.txt': 'dmesg',
    'pstore-list.txt': 'ls -l /sys/fs/pstore',
    'kernel-release.txt': 'uname -r',
    'logical-partitions.txt': 'lpdump',
    'panel-info.txt': 'cat /sys/kernel/oplus_display/dump_info',
    'touch-info.txt': 'cat /proc/touchpanel/tp_info',
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adb', default='adb')
    p.add_argument('--serial', help='Target selection only; never recorded')
    p.add_argument('--su', default='/debug_ramdisk/su')
    p.add_argument('--output', required=True, type=pathlib.Path)
    a = p.parse_args()
    repo = pathlib.Path(__file__).resolve().parents[2]
    out = a.output.resolve()
    if out == repo or repo in out.parents:
        p.error('Raw diagnostics must be outside the public checkout')
    prefix = [a.adb]+(['-s', a.serial] if a.serial else [])
    def run(command):
        return subprocess.run(prefix+['exec-out', shlex.quote(a.su)+' -c '+shlex.quote(command)],
                              capture_output=True, timeout=90)
    check = run('id -u')
    if check.returncode or check.stdout.strip() != b'0':
        raise SystemExit('An explicitly granted root shell is required')
    out.mkdir(parents=True, exist_ok=False)
    report = {}
    for name, command in CAPTURES.items():
        result = run(command)
        (out/name).write_bytes(result.stdout)
        report[name] = dict(adb_returncode=result.returncode, read_error=result.stdout.startswith((b'cat:', b'ls:', b'sh:')), size_bytes=len(result.stdout),
                            sha256=hashlib.sha256(result.stdout).hexdigest(),
                            stderr=result.stderr.decode('utf-8', errors='replace').strip())
    if (out/'live-fdt.dtb').read_bytes()[:4] != b'\xd0\x0d\xfe\xed':
        report['fdt_validation'] = 'missing-or-invalid-header'
    else:
        report['fdt_validation'] = 'valid-magic'
    (out/'capture.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(captures=len(CAPTURES), failed=[name for name in CAPTURES if report[name]['adb_returncode'] or report[name]['read_error']],
                         fdt_validation=report['fdt_validation'])))


if __name__ == '__main__':
    main()
