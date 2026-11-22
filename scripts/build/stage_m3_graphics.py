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


def merge_health_payload(files, directory):
    """Admit a checked additive native HAL; never replace graphics libraries."""
    build = json.loads((directory/'provenance.json').read_text())
    if (build.get('kind') != 'health' or not build.get('source_verified')
            or not build.get('archive_digest_verified')):
        raise ValueError('Health source artifact is not verified')
    incoming = {}
    payload = directory/'vendor'
    for path in payload.rglob('*'):
        if path.is_symlink():
            raise ValueError('Unexpected Health symlink')
        if not path.is_file():
            continue
        name = '/'+path.relative_to(payload).as_posix()
        if (not re.fullmatch(r'/[a-zA-Z0-9+@/_.-]+', name)
                or not name.startswith(('/lib64/', '/bin/hw/', '/etc/init/', '/etc/vintf/'))):
            raise ValueError('Unexpected Health input: '+name)
        data = path.read_bytes()
        if name.startswith(('/lib64/', '/bin/hw/')) and (data[:6] != b'\x7fELF\x02\x01'
                or len(data) < 64 or struct.unpack_from('<H', data, 18)[0] != 183):
            raise ValueError('Expected ARM64 Health ELF: '+name)
        if name in files and files[name] != data:
            raise ValueError('Health would replace a different existing vendor file: '+name)
        incoming[name] = data
    if {name:sha(data) for name,data in incoming.items()} != build['files']:
        raise ValueError('Health inventory differs from verified artifact')
    if '/bin/hw/android.hardware.health-service.example' not in incoming:
        raise ValueError('Health service missing')
    files.update(incoming)
    # This engineering profile does not enable a charger-mode UI or charging
    # policy. Keep only the normal Health service reading power_supply.
    files['/etc/init/android.hardware.health-service.example.rc'] = (
        SOURCE/'health.rc').read_bytes().replace(b'\r\n', b'\n')
    return build, incoming


def compose(info, guard, graphics):
    files, pinned = inventory(True, guard)
    for path, digest in pinned.items():
        data = (info/Path(path).name).read_bytes()
        if sha(data) != digest:
            raise ValueError('Accepted Keymaster input changed: '+path)
        target = path.replace('/lib64/', '/lib64/rmx-keymaster/')
        files[target] = data
    # The source HAL/client carry a RUNPATH and the full private DT_NEEDED
    # closure. Do not depend on an environment path discarded by AT_SECURE.
    for name in ('service', 'client'):
        if b'/vendor/lib64/rmx-keymaster\0' not in files['/bin/hw/rmx-keymaster-info-' + name]:
            raise ValueError('Rebuild the source Keymaster binaries with the private runtime path')
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
    health_dir = graphics.parent/'health'
    if health_dir.exists():
        health, health_files = merge_health_payload(files, health_dir)
        build = dict(build, health=health)
        incoming.update({name:sha(data) for name,data in health_files.items()})
    probe_dir = graphics.parent/'display-smoke'
    probe_build = json.loads((probe_dir/'build.json').read_text())
    probe_source = (ROOT/'scripts/device_audit/drm_scanout_state.c').read_bytes().replace(b'\r\n', b'\n')
    probe = (probe_dir/'drm-scanout-state').read_bytes()
    if (sha(probe_source) != probe_build['scanout_source_sha256']
            or sha(probe) != probe_build['scanout_binary_sha256']
            or probe[:6] != b'\x7fELF\x02\x01' or len(probe) < 64
            or struct.unpack_from('<H', probe, 18)[0] != 183):
        raise ValueError('Rebuild the read-only ARM64 scanout probe from current source')
    files['/bin/hw/rmx-m3-drm-state'] = probe
    files['/build.prop'] += b'\n'+(SOURCE/'vendor.prop').read_bytes().replace(b'\r\n', b'\n')
    files['/etc/init/rmx-m3-capture.rc'] = (SOURCE/'framecapture.rc').read_bytes().replace(b'\r\n', b'\n')
    from m3_boot_pattern import archive_bytes
    files['/etc/rmx-m3-oem/media/bootanimation.zip'] = archive_bytes()
    files['/etc/init/rmx-m3-bootpattern.rc'] = (SOURCE/'bootpattern.rc').read_bytes().replace(b'\r\n', b'\n')
    files['/etc/selinux/vendor_sepolicy.cil'] += (SOURCE/'graphics.cil').read_bytes().replace(b'\r\n', b'\n')
    files['/etc/selinux/vendor_sepolicy.cil'] += (SOURCE/'health.cil').read_bytes().replace(b'\r\n', b'\n')
    files['/etc/selinux/vendor_property_contexts'] += (
        b'vendor.minigbm.debug u:object_r:rmx_graphics_config_prop:s0 exact string\n')
    # Stable-C mapper discovery uses servicemanager's isDeclared permission
    # check even though the mapper itself is an in-process native library.
    files['/etc/selinux/vendor_service_contexts'] = (
        b'mapper/minigbm u:object_r:hal_graphics_mapper_service:s0\n')
    labels = [
        '/data/vendor/rmx-m3-diag(/.*)? u:object_r:rmx_scanout_data_file:s0',
        '/vendor/bin/hw/rmx-m3-drm-state u:object_r:rmx_scanout_probe_exec:s0',
        '/vendor/bin/hw/android\\.hardware\\.health-service\\.example u:object_r:rmx_health_exec:s0',
        '/dev/dri/card[0-9]+ u:object_r:gpu_device:s0',
        '/dev/dri/renderD[0-9]+ u:object_r:gpu_device:s0',
        '/vendor/etc/selinux/vendor_service_contexts u:object_r:vendor_service_contexts_file:s0',
        '/vendor/etc/rmx-m3-oem(/media)? u:object_r:oemfs:s0',
        '/vendor/etc/rmx-m3-oem/media/bootanimation\\.zip u:object_r:bootanim_oem_file:s0',
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
