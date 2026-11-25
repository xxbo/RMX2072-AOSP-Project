"""Record native WLAN discovery on the exact retained boot, without RF changes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def discovery(pci, network):
    endpoint = bool(re.search(r'PCI=[^\n]+\n0x17cb\n0x1101\n', pci))
    wlan = bool(re.search(r'^\d+: wlan\d+[:@]', network, re.M))
    denied = r'Permission denied|Operation not permitted'
    return dict(qca6390_enumerated=True if endpoint else
                None if re.search(denied, pci, re.I) else False,
                wlan_netdev=True if wlan else
                None if re.search(denied, network, re.I) else False,
                discovery_read_errors=bool(re.search(denied, pci + network, re.I)))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adb', default='adb')
    p.add_argument('--record', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    expected = json.loads((a.record / 'live/gsi-stable.json').read_text())['identity'][2]
    a.output.mkdir(parents=True, exist_ok=False)

    def shell(command):
        r = subprocess.run([a.adb, '-s', 'RMX2072-M1', 'shell', '( ' + command + ' ) 2>&1'],
                           capture_output=True, timeout=30)
        if r.returncode:
            raise RuntimeError(r.stderr.decode('utf-8', 'replace'))
        return r.stdout.decode('utf-8', 'replace').replace('\r', '')

    def identity():
        return shell('cat /proc/sys/kernel/random/boot_id; getenforce; '
                     'getprop vendor.rmx.m1.state; getprop sys.boot_completed').splitlines()

    before = identity()
    if before != [expected, 'Enforcing', 'retained', '1']:
        raise ValueError('Not the expected retained GSI boot')
    commands = {
        'pci': 'ls -ld /sys/bus/pci/devices; ls -l /sys/bus/pci/devices; '
               'for d in /sys/bus/pci/devices/*; do [ -d "$d" ] || continue; '
               'echo "PCI=$d"; cat "$d/vendor" "$d/device" "$d/subsystem_vendor" '
               '"$d/subsystem_device"; readlink -f "$d/driver"; done; true',
        'network': 'ip -details link; ls -l /sys/class/ieee80211 2>&1; true',
        'wifi-status': 'cmd wifi status',
        'wifi-service': 'dumpsys wifi',
        'battery': 'dumpsys battery',
    }
    captures = {name: shell(command) for name, command in commands.items()}
    boot = a.record / 'live/boot-events.txt'
    events = boot.read_text(encoding='utf-8', errors='replace')
    captures['kernel-wlan'] = '\n'.join(line for line in events.splitlines()
        if re.search(r'pcie|ath11k|qca6390|wcn|wlan|pm8009|smpf2|qrtr|firmware|defer', line, re.I)) + '\n'
    after = identity()
    if after != before:
        raise ValueError('Device changed identity during capture')
    hashes = {}
    for name, text in captures.items():
        path = a.output / (name + '.txt')
        path.write_text(text, encoding='utf-8')
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    result = dict(boot_id=expected, same_boot=True, enforcing=True,
                  **discovery(captures['pci'], captures['network']),
                  files=hashes, kernel_log_sha256=hashlib.sha256(boot.read_bytes()).hexdigest(),
                  scan='NOT RUN', association='NOT RUN', dhcp='NOT RUN', traffic='NOT RUN',
                  scope='Discovery only; no RF enable, credentials or network configuration changes')
    (a.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
