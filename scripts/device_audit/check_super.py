"""Cross-check an RMX2072 RAM diagnostic against F.20 liblp and live dm-linear devices."""
import argparse
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path

TARGETS = ('system', 'vendor', 'product')
BLOCK = 4096
SLOT_BYTES = 65536
SLOTS = 2
PREFIX = 3 * BLOCK + 2 * SLOTS * SLOT_BYTES


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prefix_checks(data):
    if len(data) != PREFIX:
        raise ValueError('Unexpected F.20 LP prefix length')
    geometry = data[BLOCK:2*BLOCK]
    if geometry != data[2*BLOCK:3*BLOCK]:
        raise ValueError('LP geometry copies differ')
    magic, size = struct.unpack_from('<2I', geometry)
    if ((magic, size) != (0x616c4467, 52)
            or struct.unpack_from('<3I', geometry, 40) != (SLOT_BYTES, SLOTS, BLOCK)
            or sha(geometry[:8] + bytes(32) + geometry[40:size]) != geometry[8:40].hex()):
        raise ValueError('Unexpected or corrupt F.20 geometry')
    digests = []
    for slot in range(SLOTS):
        offset = 3*BLOCK + slot*SLOT_BYTES
        primary = data[offset:offset+SLOT_BYTES]
        backup = offset + SLOTS*SLOT_BYTES
        if primary != data[backup:backup+SLOT_BYTES]:
            raise ValueError(f'Slot {slot} primary and backup differ')
        magic, major, minor, hsize = struct.unpack_from('<IHHI', primary)
        tsize, = struct.unpack_from('<I', primary, 44)
        if (magic, major, minor, hsize) != (0x414c5030, 10, 0, 128) or not 0 < tsize <= SLOT_BYTES-hsize:
            raise ValueError(f'Unexpected slot {slot} header')
        header = primary[:12] + bytes(32) + primary[44:hsize]
        if sha(header) != primary[12:44].hex() or sha(primary[hsize:hsize+tsize]) != primary[48:80].hex():
            raise ValueError(f'Slot {slot} header or tables checksum mismatch')
        digests.append(sha(primary[:hsize+tsize]))
    return {'prefix_sha256': sha(data), 'slot_metadata_sha256': digests}


def lp_tables(dump):
    body = dump.split('Partition table:\n', 1)[1].split('Super partition layout:', 1)[0]
    result = {}
    for segment in body.split('------------------------'):
        name = re.search(r'^\s*Name: ([\w.-]+)$', segment, re.M)
        if not name:
            continue
        name = name[1]
        if name in result:
            raise ValueError(f'Duplicate partition: {name}')
        entries = result[name] = []
        total = 0
        extent_text = segment.split('Extents:', 1)[1]
        for line in extent_text.strip().splitlines():
            entry = re.fullmatch(r'\s*(\d+) \.\. (\d+) linear super (\d+)\s*', line)
            if not entry:
                raise ValueError(f'Unsupported F.20 extent: {line}')
            start, end, physical = map(int, entry.groups())
            if start != total or end < start:
                raise ValueError(f'Noncontiguous logical sectors in {name}')
            entries.append([start, end-start+1, physical])
            total = end+1
    if not all(result.get(n) for n in TARGETS):
        raise ValueError('Expected three populated logical partitions')
    return result


def capture(serial):
    def adb(cmd):
        # Fixed board commands only. exec-out keeps binary metadata intact.
        return subprocess.check_output(['adb', '-s', serial, 'exec-out', "su -c '"+cmd+"'"], timeout=120)
    identity = adb('getprop ro.product.model; getprop ro.build.display.id; getprop sys.boot_completed').decode().split()
    if identity != ['RMX2072', 'RMX2072_11_F.20', '1']:
        raise ValueError('Expected a booted F.20 handset')
    source = '/dev/block/bootdevice/by-name/super'
    node = adb('readlink -f '+source).decode().strip().split('/')[-1]
    dev = adb('cat /sys/class/block/'+node+'/dev').decode().strip()
    prefix = adb('dd if='+source+' bs=4096 count=67 2>/dev/null')
    reference = prefix_checks(prefix)
    slots = [lp_tables(adb(f'lpdump -s {slot}').decode().replace('\r', '')) for slot in range(SLOTS)]
    live = {}
    hashes = {}
    for name in TARGETS:
        table = adb('dmctl table '+name).decode().splitlines()
        live[name] = []
        for line in table[1:]:
            if not line.strip():
                continue
            row = re.fullmatch(r'(\d+)-(\d+): linear, '+re.escape(dev)+r' (\d+)', line.strip())
            if not row:
                raise ValueError(f'Unexpected F.20 kernel target: {line}')
            start, stop, physical = map(int, row.groups())
            live[name].append([start, stop-start, physical])
        hashes[name] = adb('sha256sum /dev/block/mapper/'+name).decode().split()[0]
        if not re.fullmatch(r'[0-9a-f]{64}', hashes[name]):
            raise ValueError(f'No complete reference hash for {name}')
    matches = [i for i, tables in enumerate(slots) if all(tables[n] == live[n] for n in TARGETS)]
    if matches != [0]:
        raise ValueError(f'F.20 runtime tables select unexpected slots: {matches}')
    return dict(**reference, slots=slots, runtime_selected_slot=matches[0], reference_hashes=hashes)


def verify_metadata(ref, text):
    if not re.search(r'^'+ref['prefix_sha256']+r'\s+/run/rmx-super/prefix$', text, re.M):
        raise ValueError('6.18 LP geometry and metadata prefix differs from F.20')
    slots = []
    current = None
    for line in text.splitlines():
        if line.startswith('slot='):
            if line != f'slot={len(slots)}':
                raise ValueError('Unexpected slot order')
            current = {}
            slots.append(current)
            continue
        if current is not None:
            row = re.fullmatch(r'([\w.-]+) (\d+) (\d+) (\d+)', line)
            if row:
                current.setdefault(row[1], []).append(list(map(int, row.groups()[1:])))
    if slots != ref['slots']:
        raise ValueError('6.18 logical extent tables differ from F.20')
    return [{'slot': i, 'partitions': len(t), 'linear_extents': sum(map(len, t.values()))} for i, t in enumerate(slots)]


def verify_maps(ref, text):
    if 'cleanup_status=0' not in text.splitlines():
        raise ValueError('Diagnostic mappings did not cleanly detach')
    result = {}
    backing = None
    lines = text.splitlines()
    for name in TARGETS:
        table = ref['slots'][ref['runtime_selected_slot']][name]
        length = sum(n for _, n, _ in table)
        label = f'mapped={name} sectors={length} ro=1'
        if lines.count(label) != 1:
            raise ValueError(f'Missing read-only kernel table for {name}')
        pos = lines.index(label) + 1
        if pos + len(table) >= len(lines):
            raise ValueError(f'Truncated kernel table for {name}')
        for start, sectors, physical in table:
            row = re.fullmatch(r'(\d+) (\d+) linear (\d+:\d+) (\d+)', lines[pos])
            if not row or [int(row[1]), int(row[2]), int(row[4])] != [start, sectors, physical]:
                raise ValueError(f'Kernel extent differs for {name}')
            if backing is not None and row[3] != backing:
                raise ValueError(f'Unexpected backing device for {name}')
            backing = row[3]
            pos += 1
        digest = ref['reference_hashes'][name]
        if not re.fullmatch(digest+r'\s+/run/rmx-super/read-'+name, lines[pos]):
            raise ValueError(f'Complete mapped contents differ for {name}')
        result[name] = dict(extents=len(table), bytes=length*512, sha256=digest)
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    cap = sub.add_parser('capture')
    cap.add_argument('--serial', required=True)
    cap.add_argument('--output', type=Path, required=True)
    verify = sub.add_parser('verify')
    for name in ('reference','metadata'):
        verify.add_argument('--'+name, type=Path, required=True)
    verify.add_argument('--maps', type=Path, help='Also verify read-only kernel tables, content and cleanup')
    args = ap.parse_args()
    if args.cmd == 'capture':
        args.output.write_text(json.dumps(capture(args.serial), indent=2)+'\n', encoding='utf-8')
    else:
        ref = json.loads(args.reference.read_text())
        result = {'slots': verify_metadata(ref, args.metadata.read_text())}
        if args.maps:
            result['mappings'] = verify_maps(ref, args.maps.read_text())
        print(json.dumps(result, indent=2))
