"""Require trial-68 inputs plus only the explicit standard-PPS boot option."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'baseline', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--kernel-commit', required=True)
    p.add_argument('--run-id', required=True, type=int)
    p.add_argument('--trial', required=True)
    a = p.parse_args()
    def read(path):
        return json.loads(path.read_text(encoding='utf-8'))
    def sha(path):
        with path.open('rb') as f:
            return hashlib.file_digest(f, 'sha256').hexdigest()
    w = a.workspace.resolve()
    repo, c = w / 'repo', w / 'current'
    old = read(a.baseline / 'inputs.json')
    b, k, r, u = [read(c / name) for name in ('boot/control.json', 'kernel/provenance.json',
                                            'ramdisk/ramdisk-provenance.json', 'usb-build.json')]
    panel = repo / 'device/realme/bladerunner_48m/display/panel-samsung-rm19795.c'
    manifest = c / 'kernel/display-source.sha256'
    source_hashes = {Path(line.split()[1]).name:line.split()[0] for line in manifest.read_text().splitlines()}
    flags = ('stock_phy_test','stock_dsc_test','stock_linkclock_test','single_dsc_test',
             'panel_readback_test','solid_fill_test','first_frame_trace')
    checks = dict(
        pinned_build=k['source_commit'] == a.kernel_commit and k['run_id'] == a.run_id,
        kernel_verified=k['source_digests_verified'] and k['dist_digests_verified'] and not k['installing'],
        kernel_hash=sha(c/'kernel/Image') == k['image_sha256'] == b['kernel_sha256'] == u['kernel'],
        boot_hash=sha(c/'boot/boot-diag.img') == b['boot_sha256'],
        ramdisk_hash=sha(c/'ramdisk/ramdisk.cpio.gz') == b['ramdisk_sha256'] == r['gzip_sha256'],
        panel_source=source_hashes[panel.name] == hashlib.sha256(panel.read_bytes().replace(b'\r\n',b'\n')).hexdigest(),
        panel_manifest=sha(manifest) == k['selected_member_sha256'][manifest.name],
        same_kernel_config=k['selected_member_sha256']['sm8250_bootstrap_dot_config'] == old['kernel']['selected_member_sha256']['sm8250_bootstrap_dot_config'],
        same_kernel_patches=all(value == old['kernel']['selected_member_sha256'].get(name) for name,value in k['selected_member_sha256'].items() if name.endswith('.sha256') and name != 'display-source.sha256'),
        same_container=read(c/'candidate/candidate.json') == old['candidate'],
        same_scratch=read(c/'volumes/scratch.json') == old['scratch'],
        same_device_trees=b['device_tree_build']['outputs'] == old['boot']['device_tree_build']['outputs'],
        same_dtbo=sha(c/'boot/dtbo-diag.img') == b['dtbo_sha256'] == old['boot']['dtbo_sha256'],
        only_pps_cmdline=b['cmdline'] == old['boot']['cmdline'] + ' panel_samsung_rm19795.pps=1',
        explicit_pps=b.get('standard_pps_test') is True and u.get('standard_pps_test') is True,
        prior_pps_off=not old['boot'].get('standard_pps_test', False),
        old_flags_retained=all(b[key] == old['boot'][key] for key in flags),
        same_payloads=all(r[key] == old['ramdisk'][key] for key in ('display_probe_sha256','pattern_rgb_sha256','first_stage_init_sha256','witness_sha256','adb_public_key_sha256')),
        same_vendor_guard=all(u[key] == old['usb_build'][key] for key in ('guard','vendor_unsigned','vendor_signed')),
        trace_and_gate=r['first_frame_trace'] is True and r['display_staged'] is True and b['host_start_required_after_every_reboot'] is True,
        clean_recipe=not subprocess.check_output(['git','-C',str(repo),'status','--porcelain']),
        trial_id=r['trial_id'] == u['trial'] == a.trial,
    )
    result = dict(trial=a.trial, checks=checks, passed=all(checks.values()),
                  recipe_commit=u['recipe_commit'], kernel_commit=k['source_commit'],
                  run_id=k['run_id'], kernel=k['image_sha256'], boot=b['boot_sha256'],
                  scope='Offline input/provenance checks. No handset access or physical acceptance.')
    a.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
