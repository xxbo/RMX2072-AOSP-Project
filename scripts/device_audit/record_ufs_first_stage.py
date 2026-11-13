"""Correlate ACM mounts and persistent PID 1 read results on the same UFS boot."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
FILES = {'/system/build.prop': 659, '/system/etc/init/hw/init.rc': 757}


def match(pattern, text):
    found = re.search(pattern, text, re.MULTILINE)
    if not found:
        raise ValueError('Missing observation: ' + pattern)
    return found


def full_read(console, inode, device, size, stage):
    major, minor = map(int, device.split(':'))
    dev = (major << 20) | minor  # Kernel dev_t recorded by the probe.
    pattern = (rf'^\[\s*([0-9.]+)\]\[\s*T1\] m1_file_read: [^\n]* ino={inode} '
               rf'dev={dev} count={size} result={size}$')
    for found in re.finditer(pattern, console, re.MULTILINE):
        if float(found[1]) > stage:
            return dict(at_seconds=float(found[1]), pid=1, inode=inode, device=device,
                        requested_bytes=size, returned_bytes=size)
    raise ValueError(f'No complete post-stage read of inode {inode} on {device}')


def record(directory, layout):
    def read(name):
        return (directory/name).read_bytes().decode('ascii', errors='replace').replace('\r', '')
    serial, console = read('acm.log'), read('console-ramoops-0')
    identity = json.loads((directory/'identity.json').read_text())
    if not identity['kernel'].startswith('6.18.'):
        raise ValueError('Unexpected kernel')
    boot = match(r'^M1EVENT boot_id=([0-9a-f-]{36})$', serial)[1]
    match('kernel='+re.escape(identity['kernel'])+' phase=android-first-stage-handoff trial='+
          re.escape(identity['trial'])+' boot_id='+boot+'$', console)
    backing = match(r'^M1EVENT ufs_super=(\S*/1d84000\.ufs/\S*/sda/sda10) dev=(\d+:\d+) ro=1$', serial)
    mounts = {}
    for name in ('system', 'vendor'):
        device = match(rf'^M1EVENT verified_ufs_mount={name} dev=(\d+:\d+)$', serial)[1]
        node = match(rf'^M1EVENT mounted_mapper={name}-verity node=(dm-\d+) target=/{name}$', serial)[1]
        match(rf'^M1EVENT mount_pid=1 source=/dev/block/{node} target=/{name} fs=ext4 flags=0x1 rc=0$', serial)
        table = match(rf'^M1EVENT table={name}-verity (.+)$', serial)[1].split()
        tree = layout['signed_images'][name]['tree']
        if (table[2:4] != ['verity', '1'] or table[4] != table[5] or
                table[10:13] != ['sha256', tree['root_digest'], tree['salt']]):
            raise ValueError(f'{name}: invalid device-mapper verity table')
        status = match(rf'^M1EVENT status={name}-verity (\d+ \d+ verity V[^\n]*)$', serial)[1]
        spans = re.findall(rf'^M1EVENT table={name} (\d+) (\d+) linear (\d+:\d+) (\d+)$', serial, re.MULTILINE)
        cursor = 0
        actual = []
        for logical, length, dev, physical in spans:
            if dev != backing[2] or int(logical) != cursor:
                raise ValueError(f'{name}: unexpected linear backing or offset')
            actual.append([int(physical), int(length)])
            cursor += int(length)
        if actual != layout['candidate']['active_extents_in_512b_sectors'][name]:
            raise ValueError(f'{name}: live extents differ from the candidate')
        avb = match(rf"^\[\s*([0-9.]+)\]\[\s*T1\].+Returning avb_handle for '/{name}' with status: Success$", console)
        mounts[name] = dict(node=node, device=device, linear_device=table[4], super=backing[2],
                            extents=len(actual), root_sha256=tree['root_digest'], avb_at_seconds=float(avb[1]),
                            verity_status=status, pid=1, filesystem='ext4', readonly=True, mount_rc=0)
    enforcing = float(match(r'^\[\s*([0-9.]+)\].+ enforcing=1 old_enforcing=0 .* res=1$', console)[1])
    second = float(match(r'^\[\s*([0-9.]+)\]\[\s*T1\] init: init second stage started!$', console)[1])
    if second < enforcing:
        raise ValueError('Second-stage record precedes enforcing')
    ref = json.loads((ROOT/'build/device/gsi17-mount-reference.json').read_text())
    reads = {path: full_read(console, inode, mounts['system']['device'],
                             ref['files'][path.lstrip('/')]['size'], second) for path, inode in FILES.items()}
    return dict(id=identity['trial'], boot_id=boot, kernel=identity['kernel'], ufs_super=backing[1],
                mounts=mounts, enforcing_seconds=enforcing, second_stage_seconds=second, file_reads=reads,
                raw_sha256={f: hashlib.sha256((directory/f).read_bytes()).hexdigest()
                            for f in ('acm.log', 'console-ramoops-0')})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture', required=True, type=Path)
    p.add_argument('--layout', required=True, type=Path)
    args = p.parse_args()
    print(json.dumps(record(args.capture, json.loads(args.layout.read_text())), indent=2))
