"""Check the boot-only WLAN candidate against the retained GPU/90 Hz trial."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'build'))
from check_m3_display import check_m3_display
from check_m3_wifi import check_m3_wifi


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def config(text):
    return dict(line.split('=', 1) for line in text.splitlines() if line.startswith('CONFIG_'))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'baseline', 'baseline-config', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--trial', required=True)
    p.add_argument('--wifi-firmware', type=Path, help='Require an additive firmware-only ramdisk delta against the baseline manifest')
    p.add_argument('--wifi-board-file', type=Path, help='Require only the exact F.20 board ELF addition to a boot-firmware baseline')
    p.add_argument('--wifi-disabled-against', type=Path,
                   help='Isolation: retain this trial kernel but use the baseline non-WLAN DT')
    a = p.parse_args()
    if a.wifi_board_file and not a.wifi_firmware:
        p.error('--wifi-board-file requires --wifi-firmware')
    c = a.workspace / 'current'
    old = read(a.baseline / 'inputs.json')
    kernel, boot, usb, rd, source = [read(c / n) for n in (
        'kernel/provenance.json', 'boot/control.json', 'usb-build.json',
        'ramdisk/ramdisk-provenance.json', 'source-dt/source.json')]
    before = config(a.baseline_config.read_text())
    after = config((c / 'kernel/sm8250_bootstrap_dot_config').read_text())
    previous_members = old['kernel']['selected_member_sha256']
    unchanged_sources = [n for n in previous_members if n.endswith('.sha256')]
    flags = ('single_dsc_test', 'solid_fill_test', 'panel_readback_test',
             'stock_linkclock_test', 'stock_dsc_test', 'stock_phy_test',
             'first_frame_trace', 'standard_pps_test', 'panel_refresh')
    checks = dict(
        correct_trial=usb['trial'] == rd['trial_id'] == a.trial,
        clean_recipe=usb['recipe_dirty'] is False and source['project_dirty'] is False,
        wifi_profile=(kernel.get('wifi') is True and all(
            x.get('wifi') is (a.wifi_disabled_against is None) for x in (boot, usb, source))),
        accepted_features=all(usb.get(k) is True and kernel.get(k) is True for k in
            ('display', 'input_devices', 'battery_gauge', 'performance')),
        same_display_flags=all(boot[k] == old['boot'][k] for k in flags),
        same_cmdline=boot['cmdline'] == old['boot']['cmdline'],
        same_boot_policy=boot['boot_start_policy'] == old['boot']['boot_start_policy'],
        same_source_init=boot['first_stage_init_sha256'] == old['boot']['first_stage_init_sha256'],
        same_guard_and_keys=all(usb[k] == old['usb_build'][k] for k in
            ('guard', 'witness', 'engineering_key', 'adb_public_key_sha256', 'graphics_source_commit')),
        same_super=read(c / 'candidate/candidate.json') == old['candidate'],
        same_vendor=sha(c / 'vendor-signed.img') == old['usb_build']['vendor_signed'] == usb['vendor_signed'],
        same_test_volumes=read(c / 'volumes/scratch.json') == rd['scratch_volumes'] == old['scratch'],
        same_gpu_firmware=rd['gpu_firmware'] == old['ramdisk']['gpu_firmware'],
        same_nonwifi_kernel_sources=bool(unchanged_sources) and all(
            kernel['selected_member_sha256'].get(n) == previous_members[n] for n in unchanged_sources),
        baseline_config_verified=sha(a.baseline_config) == previous_members['sm8250_bootstrap_dot_config'],
        no_existing_builtin_removed=all(after.get(k) == 'y' for k, v in before.items() if v == 'y'),
        kernel_verified=kernel['source_digests_verified'] and kernel['dist_digests_verified']
            and not kernel['installing'],
        kernel_digest=sha(c / 'kernel/Image') == kernel['image_sha256'] == boot['kernel_sha256'],
        boot_digest=sha(c / 'boot/boot-diag.img') == boot['boot_sha256'],
        dtbo_digest=sha(c / 'boot/dtbo-diag.img') == boot['dtbo_sha256'],
    )
    data = (c / 'source-dt/effective.dtb').read_bytes()
    checks['effective_device_tree_digest'] = (hashlib.sha256(data).hexdigest() ==
        source['outputs']['effective.dtb']['sha256'])
    firmware_delta = None
    if a.wifi_firmware:
        if a.wifi_disabled_against:
            p.error('Firmware cannot be added to the disabled WLAN profile')
        from stage_m3_wifi_firmware import wifi_firmware, ramdisk_manifest, verify_ramdisk_firmware
        payloads, proof = wifi_firmware(a.wifi_firmware, a.wifi_board_file)
        manifest = ramdisk_manifest(c/'ramdisk/ramdisk.cpio.gz')
        verify_ramdisk_firmware(manifest, proof)
        baseline_manifest = read(a.baseline/'ramdisk-manifest.json')
        # The baseline manifest is tied to the original compressed archive hash.
        checks['baseline_ramdisk_manifest'] = baseline_manifest['gzip_sha256'] == old['ramdisk']['gzip_sha256']
        old_entries = baseline_manifest['entries']
        changed = sorted(n for n in old_entries.keys() & manifest.keys() if old_entries[n] != manifest[n])
        added = sorted(manifest.keys() - old_entries.keys())
        removed = sorted(old_entries.keys() - manifest.keys())
        if a.wifi_board_file:
            _, baseline_proof = wifi_firmware(a.wifi_firmware)
            checks['baseline_has_reviewed_boot_firmware_only'] = old['ramdisk'].get('wifi_firmware') == baseline_proof
            expected_additions = ['lib/firmware/ath11k/QCA6390/hw2.0/board.bin']
            delta_check = 'only_same_handset_board_and_trial_id_added'
        else:
            expected_additions = sorted(['lib/firmware/'+n for n in payloads] +
                ['lib/firmware/ath11k', 'lib/firmware/ath11k/QCA6390', 'lib/firmware/ath11k/QCA6390/hw2.0'])
            delta_check = 'only_boot_firmware_and_trial_id_added'
        checks[delta_check] = changed == ['trial-id'] and added == expected_additions and not removed
        checks['wifi_firmware_provenance'] = rd.get('wifi_firmware') == usb.get('wifi_firmware') == proof
        checks['same_firmware_trial_kernel'] = kernel['image_sha256'] == old['kernel']['image_sha256']
        checks['same_firmware_trial_dt'] = source['outputs']['effective.dtb'] == old['boot']['device_tree_build']['outputs']['effective.dtb']
        firmware_delta = dict(added=added, changed=changed, removed=removed, proof=proof)
    else:
        checks['same_wifi_firmware'] = rd.get('wifi_firmware') == old['ramdisk'].get('wifi_firmware')
    display = check_m3_display(data, True, True, True, True,
                               wifi=a.wifi_disabled_against is None)
    if a.wifi_disabled_against:
        isolated = read(a.wifi_disabled_against / 'inputs.json')
        checks['same_isolated_kernel'] = kernel['image_sha256'] == isolated['kernel']['image_sha256']
        checks['exact_baseline_device_tree'] = (source['outputs']['effective.dtb'] ==
            old['boot']['device_tree_build']['outputs']['effective.dtb'])
        wifi = dict(enabled=False, isolation_against=a.wifi_disabled_against.name,
                    hardware_result='NOT RUN; no WLAN discovery/connection pass is possible')
    else:
        wifi = check_m3_wifi(data, staged=True)
    delta = {k: dict(before=before.get(k, 'n'), after=after.get(k, 'n'))
             for k in sorted(before.keys() | after.keys()) if before.get(k) != after.get(k)}
    report = dict(trial=a.trial, baseline=a.baseline.name, passed=all(checks.values()),
        checks=checks, config_changes=delta, display=display, wifi=wifi,
        kernel=kernel['image_sha256'], boot=boot['boot_sha256'], dtbo=boot['dtbo_sha256'],
        firmware_delta=firmware_delta, device_result='NOT RUN')
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(passed=report['passed'], failed=[k for k, v in checks.items() if not v])))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
