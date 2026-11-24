"""Start the UFS first-stage test and preserve its independent ACM transcript."""
import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import subprocess
import threading
import time
from uuid import UUID

from serial import Serial, SerialException
from serial.tools.list_ports import comports
from usb_edl_return import ACM, EDL, END, QUERY, parse_identity, ports_with_id
from serve_gsi_usb import console_query, read_console_file, read_until_line


def mark(output, event, boot_id):
    with (output/'host-events.jsonl').open('a') as log:
        log.write(json.dumps(dict(event=event, boot_id=str(boot_id), monotonic=time.monotonic(),
                                  utc=datetime.now(timezone.utc).isoformat()))+'\n')


def handoff_diagnostic_command(boot_id):
    """Bounded, read-only evidence from a stalled pre-Android display handoff."""
    boot = str(UUID(str(boot_id)))
    return (f'\nif [ "$(cat /proc/sys/kernel/random/boot_id)" = "{boot}" ] '
            '&& [ -r /run/m3-display.txt ]; then\n'
            "printf '\\nM3HANDOFF_DIAG begin\\n'\n"
            "grep -E 'DRMTEST|DRMPATTERN|DRMSNAPSHOT' /run/m3-display.txt | tail -40\n"
            'tail -120 /run/m3-display.txt\n'
            'tail -60 /run/gsi17-run.log\n'
            'ps\n'
            'count=0\n'
            'for task in /proc/[0-9]*; do\n'
            ' [ "$count" -lt 20 ] || break\n'
            ' name=$(cat "$task/comm" 2>/dev/null)\n'
            ' state=$(sed -n "s/^State:[[:space:]]*//p" "$task/status" 2>/dev/null)\n'
            ' case "$state:$name" in D*|*:drm-panel-smoke|*:cat|*:sh|*:timeout)\n'
            '  echo "M3TASK path=$task name=$name state=$state"\n'
            '  cat "$task/wchan" "$task/stack" 2>/dev/null\n'
            '  count=$((count+1));;\n'
            ' esac\n'
            'done\n'
            "printf '\\nM3HANDOFF_DIAG end\\n'\nfi\n").encode()


def watch_adb(output, stop, retain=False, autonomous=False):
    """Record transport states, including offline and unauthorized, throughout the trial."""
    start = time.monotonic()
    previous = None
    accepted = False
    last_attempt = 0
    with (output/'adb.jsonl').open('x') as log:
        while not stop.is_set():
            try:
                listing = subprocess.check_output(['adb', 'devices', '-l'], timeout=3, text=True)
                rows = [s.strip() for s in listing.splitlines() if s.strip() and
                        not s.startswith('List of devices attached')]
                ports = [(p.vid, p.pid) for p in comports() if (p.vid, p.pid) in (ACM, EDL)]
                state = dict(transports=rows, diagnostic_acm=ACM in ports, edl=EDL in ports)
            except (OSError, subprocess.SubprocessError) as error:
                state = dict(error=str(error))
            entry = dict(elapsed=round(time.monotonic()-start, 3), monotonic=time.monotonic(), **state)
            if state != previous:
                for row in state.get('transports', []):
                    fields = row.split()
                    if len(fields) >= 2 and fields[1] == 'device':
                        try:
                            data = subprocess.check_output(['adb', '-s', fields[0], 'shell',
                                'getprop ro.product.model; getprop ro.build.version.sdk; '
                                'getprop init.svc.adbd; uname -r; cat /proc/sys/kernel/random/boot_id'],
                                text=True, timeout=3)
                            entry.setdefault('identity', {})[fields[0]] = data.splitlines()
                        except (OSError, subprocess.SubprocessError) as error:
                            entry['identity_error'] = str(error)
            if retain and not accepted and time.monotonic()-last_attempt > 3 and (autonomous or (output/'host-events.jsonl').exists()):
                last_attempt = time.monotonic()
                try:
                    from gsi_adb_accept import accept, fetch_autonomous
                    if any(row.startswith('RMX2072-M1') and row.split()[1]=='device' for row in state.get('transports', [])):
                        if autonomous: original=fetch_autonomous(output)
                        else:
                            events = [json.loads(x) for x in (output/'host-events.jsonl').read_text().splitlines()]
                            original = next(x['boot_id'] for x in events if x['event']=='handoff_requested')
                        accept(output, original); accepted=True
                except (OSError, subprocess.SubprocessError, ValueError, StopIteration) as error:
                    entry['accept_error'] = str(error)
            previous = state
            log.write(json.dumps(entry)+'\n')
            log.flush()
            stop.wait(1)


def previous_boot(trial, original, output, deadline, return_on_accepted=True, request_edl=True):
    while time.monotonic() < deadline:
        if return_on_accepted and (output/'gsi-accepted.json').exists(): return
        ports = comports()
        if ports_with_id(ports, EDL):
            return
        acm = ports_with_id(ports, ACM)
        if len(acm) > 1:
            raise RuntimeError('Multiple diagnostic ports attached')
        if acm:
            try:
                with Serial(acm[0].device, 115200, timeout=.25, write_timeout=3) as console:
                    console.write(QUERY)
                    identity = parse_identity(read_until_line(console, END, 5))
                    if identity['trial'] != trial:
                        raise RuntimeError('Unexpected trial after reset')
                    fresh = UUID(console_query(console, b'cat /proc/sys/kernel/random/boot_id').decode())
                    if fresh != original:
                        mark(output, 'recovery_boot', fresh)
                        (output/'intermediate-boot.json').write_text(json.dumps(
                            dict(boot_id=str(fresh), identity=identity), indent=2)+'\n')
                        console_query(console, b'mkdir -p /run/prev; mount -t pstore pstore /run/prev')
                        for name in ('console-ramoops-0', 'pmsg-ramoops-0'):
                            path = b'/run/prev/'+name.encode()
                            if console_query(console, b'test -s '+path+b' && echo present') == b'present':
                                data = read_console_file(console, b'/run/previous.gz',
                                    b'gzip -c '+path+b' > /run/previous.gz; ')
                                (output/name).write_bytes(gzip.decompress(data))
                        providers = console_query(console, b'echo DEFERRED; cat /sys/kernel/debug/devices_deferred; echo SPMI; ls -l /sys/bus/spmi/devices; echo POWER; dmesg | grep -iE "spmi|pmic|psci|power.?off|pon@|pwrkey|M1AUTO"')
                        (output/'recovery-providers.txt').write_bytes(providers)
                        if not request_edl:
                            until=min(deadline,time.monotonic()+40)
                            while time.monotonic()<until:
                                if console_query(console,b'grep -Eq "disable ioctl rc=0|^recovery watchdog|^M1RECOVERY (watchdog|unexpected)" /run/m1-recovery-watchdog.log 2>/dev/null && echo present')==b'present':
                                    data=read_console_file(console,b'/run/recovery-watchdog.gz',b'gzip -c /run/m1-recovery-watchdog.log > /run/recovery-watchdog.gz; ')
                                    (output/'recovery-watchdog.log').write_bytes(gzip.decompress(data))
                                    break
                                time.sleep(1)
                            return
                        console.write(b'/bin/reboot-edl edl\n')
                        console.flush()
                        # Closing immediately can cancel the last USB write on Windows.
                        until=time.monotonic()+3
                        while time.monotonic()<until:
                            try: console.read(1024)
                            except SerialException: break
                        return
            except (SerialException, TimeoutError, ValueError) as error:
                print('Recovery console:', error, flush=True)
        time.sleep(1)


def observe(trial, output, timeout, staged_display=False):
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
        original = UUID(console_query(console, b'cat /proc/sys/kernel/random/boot_id').decode())
        # Preserve the allocator's boot-time result before Android fills pstore.
        bridge = console_query(console, b"dmesg | grep 'SHM Bridge'")
        (output/'shmbridge.txt').write_bytes(bridge + b'\n')
        if not staged_display and console_query(console, b'test -r /sys/module/qcom_scm/parameters/temp_hmac_key && echo present') == b'present':
            before = int(console_query(console, b'/bin/busybox date -u +%s 2>/dev/null'))
            now = datetime.now(timezone.utc)
            command = now.strftime("/bin/busybox date -u -s '%Y-%m-%d %H:%M:%S' >/dev/null 2>&1 && /bin/busybox date -u +%%s 2>/dev/null")
            after = int(console_query(console, command.encode()))
            if abs(datetime.now(timezone.utc).timestamp() - after) > 5:
                raise ValueError('Diagnostic UTC did not match the USB host')
            (output/'time-control.json').write_text(json.dumps(dict(
                boot_id=str(original), source='USB host UTC', host_utc=now.isoformat(),
                before_seconds=before, after_seconds=after))+'\n')
        (output/'identity.json').write_text(json.dumps(identity, indent=2) + '\n')
        mark(output, 'handoff_requested', original)
        # Capture bootstrap failures too. A failed mount can stop PID 1 before
        # the witness observes a mount syscall, leaving the outer console alive.
        if staged_display:
            if console_query(console, b'test -f /m3-display-staged && echo staged') != b'staged':
                raise ValueError('Expected the staged-display ramdisk gate')
            ready = console_query(console, b'cat /run/m3-display-gate-ready 2>/dev/null')
            if ready != str(original).encode():
                (output/'display-gate-not-ready.txt').write_bytes(console_query(console, b'dmesg | tail -100'))
                raise ValueError('Display gate is not ready for this boot; no display bind requested')
            (output/'display-previous-guard.txt').write_bytes(console_query(
                console, b'cat /run/m3-display-previous-guard 2>/dev/null') + b'\n')
            mark(output, 'display_gate_requested', original)
            # Start the independent stream before allowing any display bind.
            # The host records the entire kernel stream, including fatal stacks.
            console.write(b"\nstty -echo; (cat /dev/kmsg > /dev/ttyGS0) & "
                          b"cat /proc/sys/kernel/random/boot_id > /run/m3-display-start\n")
        else:
            console.write(b"\nstty -echo; cat /proc/sys/kernel/random/boot_id; "
                      b"(cat /dev/kmsg | awk '/init:|libfs_mgr|libfstab|avb|verity|SELinux:|panic|enforcing=|m1_file_read/{print;fflush()}' "
                      b"> /dev/ttyGS0) & "
                      b"/bin/busybox sh -x /bin/first-stage-mount ufs install "
                      b"> /run/gsi17-run.log 2>&1; x=$?; tail -80 /run/gsi17-run.log; "
                      b"echo UFS_STAGE_RC=$x; /bin/reboot-edl edl\n")
        deadline = time.monotonic() + identity['timer_seconds'] + 25
        diagnostic_at = time.monotonic() + 90 if staged_display else None
        with (output/'acm.log').open('xb') as capture:
            tail = b''
            while time.monotonic() < deadline:
                if (output/'gsi-accepted.json').exists(): break
                try:
                    if diagnostic_at is not None and time.monotonic() >= diagnostic_at:
                        # The staged gate leaves this shell free while the
                        # handoff runs separately. Keep its existing stream;
                        # never compete for the COM port or renew a timer here.
                        diagnostic_at = None
                        console.write(handoff_diagnostic_command(original))
                        console.flush()
                        mark(output, 'display_handoff_diagnostic_requested', original)
                    data = console.read(16384)
                except SerialException:
                    break
                if data:
                    capture.write(data)
                    capture.flush()
                elif ports_with_id(comports(), EDL):
                    return
                tail += data
                if b'M1EVENT post_install_window=end' in tail:
                    mark(output, 'post_install_window_end', original)
                    break
                tail = tail[-64:]
    previous_boot(trial, original, output, time.monotonic()+300)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wait', type=int, default=120)
    parser.add_argument('--observe-adb', action='store_true')
    parser.add_argument('--retain-gsi', action='store_true')
    parser.add_argument('--autonomous', action='store_true')
    parser.add_argument('--staged-display', action='store_true')
    args = parser.parse_args()
    if args.staged_display and not args.autonomous:
        parser.error('Staged display requires the existing guarded autonomous handoff')
    stop = threading.Event()
    args.output.mkdir(parents=True, exist_ok=False)
    if args.observe_adb:
        monitor = threading.Thread(target=watch_adb, args=(args.output, stop, args.retain_gsi, args.autonomous))
        monitor.start()
    try:
        if args.staged_display:
            observe(args.trial, args.output, args.wait, staged_display=True)
        elif args.autonomous:
            deadline=time.monotonic()+400
            while ports_with_id(comports(),EDL) and time.monotonic()<deadline: time.sleep(.25)
            previous_boot(args.trial,UUID(int=0),args.output,deadline)
        else:
            observe(args.trial, args.output, args.wait)
    finally:
        stop.set()
        if args.observe_adb:
            monitor.join()
