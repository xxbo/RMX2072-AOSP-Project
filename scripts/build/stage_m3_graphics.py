"""Compose the source graphics payload with the accepted Keymaster/USB vendor.

No binary is borrowed from a stock Android graphics stack. Existing Keymaster
runtime libraries are placed in their own directory rather than overwritten by
Android 17 graphics dependencies. Build a new signed candidate only after this
inventory and the combined split policy pass validation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
from stage_keymaster_reference import inventory

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'device/realme/bladerunner_48m/m3-vendor'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def filesystem_size(files):
    # Room for directory/xattr metadata and growth, rounded to 4 MiB. Keep the
    # graphics payload bounded well below the verified super free-space budget.
    payload = sum(map(len, files.values()))
    size = max(16 << 20, ((payload * 5 // 4 + (8 << 20) + (4 << 20) - 1) // (4 << 20)) * (4 << 20))
    if size > 256 << 20:
        raise ValueError('Graphics vendor exceeds the bounded 256 MiB profile')
    return size


def compose(info, guard, graphics):
    files, pinned = inventory(True, guard)
    for path, digest in pinned.items():
        data = (info/Path(path).name).read_bytes()
        if sha(data) != digest:
            raise ValueError('Accepted Keymaster input changed: '+path)
        target = path.replace('/lib64/', '/lib64/rmx-keymaster/')
        files[target] = data
    rc = files['/etc/init/keymaster.rc']
    if rc.count(b'    class early_hal\n') != 1:
        raise ValueError('Keymaster service definition changed')
    files['/etc/init/keymaster.rc'] = rc.replace(b'    class early_hal\n',
        b'    class early_hal\n    setenv LD_LIBRARY_PATH /vendor/lib64/rmx-keymaster\n')
    build = json.loads((graphics/'provenance.json').read_text())
    if not build.get('source_verified') or not build.get('archive_digest_verified'):
        raise ValueError('Source graphics artifact is not fully verified')
    payload = graphics/'vendor'
    incoming = {}
    for path in payload.rglob('*'):
        if path.is_symlink():
            raise ValueError('Resolve and validate build output symlinks before staging')
        if not path.is_file():
            continue
        name = '/'+path.relative_to(payload).as_posix()
        if not re.fullmatch(r'/[a-zA-Z0-9+@/_.-]+', name):
            raise ValueError('Unexpected graphics filename: '+name)
        if not name.startswith(('/lib64/', '/bin/hw/', '/etc/init/', '/etc/vintf/')):
            raise ValueError('Unexpected graphics partition input: '+name)
        data = path.read_bytes()
        if name in files:
            raise ValueError('Graphics payload overlaps existing vendor content: '+name)
        if name.startswith(('/lib64/', '/bin/hw/')) and (data[:6] != b'\x7fELF\x02\x01'
                or len(data) < 64 or struct.unpack_from('<H', data, 18)[0] != 183):
            raise ValueError('Expected a real ARM64 graphics ELF: '+name)
        incoming[name] = sha(data)
        files[name] = data
    if incoming != build['files']:
        raise ValueError('Graphics inventory differs from verified artifact')
    files['/build.prop'] += b'\n'+(SOURCE/'vendor.prop').read_bytes().replace(b'\r\n', b'\n')
    files['/etc/selinux/vendor_sepolicy.cil'] += (SOURCE/'graphics.cil').read_bytes().replace(b'\r\n', b'\n')
    files['/etc/selinux/vendor_property_contexts'] += (
        b'vendor.minigbm.debug u:object_r:rmx_graphics_config_prop:s0 exact string\n')
    labels = [
        '/vendor/bin/hw/android\\.hardware\\.graphics\\.allocator-service\\.minigbm u:object_r:rmx_graphics_allocator_exec:s0',
        '/vendor/bin/hw/android\\.hardware\\.composer\\.hwc3-service\\.rmx2072 u:object_r:rmx_graphics_composer_exec:s0',
    ]
    for path in sorted(incoming):
        if path.startswith('/lib64/'):
            labels.append(re.escape('/vendor'+path)+' u:object_r:same_process_hal_file:s0')
    files['/etc/selinux/vendor_file_contexts'] += ('\n'.join(labels)+'\n').encode()
    files['/etc/ueventd.rc'] += (b'/dev/dri/card* 0660 system graphics\n'
                                b'/dev/dri/renderD* 0660 system graphics\n'
                                b'/dev/dma_heap/system 0666 system graphics\n')
    return files, build


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('info', 'guard', 'graphics', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    output = a.output.resolve()
    if output.is_relative_to(ROOT) or output.exists():
        p.error('Use a new staging directory outside the public checkout')
    files, build = compose(a.info, a.guard, a.graphics)
    for name,data in files.items():
        path = output/name.lstrip('/')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    print(json.dumps(dict(files=len(files), payload_bytes=sum(map(len,files.values())),
                          graphics_build=build['source_commit'])))


if __name__ == '__main__':
    main()
