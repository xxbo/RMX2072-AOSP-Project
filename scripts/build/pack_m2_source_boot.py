"""Package one source DTB/DTBO with verified source init for the M2 handset test.

Factory boot/DTBO are read only to preserve measured load metadata and the
unlocked-device AVB envelopes. None of their device trees enters the candidate.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import struct

from avb_footer import retain_envelope
from prepare_pstore_reader import image_id
from wrap_native_image import wrap
from pack_diag_boot import validate_pstore_layout
from inspect_boot_dt import inspect


def sha(data):
    return hashlib.sha256(data).hexdigest()


def scratch_boot_argument(provenance):
    """Identify only the checked RAM scratch profile, never physical userdata."""
    volumes = provenance.get('scratch_volumes')
    if volumes is None:
        return ''
    if (not provenance.get('autonomous_ufs') or not provenance.get('guarded_adb')
            or set(volumes) != {'data', 'metadata'}):
        raise ValueError('Scratch framework startup requires guarded isolated volumes')
    for name, sizes in [('data', (512 << 20, 2048 << 20)), ('metadata', (32 << 20,))]:
        info = volumes[name]
        if (info.get('bytes') not in sizes or any(
                not re.fullmatch(r'[0-9a-f]{64}', info.get(key, ''))
                for key in ('sha256', 'gzip_sha256'))):
            raise ValueError('Unchecked scratch volume for framework startup: ' + name)
    return ' androidboot.rmx_scratch=1'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--single-dsc-test', action='store_true')
    parser.add_argument('--solid-fill-test', action='store_true')
    parser.add_argument('--panel-readback-test', action='store_true')
    parser.add_argument('--stock-linkclock-test', action='store_true')
    parser.add_argument('--stock-dsc-test', action='store_true')
    parser.add_argument('--stock-phy-test', action='store_true')
    parser.add_argument('--first-frame-trace', action='store_true')
    parser.add_argument('--standard-pps-test', action='store_true')
    a = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    work = a.workspace.resolve()
    if work.is_relative_to(repo):
        parser.error('Keep generated images outside the repository')
    current = work / 'current'
    source = current / 'source-dt'
    dt = json.loads((source / 'source.json').read_text())
    if dt.get('factory_binary_inputs') is not False or dt.get('project_dirty'):
        raise ValueError('Requires committed, source-only device tree build')
    if a.single_dsc_test and not dt.get('display'):
        raise ValueError('Single DSC test requires the display device tree')
    if a.solid_fill_test and not dt.get('display'):
        raise ValueError('Solid-fill test requires the display device tree')
    if a.panel_readback_test and not dt.get('display'):
        raise ValueError('Panel readback requires the display device tree')
    if a.stock_linkclock_test and not dt.get('display'):
        raise ValueError('Stock link clock test requires the display device tree')
    if a.stock_dsc_test and (not a.stock_linkclock_test or not a.single_dsc_test):
        raise ValueError('Stock DSC comparison requires the trial 65 stock clock and single DSC route')
    if a.stock_phy_test and not a.stock_dsc_test:
        raise ValueError('Stock PHY timing test requires the trial 66 stock DSC configuration')
    if a.first_frame_trace and (not a.stock_phy_test or not dt.get('display_staged')):
        raise ValueError('First-frame tracing requires the staged trial 67 baseline')
    if a.standard_pps_test and (not a.first_frame_trace or not a.panel_readback_test):
        raise ValueError('Standard PPS isolation requires the complete trial 68 baseline')
    for name, expected in dt['outputs'].items():
        data = (source / name).read_bytes()
        if len(data) != expected['size_bytes'] or sha(data) != expected['sha256']:
            raise ValueError('Device tree build digest mismatch: ' + name)
    kernel_dir = current / 'kernel'
    kernel = json.loads((kernel_dir / 'provenance.json').read_text())
    raw = (kernel_dir / 'Image').read_bytes()
    if kernel.get('installing') or not kernel.get('source_digests_verified') or sha(raw) != kernel['image_sha256']:
        raise ValueError('Kernel source/build evidence is incomplete')
    patch = (repo / 'device/realme/bladerunner_48m/bootstrap-patches/rmx2072-source-pon.patch').read_bytes().replace(b'\r\n', b'\n')
    if (kernel_dir / 'source-pon-patch.sha256').read_text().split()[0] != sha(patch):
        raise ValueError('Kernel does not contain the reviewed source-tree PON patch')
    if dt.get('display'):
        patch = (repo / 'device/realme/bladerunner_48m/bootstrap-patches/rmx2072-display-clock.patch').read_bytes().replace(b'\r\n', b'\n')
        manifest = kernel_dir / 'display-clock-patch.sha256'
        if not manifest.is_file() or manifest.read_text().split()[0] != sha(patch):
            raise ValueError('Display DT requires the matching deferred DSI clock-parent kernel patch')
    config = (kernel_dir / 'sm8250_bootstrap_dot_config').read_text().splitlines()
    if dt.get('display') and 'CONFIG_REGULATOR_QCOM_REFGEN=y' not in config:
        raise ValueError('Display DT requires the native REFGEN regulator driver')
    if a.single_dsc_test:
        name = 'rmx2072-dsc-route-test'
        patch = (repo / ('device/realme/bladerunner_48m/bootstrap-patches/' + name + '.patch')).read_bytes().replace(b'\r\n', b'\n')
        manifest = kernel_dir / (name + '.sha256')
        if not manifest.is_file() or manifest.read_text().split()[0] != sha(patch):
            raise ValueError('Single DSC test requires the verified matching kernel patch')
    if a.solid_fill_test:
        name = 'rmx2072-dpu-solid-fill-test'
        patch = (repo / ('device/realme/bladerunner_48m/bootstrap-patches/' + name + '.patch')).read_bytes().replace(b'\r\n', b'\n')
        manifest = kernel_dir / (name + '.sha256')
        if not manifest.is_file() or manifest.read_text().split()[0] != sha(patch):
            raise ValueError('Solid-fill test requires the verified matching kernel patch')
    if a.stock_linkclock_test:
        name = 'rmx2072-stock-linkclock-test'
        patch = (repo / ('device/realme/bladerunner_48m/bootstrap-patches/' + name + '.patch')).read_bytes().replace(b'\r\n', b'\n')
        manifest = kernel_dir / (name + '.sha256')
        if not manifest.is_file() or manifest.read_text().split()[0] != sha(patch):
            raise ValueError('Stock link clock test requires the verified matching kernel patch')
    if a.stock_dsc_test:
        name = 'rmx2072-stock-dsc-test'
        patch = (repo / ('device/realme/bladerunner_48m/bootstrap-patches/' + name + '.patch')).read_bytes().replace(b'\r\n', b'\n')
        manifest = kernel_dir / (name + '.sha256')
        if not manifest.is_file() or manifest.read_text().split()[0] != sha(patch):
            raise ValueError('Stock DSC test requires the verified matching kernel patch')
    if a.stock_phy_test:
        name = 'rmx2072-stock-phy-timing-test'
        patch = (repo / ('device/realme/bladerunner_48m/bootstrap-patches/' + name + '.patch')).read_bytes().replace(b'\r\n', b'\n')
        manifest = kernel_dir / (name + '.sha256')
        if not manifest.is_file() or manifest.read_text().split()[0] != sha(patch):
            raise ValueError('Stock PHY timing test requires the verified matching kernel patch')
    if a.panel_readback_test:
        panel = repo / 'device/realme/bladerunner_48m/display/panel-samsung-rm19795.c'
        manifest = kernel_dir / 'display-source.sha256'
        hashes = {Path(row.split()[1]).name:row.split()[0]
                  for row in manifest.read_text().splitlines()} if manifest.is_file() else {}
        if hashes.get(panel.name) != sha(panel.read_bytes().replace(b'\r\n', b'\n')):
            raise ValueError('Panel readback requires the verified matching panel source')
    if a.first_frame_trace:
        name = 'rmx2072-first-frame-trace'
        patch = (repo / ('device/realme/bladerunner_48m/bootstrap-patches/' + name + '.patch')).read_bytes().replace(b'\r\n', b'\n')
        manifest = kernel_dir / (name + '.sha256')
        if not manifest.is_file() or manifest.read_text().split()[0] != sha(patch):
            raise ValueError('First-frame tracing requires the verified matching kernel patch')
    if any('CONFIG_' + name + '=y' not in config for name in ('INPUT_PM8941_PWRKEY', 'POWER_RESET_MSM', 'POWER_RESET_QCOM_PON')):
        raise ValueError('Upstream PON/PS_HOLD drivers are not built in')
    rd = (current / 'ramdisk/ramdisk.cpio.gz').read_bytes()
    provenance = json.loads((current / 'ramdisk/ramdisk-provenance.json').read_text())
    if bool(provenance.get('first_frame_trace')) != a.first_frame_trace:
        raise ValueError('First-frame trace request and ramdisk marker must agree')
    if bool(provenance.get('solid_fill_test')) != a.solid_fill_test:
        raise ValueError('Solid-fill boot request and ramdisk marker must agree')
    if (not provenance.get('autonomous_ufs') or not provenance.get('guarded_adb') or
            provenance.get('first_stage_source', {}).get('origin') != 'project-source-build'):
        raise ValueError('M2 requires autonomous guarded source-init ramdisk')
    if sha(rd) != provenance['gzip_sha256'] or gzip.decompress(rd)[:6] != b'070701':
        raise ValueError('Invalid ramdisk')
    if bool(dt.get('display_staged')) != bool(provenance.get('display_staged')):
        raise ValueError('Staged display DT and ramdisk gate must agree')
    stock = (work / 'recovery/f20/boot.img').read_bytes()
    stock_dtbo = (work / 'recovery/f20/dtbo.img').read_bytes()
    if sha(stock) != '9ae2f907fd029e88c841121f4fbeb6f3a1ae32322a6703d8d142bbba31bb93c3' or sha(stock_dtbo) != '61d9b3ac8426a886de63cf4cde0552e2cab3cd5c47f83ef4335a624b657949ef':
        raise ValueError('Original recovery metadata differs')
    word = lambda n: struct.unpack_from('<I', stock, n)[0]
    if stock[:8] != b'ANDROID!' or image_id(stock) != stock[576:608] or word(40) != 2 or word(36) != 4096 or word(24) or word(1632):
        raise ValueError('Unexpected boot-v2 geometry')
    tree = (source / 'rmx2072.dtb').read_bytes()
    validate_pstore_layout(tree)
    wrapped = wrap(raw, None)  # Entry probe must never overwrite ECC pmsg.
    header = bytearray(stock[:4096])
    cmdline = ('rdinit=/init earlycon console=ttyMSM0,115200n8 loglevel=8 ignore_loglevel '
               'printk.devkmsg=on clk_ignore_unused pd_ignore_unused fw_devlink=permissive '
               'panic=30 androidboot.hardware=qcom '
               'androidboot.boot_devices=soc/soc:ufs-host-lab/1d84000.ufs '
               'tp_printk tp_printk_stop_on_boot')
    if dt.get('display'):
        # MSM's DBG clock/PHY messages use DRM_UT_DRIVER (bit 1).
        cmdline += ' initcall_debug drm.debug=0x2'
    if a.single_dsc_test:
        cmdline += ' msm.rmx2072_single_dsc=1'
    if a.panel_readback_test:
        cmdline += ' panel_samsung_rm19795.readback=1'
    if a.stock_linkclock_test:
        cmdline += ' msm.rmx2072_stock_linkclk=1'
    if a.stock_dsc_test:
        cmdline += ' msm.rmx2072_stock_dsc=1'
    if a.stock_phy_test:
        cmdline += ' msm.rmx2072_stock_phy=1'
    if a.standard_pps_test:
        cmdline += ' panel_samsung_rm19795.pps=1'
    cmdline += scratch_boot_argument(provenance)
    if len(cmdline.encode()) >= 512:
        raise ValueError('Diagnostic command line exceeds the boot header field')
    header[64:576] = cmdline.encode().ljust(512, b'\0')
    header[608:1632] = bytes(1024)
    for offset, value in ((8, len(wrapped)), (16, len(rd)), (1648, len(tree))):
        struct.pack_into('<I', header, offset, value)
    payload = header + wrapped + bytes(-len(wrapped) % 4096) + rd + bytes(-len(rd) % 4096) + tree
    payload[576:608] = image_id(payload)
    payload.extend(bytes(-len(payload) % 4096))
    boot, boot_avb = retain_envelope(stock, payload)
    dtbo, dtbo_avb = retain_envelope(stock_dtbo, (source / 'dtbo.img').read_bytes())
    output = current / 'boot'
    allowed = {'boot-diag.img', 'dtbo-diag.img', 'control.json'}
    if any(p.name not in allowed or not p.is_file() for p in output.iterdir()):
        raise ValueError('Unrecognized candidate boot directory')
    (output / 'boot-diag.img').write_bytes(boot)
    (output / 'dtbo-diag.img').write_bytes(dtbo)
    for name, expected in (('boot-diag.img', tree), ('dtbo-diag.img', (source / 'rmx2072.dtbo').read_bytes())):
        trees = inspect(output / name)['trees']
        if len(trees) != 1 or trees[0]['sha256'] != sha(expected):
            raise ValueError('Packaged source device tree differs')
    record = dict(source_device_trees=True, boot_sha256=sha(boot), dtbo_sha256=sha(dtbo),
                  source_boot_sha256=sha(stock), source_dtbo_sha256=sha(stock_dtbo),
                  kernel_sha256=sha(raw), ramdisk_sha256=sha(rd), dtb_bundle_sha256=sha(tree),
                  selected_base_sha256=sha(tree), dtb_entries=1, dtbo_entries=1,
                  first_stage_init_sha256=provenance['first_stage_init_sha256'],
                  device_tree_build=dt, cmdline=cmdline, entry_probe=False,
                  avb_envelopes=dict(boot=boot_avb, dtbo=dtbo_avb),
                  status='packaged-not-device-tested')
    # The autonomous UFS ramdisk variant also hosts gated display experiments.
    # A retained Android guardian does not remove that next-boot host gate.
    record['boot_start_policy'] = 'host-gated-display' if provenance.get('display_staged') else 'autonomous-ufs'
    record['host_start_required_after_every_reboot'] = bool(provenance.get('display_staged'))
    record['single_dsc_test'] = a.single_dsc_test
    record['solid_fill_test'] = a.solid_fill_test
    record['panel_readback_test'] = a.panel_readback_test
    record['stock_linkclock_test'] = a.stock_linkclock_test
    record['stock_dsc_test'] = a.stock_dsc_test
    record['stock_phy_test'] = a.stock_phy_test
    record['first_frame_trace'] = a.first_frame_trace
    record['standard_pps_test'] = a.standard_pps_test
    record['scratch_framework_start'] = bool(provenance.get('scratch_volumes'))
    (output / 'control.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({k: record[k] for k in ('boot_sha256', 'dtbo_sha256', 'kernel_sha256')}))


if __name__ == '__main__':
    main()
