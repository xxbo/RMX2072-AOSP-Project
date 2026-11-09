#!/usr/bin/env python3
"""Replace the kernel in a verified, private RMX2072 native-entry boot-v2 image."""
import argparse
import hashlib
import json
import pathlib
import struct

from avb_footer import retain_envelope
from prepare_pstore_reader import image_id
from wrap_native_image import wrap


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace_kernel(source, kernel, probe):
    word = lambda offset: struct.unpack_from('<I', source, offset)[0]
    align = lambda size: (size + 4095) // 4096 * 4096
    if (source[:8] != b'ANDROID!' or word(36) != 4096 or word(40) != 2
            or word(24) or word(1632) or image_id(source) != source[576:608]):
        raise ValueError('Requires an intact boot-v2 image with a 4K page and no second/recovery payload')
    old = source[4096:4096 + word(8)]
    if sha(old) != '1e206ad78485b825ffba9bd427023adc9f53f12f54e666041b2bb377701ba793':
        raise ValueError('Expected the physically tested native entry-probe kernel')
    wrapped = wrap(kernel, probe)
    ramdisk_start = 4096 + align(len(old))
    tail = source[ramdisk_start:ramdisk_start + align(word(16)) + word(1648)]
    if len(tail) != align(word(16)) + word(1648):
        raise ValueError('Truncated ramdisk or board bundle')
    raw = bytearray(source[:4096]) + wrapped + bytes(align(len(wrapped)) - len(wrapped)) + tail
    struct.pack_into('<I', raw, 8, len(wrapped))
    raw[576:608] = image_id(raw)
    raw.extend(bytes(-len(raw) % 4096))
    result, envelope = retain_envelope(source, raw)
    start = 4096 + align(len(wrapped))
    if result[start:start + len(tail)] != tail or result[4096:4096 + len(wrapped)] != wrapped:
        raise ValueError('Packaged components do not match input')
    return result, dict(source_boot_sha256=sha(source), boot_sha256=sha(result), kernel_sha256=sha(kernel),
                        wrapped_kernel_sha256=sha(wrapped), ramdisk_sha256=sha(tail[:word(16)]),
                        dtb_bundle_sha256=sha(tail[align(word(16)):]), avb_envelope=envelope)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'kernel', 'entry-probe', 'output'):
        parser.add_argument('--' + name, required=True, type=pathlib.Path)
    for name in ('source', 'kernel'):
        parser.add_argument('--expected-' + name + '-sha256', required=True)
    args = parser.parse_args()
    repo = pathlib.Path(__file__).resolve().parents[2]
    if args.output.resolve() == repo or repo in args.output.resolve().parents:
        parser.error('Keep private images outside the repository')
    source, kernel = args.source.read_bytes(), args.kernel.read_bytes()
    if sha(source) != args.expected_source_sha256 or sha(kernel) != args.expected_kernel_sha256:
        raise ValueError('Source boot or kernel hash mismatch')
    result, report = replace_kernel(source, kernel, args.entry_probe.read_bytes())
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'boot-diag.img').write_bytes(result)
    (args.output / 'control.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
