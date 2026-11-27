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


def kernel_discovery(events):
    # Exact enumerated device identities, not DT nodes or a driver filename.
    return dict(pci_root_port_reported=bool(re.search(
                    r'pci \S+: \[17cb:010b\]', events)),
                qca6390_reported=bool(re.search(
                    r'pci \S+: \[17cb:1101\]', events)),
                link_down_reported='Phy link never came up' in events,
                digital_rail_registration_failed=bool(re.search(
                    r'wlan-digital-regulators: smps2: devm_regulator_register\(\) failed', events)))


def firmware_discovery(events):
    """Separate MHI setup from a real QMI reply and unqualified board identity."""
    targets = []
    for values in re.findall(r'ath11k_pci [^\n]+: chip_id (0x[0-9a-f]+) '
            r'chip_family (0x[0-9a-f]+) board_id (0x[0-9a-f]+) soc_id (0x[0-9a-f]+)', events, re.I):
        row = dict(zip(('chip_id', 'chip_family', 'board_id', 'soc_id'),
                       (int(value, 16) for value in values)))
        # ath11k assigns 0xff when board_info_valid is absent. The normal log
        # does not emit the validity bit; an explicit 0xff response is also
        # possible. Do not label this value as a proven board/calibration ID.
        row['board_id_may_be_default'] = row['board_id'] == 0xff
        if row not in targets:
            targets.append(row)
    versions = []
    for version, timestamp, build_id in re.findall(
            r'ath11k_pci [^\n]+: fw_version (0x[0-9a-f]+) '
            r'fw_build_timestamp ([^\n]+?) fw_build_id([^\n]*)', events, re.I):
        row = dict(version=version.lower(), timestamp=timestamp.strip(), build_id=build_id.strip())
        if row not in versions:
            versions.append(row)
    return dict(
        mhi_setup_reported=bool(re.search(r'mhi \S+: Power on setup success', events)),
        qmi_target_response_observed=bool(targets), target_info=targets, firmware_versions=versions,
        amss_missing=bool(re.search(r'Direct firmware load for ath11k/QCA6390/hw2.0/amss\.bin failed with error -2\b', events)),
        board_data_missing=bool(re.search(r'ath11k_pci [^\n]+: (?:qmi failed to fetch board file|failed to load board data file): -2\b', events)),
        mhi_start_errors=sorted(set(int(code) for code in re.findall(
            r'ath11k_pci [^\n]+: failed to (?:power up|start) mhi: (-?\d+)', events))),
        regulatory_db_missing=bool(re.search(r'Direct firmware load for regulatory\.db failed with error -2\b', events)),
        board_compatibility_verified=False,
        scope='Observed boot messages only; QMI response is not board-data, WLAN interface or RF acceptance')


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
    # boot-events is the supervisor event stream, not the full kernel log.
    # Early regulator/PCI failures are in the same-boot diagnostic ACM stream.
    logs = {name: a.record / 'live' / name for name in ('boot-events.txt', 'acm.log')}
    streams = {name: path.read_text(encoding='utf-8', errors='replace')
               for name, path in logs.items()}
    for name, stream in streams.items():
        if expected not in stream:
            raise ValueError('Missing expected boot identity in ' + name)
    events = '\n'.join(streams.values())
    captures['kernel-wlan'] = '\n'.join(line for line in events.splitlines()
        if re.search(r'\bpci\b|pcie|\bmhi\b|pwrseq|ath11k|qca6390|wcn|wlan|pm8009|smpf2|qrtr|firmware|defer', line, re.I)) + '\n'
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
                  kernel_discovery=kernel_discovery(events),
                  firmware_discovery=firmware_discovery(events),
                  files=hashes, kernel_log_sha256={name: hashlib.sha256(path.read_bytes()).hexdigest()
                                                 for name, path in logs.items()},
                  scan='NOT RUN', association='NOT RUN', dhcp='NOT RUN', traffic='NOT RUN',
                  scope='Discovery only; no RF enable, credentials or network configuration changes')
    if result['kernel_discovery']['qca6390_reported']:
        result['qca6390_enumerated'] = True
    (a.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
