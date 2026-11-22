"""Exercise the source HAL with one disposable AES key on an identified GSI boot.

No reboot, property change or original partition access. The source client deletes
its returned wrapped blob and never emits key/blob/plaintext bytes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from uuid import UUID


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--record', type=Path, required=True)
    p.add_argument('--boot-id', required=True)
    a = p.parse_args()
    UUID(a.boot_id)
    repo = Path(__file__).resolve().parents[2]
    pins_path = repo/'device/realme/bladerunner_48m/m1-keymaster-info/inputs.json'
    pins = json.loads(pins_path.read_text())
    output = a.record/'live/keymaster-aes'
    output.mkdir(exist_ok=False)

    def shell(command, timeout=15):
        return subprocess.run(['adb', '-s', 'RMX2072-M1', 'shell', command],
            capture_output=True, timeout=timeout)

    def text(result):
        return (result.stdout+result.stderr).decode('utf-8', errors='replace').replace('\r', '')

    def boot():
        result = shell('cat /proc/sys/kernel/random/boot_id')
        if result.returncode or text(result).strip() != a.boot_id:
            raise ValueError('Phone is not on the requested GSI boot')

    boot()
    recorded = json.loads((a.record/'inputs.json').read_text())
    from gsi_adb_accept import inspect
    # The device witness contains the boot UUID and UFS graph, not a trial name.
    # Match it to this record's captured USB handoff and authenticated ADB state.
    inspect(a.record/'live', a.boot_id)
    for kind in ('service', 'client'):
        name = '/bin/hw/rmx-keymaster-info-'+kind
        actual = text(shell('sha256sum /vendor'+name)).split()
        if not actual or actual[0] != pins[name]:
            raise ValueError('Source Keymaster binary differs: '+name)
    checks = {}
    for name, command, timeout in (
        ('identity', 'id; getenforce; cat /proc/sys/kernel/random/boot_id; ls -lZ /dev/rmx2072_keymaster', 15),
        ('hardware-info', '/vendor/bin/hw/rmx-keymaster-info-client', 30),
        ('aes', '/vendor/bin/hw/rmx-keymaster-info-client --aes-selftest', 90),
        ('services', 'service check android.security.maintenance; getprop init.svc.vendor.rmx-keymaster; getprop sys.boot_completed', 15),
        ('logcat', 'logcat -b all -d -s RMXKeymaster:V', 15)):
        boot()
        try:
            result = shell(command, timeout)
            data = text(result)
            rc = result.returncode
        except subprocess.TimeoutExpired as error:
            data = ((error.stdout or b'')+(error.stderr or b'')).decode('utf-8', errors='replace')
            rc = None
        path = output/(name+'.txt')
        path.write_text(data, encoding='utf-8')
        checks[name] = dict(returncode=rc, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if name == 'aes':
            checks[name]['roundtrip_and_tamper_rejection'] = bool(rc == 0 and
                'aes_import status=0 ' in data and 'aes_delete pass=1' in data and
                re.search(r'aes_decrypt tampered=0 status=0 output=51 match=1', data) and
                re.search(r'aes_decrypt tampered=1 status=-30 output=0 match=0', data))
            print(data, end='', flush=True)
    boot()
    report = dict(boot_id=a.boot_id, trial=recorded['trial'], checks=checks,
        passed=checks['hardware-info']['returncode'] == 0 and
               checks['aes']['roundtrip_and_tamper_rejection'],
        pins_sha256=hashlib.sha256(pins_path.read_bytes()).hexdigest(),
        scope='Temporary no-auth AES-GCM import/update/finish/decrypt/tamper/delete via source HIDL HAL; not full Keymaster or desktop acceptance')
    (output/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(passed=report['passed'], boot_id=a.boot_id)))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
