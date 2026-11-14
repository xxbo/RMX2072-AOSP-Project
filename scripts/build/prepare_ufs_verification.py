"""Prepare Android first-stage verification inputs from two signed UFS images."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/device_audit'))
from check_verity import verified_vbmeta


def image_profile(path, name, key_digest):
    with path.open('rb') as image:
        size = image.seek(0, 2)
        image.seek(-64, 2)
        magic, version, _, original, offset, length = struct.unpack('>4sIIQQQ', image.read(36))
        if magic != b'AVBf' or version != 1 or not (0 < original <= offset < size - 64):
            raise ValueError(f'{name}: invalid AVB footer')
        if length > min(1024 * 1024, size - 64 - offset):
            raise ValueError(f'{name}: invalid vbmeta size')
        image.seek(offset)
        _, key, _, descriptors = verified_vbmeta(image.read(length))
        if hashlib.sha256(key).hexdigest() != key_digest or set(descriptors) != {name}:
            raise ValueError(f'{name}: unexpected signing key or hashtree partition name')
        tree = descriptors[name]
        if (tree['image_bytes'] != original or tree['tree_offset'] < original or
                tree['tree_offset'] + tree['tree_bytes'] > offset or tree['algorithm'] != 'sha256'):
            raise ValueError(f'{name}: invalid hashtree bounds or algorithm')
        image.seek(0)
        full = hashlib.file_digest(image, 'sha256').hexdigest()
    return key, dict(sha256=full, key_sha256=key_digest, bytes=size, tree=tree)


def prepare(system, vendor, vendor_key, output, vendor_report=None, keymaster_reference=False, keymaster_info=False, usb_guard=None):
    reference = json.loads((ROOT/'build/device/gsi17-mount-reference.json').read_text())
    inputs = [('system', system, reference['key_sha256']),
              ('vendor', vendor, hashlib.sha256(vendor_key.read_bytes()).hexdigest())]
    records, keys = {}, {}
    for name, path, key_digest in inputs:
        keys[name], records[name] = image_profile(path, name, key_digest)
    if records['system']['sha256'] != reference['image_sha256'] or records['system']['tree'] != reference['hashtree']:
        raise ValueError('GSI differs from the pinned image')
    payload_bytes = records['vendor']['tree']['image_bytes']
    if payload_bytes != (16 if keymaster_reference or keymaster_info else 2) * 1024 * 1024:
        raise ValueError('Unexpected project vendor filesystem size')
    with vendor.open('rb') as image:
        payload = hashlib.sha256(image.read(payload_bytes)).hexdigest()
    if vendor_report:
        report = json.loads(vendor_report.read_text())
        source = ROOT/'device/realme/bladerunner_48m/m1-vendor'
        files = {'/'+p.relative_to(source).as_posix():
                 hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                 for p in source.rglob('*') if p.is_file()}
        if keymaster_reference or keymaster_info:
            from stage_keymaster_reference import inventory
            project, blobs = inventory(keymaster_info, usb_guard)
            files = {path: hashlib.sha256(data).hexdigest() for path, data in project.items()} | blobs
        if files != report['files']:
            raise ValueError('Vendor report differs from the project sources')
        expected = report['sha256']
    else:
        control = json.loads((ROOT/'build/device/gsi17-enforcing-second-stage-2026-11-12.json').read_text())
        expected = control['trials'][-1]['vendor_image_sha256']
    if payload != expected:
        raise ValueError('Signed vendor filesystem differs from the specified build')
    if output.exists() and any(p.name not in {'system.avbpubkey','vendor.avbpubkey','signed.json'} or not p.is_file() for p in output.iterdir()):
        raise ValueError('Refuse to replace an unrecognized verification directory')
    output.mkdir(parents=True, exist_ok=True)
    for name, key in keys.items():
        (output/(name+'.avbpubkey')).write_bytes(key)
    (output/'signed.json').write_text(json.dumps(records, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('system', 'vendor', 'vendor-key', 'output'):
        parser.add_argument('--'+option, required=True, type=Path)
    parser.add_argument('--vendor-report', type=Path, help='CI vendor.json for the current project sources')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--keymaster-reference', action='store_true', help='Check the pinned private F.20 comparison inventory')
    group.add_argument('--keymaster-info', action='store_true', help='Check source-built info HAL and AOSP VNDK hashes')
    parser.add_argument('--usb-guard', type=Path)
    args = parser.parse_args()
    if args.usb_guard and not args.keymaster_info: parser.error('--usb-guard requires --keymaster-info')
    if (args.keymaster_reference or args.keymaster_info) and not args.vendor_report:
        parser.error('A Keymaster profile requires its image report')
    prepare(args.system, args.vendor, args.vendor_key, args.output, args.vendor_report,
            args.keymaster_reference, args.keymaster_info, args.usb_guard)
