#!/usr/bin/env python3
"""Prepare a local RMX2072 stock-kernel debug boot with aligned console layout.

Only accepts the previously device-tested Magisk boot. No device writes.
The stock signed AVB payload hash remains mismatched on this unlocked handset.
"""
import argparse
import hashlib
import json
import pathlib
import struct
from avb_footer import parse_footer

KNOWN_DEBUG = '9593e11ba8cd2fabe162fe821b951035efd328b2b2cbf5b9c57c1a7b5c0969ad'


def patch_tree(image, base, ecc_size=0):
    header = struct.unpack_from('>10I', image, base)
    magic, size, structure, strings = header[:4]
    if magic != 0xd00dfeed or base + size > len(image):
        raise ValueError('Invalid DTB boundary')
    cursor, end, stack, changed = base + structure, base + structure + header[9], [], []
    while cursor < end:
        token = struct.unpack_from('>I', image, cursor)[0]
        cursor += 4
        if token == 1:
            stop = image.index(0, cursor, end)
            stack.append(bytes(image[cursor:stop]).decode())
            cursor = base + ((stop - base + 4) & ~3)
        elif token == 2:
            stack.pop()
        elif token == 3:
            length, name_offset = struct.unpack_from('>II', image, cursor)
            cursor += 8
            name_start = base + strings + name_offset
            name_end = image.index(0, name_start, base + strings + header[8])
            name = bytes(image[name_start:name_end]).decode()
            if name == 'devinfo-size' and stack[-1] == 'ramoops@0xB0000000':
                if length != 4 or struct.unpack_from('>I', image, cursor)[0] != 0x1000:
                    raise ValueError('Unexpected original ramoops device-info size')
                struct.pack_into('>I', image, cursor, 0)
                changed.append(cursor)
            if name == 'ecc-size' and stack[-1] == 'ramoops@0xB0000000' and ecc_size:
                if length != 4 or struct.unpack_from('>I', image, cursor)[0] != 0:
                    raise ValueError('Unexpected original ramoops ECC size')
                struct.pack_into('>I', image, cursor, ecc_size)
                changed.append(cursor)
            cursor = base + ((cursor - base + length + 3) & ~3)
        elif token == 4:
            pass
        elif token == 9:
            return size, changed
        else:
            raise ValueError('Invalid FDT token')
    raise ValueError('Incomplete FDT')


def image_id(image):
    word = lambda offset: struct.unpack_from('<I', image, offset)[0]
    align = lambda value: (value + 4095) // 4096 * 4096
    cursor, digest = 4096, hashlib.sha1()
    for size in [word(8), word(16), word(24), word(1632), word(1648)]:
        digest.update(image[cursor:cursor + size])
        digest.update(struct.pack('<I', size))
        cursor += align(size)
    return digest.digest() + bytes(12)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=pathlib.Path)
    parser.add_argument('--output', required=True, type=pathlib.Path)
    parser.add_argument('--ecc-size', type=int, choices=[0, 16], default=0)
    args = parser.parse_args()
    repo = pathlib.Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    if output == repo or repo in output.parents:
        parser.error('Private boot images must remain outside checkout')
    original = args.source.read_bytes()
    if hashlib.sha256(original).hexdigest() != KNOWN_DEBUG:
        raise ValueError('Requires the exact device-tested RMX2072 debug boot')
    if original[576:608] != image_id(original):
        raise ValueError('Original boot-v2 ID does not match AOSP calculation')
    word = lambda offset: struct.unpack_from('<I', original, offset)[0]
    align = lambda value: (value + 4095) // 4096 * 4096
    if word(40) != 2 or word(36) != 4096 or word(24) or word(1632):
        raise ValueError('Unexpected stock geometry')
    dtb_start = 4096 + align(word(8)) + align(word(16))
    dtb_end = dtb_start + word(1648)
    result, cursor, trees, offsets = bytearray(original), dtb_start, [], []
    while cursor < dtb_end:
        size, changes = patch_tree(result, cursor, args.ecc_size)
        trees.append(dict(index=len(trees), changed_properties=len(changes)))
        offsets.extend(changes)
        cursor += size
    expected_per_tree = 2 if args.ecc_size else 1
    if (cursor != dtb_end or len(trees) != 25 or len(offsets) != 21 * expected_per_tree
            or trees[12]['changed_properties'] != expected_per_tree):
        raise ValueError('Unexpected DTB patch coverage')
    result[576:608] = image_id(result)
    allowed = set(range(576, 608)) | {position + byte for position in offsets for byte in range(4)}
    changes = [i for i, (old, new) in enumerate(zip(original, result)) if old != new]
    if any(i not in allowed for i in changes) or result[4096:dtb_start] != original[4096:dtb_start]:
        raise ValueError('Changes escaped DT properties / boot ID')
    if parse_footer(result) != parse_footer(original):
        raise ValueError('AVB envelope changed')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result)
    report = dict(source_sha256=KNOWN_DEBUG, output_sha256=hashlib.sha256(result).hexdigest(),
                  size_bytes=len(result), changed_byte_count=len(changes), patched_trees=trees,
                  source_derived_console_address='0xb0180000',
                  ecc_size=args.ecc_size,
                  scope='Stock kernel/ramdisk unchanged; ramoops devinfo-size, optional ECC and boot ID only',
                  qualification='Candidate reader; actual F.20 layout and cross-kernel retention require runtime tests',
                  status='prepared-not-device-tested')
    output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ['output_sha256', 'changed_byte_count', 'status']}))


if __name__ == '__main__':
    main()
