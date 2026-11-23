"""Check the input candidate against the accepted display/render inputs.

Local provenance and scope checks only; real touch and physical keys need
target getevent, InputReader and operator-visible UI evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'build'))
from check_m3_display import check_m3_display
from check_m3_input import check_m3_input


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def config(path):
    return dict(line.split('=', 1) for line in path.read_text().splitlines()
                if line.startswith('CONFIG_') and '=' in line)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'baseline', 'baseline-config', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--trial', required=True)
    a = p.parse_args()
    current = a.workspace / 'current'
    old = read(a.baseline / 'inputs.json')
    old_vendor = read(a.baseline / 'vendor-inventory.json')
    usb = read(current / 'usb-build.json')
    boot = read(current / 'boot/control.json')
    rd = read(current / 'ramdisk/ramdisk-provenance.json')
    kernel = read(current / 'kernel/provenance.json')
    vendor = read(current / 'vendor/vendor.json')
    candidate = read(current / 'candidate/candidate.json')
    graphics = read(current / 'graphics-candidate.json')
    overlay = read(current / 'input-overlay/provenance.json')
    dt = (current / 'source-dt/effective.dtb').read_bytes()
    resources = dict(input=check_m3_input(dt, True),
                     display=check_m3_display(dt, True, True))
    before, after = config(a.baseline_config), config(current / 'kernel/sm8250_bootstrap_dot_config')
    delta = {k: [before.get(k), after.get(k)] for k in before.keys() | after.keys()
             if before.get(k) != after.get(k)}
    prior_digests = old['kernel']['selected_member_sha256']
    immutable = {k for k in prior_digests if k.endswith('.sha256')} | {'resolved-manifest.xml'}
    flags = ('single_dsc_test', 'solid_fill_test', 'panel_readback_test',
             'stock_linkclock_test', 'stock_dsc_test', 'stock_phy_test',
             'first_frame_trace', 'standard_pps_test')
    same = lambda left, right, keys: all(left[k] == right[k] for k in keys)
    changed = sorted(k for k in old_vendor['files'] if vendor['files'].get(k) != old_vendor['files'][k])
    added = sorted(set(vendor['files']) - set(old_vendor['files']))
    checks = dict(
        correct_trial=a.trial == usb['trial'] == rd['trial_id'] == graphics['trial'],
        clean_recipe=usb['recipe_dirty'] is False,
        input_requested=usb['input_devices'] is True and kernel['input_devices'] is True,
        baseline_inventory=old_vendor['sha256'] == old['usb_build']['vendor_unsigned'],
        same_display_flags=same(boot, old['boot'], flags) and same(usb, old['usb_build'], flags),
        same_boot_policy=same(boot, old['boot'], ('first_stage_init_sha256', 'cmdline',
            'boot_start_policy', 'host_start_required_after_every_reboot', 'source_boot_sha256')),
        same_guard_and_keys=same(usb, old['usb_build'], ('guard', 'witness',
            'graphics_source_commit', 'engineering_key', 'adb_public_key_sha256',
            'source_first_stage', 'display', 'display_staged')),
        same_native_pattern=same(rd, old['ramdisk'], ('display_probe_sha256', 'pattern_rgb_sha256',
            'busybox_sha256', 'reboot_helper_sha256', 'entry_carrier_sha256', 'witness_sha256')),
        kernel_checked=kernel['source_digests_verified'] and kernel['dist_digests_verified']
            and kernel['installing'] is False,
        existing_kernel_sources_unchanged=all(prior_digests[k] == kernel['selected_member_sha256'].get(k)
                                              for k in immutable),
        only_touch_config_added=delta == {'CONFIG_TOUCHSCREEN_GOODIX_GTX8': [None, 'y']},
        boot_digest=sha(current / 'boot/boot-diag.img') == boot['boot_sha256'],
        dtbo_digest=sha(current / 'boot/dtbo-diag.img') == boot['dtbo_sha256'],
        kernel_digest=sha(current / 'kernel/Image') == boot['kernel_sha256'] == usb['kernel'] == kernel['image_sha256'],
        ramdisk_digest=sha(current / 'ramdisk/ramdisk.cpio.gz') == boot['ramdisk_sha256'] == rd['gzip_sha256'],
        effective_dt_digest=hashlib.sha256(dt).hexdigest() == boot['device_tree_build']['outputs']['effective.dtb']['sha256'],
        vendor_digest=sha(current / 'vendor-signed.img') == usb['vendor_signed'] == candidate['signed']['vendor']['sha256'],
        same_gsi=candidate['signed']['system'] == old['candidate']['signed']['system'],
        same_vendor_key=candidate['signed']['vendor']['key_sha256'] == old['candidate']['signed']['vendor']['key_sha256'],
        same_original=candidate['source_sha256'] == old['candidate']['source_sha256'],
        same_volumes=read(current / 'volumes/scratch.json') == old['scratch'] == rd['scratch_volumes'] == graphics['scratch'],
        same_layout=candidate['prefix_sha256'] == old['candidate']['prefix_sha256'] and candidate['targets'] == old['candidate']['targets'],
        only_input_vendor_changes=set(changed) == {'/etc/init/rmx-m1-usb.rc', '/etc/selinux/vendor_file_contexts'},
        only_input_vendor_additions=set(added) == {'/overlay/RmxCpuInputOverlay.apk', '/usr/idc/Goodix_GTX8_Capacitive_TouchScreen.idc'},
        no_removed_files=set(old_vendor['files']) <= set(vendor['files']),
        overlay_matches=sha(current / 'input-overlay/RmxCpuInputOverlay.apk') == overlay['apk_sha256']
            == vendor['files']['/overlay/RmxCpuInputOverlay.apk'],
        same_strict_policy=graphics['policy_proof_reused_for_identical_statements'] is True
            and vendor['files']['/etc/selinux/vendor_sepolicy.cil'] == old_vendor['files']['/etc/selinux/vendor_sepolicy.cil'],
    )
    report = dict(trial=a.trial, baseline=old['trial'], recipe_commit=usb['recipe_commit'],
                  kernel_run=kernel['run_id'], kernel_source=kernel['source_commit'], checks=checks,
                  passed=all(checks.values()), config_delta=delta, resources=resources,
                  vendor_changed=changed, vendor_added=added, boot_sha256=boot['boot_sha256'],
                  super_sha256=candidate['sha256'], device_result='NOT RUN')
    a.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'], checks=len(checks),
                         failed=[k for k, v in checks.items() if not v], config_delta=delta)))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
