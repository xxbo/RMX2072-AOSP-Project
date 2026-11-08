#!/usr/bin/env python3
"""Prepare a private premerged-stock-DT handoff control. Never flashes."""
import argparse
import ctypes
import hashlib
import json
import pathlib
import struct
import subprocess
import sys
from avb_footer import retain_envelope
from prepare_stock_table_noop import replace_entry
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'device_audit'))
from inspect_boot_dt import inspect, fdt

BOOT = '5b5cb9a15c174211a82c6b567d276caa6e6acd4ddf00d6e2faf68ed9ac0f5e58'
ALIGNED_BOOT = '6bf6eb2abc9b237630a45452c3d0ba1969de7bbc77eaf3fbf7978ad21086233c'
STOCK = '61d9b3ac8426a886de63cf4cde0552e2cab3cd5c47f83ef4335a624b657949ef'
EMPTY = '697fcba8c2214d736b246cb991969f9248fc736029b59be49db7ab93fc7282e5'
CORE = '1bf3ffe9e252132928cc4b73e473809a43385d1581469ea6196b152fa4881970'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('control-boot', 'stock-dtbo', 'empty-dtbo', 'libfdt', 'mkbootimg', 'output'):
        p.add_argument('--'+key, required=True, type=pathlib.Path)
    p.add_argument('--core-dtb', type=pathlib.Path, help='Pinned diagnostic-only upstream DTB override')
    a = p.parse_args()
    repo = pathlib.Path(__file__).resolve().parents[2]
    if a.output.resolve() == repo or repo in a.output.resolve().parents:
        p.error('Private outputs must remain outside checkout')
    source, dtbo, empty = a.control_boot.read_bytes(), a.stock_dtbo.read_bytes(), a.empty_dtbo.read_bytes()
    source_hash = hashlib.sha256(source).hexdigest()
    if source_hash not in (BOOT, ALIGNED_BOOT):
        raise ValueError('Unexpected source control boot')
    for blob, expected in ((dtbo, STOCK), (empty, EMPTY)):
        if hashlib.sha256(blob).hexdigest() != expected:
            raise ValueError('Unexpected control source hash')
    def selected(blob):
        entries = struct.unpack_from('>I', blob, 20)[0]
        size, offset = struct.unpack_from('>2I', blob, entries+17*32)
        return blob[offset:offset+size]
    if replace_entry(dtbo, 17, selected(empty))[0] != empty:
        raise ValueError('Empty DTBO changes unselected data')
    trees = inspect(a.control_boot)['trees']
    if len(trees) != 25:
        raise ValueError('Expected 25 base DTBs')
    blobs = [source[t['offset']:t['offset']+t['size_bytes']] for t in trees]
    library = ctypes.CDLL(str(a.libfdt.resolve()))
    library.fdt_open_into.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    library.fdt_overlay_apply.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    library.fdt_pack.argtypes = [ctypes.c_void_p]
    def merge(base, patch):
        target = ctypes.create_string_buffer(2*1024*1024)
        if library.fdt_open_into(ctypes.create_string_buffer(base), target, len(target)):
            raise ValueError('libfdt base open failed')
        if library.fdt_overlay_apply(target, ctypes.create_string_buffer(patch)) or library.fdt_pack(target):
            raise ValueError('libfdt merge/pack failed')
        return target.raw[:struct.unpack_from('>I', target.raw, 4)[0]]
    merged = merge(blobs[12], selected(dtbo))
    if a.core_dtb:
        core = a.core_dtb.read_bytes()
        if hashlib.sha256(core).hexdigest() != CORE:
            raise ValueError('Core override hash mismatch')
        properties = next(n['properties'] for n in fdt(core, ('**',))['matching_nodes'] if n['path']=='')
        if properties.get('rmx2072,diagnostic-profile') != ['core-only']:
            raise ValueError('Missing core-only marker')
        merged = core
    if merge(merged, selected(empty)) != merged:
        raise ValueError('Empty overlay changes effective merged hardware description')
    blobs[12] = merged
    word = lambda off: struct.unpack_from('<I', source, off)[0]
    align = lambda size: (size+4095)//4096*4096
    kernel = source[4096:4096+word(8)]
    ramdisk_start = 4096+align(word(8))
    ramdisk = source[ramdisk_start:ramdisk_start+word(16)]
    a.output.mkdir(exist_ok=False, parents=True)
    for name, blob in (('kernel', kernel), ('ramdisk', ramdisk), ('dtb-bundle', b''.join(blobs))):
        (a.output/name).write_bytes(blob)
    version, patch = word(44)>>11, word(44)&0x7ff
    # The exact source command line is known for this hash-guarded positive control.
    cmdline = source[64:576].split(b'\0')[0].decode()+source[608:1632].split(b'\0')[0].decode()
    if a.core_dtb:
        cmdline = ('rdinit=/init console=ttynull loglevel=8 ignore_loglevel printk.devkmsg=on '
                   'clk_ignore_unused pd_ignore_unused fw_devlink=permissive panic=30 '
                   'androidboot.hardware=qcom maxcpus=1 cpuidle.off=1')
    image = a.output/'boot-diag.img'
    command = [sys.executable, str(a.mkbootimg), '--header_version', '2', '--pagesize', '4096',
               '--base', '0', '--kernel_offset', hex(word(12)), '--ramdisk_offset', hex(word(20)),
               '--tags_offset', hex(word(32)), '--dtb_offset', hex(struct.unpack_from('<Q', source, 1652)[0]),
               '--os_version', f'{(version>>14)&127}.{(version>>7)&127}.{version&127}',
               '--os_patch_level', f'{2000+(patch>>4):04d}-{patch&15:02d}',
               '--kernel', str(a.output/'kernel'), '--ramdisk', str(a.output/'ramdisk'),
               '--dtb', str(a.output/'dtb-bundle'), '--cmdline', cmdline, '--output', str(image)]
    subprocess.run(command, check=True)
    result, envelope = retain_envelope(source, image.read_bytes())
    image.write_bytes(result)
    (a.output/'dtbo-diag.img').write_bytes(empty)
    packaged_trees = inspect(image)['trees']
    if len(packaged_trees) != 25:
        raise ValueError('Repackaged DTB count changed')
    for index, tree in enumerate(packaged_trees):
        if result[tree['offset']:tree['offset']+tree['size_bytes']] != blobs[index]:
            raise ValueError('Repackaged DTB bytes changed')
    if result[4096:4096+len(kernel)] != kernel or result[ramdisk_start:ramdisk_start+len(ramdisk)] != ramdisk:
        raise ValueError('Kernel/ramdisk changed')
    report = dict(scope=('Core-only upstream DTB handoff; no peripheral support claim' if a.core_dtb else
                         'Premerged legacy hardware description; no new hardware support claim'),
                  source_boot_sha256=source_hash, stock_dtbo_sha256=STOCK, paired_dtbo_sha256=EMPTY,
                  replaced_base_index=12, preapplied_overlay_index=None if a.core_dtb else 17,
                  core_only=bool(a.core_dtb),
                  all_other_24_base_trees_identical=True,
                  merged_dt_sha256=hashlib.sha256(merged).hexdigest(),
                  empty_overlay_reapplication_byte_identical=True,
                  kernel_sha256=hashlib.sha256(kernel).hexdigest(), ramdisk_sha256=hashlib.sha256(ramdisk).hexdigest(),
                  boot_sha256=hashlib.sha256(result).hexdigest(), cmdline=cmdline, avb_envelope=envelope,
                  status='prepared-not-device-tested')
    (a.output/'control.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
