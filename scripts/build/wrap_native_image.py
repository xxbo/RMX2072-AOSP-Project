#!/usr/bin/env python3
"""Native ARM64 handoff wrapper for a 0x80000-offset Qualcomm loader.

The unmodified zero-offset Image starts at the next 2 MiB boundary. Only B/NOP
execute before its original header: no register, stack, cache or device writes.
This wrapper has no PE header and must not be used as an EFI application.
"""
import argparse
import hashlib
import json
import pathlib
import struct

ALIGNMENT = 0x200000
TEXT_OFFSET = 0x80000
PADDING = ALIGNMENT-TEXT_OFFSET


def wrap(image):
    if len(image) < 64 or image[56:60] != b'ARM\x64':
        raise ValueError('Expected raw ARM64 Image')
    text_offset, image_size, flags = struct.unpack_from('<3Q', image, 8)
    if text_offset != 0 or image_size < len(image) or (flags & 1) or (flags >> 1) & 3 != 1:
        raise ValueError('Requires nonzero-sized, zero-offset, little-endian 4K Image')
    result = bytearray(PADDING)+image
    branch = 0x14000000 | (PADDING >> 2)
    struct.pack_into('<IIQQQ', result, 0, branch, 0xd503201f,
                     TEXT_OFFSET, PADDING+image_size, flags)
    result[56:60] = b'ARM\x64'
    if result[PADDING:] != image or (TEXT_OFFSET+PADDING) % ALIGNMENT:
        raise ValueError('Image preservation / alignment failure')
    return bytes(result)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kernel', required=True, type=pathlib.Path)
    p.add_argument('--expected-kernel-sha256', required=True)
    p.add_argument('--output', required=True, type=pathlib.Path)
    a = p.parse_args()
    data = a.kernel.read_bytes()
    source_hash = hashlib.sha256(data).hexdigest()
    if source_hash != a.expected_kernel_sha256:
        raise ValueError('Source Image hash mismatch')
    wrapped = wrap(data)
    a.output.mkdir(exist_ok=False, parents=True)
    (a.output/'Image-native-aligned').write_bytes(wrapped)
    report = dict(scope='Native entry alignment control, not EFI or runtime qualification',
                  original_kernel_sha256=source_hash, original_kernel_bytes=len(data),
                  wrapped_sha256=hashlib.sha256(wrapped).hexdigest(), wrapped_bytes=len(wrapped),
                  wrapper_text_offset=TEXT_OFFSET, embedded_image_file_offset=PADDING,
                  original_image_size=struct.unpack_from('<Q', data, 16)[0],
                  wrapper_image_size=struct.unpack_from('<Q', wrapped, 16)[0],
                  branch_instruction_hex=hex(struct.unpack_from('<I', wrapped)[0]),
                  original_image_byte_identical=True, entry_registers_unchanged=True,
                  qualification='Requires native loader honoring or using 0x80000 offset; does not identify prior reset cause',
                  status='prepared-not-device-tested')
    (a.output/'alignment.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
