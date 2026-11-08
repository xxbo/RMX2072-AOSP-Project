#!/usr/bin/env python3
"""Prepare a private DTBO selection control; never flashes a device.

Retain the original table and every other overlay. Replace only selected overlay
content while copying its complete root selector properties. Modified AVB payload
is not OEM signed; the device must remain unlocked.
"""
import argparse
import ctypes
import hashlib
import json
import pathlib
import struct
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'device_audit'))
from inspect_boot_dt import fdt

STOCK = '61d9b3ac8426a886de63cf4cde0552e2cab3cd5c47f83ef4335a624b657949ef'
OVERLAY = '09076cd383b587d24b67faeea39dda9caebdbbe58f40441f3bf6e6ccd97235e4'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def replace_entry(source, index, replacement):
    magic, total, header, entry_size, count, entries, page, version = struct.unpack_from('>8I', source)
    if (magic != 0xd7b7ab1e or total > len(source) or header < 32 or
            entry_size != 32 or entries < header or entries+count*entry_size > total or
            not 0 <= index < count):
        raise ValueError('Invalid DTBO table')
    ranges = []
    for entry in range(count):
        size, offset = struct.unpack_from('>2I', source, entries+entry*entry_size)
        if offset < entries+count*entry_size or offset+size > total:
            raise ValueError('DTBO payload exceeds bounds')
        ranges.append((offset, offset+size))
    ordered = sorted(ranges)
    if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
        raise ValueError('Overlapping DTBO payloads')
    start, end = ranges[index]
    if len(replacement) > end-start:
        raise ValueError('Replacement exceeds selected slot')
    if replacement[:4] != b'\xd0\x0d\xfe\xed' or struct.unpack_from('>I', replacement, 4)[0] != len(replacement):
        raise ValueError('Replacement must be one complete FDT')
    result = bytearray(source)
    result[start:end] = replacement + bytes(end-start-len(replacement))
    struct.pack_into('>I', result, entries+index*entry_size, len(replacement))
    # Prove every byte outside the selected slot / its size word is unchanged.
    size_word = entries+index*entry_size
    for lo, hi in ((0, size_word), (size_word+4, start), (end, len(source))):
        if result[lo:hi] != source[lo:hi]:
            raise ValueError('Unexpected change outside selected overlay')
    return bytes(result), (start, end)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('stock-dtbo', 'overlay', 'libfdt', 'output'):
        p.add_argument('--'+key, required=True, type=pathlib.Path)
    a = p.parse_args()
    repo = pathlib.Path(__file__).resolve().parents[2]
    if a.output.resolve() == repo or repo in a.output.resolve().parents:
        p.error('Private output must remain outside the checkout')
    source, overlay = a.stock_dtbo.read_bytes(), a.overlay.read_bytes()
    if hashlib.sha256(source).hexdigest() != STOCK or hashlib.sha256(overlay).hexdigest() != OVERLAY:
        raise ValueError('Requires the exact captured stock DTBO and CI selector overlay')
    count, entries = struct.unpack_from('>2I', source, 16)
    require(count == 18, 'Expected 18 stock entries')
    size, offset = struct.unpack_from('>2I', source, entries+17*32)
    original = source[offset:offset+size]
    root = next(n['properties'] for n in fdt(original, ('**',))['matching_nodes'] if n['path']=='')
    library = ctypes.CDLL(str(a.libfdt.resolve()))
    library.fdt_open_into.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    library.fdt_setprop.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int]
    library.fdt_delprop.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p]
    library.fdt_add_subnode.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p]
    library.fdt_pack.argtypes = [ctypes.c_void_p]
    buffer = ctypes.create_string_buffer(4096)
    require(library.fdt_open_into(ctypes.create_string_buffer(overlay), buffer, len(buffer)) == 0,
            'libfdt could not open overlay')
    old_root = next(n['properties'] for n in fdt(overlay, ('**',))['matching_nodes'] if n['path']=='')
    for key in old_root.keys()-root.keys():
        require(library.fdt_delprop(buffer, 0, key.encode()) == 0, 'Could not remove extra selector')
    for key, value in root.items():
        raw = (b'\0'.join(s.encode() for s in value)+b'\0' if value and isinstance(value[0], str)
               else struct.pack('>'+str(len(value))+'I', *value))
        require(library.fdt_setprop(buffer, 0, key.encode(), raw, len(raw)) == 0,
                'Could not copy original selector')
    # Some vendor overlay implementations expect a fixups node even if empty.
    require(library.fdt_add_subnode(buffer, 0, b'__fixups__') >= 0, 'Could not add empty fixups node')
    require(library.fdt_pack(buffer) == 0, 'Could not pack overlay')
    new = buffer.raw[:struct.unpack_from('>I', buffer.raw, 4)[0]]
    new_root = next(n['properties'] for n in fdt(new, ('**',))['matching_nodes'] if n['path']=='')
    require(root == new_root, 'Root selector properties changed')
    result, slot = replace_entry(source, 17, new)
    a.output.mkdir(exist_ok=False, parents=True)
    (a.output/'overlay17-noop.dtb').write_bytes(new)
    (a.output/'dtbo-diag.img').write_bytes(result)
    report = dict(scope='Selection-preserving DTBO control; no hardware-support claim',
                  original_entries=18, selected_index=17, selected_slot=list(slot),
                  original_root=root, root_properties_identical=True,
                  all_other_entries_and_avb_metadata_identical=True,
                  libfdt_sha256=hashlib.sha256(a.libfdt.read_bytes()).hexdigest(),
                  overlay_sha256=hashlib.sha256(new).hexdigest(),
                  dtbo_sha256=hashlib.sha256(result).hexdigest(),
                  qualification='Original signed metadata does not authenticate modified payload; unlocked only',
                  status='prepared-not-device-tested')
    (a.output/'control.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
