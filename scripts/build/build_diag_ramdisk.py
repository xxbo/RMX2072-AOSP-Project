#!/usr/bin/env python3
"""Build a deterministic RAM-only diagnostic initramfs from verified static BusyBox."""
import argparse
import gzip
import hashlib
import io
import json
import pathlib
import re
import struct


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--busybox', required=True, type=pathlib.Path)
    p.add_argument('--output', required=True, type=pathlib.Path)
    p.add_argument('--reboot-helper', type=pathlib.Path)
    p.add_argument('--entry-carrier', type=pathlib.Path)
    p.add_argument('--trial-id')
    p.add_argument('--return-to-edl-after', type=int)
    p.add_argument('--defer-gadget-bind', action='store_true',
                   help='Register UDC but do not start gadget/DMA; isolates post-bind failure')
    p.add_argument('--gadget-bind-delay', type=int,
                   help='Wait 1..120 seconds after UDC discovery before binding')
    p.add_argument('--snapshot-delays', help='Comma-separated 1..60 second snapshot intervals')
    a = p.parse_args()
    if a.trial_id and not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', a.trial_id):
        p.error('Invalid trial ID')
    if a.return_to_edl_after is not None and (
            not a.reboot_helper or not 45 <= a.return_to_edl_after <= 300):
        p.error('A 45..300 second control return requires a static reboot helper')
    if a.gadget_bind_delay is not None and (
            a.defer_gadget_bind or not 1 <= a.gadget_bind_delay <= 120 or
            (a.return_to_edl_after and a.gadget_bind_delay >= a.return_to_edl_after)):
        p.error('Bind delay must be 1..120 seconds, before return, and cannot be deferred')
    delays = None
    if a.snapshot_delays:
        try:
            delays = [int(value) for value in a.snapshot_delays.split(',')]
        except ValueError:
            p.error('Snapshot intervals must be integers')
        if not 1 <= len(delays) <= 8 or any(not 1 <= d <= 60 for d in delays) or sum(delays) > 180:
            p.error('Snapshot intervals must be 1..60 seconds, at most 8, total <=180')
    root = pathlib.Path(__file__).resolve().parents[2]
    if root == a.output.resolve() or root in a.output.resolve().parents:
        p.error('Generated boot material must remain outside checkout')
    lock = json.loads((root/'build/diagnostic-tools.json').read_text())
    binary = a.busybox.read_bytes()
    actual = hashlib.sha256(binary).hexdigest()
    if actual != lock['busybox_sha256']:
        raise ValueError('BusyBox hash mismatch')
    if binary[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', binary, 18)[0] != 183:
        raise ValueError('Expected AArch64 ELF64')
    offset = struct.unpack_from('<Q', binary, 32)[0]
    size, count = struct.unpack_from('<HH', binary, 54)
    if any(struct.unpack_from('<I', binary, offset+i*size)[0] == 3 for i in range(count)):
        raise ValueError('Diagnostic BusyBox must have no dynamic interpreter')
    archive, inode = bytearray(), 0
    def add(name, mode, content=b'', major=0, minor=0):
        nonlocal inode
        inode += 1
        encoded = name.encode()+b'\0'
        fields = [inode, mode, 0, 0, 1, 0, len(content), 0, 0, major, minor, len(encoded), 0]
        archive.extend(b'070701'+''.join(f'{v:08x}' for v in fields).encode()+encoded)
        archive.extend(b'\0'*(-len(archive)%4))
        archive.extend(content)
        archive.extend(b'\0'*(-len(archive)%4))
    for name in ['bin', 'sbin', 'dev', 'proc', 'sys', 'run', 'tmp']:
        add(name, 0o40755)
    add('dev/console', 0o20600, major=5, minor=1)
    add('dev/null', 0o20666, major=1, minor=3)
    add('dev/kmsg', 0o20600, major=1, minor=11)
    add('bin/busybox', 0o100755, binary)
    helper_hash = None
    carrier_hash = None
    if a.entry_carrier:
        carrier = a.entry_carrier.read_bytes()
        if carrier[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', carrier, 18)[0] != 183:
            raise ValueError('Expected static ARM64 entry carrier')
        off = struct.unpack_from('<Q', carrier, 32)[0]
        width, count = struct.unpack_from('<HH', carrier, 54)
        if any(struct.unpack_from('<I', carrier, off+i*width)[0] == 3 for i in range(count)):
            raise ValueError('Entry carrier must have no dynamic interpreter')
        add('bin/entry-carry', 0o100755, carrier)
        carrier_hash = hashlib.sha256(carrier).hexdigest()
    if a.trial_id:
        add('trial-id', 0o100600, (a.trial_id+'\n').encode())
    if a.defer_gadget_bind:
        add('defer-gadget-bind', 0o100600, b'1\n')
    if a.gadget_bind_delay is not None:
        add('gadget-bind-delay', 0o100600, (str(a.gadget_bind_delay)+'\n').encode())
    if delays:
        add('snapshot-delays', 0o100600, (' '.join(map(str, delays))+'\n').encode())
    if a.reboot_helper:
        helper = a.reboot_helper.read_bytes()
        if helper[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', helper, 18)[0] != 183:
            raise ValueError('Expected ARM64 ELF reboot helper')
        phoff = struct.unpack_from('<Q', helper, 32)[0]
        phsize, phcount = struct.unpack_from('<HH', helper, 54)
        if any(struct.unpack_from('<I', helper, phoff+i*phsize)[0] == 3 for i in range(phcount)):
            raise ValueError('Reboot helper must have no dynamic interpreter')
        add('bin/reboot-edl', 0o100755, helper)
        helper_hash = hashlib.sha256(helper).hexdigest()
    if a.return_to_edl_after is not None:
        add('control-return-seconds', 0o100600, (str(a.return_to_edl_after)+'\n').encode())
    init = root/'device/realme/bladerunner_48m/bootstrap/diag-init.sh'
    supervisor = root/'device/realme/bladerunner_48m/bootstrap/diag-supervisor.sh'
    snapshot = root/'device/realme/bladerunner_48m/bootstrap/diag-snapshot.sh'
    add('init', 0o100755, supervisor.read_bytes().replace(b'\r\n', b'\n'))
    add('diag-init.sh', 0o100755, init.read_bytes().replace(b'\r\n', b'\n'))
    add('diag-snapshot.sh', 0o100755, snapshot.read_bytes().replace(b'\r\n', b'\n'))
    add('TRAILER!!!', 0)
    data = io.BytesIO()
    with gzip.GzipFile(fileobj=data, mode='wb', mtime=0, filename='') as stream:
        stream.write(archive)
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output/'ramdisk.cpio').write_bytes(archive)
    (a.output/'ramdisk.cpio.gz').write_bytes(data.getvalue())
    report = dict(busybox_sha256=actual, reboot_helper_sha256=helper_hash,
                  entry_carrier_sha256=carrier_hash, trial_id=a.trial_id,
                  control_return_seconds=a.return_to_edl_after,
                  defer_gadget_bind=a.defer_gadget_bind,
                  gadget_bind_delay_seconds=a.gadget_bind_delay,
                  snapshot_intervals_seconds=delays or [15, 30, 30],
                  init_sha256=hashlib.sha256(init.read_bytes()).hexdigest(),
                  supervisor_sha256=hashlib.sha256(supervisor.read_bytes()).hexdigest(),
                  snapshot_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                  cpio_sha256=hashlib.sha256(archive).hexdigest(),
                  gzip_sha256=hashlib.sha256(data.getvalue()).hexdigest(),
                  scope='USB serial shell in RAM; no block mounts or handset writes')
    (a.output/'ramdisk-provenance.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
