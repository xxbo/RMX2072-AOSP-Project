#!/usr/bin/env python3
"""Seed reserved-RAM pmsg for an early-entry trial; no partition writes."""
import argparse
import hashlib
import json
import pathlib
import re
import shlex
import subprocess
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'build'))
from pack_diag_boot import validate_pstore_layout


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adb', required=True)
    p.add_argument('--serial', required=True)
    p.add_argument('--trial-id', required=True)
    p.add_argument('--output', required=True, type=pathlib.Path)
    a = p.parse_args()
    repo = pathlib.Path(__file__).resolve().parents[2]
    if a.output.resolve() == repo or repo in a.output.resolve().parents:
        p.error('Raw captures stay outside checkout')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', a.trial_id):
        p.error('Invalid trial ID')
    prefix = [a.adb, '-s', a.serial]
    def root(command):
        result = subprocess.run(prefix+['exec-out', '/debug_ramdisk/su -c '+shlex.quote(command)],
                                capture_output=True, timeout=45)
        if result.returncode:
            raise RuntimeError('Root command failed: '+result.stderr.decode(errors='replace'))
        return result.stdout
    if root('id -u').strip() != b'0' or not root('uname -r').startswith(b'4.19.157'):
        raise ValueError('Requires the verified stock-reader root environment')
    layout = root('cat /sys/firmware/fdt')
    validate_pstore_layout(layout)
    root('test -c /dev/pmsg0')
    a.output.mkdir(exist_ok=False, parents=True)
    (a.output/'live-fdt.dtb').write_bytes(layout)
    line = ('RMX2072-SEED trial='+a.trial_id+'\n').encode()
    seed = (line*((2*1024*1024+len(line)-1)//len(line)))[:2*1024*1024]
    if b'RMX618E0' in seed:
        raise ValueError('Seed contains entry magic')
    (a.output/'seed.txt').write_bytes(seed)
    remote = '/data/local/tmp/rmx2072-entry-seed.txt'
    subprocess.run(prefix+['push', str(a.output/'seed.txt'), remote], check=True, capture_output=True)
    root('cat '+shlex.quote(remote)+' > /dev/pmsg0')
    report = dict(trial_id=a.trial_id, seed_bytes=len(seed), seed_sha256=hashlib.sha256(seed).hexdigest(),
                  pstore_layout_verified=True, entry_magic_absent_from_seed=True,
                  target='reserved-RAM /dev/pmsg0', status='seed-written-before-candidate-reboot')
    (a.output/'seed.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
