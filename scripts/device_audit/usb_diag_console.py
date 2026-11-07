#!/usr/bin/env python3
"""Collect a RAM-only diagnostic ACM console; commands only read runtime state."""
import argparse
import json
import pathlib
import re
import time
import serial
from serial.tools import list_ports

COMMANDS = [
    'echo RMX_DIAG_BEGIN', 'uname -a', 'cat /proc/uptime', 'cat /proc/cmdline',
    'cat /proc/mounts', 'cat /sys/devices/system/cpu/online',
    'cat /sys/class/udc/*/state',
    'cat /sys/class/watchdog/watchdog*/bootstatus',
    'cat /sys/class/watchdog/watchdog*/status',
    'dmesg', 'echo RMX_DIAG_END',
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port')
    parser.add_argument('--output', required=True, type=pathlib.Path)
    parser.add_argument('--timeout', type=float, default=30)
    args = parser.parse_args()
    repo = pathlib.Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    if output == repo or repo in output.parents:
        parser.error('Raw logs must remain outside the checkout')
    port = args.port
    if not port:
        matches = [p.device for p in list_ports.comports() if (p.vid, p.pid) == (0x1d6b, 0x0104)]
        if len(matches) != 1:
            raise SystemExit('Expected one RMX2072 diagnostic ACM port, found ' + str(len(matches)))
        port = matches[0]
    output.parent.mkdir(parents=True, exist_ok=True)
    captured = bytearray()
    complete = False
    # Save bytes even if the handset resets or unplugging raises SerialException.
    with output.open('xb') as destination:
        with serial.Serial(port, baudrate=115200, timeout=0.2, write_timeout=3) as console:
            console.write(b'\n')
            console.write(('; '.join(COMMANDS) + '\n').encode())
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline:
                data = console.read(65536)
                if data:
                    destination.write(data)
                    destination.flush()
                    captured.extend(data)
                    if re.search(rb'(?:^|[\r\n])RMX_DIAG_END\r?\n', captured):
                        complete = True
                        break
    text = bytes(captured).decode('utf-8', errors='replace')
    kernel = next((line.strip() for line in text.splitlines()
                   if re.match(r'^Linux\s+\S+\s+6\.18\.\S+', line.strip())), None)
    report = dict(probe_completed=complete, expected_kernel_line=kernel,
                  received_bytes=len(captured), commands=COMMANDS)
    output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'commands'}))
    if not complete or not kernel:
        raise SystemExit('Diagnostic 6.18 shell proof not established')


if __name__ == '__main__':
    main()
