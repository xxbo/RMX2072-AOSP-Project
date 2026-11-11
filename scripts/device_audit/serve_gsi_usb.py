"""Serve one hash-pinned Android 17 image read-only to the RMX2072 diagnostic ACM."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import struct
import time
import zlib

from check_verity import verified_vbmeta, verity_args
from usb_edl_return import ACM, END, QUERY, parse_identity

REFERENCE = Path(__file__).resolve().parents[2]/'build/device/gsi17-mount-reference.json'


def verify_image(stream, reference):
    stream.seek(0)
    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    size = stream.seek(0, 2)
    if digest != reference['image_sha256'] or size != reference['image_bytes']:
        raise ValueError('Expected the exact CP3A.260905.010 raw system.img')
    stream.seek(-4096, 2)
    last = stream.read(4096)
    footer = last[-64:]
    original, offset, length = struct.unpack_from('>QQQ', footer, 12)
    if (footer[:4] != b'AVBf' or original != reference['hashtree']['image_bytes'] or
            not 256 <= length <= 65536 or offset+length > size-64):
        raise ValueError('Invalid GSI AVB footer')
    stream.seek(offset)
    _, key, _, trees = verified_vbmeta(stream.read(length))
    if hashlib.sha256(key).hexdigest() != reference['key_sha256'] or trees != {'system':reference['hashtree']}:
        raise ValueError('Unexpected GSI signer or hashtree')
    return hashlib.sha256(last).hexdigest()


def read_packet(stream, image_size, offset, count):
    if (not 0 < count <= 4096 or offset < 0 or offset % 512 or count % 512 or
            offset + count > image_size):
        raise ValueError(f'Invalid image read: {offset}+{count}')
    stream.seek(offset)
    data = stream.read(count)
    if len(data) != count:
        raise IOError('Short image read')
    return struct.pack('<I',zlib.crc32(data)) + data


def read_until_line(console, end, timeout):
    data = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data.extend(console.read_until(b'\n'))
        if end in data.replace(b'\r',b'').splitlines():
            return bytes(data)
        if len(data) > 256*1024:
            raise ValueError('Unexpectedly large console reply')
    raise TimeoutError(end.decode())


def transcript(console):
    def query(cmd):
        console.write(b"\nprintf '\\nMOUNT_''BEGIN\\n'; "+cmd+b"; printf '\\nMOUNT_''END\\n'\n")
        rows = read_until_line(console,b'MOUNT_END',8).replace(b'\r',b'').splitlines()
        return b''.join(rows[rows.index(b'MOUNT_BEGIN')+1:rows.index(b'MOUNT_END')])

    path = b'/run/gsi17-transcript'
    meta = query(b"{ cat /run/gsi17-run.log; cat /run/gsi17/backend.log 2>/dev/null; "
                 b"dmesg | grep -Ei 'dm-user|EXT4-fs|verity:|corrupted' | tail -12; } > "+path+
                 b"; printf '%s %s' \"$(wc -c < "+path+b")\" \"$(sha256sum "+path+b" | cut -d' ' -f1)\"")
    size, digest = meta.split()
    size = int(size)
    if not 0 < size <= 256*1024 or not re.fullmatch(b'[0-9a-f]{64}',digest):
        raise ValueError('Unexpected diagnostic transcript metadata')
    data = bytearray()
    for pos in range(0,size,384):
        cmd = b'dd if='+path+f' bs=384 skip={pos//384} count=1 2>/dev/null | base64'.encode()
        data.extend(base64.b64decode(query(cmd),validate=True))
    if len(data) != size or hashlib.sha256(data).hexdigest().encode() != digest:
        raise ValueError('Incomplete USB transcript')
    return data.decode(errors='replace')


def verify_gsi_tables(log, ref):
    tree = ref['hashtree']
    size = ref['image_bytes']//512
    blocks = tree['image_bytes']//4096
    table = re.search(r'^verity_table=0 (\d+) verity 1 (\d+:\d+) (\d+:\d+) (.*)$', log, re.M)
    if (not table or table[2] != table[3] or int(table[1]) != blocks*8 or
            table[4].split() != ['4096','4096',str(blocks),str(tree['tree_offset']//4096),
                                 tree['algorithm'],tree['root_digest'],tree['salt']]):
        raise ValueError('Loaded table differs from signed GSI descriptor')
    # The dm-user driver may omit its construction arguments from table status.
    if not re.search(r'^source_table=0 '+str(size)+r' user(?:\s.*)?$',log,re.M):
        raise ValueError('Unexpected dm-user source table')


def verify_mount(log, ref, footer_digest, userspace=False, *, combined=False):
    verify_gsi_tables(log, ref)
    lines = log.splitlines()
    blocks = ref['hashtree']['image_bytes']//4096
    checks = ['last_block_sha256='+footer_digest,'cleanup=0','ro.system.build.version.release=17',
              'ro.system.build.version.sdk=37','ro.system.build.id='+ref['build']]
    checks += [f"file={p} sha256={v['sha256']}" for p,v in ref['files'].items()]
    m = re.search(r'^mounted=/run/gsi17/mnt fs=ext4 options=(\S+)$',log,re.M)
    required = {'ro','nodev','nosuid'} if userspace or combined else {'ro','nodev','nosuid','noexec'}
    if (not m or not required <= set(m[1].split(',')) or
            ((userspace or combined) and 'noexec' in m[1].split(',')) or
            not re.search(r'^verity_status=0 '+str(blocks*8)+r' verity V(?: -)?$',log,re.M)):
        raise ValueError('No healthy read-only ext4/verity mount')
    for check in checks:
        if check not in lines:
            raise ValueError('Missing mount result: '+check)
    if userspace and ('android_toybox_read=match' not in lines or
                      not re.search(r'^android_toybox_uname=6\.18\.[^\n]+$',log,re.M)):
        raise ValueError('Android userspace execution was not observed')
    if combined:
        return verify_policy_probe(log)


def verify_first_stage(log, ref, footer, vendor_hash=None, check_genfs=False):
    verify_gsi_tables(log, ref)
    rows = set(log.splitlines())
    pin = json.loads((REFERENCE.parent/'android17-first-stage-source.json').read_text())['init_sha256']
    sectors = ref['hashtree']['image_bytes']//512
    policy_exec = 'exec_pid=1 path=/system/bin/init arg=selinux_setup'
    executable = ref['init_sha256'] if vendor_hash and policy_exec in rows else pin
    required = {'exec_pid=1 path=/init staged_inode_match=1', 'init_sha256='+pin,
                'pid1_sha256='+executable, 'last_block_sha256='+footer}
    if required-rows or not re.search(r'^verity_status=0 '+str(sectors)+r' verity V(?: -| 0)?$', log, re.M):
        raise ValueError('Unverified PID 1 or GSI source')
    boot = re.search(r'^boot_id=([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})$', log, re.M)
    device = re.search(r'^gsi_device=(dm-[0-9]+) dev=(\d+:\d+)$', log, re.M)
    mounts = [s for s in log.splitlines() if s.startswith('mount_pid=1 ')]
    stop = re.search(r'^trial_stop=([a-z-]+)$', log, re.M)
    if not (boot and device and mounts and stop):
        raise ValueError('Incomplete first-stage transcript')
    partition = [s for s in mounts if ' target=/system ' in s]
    if vendor_hash:
        vendor = re.search(r'^vendor_device=(loop\d+) dev=(\d+:\d+) image_sha256=([0-9a-f]{64})$',log,re.M)
        if not vendor or vendor[3] != vendor_hash:
            raise ValueError('Unexpected project vendor backing')
        for entry, mountpoint in ((device, '/'), (vendor, '/vendor')):
            if not re.search(r'^pid1_mountinfo=\d+ \d+ '+entry[2]+' / '+mountpoint+r' ro\b.* - ext4 /dev/block/'+entry[1]+r' ',log,re.M):
                raise ValueError('Missing read-only PID 1 mount at '+mountpoint)
        for entry, target in ((device, '/system'), (vendor, '/vendor')):
            if not any(re.fullmatch('mount_pid=1 source=/dev/block/'+entry[1]+' target='+target+
                                    r' fs=ext4 flags=0x[0-9a-f]+ rc=0', m) for m in mounts):
                raise ValueError('Missing successful Android mount at '+target)
        if (policy_exec not in rows or 'mounted_vendor_fstab=match' not in rows or
                'mounted_vendor_policy_version=202604' not in rows or
                'mount_pid=1 source=/system target=/ fs=(null) flags=0x2000 rc=0' not in rows or
                not re.search(r'^pid1_cmdline=/system/bin/init selinux_setup *$', log, re.M)):
            raise ValueError('Project vendor or SELinux exec did not reach the checkpoint')
        messages = [row for row in log.splitlines() if re.search(r'\[\s*T1\] init: .*SELinux policy',row)]
        if not messages:
            raise ValueError('Missing PID 1 SELinux setup log')
        result = dict(boot_id=boot[1], first_mount=mounts[0], partition_mounts=partition,
                      vendor_sha256=vendor_hash, policy_messages=messages, stop=stop[1])
        if check_genfs:
            strict = re.search(r'^strict_policy_sha256=([0-9a-f]{64})$', log, re.M)
            if (not strict or 'strict_compile_rc=0' not in rows or stop[1] != 'policy-load-open' or
                    not re.search(r'\[\s*T1\] init: Using /system/etc/selinux/plat_sepolicy_genfs_202604.cil for genfs labels',log)):
                raise ValueError('Project genfs selection or strict compile failed: see mount.txt')
            result['strict_policy_sha256'] = strict[1]
        return result
    if partition and partition[-1].endswith(' rc=0'):
        if (f'source=/dev/block/{device[1]} target=/system fs=ext4 ' not in partition[-1] or
                not re.search(r'^pid1_mountinfo=\d+ \d+ '+device[2]+r' / /system ro\b.* - ext4 ',log,re.M)):
            raise ValueError('PID 1 mountinfo does not match the GSI verity device')
    return dict(boot_id=boot[1], first_mount=mounts[0], partition_mounts=partition, stop=stop[1])


def init_policy_observations(log):
    # Each rc is printed before its captured kmsg. Direct secilc diagnostics
    # must never be attributed to init's compiler child.
    stages = {}
    for start, end in [('init_selinux_setup', 'secilc_rc'), ('init_with_f20_mapping', 'comparison_compiler_rc')]:
        capture = re.search(r'^'+start+r'_rc=(\d+)\n(.*?)^'+end+r'=\d+$', log, re.M | re.S)
        if not capture:
            raise ValueError('Missing init capture: '+start)
        lines = capture[2].splitlines()
        if '<6>init: Compiling SELinux policy' not in lines:
            raise ValueError('Init did not reach policy compilation: '+start)
        if ('<6>init: Loading SELinux policy' not in lines and
                not any(s.startswith('<3>init: /system/bin/secilc:') for s in lines)):
            raise ValueError('No compiler child output in init log: '+start)
        stages[start] = int(capture[1])
    return stages


def verify_policy_probe(log):
    stock = json.loads((REFERENCE.parent/'f20-verity-reference.json').read_text())
    odm = json.loads((REFERENCE.parent/'f20-odm-verity-reference.json').read_text())
    rows = set(log.splitlines())
    required = {'odm_signer='+odm['key_sha256'], 'android_read_vendor_odm=match',
                'vendor_policy_version=30.0', 'policy_cleanup=0', 'cleanup_status=0',
                '<6>init: Opening SELinux policy', '<6>init: Compiling SELinux policy'}
    required.update(f'vbmeta={n} sha256={h}' for n,h in stock['gpt_vbmeta_sha256'].items())
    for name, part in [('vendor', stock['partitions']['vendor']), ('odm', odm),
                       ('system', stock['partitions']['system'])]:
        tree = part['descriptor']
        sectors = tree['image_bytes']//512
        required.update({f'verified={name} sectors={sectors} sha256='+part['verified_data_sha256'],
                         f'health={name} 0 {sectors} verity V 0', f'verity_cleanup={name} rc=0'})
        table = re.search(r'^verity_table='+name+r' 0 (\d+) verity 1 (\d+:\d+) (.*)$', log, re.M)
        linear = re.search(r'^mapped='+name+r' sectors=(\d+) ro=1$', log, re.M)
        if not table or not linear or int(table[1]) != sectors:
            raise ValueError(f'Missing {name} verity table')
        dev = table[2]
        fec = str(tree['fec_offset']//tree['data_block_bytes'])
        args = verity_args(tree,dev,int(linear[1])*512)
        if ['1',dev]+table[3].split() != args+['8','use_fec_from_device',dev,'fec_blocks',fec,'fec_start',fec,'fec_roots','2']:
            raise ValueError(f'{name} verity descriptor mismatch')
        required.update(f'file={name}/{p} sha256={h}' for p,h in part['files'].items())
        if name == 'system':
            continue  # The stock system supplies the comparison CIL outside the GSI root.
        mount = re.search(r'^combined_mount=/run/gsi17/mnt/'+name+r' fs=erofs options=(\S+)$',log,re.M)
        if not mount or not {'ro','nodev','nosuid','noexec'} <= set(mount[1].split(',')):
            raise ValueError(f'Missing combined {name} mount')
    if required-rows:
        raise ValueError('Missing combined results: '+', '.join(sorted(required-rows)))
    count = re.search(r'^neverallow_reports=(\d+)$',log,re.M)
    conflicts = re.findall(r'^conflict=(\S+) allow=\S* source=(\S+)$',log,re.M)
    if not count or len(conflicts) != int(count[1]):
        raise ValueError('Incomplete neverallow conflict index')
    return init_policy_observations(log)


def serve(console, image, ref, deadline, stats, mode):
    console.write(b"\n/bin/gsi17-mount "+mode+b" >/run/gsi17-run.log 2>&1; rc=$?; printf '\\nGSI17_''EXIT %s\\n' \"$rc\"\n")
    pending = bytearray()
    traces = []
    while time.monotonic() < deadline:
        pending.extend(console.read_until(b'\n'))
        if len(pending) > 4096:
            raise ValueError('Unframed device request')
        if not pending.endswith(b'\n'):
            continue
        line = bytes(pending).strip()
        pending.clear()
        if re.fullmatch(rb'GSI17_EXIT [0-9]+',line):
            return int(line.split()[1]), traces
        match = re.fullmatch(rb'GSI17 READ ([0-9]+) ([0-9]+)',line)
        if not match:
            if line.startswith(b'GSI17 READ'):
                raise ValueError('Malformed device request')
            continue
        offset, count = map(int,match.groups())
        packet = read_packet(image,ref['image_bytes'],offset,count)
        for pos in range(0,len(packet),1024):
            chunk = packet[pos:pos+1024]
            if console.write(chunk) != len(chunk):
                raise IOError('Short serial write')
            time.sleep(.001)
        stats['requests'] += 1
        stats['bytes'] += count
        if offset < ref['hashtree']['image_bytes']:
            stats['data_bytes'] += count
        elif offset < ref['hashtree']['fec_offset']:
            stats['tree_bytes'] += count
        if len(traces) < 12:
            traces.append([offset,count])
    raise TimeoutError('Mount did not finish before the return window')


def main():
    import serial
    from serial.tools import list_ports

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image',type=Path,required=True)
    p.add_argument('--trial',required=True)
    p.add_argument('--output',type=Path,required=True)
    modes = p.add_mutually_exclusive_group()
    modes.add_argument('--userspace',action='store_true',help='Run the GSI toybox with its bootstrap linker inside the verified root')
    modes.add_argument('--combined',action='store_true',help='Mount F.20 vendor and odm and collect the Android policy probe')
    modes.add_argument('--first-stage',action='store_true',help='Hand PID 1 to Android and capture its mount syscalls')
    modes.add_argument('--project-vendor-report',type=Path,help='Verify switched GSI root, project vendor image and SELinux setup')
    a = p.parse_args()
    if not re.fullmatch(r'ufs-host-g3-gsi17-[A-Za-z0-9-]+',a.trial):
        p.error('Unexpected trial id')
    a.output.mkdir(parents=True,exist_ok=False)
    ref = json.loads(REFERENCE.read_text())
    stats = dict(requests=0,bytes=0,data_bytes=0,tree_bytes=0)
    report = dict(trial=a.trial,stats=stats,status='failed')
    try:
        with a.image.open('rb') as image:
            footer = verify_image(image,ref)
            report['image_sha256'] = ref['image_sha256']
            until = time.monotonic()+150
            while time.monotonic() < until:
                ports = [d.device for d in list_ports.comports() if (d.vid,d.pid)==ACM]
                if len(ports) == 1:
                    break
                time.sleep(.25)
            else:
                raise TimeoutError('No diagnostic ACM')
            with serial.Serial(ports[0],115200,timeout=.25,write_timeout=4) as console:
                console.write(QUERY)
                ident = parse_identity(read_until_line(console,END,15))
                if ident['trial'] != a.trial:
                    raise ValueError('Unexpected live trial')
                report['identity'] = ident
                until = time.monotonic()+ident['timer_seconds']-ident['uptime_seconds']-30
                first_stage = a.first_stage or a.project_vendor_report
                mode = b'firststage' if first_stage else b'combined' if a.combined else b'userspace' if a.userspace else b'mount'
                rc, report['first_requests'] = serve(console,image,ref,until,stats,mode)
                log = transcript(console)
                captured = log.encode('utf-8')
                (a.output/'mount.txt').write_bytes(captured)
                report['transcript_sha256'] = hashlib.sha256(captured).hexdigest()
                if first_stage:
                    if rc:
                        raise ValueError(f'First-stage capture returned {rc}: see mount.txt')
                    vendor = json.loads(a.project_vendor_report.read_text()) if a.project_vendor_report else {}
                    check_genfs = '/etc/selinux/genfs_labels_version.txt' in vendor.get('files', {})
                    report.update(status='handoff-observed', **verify_first_stage(log,ref,footer,vendor.get('sha256'),check_genfs))
                    return
                if rc or not stats['tree_bytes'] or not stats['data_bytes']:
                    raise ValueError(f'Mount failed rc={rc}, served {stats}')
                observation = verify_mount(log,ref,footer,a.userspace,combined=a.combined)
                if a.combined:
                    report['init_exit_codes'] = observation
                report.update(status='verified',last_block_sha256=footer)
    finally:
        (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report),flush=True)


if __name__ == '__main__':
    main()
