#!/usr/bin/env python3
"""Prepare one nonsemantic DTBO-byte control; never flashes or signs an image."""
import argparse
import ctypes
import hashlib
import json
import pathlib
import struct
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'device_audit'))
from inspect_boot_dt import fdt, inspect

STOCK = '61d9b3ac8426a886de63cf4cde0552e2cab3cd5c47f83ef4335a624b657949ef'
BOOT = '5b5cb9a15c174211a82c6b567d276caa6e6acd4ddf00d6e2faf68ed9ac0f5e58'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('stock-dtbo', 'control-boot', 'libfdt', 'output'):
        p.add_argument('--'+key, required=True, type=pathlib.Path)
    a = p.parse_args()
    repo = pathlib.Path(__file__).resolve().parents[2]
    if a.output.resolve() == repo or repo in a.output.resolve().parents:
        p.error('Private outputs must remain outside checkout')
    stock, boot = a.stock_dtbo.read_bytes(), a.control_boot.read_bytes()
    if hashlib.sha256(stock).hexdigest() != STOCK or hashlib.sha256(boot).hexdigest() != BOOT:
        raise ValueError('Requires exact stock DTBO and physically executed 6.18 control boot')
    entries = struct.unpack_from('>I', stock, 20)[0]
    size, offset = struct.unpack_from('>2I', stock, entries+17*32)
    overlay = stock[offset:offset+size]
    structure = struct.unpack_from('>I', overlay, 8)[0]
    # BEGIN_NODE token, empty root name, then 3 bytes of alignment padding.
    if overlay[structure:structure+8] != b'\0\0\0\x01\0\0\0\0':
        raise ValueError('Expected empty root name with zero alignment padding')
    mutated = bytearray(overlay)
    mutated[structure+7] = 1
    if fdt(overlay, ('**',))['matching_nodes'] != fdt(mutated, ('**',))['matching_nodes']:
        raise ValueError('Parsed DT properties changed')
    tree = inspect(a.control_boot)['trees'][12]
    base = boot[tree['offset']:tree['offset']+tree['size_bytes']]
    library = ctypes.CDLL(str(a.libfdt.resolve()))
    library.fdt_open_into.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    library.fdt_overlay_apply.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    library.fdt_pack.argtypes = [ctypes.c_void_p]
    def merge(blob):
        target = ctypes.create_string_buffer(2*1024*1024)
        original = ctypes.create_string_buffer(base)
        patch = ctypes.create_string_buffer(bytes(blob))
        if library.fdt_open_into(original, target, len(target)):
            raise ValueError('libfdt could not open base')
        if library.fdt_overlay_apply(target, patch) or library.fdt_pack(target):
            raise ValueError('libfdt could not apply / pack overlay')
        return target.raw[:struct.unpack_from('>I', target.raw, 4)[0]]
    merged = merge(overlay)
    if merged != merge(mutated):
        raise ValueError('Actual merged DT bytes changed')
    result = bytearray(stock)
    location = offset+structure+7
    result[location] = 1
    if sum(x != y for x, y in zip(stock, result)) != 1 or len(stock) != len(result):
        raise ValueError('Control must differ by exactly one byte')
    a.output.mkdir(exist_ok=False, parents=True)
    (a.output/'boot-diag.img').write_bytes(boot)
    (a.output/'dtbo-diag.img').write_bytes(result)
    report = dict(scope='One ignored padding byte; every node/property and actual merged DT identical',
                  boot_sha256=BOOT, source_dtbo_sha256=STOCK,
                  dtbo_sha256=hashlib.sha256(result).hexdigest(),
                  byte_change=dict(offset=location, before=0, after=1),
                  selected_index=17, decoded_nodes_properties_identical=True,
                  merged_dt_sha256=hashlib.sha256(merged).hexdigest(),
                  original_and_mutated_merged_bytes_identical=True,
                  avb_metadata_and_footer_identical=True,
                  libfdt_sha256=hashlib.sha256(a.libfdt.read_bytes()).hexdigest(),
                  qualification='Payload digest changes; original signed metadata no longer authenticates it; unlocked only',
                  status='prepared-not-device-tested')
    (a.output/'control.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
