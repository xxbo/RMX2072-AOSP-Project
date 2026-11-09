#!/usr/bin/env python3
"""Request EDL from the RMX2072 RAM diagnostic shell, or observe its return timer."""
import argparse
import json
import pathlib
import re
import time

ACM = (0x1d6b, 0x0104)
EDL = (0x05c6, 0x9008)
BEGIN, END = b'RMX_EDL_BEGIN', b'RMX_EDL_END'
# Split the markers so echoed terminal input cannot qualify as a reply.
QUERY = (b"\nprintf '\\nRMX_EDL_''BEGIN\\n'; uname -r; cat /trial-id; "
         b"od -An -tx1 /sys/firmware/devicetree/base/oplus,dtsi_no; "
         b"cat /sys/class/udc/*/state; cat /proc/uptime /control-return-seconds; "
         b"printf '\\nRMX_EDL_''END\\n'\n")


def parse_identity(raw):
    lines = bytes(raw).replace(b'\r', b'').splitlines()
    start = lines.index(BEGIN)
    stop = lines.index(END, start + 1)
    kernel, trial, board, udc, uptime, timer = (s.strip().decode('ascii')
        for s in lines[start + 1:stop] if s.strip())
    if (not kernel.startswith('6.18.') or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', trial)
            or board.split() != ['00', '00', '50', '7f'] or udc != 'configured'):
        raise ValueError('Unexpected board, kernel, trial ID or UDC')
    return dict(kernel=kernel, trial=trial, udc=udc, uptime_seconds=float(uptime.split()[0]),
                timer_seconds=int(timer))


def ports_with_id(ports, ids):
    return [p for p in ports if (p.vid, p.pid) == ids]


def observe(args, report):
    import serial
    from serial.tools import list_ports

    initial = list(list_ports.comports())
    acm = ports_with_id(initial, ACM)
    if len(acm) != 1 or ports_with_id(initial, EDL):
        raise ValueError('Expected one diagnostic ACM and no pre-existing Qualcomm 9008 on this host')
    port = acm[0]
    report['acm_port'] = port.device
    with serial.Serial(port.device, 115200, timeout=0.25, write_timeout=3) as console:
        console.write(QUERY)
        data = bytearray()
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            data.extend(console.read(8192))
            if END in data.replace(b'\r', b'').splitlines():
                break
        report['identity'] = identity = parse_identity(data)
        if args.trial and identity['trial'] != args.trial:
            raise ValueError(f"Expected trial {args.trial}, received {identity['trial']}")
        if args.mode == 'command':
            if identity['timer_seconds'] - identity['uptime_seconds'] <= 10:
                raise ValueError('Too close to the timer deadline for an independent command test')
            console.write(b'/bin/reboot-edl edl\n')
            report['command_sent'] = True

    timeout = args.timeout
    if timeout is None:
        timeout = 90 if args.mode == 'command' else max(0, identity['timer_seconds'] - identity['uptime_seconds']) + 90
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        ports = list(list_ports.comports())
        edl = ports_with_id(ports, EDL)
        if len(edl) > 1:
            raise ValueError('Multiple new Qualcomm 9008 ports')
        if edl and not ports_with_id(ports, ACM):
            report.update(edl_port=edl[0].device, edl_vid_pid='05c6:9008',
                          host_wait_seconds=round(time.monotonic() - start, 3))
            return
        time.sleep(0.25)
    raise TimeoutError('Diagnostic ACM did not transition to Qualcomm 9008 within the timeout')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('command', 'timer'), required=True)
    parser.add_argument('--trial', help='Require this ramdisk trial ID')
    parser.add_argument('--timeout', type=int, help='Override the wait inferred from the ramdisk timer')
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    if args.timeout is not None and args.timeout <= 0:
        parser.error('Timeout must be positive')
    report = dict(mode=args.mode, command_sent=False, status='failed')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as out:
        try:
            observe(args, report)
            report['status'] = 'enumerated'
        except Exception as exc:
            report['error'] = str(exc)
            raise
        finally:
            json.dump(report, out, indent=2)
            out.write('\n')
            print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
