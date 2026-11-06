#!/usr/bin/env python3
"""Read-only RMX2072 audit. Raw evidence must remain outside the public repository."""
import argparse
import gzip
import hashlib
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

PROPERTIES = (
    'ro.product.model', 'ro.product.device', 'ro.product.name', 'ro.product.board',
    'ro.board.platform', 'ro.hardware', 'ro.soc.model', 'ro.soc.manufacturer',
    'ro.build.display.id', 'ro.build.fingerprint', 'ro.build.version.ota',
    'ro.build.version.release', 'ro.build.version.sdk', 'ro.build.version.security_patch',
    'ro.vendor.build.fingerprint', 'ro.vendor.build.security_patch',
    'ro.vendor.build.version.sdk', 'ro.product.first_api_level', 'ro.board.first_api_level',
    'ro.vndk.version', 'ro.vendor.api_level', 'ro.treble.enabled',
    'ro.product.cpu.abilist', 'ro.boot.flash.locked', 'ro.boot.vbmeta.device_state',
    'ro.boot.verifiedbootstate', 'ro.boot.veritymode', 'ro.boot.slot_suffix',
    'ro.boot.dynamic_partitions', 'ro.boot.super_partition', 'ro.build.ab_update',
    'ro.virtual_ab.enabled', 'ro.boot.prjname', 'ro.boot.hw_version', 'ro.boot.dtb_idx', 'ro.boot.dtbo_idx',
    'sys.boot_completed',
)
PULL_PATHS = (
    '/vendor/etc/vintf', '/system/etc/vintf', '/odm/etc/vintf',
    '/product/etc/vintf', '/system_ext/etc/vintf',
    '/vendor/etc/fstab.qcom', '/proc/config.gz',
)
COMMANDS = {
    'kernel-release': ['uname', '-r'],
    'partition-links': ['ls', '-l', '/dev/block/by-name'],
    'mounts': ['cat', '/proc/mounts'],
    'memory': ['cat', '/proc/meminfo'],
    'device-tree-model': ['cat', '/sys/firmware/devicetree/base/model'],
    'device-tree-compatible': ['cat', '/sys/firmware/devicetree/base/compatible'],
    'vintf-tool': ['which', 'checkvintf'],
    'module-directories': ['ls', '-l', '/vendor/lib/modules', '/vendor_dlkm/lib/modules'],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', default='adb')
    parser.add_argument('--serial', help='Select the target when multiple devices are attached; never saved.')
    parser.add_argument('--output', required=True, type=pathlib.Path)
    args = parser.parse_args()
    out = args.output.resolve()
    repo = pathlib.Path(__file__).resolve().parents[2]
    if out == repo or repo in out.parents:
        parser.error('Choose an evidence directory outside the public repository.')
    out.mkdir(parents=True, exist_ok=False)
    prefix = [args.adb] + (['-s', args.serial] if args.serial else [])
    def run(argv):
        result = subprocess.run(prefix+argv, capture_output=True, timeout=90)
        return result.returncode, result.stdout, result.stderr
    code, state, err = run(['get-state'])
    if code or state.strip() != b'device':
        sys.exit('ADB target must be online and authorized.')
    code, raw, err = run(['shell', 'getprop'])
    if code: sys.exit('getprop failed')
    all_props = {}
    for line in raw.decode('utf-8', 'replace').splitlines():
        if line.startswith('[') and ']: [' in line:
            key, value = line[1:-1].split(']: [', 1)
            all_props[key] = value
    props = {key: all_props.get(key, '') for key in PROPERTIES}
    if props['ro.product.model'] != 'RMX2072':
        sys.exit('Unexpected model; this collector currently targets RMX2072 only.')
    evidence = dict(schema_version=1, captured_utc=datetime.now(timezone.utc).isoformat(),
                    properties=props, commands={}, pulls=[])
    for name, command in COMMANDS.items():
        code, stdout, stderr = run(['shell']+command)
        text = stdout.decode('utf-8', 'replace').replace('\x00', '\n')
        (out/(name+'.txt')).write_text(text, encoding='utf-8')
        evidence['commands'][name] = dict(returncode=code, stderr=stderr.decode('utf-8', 'replace').strip())
    for remote in PULL_PATHS:
        local = out/'files'/remote.lstrip('/')
        local.parent.mkdir(parents=True, exist_ok=True)
        code, stdout, stderr = run(['pull', remote, str(local)])
        evidence['pulls'].append(dict(remote=remote, returncode=code,
            message=(stdout+stderr).decode('utf-8', 'replace').strip()))
    config = out/'files'/'proc'/'config.gz'
    if config.exists():
        (out/'kernel.config').write_bytes(gzip.decompress(config.read_bytes()))
    files = []
    for path in sorted(out.rglob('*')):
        if path.is_file():
            files.append(dict(path=path.relative_to(out).as_posix(), size_bytes=path.stat().st_size,
                              sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    evidence['files'] = files
    (out/'audit.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(json.dumps(dict(model=props['ro.product.model'], firmware=props['ro.build.display.id'],
        boot_state=props['ro.boot.vbmeta.device_state'], files=len(files),
        failed_pulls=[x['remote'] for x in evidence['pulls'] if x['returncode']], output=str(out)), ensure_ascii=False))


if __name__ == '__main__':
    main()
