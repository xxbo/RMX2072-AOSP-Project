"""Correlate same-boot PID 1 mappings and ftrace errors with the pinned GSI extents."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from record_m1_vendor import digest, install_record, read, require, verified_recovery


def sector_for_offset(runs, offset, bs):
    page = offset//bs
    for start, count in runs:
        if page < count:
            return (start+page)*bs//512 if start is not None else None
        page -= count
    raise ValueError('Page beyond end of inode')


def faults(console, events, fs):
    # Use complete fields. ramoops on this handset also contains damaged lines.
    ring = console.partition('Dumping ftrace buffer:')[2]
    mappings = {}
    for m in re.finditer(r'^M1EVENT map=[\da-f]+-[\da-f]+ \S+ \S+ fe:01 (\d+) +(/\S+)$', events, re.M):
        mappings[int(m[1])] = m[2]
    faults = {}
    for m in re.finditer(r'\binit-1\s+\S+ (\d+)us : mm_filemap_fault: dev=254:1 ino=([\da-f]+) ofs=(\d+)\b', ring):
        ino, offset = int(m[2],16), int(m[3])
        if ino not in mappings:
            continue
        path = mappings[ino]
        node = fs.get(path)
        require(node.inum == ino, 'GSI inode does not match the live mapping')
        sector = sector_for_offset(node.dataruns(), offset, fs.block_size)
        bio = re.search(r'block_bio_complete: 254,1 R '+str(sector)+r' \+ 8 \[-5\]', ring)
        if bio:
            faults[ino,offset] = dict(path=path, inode=ino, file_offset=offset, gsi_sector=sector,
                                      sectors=8, block_errno=5, fault_trace=m[0], bio_trace=bio[0])
    return list(faults.values())


def record(work, trial, vendor, image):
    from dissect.extfs import ExtFS

    live = work/(trial+'-live')
    run = read(live/'result.json')
    if run.get('status') == 'fixture-exited' and run.get('fixture_rc'):
        package = work/(trial+'-package')
        pack = read(package/'control.json')
        transcript = (live/'mount.txt').read_text()
        require(run['trial'] == trial and 'Please specify both major number and minor number.' in transcript,
                'Unexpected fixture failure')
        return dict(trial=trial, boot_sha256=pack['boot_sha256'], kernel=run['identity']['kernel'],
                    fixture_rc=run['fixture_rc'], phase='dmsetup before PID 1 handoff',
                    error='Please specify both major number and minor number.', usb=run['stats'],
                    recovery=verified_recovery(work/(trial+'-trial'),package,pack,live/'restored.txt',None))
    base = install_record(work,trial,vendor,live/'restored.txt')
    rows = (live/'policy-events.txt').read_text()
    console = (live/'console-ramoops-0').read_bytes().decode('ascii', errors='replace')
    require(base['boot_id'] in rows and 'fault_trace=armed' in rows, 'Missing live trace identity')
    with image.open('rb') as src:
        require(hashlib.file_digest(src,'sha256').hexdigest() == base['gsi_sha256'], 'GSI hash mismatch')
        src.seek(0)
        fs = ExtFS(src)
        matched = faults(console, rows, fs)
        host_requests = {int(line.split()[0]) for line in (live/'gsi-reads.txt').read_text().splitlines()}
        next_reads = []
        for path in ('/system/etc/selinux/plat_file_contexts', '/system/build.prop'):
            node = fs.get(path)
            sector = sector_for_offset(node.dataruns(),0,fs.block_size)
            failure = f'I/O error: sector {sector}: no user-space daemon for dm-user/rmx-gsi17-source target'
            if sector*512 in host_requests or failure in console:
                next_reads.append(dict(path=path, inode=node.inum, file_offset=0, gsi_sector=sector,
                                       kernel_io_error=failure in console, host_request=sector*512 in host_requests))
    base['observations'] = [r for r in base['observations'] if not r.startswith('map=')]
    base['faults_with_matching_io_error'] = matched
    base['raw_console_sha256'] = digest(live/'console-ramoops-0')
    base['host_read_list_sha256'] = digest(live/'gsi-reads.txt')
    rd = read(work/(trial+'-rd')/'ramdisk-provenance.json')
    if 'gsi_seed_sha256' in rd:
        base['gsi_seed_sha256'] = rd['gsi_seed_sha256']
        base['gsi_seed_ranges_sha256'] = rd['gsi_seed_ranges_sha256']
        require(any(s.startswith('seed_backing=254:2 ram=7:1 ') and s.endswith(rd['gsi_seed_ranges_sha256'])
                    for s in base['observations']), 'Runtime seed differs from packaged seed')
        base['selected_fallback_reads'] = next_reads
    base['kernel_observations'] = []
    for pattern in (r'I/O error: sector \d+: no user-space daemon for dm-user/rmx-gsi17-source target',
                    r'signal_generate: sig=7 errno=0 code=2 comm=init pid=1 grp=0 res=0',
                    r'sched_process_exec: filename=/system/bin/init pid=1 old_pid=1',
                    r'\[\s*T1\] init: init second stage started!',
                    r'Kernel panic - not syncing: Attempted to kill init! exitcode=0x[\da-f]{8}'):
        for m in re.finditer(pattern, console):
            if m[0] not in base['kernel_observations']:
                base['kernel_observations'].append(m[0])
    messages = re.findall(r"^\[\s*(\d+\.\d+)\]\[\s*T1\] init: (init second stage started!|Couldn't load property file '/system/build.prop': [^\r\n]+|Unable to read config file '/system/etc/init/hw/init.rc': [^\r\n]+|Failed to read task profiles from /etc/cgroups.json: [^\r\n]+)$",
                          console, re.M)
    if messages:
        base['second_stage_messages'] = [dict(seconds=float(t),message=m) for t,m in messages]
    if any(m == 'init second stage started!' for _,m in messages):
        base['results']['second_stage_exec'] = 'PASS'
    return base


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('work','vendor','image','output'):
        p.add_argument('--'+arg,type=Path,required=True)
    p.add_argument('--trial',required=True,action='append')
    a = p.parse_args()
    records = [record(a.work,trial,a.vendor,a.image) for trial in a.trial]
    row = records[0] if len(records) == 1 else dict(trials=records)
    with a.output.open('x',encoding='utf-8',newline='\n') as out:
        out.write(json.dumps(row,indent=2)+'\n')
