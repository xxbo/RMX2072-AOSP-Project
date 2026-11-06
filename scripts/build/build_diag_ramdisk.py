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
    a = p.parse_args()
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
    add('bin/busybox', 0o100755, binary)
    init = root/'device/realme/bladerunner_48m/bootstrap/diag-init.sh'
    add('init', 0o100755, init.read_bytes().replace(b'\r\n', b'\n'))
    add('TRAILER!!!', 0)
    data = io.BytesIO()
    with gzip.GzipFile(fileobj=data, mode='wb', mtime=0, filename='') as stream:
        stream.write(archive)
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output/'ramdisk.cpio').write_bytes(archive)
    (a.output/'ramdisk.cpio.gz').write_bytes(data.getvalue())
    report = dict(busybox_sha256=actual, init_sha256=hashlib.sha256(init.read_bytes()).hexdigest(),
                  cpio_sha256=hashlib.sha256(archive).hexdigest(),
                  gzip_sha256=hashlib.sha256(data.getvalue()).hexdigest(),
                  scope='USB serial shell in RAM; no block mounts or handset writes')
    (a.output/'ramdisk-provenance.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
