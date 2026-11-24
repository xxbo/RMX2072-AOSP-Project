"""Check performance candidate scope against the accepted display/input trial."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'build'))
from check_m3_display import check_m3_display
from stage_m3_acceleration import gpu_firmware


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'baseline', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--trial', required=True)
    a = p.parse_args()
    c = a.workspace/'current'
    old = read(a.baseline/'inputs.json')
    ov = read(a.baseline/'vendor-inventory.json')
    vendor = read(c/'vendor/vendor.json')
    usb = read(c/'usb-build.json')
    boot = read(c/'boot/control.json')
    candidate = read(c/'candidate/candidate.json')
    kernel = read(c/'kernel/provenance.json')
    rd = read(c/'ramdisk/ramdisk-provenance.json')
    graphics = read(c/'graphics-candidate.json')
    turnip = read(c/'turnip/provenance.json')
    firmware, fp = gpu_firmware(c/'gpu-firmware')
    flags = ('single_dsc_test', 'solid_fill_test', 'panel_readback_test',
             'stock_linkclock_test', 'stock_dsc_test', 'stock_phy_test',
             'first_frame_trace', 'standard_pps_test')
    changed = sorted(n for n in ov['files'] if vendor['files'].get(n) != ov['files'][n])
    added = sorted(set(vendor['files'])-set(ov['files']))
    expected_additions = {'/lib64/hw/vulkan.freedreno.so', *('/firmware/'+n for n in firmware)}
    checks = dict(
        correct_trial=a.trial == usb['trial'] == rd['trial_id'] == graphics['trial'],
        clean_recipe=usb['recipe_dirty'] is False,
        accepted_display_flags=all(boot[k] == old['boot'][k] for k in flags) and boot['standard_pps_test'],
        accepted_input_and_gauge=all(usb.get(k) is True for k in ('input_devices', 'battery_gauge')),
        source_init_unchanged=boot['first_stage_init_sha256'] == old['boot']['first_stage_init_sha256'],
        same_boot_policy=boot['boot_start_policy'] == old['boot']['boot_start_policy'],
        same_guard_and_keys=all(usb[k] == old['usb_build'][k] for k in
            ('guard', 'witness', 'engineering_key', 'adb_public_key_sha256', 'graphics_source_commit')),
        same_gsi=candidate['signed']['system'] == old['candidate']['signed']['system'],
        same_original=candidate['source_sha256'] == old['candidate']['source_sha256'],
        same_test_volumes=read(c/'volumes/scratch.json') == old['scratch'] == rd['scratch_volumes'],
        performance_enabled=kernel.get('performance') and boot.get('performance') and usb.get('performance'),
        panel_90=boot.get('panel_refresh') == 90,
        kernel_verified=kernel['source_digests_verified'] and kernel['dist_digests_verified'] and not kernel['installing'],
        same_kernel=sha(c/'kernel/Image') == kernel['image_sha256'] == boot['kernel_sha256'],
        boot_digest=sha(c/'boot/boot-diag.img') == boot['boot_sha256'],
        dtbo_digest=sha(c/'boot/dtbo-diag.img') == boot['dtbo_sha256'],
        vendor_digest=sha(c/'vendor-signed.img') == candidate['signed']['vendor']['sha256'] == usb['vendor_signed'],
        turnip_verified=turnip['source_verified'] and turnip['archive_digest_verified'] and
            all(vendor['files'][n] == h for n, h in turnip['files'].items()),
        firmware_verified=all(vendor['files']['/firmware/'+n] == fp['files'][n]['sha256'] for n in firmware),
        vendor_change_scope=set(changed) == {'/build.prop', '/etc/selinux/vendor_file_contexts', '/etc/selinux/vendor_sepolicy.cil'},
        vendor_addition_scope=set(added) == expected_additions,
        no_removed_files=set(ov['files']) <= set(vendor['files']),
        strict_policy=graphics['policy_proof_reused_for_identical_statements'] and
            vendor['files']['/etc/selinux/vendor_sepolicy.cil'] == graphics['composed_vendor_cil_sha256'],
    )
    resources = check_m3_display((c/'source-dt/effective.dtb').read_bytes(), True, True, True, True)
    report = dict(trial=a.trial, checks=checks, passed=all(checks.values()),
        changed=changed, added=added, resources=resources, device_result='NOT RUN')
    a.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(passed=report['passed'], failed=[k for k, v in checks.items() if not v])))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
