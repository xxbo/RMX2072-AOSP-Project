"""Read real gauge and Android battery state in one identified GSI boot.

No battery overrides, sysfs writes, input injection, service restarts or charging
commands are issued. Raw evidence is retained even when acceptance fails.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--boot-id', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)

    def shell(command):
        return subprocess.check_output(['adb', '-s', 'RMX2072-M1', 'shell', command],
            timeout=20, stderr=subprocess.STDOUT).decode('utf-8', errors='replace').replace('\r', '')

    def identity():
        result = shell('cat /proc/sys/kernel/random/boot_id; getenforce; getprop ro.build.version.sdk; getprop sys.boot_completed').splitlines()
        if result != [a.boot_id, 'Enforcing', '37', '1']:
            raise ValueError('Not the identified boot-complete enforcing GSI')
        return result

    identity()
    shell('ls -lZ /sys/class/power_supply')  # Fail visibly if discovery itself is denied.
    names = shell('ls /sys/class/power_supply').split()
    if any(not re.fullmatch(r'[A-Za-z0-9_.-]+', n) for n in names):
        raise ValueError('Unexpected power_supply name')
    samples = []
    for index in range(3):
        identity()
        gauge = {}
        for name in names:
            base = '/sys/class/power_supply/'+name
            raw = shell('cat '+base+'/uevent')
            (a.output/f'{index}-{name}-uevent.txt').write_text(raw)
            values = dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)
            gauge[name] = dict(values=values, device_path=shell('readlink -f '+base).strip(),
                               labels=shell('ls -ldZ '+base+'/ '+base+'/capacity '+base+'/present'))
        raw = shell('dumpsys battery')
        (a.output/f'{index}-battery-service.txt').write_text(raw)
        android = dict(re.findall(r'^\s*([A-Za-z_ ]+):\s*([^\n]*)$', raw, re.M))
        android = {k.strip(): v.strip() for k, v in android.items()}
        batteries = [g for g in gauge.values() if g['values'].get('POWER_SUPPLY_TYPE') == 'Battery']
        checks = dict(one_real_gauge=len(batteries) == 1, no_android_override='UPDATES STOPPED' not in raw)
        if len(batteries) == 1:
            g = batteries[0]
            v = g['values']
            try:
                capacity = int(v['POWER_SUPPLY_CAPACITY'])
                voltage = int(v['POWER_SUPPLY_VOLTAGE_NOW'])
                temperature = int(v['POWER_SUPPLY_TEMP'])
                checks.update(
                    dedicated_board_bus='/888000.i2c/' in g['device_path'] and bool(
                        re.search(r'/\d+-0055/', g['device_path'])),
                    present=v['POWER_SUPPLY_PRESENT'] == '1' and android.get('present') == 'true',
                    capacity_range=0 <= capacity <= 100,
                    voltage_range=2500000 <= voltage <= 10000000,
                    temperature_range=-200 <= temperature <= 600,
                    android_capacity=int(android.get('level', '-1')) == capacity,
                    android_voltage=abs(int(android.get('voltage', '-1'))*1000-voltage) <= 20000,
                    android_temperature=abs(int(android.get('temperature', '-10000'))-temperature) <= 10,
                )
            except (KeyError, ValueError) as error:
                checks['readable_measurements'] = False
                g['parse_error'] = str(error)
        samples.append(dict(utc=datetime.now(timezone.utc).isoformat(), gauge=gauge,
                            android=android, checks=checks))
        if index != 2:
            time.sleep(10)
    final_identity = identity()
    logs = shell('logcat -b all -d -v threadtime')
    relevant = '\n'.join(line for line in logs.splitlines() if re.search(
        r'healthd|BatteryService|bq27|bq28|sysfs_batteryinfo|vendor_idc_file|Goodix|avc:.*rmx_health', line, re.I))+'\n'
    (a.output/'battery-logcat.txt').write_text(relevant, encoding='utf-8')
    report = dict(boot_id=a.boot_id, identity=final_identity, samples=samples,
        passed=all(all(s['checks'].values()) for s in samples),
        scope='Gauge-to-Android telemetry only; charging, setup and Launcher require separate acceptance',
        injected_battery_state=False, charging_control=False,
        evidence_sha256={f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in a.output.glob('*.txt')})
    (a.output/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(passed=report['passed'], boot_id=a.boot_id,
        levels=[s['android'].get('level') for s in samples],
        failed=[{k: v for k, v in s['checks'].items() if not v} for s in samples])))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
