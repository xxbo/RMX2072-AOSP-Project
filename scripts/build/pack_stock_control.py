#!/usr/bin/env python3
"""Package a RAM-only stock-kernel control using the verified logging reader DTBs.

Uses the diagnostic candidate's command line, but keeps the known stock kernel
and 25-DTB bundle. Pair only with the original stock DTBO. Never flashes.
"""
import argparse
import gzip
import hashlib
import json
import pathlib
import struct
import subprocess
import sys
from avb_footer import retain_envelope

SOURCE = '9ae2f907fd029e88c841121f4fbeb6f3a1ae32322a6703d8d142bbba31bb93c3'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['source', 'ramdisk', 'reference-package', 'mkbootimg', 'output']:
        parser.add_argument('--' + name, required=True, type=pathlib.Path)
    args = parser.parse_args()
    repo = pathlib.Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    if output == repo or repo in output.parents:
        parser.error('Private images must remain outside checkout')
    source = args.source.read_bytes()
    if hashlib.sha256(source).hexdigest() != SOURCE:
        raise ValueError('Requires exact device-tested shared-layout reader boot')
    if gzip.decompress(args.ramdisk.read_bytes())[:6] != b'070701':
        raise ValueError('Expected diagnostic newc ramdisk')
    word = lambda offset: struct.unpack_from('<I', source, offset)[0]
    align = lambda value: (value + 4095) // 4096 * 4096
    kernel_size, ramdisk_size, dtb_size = word(8), word(16), word(1648)
    dtb_start = 4096 + align(kernel_size) + align(ramdisk_size)
    kernel = source[4096:4096 + kernel_size]
    dtb = source[dtb_start:dtb_start + dtb_size]
    output.mkdir(parents=True, exist_ok=True)
    kernel_path, dtb_path = output / 'stock-kernel', output / 'stock-dtb-bundle'
    kernel_path.write_bytes(kernel)
    dtb_path.write_bytes(dtb)
    reference = json.loads(args.reference_package.read_text())
    command_line = reference['command'][reference['command'].index('--cmdline') + 1]
    version, patch = word(44) >> 11, word(44) & 0x7ff
    image = output / 'boot-stock-control.img'
    command = [sys.executable, str(args.mkbootimg), '--header_version', '2',
               '--pagesize', '4096', '--base', '0', '--kernel_offset', hex(word(12)),
               '--ramdisk_offset', hex(word(20)), '--tags_offset', hex(word(32)),
               '--dtb_offset', hex(struct.unpack_from('<Q', source, 1652)[0]),
               '--os_version', f'{(version>>14)&127}.{(version>>7)&127}.{version&127}',
               '--os_patch_level', f'{2000+(patch>>4):04d}-{patch&15:02d}',
               '--kernel', str(kernel_path), '--dtb', str(dtb_path),
               '--ramdisk', str(args.ramdisk), '--cmdline', command_line,
               '--output', str(image)]
    subprocess.run(command, check=True)
    result, envelope = retain_envelope(source, image.read_bytes())
    image.write_bytes(result)
    new_ramdisk_size = struct.unpack_from('<I', result, 16)[0]
    new_dtb_start = 4096 + align(kernel_size) + align(new_ramdisk_size)
    if result[4096:4096 + kernel_size] != kernel or result[new_dtb_start:new_dtb_start + dtb_size] != dtb:
        raise ValueError('Stock kernel or DTB bundle changed')
    report = dict(source_sha256=SOURCE, boot_sha256=hashlib.sha256(result).hexdigest(),
                  kernel_sha256=hashlib.sha256(kernel).hexdigest(),
                  ramdisk_sha256=hashlib.sha256(args.ramdisk.read_bytes()).hexdigest(),
                  dtb_sha256=hashlib.sha256(dtb).hexdigest(), avb_envelope=envelope,
                  cmdline=command_line, paired_dtbo='original stock DTBO only',
                  scope='Stock 4.19 RAM-only control, not a 6.18 boot result',
                  status='packaged-not-device-tested')
    (output / 'control.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
