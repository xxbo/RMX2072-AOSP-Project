"""Capture one USB-backed GSI trial and request the verified software return to EDL."""
import argparse
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--trial', required=True)
    parser.add_argument('--output', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    for name in ('userspace', 'combined', 'first-stage'):
        mode.add_argument('--'+name, action='store_true')
    mode.add_argument('--project-vendor-report', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Select a new capture directory')
    if not args.image.is_file() or (args.project_vendor_report and not args.project_vendor_report.is_file()):
        parser.error('Missing source image or vendor report')
    scripts = Path(__file__).resolve().parent
    command = [sys.executable, scripts/'serve_gsi_usb.py', '--image', args.image,
               '--trial', args.trial, '--output', args.output]
    if args.project_vendor_report:
        command += ['--project-vendor-report', args.project_vendor_report]
    for name in ('userspace', 'combined', 'first-stage'):
        if getattr(args, name.replace('-', '_')):
            command.append('--'+name)
    capture = subprocess.run(command)
    if capture.returncode:
        # Preserve the original window for examining a failed capture before recovery.
        log = args.output/'mount.txt'
        if log.is_file():
            print(log.read_text(encoding='utf-8')[-2200:], flush=True)
        deadline = time.monotonic()+45
        while time.monotonic() < deadline and not (args.output/'return-now').exists():
            time.sleep(.3)
    recovery = subprocess.run([sys.executable, scripts/'usb_edl_return.py', '--mode', 'command',
                               '--trial', args.trial, '--timeout', '55', '--output', args.output/'return.json'])
    return recovery.returncode or capture.returncode


if __name__ == '__main__':
    sys.exit(main())
