"""Record a bounded operator input session on an identified GSI boot.

No input injection or settings changes. Raw getevent and Android dumps stay in
the private trial directory; publish only reviewed hardware acceptance results.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import time


def shell(command, timeout=10):
    r = subprocess.run(['adb', '-s', 'RMX2072-M1', 'shell', command],
                       capture_output=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr).decode('utf-8', errors='replace').replace('\r', '')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--trial', required=True)
    p.add_argument('--boot-id', required=True)
    p.add_argument('--label', required=True)
    p.add_argument('--seconds', type=int, default=240)
    a = p.parse_args()
    if (not re.fullmatch(r'ufs-host-g3-gsi17-firststage-ufs-\d{2}', a.trial)
            or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,40}', a.label)
            or not re.fullmatch(r'[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}', a.boot_id)
            or not 10 <= a.seconds <= 600):
        p.error('Use a recorded trial/boot, simple label and 10..600 seconds')
    rc, identity = shell('cat /proc/sys/kernel/random/boot_id; getprop ro.build.version.sdk; getenforce')
    if rc or identity.splitlines() != [a.boot_id, '37', 'Enforcing']:
        raise ValueError('Not the requested enforcing GSI boot: ' + repr(identity))
    root = a.workspace.resolve() / 'records' / a.trial / 'live'
    if not (root / 'host-events.jsonl').is_file():
        raise ValueError('Missing matching device trial record')
    dest = root / ('input-' + a.label)
    dest.mkdir(exist_ok=False)
    snapshots = {
        'input': 'getevent -pl; cat /proc/bus/input/devices; timeout 8 dumpsys input',
        'state': 'cat /proc/sys/kernel/random/boot_id; getprop sys.boot_completed; '
                 'getprop sys.usb.state; getprop persist.sys.usb.config; '
                 'pidof system_server surfaceflinger audioserver; '
                 'timeout 8 dumpsys power; timeout 8 dumpsys window windows',
        'overlay': 'cmd overlay list; cmd overlay lookup android android:bool/config_displayColorFadeDisabled',
        'kernel': 'dmesg',
    }
    def save_snapshots(prefix):
        for name, command in snapshots.items():
            try:
                rc, out = shell(command, 22)
                text = 'exit_code=' + str(rc) + '\n' + out
            except subprocess.SubprocessError as error:
                text = 'collection_error=' + str(error)
            (dest / (prefix + '-' + name + '.txt')).write_text(text, encoding='utf-8')
    save_snapshots('before')
    rows = []
    with (dest / 'getevent.txt').open('wb') as events:
        proc = subprocess.Popen(['adb', '-s', 'RMX2072-M1', 'shell',
                                 'timeout ' + str(a.seconds) + ' getevent -lt'],
                                stdout=events, stderr=subprocess.STDOUT)
        start = time.monotonic()
        print('INPUT_CAPTURE_READY boot=' + a.boot_id + ' label=' + a.label, flush=True)
        try:
            while proc.poll() is None and time.monotonic() - start < a.seconds + 8:
                try:
                    rc, state = shell('cat /proc/sys/kernel/random/boot_id; '
                        'pidof system_server; getprop sys.usb.state', 4)
                    row = dict(elapsed=round(time.monotonic() - start, 2), rc=rc, state=state.splitlines())
                except subprocess.SubprocessError as error:
                    row = dict(elapsed=round(time.monotonic() - start, 2), error=str(error))
                rows.append(row)
                if row.get('rc') or 'error' in row or row.get('state', [])[:1] != [a.boot_id]:
                    print('INPUT_CONNECTION_CHANGE ' + json.dumps(row), flush=True)
                time.sleep(3)
        finally:
            if proc.poll() is None:
                proc.terminate()
            proc.wait(timeout=5)
    save_snapshots('after')
    report = dict(boot_id=a.boot_id, label=a.label, seconds=a.seconds,
                  utc=datetime.now(timezone.utc).isoformat(), event_process_returncode=proc.returncode,
                  connection_samples=rows, input_injected=False,
                  acceptance='NOT AUTOMATICALLY DETERMINED; correlate operator action, events and UI')
    (dest / 'session.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('INPUT_CAPTURE_COMPLETE ' + str(dest), flush=True)


if __name__ == '__main__':
    main()
