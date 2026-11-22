"""Compose and sign the sole M3 graphics candidate from verified source artifacts.

This prepares local images only. It never changes the connected handset.
The pinned GSI, Keymaster inputs, USB guardian and scratch seeds remain fixed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from stage_m3_graphics import compose, filesystem_size


DISPLAY_OPTIONS = ('single_dsc_test', 'solid_fill_test', 'panel_readback_test',
                   'stock_linkclock_test', 'stock_dsc_test', 'stock_phy_test',
                   'first_frame_trace', 'standard_pps_test')


def retained_display_flags(prior, display_staged):
    """A vendor-only change must not silently undo the accepted panel setup."""
    if bool(prior.get('display_staged')) != display_staged:
        raise ValueError('Vendor rebuild must retain the prior display staging mode')
    if any(not isinstance(prior.get(key, False), bool) for key in DISPLAY_OPTIONS):
        raise ValueError('Invalid prior display option')
    return ['--' + key.replace('_', '-') for key in DISPLAY_OPTIONS if prior.get(key)]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'ndk', 'adb-public-key', 'board-source'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--trial', required=True)
    p.add_argument('--openssl', type=Path, help='OpenSSL executable; defaults to the executable on PATH')
    p.add_argument('--display-staged', action='store_true', help='Keep the diagnostic USB gate and native staged display paths')
    a = p.parse_args()
    if not re.fullmatch(r'ufs-host-g3-gsi17-firststage-ufs-\d{2}', a.trial):
        p.error('Use the recorded handset trial naming')
    repo = Path(__file__).resolve().parents[2]
    if subprocess.check_output(['git', '-C', repo, 'status', '--porcelain']):
        raise ValueError('Commit the complete graphics recipe before packaging')
    openssl = a.openssl or shutil.which('openssl')
    if not openssl:
        p.error('Provide --openssl or install OpenSSL on PATH before composing images')
    openssl = Path(openssl).resolve()
    if not openssl.is_file() or openssl.name.lower() not in ('openssl', 'openssl.exe'):
        p.error('--openssl must name the OpenSSL executable used by avbtool')
    openssl_version = subprocess.check_output([str(openssl), 'version'], text=True).strip()
    work = a.workspace.resolve()
    if work.is_relative_to(repo):
        raise ValueError('Keep generated images outside the public checkout')
    current = work/'current'
    build = repo/'scripts/build'
    graphics = current/'graphics'
    prior = json.loads((current/'usb-build.json').read_text())
    display_flags = retained_display_flags(prior, a.display_staged)
    if sha(current/'rmx-m1-guard') != prior['guard']:
        raise ValueError('USB guardian differs from the retained input')
    seeds = json.loads((current/'volumes/scratch.json').read_text())
    system_sha = sha(current/'system.img')
    reference = json.loads((repo/'build/device/gsi17-mount-reference.json').read_text())
    if system_sha != reference['image_sha256']:
        raise ValueError('GSI changed')
    subprocess.run([sys.executable, str(build/'build_display_smoke.py'),
                    '--ndk', str(a.ndk.resolve()), '--output', str(current/'display-smoke')], check=True)
    files, provenance = compose(current/'info-input', current/'rmx-m1-guard', graphics)
    policy = json.loads((repo/'build/device/m3-graphics-policy-2026-11-16.json').read_text())
    cil = files['/etc/selinux/vendor_sepolicy.cil']
    cil_sha = hashlib.sha256(cil).hexdigest()
    compiled_input = (current/'policy-check/m3-vendor.cil').read_bytes()
    statements = lambda data: [line.strip() for line in data.splitlines()
                               if line.strip() and not line.lstrip().startswith(b';')]
    if (policy['result'] != 'PASS_STRICT_COMPILE_ONLY'
            or hashlib.sha256(compiled_input).hexdigest() != policy['combined_vendor_policy_sha256']
            or statements(cil) != statements(compiled_input)):
        raise ValueError('Compile the exact new split policy with neverallow checks before packaging')
    # Reuse the proof only for the same GSI and identical statements. Full-line
    # comments and surrounding whitespace do not alter CIL semantics.
    payload_size = filesystem_size(files)
    del files
    avb = current/'avbtool.py'
    if sha(avb) != 'e5a664a38db623da00f080219bc0ee60a640a9dc4a872803616fae4938ac749b':
        raise ValueError('AVB tool differs from the pinned input')
    os.environ['PATH'] = os.pathsep.join((str(current/'fs-tools'), str(openssl.parent), os.environ['PATH']))
    def run(*args):
        subprocess.run([str(x) for x in args], check=True)
    run(sys.executable, build/'build_m1_vendor.py', '--output', current/'vendor',
        '--keymaster-info', current/'info-input', '--usb-guard', current/'rmx-m1-guard',
        '--graphics', graphics)
    report = json.loads((current/'vendor/vendor.json').read_text())
    unsigned = current/'vendor/vendor.img'
    if unsigned.stat().st_size != payload_size or sha(unsigned) != report['sha256']:
        raise ValueError('Vendor image differs from checked source inventory')
    # Ask avbtool for its real tree/metadata budget, rather than assuming the
    # old 17 MiB partition is sufficient for a source graphics payload.
    for padding_mib in range(1, 9):
        signed_size = payload_size+(padding_mib << 20)
        limit = int(subprocess.check_output([sys.executable, str(avb), 'add_hashtree_footer',
            '--partition_size', str(signed_size), '--calc_max_image_size', '--do_not_generate_fec']))
        if limit >= payload_size:
            break
    else:
        raise ValueError('AVB metadata exceeds the bounded graphics budget')
    shutil.copyfile(unsigned, current/'vendor-signed.img')
    run(sys.executable, avb, 'add_hashtree_footer', '--image', current/'vendor-signed.img',
        '--partition_name', 'vendor', '--partition_size', signed_size,
        '--algorithm', 'SHA256_RSA4096', '--key', current/'engineering-vendor.pem',
        '--hash_algorithm', 'sha256', '--salt', report['sha256'], '--do_not_generate_fec')
    run(sys.executable, build/'prepare_ufs_verification.py', '--system', current/'system.img',
        '--vendor', current/'vendor-signed.img', '--vendor-key', current/'vendor.avbpubkey',
        '--vendor-report', current/'vendor/vendor.json', '--graphics', graphics,
        '--graphics-keymaster-info', current/'info-input', '--usb-guard', current/'rmx-m1-guard',
        '--output', current/'verified-profile')
    run(sys.executable, repo/'scripts/device_audit/build_ufs_candidate.py',
        '--stock', work/'recovery/f20', '--system', current/'system.img',
        '--vendor', current/'vendor-signed.img', '--profile', current/'verified-profile',
        '--output', current/'candidate')
    staged = dict(prior, vendor_unsigned=report['sha256'], vendor_signed=sha(current/'vendor-signed.img'),
                  graphics_source_commit=provenance['source_commit'], graphics_device_result='NOT RUN')
    (current/'usb-build.json').write_text(json.dumps(staged, indent=2)+'\n')
    run(sys.executable, build/'rebuild_m2_source_trial.py', '--workspace', work,
        '--ndk', a.ndk.resolve(), '--adb-public-key', a.adb_public_key.resolve(),
        '--board-source', a.board_source.resolve(), '--trial', a.trial, '--display',
        *(['--display-staged'] if a.display_staged else []), *display_flags)
    if sha(current/'system.img') != system_sha or json.loads((current/'volumes/scratch.json').read_text()) != seeds:
        raise ValueError('GSI or scratch seed manifest changed during preparation')
    result = dict(trial=a.trial, graphics_source=provenance, vendor_payload_bytes=payload_size,
                  vendor_signed_bytes=signed_size, vendor_signed_sha256=staged['vendor_signed'],
                  composed_vendor_cil_sha256=cil_sha,
                  strict_compile_input_sha256=policy['combined_vendor_policy_sha256'],
                  policy_proof_reused_for_identical_statements=True,
                  source_gsi_sha256=system_sha, scratch=seeds, display_staged=a.display_staged,
                  retained_display_flags=display_flags,
                  openssl_version=openssl_version,
                  handset_write='NOT RUN')
    (current/'graphics-candidate.json').write_text(json.dumps(result, indent=2)+'\n')
    print('Signed source graphics candidate prepared and verified; handset unchanged.')


if __name__ == '__main__':
    main()
