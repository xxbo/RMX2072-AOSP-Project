#!/usr/bin/env python3
"""Build a deterministic RAM-only diagnostic initramfs from verified static BusyBox."""
import argparse
import gzip
import hashlib
import io
import json
import pathlib
import re
import struct
from super_tools import read_tools


def read_static_arm64(path):
    binary = path.read_bytes()
    if len(binary) < 64 or binary[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', binary, 18)[0] != 183:
        raise ValueError(f'{path.name}: expected an AArch64 ELF64 binary')
    off = struct.unpack_from('<Q', binary, 32)[0]
    width, count = struct.unpack_from('<HH', binary, 54)
    if width < 56 or count == 0 or off + width * count > len(binary):
        raise ValueError(f'{path.name}: invalid ELF program headers')
    if any(struct.unpack_from('<I', binary, off+i*width)[0] == 3 for i in range(count)):
        raise ValueError(f'{path.name}: diagnostic binaries must have no dynamic interpreter')
    return binary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--busybox', required=True, type=pathlib.Path)
    p.add_argument('--output', required=True, type=pathlib.Path)
    p.add_argument('--reboot-helper', type=pathlib.Path)
    p.add_argument('--entry-carrier', type=pathlib.Path)
    p.add_argument('--ufs-reset-info', type=pathlib.Path,
                   help='Static ARM64 read-only TLMM line-info tool')
    p.add_argument('--ufs-phy-cycle', action='store_true',
                   help='Include the staged SM8250 UFS PHY diagnostic shell commands')
    p.add_argument('--ufs-host-test', action='store_true',
                   help='Include the staged UFS host and read-only LUN diagnostic')
    p.add_argument('--ufs-host-g3-test', action='store_true',
                   help='Include the staged host commands and HS-G3 read, wake and GPT controls')
    p.add_argument('--super-tools-apks', type=pathlib.Path,
                   help='Verified APK cache for the read-only dynamic partition diagnostic')
    p.add_argument('--f20-verity', action='store_true',
                   help='Include the signed F.20 hashtree reference and read-only mount trial')
    p.add_argument('--gsi-usb-reader', type=pathlib.Path,
                   help='Static ARM64 dm-user reader for the read-only Android 17 GSI trial')
    p.add_argument('--trial-id')
    p.add_argument('--android-first-stage', type=pathlib.Path, help='Pinned API 37 generic ramdisk /init')
    p.add_argument('--first-stage-witness', type=pathlib.Path, help='Static ARM64 mount observer')
    p.add_argument('--project-vendor', type=pathlib.Path, help='Directory with CI-built vendor.img and vendor.json')
    p.add_argument('--trace-init-fault', action='store_true', help='Trace PID 1 file faults and failed block completions')
    p.add_argument('--gsi-block-seed', type=pathlib.Path, help='Original GSI blocks and ranges for the RAM-backed comparison')
    p.add_argument('--gsi-init-probe', type=pathlib.Path,
                   help='Include the Android 17 and F.20 combined policy diagnostic')
    p.add_argument('--return-to-edl-after', type=int)
    p.add_argument('--defer-gadget-bind', action='store_true',
                   help='Register UDC but do not start gadget/DMA; isolates post-bind failure')
    p.add_argument('--gadget-bind-delay', type=int,
                   help='Wait 1..120 seconds after UDC discovery before binding')
    p.add_argument('--snapshot-delays', help='Comma-separated 1..60 second snapshot intervals')
    a = p.parse_args()
    if a.project_vendor and not a.android_first_stage:
        p.error('The project vendor requires the Android first-stage profile')
    if a.trace_init_fault and not (a.project_vendor and (a.trial_id or '').startswith('ufs-host-g3-gsi17-firststage-vendor-load-')):
        p.error('Fault tracing requires a policy-install trial')
    if a.gsi_block_seed and not a.trace_init_fault:
        p.error('The seed comparison requires the same fault tracing as the USB control')
    if bool(a.android_first_stage) != bool(a.first_stage_witness) or (a.android_first_stage and
            not (a.gsi_usb_reader and a.return_to_edl_after and (a.trial_id or '').startswith('ufs-host-g3-gsi17-firststage-'))):
        p.error('First-stage requires the init, observer, GSI reader, recovery timer and firststage trial ID')
    if a.gsi_init_probe and not (a.gsi_usb_reader and a.f20_verity):
        p.error('--gsi-init-probe requires --gsi-usb-reader and --f20-verity')
    if a.super_tools_apks and not a.ufs_host_g3_test:
        p.error('--super-tools-apks requires --ufs-host-g3-test')
    if a.f20_verity and not a.super_tools_apks:
        p.error('--f20-verity requires --super-tools-apks')
    if a.gsi_usb_reader and not a.super_tools_apks:
        p.error('--gsi-usb-reader requires the verified dmsetup runtime from --super-tools-apks')
    if a.trial_id and not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', a.trial_id):
        p.error('Invalid trial ID')
    if a.return_to_edl_after is not None and (
            not a.reboot_helper or not 45 <= a.return_to_edl_after <= 900):
        p.error('A 45..900 second control return requires a static reboot helper')
    if a.gadget_bind_delay is not None and (
            a.defer_gadget_bind or not 1 <= a.gadget_bind_delay <= 120 or
            (a.return_to_edl_after and a.gadget_bind_delay >= a.return_to_edl_after)):
        p.error('Bind delay must be 1..120 seconds, before return, and cannot be deferred')
    delays = None
    if a.snapshot_delays:
        try:
            delays = [int(value) for value in a.snapshot_delays.split(',')]
        except ValueError:
            p.error('Snapshot intervals must be integers')
        if not 1 <= len(delays) <= 8 or any(not 1 <= d <= 60 for d in delays) or sum(delays) > 180:
            p.error('Snapshot intervals must be 1..60 seconds, at most 8, total <=180')
    root = pathlib.Path(__file__).resolve().parents[2]
    if root == a.output.resolve() or root in a.output.resolve().parents:
        p.error('Generated boot material must remain outside checkout')
    lock = json.loads((root/'build/diagnostic-tools.json').read_text())
    binary = read_static_arm64(a.busybox)
    actual = hashlib.sha256(binary).hexdigest()
    if actual != lock['busybox_sha256']:
        raise ValueError('BusyBox hash mismatch')
    archive, inode = bytearray(), 0
    def add(name, mode, content=b'', major=0, minor=0):
        nonlocal inode
        inode += 1
        encoded = name.encode()+b'\0'
        fields = [inode, mode, 0, 0, 1, 0, len(content), 0, 0, major, minor, len(encoded), 0]
        archive.extend(b'070701'+''.join(f'{v:08x}' for v in fields).encode()+encoded)
        archive.extend(b'\0'*(-len(archive)%4))
        archive.extend(content)
        archive.extend(b'\0'*(-len(archive)%4))
    for name in ['bin', 'sbin', 'dev', 'proc', 'sys', 'run', 'tmp']:
        add(name, 0o40755)
    add('dev/console', 0o20600, major=5, minor=1)
    add('dev/null', 0o20666, major=1, minor=3)
    add('dev/kmsg', 0o20600, major=1, minor=11)
    add('bin/busybox', 0o100755, binary)
    helper_hash = None
    carrier_hash = None
    if a.entry_carrier:
        carrier = read_static_arm64(a.entry_carrier)
        add('bin/entry-carry', 0o100755, carrier)
        carrier_hash = hashlib.sha256(carrier).hexdigest()
    if a.ufs_reset_info:
        line_info = read_static_arm64(a.ufs_reset_info)
        add('bin/ufs-reset-info', 0o100755, line_info)
    if a.ufs_phy_cycle:
        cycle = (root/'scripts/device_audit/ufs_phy_cycle.sh').read_bytes().replace(b'\r\n', b'\n')
        add('bin/ufs-phy-cycle', 0o100755, cycle)
    if a.ufs_host_test or a.ufs_host_g3_test:
        host = (root/'scripts/device_audit/ufs_host_trial.sh').read_bytes().replace(b'\r\n', b'\n')
        add('bin/ufs-host-test', 0o100755, host)
    if a.ufs_host_g3_test:
        g3 = (root/'scripts/device_audit/ufs_g3_test.sh').read_bytes().replace(b'\r\n', b'\n')
        add('bin/ufs-g3-test', 0o100755, g3)
    if a.super_tools_apks:
        binaries = read_tools(a.super_tools_apks)
        add('bin/lp', 0o40755)
        for name, elf in sorted(binaries.items()):
            add('bin/lp/'+name, 0o100755, elf)
        super_test = (root/'scripts/device_audit/super_readonly.sh').read_bytes().replace(b'\r\n', b'\n')
        add('bin/super-readonly', 0o100755, super_test)
    if a.gsi_usb_reader:
        reader = read_static_arm64(a.gsi_usb_reader)
        if a.android_first_stage:
            first = read_static_arm64(a.android_first_stage)
            first_hash = hashlib.sha256(first).hexdigest()
            source = json.loads((root/'build/device/android17-first-stage-source.json').read_text())
            if first_hash != source['init_sha256']:
                raise ValueError('Unexpected API 37 first-stage init')
            add('android-first-stage', 0o100755, first)
            witness = read_static_arm64(a.first_stage_witness)
            add('bin/first-stage-witness', 0o100755, witness)
            stage_script = (root/'scripts/device_audit/first_stage_mount.sh').read_bytes().replace(b'\r\n', b'\n')
            add('bin/first-stage-mount', 0o100755, stage_script)
            if a.trace_init_fault:
                add('m1-trace-fault', 0o100444, b'1\n')
            if a.project_vendor:
                info = json.loads((a.project_vendor/'vendor.json').read_text())
                vendor = (a.project_vendor/'vendor.img').read_bytes()
                vendor_hash = hashlib.sha256(vendor).hexdigest()
                source_dir = root/'device/realme/bladerunner_48m/m1-vendor'
                files = {('/'+path.relative_to(source_dir).as_posix()):
                         hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                         for path in source_dir.rglob('*') if path.is_file()}
                if len(vendor) != 2*1024*1024 or vendor_hash != info['sha256'] or files != info['files']:
                    raise ValueError('Vendor image or source inventory differs from build report')
                add('project-vendor.img', 0o100444, vendor)
                add('project-vendor.sha256', 0o100444, (vendor_hash+'\n').encode())
                add('project-vendor.fstab', 0o100444, (source_dir/'etc/fstab.qcom').read_bytes().replace(b'\r\n', b'\n'))
        add('bin/gsi-usb-reader', 0o100755, reader)
        script = (root/'scripts/device_audit/gsi17_mount.sh').read_bytes().replace(b'\r\n', b'\n')
        add('bin/gsi17-mount', 0o100755, script)
        ref = json.loads((root/'build/device/gsi17-mount-reference.json').read_text())
        if a.gsi_block_seed:
            info = json.loads((a.gsi_block_seed/'seed.json').read_text())
            blob = (a.gsi_block_seed/'blocks.bin').read_bytes()
            ranges = (a.gsi_block_seed/'ranges.txt').read_bytes()
            spans = [tuple(map(int, row.split())) for row in ranges.splitlines()]
            end = total = 0
            for offset,length in spans:
                if offset < end or length <= 0 or (offset+length)*4096 > ref['image_bytes']:
                    raise ValueError('Invalid GSI block ranges')
                end = offset+length
                total += length
            if (info['gsi_sha256'] != ref['image_sha256'] or info['block_size'] != 4096 or
                total != info['blocks'] or len(blob) != total*4096 or not total or
                hashlib.sha256(blob).hexdigest() != info['blocks_sha256'] or
                hashlib.sha256(ranges).hexdigest() != info['ranges_sha256']):
                raise ValueError('GSI seed identity mismatch')
            add('gsi-seed.blocks', 0o100444, blob)
            add('gsi-seed.ranges', 0o100444, ranges)
        t = ref['hashtree']
        args = [ref['image_bytes'], t['image_bytes'], t['data_block_bytes'],
                t['tree_offset']//t['hash_block_bytes'], t['root_digest'], t['salt']]
        add('gsi17-table', 0o100444, (' '.join(map(str, args))+'\n').encode())
        add('gsi17-files', 0o100444, ''.join(f"{v['sha256']} {p}\n" for p,v in ref['files'].items()).encode())
    if a.f20_verity:
        ref = json.loads((root/'build/device/f20-verity-reference.json').read_text())
        add('verity-profile', 0o40755)
        hashes = ''.join(f'{name} {digest}\n' for name,digest in ref['gpt_vbmeta_sha256'].items())
        add('verity-profile/vbmeta-hashes', 0o100444, hashes.encode())
        if a.gsi_init_probe:
            launcher = read_static_arm64(a.gsi_init_probe)
            add('bin/gsi-init-probe', 0o100755, launcher)
            probe = (root/'scripts/device_audit/gsi17_policy.sh').read_bytes().replace(b'\r\n', b'\n')
            add('bin/gsi17-policy', 0o100755, probe)
            odm = json.loads((root/'build/device/f20-odm-verity-reference.json').read_text())
            ref['partitions']['odm'] = odm
            fields = [odm['logical_bytes'], odm['footer_block_sha256'], odm['vbmeta_block'],
                      odm['vbmeta_block_sha256'], odm['key_sha256']]
            add('verity-profile/odm-source', 0o100444, (' '.join(map(str, fields))+'\n').encode())
            lp = json.loads((root/'build/device/super-readonly-2026-11-10.json').read_text())
            add('verity-profile/lp-prefix', 0o100444, (lp['prefix_sha256']+'\n').encode())
        for name, part in ref['partitions'].items():
            tree = part['descriptor']
            fields = [tree['image_bytes']//512, tree['data_block_bytes'], tree['hash_block_bytes'],
                      tree['image_bytes']//tree['data_block_bytes'], tree['tree_offset']//tree['hash_block_bytes'],
                      tree['algorithm'], tree['root_digest'], tree['salt'], tree['fec_offset']//tree['data_block_bytes'],
                      tree['fec_roots'], part['filesystem'], part['verified_data_sha256']]
            add('verity-profile/'+name, 0o100444, (' '.join(map(str, fields))+'\n').encode())
            files = ''.join(f'{digest} {path}\n' for path,digest in part['files'].items())
            add('verity-profile/'+name+'.files', 0o100444, files.encode())
        verity_test = (root/'scripts/device_audit/verity_readonly.sh').read_bytes().replace(b'\r\n', b'\n')
        add('bin/verity-readonly', 0o100755, verity_test)
    if a.trial_id:
        add('trial-id', 0o100600, (a.trial_id+'\n').encode())
    if a.defer_gadget_bind:
        add('defer-gadget-bind', 0o100600, b'1\n')
    if a.gadget_bind_delay is not None:
        add('gadget-bind-delay', 0o100600, (str(a.gadget_bind_delay)+'\n').encode())
    if delays:
        add('snapshot-delays', 0o100600, (' '.join(map(str, delays))+'\n').encode())
    if a.reboot_helper:
        helper = read_static_arm64(a.reboot_helper)
        add('bin/reboot-edl', 0o100755, helper)
        helper_hash = hashlib.sha256(helper).hexdigest()
    if a.return_to_edl_after is not None:
        add('control-return-seconds', 0o100600, (str(a.return_to_edl_after)+'\n').encode())
    init = root/'device/realme/bladerunner_48m/bootstrap/diag-init.sh'
    supervisor = root/'device/realme/bladerunner_48m/bootstrap/diag-supervisor.sh'
    snapshot = root/'device/realme/bladerunner_48m/bootstrap/diag-snapshot.sh'
    add('init', 0o100755, supervisor.read_bytes().replace(b'\r\n', b'\n'))
    add('diag-init.sh', 0o100755, init.read_bytes().replace(b'\r\n', b'\n'))
    add('diag-snapshot.sh', 0o100755, snapshot.read_bytes().replace(b'\r\n', b'\n'))
    add('TRAILER!!!', 0)
    data = io.BytesIO()
    with gzip.GzipFile(fileobj=data, mode='wb', mtime=0, filename='') as stream:
        stream.write(archive)
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output/'ramdisk.cpio').write_bytes(archive)
    (a.output/'ramdisk.cpio.gz').write_bytes(data.getvalue())
    report = dict(busybox_sha256=actual, reboot_helper_sha256=helper_hash,
                  entry_carrier_sha256=carrier_hash, trial_id=a.trial_id,
                  control_return_seconds=a.return_to_edl_after,
                  defer_gadget_bind=a.defer_gadget_bind,
                  gadget_bind_delay_seconds=a.gadget_bind_delay,
                  snapshot_intervals_seconds=delays or [2, 13, 30, 30],
                  init_sha256=hashlib.sha256(init.read_bytes()).hexdigest(),
                  supervisor_sha256=hashlib.sha256(supervisor.read_bytes()).hexdigest(),
                  snapshot_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                  cpio_sha256=hashlib.sha256(archive).hexdigest(),
                  gzip_sha256=hashlib.sha256(data.getvalue()).hexdigest(),
                  scope='USB serial shell in RAM; no block mounts or handset writes')
    if a.ufs_reset_info:
        report['ufs_reset_info_sha256'] = hashlib.sha256(line_info).hexdigest()
    if a.ufs_phy_cycle:
        report['ufs_phy_cycle_sha256'] = hashlib.sha256(cycle).hexdigest()
    if a.ufs_host_test or a.ufs_host_g3_test:
        report['ufs_host_test_sha256'] = hashlib.sha256(host).hexdigest()
    if a.ufs_host_g3_test:
        report['ufs_g3_test_sha256'] = hashlib.sha256(g3).hexdigest()
    if a.super_tools_apks:
        report['super_tools_files'] = len(binaries)
        report['super_test_sha256'] = hashlib.sha256(super_test).hexdigest()
    if a.f20_verity:
        report['verity_test_sha256'] = hashlib.sha256(verity_test).hexdigest()
    if a.gsi_usb_reader:
        report['gsi_reader_sha256'] = hashlib.sha256(reader).hexdigest()
        report['gsi_mount_script_sha256'] = hashlib.sha256(script).hexdigest()
    if a.gsi_init_probe:
        report.update(scope='Verified read-only Android 17 and F.20 mounts with RAM-only SELinux probes',
                      init_launcher_sha256=hashlib.sha256(launcher).hexdigest(),
                      policy_probe_sha256=hashlib.sha256(probe).hexdigest())
    if a.android_first_stage:
        report.update(scope='Android API 37 first-stage init as global PID 1 with read-only USB-backed GSI',
                      first_stage_init_sha256=first_hash, witness_sha256=hashlib.sha256(witness).hexdigest())
    if a.project_vendor:
        report['project_vendor_sha256'] = vendor_hash
    if a.gsi_block_seed:
        report['gsi_seed_sha256'] = info['blocks_sha256']
        report['gsi_seed_ranges_sha256'] = info['ranges_sha256']
    (a.output/'ramdisk-provenance.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
