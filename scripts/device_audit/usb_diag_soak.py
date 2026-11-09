#!/usr/bin/env python3
"""Verify one live kernel boot and repeated RAM-only USB transfers over time."""
import argparse
import base64
import hashlib
import json
import pathlib
import re
import time


def command(index, size):
    # Split literal marker text so echoed input cannot impersonate a response.
    def marker(name):
        return "printf '\\nSOAK_''"+name+'_'+str(index)+"\\n'"
    return '; '.join([marker('BEGIN'), 'uname -r', 'cat /proc/uptime',
                     'cat /proc/sys/kernel/random/boot_id', 'cat /sys/class/udc/*/state',
                     marker('DATA'), 'head -c '+str(size)+' /dev/zero | base64',
                     marker('DATA_END'), marker('END')])+'\n'


def parse_sample(data, index, size):
    text = data.replace(b'\r', b'').decode('ascii', errors='replace')
    begin, end = 'SOAK_BEGIN_'+str(index), 'SOAK_END_'+str(index)
    lines = text.splitlines()
    start, stop = lines.index(begin), lines.index(end)
    body = lines[start+1:stop]
    ds, de = body.index('SOAK_DATA_'+str(index)), body.index('SOAK_DATA_END_'+str(index))
    header = [line.strip() for line in body[:ds] if line.strip()]
    if len(header) != 4 or not header[0].startswith('6.18.') or header[3] != 'configured':
        raise ValueError('Expected 6.18 uname, uptime, boot ID and configured UDC')
    if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', header[2]):
        raise ValueError('Invalid boot ID')
    uptime = float(header[1].split()[0])
    decoded = base64.b64decode(''.join(body[ds+1:de]), validate=True)
    if len(decoded) != size or any(decoded):
        raise ValueError('RAM transfer length/content mismatch')
    return dict(kernel=header[0], uptime_seconds=uptime,
                boot_id_sha256=hashlib.sha256(header[2].encode()).hexdigest(),
                udc_state=header[3], transfer_bytes=len(decoded),
                transfer_sha256=hashlib.sha256(decoded).hexdigest())


def main():
    import serial
    from serial.tools import list_ports
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port')
    p.add_argument('--output', required=True, type=pathlib.Path)
    p.add_argument('--duration', type=int, default=600)
    p.add_argument('--interval', type=int, default=30)
    p.add_argument('--bytes-per-sample', type=int, default=65536)
    a = p.parse_args()
    if not 30 <= a.duration <= 900 or not 5 <= a.interval <= 60 or not 1 <= a.bytes_per_sample <= 1048576:
        p.error('Duration 30..900, interval 5..60, transfer 1..1048576 bytes required')
    repo = pathlib.Path(__file__).resolve().parents[2]
    if a.output.resolve() == repo or repo in a.output.resolve().parents:
        p.error('Raw runtime data must remain outside checkout')
    port = a.port
    if not port:
        matches = [p.device for p in list_ports.comports() if (p.vid, p.pid) == (0x1d6b, 0x0104)]
        if len(matches) != 1:
            raise SystemExit('Expected one diagnostic ACM port')
        port = matches[0]
    a.output.mkdir(parents=True, exist_ok=False)
    samples, status, error = [], 'running', None
    started = time.monotonic()
    try:
        with serial.Serial(port, 115200, timeout=0.2, write_timeout=5) as console:
            index = 0
            console.write(b'\n')
            while time.monotonic()-started < a.duration+60:
                console.write(command(index, a.bytes_per_sample).encode())
                data, deadline = bytearray(), time.monotonic()+25
                marker = ('\nSOAK_END_'+str(index)+'\n').encode()
                with (a.output/('sample-%03d.txt' % index)).open('xb') as raw:
                    while time.monotonic() < deadline:
                        chunk = console.read(65536)
                        raw.write(chunk)
                        data.extend(chunk)
                        if marker in bytes(data).replace(b'\r', b''):
                            break
                    else:
                        raise TimeoutError('USB response deadline exceeded')
                sample = parse_sample(bytes(data), index, a.bytes_per_sample)
                if samples and (sample['boot_id_sha256'] != samples[0]['boot_id_sha256'] or
                                sample['uptime_seconds'] <= samples[-1]['uptime_seconds']):
                    raise ValueError('Kernel reboot or nonmonotonic uptime detected')
                samples.append(sample)
                (a.output/'samples.json').write_text(json.dumps(samples, indent=2)+'\n')
                print(json.dumps(dict(sample=index, uptime=sample['uptime_seconds'],
                                      transfer_bytes=sample['transfer_bytes'], udc=sample['udc_state'])), flush=True)
                if sample['uptime_seconds']-samples[0]['uptime_seconds'] >= a.duration:
                    status = 'passed'
                    break
                index += 1
                time.sleep(a.interval)
            else:
                raise TimeoutError('Requested live-kernel duration not established')
    except Exception as exc:
        status, error = 'failed', str(exc)
    report = dict(status=status, error=error, samples=len(samples), requested_seconds=a.duration,
                  live_kernel_span_seconds=(samples[-1]['uptime_seconds']-samples[0]['uptime_seconds']) if samples else 0,
                  verified_transfer_bytes=sum(s['transfer_bytes'] for s in samples),
                  boot_id_constant=bool(samples) and len({s['boot_id_sha256'] for s in samples}) == 1,
                  scope='Read-only serial commands; data generated from /dev/zero; no block filesystems')
    (a.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)
    if status != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
