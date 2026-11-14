"""Rebuild the measured UFS diagnostic tree from the retained F.20 reader boot.

No historical intermediate boot images are needed. This packages an unlocked
engineering boot only; the retained stock AVB envelope does not sign its payload.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import struct
import sys

from avb_footer import retain_envelope
from prepare_pstore_reader import image_id
from wrap_native_image import wrap
from pack_diag_boot import validate_pstore_layout
from check_watchdog import check_watchdog_control
from check_ufs_host import check_ufs_host
from check_pdc import check_pdc_control
from check_usb_stream import require_sid0
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'device_audit'))
from inspect_boot_dt import inspect, fdt

OVERLAYS = {
    'rmx2072-legacy-usb-scm-sid0.dtb': '1005264c3bc6a07c753e99088358f0465e49b2621243a426e51a0f975ff030e4',
    'rmx2072-sid0-watchdog.dtb': '4bd8ef4974d2160f2ba230259e7058bf50beecd9698e382ed7d464ac2bb40e7a',
    'rmx2072-ufs-host-g3.dtb': '5937aeb644b5784dc20e354e9f3a8b87eaf4cf30e8ab3e3a1680394f25e5ea59',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pack(stock_boot, stock_dtbo, overlays, libfdt, kernel, expected_kernel_sha256,
         ramdisk, output, entry_probe=None, pdc_overlay=None):
    repo = Path(__file__).resolve().parents[2]
    if output.resolve().is_relative_to(repo):
        raise ValueError('Keep private images outside the repository')
    source, dtbo = stock_boot.read_bytes(), stock_dtbo.read_bytes()
    if sha(source) != '9ae2f907fd029e88c841121f4fbeb6f3a1ae32322a6703d8d142bbba31bb93c3':
        raise ValueError('Requires the verified F.20 logging-reader boot')
    if sha(dtbo) != '61d9b3ac8426a886de63cf4cde0552e2cab3cd5c47f83ef4335a624b657949ef':
        raise ValueError('Requires original DTBO')
    if source[:8] != b'ANDROID!' or image_id(source) != source[576:608]:
        raise ValueError('Invalid source boot')
    word = lambda n: struct.unpack_from('<I', source, n)[0]
    if word(40) != 2 or word(36) != 4096 or word(24) or word(1632):
        raise ValueError('Unexpected boot-v2 layout')
    trees = inspect(stock_boot)['trees']
    if len(trees) != 25:
        raise ValueError('Expected all 25 original base trees')
    blobs = [source[t['offset']:t['offset']+t['size_bytes']] for t in trees]
    original = blobs[12]
    validate_pstore_layout(original)
    library = ctypes.CDLL(str(libfdt.resolve()))
    library.fdt_open_into.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    library.fdt_overlay_apply.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    library.fdt_pack.argtypes = [ctypes.c_void_p]

    def apply(base, overlay):
        buffer = ctypes.create_string_buffer(2*1024*1024)
        if library.fdt_open_into(ctypes.create_string_buffer(base), buffer, len(buffer)):
            raise ValueError('Cannot open base DTB')
        if library.fdt_overlay_apply(buffer, ctypes.create_string_buffer(overlay)):
            raise ValueError('Overlay no longer applies')
        if library.fdt_pack(buffer):
            raise ValueError('Cannot pack applied DTB')
        return buffer.raw[:int.from_bytes(buffer.raw[4:8], 'big')]

    table = struct.unpack_from('>I', dtbo, 20)[0]
    size, offset = struct.unpack_from('>2I', dtbo, table+17*32)
    oem = dtbo[offset:offset+size]
    stages = [original]
    for name, expected in OVERLAYS.items():
        overlay = (overlays/name).read_bytes()
        if sha(overlay) != expected:
            raise ValueError('Unexpected compiled overlay: '+name)
        stages.append(apply(stages[-1], overlay))
    checks = dict(
        watchdog_pre_oem=check_watchdog_control(stages[1], stages[2]),
        watchdog_post_oem=check_watchdog_control(apply(stages[1], oem), apply(stages[2], oem)),
        ufs_pre_oem=check_ufs_host(stages[2], stages[3], g3=True),
        ufs_post_oem=check_ufs_host(apply(stages[2], oem), apply(stages[3], oem), g3=True),
        final_usb_sid=require_sid0(apply(stages[3], oem), legacy_base=True))
    validate_pstore_layout(stages[3])
    if fdt(original)['root'] != fdt(stages[3])['root']:
        raise ValueError('Board selectors changed')
    blobs[12] = stages[3]
    raw_kernel = kernel.read_bytes()
    if sha(raw_kernel) != expected_kernel_sha256:
        raise ValueError('Kernel digest mismatch')
    # Autonomous recovery owns pmsg. The old entry probe overwrites its data
    # without updating ramoops ECC and can destroy the previous guard marker.
    wrapped = wrap(raw_kernel, entry_probe.read_bytes() if entry_probe else None)
    rd = ramdisk.read_bytes()
    import gzip
    if gzip.decompress(rd)[:6] != b'070701':
        raise ValueError('Invalid diagnostic ramdisk')
    header = bytearray(source[:4096])
    command = ('rdinit=/init earlycon console=ttyMSM0,115200n8 loglevel=8 ignore_loglevel '
               'printk.devkmsg=on clk_ignore_unused pd_ignore_unused fw_devlink=permissive '
               'panic=30 androidboot.hardware=qcom '
               'androidboot.boot_devices=soc/soc:ufs-host-lab/1d84000.ufs '
               'tp_printk tp_printk_stop_on_boot').encode()
    if len(command) >= 512:
        raise ValueError('Command line too long')
    header[64:576] = command.ljust(512, b'\0')
    header[608:1632] = bytes(1024)
    bundle = b''.join(blobs)
    if sha(bundle) != '40860552644099158f121f2b14c3d92d26c85bf55b2fd4988fc1faa9a9c27758':
        raise ValueError('Rebuilt bundle differs from the previously tested G3 bundle')
    extra_overlays = {}
    if pdc_overlay:
        overlay = pdc_overlay.read_bytes()
        if sha(overlay) != '453d9e5e753cb0e6196e17e301c79c430bbd1f4541f62106c78c5c759d5c3519':
            raise ValueError('Unexpected PDC-only overlay')
        changed = apply(blobs[12], overlay)
        checks['pdc_pre_oem'] = check_pdc_control(blobs[12], changed)
        checks['pdc_post_oem'] = check_pdc_control(apply(blobs[12], oem), apply(changed, oem))
        blobs[12] = changed
        bundle = b''.join(blobs)
        extra_overlays['pdc_only'] = sha(overlay)
    for at, value in ((8, len(wrapped)), (16, len(rd)), (1648, len(bundle))):
        struct.pack_into('<I', header, at, value)
    raw = header + wrapped + bytes(-len(wrapped)%4096) + rd + bytes(-len(rd)%4096) + bundle
    raw[576:608] = image_id(raw)
    raw.extend(bytes(-len(raw)%4096))
    result, envelope = retain_envelope(source, raw)
    if output.exists() and any(p.name not in {'boot-diag.img','control.json'} or not p.is_file() for p in output.iterdir()):
        raise ValueError('Refuse to replace an unrecognized boot output directory')
    output.mkdir(parents=True, exist_ok=True)
    path = output/'boot-diag.img'
    path.write_bytes(result)
    packed = inspect(path)['trees']
    if len(packed) != 25 or any(result[t['offset']:t['offset']+t['size_bytes']] != blobs[i]
                                for i, t in enumerate(packed)):
        raise ValueError('Packaged DTB bundle differs')
    record = dict(source_boot_sha256=sha(source), dtbo_sha256=sha(dtbo), boot_sha256=sha(result),
                  kernel_sha256=sha(raw_kernel), entry_probe=bool(entry_probe),
                  ramdisk_sha256=sha(rd), dtb_bundle_sha256=sha(bundle),
                  selected_base_sha256=sha(blobs[12]), other_24_trees_identical=True,
                  extra_overlays=extra_overlays,
                  overlays=OVERLAYS, checks=checks, cmdline=command.decode(), avb_envelope=envelope,
                  status='packaged-not-device-tested')
    (output/'control.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(dict(boot_sha256=record['boot_sha256'], dtb_bundle_sha256=record['dtb_bundle_sha256'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('stock-boot', 'stock-dtbo', 'overlays', 'libfdt', 'kernel', 'ramdisk', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--entry-probe', type=Path)
    parser.add_argument('--pdc-overlay', type=Path, help='Independently checked PDC-only binding control')
    parser.add_argument('--expected-kernel-sha256', required=True)
    pack(**vars(parser.parse_args()))
