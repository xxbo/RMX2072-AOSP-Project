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


def merge_native_hal_payload(files, directory, kind):
    """Admit a checked additive native HAL; never replace graphics libraries."""
    build = json.loads((directory/'provenance.json').read_text())
    if kind not in ('health', 'power', 'audio'):
        raise ValueError('Unrecognized additive HAL')
    if (build.get('kind') != kind or not build.get('source_verified')
            or not build.get('archive_digest_verified')):
        raise ValueError(kind+' source artifact is not verified')
    incoming = {}
    payload = directory/'vendor'
    for path in payload.rglob('*'):
        if path.is_symlink():
            raise ValueError('Unexpected '+kind+' symlink')
        if not path.is_file():
            continue
        name = '/'+path.relative_to(payload).as_posix()
        if (not re.fullmatch(r'/[a-zA-Z0-9+@/_.-]+', name)
                or not name.startswith(('/lib64/', '/bin/hw/', '/etc/init/', '/etc/vintf/'))):
            raise ValueError('Unexpected '+kind+' input: '+name)
        data = path.read_bytes()
        if name.startswith(('/lib64/', '/bin/hw/')) and (data[:6] != b'\x7fELF\x02\x01'
                or len(data) < 64 or struct.unpack_from('<H', data, 18)[0] != 183):
            raise ValueError('Expected ARM64 '+kind+' ELF: '+name)
        if name in files and files[name] != data:
            raise ValueError(kind+' would replace a different existing vendor file: '+name)
        incoming[name] = data
    if {name:sha(data) for name,data in incoming.items()} != build['files']:
        raise ValueError(kind+' inventory differs from verified artifact')
    service = {'health': 'android.hardware.health-service.example',
               'power': 'android.hardware.power-service.rmx2072',
               'audio': 'android.hardware.audio-service.rmx2072'}[kind]
    if '/bin/hw/'+service not in incoming:
        raise ValueError(kind+' service missing')
    files.update(incoming)
    # This engineering profile does not enable a charger-mode UI or charging
    # policy. Keep only the normal Health service reading power_supply.
    if kind == 'health':
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
    for kind in ('health', 'power', 'audio'):
        hal_dir = graphics.parent/kind
        if hal_dir.exists():
            hal, hal_files = merge_native_hal_payload(files, hal_dir, kind)
            build = dict(build, **{kind: hal})
            incoming.update({name:sha(data) for name,data in hal_files.items()})
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
    # SystemServer starts WifiService only for this board feature. Without it,
    # the GSI SetupWizard network page dereferences a null WifiManager. This
    # starts the framework path; it does not supply a radio driver or Wi-Fi HAL.
    files['/etc/permissions/android.hardware.wifi.xml'] = (
        SOURCE/'android.hardware.wifi.xml').read_bytes().replace(b'\r\n', b'\n')
    # Launcher3 calls AppWidgetManager while loading its workspace. SystemServer
    # needs this software feature to register the existing GSI AppWidgetService.
    files['/etc/permissions/android.software.app_widgets.xml'] = (
        SOURCE/'android.software.app_widgets.xml').read_bytes().replace(b'\r\n', b'\n')
    files['/etc/init/rmx-m3-capture.rc'] = (SOURCE/'framecapture.rc').read_bytes().replace(b'\r\n', b'\n')
    from m3_boot_pattern import archive_bytes
    files['/etc/rmx-m3-oem/media/bootanimation.zip'] = archive_bytes()
    files['/etc/init/rmx-m3-bootpattern.rc'] = (SOURCE/'bootpattern.rc').read_bytes().replace(b'\r\n', b'\n')
    files['/etc/selinux/vendor_sepolicy.cil'] += (SOURCE/'graphics.cil').read_bytes().replace(b'\r\n', b'\n')
    files['/etc/selinux/vendor_sepolicy.cil'] += (SOURCE/'health.cil').read_bytes().replace(b'\r\n', b'\n')
    files['/etc/selinux/vendor_sepolicy.cil'] += (SOURCE/'power.cil').read_bytes().replace(b'\r\n', b'\n')
    files['/etc/selinux/vendor_sepolicy.cil'] += (SOURCE/'audio.cil').read_bytes().replace(b'\r\n', b'\n')
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
        '/vendor/bin/hw/android\\.hardware\\.power-service\\.rmx2072 u:object_r:rmx_power_exec:s0',
        '/vendor/bin/hw/android\\.hardware\\.audio-service\\.rmx2072 u:object_r:rmx_audio_exec:s0',
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
    # In-process mappers also run as application UIDs, outside graphics GID.
    # Render nodes expose rendering/import operations, not DRM master/modeset.
    # Keep primary nodes restricted and retain gpu_device SELinux enforcement.
    files['/etc/ueventd.rc'] += (b'/dev/dri/card* 0660 system graphics\n'
                                b'/dev/dri/renderD* 0666 system graphics\n'
                                b'/dev/dma_heap/system 0666 system graphics\n')
    overlay = graphics.parent/'input-overlay'
    if (overlay/'provenance.json').is_file():
        proof = json.loads((overlay/'provenance.json').read_text())
        source = ROOT/'device/realme/bladerunner_48m/input'
        actual = {x.relative_to(source/'overlay').as_posix(): sha(x.read_bytes())
                  for x in (source/'overlay').rglob('*') if x.is_file()}
        apk = (overlay/'RmxCpuInputOverlay.apk').read_bytes()
        if actual != proof['source_sha256'] or sha(apk) != proof['apk_sha256']:
            raise ValueError('Rebuild the changed source input overlay')
        files['/overlay/RmxCpuInputOverlay.apk'] = apk
        files['/usr/idc/Goodix_GTX8_Capacitive_TouchScreen.idc'] = (
            source/'Goodix_GTX8_Capacitive_TouchScreen.idc').read_bytes().replace(b'\r\n', b'\n')
        # Match the pinned GSI's platform file contexts. InputReader cannot
        # read vendor_file under enforcing; its IDC files use vendor_idc_file.
        files['/etc/selinux/vendor_file_contexts'] += (
            b'/vendor/overlay(/.*)? u:object_r:vendor_overlay_file:s0\n'
            b'/vendor/usr/idc(/.*)? u:object_r:vendor_idc_file:s0\n')
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
