"""Extract first-crash, Binder, vdc, APEX and physical USB evidence from a scratch trial."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from record_ufs_first_stage import match, record, vendor_services


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


def extract(live, port_log, layout):
    trial = record(live, layout)
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
    abort = match(rf"^\[\s*([0-9.]+)\]\[\s*T1\] init: Service 'keystore2' \(pid {pid}\) received SIGABRT$", console)
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
    trial.update(scratch_mounts=volumes, keystore_add_service_attempts=attempted,
                 maintenance_last_lookup_failure=missing[-1] if missing else None,
                 vdc=dict(pid=int(vdc[2]),start=vdc[0], exit_record=end[0] if end else None),
                 usb=usb_interfaces(port_log,live))
    trial['apex_observations'] = [l for l in console.splitlines() if
        ('apexd' in l and ('com.google.android.adbd' in l or 'Found bootstrap APEX' in l or 'Activated ' in l))
        or re.search(r"init: starting service '(adbd|apexd)'", l)]
    trial['keystore_sigabrt_count'] = len(re.findall(r"init: Service 'keystore2' \(pid \d+\) received SIGABRT",console))
    return trial


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['capture','usb','layout']:
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(extract(args.capture, args.usb, json.loads(args.layout.read_text())), indent=2))
