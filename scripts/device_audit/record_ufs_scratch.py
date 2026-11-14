"""Extract first-crash, Binder, vdc, APEX and physical USB evidence from a scratch trial."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from record_ufs_first_stage import adb_observations, match, record, vendor_services


def usb_interfaces(port_log, live):
    events = [json.loads(row) for row in (live/'host-events.jsonl').read_text().splitlines()]
    times = {e['event']: datetime.fromisoformat(e['utc']) for e in events}
    start, stop = times['handoff_requested'], times['recovery_boot']
    observations = list(map(json.loads, port_log.read_text(encoding='utf-8-sig').splitlines()))
    rows = [row for row in observations if start <= datetime.fromisoformat(row['utc']) <= stop]
    if not rows:
        raise ValueError('No physical USB samples during handoff')
    ids = sorted({device['id'] for row in rows for device in row['devices']})
    compatible = sorted({cid for row in rows for device in row['devices'] for cid in device['compatible']
                         if cid and cid.startswith('USB\\Class_')})
    stamps = [start, *[datetime.fromisoformat(row['utc']) for row in rows], stop]
    return dict(samples=len(rows), device_ids=ids, interface_ids=compatible,
                adb_interface_seen=any(i.upper() == 'USB\\CLASS_FF&SUBCLASS_42&PROT_01' for i in compatible),
                max_gap_seconds=round(max((b-a).total_seconds() for a,b in zip(stamps, stamps[1:])), 3),
                raw_sha256=hashlib.sha256(port_log.read_bytes()).hexdigest())


def keymaster_observations(serial, console, keystore):
    result = {}
    version = re.search(r'^M1EVENT keymaster_version transport_rc=(0) status=(0) '
                        r'api=(\d+\.\d+) ta=(\d+\.\d+)$', serial, re.M)
    if version:
        result['version_transaction'] = dict(transport_rc=0, status=0, api=version[3], ta=version[4])
    fields = ('id', 'register_rc', 'register_result', 'unregister_rc', 'unregister_result')
    lifetime = r'^M1EVENT qsee_listener_lifetime ' + ' '.join(f + r'=(-?\d+)' for f in fields) + '$'
    rows = [dict(zip(fields, map(int, row.groups()))) for row in re.finditer(lifetime, serial, re.M)]
    if rows:
        result['listener_lifetimes'] = rows
    key_fields = ('rc', 'first', 'listener', 'command', 'callbacks', 'final', 'generate',
                  'blob_bytes', 'delete', 'unregister')
    key = re.search(r'^M1EVENT temporary_key ' + ' '.join(f + r'=(-?\d+)' for f in key_fields) + '$',
                    serial, re.M)
    if key:
        result['temporary_hmac_key'] = dict(zip(key_fields, map(int, key.groups())))

    # Match the init-launched service and client from the same boot. The log
    # in getHardwareInfo runs after the HIDL service has invoked its reply.
    service = re.search(r"^\[\s*([0-9.]+)\]\[\s*T1\] init: \.\.\. started service 'vendor.rmx-keymaster'"
                        r" has pid (\d+)$", console, re.M)
    if service:
        pid = int(service[2])
        prefix = rf'^\[\s*([0-9.]+)\]\[\s*T{pid}\] ks_log: [^\n]*? tag="RMXKeymaster" msg="'
        registered = re.search(prefix + 'registered default"$', console[service.end():], re.M)
        reply = re.search(prefix + rf'getHardwareInfo caller={keystore} level=(\w+) name=([^"]+)"$',
                          console[service.end():], re.M)
        if registered and reply and float(registered[1]) <= float(reply[1]):
            result['gsi_hidl_reply'] = dict(instance='android.hardware.keymaster@4.0::IKeymasterDevice/default',
                                            service_pid=pid, caller='keystore2', caller_pid=keystore,
                                            registration_seconds=float(registered[1]), reply_seconds=float(reply[1]),
                                            level=reply[2], name=reply[3])
            after = console[service.end()+reply.end():]
            parameters = re.search(prefix + rf'getHmacSharingParameters caller={keystore} status=(-?\d+)"$',
                                   after, re.M)
            if parameters:
                result['hmac_parameter_reply'] = dict(service_pid=pid, caller_pid=keystore,
                                                      seconds=float(parameters[1]), status=int(parameters[2]))
            negotiation = re.search(r'^\[\s*([0-9.]+)\]\[\s*T\d+\] ks_buf: [^\n]* tag="keystore2" '
                                    r'msg="[^\n]*ParameterRetrieval \{ e: Binder\(SERVICE_SPECIFIC, (-?\d+)\), '
                                    r'p: Hidl \{ is_strongbox: false, version: \(4, 0\)',
                                    console[service.end()+reply.end():], re.M)
            if negotiation:
                result['shared_secret_parameter_error'] = dict(seconds=float(negotiation[1]), rc=int(negotiation[2]))
            computation = re.search(r'^\[\s*([0-9.]+)\]\[\s*T\d+\] ks_buf: [^\n]* tag="keystore2" '
                                    r'msg="[^\n]*Computation \{ e: Binder\(SERVICE_SPECIFIC, (-?\d+)\)',
                                    after, re.M)
            if computation:
                result['shared_secret_computation_error'] = dict(seconds=float(computation[1]), rc=int(computation[2]))
    return result


def extract(live, port_log, layout, *, console_tail=False):
    trial = record(live, layout, console_tail=console_tail)
    if console_tail:
        trial['adb'] = adb_observations(live, trial)
        trial['console_start_missing'] = True
    else:
        trial.update(vendor_services(live, trial))
    console = (live/'console-ramoops-0').read_bytes().decode('utf8', errors='replace').replace('\r','')
    serial = (live/'acm.log').read_bytes().decode('utf8', errors='replace').replace('\r','')
    pmsg = (live/'pmsg-ramoops-0').read_bytes()
    volumes = {}
    for name, dev in [('data','7:0'), ('metadata','7:1')]:
        match(rf'^M1EVENT scratch_mount=/{name} device={dev} flags=rw,[^ ]+ fs=ext4$', serial)
        match(rf'^M1EVENT scratch_backing=/{name} file=/run/m1-scratch/{name}.ext4$', serial)
        volumes[name] = dict(device=dev, filesystem='ext4', backing=f'/run/m1-scratch/{name}.ext4',
                             write_fsync_unlink='PASS')
    match(r'^M1EVENT keystore_trace=armed$', serial)
    trial['raw_sha256']['pmsg-ramoops-0'] = hashlib.sha256(pmsg).hexdigest()
    proc = match(r"^\[\s*([0-9.]+)\]\[\s*T1\] init: \.\.\. started service 'keystore2' has pid (\d+)$", console)
    pid = int(proc[2])
    observations = keymaster_observations(serial, console, pid)
    if observations:
        trial['keymaster'] = observations
    clock = live/'time-control.json'
    if clock.exists():
        control = json.loads(clock.read_text())
        if control['boot_id'] != trial['boot_id']:
            raise ValueError('UTC observation belongs to a different boot')
        trial['diagnostic_clock'] = control
    abort = re.search(rf"^\[\s*([0-9.]+)\]\[\s*T1\] init: Service 'keystore2' \(pid {pid}\) received SIGABRT$", console, re.M)
    trial['first_keystore_abort'] = None
    if abort:
        before = console[proc.start():abort.start()]
        # printk prepends the same timestamp and TID to each line of a Rust panic.
        # Keep the full multiline cause chain, plus the registration entry and return.
        logs = [re.sub(r'\(0x[0-9a-f]+(?: <- 0x[0-9a-f]+)?\)', '(uprobe)', line)
                for line in before.splitlines() if re.match(rf'^\[\s*[0-9.]+\]\[\s*T{pid}\] ', line)]
        if not any('panicked at' in l for l in logs):
            raise ValueError('First SIGABRT captured without its matching panic log')
        trial['first_keystore_abort'] = dict(pid=pid, start_seconds=float(proc[1]), sigabrt_seconds=float(abort[1]),
                                             first_process_log=logs)
    attempted = sorted(set(re.findall(r'ks_add: .* task="keystore2" name="([^"]+)"',console)))
    missing = [l for l in console.splitlines() if "Could not find 'aidl/android.security.maintenance'" in l]
    vdc = match(r"^.*SVC_EXEC service '(exec \d+ \(/system/bin/vdc keymaster earlyBootEnded\))' pid (\d+).*waiting\.\.\.$",console)
    end = re.search(r"^.*init: Service '"+re.escape(vdc[1])+r"' \(pid "+vdc[2]+r"\) .+$",console[vdc.end():],re.M)
    registrations = []
    pending = {}
    for line in console.splitlines():
        entry = re.search(r'\[\s*T(\d+)\] ks_add: .* task="keystore2" name="([^"]+)"', line)
        if entry:
            pending[entry[1]] = entry[2]
        ret = re.search(r'\[\s*T(\d+)\] ks_added: .* task="keystore2" rc=(-?\d+)', line)
        if ret and ret[1] in pending:
            registrations.append(dict(tid=int(ret[1]), name=pending.pop(ret[1]), rc=int(ret[2])))
    trial['keystore_registrations'] = registrations
    lookup = re.search(r'^M1EVENT qsee_lookup keymaster=(-?\d+) keymaster64=(-?\d+)$', serial, re.M)
    if lookup:
        trial['qsee_app_lookup_rc'] = dict(keymaster=int(lookup[1]), keymaster64=int(lookup[2]))
    trial.update(scratch_mounts=volumes, keystore_add_service_attempts=attempted,
                 maintenance_last_lookup_failure=missing[-1] if missing else None,
                 vdc=dict(pid=int(vdc[2]),start=vdc[0], exit_record=end[0] if end else None),
                 usb=usb_interfaces(port_log,live))
    trial['apex_observations'] = [l for l in console.splitlines() if
        ('apexd' in l and ('com.google.android.adbd' in l or 'Found bootstrap APEX' in l or 'Activated ' in l))
        or re.search(r"init: starting service '(adbd|apexd)'", l)]
    trial['keystore_sigabrt_count'] = len(re.findall(r"init: Service 'keystore2' \(pid \d+\) received SIGABRT",console))
    trial['keystore_entropy_waits'] = [
        re.sub(r'\([^)]*\)', '(probe)', line)
        for line in console.splitlines() if re.search(r'ks_random_(wait|ready): .*task="keystore2"', line)
    ]
    return trial


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['capture','usb','layout']:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--console-tail', action='store_true', help='Early timestamps and file reads rolled out of the console')
    args = parser.parse_args()
    print(json.dumps(extract(args.capture, args.usb, json.loads(args.layout.read_text()), console_tail=args.console_tail), indent=2))
