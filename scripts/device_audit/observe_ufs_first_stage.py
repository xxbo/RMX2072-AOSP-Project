"""Start the UFS first-stage test and preserve its independent ACM transcript."""
import argparse
import json
from pathlib import Path
import time

from serial import Serial, SerialException
from serial.tools.list_ports import comports
from usb_edl_return import ACM, EDL, END, QUERY, parse_identity, ports_with_id
from serve_gsi_usb import read_until_line


def observe(trial, output, timeout):
    output.mkdir(parents=True, exist_ok=False)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ports = ports_with_id(comports(), ACM)
        if len(ports) > 1:
            raise RuntimeError('Multiple diagnostic ports attached')
        if ports:
            break
        time.sleep(.25)
    else:
        raise TimeoutError('Diagnostic ACM did not appear')
    with Serial(ports[0].device, 115200, timeout=.25, write_timeout=4) as console:
        console.write(QUERY)
        identity = parse_identity(read_until_line(console, END, 12))
        if identity['trial'] != trial:
            raise ValueError('Unexpected running trial')
        (output/'identity.json').write_text(json.dumps(identity, indent=2) + '\n')
        # Capture bootstrap failures too. A failed mount can stop PID 1 before
        # the witness observes a mount syscall, leaving the outer console alive.
        console.write(b"\nstty -echo; cat /proc/sys/kernel/random/boot_id; "
                      b"(cat /dev/kmsg | awk '/init:|libfs_mgr|libfstab|avb|verity|SELinux:|panic|enforcing=/{print;fflush()}' "
                      b"> /dev/ttyGS0) & "
                      b"/bin/busybox sh -x /bin/first-stage-mount ufs install "
                      b"> /run/gsi17-run.log 2>&1; x=$?; tail -80 /run/gsi17-run.log; "
                      b"echo UFS_STAGE_RC=$x; /bin/reboot-edl edl\n")
        deadline = time.monotonic() + identity['timer_seconds'] + 25
        with (output/'acm.log').open('xb') as capture:
            while time.monotonic() < deadline:
                try:
                    data = console.read(16384)
                except SerialException:
                    return
                if data:
                    capture.write(data)
                    capture.flush()
                elif ports_with_id(comports(), EDL):
                    return
            raise TimeoutError('No disconnect within the trial window')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wait', type=int, default=120)
    args = parser.parse_args()
    observe(args.trial, args.output, args.wait)
