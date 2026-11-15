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
    a = p.parse_args()
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
        '--dtc', current / 'dtc-tools/dtc.exe', '--libfdt', current / 'dtc-tools/libfdt-1.dll')
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
        '--adb-public-key', a.adb_public_key.resolve(), '--output', current / 'ramdisk', '--autonomous-ufs')
    run(sys.executable, build / 'pack_m2_source_boot.py', '--workspace', work)
    record = dict(previous, trial=a.trial, recipe_commit=commit, recipe_dirty=False,
                  kernel=kernel['image_sha256'], witness=sha(current / 'first-stage-witness'),
                  source_first_stage=init, source_device_trees=True,
                  adb_public_key_sha256=json.loads((current / 'ramdisk/ramdisk-provenance.json').read_text())['adb_public_key_sha256'])
    (current / 'usb-build.json').write_text(json.dumps(record, indent=2) + '\n')
    print('M2 source candidate prepared; original GSI/vendor/container and scratch seeds retained.')


if __name__ == '__main__':
    main()
