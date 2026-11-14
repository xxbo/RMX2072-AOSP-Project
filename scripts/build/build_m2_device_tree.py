"""Build the 20607 DTB and complete board DTBO from pinned source, without images.

The optional measurements are checked separately; no factory DTB enters this
generator. The source staging tree is small and overwritten on each build.
"""
import argparse
import base64
import ctypes
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import urllib.request

from pack_diag_boot import validate_pstore_layout
from check_usb_stream import require_sid0
from check_watchdog import check_watchdog_control
from check_ufs_host import check_ufs_host
from check_pdc import check_pdc_control
from check_m2_resources import check_m2_resources
from inspect_boot_dt import fdt

OVERLAYS = ('rmx2072-legacy-usb-scm-sid0', 'rmx2072-sid0-watchdog',
            'rmx2072-ufs-host-g3', 'rmx2072-pdc-only')
ACK_HEADERS = ('clock/qcom,gcc-sm8250.h', 'clock/qcom,rpmh.h',
               'interrupt-controller/arm-gic.h', 'interrupt-controller/irq.h',
               'interconnect/qcom,sm8250.h')


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Fdt:
    def __init__(self, path):
        self.lib = ctypes.CDLL(str(path.resolve()))
        self.lib.fdt_open_into.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
        self.lib.fdt_overlay_apply.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.lib.fdt_pack.argtypes = [ctypes.c_void_p]

    def apply(self, base, overlay):
        buf = ctypes.create_string_buffer(4 * 1024 * 1024)
        if self.lib.fdt_open_into(ctypes.create_string_buffer(base), buf, len(buf)):
            raise ValueError('Cannot open source base')
        rc = self.lib.fdt_overlay_apply(buf, ctypes.create_string_buffer(overlay))
        if rc:
            raise ValueError(f'Source overlay application failed: {rc}')
        if self.lib.fdt_pack(buf):
            raise ValueError('Cannot pack source tree')
        return buf.raw[:int.from_bytes(buf.raw[4:8], 'big')]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('source', 'output', 'cpp', 'dtc', 'libfdt'):
        p.add_argument('--' + key, required=True, type=Path)
    a = p.parse_args()
    repo = Path(__file__).resolve().parents[2]
    source, output = a.source.resolve(), a.output.resolve()
    if output.is_relative_to(repo) or output.is_relative_to(source):
        p.error('Keep generated trees outside the project and upstream checkout')
    lock = json.loads((repo / 'sources/SOURCE_LOCK.json').read_text())['sources']
    official = next(s for s in lock if s['id'] == 'realme-player-android-q-kernel')
    ack = next(s for s in lock if s['id'] == 'android17-gki-618')
    revision = subprocess.check_output(['git', '-C', source, 'rev-parse', 'HEAD'], text=True).strip()
    if revision != official['commit']:
        raise ValueError('Official board source is not at the locked revision')
    paths = ['arch/arm64/boot/dts/20607', 'include/dt-bindings', 'include/uapi/linux/input-event-codes.h']
    if subprocess.check_output(['git', '-C', source, 'status', '--porcelain', '--', *paths]):
        raise ValueError('Official board source has local modifications')
    output.mkdir(parents=True, exist_ok=True)
    stage = output / 'source'
    board = stage / 'board'
    includes = stage / 'include'
    board.mkdir(parents=True, exist_ok=True)
    inputs = {}
    # Materialize tracked blobs through git: this also handles Windows symlink
    # checkouts and makes the source bytes independent of core.autocrlf.
    entries = subprocess.check_output(['git', '-C', source, 'ls-files', '-s', '--', *paths], text=True)
    entries = entries.splitlines()
    data_stream = io.BytesIO(subprocess.check_output(['git', '-C', source, 'cat-file', '--batch'],
        input=''.join(line.split()[1] + '\n' for line in entries).encode()))
    for line in entries:
        metadata, name = line.split('\t', 1)
        mode, blob, _ = metadata.split()
        returned, kind, length = data_stream.readline().decode().split()
        if returned != blob or kind != 'blob':
            raise ValueError('Unexpected git source object')
        data = data_stream.read(int(length))
        if data_stream.read(1) != b'\n':
            raise ValueError('Truncated git source batch')
        inputs[name] = sha(data)
        target = board / name.split('/20607/', 1)[1] if '/20607/' in name else stage / name
        if mode == '120000':
            linked = (source / name).parent.joinpath(data.decode()).resolve()
            if not linked.is_relative_to(source):
                raise ValueError('Source symlink escapes the pinned checkout')
            relative = linked.relative_to(source).as_posix()
            data = subprocess.check_output(['git', '-C', source, 'show', revision + ':' + relative])
            inputs[relative] = sha(data)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    project = repo / 'device/realme/bladerunner_48m/dts'
    patch = project / 'rmx2072-m2-pm8150.patch'
    subprocess.run(['git', 'apply', '--check', patch], cwd=board, check=True)
    subprocess.run(['git', 'apply', patch], cwd=board, check=True)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    ack_include = output / 'ack-include'
    ack_inputs = {}
    header_lock = json.loads((repo / 'build/m2-dt-bindings.json').read_text())
    if header_lock['ack_commit'] != ack['commit']:
        raise ValueError('DT binding header lock does not match the kernel source')
    for header in ACK_HEADERS:
        rel = 'include/dt-bindings/' + header
        url = 'https://android.googlesource.com/kernel/common/+/' + ack['commit'] + '/' + rel + '?format=TEXT'
        target = ack_include / 'dt-bindings' / header
        data = target.read_bytes() if target.is_file() else b''
        if sha(data) != header_lock['files'][rel]:
            data = base64.b64decode(opener.open(url, timeout=60).read(), validate=True)
        if sha(data) != header_lock['files'][rel]:
            raise ValueError('Pinned DT header digest mismatch: ' + rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        ack_inputs[rel] = sha(data)
    project_inputs = {}
    def compile(name, dirs):
        expanded = output / (name + '.expanded.dts')
        cmd = [str(a.cpp.resolve()), '-E', '-P', '-x', 'assembler-with-cpp',
               '-nostdinc', '-undef', '-D__DTS__', *['-I' + str(d) for d in dirs],
               str(project / (name + '.dts'))]
        with expanded.open('wb') as out:
            subprocess.run(cmd, stdout=out, check=True)
        with (output / (name + '.warnings')).open('wb') as log:
            subprocess.run([a.dtc.resolve(), '-@', '-I', 'dts', '-O', 'dtb', '-o',
                            output / (name + '.dtb'), expanded], stderr=log, check=True)
        return (output / (name + '.dtb')).read_bytes()
    base = compile('rmx2072-m2-base', (includes, board, project))
    overlay = compile('rmx2072-m2-overlay', (includes, board, project))
    lib = Fdt(a.libfdt)
    overlays = {name: compile(name, (ack_include, project)) for name in OVERLAYS}
    stages = [base]
    for name in OVERLAYS:
        stages.append(lib.apply(stages[-1], overlays[name]))
    checks = {}
    # Existing subsystem checks run both before and after the complete source
    # board overlay, including phandle relocation and the parked legacy host.
    for suffix, trees in [('base', stages), ('board', [lib.apply(t, overlay) for t in stages])]:
        checks['watchdog_' + suffix] = check_watchdog_control(trees[1], trees[2])
        checks['ufs_' + suffix] = check_ufs_host(trees[2], trees[3], g3=True)
        checks['pdc_' + suffix] = check_pdc_control(trees[3], trees[4])
        checks['pstore_' + suffix] = validate_pstore_layout(trees[4])
        checks['usb_' + suffix] = require_sid0(trees[4], legacy_base=True)
    final = stages[-1]
    effective = lib.apply(final, overlay)
    checks['m1_resource_reference'] = check_m2_resources(effective)
    expected = json.loads((repo / 'build/device/stock-dt-selection.json').read_text())
    for data, entry in ((final, expected['boot']['selected']), (overlay, expected['dtbo']['selected'])):
        # The early selection inventory omitted the base's OEM property;
        # independent F.20 parsing confirms it is 20607 on both entries.
        selectors = dict(entry['root'], **{'oplus,dtsi_no': [20607]})
        if fdt(data)['root'] != selectors:
            raise ValueError('Source board selectors do not match the measured handset')
    # Single exact board entry, with full hardware content. No unselected OEM
    # trees or precompiled overlay bytes are placed in either output.
    size = 4096 + (len(overlay) + 4095) // 4096 * 4096
    container = bytearray(size)
    struct.pack_into('>8I', container, 0, 0xd7b7ab1e, size, 32, 32, 1, 32, 4096, 0)
    struct.pack_into('>8I', container, 32, len(overlay), 4096, 0, 0, 0, 0, 0, 0)
    container[4096:4096 + len(overlay)] = overlay
    blobs = {'rmx2072.dtb': final, 'rmx2072.dtbo': overlay,
             'dtbo.img': bytes(container), 'effective.dtb': effective}
    for name, data in blobs.items():
        (output / name).write_bytes(data)
    for path in project.iterdir():
        if path.is_file() and path.suffix in ('.dts', '.dtsi', '.patch'):
            project_inputs[path.name] = sha(path.read_bytes())
    report = dict(schema_version=1, official_source=official, ack_source=ack,
                  official_inputs=inputs, ack_inputs=ack_inputs, project_inputs=project_inputs,
                  project_commit=subprocess.check_output(['git', '-C', repo, 'rev-parse', 'HEAD'], text=True).strip(),
                  project_dirty=bool(subprocess.check_output(['git', '-C', repo, 'status', '--porcelain'])),
                  tools={k: sha(getattr(a, k).read_bytes()) for k in ('cpp', 'dtc', 'libfdt')},
                  outputs={name: dict(size_bytes=len(data), sha256=sha(data)) for name, data in blobs.items()},
                  overlays={name: sha(data) for name, data in overlays.items()}, checks=checks,
                  factory_binary_inputs=False, status='source-built-not-device-tested')
    (output / 'source.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report['outputs'], indent=2))


if __name__ == '__main__':
    main()
