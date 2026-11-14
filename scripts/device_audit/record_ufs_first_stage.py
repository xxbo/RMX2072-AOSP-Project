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


def full_read(console, inode, device, size, stage, pid=1):
    major, minor = map(int, device.split(':'))
    dev = (major << 20) | minor  # Kernel dev_t recorded by the probe.
    pattern = (rf'^\[\s*([0-9.]+)\]\[\s*T{pid}\] m1_file_read: [^\n]* ino={inode} '
               rf'dev={dev} count=(\d+) result={size}$')
    for found in re.finditer(pattern, console, re.MULTILINE):
        if float(found[1]) > stage and int(found[2]) >= size:
            return dict(at_seconds=float(found[1]), pid=pid, inode=inode, device=device,
                        requested_bytes=int(found[2]), returned_bytes=size)
    raise ValueError(f'No complete post-stage read of inode {inode} on {device}')


def record(directory, layout, *, console_tail=False):
    def read(name):
        return (directory/name).read_bytes().decode('ascii', errors='replace').replace('\r', '')
    serial, console = read('acm.log'), read('console-ramoops-0')
    identity = json.loads((directory/'identity.json').read_text())
    if not identity['kernel'].startswith('6.18.'):
        raise ValueError('Unexpected kernel')
    boot = match(r'^M1EVENT boot_id=([0-9a-f-]{36})$', serial)[1]
    handoff = ('kernel='+re.escape(identity['kernel'])+' phase=android-first-stage-handoff trial='+
               re.escape(identity['trial'])+' boot_id='+boot+'$')
    # Heavy service logging can wrap the console ring before the next boot.
    # The same supervisor writes the same handoff marker to the pmsg ring.
    if not re.search(handoff, console, re.MULTILINE):
        match(handoff, read('pmsg-ramoops-0'))
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
        avb_text = f"Returning avb_handle for '/{name}' with status: Success"
        avb = re.search(r'^\[\s*([0-9.]+)\]\[\s*T1\].+'+avb_text+'$', console, re.M)
        if avb:
            avb_seconds = float(avb[1])
        else:
            kmsg = match(r'^\d+,\d+,(\d+),[^\n]*,caller=T1;init: .+'+avb_text+'$', serial)
            avb_seconds = int(kmsg[1])/1_000_000
        mounts[name] = dict(node=node, device=device, linear_device=table[4], super=backing[2],
                            extents=len(actual), root_sha256=tree['root_digest'], avb_at_seconds=avb_seconds,
                            verity_status=status, pid=1, filesystem='ext4', readonly=True, mount_rc=0)
    if console_tail:
        # The circular console may start after second stage on a verbose HAL trial.
        match(r'^\[\s*([0-9.]+)\]\[\s*T1\] init:', console)
        if 'init second stage started!' in console or 'permissive=0' not in console:
            raise ValueError('Expected a post-handoff console tail with enforcing evidence')
        enforcing = second = None
        reads = {}
    else:
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


def vendor_services(directory, trial):
    serial = (directory/'acm.log').read_text(errors='replace')
    console = (directory/'console-ramoops-0').read_text(errors='replace')
    mounts = trial['mounts']
    stage = trial['second_stage_seconds']
    reads = {}
    for rc in ('init.zygote64_32.rc', 'init.zygote64.rc', 'init.boringssl.zygote64_32.rc'):
        path = '/system/etc/init/hw/'+rc
        target = match(r'^M1EVENT read_target='+re.escape(path)+r' ino=(\d+) bytes=(\d+)$', serial)
        parsed = match(r'^\[\s*([0-9.]+)\]\[\s*T1\] init: Parsing file '+re.escape(path)+r'\.\.\.$', console)
        if float(parsed[1]) <= stage:
            raise ValueError('Import outside second stage: '+path)
        reads[path] = full_read(console, int(target[1]), mounts['system']['device'], int(target[2]), stage)
        reads[path]['parsing_seconds'] = float(parsed[1])
    start = match(r"^\[\s*([0-9.]+)\]\[\s*T1\] init: \.\.\. started service 'vold' has pid (\d+)$", console)
    target = match(r'^M1EVENT read_target=/vendor/etc/fstab\.qcom ino=(\d+) bytes=(\d+)$', serial)
    fstab = full_read(console, int(target[1]), mounts['vendor']['device'], int(target[2]), stage, int(start[2]))
    caller = match(r'Caller\(pid='+start[2]+r',uid=0,sid=u:r:vold:s0\)', console)
    fstab.update(service='vold', domain='u:r:vold:s0', service_start_seconds=float(start[1]),
                 domain_evidence=caller[0])
    return dict(zygote_imports=reads, vold_fstab=fstab, adb=adb_observations(directory, trial))


def adb_observations(directory, trial):
    events = [json.loads(row) for row in (directory/'host-events.jsonl').read_text().splitlines()]
    handoff = next(e for e in events if e['event'] == 'handoff_requested' and e['boot_id'] == trial['boot_id'])
    recovery = next(e for e in events if e['event'] == 'recovery_boot' and e['boot_id'] != trial['boot_id'])
    samples = map(json.loads, (directory/'adb.jsonl').read_text().splitlines())
    rows = [r for r in samples if handoff['monotonic'] <= r['monotonic'] <= recovery['monotonic']]
    if not rows:
        raise ValueError('No ADB observations within the test interval')
    times = [handoff['monotonic'], *[r['monotonic'] for r in rows], recovery['monotonic']]
    states = sorted({line.split()[1] for row in rows for line in row.get('transports', [])})
    errors = sum('error' in row for row in rows)
    identities = [fields for r in rows for fields in r.get('identity', {}).values()]
    confirmed = any(len(fields) == 5 and fields[1:] == ['37', 'running', trial['kernel'],
                    trial['boot_id']] for fields in identities)
    result = 'NO_TRANSPORT_OBSERVED'
    if confirmed:
        result = 'API37_SHELL_VERIFIED'
    elif states:
        result = 'TRANSPORT_PRESENT_IDENTITY_UNVERIFIED'
    elif errors:
        result = 'INCOMPLETE_SAMPLING'
    return dict(result=result,
                samples=len(rows), errors=errors, transport_states=states,
                interval_seconds=round(times[-1]-times[0], 3),
                maximum_sample_gap_seconds=round(max(b-a for a,b in zip(times,times[1:])), 3),
                diagnostic_acm_seen=any(row.get('diagnostic_acm') for row in rows),
                raw_sha256={name:hashlib.sha256((directory/name).read_bytes()).hexdigest()
                            for name in ('adb.jsonl', 'host-events.jsonl')})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture', required=True, type=Path)
    p.add_argument('--layout', required=True, type=Path)
    p.add_argument('--vendor-services', action='store_true')
    args = p.parse_args()
    trial = record(args.capture, json.loads(args.layout.read_text()))
    if args.vendor_services:
        trial.update(vendor_services(args.capture, trial))
    print(json.dumps(trial, indent=2))
