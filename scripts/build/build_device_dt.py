#!/usr/bin/env python3
"""Compile project DTS against the exact 6.18 source; never flashes a device."""
import argparse
import hashlib
import json
import pathlib
import shutil
import struct
import subprocess
import sys
import tarfile
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'device_audit'))
from inspect_boot_dt import fdt
from check_usb_stream import require_sid0
from check_watchdog import check_watchdog_control
from check_ufs_pinctrl import check_ufs_pinctrl, check_isolated_pad
from check_ufs_phy import check_ufs_phy
from check_ufs_host import check_ufs_host


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work', required=True, type=pathlib.Path)
    p.add_argument('--output', required=True, type=pathlib.Path)
    a = p.parse_args()
    project = pathlib.Path(__file__).resolve().parents[2]
    work, output = a.work.resolve(), a.output.resolve()
    if work == project or project in work.parents:
        p.error('source workspace must be outside checkout')
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    source = next(s for s in json.loads((project/'sources/SOURCE_LOCK.json').read_text())['sources'] if s['id']=='android17-gki-618')
    url = 'https://codeload.github.com/xxbo/RMX2072-AOSP-Project/tar.gz/'+source['mirror_commit']
    archive = work/'source.tar.gz'
    with urllib.request.urlopen(url, timeout=180) as response, archive.open('wb') as dest:
        shutil.copyfileobj(response, dest, 1024*1024)
    with archive.open('rb') as stream:
        archive_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    with tarfile.open(archive) as tf:
        tf.extractall(work/'source', filter='data')
    roots = list((work/'source').iterdir())
    if len(roots)!=1:
        raise ValueError('unexpected source archive structure')
    src = roots[0]
    archive.unlink()
    dts = project/'device/realme/bladerunner_48m/dts'
    commands = []
    with (output/'compile.log').open('w') as log:
        for name in ['sm8250-realme-rmx2072-usb-diag', 'rmx2072-noop-overlay',
                     'rmx2072-legacy-usb-bridge', 'rmx2072-legacy-usb-iommu',
                     'rmx2072-legacy-usb-scm', 'rmx2072-legacy-usb-scm-sid0',
                     'rmx2072-sid0-watchdog', 'rmx2072-ufs-pinctrl', 'rmx2072-ufs-pad-only',
                     'rmx2072-ufs-phy', 'rmx2072-ufs-host']:
            expanded = output/(name+'.expanded.dts')
            cmd = ['gcc', '-E', '-P', '-x', 'assembler-with-cpp', '-nostdinc', '-undef', '-D__DTS__',
                   '-I'+str(src/'include'), '-I'+str(src/'arch/arm64/boot/dts/qcom'), str(dts/(name+'.dts'))]
            commands.append(cmd)
            with expanded.open('wb') as target:
                subprocess.run(cmd, stdout=target, stderr=log, check=True)
            cmd = ['dtc', '-@', '-I', 'dts', '-O', 'dtb', '-o', str(output/(name+'.dtb')), str(expanded)]
            commands.append(cmd)
            subprocess.run(cmd, stdout=log, stderr=log, check=True)
    overlay = (output/'rmx2072-noop-overlay.dtb').read_bytes()
    selectors = fdt(overlay)['root']
    stock_selectors = json.loads((project/'build/device/stock-dt-selection.json').read_text())['dtbo']['selected']['root']
    for selector in ('qcom,board-id', 'oplus,dtsi_no'):
        if selectors.get(selector) != stock_selectors[selector]:
            raise ValueError('Compiled overlay selector differs from captured stock entry: '+selector)
    page = 4096
    size = page+(len(overlay)+page-1)//page*page
    image = bytearray(size)
    struct.pack_into('>8I', image, 0, 0xd7b7ab1e, size, 32, 32, 1, 32, page, 0)
    struct.pack_into('>8I', image, 32, len(overlay), page, 0, 0, 0, 0, 0, 0)
    image[page:page+len(overlay)] = overlay
    (output/'rmx2072-noop-dtbo.img').write_bytes(image)
    # Exercise libfdt's actual overlay application, not just syntax compilation.
    subprocess.run(['fdtoverlay', '-i', str(output/'sm8250-realme-rmx2072-usb-diag.dtb'),
                    '-o', str(output/'merged-diag.dtb'), str(output/'rmx2072-noop-overlay.dtb')], check=True)
    reference = require_sid0((output/'merged-diag.dtb').read_bytes(), legacy_base=False)
    fixture = work/'legacy-usb-base.dtb'
    applied = work/'legacy-usb-applied.dtb'
    subprocess.run(['dtc', '-@', '-I', 'dts', '-O', 'dtb', '-o', str(fixture),
                    str(project/'tests/fixtures/legacy-usb-base.dts')], check=True)
    subprocess.run(['fdtoverlay', '-i', str(fixture), '-o', str(applied),
                    str(output/'rmx2072-legacy-usb-scm-sid0.dtb')], check=True)
    candidate = require_sid0(applied.read_bytes(), legacy_base=True)
    watchdog = work/'legacy-watchdog-applied.dtb'
    subprocess.run(['fdtoverlay', '-i', str(applied), '-o', str(watchdog),
                    str(output/'rmx2072-sid0-watchdog.dtb')], check=True)
    watchdog_control = check_watchdog_control(applied.read_bytes(), watchdog.read_bytes())
    pinctrl = work/'legacy-ufs-pinctrl-applied.dtb'
    subprocess.run(['fdtoverlay', '-i', str(watchdog), '-o', str(pinctrl),
                    str(output/'rmx2072-ufs-pinctrl.dtb')], check=True)
    pinctrl_control = check_ufs_pinctrl(watchdog.read_bytes(), pinctrl.read_bytes())
    pad = work/'legacy-ufs-pad-applied.dtb'
    subprocess.run(['fdtoverlay', '-i', str(watchdog), '-o', str(pad),
                    str(output/'rmx2072-ufs-pad-only.dtb')], check=True)
    pad_control = check_isolated_pad(watchdog.read_bytes(), pad.read_bytes())
    phy = work/'legacy-ufs-phy-applied.dtb'
    subprocess.run(['fdtoverlay', '-i', str(watchdog), '-o', str(phy),
                    str(output/'rmx2072-ufs-phy.dtb')], check=True)
    phy_control = check_ufs_phy(watchdog.read_bytes(), phy.read_bytes())
    host = work/'legacy-ufs-host-applied.dtb'
    subprocess.run(['fdtoverlay', '-i', str(watchdog), '-o', str(host),
                    str(output/'rmx2072-ufs-host.dtb')], check=True)
    host_control = check_ufs_host(watchdog.read_bytes(), host.read_bytes())
    report = dict(upstream_commit=source['commit'], mirror_commit=source['mirror_commit'],
                  overlay_selectors=selectors,
                  watchdog_on_sid0_fixture=watchdog_control,
                  ufs_pinctrl_on_watchdog_fixture=pinctrl_control,
                  isolated_ufs_pad_on_watchdog_fixture=pad_control,
                  ufs_phy_on_watchdog_fixture=phy_control,
                  ufs_host_on_watchdog_fixture=host_control,
                  primary_usb_sid_mask=dict(pinned_reference=reference, sid0_on_fixture=candidate),
                  legacy_usb_bridge='SID0 applied to synthetic targets; handset requires private OEM merge',
                  archive_sha256=archive_hash, commands=commands,
                  status='compiled-and-overlay-applied-not-device-tested',
                  scope='Independent USB, watchdog and UFS diagnostic overlays',
                  files={f.name: dict(size_bytes=f.stat().st_size, sha256=hashlib.sha256(f.read_bytes()).hexdigest())
                         for f in output.iterdir() if f.is_file()})
    (output/'provenance.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(status=report['status'], files=len(report['files']))))


if __name__ == '__main__':
    main()
