"""Stage the F.20 comparison HAL beside the source-built M1 vendor files."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEVICE = ROOT / 'device/realme/bladerunner_48m'


def inventory(info=False, usb_guard=None):
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
    blobs.update(json.loads((ref / 'f20-vndk30.json').read_text()))
    if info:
        src = DEVICE / 'm1-keymaster-info'
        files['/etc/init/keymaster.rc'] = (src / 'keymaster.rc').read_bytes().replace(b'\r\n', b'\n')
        files['/etc/selinux/vendor_sepolicy.cil'] += (src / 'version.cil').read_bytes().replace(b'\r\n', b'\n')
        files['/etc/selinux/vendor_file_contexts'] = (
            (base / 'etc/selinux/vendor_file_contexts').read_bytes().replace(b'\r\n', b'\n') +
            b'/vendor/bin/hw/rmx-keymaster-info-service u:object_r:rmx_keymaster_exec:s0\n')
        blobs = json.loads((src / 'inputs.json').read_text())
    if usb_guard:
        from build_diag_ramdisk import read_static_arm64
        usb = DEVICE / 'm1-usb'
        files['/bin/hw/rmx-m1-guard'] = read_static_arm64(usb_guard)
        files['/bin/hw/rmx-m1-control'] = files['/bin/hw/rmx-m1-guard']
        files['/etc/init/rmx-m1-usb.rc'] = (usb/'usb.rc').read_bytes().replace(b'\r\n', b'\n')
        files['/etc/selinux/vendor_sepolicy.cil'] += (usb/'guard.cil').read_bytes().replace(b'\r\n', b'\n')
        files['/etc/selinux/vendor_file_contexts'] += b'/vendor/bin/hw/rmx-m1-guard u:object_r:rmx_m1_guard_exec:s0\n/vendor/bin/hw/rmx-m1-control u:object_r:vendor_shell_exec:s0\n/dev/socket/rmx_m1_guard u:object_r:rmx_m1_guard_socket:s0\n'
        files['/etc/selinux/vendor_property_contexts'] = b'vendor.rmx.m1. u:object_r:rmx_m1_control_prop:s0 prefix string\n'
        files['/etc/ueventd.rc'] += b'/dev/watchdog 0600 root root\n'
    return files, blobs


def stage(reference, output, info=False, usb_guard=None):
    if ROOT == output.resolve() or ROOT in output.resolve().parents:
        raise ValueError('The extracted F.20 files belong in a private output directory')
    files, blobs = inventory(info, usb_guard)
    for path, digest in blobs.items():
        data = (reference / Path(path).name).read_bytes()
        if data[:6] != b'\x7fELF\x02\x01' or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Wrong pinned ELF for ' + path)
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
