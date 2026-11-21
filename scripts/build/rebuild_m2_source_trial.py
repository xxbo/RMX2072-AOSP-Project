"""Rebuild only M2 boot components; retain the exact GSI, vendor and test seeds."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from check_source_first_stage import verify_source_first_stage


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'ndk', 'adb-public-key', 'board-source'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--trial', required=True)
    p.add_argument('--display', action='store_true', help='Build the M3 DRM candidate and physical KMS probe')
    p.add_argument('--display-staged', action='store_true', help='Gate staged display binding on diagnostic USB capture')
    p.add_argument('--single-dsc-test', action='store_true', help='Opt in to the RM19795 single DSC isolation experiment')
    p.add_argument('--solid-fill-test', action='store_true', help='Opt in to native SSPP hardware pixel generation')
    p.add_argument('--panel-readback-test', action='store_true', help='Opt in to one-shot RM19795 status/PPS readback')
    p.add_argument('--stock-linkclock-test', action='store_true', help='Opt in to the measured F.20 DSI transfer-clock budget')
    p.add_argument('--stock-dsc-test', action='store_true', help='Match both encoder and panel to the original RM19795 PPS')
    p.add_argument('--stock-phy-test', action='store_true', help='Match the original 660 MHz PHY timing table, retaining trial 66 DSC')
    p.add_argument('--first-frame-trace', action='store_true', help='Capture the native first-frame event history without changing display settings')
    a = p.parse_args()
    if a.display_staged and not a.display:
        p.error('--display-staged requires --display')
    if a.single_dsc_test and not a.display:
        p.error('--single-dsc-test requires --display')
    if a.solid_fill_test and not a.display:
        p.error('--solid-fill-test requires --display')
    if a.panel_readback_test and not a.display:
        p.error('--panel-readback-test requires --display')
    if a.stock_linkclock_test and not a.display:
        p.error('--stock-linkclock-test requires --display')
    if a.stock_dsc_test and (not a.stock_linkclock_test or not a.single_dsc_test):
        p.error('--stock-dsc-test requires --stock-linkclock-test and --single-dsc-test')
    if a.stock_phy_test and not a.stock_dsc_test:
        p.error('--stock-phy-test requires --stock-dsc-test')
    if a.first_frame_trace and (not a.stock_phy_test or not a.display_staged):
        p.error('--first-frame-trace requires the staged trial 67 baseline')
    if not re.fullmatch(r'ufs-host-g3-gsi17-firststage-ufs-\d{2}', a.trial):
        p.error('Use the recorded handset trial naming')
    repo = Path(__file__).resolve().parents[2]
    if subprocess.check_output(['git', '-C', repo, 'status', '--porcelain']):
        raise ValueError('Commit the complete recipe before packaging a physical candidate')
    commit = subprocess.check_output(['git', '-C', repo, 'rev-parse', 'HEAD'], text=True).strip()
    work = a.workspace.resolve()
    current = work / 'current'
    build = repo / 'scripts/build'
    tools = a.ndk.resolve() / 'toolchains/llvm/prebuilt/windows-x86_64/bin'
    def run(*args):
        subprocess.run([str(x) for x in args], check=True)
    def sha(path):
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()
    init = verify_source_first_stage(current / 'init-build', (current / 'init').read_bytes())
    kernel = json.loads((current / 'kernel/provenance.json').read_text())
    if not kernel.get('source_pon') or kernel.get('installing'):
        raise ValueError('Install the checked source-PON kernel before packaging')
    previous = json.loads((current / 'usb-build.json').read_text())
    if sha(current / 'rmx-m1-guard') != previous['guard'] or sha(current / 'vendor-signed.img') != previous['vendor_signed']:
        raise ValueError('M2 must retain the accepted vendor/guard')
    sys.path.insert(0, str(repo / 'scripts/device_audit'))
    from check_super_chunks import verify
    candidate = json.loads((current / 'candidate/candidate.json').read_text())
    profile = json.loads((current / 'verified-profile/signed.json').read_text())
    if (candidate['signed'] != profile or profile['system']['sha256'] != sha(current / 'system.img')
            or profile['vendor']['sha256'] != sha(current / 'vendor-signed.img')
            or [p['sha256'] for p in verify(current / 'candidate', candidate['sha256'])['parts']] != candidate['parts']):
        raise ValueError('M2 GSI/vendor/container differ from the verified profile')
    run(sys.executable, build / 'build_m2_device_tree.py', '--source', a.board_source.resolve(),
        '--output', current / 'source-dt', '--cpp', tools / 'clang.exe',
        '--dtc', current / 'dtc-tools/dtc.exe', '--libfdt', current / 'dtc-tools/libfdt-1.dll',
        *(['--display'] if a.display else []),
        *(['--display-staged'] if a.display_staged else []))
    if a.display:
        if not kernel.get('display'):
            raise ValueError('Install the checked DRM/panel kernel before packaging M3')
        run(sys.executable, build / 'build_display_smoke.py', '--ndk', a.ndk.resolve(),
            '--output', current / 'display-smoke')
    run(tools / 'aarch64-linux-android35-clang.cmd', '-static', '-O2', '-Wall', '-Wextra', '-Werror',
        repo / 'scripts/device_audit/first_stage_witness.c', '-o', current / 'first-stage-witness')
    run(tools / 'llvm-strip.exe', '--strip-all', current / 'first-stage-witness')
    run(sys.executable, build / 'build_diag_ramdisk.py', '--busybox', current / 'busybox',
        '--reboot-helper', current / 'reboot-edl', '--entry-carrier', current / 'entry-carry',
        '--return-to-edl-after', 180, '--gadget-bind-delay', 20, '--trial-id', a.trial,
        '--ufs-host-g3-test', '--super-tools-apks', current / 'apks',
        '--android-first-stage', current / 'init', '--first-stage-source-build', current / 'init-build',
        '--first-stage-witness', current / 'first-stage-witness',
        '--ufs-first-stage', current / 'verified-profile', '--scratch-volumes', current / 'volumes',
        '--adb-public-key', a.adb_public_key.resolve(), '--output', current / 'ramdisk', '--autonomous-ufs',
        *(['--display-smoke', current / 'display-smoke/drm-panel-smoke'] if a.display else []),
        *(['--display-staged'] if a.display_staged else []),
        *(['--solid-fill-test'] if a.solid_fill_test else []),
        *(['--first-frame-trace'] if a.first_frame_trace else []))
    run(sys.executable, build / 'pack_m2_source_boot.py', '--workspace', work,
        *(['--single-dsc-test'] if a.single_dsc_test else []),
        *(['--solid-fill-test'] if a.solid_fill_test else []),
        *(['--panel-readback-test'] if a.panel_readback_test else []),
        *(['--stock-linkclock-test'] if a.stock_linkclock_test else []),
        *(['--stock-dsc-test'] if a.stock_dsc_test else []),
        *(['--stock-phy-test'] if a.stock_phy_test else []),
        *(['--first-frame-trace'] if a.first_frame_trace else []))
    record = dict(previous, trial=a.trial, recipe_commit=commit, recipe_dirty=False,
                  kernel=kernel['image_sha256'], witness=sha(current / 'first-stage-witness'),
                  source_first_stage=init, source_device_trees=True,
                  display=a.display,
                  display_staged=a.display_staged,
                  single_dsc_test=a.single_dsc_test,
                  solid_fill_test=a.solid_fill_test,
                  panel_readback_test=a.panel_readback_test,
                  stock_linkclock_test=a.stock_linkclock_test,
                  stock_dsc_test=a.stock_dsc_test,
                  stock_phy_test=a.stock_phy_test,
                  first_frame_trace=a.first_frame_trace,
                  adb_public_key_sha256=json.loads((current / 'ramdisk/ramdisk-provenance.json').read_text())['adb_public_key_sha256'])
    (current / 'usb-build.json').write_text(json.dumps(record, indent=2) + '\n')
    print('M2 source candidate prepared; original GSI/vendor/container and scratch seeds retained.')


if __name__ == '__main__':
    main()
