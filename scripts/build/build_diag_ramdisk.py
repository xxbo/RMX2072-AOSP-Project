#!/usr/bin/env python3
"""Build a deterministic RAM-only diagnostic initramfs from verified static BusyBox."""
import argparse
import gzip
import hashlib
import io
import json
import pathlib
import struct


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--busybox', required=True, type=pathlib.Path)
    p.add_argument('--output', required=True, type=pathlib.Path)
    p.add_argument('--reboot-helper', type=pathlib.Path)
    p.add_argument('--return-to-edl-after', type=int)
    a = p.parse_args()
    if a.return_to_edl_after is not None and (
            not a.reboot_helper or not 45 <= a.return_to_edl_after <= 300):
        p.error('A 45..300 second control return requires a static reboot helper')
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
                  control_return_seconds=a.return_to_edl_after,
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
