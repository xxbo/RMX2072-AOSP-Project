"""Collect the fixed graphics-group capture from a matching, accepted GSI boot.

No service restart, property write, policy change or device reboot. An optional
reference compares decoded pixels, not PNG encodings or physical scanout.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from PIL import Image, ImageChops


def shell(command):
    return subprocess.check_output(
        ['adb', '-s', 'RMX2072-M1', 'shell', command],
        timeout=10, stderr=subprocess.STDOUT).decode().replace('\r', '')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--reference', type=Path)
    args = parser.parse_args()
    live = args.record.resolve() / 'live'
    accepted = json.loads((live / 'gsi-accepted.json').read_text(encoding='utf-8'))
    boot = accepted['identity'][2]
    end = time.monotonic() + 120
    while time.monotonic() < end:
        if shell('cat /proc/sys/kernel/random/boot_id').strip() != boot:
            raise ValueError('Boot changed before frame collection')
        status = shell('cat /data/local/tmp/rmx-m3-capture.txt')
        if not status.startswith(boot + '\n'):
            raise ValueError('Capture belongs to another boot')
        size = re.search(r'^(\d+) /data/local/tmp/rmx-m3-frame.png$', status, re.M)
        exit_code = re.search(r'^capture_exit=(\d+)$', status, re.M)
        if size and exit_code:
            break
        time.sleep(2)
    else:
        raise TimeoutError('Fixed capture did not finish in the collection window')
    (live / 'capture-status.txt').write_text(status, encoding='utf-8')
    if exit_code[1] != '0':
        raise ValueError('Fixed capture failed: ' + exit_code[1])
    target = live / 'android-frame.png'
    subprocess.run(['adb', '-s', 'RMX2072-M1', 'pull',
                    '/data/local/tmp/rmx-m3-frame.png', str(target)],
                   capture_output=True, timeout=30, check=True)
    if shell('cat /proc/sys/kernel/random/boot_id').strip() != boot:
        raise ValueError('Boot changed during frame collection')
    raw = target.read_bytes()
    if len(raw) != int(size[1]):
        raise ValueError('PNG size changed during collection')
    with Image.open(target) as image:
        image.load()
        pixels = image.convert('RGBA')
        result = dict(boot_id=boot, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                      size=image.size, mode=image.mode, colors=pixels.getcolors(32),
                      scope='CPU RenderEngine screenshot, not DPU readback or physical acceptance')
    uptimes = re.findall(r'^(\d+\.\d+) \d+\.\d+$', status, re.M)
    if len(uptimes) == 2:
        result['capture_seconds'] = round(float(uptimes[1]) - float(uptimes[0]), 2)
    if args.reference:
        with Image.open(args.reference) as reference:
            reference.load()
            if reference.size != pixels.size:
                raise ValueError('Reference dimensions do not match captured image')
            diff = ImageChops.difference(pixels, reference.convert('RGBA'))
        maximum = max(high for low, high in diff.getextrema())
        result['reference'] = dict(sha256=hashlib.sha256(args.reference.read_bytes()).hexdigest(),
                                   maximum_channel_error=maximum, exact=maximum == 0,
                                   all_pixels_within_one=maximum <= 1)
    (live / 'decoded-frame.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
