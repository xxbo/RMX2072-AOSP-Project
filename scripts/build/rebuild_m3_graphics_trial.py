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


def retained_wifi_flags(prior, firmware, board_file=None):
    """Vendor changes must keep the existing WLAN DT and boot firmware."""
    enabled = prior.get('wifi', False)
    if not isinstance(enabled, bool):
        raise ValueError('Invalid prior Wi-Fi option')
    previous = prior.get('wifi_firmware')
    if not enabled:
        if previous or firmware is not None or board_file is not None:
            raise ValueError('Wi-Fi firmware requires an existing WLAN profile')
        return []
    flags = ['--wifi']
    if previous:
        if firmware is None:
            raise ValueError('Provide --wifi-firmware to retain the existing boot firmware')
        from stage_m3_wifi_firmware import wifi_firmware
        _, actual = wifi_firmware(firmware, board_file)
        if actual != previous:
            raise ValueError('A vendor rebuild must retain the exact WLAN boot firmware')
        flags += ['--wifi-firmware', str(firmware.resolve())]
        if board_file is not None:
            flags += ['--wifi-board-file', str(board_file.resolve())]
    elif firmware is not None or board_file is not None:
        raise ValueError('Stage new WLAN firmware separately from a vendor rebuild')
    return flags


def check_retained_peripherals(prior, requested):
    for key in ('input_devices', 'battery_gauge', 'performance', 'panel_refresh'):
        if key in prior and requested.get(key) != prior[key]:
            raise ValueError('Vendor rebuild must retain '+key)


def check_wifi_overlay_choice(previous, overlay, remove):
    if overlay and remove:
        raise ValueError('Cannot retain and remove the Wi-Fi overlay together')
    if remove and not previous:
        raise ValueError('No previous Wi-Fi overlay to remove')
    if previous and not overlay and not remove:
        raise ValueError('Retain --wifi-overlay or explicitly --remove-wifi-overlay')


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
    p.add_argument('--policy-proof', type=Path, help='Strict compilation record for the exact composed policy')
    p.add_argument('--input-devices', action='store_true', help='Include the M3 touch and volume-key bindings')
    p.add_argument('--battery-gauge', action='store_true', help='Include the external BQ28Z610 measurement path')
    p.add_argument('--performance', action='store_true')
    p.add_argument('--wifi-firmware', type=Path, help='Retain exactly the previous WLAN boot firmware')
    p.add_argument('--wifi-board-file', type=Path, help='Retain the exact previously included same-handset board ELF')
    p.add_argument('--wifi-overlay', type=Path, help='Explicitly compose the reviewed mainline supplicant RRO')
    p.add_argument('--wifi-vendor', type=Path, help='Explicitly compose the verified source vendor supplicant')
    p.add_argument('--remove-wifi-overlay', action='store_true', help='Explicitly withdraw the failed mainline RRO; use the wifi-rollback preflight before writing')
    p.add_argument('--panel-refresh', type=int, choices=(60, 90), default=60)
    a = p.parse_args()
    if a.battery_gauge and not a.input_devices:
        p.error('--battery-gauge requires --input-devices')
    if not re.fullmatch(r'ufs-host-g3-gsi17-firststage-ufs-\d{2,3}', a.trial):
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
    if a.input_devices and not (current/'input-overlay/provenance.json').is_file():
        raise ValueError('Input trial requires the source ColorFade overlay before power-key testing')
    prior = json.loads((current/'usb-build.json').read_text())
    check_retained_peripherals(prior, vars(a))
    display_flags = retained_display_flags(prior, a.display_staged)
    wifi_flags = retained_wifi_flags(prior, a.wifi_firmware, a.wifi_board_file)
    if prior.get('wifi') and not (a.performance and a.battery_gauge):
        p.error('Retaining Wi-Fi requires --performance and --battery-gauge')
    if (a.wifi_overlay or a.wifi_vendor) and not prior.get('wifi'):
        p.error('Wi-Fi userspace requires the existing native WLAN profile')
    if a.wifi_overlay and a.wifi_vendor:
        p.error('Choose either --wifi-overlay or --wifi-vendor')
    old_graphics = current/'graphics-candidate.json'
    old_sources = json.loads(old_graphics.read_text())['graphics_source'] if old_graphics.is_file() else {}
    old_overlay = old_sources.get('wifi_android')
    if old_sources.get('wifi') and not a.wifi_vendor:
        raise ValueError('Retain the existing source supplicant explicitly with --wifi-vendor')
    check_wifi_overlay_choice(old_overlay, a.wifi_overlay, a.remove_wifi_overlay)
    if a.remove_wifi_overlay:
        from stage_m3_wifi_android import overlay_payload
        _, expected_overlay = overlay_payload(current/'wifi-overlay')
        if old_overlay != expected_overlay:
            raise ValueError('Only the exact reviewed mainline RRO can be withdrawn')
    overlay_flags = ['--wifi-overlay', a.wifi_overlay.resolve()] if a.wifi_overlay else []
    if a.wifi_vendor:
        overlay_flags += ['--wifi-vendor', a.wifi_vendor.resolve()]
    if sha(current/'rmx-m1-guard') != prior['guard']:
        raise ValueError('USB guardian differs from the retained input')
    seeds = json.loads((current/'volumes/scratch.json').read_text())
    system_sha = sha(current/'system.img')
    reference = json.loads((repo/'build/device/gsi17-mount-reference.json').read_text())
    if system_sha != reference['image_sha256']:
        raise ValueError('GSI changed')
    subprocess.run([sys.executable, str(build/'build_display_smoke.py'),
                    '--ndk', str(a.ndk.resolve()), '--output', str(current/'display-smoke')], check=True)
    files, provenance = compose(current/'info-input', current/'rmx-m1-guard', graphics, a.wifi_overlay, a.wifi_vendor)
    policy = json.loads((a.policy_proof or repo/'build/device/m3-graphics-policy-2026-11-16.json').read_text())
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
        '--graphics', graphics, *overlay_flags)
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
        '--output', current/'verified-profile', *overlay_flags)
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
        *(['--display-staged'] if a.display_staged else []),
        *(['--input-devices'] if a.input_devices else []),
        *(['--battery-gauge'] if a.battery_gauge else []),
        *(['--performance'] if a.performance else []), '--panel-refresh', a.panel_refresh,
        *display_flags, *wifi_flags)
    if sha(current/'system.img') != system_sha or json.loads((current/'volumes/scratch.json').read_text()) != seeds:
        raise ValueError('GSI or scratch seed manifest changed during preparation')
    result = dict(trial=a.trial, graphics_source=provenance, vendor_payload_bytes=payload_size,
                  vendor_signed_bytes=signed_size, vendor_signed_sha256=staged['vendor_signed'],
                  composed_vendor_cil_sha256=cil_sha,
                  strict_compile_input_sha256=policy['combined_vendor_policy_sha256'],
                  policy_proof_reused_for_identical_statements=True,
                  source_gsi_sha256=system_sha, scratch=seeds, display_staged=a.display_staged,
                  retained_display_flags=display_flags,
                  retained_wifi_flags=wifi_flags,
                  openssl_version=openssl_version,
                  handset_write='NOT RUN')
    (current/'graphics-candidate.json').write_text(json.dumps(result, indent=2)+'\n')
    print('Signed source graphics candidate prepared and verified; handset unchanged.')


if __name__ == '__main__':
    main()
