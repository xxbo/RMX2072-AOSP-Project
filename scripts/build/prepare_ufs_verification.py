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


def prepare(system, vendor, vendor_key, output, vendor_report=None, keymaster_reference=False):
    reference = json.loads((ROOT/'build/device/gsi17-mount-reference.json').read_text())
    inputs = [('system', system, reference['key_sha256']),
              ('vendor', vendor, hashlib.sha256(vendor_key.read_bytes()).hexdigest())]
    records, keys = {}, {}
    for name, path, key_digest in inputs:
        keys[name], records[name] = image_profile(path, name, key_digest)
    if records['system']['sha256'] != reference['image_sha256'] or records['system']['tree'] != reference['hashtree']:
        raise ValueError('GSI differs from the pinned image')
    payload_bytes = records['vendor']['tree']['image_bytes']
    if payload_bytes != 2 * 1024 * 1024:
        raise ValueError('Unexpected project vendor filesystem size')
    with vendor.open('rb') as image:
        payload = hashlib.sha256(image.read(payload_bytes)).hexdigest()
    if vendor_report:
        report = json.loads(vendor_report.read_text())
        source = ROOT/'device/realme/bladerunner_48m/m1-vendor'
        files = {'/'+p.relative_to(source).as_posix():
                 hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                 for p in source.rglob('*') if p.is_file()}
        if keymaster_reference:
            from stage_keymaster_reference import inventory
            project, blobs = inventory()
            files = {path: hashlib.sha256(data).hexdigest() for path, data in project.items()} | blobs
        if files != report['files']:
            raise ValueError('Vendor report differs from the project sources')
        expected = report['sha256']
    else:
        control = json.loads((ROOT/'build/device/gsi17-enforcing-second-stage-2026-11-12.json').read_text())
        expected = control['trials'][-1]['vendor_image_sha256']
    if payload != expected:
        raise ValueError('Signed vendor filesystem differs from the specified build')
    output.mkdir(parents=True, exist_ok=False)
    for name, key in keys.items():
        (output/(name+'.avbpubkey')).write_bytes(key)
    (output/'signed.json').write_text(json.dumps(records, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('system', 'vendor', 'vendor-key', 'output'):
        parser.add_argument('--'+option, required=True, type=Path)
    parser.add_argument('--vendor-report', type=Path, help='CI vendor.json for the current project sources')
    parser.add_argument('--keymaster-reference', action='store_true', help='Check the pinned private F.20 comparison inventory')
    args = parser.parse_args()
    if args.keymaster_reference and not args.vendor_report:
        parser.error('The reference comparison requires its image report')
    prepare(args.system, args.vendor, args.vendor_key, args.output, args.vendor_report, args.keymaster_reference)
