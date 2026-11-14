"""Package one source DTB/DTBO with verified source init for the M2 handset test.

Factory boot/DTBO are read only to preserve measured load metadata and the
unlocked-device AVB envelopes. None of their device trees enters the candidate.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct

from avb_footer import retain_envelope
from prepare_pstore_reader import image_id
from wrap_native_image import wrap
from pack_diag_boot import validate_pstore_layout
from inspect_boot_dt import inspect


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
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
    config = (kernel_dir / 'sm8250_bootstrap_dot_config').read_text().splitlines()
    if any('CONFIG_' + name + '=y' not in config for name in ('INPUT_PM8941_PWRKEY', 'POWER_RESET_MSM', 'POWER_RESET_QCOM_PON')):
        raise ValueError('Upstream PON/PS_HOLD drivers are not built in')
    rd = (current / 'ramdisk/ramdisk.cpio.gz').read_bytes()
    provenance = json.loads((current / 'ramdisk/ramdisk-provenance.json').read_text())
    if (not provenance.get('autonomous_ufs') or not provenance.get('guarded_adb') or
            provenance.get('first_stage_source', {}).get('origin') != 'project-source-build'):
        raise ValueError('M2 requires autonomous guarded source-init ramdisk')
    if sha(rd) != provenance['gzip_sha256'] or gzip.decompress(rd)[:6] != b'070701':
        raise ValueError('Invalid ramdisk')
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
    (output / 'control.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({k: record[k] for k in ('boot_sha256', 'dtbo_sha256', 'kernel_sha256')}))


if __name__ == '__main__':
    main()
