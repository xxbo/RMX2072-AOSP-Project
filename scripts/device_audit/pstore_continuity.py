#!/usr/bin/env python3
"""Mark RAM-only logs, then inspect them after an independently controlled reboot.

Never flashes, erases logs or reboots. Raw output must remain outside the checkout.
"""
import argparse
import datetime
import io
import json
import pathlib
import secrets
import shlex
import subprocess
import tarfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['mark', 'capture'])
    parser.add_argument('--adb', default='adb')
    parser.add_argument('--serial')
    parser.add_argument('--su', default='/debug_ramdisk/su')
    parser.add_argument('--output', required=True, type=pathlib.Path)
    args = parser.parse_args()
    output = args.output.resolve()
    repo = pathlib.Path(__file__).resolve().parents[2]
    if output == repo or repo in output.parents:
        parser.error('Raw evidence must stay outside checkout')
    prefix = [args.adb] + (['-s', args.serial] if args.serial else [])

    def root(command):
        result = subprocess.run(prefix + ['exec-out', shlex.quote(args.su) +
                                ' -c ' + shlex.quote(command)],
                                capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors='replace'))
        return result.stdout

    if root('id -u').strip() != b'0':
        raise SystemExit('Authorized root shell not available')
    state_path = output / 'marker.json'
    if args.stage == 'mark':
        output.mkdir(parents=True, exist_ok=False)
        token = 'RMX2072_PSTORE_CONTROL_' + secrets.token_hex(8)
        # Stock console_loglevel is 4. Use an explicit emergency-level marker
        # so console filtering cannot invalidate the continuity control.
        command = ("printf '%s\\n' " + shlex.quote('<0>' + token) +
                   " > /dev/kmsg && printf '%s\\n' " + shlex.quote(token) +
                   ' > /dev/pmsg0 && echo MARK_OK')
        reply = root(command)
        (output / 'mark-reply.txt').write_bytes(reply)
        if reply.strip() != b'MARK_OK':
            raise SystemExit('RAM marker write failed; do not interpret this as a continuity test')
        before = root('dmesg')
        (output / 'before-dmesg.txt').write_bytes(before)
        metadata = dict(token=token, marked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        kernel=root('uname -r').decode().strip(),
                        marker_seen_in_dmesg=token.encode() in before, marker_loglevel=0,
                        boot_id=root('cat /proc/sys/kernel/random/boot_id').decode().strip())
        state_path.write_text(json.dumps(metadata, indent=2) + '\n')
        print(json.dumps(dict(stage='marked', marker_seen_in_dmesg=metadata['marker_seen_in_dmesg'])))
        return

    metadata = json.loads(state_path.read_text())
    archive_bytes = root('tar -C /sys/fs/pstore -cf - .')
    (output / 'after-pstore.tar').write_bytes(archive_bytes)
    (output / 'after-dmesg.txt').write_bytes(root('dmesg'))
    current_boot = root('cat /proc/sys/kernel/random/boot_id').decode().strip()
    matches = []
    identity_matches = []
    marker_id = metadata['token'].rsplit('_', 1)[1].encode()
    with tarfile.open(fileobj=io.BytesIO(archive_bytes)) as archive:
        members = [m.name for m in archive.getmembers() if m.isfile()]
        for member in archive.getmembers():
            if member.isfile():
                contents = archive.extractfile(member).read()
                if metadata['token'].encode() in contents:
                    matches.append(member.name)
                if marker_id in contents:
                    identity_matches.append(member.name)
    report = dict(reboot_observed=current_boot != metadata['boot_id'],
                  kernel=root('uname -r').decode().strip(), pstore_files=members,
                  marker_found_in=matches,
                  marker_64bit_id_found_in=identity_matches,
                  qualification='Only this tested reboot path and stock kernel layout; not 6.18 evidence')
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
