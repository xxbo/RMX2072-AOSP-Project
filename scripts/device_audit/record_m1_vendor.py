"""Reconstruct a public M1 vendor trial record from the private capture and readbacks."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from uuid import UUID

from serve_gsi_usb import REFERENCE, verify_first_stage


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def recovery_events(path):
    phases = [
        'enter: Sahara programmer ready', 'before: complete boot and original DTBO hashes matched',
        'candidate: complete boot and original DTBO hashes matched', 'candidate reset',
        'return: Sahara programmer ready', 'return-read: complete boot and original DTBO hashes matched',
        'restored: complete boot and original DTBO hashes matched', 'original reader reset',
        'stock Android boot completed', 'stock root evidence saved',
    ]
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    require([row['event'] for row in rows] == phases, 'Incomplete recovery sequence')
    times = [datetime.fromisoformat(row['at']) for row in rows]
    require(times == sorted(times), 'Out-of-order recovery events')
    return [dict(at=t.isoformat(), event=event) for t, event in zip(times, phases)]


def record(work, trial, vendor_dir, restored, image_build_run):
    require(re.fullmatch(r'ufs-host-g3-gsi17-firststage-vendor-[A-Za-z0-9-]+', trial), 'Unexpected trial ID')
    live = work/(trial+'-live')
    disk = work/(trial+'-trial')
    package = work/(trial+'-package')
    run, edl, pack = read(live/'result.json'), read(live/'return.json'), read(package/'control.json')
    ramdisk = read(work/(trial+'-rd')/'ramdisk-provenance.json')
    vendor = read(vendor_dir/'vendor.json')
    raw = live/'mount.txt'
    require(run['trial'] == run['identity']['trial'] == edl['identity']['trial'] == ramdisk['trial_id'] == trial,
            'Capture identities differ')
    require(run['identity']['kernel'] == edl['identity']['kernel'] and ramdisk['gzip_sha256'] == pack['ramdisk_sha256'],
            'Kernel or ramdisk identities differ')
    require(run['status'] == 'handoff-observed' and run['transcript_sha256'] == digest(raw), 'Transcript mismatch')
    require(vendor['sha256'] == digest(vendor_dir/'vendor.img') == ramdisk['project_vendor_sha256'],
            'Vendor image mismatch')
    require(edl['status'] == 'enumerated' and edl['command_sent'] and edl['before_timer_deadline'],
            'Software return to EDL was not verified')
    ref = read(REFERENCE)
    require(run['image_sha256'] == ref['image_sha256'], 'Unexpected GSI')
    text = raw.read_text(encoding='utf-8')
    footer = re.search(r'^last_block_sha256=([0-9a-f]{64})$', text, re.M)
    require(footer, 'Missing GSI footer read')
    genfs = '/etc/selinux/genfs_labels_version.txt' in vendor['files']
    seen = verify_first_stage(text, ref, footer[1], vendor['sha256'], genfs)
    require(seen['boot_id'] == run['boot_id'] and seen['stop'] == 'policy-load-open', 'Unexpected PID 1 checkpoint')
    require(all(any(line.endswith(message) for line in seen['policy_messages'])
                for message in ('Opening SELinux policy', 'Compiling SELinux policy', 'Loading SELinux policy')),
            'Missing runtime policy compilation evidence')
    if not genfs:
        require('plat_sepolicy_genfs_202404.cil; skipping' in text and 'strict_compile_rc=' not in text,
                'Unrecognized earlier genfs outcome')
    stock_build, completion, stock_id = restored.read_text(encoding='utf-8-sig').split()
    require(stock_build == 'RMX2072_11_F.20' and completion == '1' and UUID(stock_id) != UUID(seen['boot_id']),
            'Missing separate F.20 boot')
    events = recovery_events(disk/'events.jsonl')
    stock = '9ae2f907fd029e88c841121f4fbeb6f3a1ae32322a6703d8d142bbba31bb93c3'
    dtbo = '61d9b3ac8426a886de63cf4cde0552e2cab3cd5c47f83ef4335a624b657949ef'
    candidate = digest(package/'boot-diag.img')
    require(candidate == pack['boot_sha256'], 'Packaged boot mismatch')
    for stage, expected in [('before', stock), ('candidate', candidate), ('return-read', candidate), ('restored', stock)]:
        require(digest(disk/stage/'boot-readback.img') == expected and digest(disk/stage/'dtbo-readback.img') == dtbo,
                'Full partition readback differs at '+stage)
    fields = ('last_block_sha256=', 'source_table=', 'verity_table=', 'boot_id=', 'init_sha256=', 'gsi_device=',
              'vendor_device=', 'exec_pid=', 'mount_pid=', 'trial_stop=', 'pid1_', 'mounted_vendor_', 'strict_', 'verity_status=')
    messages = re.compile(r'\[\s*T1\] init: (?:(?:Opening|Compiling|Loading) SELinux policy|(?:Missing|Using) /system/etc/selinux/plat_sepolicy_genfs)')
    observations = [line for line in text.splitlines() if line.startswith(fields) or messages.search(line)]
    return dict(
        trial=trial, boot_id=seen['boot_id'], image_build_run=image_build_run,
        boot_sha256=candidate, ramdisk_sha256=pack['ramdisk_sha256'],
        vendor_image_sha256=vendor['sha256'], vendor_source_files=vendor['files'], kernel=run['identity']['kernel'],
        kernel_sha256=pack['kernel_sha256'], dtb_bundle_sha256=pack['dtb_bundle_sha256'],
        first_stage_sha256=ramdisk['first_stage_init_sha256'], witness_sha256=ramdisk['witness_sha256'],
        gsi_sha256=run['image_sha256'], transcript_sha256=run['transcript_sha256'], usb=run['stats'],
        observations=observations,
        results=dict(first_stage_pid1='PASS', switch_root_to_gsi='PASS', project_vendor_mount='PASS',
                     gsi_pid1_selinux_setup='PASS', runtime_policy_compilation='PASS',
                     genfs_202604='PASS' if genfs else 'FAIL', strict_neverallow_compile='PASS' if genfs else 'NOT RUN',
                     first_unmet_step=None if genfs else 'Vendor did not select 202604 genfs labels. Init fell back to 202404 and skipped the missing optional input.',
                     kernel_policy_load='NOT RUN', second_stage_init='NOT RUN', full_vintf_check='NOT RUN',
                     android17_adb='NOT RUN', disconnected_ufs_boot='NOT RUN'),
        recovery=dict(status='PASS', build=stock_build, boot_id=stock_id, sys_boot_completed=1,
                      kernel=(disk/'recovered/kernel-release.txt').read_text().strip(),
                      software_edl_seconds=edl['host_wait_seconds'], readbacks={'boot-readback.img':stock, 'dtbo-readback.img':dtbo},
                      host_local_events=events))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--trial', required=True)
    parser.add_argument('--vendor-dir', required=True, type=Path)
    parser.add_argument('--restored', required=True, type=Path, help='F.20 display ID, boot completion and boot ID')
    parser.add_argument('--image-build-run', required=True, type=int)
    parser.add_argument('--output', required=True, type=Path, help='New JSON file for one trial')
    args = parser.parse_args()
    row = record(args.work, args.trial, args.vendor_dir, args.restored, args.image_build_run)
    with args.output.open('x', encoding='utf-8') as out:
        out.write(json.dumps(row, indent=2)+'\n')
