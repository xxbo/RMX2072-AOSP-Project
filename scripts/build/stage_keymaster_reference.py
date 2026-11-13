"""Stage the F.20 comparison HAL beside the source-built M1 vendor files."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEVICE = ROOT / 'device/realme/bladerunner_48m'
SERVICE = '/bin/hw/android.hardware.keymaster@4.0-service-qti'


def inventory():
    base = DEVICE / 'm1-vendor'
    ref = DEVICE / 'm1-keymaster-reference'
    files = {'/' + f.relative_to(base).as_posix(): f.read_bytes().replace(b'\r\n', b'\n')
             for f in base.rglob('*') if f.is_file()}
    files['/etc/vintf/manifest.xml'] = (ref / 'manifest.xml').read_bytes().replace(b'\r\n', b'\n')
    files['/etc/init/keymaster.rc'] = (ref / 'keymaster.rc').read_bytes().replace(b'\r\n', b'\n')
    files['/etc/selinux/vendor_sepolicy.cil'] += (ref / 'keymaster.cil').read_bytes().replace(b'\r\n', b'\n')
    files['/etc/selinux/vendor_file_contexts'] += (
        b'/vendor/bin/hw/android\\.hardware\\.keymaster@4\\.0-service-qti u:object_r:rmx_keymaster_exec:s0\n')
    blobs = json.loads((ref / 'f20-files.json').read_text())
    return files, blobs


def stage(reference, output):
    if ROOT == output.resolve() or ROOT in output.resolve().parents:
        raise ValueError('The extracted F.20 files belong in a private output directory')
    files, blobs = inventory()
    for path, digest in blobs.items():
        data = (reference / Path(path).name).read_bytes()
        if data[:6] != b'\x7fELF\x02\x01' or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Wrong F.20 ELF for ' + path)
        files[path] = data
    output.mkdir(parents=True, exist_ok=False)
    for path, data in files.items():
        dest = output / path.lstrip('/')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    stage(args.reference, args.output)
