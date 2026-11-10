#!/usr/bin/env python3
"""Patch only base DTB 12 in a proven boot; always keep original stock DTBO."""
import argparse
import ctypes
from functools import partial
import hashlib
import json
import pathlib
import struct
import sys
from avb_footer import retain_envelope
from check_usb_stream import primary_usb_stream, require_sid0
from check_watchdog import check_watchdog_control
from check_ufs_pinctrl import check_ufs_pinctrl, check_isolated_pad, UFS_INITCALLS
from check_ufs_phy import check_ufs_phy
from check_ufs_host import check_ufs_host
from prepare_pstore_reader import image_id
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'device_audit'))
from inspect_boot_dt import fdt, inspect

BOOT = 'ddf65a75d5abc34f69517b6eea9769a516ba170b658a24e5ae2fbb04bc9b107b'
SID0_PACED_BOOT = 'df2c4e3b054e0a62a0a0e02a7b1dc797bc6f8b0c386132c5721fff4602049c72'
WATCHDOG_BOOT = '4fac7189f711bb130fcc64b451eabbb822d9cc2e1a1a41a4d7b499f31d2b8d35'
DTBO = '61d9b3ac8426a886de63cf4cde0552e2cab3cd5c47f83ef4335a624b657949ef'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('control-boot', 'stock-dtbo', 'libfdt', 'output'):
        p.add_argument('--'+name, required=True, type=pathlib.Path)
    p.add_argument('--overlay', type=pathlib.Path)
    p.add_argument('--expected-overlay-sha256')
    p.add_argument('--check-usb-sid0', action='store_true',
                   help='Require SID 0/mask 0 on the apps SMMU after the original OEM overlay')
    profiles = p.add_mutually_exclusive_group()
    profiles.add_argument('--watchdog-control', action='store_true',
                   help='Apply the isolated watchdog overlay to the physically tested paced SID0 boot')
    profiles.add_argument('--ufs-pinctrl-control', action='store_true',
                          help='Migrate PDC/TLMM on the tested watchdog boot with storage disabled')
    profiles.add_argument('--ufs-pad-only-control', action='store_true',
                          help='Add an isolated TLMM with the OEM consumers and PDC untouched')
    profiles.add_argument('--ufs-phy-control', action='store_true',
                          help='Add a staged QMP UFS PHY while excluding the storage host driver')
    profiles.add_argument('--ufs-host-control', action='store_true',
                          help='Stage the native UFS host, PHY and interconnect providers')
    profiles.add_argument('--ufs-host-g3-control', action='store_true',
                          help='Stage the G3 host with the F.20 AXI and UniPro frequency range')
    a = p.parse_args()
    host_control = a.ufs_host_control or a.ufs_host_g3_control
    storage_control = a.ufs_pinctrl_control or a.ufs_pad_only_control or a.ufs_phy_control or host_control
    if bool(a.overlay) != bool(a.expected_overlay_sha256):
        p.error('Overlay requires its expected hash')
    if (a.check_usb_sid0 or a.watchdog_control or storage_control) and not a.overlay:
        p.error('The selected control requires a project overlay')
    repo = pathlib.Path(__file__).resolve().parents[2]
    if a.output.resolve() == repo or repo in a.output.resolve().parents:
        p.error('Private outputs stay outside checkout')
    source, dtbo = a.control_boot.read_bytes(), a.stock_dtbo.read_bytes()
    expected_boot = SID0_PACED_BOOT if a.watchdog_control else BOOT
    if storage_control:
        expected_boot = WATCHDOG_BOOT
    if hashlib.sha256(source).hexdigest() != expected_boot or hashlib.sha256(dtbo).hexdigest() != DTBO:
        raise ValueError('Requires the exact baseline boot for this control and original DTBO')
    if image_id(source) != source[576:608]:
        raise ValueError('Source boot ID does not match parsed components')
    trees = inspect(a.control_boot)['trees']
    if len(trees) != 25:
        raise ValueError('Expected original 25-DTB bundle')
    blobs = [source[t['offset']:t['offset']+t['size_bytes']] for t in trees]
    library = ctypes.CDLL(str(a.libfdt.resolve()))
    library.fdt_open_into.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    library.fdt_setprop.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int]
    library.fdt_overlay_apply.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    library.fdt_pack.argtypes = [ctypes.c_void_p]
    buffer = ctypes.create_string_buffer(2*1024*1024)
    if library.fdt_open_into(ctypes.create_string_buffer(blobs[12]), buffer, len(buffer)):
        raise ValueError('Cannot open selected base')
    if a.overlay:
        overlay = a.overlay.read_bytes()
        if hashlib.sha256(overlay).hexdigest() != a.expected_overlay_sha256:
            raise ValueError('Overlay hash mismatch')
        if library.fdt_overlay_apply(buffer, ctypes.create_string_buffer(overlay)):
            raise ValueError('Project overlay cannot apply to captured base')
    else:
        if library.fdt_setprop(buffer, 0, b'rmx2072,diagnostic-stage', b'legacy-marker\0', 14):
            raise ValueError('Cannot add benign marker')
    if library.fdt_pack(buffer):
        raise ValueError('Cannot pack base')
    changed = buffer.raw[:int.from_bytes(buffer.raw[4:8], 'big')]
    original_root, patched_root = fdt(blobs[12])['root'], fdt(changed)['root']
    if original_root != patched_root:
        raise ValueError('Original root selection metadata changed')
    if fdt(blobs[12], ('ramoops',))['matching_nodes'] != fdt(changed, ('ramoops',))['matching_nodes']:
        raise ValueError('pstore layout changed')
    # The unchanged original overlay must still resolve its complete symbol set.
    entries = struct.unpack_from('>I', dtbo, 20)[0]
    size, offset = struct.unpack_from('>2I', dtbo, entries+17*32)
    def with_oem_overlay(base):
        merged = ctypes.create_string_buffer(2*1024*1024)
        if library.fdt_open_into(ctypes.create_string_buffer(base), merged, len(merged)):
            raise ValueError('Cannot validate final merged tree')
        if library.fdt_overlay_apply(merged, ctypes.create_string_buffer(dtbo[offset:offset+size])):
            raise ValueError('Original overlay no longer applies')
        return merged.raw

    merged = with_oem_overlay(changed)
    checks = {}
    if a.watchdog_control:
        checks['watchdog_control'] = {
            'pre_oem': check_watchdog_control(blobs[12], changed),
            'post_oem': check_watchdog_control(with_oem_overlay(blobs[12]), merged),
        }
    if storage_control:
        name, check = 'ufs_pinctrl_control', check_ufs_pinctrl
        if a.ufs_pad_only_control:
            name, check = 'ufs_pad_only_control', check_isolated_pad
        if a.ufs_phy_control:
            name, check = 'ufs_phy_control', check_ufs_phy
        if host_control:
            name = 'ufs_host_g3_control' if a.ufs_host_g3_control else 'ufs_host_control'
            check = partial(check_ufs_host, g3=a.ufs_host_g3_control)
        checks[name] = {
            'pre_oem': check(blobs[12], changed),
            'post_oem': check(with_oem_overlay(blobs[12]), merged),
        }
    project_stream = primary_usb_stream(changed, legacy_base=True, allow_unmapped=True)
    final_usb_stream = None
    if a.check_usb_sid0 or checks:
        final_usb_stream = require_sid0(merged, legacy_base=True)
    elif project_stream is not None:
        final_usb_stream = primary_usb_stream(merged, legacy_base=True)
    if final_usb_stream != project_stream:
        raise ValueError(f'OEM overlay changed primary USB mapping: {project_stream} -> {final_usb_stream}')
    blobs[12] = changed
    start = trees[0]['offset']
    raw = bytearray(source[:start])+b''.join(blobs)
    struct.pack_into('<I', raw, 1648, sum(map(len, blobs)))
    if storage_control and not host_control:
        # OEM fragments 61/62 re-enable both stock nodes. Scope the exclusion
        # to this debug boot, leaving their DT properties and overlays intact.
        current = source[64:576].rstrip(b'\0')
        if any(source[608:1632]) or b'initcall_blacklist=' in current:
            raise ValueError('Unexpected baseline boot command line')
        blocked = ['ufs_qcom_pltform_init'] if a.ufs_phy_control else list(UFS_INITCALLS)
        cmdline = current + b' initcall_blacklist=' + ','.join(blocked).encode()
        if len(cmdline) >= 512:
            raise ValueError('Storage isolation options exceed the boot-v2 command line')
        raw[64:576] = cmdline.ljust(512, b'\0')
        checks['ufs_initcall_blacklist'] = blocked
    raw[576:608] = image_id(raw)
    raw.extend(bytes(-len(raw)%4096))
    result, envelope = retain_envelope(source, raw)
    if result[608:1648] != source[608:1648] or result[1652:start] != source[1652:start]:
        raise ValueError('Non-DT component/header changed')
    a.output.mkdir(exist_ok=False, parents=True)
    (a.output/'boot-diag.img').write_bytes(result)
    (a.output/'dtbo-diag.img').write_bytes(dtbo)
    packaged = inspect(a.output/'boot-diag.img')['trees']
    if len(packaged) != 25 or any(result[t['offset']:t['offset']+t['size_bytes']] != blobs[i]
                                   for i, t in enumerate(packaged)):
        raise ValueError('Repackaged DTB mismatch')
    report = dict(scope='Legacy-tree incremental patch; original DTBO unchanged', source_boot_sha256=expected_boot,
                  boot_sha256=hashlib.sha256(result).hexdigest(), dtbo_sha256=DTBO,
                  selected_base_index=12, other_24_trees_identical=True,
                  selected_base_sha256=hashlib.sha256(changed).hexdigest(),
                  overlay_sha256=a.expected_overlay_sha256,
                  root_selectors_and_pstore_unchanged=True, original_overlay_application_passed=True,
                  avb_envelope=envelope, status='prepared-not-device-tested')
    if final_usb_stream is not None:
        report['final_oem_primary_usb_sid_mask'] = final_usb_stream
    report.update(checks)
    (a.output/'control.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
