#!/usr/bin/env python3
"""Probe uncapped ACM bursts and preserve Windows serial error flags, if any."""
import argparse
import ctypes
import json
import pathlib
import time
from usb_diag_soak import command, parse_sample


def main():
    import serial
    from serial.tools import list_ports
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port')
    p.add_argument('--output', required=True, type=pathlib.Path)
    a = p.parse_args()
    repo = pathlib.Path(__file__).resolve().parents[2]
    if a.output.resolve() == repo or repo in a.output.resolve().parents:
        p.error('Raw logs stay outside checkout')
    ports = [a.port] if a.port else [x.device for x in list_ports.comports()
                                    if (x.vid, x.pid) == (0x1d6b, 0x0104)]
    if len(ports) != 1:
        raise SystemExit('Expected one diagnostic ACM port')
    a.output.mkdir(parents=True, exist_ok=False)
    events, samples, failures = [], [], []
    original, backend = None, None
    # pyserial otherwise clears these flags before each Windows ReadFile call
    # without preserving them. Observe them; do not alter the returned flags.
    if hasattr(serial, 'win32'):
        backend = serial.win32
        original = backend.ClearCommError
        def observe(handle, flags, stat):
            result = original(handle, flags, stat)
            if result and flags:
                value = ctypes.cast(flags, ctypes.POINTER(backend.DWORD)).contents.value
                if value:
                    events.append(dict(host_monotonic=time.monotonic(), flags=value,
                                       rx_overflow=bool(value & backend.CE_RXOVER),
                                       character_overrun=bool(value & backend.CE_OVERRUN)))
            return result
        backend.ClearCommError = observe
    def capture(console, index, size):
        console.write(command(index, size, 0).encode())
        data, end = bytearray(), time.monotonic()+12
        marker = ('\nSOAK_END_'+str(index)+'\n').encode()
        while time.monotonic() < end:
            data.extend(console.read(65536))
            if marker in bytes(data).replace(b'\r', b''):
                break
        (a.output/('sample-%02d.txt' % index)).write_bytes(data)
        return parse_sample(bytes(data), index, size)
    try:
        with serial.Serial(ports[0], 115200, timeout=0.2, write_timeout=5) as console:
            if hasattr(console, 'set_buffer_size'):
                console.set_buffer_size(rx_size=4*1024*1024, tx_size=65536)
            console.write(b'\n')
            samples.append(capture(console, 0, 64))
            for index in range(1, 7):
                try:
                    samples.append(capture(console, index, 262144))
                except Exception as exc:
                    failures.append(dict(sample=index, error=str(exc)))
                    break
            try:
                samples.append(capture(console, 99, 64))
            except Exception as exc:
                failures.append(dict(sample=99, error=str(exc)))
    finally:
        if original:
            backend.ClearCommError = original
        report = dict(valid_samples=samples, failures=failures, windows_error_events=events,
                      host_rx_overflow_reported=any(e['rx_overflow'] for e in events),
                      qualification='Missing flags do not exclude host loss; no exact cause inferred from short data alone')
        (a.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(dict(valid_samples=len(samples), failures=failures,
                              windows_error_events=events)), flush=True)


if __name__ == '__main__':
    main()
