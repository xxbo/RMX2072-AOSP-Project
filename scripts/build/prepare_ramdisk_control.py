#!/usr/bin/env python3
"""Replace only a hash-verified boot-v2 ramdisk for an isolated runtime control."""
import argparse
import gzip
import hashlib
import json
import pathlib
import struct
from avb_footer import retain_envelope
from prepare_pstore_reader import image_id


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'ramdisk', 'output'):
        p.add_argument('--'+name, required=True, type=pathlib.Path)
    p.add_argument('--expected-source-sha256', required=True)
    p.add_argument('--ufs-boot-device', action='store_true',
                   help='Expose the 6.18 staged UFS controller to Android first-stage discovery')
    a = p.parse_args()
    repo = pathlib.Path(__file__).resolve().parents[2]
    if a.output.resolve() == repo or repo in a.output.resolve().parents:
        p.error('Private boot output must remain outside checkout')
    b, rd = a.source.read_bytes(), a.ramdisk.read_bytes()
    sha = lambda data: hashlib.sha256(data).hexdigest()
    word = lambda offset: struct.unpack_from('<I', b, offset)[0]
    align = lambda n: (n+4095)//4096*4096
    if sha(b) != a.expected_source_sha256 or b[:8] != b'ANDROID!':
        raise ValueError('Source identity mismatch')
    if word(40) != 2 or word(36) != 4096 or word(24) or struct.unpack_from('<I', b, 1632)[0]:
        raise ValueError('Requires v2, 4K pages, no second/recovery payload')
    if image_id(b) != b[576:608] or gzip.decompress(rd)[:6] != b'070701':
        raise ValueError('Invalid boot ID or ramdisk')
    start = 4096+align(word(8))
    dtstart = start+align(word(16))
    dtb = b[dtstart:dtstart+word(1648)]
    raw = bytearray(b[:start])+rd+bytes(align(len(rd))-len(rd))+dtb
    if a.ufs_boot_device:
        cmdline = b[64:576].split(b'\0', 1)[0]
        # Match the staged platform controller when Android builds by-name links.
        cmdline += b' androidboot.boot_devices=soc/soc:ufs-host-lab/1d84000.ufs tp_printk tp_printk_stop_on_boot'
        if len(cmdline) >= 512 or any(b[608:1632]):
            raise ValueError('UFS boot device does not fit the expected boot header')
        raw[64:576] = cmdline.ljust(512, b'\0')
    struct.pack_into('<I', raw, 16, len(rd))
    raw[576:608] = image_id(raw)
    raw.extend(bytes(-len(raw)%4096))
    result, envelope = retain_envelope(b, raw)
    assert result[4096:start] == b[4096:start]
    assert result[start+align(len(rd)):start+align(len(rd))+len(dtb)] == dtb
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output/'boot-diag.img').write_bytes(result)
    report = dict(source_boot_sha256=sha(b), boot_sha256=sha(result), ramdisk_sha256=sha(rd),
                  kernel_and_dtb_byte_identical=True, command_line_byte_identical=not a.ufs_boot_device,
                  avb_envelope=envelope, status='prepared-not-device-tested')
    (a.output/'control.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
