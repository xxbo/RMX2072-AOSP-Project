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
    p.add_argument('--stage', choices=('health', 'power', 'audio', 'heap'), default='health')
    a = p.parse_args()
    if not re.fullmatch(r'ufs-host-g3-gsi17-firststage-ufs-\d{2}', a.trial):
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
    hal_kind = 'audio' if a.stage == 'heap' else a.stage
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
        'same_kernel_and_boot_components': same(boot, old['boot'], (
            'kernel_sha256', 'dtbo_sha256', 'source_boot_sha256',
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
        'no_graphics_or_existing_hal_replacement': set(changed) <= ({'/build.prop'} if a.stage == 'heap' else {'/etc/selinux/vendor_sepolicy.cil', '/etc/selinux/vendor_file_contexts'}),
        'only_selected_hal_files_added': set(added) == (set() if a.stage == 'heap' else set(extra['files'])-set(old_files['files'])),
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
        if a.stage != 'heap':
            checks[a.stage+'_service_added'] = '/bin/hw/android.hardware.'+a.stage+'-service.rmx2072' in added
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
                  metadata_and_extents_unchanged=(candidate['prefix_sha256'] == old['candidate']['prefix_sha256'] and candidate['targets'] == old['candidate']['targets']),
                  headroom_bytes=candidate['headroom'],
                  scope='Local input comparison only; no handset or desktop acceptance implied')
    a.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(passed=report['passed'], checks=len(checks),
                          failed=[k for k,v in checks.items() if not v])))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
