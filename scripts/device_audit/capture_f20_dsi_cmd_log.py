"""Bounded F.20 display-only sleep/wake with the vendor DSI logger restored."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex

from capture_f20_display_baseline import shell


def checked(command, timeout=30):
    value = shell('{ ' + command + '; }; rmx_status=$?; '
                  'printf "\\nRMX_REMOTE_STATUS=%s\\n" "$rmx_status"', timeout)
    value, marker, status = value.rpartition('\nRMX_REMOTE_STATUS=')
    if not marker or status.strip() != '0':
        raise RuntimeError('Remote command failed: ' + value[-1000:])
    return value


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--refresh60', action='store_true', help='Temporarily request 60 Hz, restoring the previous setting')
    a = p.parse_args()
    node = '/sys/kernel/oplus_display/dsi_cmd_log_switch'
    identity = checked('getprop ro.build.display.id; getprop sys.boot_completed; '
                       'uname -r; cat /proc/sys/kernel/random/boot_id; id').splitlines()
    if identity[:3] != ['RMX2072_11_F.20', '1', '4.19.157-perf+'] or not identity[-1].startswith('uid=0('):
        raise ValueError('Completed F.20 root shell required')
    saved = checked('cat ' + node).strip()
    power = checked('cat /sys/kernel/oplus_display/power_status').strip()
    if saved not in ('0', '1') or power != '2':
        raise ValueError('Expected readable logger flag and powered-on display')
    refresh = checked('settings get system peak_refresh_rate').strip()
    if a.refresh60 and refresh not in ('60.0', '60.000004', '90.0'):
        raise ValueError('Unexpected peak_refresh_rate: ' + repr(refresh))
    a.output.mkdir(parents=True, exist_ok=False)
    token = 'RMX_DSI_LOG_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    results = {}

    def save(name, value):
        raw = value.encode('utf-8')
        (a.output / (name + '.txt')).write_bytes(raw)
        results[name] = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())

    save('kernel-debug-config', checked('zcat /proc/config.gz | grep -E '
         + shlex.quote('CONFIG_(DEBUG_FS|DEVMEM|PROC_KCORE|KPROBES|FUNCTION_TRACER|DYNAMIC_DEBUG)')))
    # The trap lives on the phone, so normal shell exit or HUP restores the
    # logger even if the local process stops. Python finally retries restoration.
    script = '\n'.join([
        'set -e',
        'cleanup() { echo ' + saved + ' > ' + node + '; input keyevent 224; '
        + ('settings put system peak_refresh_rate ' + shlex.quote(refresh) + '; ' if a.refresh60 else '') + '}',
        'trap cleanup EXIT', 'trap "exit 1" HUP INT TERM',
        # Stock toybox printf writes one byte per write(2); echo emits one
        # record, so the kernel marker is not fragmented into characters.
        'echo "<6>' + token + ' BEGIN" > /dev/kmsg',
        'echo 1 > ' + node,
        'test "$(cat ' + node + ')" = 1',
        *(['settings put system peak_refresh_rate 60.0', 'sleep 2'] if a.refresh60 else []),
        'input keyevent 223', 'sleep 2',
        'echo "<6>' + token + ' SLEEP power=$(cat /sys/kernel/oplus_display/power_status)" > /dev/kmsg',
        'input keyevent 224', 'sleep 4',
        'echo "<6>' + token + ' WAKE power=$(cat /sys/kernel/oplus_display/power_status)" > /dev/kmsg',
        'echo "<6>' + token + ' END" > /dev/kmsg',
    ])
    try:
        save('cycle-command', checked('sh -c ' + shlex.quote(script), 40))
    finally:
        checked('echo ' + saved + ' > ' + node + '; input keyevent 224'
                + ('; settings put system peak_refresh_rate ' + shlex.quote(refresh) if a.refresh60 else ''))
        restored = checked('cat ' + node).strip()
        if restored != saved:
            raise RuntimeError('Logger restoration failed')
    after = checked('dmesg', 30)
    save('kernel-after', after)
    lines = after.splitlines()
    start = next(i for i, line in enumerate(lines) if token + ' BEGIN' in line)
    end = next(i for i, line in enumerate(lines) if token + ' END' in line)
    bounded = lines[start:end + 1]
    save('bounded-kernel-log', '\n'.join(bounded) + '\n')
    selected = [line for line in bounded if re.search(r'dsi|dcs|panel|sde|mdss|rmx_dsi', line, re.I)]
    save('display-log', '\n'.join(selected) + '\n')
    after_id = checked('cat /proc/sys/kernel/random/boot_id').strip()
    after_power = checked('cat /sys/kernel/oplus_display/power_status').strip()
    after_refresh = checked('settings get system peak_refresh_rate').strip()
    if after_id != identity[3] or after_power != '2':
        raise RuntimeError('Boot or final display power state changed unexpectedly')
    if a.refresh60 and after_refresh != refresh:
        raise RuntimeError('Refresh setting was not restored')
    receipt = dict(utc=datetime.now(timezone.utc).isoformat(), firmware=identity[0], kernel=identity[2],
                   boot_id=identity[3], original_logger=saved, restored_logger=restored,
                   original_power=power, final_power=after_power, marker=token,
                   requested_refresh60=a.refresh60, original_peak_refresh_rate=refresh,
                   restored_peak_refresh_rate=after_refresh,
                   bounded_lines=len(bounded), display_lines=len(selected), results=results,
                   scope='One display-only sleep/wake with vendor DSI logger, optionally requesting 60 Hz. Logger and peak refresh setting restored. No phone restart, host-register writes or partition readback. Active mode requires kernel log evidence; raw logs stay local pending review.')
    (a.output / 'capture.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2), flush=True)


if __name__ == '__main__':
    main()
