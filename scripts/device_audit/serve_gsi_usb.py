"""Serve one hash-pinned Android 17 image read-only to the RMX2072 diagnostic ACM."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import time
import zlib

from check_verity import verified_vbmeta
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
    console.write(b"\nprintf '\\nMOUNT_''BEGIN\\n'; cat /run/gsi17-run.log; "
                  b"cat /run/gsi17/backend.log 2>/dev/null; dmesg | grep -Ei 'dm-user|EXT4-fs|verity:|corrupted' | tail -12; "
                  b"printf '\\nMOUNT_''END\\n'\n")
    rows = read_until_line(console,b'MOUNT_END',20).replace(b'\r',b'').splitlines()
    return b'\n'.join(rows[rows.index(b'MOUNT_BEGIN')+1:rows.index(b'MOUNT_END')]).decode(errors='replace')


def verify_mount(log, ref, footer_digest, userspace=False):
    lines = log.splitlines()
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
    checks = ['last_block_sha256='+footer_digest,'cleanup=0','ro.system.build.version.release=17',
              'ro.system.build.version.sdk=37','ro.system.build.id='+ref['build']]
    checks += [f"file={p} sha256={v['sha256']}" for p,v in ref['files'].items()]
    m = re.search(r'^mounted=/run/gsi17/mnt fs=ext4 options=(\S+)$',log,re.M)
    required = {'ro','nodev','nosuid'} if userspace else {'ro','nodev','nosuid','noexec'}
    if (not m or not required <= set(m[1].split(',')) or
            not re.search(r'^verity_status=0 '+str(blocks*8)+r' verity V(?: -)?$',log,re.M)):
        raise ValueError('No healthy read-only ext4/verity mount')
    for check in checks:
        if check not in lines:
            raise ValueError('Missing mount result: '+check)
    if userspace and ('android_toybox_read=match' not in lines or
                      not re.search(r'^android_toybox_uname=6\.18\.[^\n]+$',log,re.M)):
        raise ValueError('Android userspace execution was not observed')


def serve(console, image, ref, deadline, stats, userspace=False):
    mode = b'userspace' if userspace else b'mount'
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
    p.add_argument('--userspace',action='store_true',help='Run the GSI toybox with its bootstrap linker inside the verified root')
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
                rc, report['first_requests'] = serve(console,image,ref,until,stats,a.userspace)
                log = transcript(console)
                (a.output/'mount.txt').write_text(log+'\n',encoding='utf-8')
                if rc or not stats['tree_bytes'] or not stats['data_bytes']:
                    raise ValueError(f'Mount failed rc={rc}, served {stats}')
                verify_mount(log,ref,footer,a.userspace)
                report.update(status='verified',last_block_sha256=footer)
    finally:
        (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report),flush=True)


if __name__ == '__main__':
    main()
