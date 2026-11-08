#!/usr/bin/env python3
"""Package a local boot-v2 diagnostic candidate, preserving stock load/OS metadata.

This never writes a device. It does not produce an Android desktop/system image.
"""
import argparse
import gzip
import hashlib
import json
import pathlib
import struct
import subprocess
import sys
from avb_footer import retain_envelope
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'device_audit'))
from inspect_boot_dt import fdt


def validate_pstore_layout(data):
    nodes = fdt(data, ('ramoops',))['matching_nodes']
    expected = {'reg': [0, 0xb0000000, 0, 0x400000], 'record-size': [0x40000],
                'console-size': [0x40000], 'pmsg-size': [0x200000],
                'ftrace-size': [0], 'ecc-size': [16]}
    if len(nodes) != 1 or any(nodes[0]['properties'].get(k) != v for k, v in expected.items()):
        raise ValueError('Diagnostic DT must match the validated ECC console/pmsg reader layout')
    return expected


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda: f.read(8*1024*1024), b''):
            h.update(data)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['stock-boot', 'stock-dtbo', 'kernel', 'config', 'dtb', 'dtbo', 'ramdisk', 'mkbootimg', 'output']:
        p.add_argument('--'+name, required=True, type=pathlib.Path)
    p.add_argument('--disable-cpuidle', action='store_true',
                   help='Isolate upstream PSCI idle-domain entry; diagnostic experiment only')
    a = p.parse_args()
    root = pathlib.Path(__file__).resolve().parents[2]
    if root == a.output.resolve() or root in a.output.resolve().parents:
        p.error('Generated images must remain outside public checkout')
    stock = a.stock_boot.read_bytes()
    word = lambda offset: struct.unpack_from('<I', stock, offset)[0]
    if stock[:8] != b'ANDROID!' or word(40) != 2 or word(36) != 4096 or word(24) != 0 or word(1632) != 0:
        raise ValueError('Expected captured boot-v2 geometry without second/recovery payload')
    config = set(a.config.read_text().splitlines())
    for key in ['ARM64_4K_PAGES', 'PINCTRL_SM8250', 'SM_GCC_8250', 'USB_DWC3_QCOM',
                'PHY_QCOM_USB_SNPS_FEMTO_V2', 'USB_CONFIGFS_ACM', 'PSTORE_RAM',
                'HWSPINLOCK_QCOM', 'QCOM_SMEM', 'QCOM_SCM', 'QCOM_WDT',
                'PSTORE_CONSOLE', 'PSTORE_PMSG', 'REED_SOLOMON_ENC8', 'REED_SOLOMON_DEC8',
                'PROC_FS', 'SYSFS', 'TMPFS', 'BINFMT_ELF', 'BINFMT_SCRIPT', 'RD_GZIP']:
        if 'CONFIG_'+key+'=y' not in config:
            raise ValueError('Required built-in option absent: '+key)
    with a.kernel.open('rb') as f:
        header = f.read(64)
    if header[56:60] != b'ARM\x64':
        raise ValueError('Expected raw ARM64 Image')
    if gzip.decompress(a.ramdisk.read_bytes())[:6] != b'070701':
        raise ValueError('Expected gzip newc initramfs')
    if a.dtb.read_bytes()[:4] != b'\xd0\x0d\xfe\xed' or a.dtbo.read_bytes()[:4] != b'\xd7\xb7\xab\x1e':
        raise ValueError('Invalid DTB/DTBO container magic')
    pstore_layout = validate_pstore_layout(a.dtb.read_bytes())
    version = word(44) >> 11
    patch = word(44) & 0x7ff
    os_version = f'{(version>>14)&127}.{(version>>7)&127}.{version&127}'
    patch_level = f'{2000+(patch>>4):04d}-{patch&15:02d}'
    a.output.mkdir(parents=True, exist_ok=True)
    boot = a.output/'boot-diag.img'
    cmdline = 'rdinit=/init earlycon console=ttyMSM0,115200n8 loglevel=8 ignore_loglevel printk.devkmsg=on clk_ignore_unused pd_ignore_unused fw_devlink=permissive panic=30 androidboot.hardware=qcom'
    if a.disable_cpuidle:
        cmdline += ' cpuidle.off=1'
    command = [sys.executable, str(a.mkbootimg), '--header_version', '2', '--pagesize', '4096',
               '--base', '0', '--kernel_offset', hex(word(12)), '--ramdisk_offset', hex(word(20)),
               '--tags_offset', hex(word(32)), '--dtb_offset', hex(struct.unpack_from('<Q', stock, 1652)[0]),
               '--os_version', os_version, '--os_patch_level', patch_level,
               '--kernel', str(a.kernel), '--ramdisk', str(a.ramdisk), '--dtb', str(a.dtb),
               '--cmdline', cmdline, '--output', str(boot)]
    subprocess.run(command, check=True)
    if boot.stat().st_size > len(stock):
        raise ValueError('Diagnostic boot exceeds stock boot partition capacity')
    packaged, boot_avb = retain_envelope(stock, boot.read_bytes())
    boot.write_bytes(packaged)
    dtbo = a.output/'dtbo-diag.img'
    if a.dtbo.stat().st_size > a.stock_dtbo.stat().st_size:
        raise ValueError('Diagnostic DTBO exceeds partition capacity')
    packaged, dtbo_avb = retain_envelope(a.stock_dtbo.read_bytes(), a.dtbo.read_bytes())
    dtbo.write_bytes(packaged)
    with boot.open('rb') as f:
        result = f.read(1660)
    for offset in [12, 20, 32, 36, 40, 44]:
        if struct.unpack_from('<I', result, offset)[0] != word(offset):
            raise ValueError('Stock load/OS metadata changed')
    report = dict(scope='RAM-only USB diagnostic, not Android desktop', command=command,
                  kernel_sha256=digest(a.kernel), config_sha256=digest(a.config), dtb_sha256=digest(a.dtb),
                  ramdisk_sha256=digest(a.ramdisk), stock_boot_sha256=digest(a.stock_boot),
                  avb_envelopes=dict(boot=boot_avb, dtbo=dtbo_avb),
                  pstore_layout=pstore_layout,
                  cpuidle_disabled=a.disable_cpuidle,
                  outputs={q.name: dict(size_bytes=q.stat().st_size, sha256=digest(q)) for q in [boot, dtbo]},
                  bootloader_requirement='Use diagnostic boot and no-op DTBO together; restore both stock partitions afterward',
                  status='packaged-not-boot-tested')
    (a.output/'packaging.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report['outputs'], indent=2))


if __name__ == '__main__':
    main()
