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
                     'rmx2072-legacy-usb-bridge', 'rmx2072-legacy-usb-iommu']:
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
    report = dict(upstream_commit=source['commit'], mirror_commit=source['mirror_commit'],
                  overlay_selectors=selectors,
                  legacy_usb_bridge='compile only; private downstream base required for application',
                  archive_sha256=archive_hash, commands=commands,
                  status='compiled-and-overlay-applied-not-device-tested',
                  scope='USB diagnostic only; UFS, display and Android system are not enabled by this DT',
                  files={f.name: dict(size_bytes=f.stat().st_size, sha256=hashlib.sha256(f.read_bytes()).hexdigest())
                         for f in output.iterdir() if f.is_file()})
    (output/'provenance.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(status=report['status'], files=len(report['files']))))


if __name__ == '__main__':
    main()
