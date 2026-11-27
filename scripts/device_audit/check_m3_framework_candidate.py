"""Compare an additive framework HAL candidate with the saved display baseline.

Read-only local inspection. The device runner separately verifies the complete
container before writing and reads the candidate back after writing.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'build'))


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'baseline', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--trial', required=True)
    p.add_argument('--stage', choices=('health', 'power', 'audio', 'heap', 'keymaster', 'render-access', 'thermal-readout', 'wifi-supplicant', 'wifi-rollback', 'wifi-native'), default='health')
    p.add_argument('--accepted-baseline', type=Path, help='Required for wifi-rollback: retained pre-overlay trial with exact vendor/container and ramdisk manifest')
    p.add_argument('--keymaster-build', type=Path, help='Source HAL build report for the keymaster stage')
    a = p.parse_args()
    if not re.fullmatch(r'ufs-host-g3-gsi17-firststage-ufs-\d{2,3}', a.trial):
        p.error('Use the recorded handset trial name')
    old = read(a.baseline/'inputs.json')
    old_files = read(a.baseline/'vendor-inventory.json')
    if old_files['sha256'] != old['usb_build']['vendor_unsigned']:
        raise ValueError('Baseline vendor inventory is from a different trial')
    current = a.workspace/'current'
    boot = read(current/'boot/control.json')
    usb = read(current/'usb-build.json')
    rd = read(current/'ramdisk/ramdisk-provenance.json')
    vendor = read(current/'vendor/vendor.json')
    candidate = read(current/'candidate/candidate.json')
    graphics = read(current/'graphics-candidate.json')
    health = read(current/'health/provenance.json')
    hal_kind = ('wifi' if a.stage == 'wifi-native' else
                'power' if a.stage in ('thermal-readout', 'wifi-supplicant', 'wifi-rollback') else
                'audio' if a.stage in ('heap', 'keymaster', 'render-access') else a.stage)
    extra = read(current/hal_kind/'provenance.json')
    scratch = read(current/'volumes/scratch.json')
    flags = ('single_dsc_test', 'solid_fill_test', 'panel_readback_test',
             'stock_linkclock_test', 'stock_dsc_test', 'stock_phy_test',
             'first_frame_trace', 'standard_pps_test')
    changed = sorted(n for n in old_files['files']
                     if vendor['files'].get(n) != old_files['files'][n])
    added = sorted(set(vendor['files'])-set(old_files['files']))
    same = lambda left, right, keys: all(left[k] == right[k] for k in keys)
    checks = {
        'correct_trial': rd['trial_id'] == usb['trial'] == graphics['trial'] == a.trial,
        'clean_recipe': usb['recipe_dirty'] is False,
        'same_display_flags': same(boot, old['boot'], flags) and same(usb, old['usb_build'], flags),
        'standard_pps_retained': boot['standard_pps_test'] is True,
        'same_boot_components': same(boot, old['boot'], (
            'dtbo_sha256', 'source_boot_sha256',
            'source_dtbo_sha256', 'dtb_bundle_sha256', 'first_stage_init_sha256',
            'boot_start_policy', 'host_start_required_after_every_reboot', 'cmdline')),
        'same_dt_outputs': boot['device_tree_build']['outputs'] == old['boot']['device_tree_build']['outputs'],
        'same_graphics_guard_and_keys': same(usb, old['usb_build'], (
            'guard', 'witness', 'graphics_source_commit', 'engineering_key',
            'adb_public_key_sha256', 'source_first_stage', 'display', 'display_staged')),
        'same_native_pattern': same(rd, old['ramdisk'], (
            'display_probe_sha256', 'pattern_rgb_sha256', 'busybox_sha256',
            'reboot_helper_sha256', 'entry_carrier_sha256', 'witness_sha256')),
        'bounded_cmdline': len(boot['cmdline'].encode()) <= 512,
        'scratch_framework_start': boot['scratch_framework_start'] is True,
        'boot_digest': sha(current/'boot/boot-diag.img') == boot['boot_sha256'],
        'dtbo_digest': sha(current/'boot/dtbo-diag.img') == boot['dtbo_sha256'],
        'kernel_digest': sha(current/'kernel/Image') == boot['kernel_sha256'] == usb['kernel'],
        'ramdisk_digest': sha(current/'ramdisk/ramdisk.cpio.gz') == boot['ramdisk_sha256'] == rd['gzip_sha256'],
        'vendor_digest': sha(current/'vendor-signed.img') == usb['vendor_signed'] == candidate['signed']['vendor']['sha256'],
        'same_gsi_content': candidate['signed']['system'] == old['candidate']['signed']['system'],
        'same_vendor_key': candidate['signed']['vendor']['key_sha256'] == old['candidate']['signed']['vendor']['key_sha256'],
        'same_original_container': candidate['source_sha256'] == old['candidate']['source_sha256'],
        'same_active_other_partitions': {k:v for k,v in candidate['partitions_after'][0].items() if k != 'vendor'} == {k:v for k,v in old['candidate']['partitions_after'][0].items() if k != 'vendor'},
        'same_inactive_nonalias_partitions': {k:v for k,v in candidate['partitions_after'][1].items() if k != 'system'} == {k:v for k,v in old['candidate']['partitions_after'][1].items() if k != 'system'},
        'health_source_verified': health.get('kind') == 'health' and health.get('source_verified') is True and health.get('archive_digest_verified') is True,
        'health_is_composed': graphics['graphics_source'].get('health') == health,
        'no_unrelated_vendor_change': set(changed) <= ({'/etc/ueventd.rc'} if a.stage == 'render-access' else
            {'/build.prop'} if a.stage == 'heap' else
            {'/bin/hw/rmx-keymaster-info-service', '/bin/hw/rmx-keymaster-info-client',
             '/etc/init/keymaster.rc', '/etc/ueventd.rc', '/etc/selinux/vendor_sepolicy.cil', '/etc/selinux/vendor_file_contexts'}
            if a.stage == 'keymaster' else {'/etc/selinux/vendor_sepolicy.cil', '/etc/selinux/vendor_file_contexts'}),
        'only_selected_hal_files_added': set(added) == ({'/overlay/RmxWifiOverlay.apk'} if a.stage == 'wifi-supplicant' else
            set() if a.stage in ('heap', 'keymaster', 'render-access', 'thermal-readout', 'wifi-rollback') else set(extra['files'])-set(old_files['files'])),
        'no_vendor_files_removed': set(old_files['files']) <= set(vendor['files']),
        'scratch_profile_consistent': scratch == rd['scratch_volumes'] == graphics['scratch'],
        'same_metadata_seed': scratch['metadata'] == old['scratch']['metadata'],
    }
    if a.stage == 'health':
        checks['bounded_data_expansion'] = (old['scratch']['data']['bytes'] == 512 << 20
            and scratch['data']['bytes'] == 2048 << 20
            and scratch['data']['uuid'] == old['scratch']['data']['uuid'])
    else:
        checks.update({
            'same_data_seed': scratch['data'] == old['scratch']['data'],
            hal_kind+'_source_verified': (extra.get('kind') == hal_kind and extra.get('source_verified') is True
                                        and extra.get('archive_digest_verified') is True),
            hal_kind+'_is_composed': graphics['graphics_source'].get(hal_kind) == extra})
        if a.stage not in ('heap', 'keymaster', 'render-access', 'thermal-readout', 'wifi-supplicant', 'wifi-rollback', 'wifi-native'):
            checks[a.stage+'_service_added'] = '/bin/hw/android.hardware.'+a.stage+'-service.rmx2072' in added
    if a.stage == 'wifi-native':
        from stage_m3_graphics import compose
        from stage_m3_wifi_vendor import CONFIG_FILES
        from stage_m3_wifi_firmware import ramdisk_manifest, verify_ramdisk_firmware
        files, source = compose(current/'info-input', current/'rmx-m1-guard',
                                current/'graphics', wifi_vendor=current/'wifi')
        actual = {n: hashlib.sha256(data).hexdigest() for n, data in files.items()}
        firmware = rd.get('wifi_firmware')
        manifest = ramdisk_manifest(current/'ramdisk/ramdisk.cpio.gz')
        verify_ramdisk_firmware(manifest, firmware)
        before = read(a.baseline/'ramdisk-manifest.json')
        allowed_rd = {'trial-id', 'vendor.verity-root'}
        checks.update(
            only_selected_hal_files_added=set(added) == (set(extra['files']) | set(CONFIG_FILES))-set(old_files['files']),
            exact_composed_vendor=actual == vendor['files'],
            exact_source_provenance=source == graphics['graphics_source'],
            no_mainline_rro='/overlay/RmxWifiOverlay.apk' not in files and not source.get('wifi_android'),
            source_supplicant_added='/bin/hw/wpa_supplicant' in added,
            same_wifi_firmware=firmware == old['ramdisk'].get('wifi_firmware') == usb.get('wifi_firmware'),
            baseline_manifest_digest=before['gzip_sha256'] == old['ramdisk']['gzip_sha256'],
            only_vendor_root_and_trial_change_in_ramdisk=(set(before['entries']) == set(manifest)
                and {n for n in manifest if manifest[n] != before['entries'][n]} <= allowed_rd),
            same_input_battery_gpu_and_radio=same(usb, old['usb_build'], (
                'input_devices', 'battery_gauge', 'performance', 'panel_refresh', 'wifi')),
            wifi_enabled=usb.get('wifi') is True)
    if a.stage == 'wifi-rollback':
        if not a.accepted_baseline:
            p.error('--accepted-baseline is required for wifi-rollback')
        from stage_m3_wifi_android import APK, overlay_payload
        from stage_m3_wifi_firmware import ramdisk_manifest, verify_ramdisk_firmware
        accepted = read(a.accepted_baseline/'inputs.json')
        accepted_stable = read(a.accepted_baseline/'live/gsi-stable.json')
        accepted_manifest = read(a.accepted_baseline/'ramdisk-manifest.json')
        _, overlay_proof = overlay_payload(current/'wifi-overlay')
        actual_manifest = ramdisk_manifest(current/'ramdisk/ramdisk.cpio.gz')
        firmware = rd.get('wifi_firmware')
        verify_ramdisk_firmware(actual_manifest, firmware)
        before = accepted_manifest['entries']
        checks.pop('no_vendor_files_removed')
        checks.update(
            no_unrelated_vendor_change=changed == [APK] and not added,
            only_reviewed_rro_removed=(set(old_files['files']) - set(vendor['files']) == {APK}
                and old_files['files'][APK] == overlay_proof['apk_sha256']),
            no_overlay_composed=not graphics['graphics_source'].get('wifi_android'),
            accepted_boot_was_retained=accepted_stable.get('guardian') == 'retained' and accepted_stable.get('seconds', 0) >= 190,
            exact_accepted_vendor=(usb['vendor_unsigned'] == accepted['usb_build']['vendor_unsigned']
                and usb['vendor_signed'] == accepted['usb_build']['vendor_signed']),
            exact_accepted_container=candidate['sha256'] == accepted['candidate']['sha256'],
            accepted_manifest_digest=accepted_manifest['gzip_sha256'] == accepted['ramdisk']['gzip_sha256'],
            only_trial_id_differs_from_accepted_ramdisk=(set(before) == set(actual_manifest)
                and [n for n in before if before[n] != actual_manifest[n]] == ['trial-id']),
            same_wifi_firmware=firmware == old['ramdisk'].get('wifi_firmware') == usb.get('wifi_firmware'),
            same_input_battery_gpu_and_radio=same(usb, old['usb_build'], (
                'input_devices', 'battery_gauge', 'performance', 'panel_refresh', 'wifi')))
    if a.stage == 'wifi-supplicant':
        from stage_m3_wifi_android import APK, overlay_payload
        from stage_m3_wifi_firmware import ramdisk_manifest, verify_ramdisk_firmware
        apk, proof = overlay_payload(current/'wifi-overlay')
        # Read the actual ext4 payload, not just its generated inventory.
        installed = subprocess.check_output([str(current/'fs-tools/debugfs.exe'),
            '-R', 'cat '+APK, str(current/'vendor/vendor.img')], stderr=subprocess.DEVNULL)
        firmware = rd.get('wifi_firmware')
        if not firmware:
            raise ValueError('Supplicant trial requires the retained boot firmware')
        verify_ramdisk_firmware(ramdisk_manifest(current/'ramdisk/ramdisk.cpio.gz'), firmware)
        checks.update(
            only_wifi_rro_added=not changed and added == [APK],
            wifi_rro_actual_bytes=installed == apk,
            wifi_rro_inventory_digest=vendor['files'].get(APK) == proof['apk_sha256'],
            wifi_rro_provenance=graphics['graphics_source'].get('wifi_android') == proof,
            same_wifi_firmware=firmware == old['ramdisk'].get('wifi_firmware') == usb.get('wifi_firmware'),
            same_input_battery_gpu_and_radio=same(usb, old['usb_build'], (
                'input_devices', 'battery_gauge', 'performance', 'panel_refresh', 'wifi')),
            wifi_enabled=usb.get('wifi') is True)
    if a.stage == 'thermal-readout':
        before = (a.baseline/'vendor-sepolicy.cil').read_bytes()
        after = subprocess.check_output([str(current/'fs-tools/debugfs.exe'), '-R',
            'cat /etc/selinux/vendor_sepolicy.cil', str(current/'vendor/vendor.img')],
            stderr=subprocess.DEVNULL)
        lines = lambda data: [x.strip() for x in data.splitlines()
                              if x.strip() and not x.lstrip().startswith(b';')]
        expected = {
            b'(genfscon sysfs "/devices/virtual/thermal" (u object_r sysfs_thermal ((s0) (s0))))',
            b'(allow shell sysfs_thermal (dir (getattr search open read)))',
            b'(allow shell sysfs_thermal (lnk_file (getattr read)))',
            b'(allow shell sysfs_thermal (file (getattr open read)))',
        }
        old_lines, new_lines = lines(before), lines(after)
        checks.update(
            baseline_policy_digest=hashlib.sha256(before).hexdigest() == old_files['files']['/etc/selinux/vendor_sepolicy.cil'],
            current_policy_digest=hashlib.sha256(after).hexdigest() == vendor['files']['/etc/selinux/vendor_sepolicy.cil'],
            only_policy_file_changed=changed == ['/etc/selinux/vendor_sepolicy.cil'] and not added,
            exact_readonly_thermal_delta=(not expected.intersection(old_lines)
                and all(new_lines.count(x) == 1 for x in expected)
                and [x for x in new_lines if x not in expected] == old_lines))
    if a.stage != 'keymaster':
        checks['same_kernel'] = boot['kernel_sha256'] == old['boot']['kernel_sha256']
    else:
        if not a.keymaster_build:
            p.error('--keymaster-build is required for the keymaster stage')
        repo = Path(__file__).resolve().parents[2]
        previous_kernel = read(a.baseline/'kernel-inputs/provenance.json')
        new_kernel = read(current/'kernel/provenance.json')
        allowed_sources = {'keymaster-lookup.sha256', 'keymaster-transport.sha256', 'listener.sha256'}
        prev_hashes = previous_kernel['selected_member_sha256']
        new_hashes = new_kernel['selected_member_sha256']
        immutable = {k for k in prev_hashes if k.endswith('.sha256')} - allowed_sources
        immutable.update(('sm8250_bootstrap_dot_config', 'resolved-manifest.xml'))
        source_root = 'device/realme/bladerunner_48m/'
        changed_sources = set(subprocess.check_output(['git', '-C', str(repo), 'diff', '--name-only',
            previous_kernel['source_commit'], new_kernel['source_commit'], '--',
            source_root+'bootstrap-probes', source_root+'bootstrap-patches', source_root+'display',
            '.github/workflows/sm8250-bootstrap.yml', 'scripts/kernel_research/build_sm8250_bootstrap.sh'],
            text=True).splitlines())
        allowed_paths = {source_root+'bootstrap-probes/'+name for name in (
            'rmx2072-keymaster-lookup.c', 'rmx2072-keymaster-transport.h', 'rmx2072-listener.inc')}
        km = read(a.keymaster_build)
        pins = read(repo/source_root/'m1-keymaster-info/inputs.json')
        expected_sources = {
            'service': {'m1-keymaster-info/service.cpp', 'm1-keymaster-info/wire.h',
                        'm1-keymaster-info/operations.h', 'm1-keymaster-info/selftest.h', 'bootstrap-probes/rmx2072-keymaster-transport.h'},
            'client': {'m1-keymaster-info/client.cpp', 'm1-keymaster-info/selftest.h', 'm1-keymaster-info/wire.h'}}
        source_ok = True
        for kind, sources in expected_sources.items():
            name = 'rmx-keymaster-info-'+kind
            report = km[name]
            source_ok &= (set(report['source_files']) == sources and
                all(sha(repo/source_root/path) == digest for path,digest in report['source_files'].items()) and
                sha(current/'info-input'/name) == report['sha256'] == pins['/bin/hw/'+name] == vendor['files']['/bin/hw/'+name] and
                report['runpath'] == ['/vendor/lib64/rmx-keymaster'] and
                {Path(path).name for path in pins if path.startswith('/lib64/')} <= set(report['needed']))
        checks.update(
            baseline_kernel_record_matches=previous_kernel['image_sha256'] == old['boot']['kernel_sha256'],
            kernel_inputs_verified=(new_kernel['source_digests_verified'] is True and
                new_kernel['dist_digests_verified'] is True and new_kernel['installing'] is False and
                new_kernel['image_sha256'] == boot['kernel_sha256']),
            kernel_has_only_keymaster_source_change=changed_sources == allowed_paths,
            same_display_and_non_keymaster_kernel_inputs=all(prev_hashes[k] == new_hashes.get(k) for k in immutable),
            keymaster_binary_and_source_verified=bool(source_ok),
            same_audio_source=extra == read(a.baseline/'audio-provenance.json'))
    if a.stage == 'render-access':
        before = (a.baseline/'vendor-ueventd.rc').read_bytes()
        after = subprocess.check_output([str(current/'fs-tools/debugfs.exe'), '-R', 'cat /etc/ueventd.rc',
                                        str(current/'vendor/vendor.img')], stderr=subprocess.DEVNULL)
        old_rule = b'/dev/dri/renderD* 0660 system graphics\n'
        new_rule = b'/dev/dri/renderD* 0666 system graphics\n'
        checks.update(
            baseline_ueventd_digest=hashlib.sha256(before).hexdigest() == old_files['files']['/etc/ueventd.rc'],
            current_ueventd_digest=hashlib.sha256(after).hexdigest() == vendor['files']['/etc/ueventd.rc'],
            only_render_node_dac_changed=(before.count(old_rule) == 1 and after == before.replace(old_rule,new_rule)),
            primary_node_restricted=b'/dev/dri/card* 0660 system graphics\n' in after,
            same_audio_source=extra == read(a.baseline/'audio-provenance.json'))
    if a.stage == 'heap':
        before = (a.baseline/'vendor-build.prop').read_bytes()
        after = subprocess.check_output([str(current/'fs-tools/debugfs.exe'), '-R', 'cat /build.prop',
                                         str(current/'vendor/vendor.img')], stderr=subprocess.DEVNULL)
        def properties(data):
            result = {}
            for row in data.decode().splitlines():
                row = row.strip()
                if not row or row.startswith('#'):
                    continue
                key, value = row.split('=', 1)
                if key in result:
                    raise ValueError('Duplicate vendor property: '+key)
                result[key] = value
            return result
        pinned = read(Path(__file__).resolve().parents[2]/'build/m3-dalvik-heap-source.json')['properties']
        prior_props, new_props = properties(before), properties(after)
        checks.update(
            baseline_property_digest=hashlib.sha256(before).hexdigest() == old_files['files']['/build.prop'],
            current_property_digest=hashlib.sha256(after).hexdigest() == vendor['files']['/build.prop'],
            previously_missing_heap_properties=not (set(prior_props) & set(pinned)),
            only_pinned_heap_properties_added=new_props == dict(prior_props, **pinned),
            same_audio_source=extra == read(a.baseline/'audio-provenance.json'))
    report = dict(trial=a.trial, baseline=old['trial'], recipe_commit=usb['recipe_commit'],
                  checks=checks, passed=all(checks.values()),
                  boot_sha256=boot['boot_sha256'], kernel_sha256=boot['kernel_sha256'],
                  vendor_sha256=usb['vendor_signed'], super_sha256=candidate['sha256'],
                  health_build=health['run_id'], health_source_commit=health['source_commit'],
                  stage=a.stage, selected_hal_build=extra['run_id'],
                  selected_hal_source_commit=extra['source_commit'],
                  vendor_files_changed=changed, vendor_files_added=added,
                  vendor_files_removed=sorted(set(old_files['files'])-set(vendor['files'])),
                  metadata_and_extents_unchanged=(candidate['prefix_sha256'] == old['candidate']['prefix_sha256'] and candidate['targets'] == old['candidate']['targets']),
                  headroom_bytes=candidate['headroom'],
                  scope='Local input comparison only; no handset or desktop acceptance implied')
    if a.stage == 'keymaster':
        report.update(selected_hal_build=None,
            selected_hal_source_commit=usb['recipe_commit'],
            keymaster_build_report_sha256=sha(a.keymaster_build),
            kernel_source_commit=new_kernel['source_commit'], kernel_build=new_kernel['run_id'],
            retained_audio_build=extra['run_id'])
    a.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(passed=report['passed'], checks=len(checks),
                          failed=[k for k,v in checks.items() if not v])))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
