#!/usr/bin/env python3
"""Native ARM64 handoff wrapper for a 0x80000-offset Qualcomm loader.

The unmodified zero-offset Image starts at the next 2 MiB boundary. Default
entry is B/NOP only. The optional reviewed probe writes reserved pmsg RAM.
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
ENTRY_PROBE_SHA = '0484b246c561fde26f07a5eb40ed2f6bea0683a83607a5157ed7bd00ea11e8b6'


def wrap(image, probe=None):
    if len(image) < 64 or image[56:60] != b'ARM\x64':
        raise ValueError('Expected raw ARM64 Image')
    text_offset, image_size, flags = struct.unpack_from('<3Q', image, 8)
    if text_offset != 0 or image_size < len(image) or (flags & 1) or (flags >> 1) & 3 != 1:
        raise ValueError('Requires nonzero-sized, zero-offset, little-endian 4K Image')
    if probe is not None:
        if len(probe) != PADDING+4 or hashlib.sha256(probe).hexdigest() != ENTRY_PROBE_SHA:
            raise ValueError('Entry probe does not match reviewed assembly')
        if probe[:64] != bytes(64) or probe[PADDING:] != b'\x1f\x20\x03\xd5':
            raise ValueError('Entry probe envelope invalid')
    result = bytearray(probe[:PADDING] if probe is not None else bytes(PADDING))+image
    branch = 0x14000000 | ((64 if probe is not None else PADDING) >> 2)
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
    p.add_argument('--entry-probe', type=pathlib.Path)
    p.add_argument('--layout-fdt', type=pathlib.Path)
    a = p.parse_args()
    data = a.kernel.read_bytes()
    source_hash = hashlib.sha256(data).hexdigest()
    if source_hash != a.expected_kernel_sha256:
        raise ValueError('Source Image hash mismatch')
    if bool(a.entry_probe) != bool(a.layout_fdt):
        p.error('Entry probe requires the verified shared-layout FDT')
    if a.layout_fdt:
        from pack_diag_boot import validate_pstore_layout
        validate_pstore_layout(a.layout_fdt.read_bytes())
    wrapped = wrap(data, a.entry_probe.read_bytes() if a.entry_probe else None)
    a.output.mkdir(exist_ok=False, parents=True)
    (a.output/'Image-native-aligned').write_bytes(wrapped)
    report = dict(scope='Native entry alignment control, not EFI or runtime qualification',
                  original_kernel_sha256=source_hash, original_kernel_bytes=len(data),
                  wrapped_sha256=hashlib.sha256(wrapped).hexdigest(), wrapped_bytes=len(wrapped),
                  wrapper_text_offset=TEXT_OFFSET, embedded_image_file_offset=PADDING,
                  original_image_size=struct.unpack_from('<Q', data, 16)[0],
                  wrapper_image_size=struct.unpack_from('<Q', wrapped, 16)[0],
                  branch_instruction_hex=hex(struct.unpack_from('<I', wrapped)[0]),
                  original_image_byte_identical=True, entry_registers_unchanged=not bool(a.entry_probe),
                  boot_argument_registers_x0_x3_unchanged=True,
                  scratch_registers=['x9', 'x10', 'x11', 'x12', 'x13', 'x14', 'x15', 'x16', 'NZCV'] if a.entry_probe else [],
                  probe_cleans_written_ram_to_poc=bool(a.entry_probe),
                  entry_probe=bool(a.entry_probe),
                  probe_sha256=ENTRY_PROBE_SHA if a.entry_probe else None,
                  probe_ram_range=['0xb0200010', '0xb0201010'] if a.entry_probe else None,
                  qualification='Requires native loader honoring or using 0x80000 offset; does not identify prior reset cause',
                  status='prepared-not-device-tested')
    (a.output/'alignment.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
