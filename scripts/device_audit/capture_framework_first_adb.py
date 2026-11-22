"""Capture framework progress without restarting Android or changing properties."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time


def shell(command, timeout=30):
    result = subprocess.run(['adb', '-s', 'RMX2072-M1', 'shell', command],
                            capture_output=True, timeout=timeout)
    return (result.stdout + result.stderr).decode(errors='replace').replace('\r', '')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--trial', required=True)
    p.add_argument('--previous-boot', required=True)
    args = p.parse_args()
    if not re.fullmatch(r'ufs-host-g3-gsi17-firststage-ufs-\d{2}', args.trial):
        p.error('Use the recorded trial name')
    live = args.workspace.resolve()/'records'/args.trial/'live'
    deadline = time.monotonic()+1500
    while time.monotonic() < deadline:
        try:
            boot = shell('cat /proc/sys/kernel/random/boot_id', 3).strip()
            host = live/'host-events.jsonl'
            if (re.fullmatch(r'[0-9a-f-]{36}', boot) and boot != args.previous_boot
                    and host.exists() and boot in host.read_text()
                    and 'M1EVENT boot_id='+boot in shell('cat /data/local/tmp/rmx-m1-boot.txt', 3)):
                break
        except (OSError, subprocess.SubprocessError):
            pass
        time.sleep(2)
    else:
        raise TimeoutError('No matching new authenticated GSI ADB')
    commands = {
        'identity': 'cat /proc/sys/kernel/random/boot_id; uname -r; getenforce; getprop vendor.rmx.m1.state; getprop ro.boot.rmx_scratch; getprop sys.boot_completed',
        'services': 'getprop init.svc.installd; getprop init.svc.storaged; getprop init.svc.vendor.health-default; service check activity; service check window; service check package; service check SurfaceFlinger; service check android.security.maintenance; ps -AZ | grep -E "health-service|system_server|installd|surfaceflinger"',
        'storage': 'df -k /data /metadata; ls -lZ /sys/class/power_supply',
        'battery': 'timeout 15 dumpsys battery',
        'logcat': 'logcat -b all -d',
    }
    print('FIRST_FRAMEWORK_ADB '+boot, flush=True)
    for iteration in range(5):
        if shell('cat /proc/sys/kernel/random/boot_id', 3).strip() != boot:
            raise ValueError('Boot changed during framework capture')
        for name,command in commands.items():
            try:
                output = shell(command)
            except (OSError, subprocess.SubprocessError) as error:
                output = str(error)
            (live/f'framework-{iteration}-{name}.txt').write_text(output, encoding='utf-8')
            if name in ('identity', 'services'):
                print(f'{iteration} {name} '+output, flush=True)
        if iteration < 4:
            time.sleep(25)
    print('FRAMEWORK_CAPTURE_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
