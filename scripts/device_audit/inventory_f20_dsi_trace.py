"""Read-only F.20 DSI tracing capabilities; does not enable tracing or send DCS."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from capture_f20_display_baseline import shell


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    identity = shell('getprop ro.build.display.id; getprop sys.boot_completed; uname -r; cat /proc/sys/kernel/random/boot_id; id').splitlines()
    if identity[:3] != ['RMX2072_11_F.20', '1', '4.19.157-perf+'] or len(identity) != 5 or not identity[4].startswith('uid=0('):
        raise ValueError('Completed F.20 root shell required')
    args.output.mkdir(parents=True, exist_ok=False)
    queries = {
        'debug-mount-state': 'grep -E "debugfs|tracefs" /proc/mounts; ls -ld /sys/kernel/debug /d',
        'events': 'grep -Ei "dsi|dcs|sde.*(cmd|evtlog|dsc)|mdss.*(cmd|dsc)" /sys/kernel/tracing/available_events',
        'functions': 'grep -E "dsi_(ctrl_cmd|panel_tx|panel_update_pps|panel_send_pps|display_cmd|display_host|catalog|ctrl_hw).*|sde_hw_dsc" /sys/kernel/tracing/available_filter_functions',
        'dynamic-debug': 'grep -E "dsi_(ctrl|panel|display|host)\\.c" /sys/kernel/debug/dynamic_debug/control',
        'dri-interface-names': 'find /sys/kernel/debug/dri -maxdepth 4 -type f',
        'vendor-interface-names': 'ls /sys/kernel/oplus_display',
        'vendor-log-state': 'cat /sys/kernel/oplus_display/dsi_cmd_log_switch',
        'tracer-state': 'cat /sys/kernel/tracing/current_tracer /sys/kernel/tracing/tracing_on; ls /sys/kernel/tracing/instances; ls -l /sys/kernel/tracing/kprobe_events',
        'display-event-formats': 'for f in /sys/kernel/tracing/events/dsi/*/format /sys/kernel/tracing/events/sde/sde_evtlog/format; do if [ -f "$f" ]; then echo FILE=$f; cat "$f"; fi; done',
    }
    results = {}
    for name, command in queries.items():
        try:
            # Some stock su/ADB combinations hide the command exit status.
            # Keep an explicit remote status rather than treating tool exit 0
            # as evidence that an unavailable tracing interface was read.
            value = shell('{ ' + command + '; }; rmx_status=$?; printf "\\nRMX_REMOTE_STATUS=%s\\n" "$rmx_status"', 30)
            value, marker, status_text = value.rpartition('\nRMX_REMOTE_STATUS=')
            if not marker:
                raise ValueError('Missing remote status marker for ' + name)
            status = int(status_text.strip())
        except subprocess.CalledProcessError as error:
            value = error.output.decode('utf-8', errors='replace')
            status = error.returncode
        raw = value.encode('utf-8')
        (args.output / (name + '.txt')).write_bytes(raw)
        results[name] = dict(command=command, exit_status=status, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        print(name, status, len(raw), flush=True)
    if shell('cat /proc/sys/kernel/random/boot_id').strip() != identity[3]:
        raise ValueError('F.20 boot changed during inventory')
    (args.output / 'inventory.json').write_text(json.dumps(dict(
        utc=datetime.now(timezone.utc).isoformat(), firmware=identity[0], kernel=identity[2],
        boot_id=identity[3], results=results,
        scope='Read-only interface names, trace formats and source-location inventory. No tracing writes, DCS commands, register access, display cycle, reboot or partition readback.'
    ), indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
