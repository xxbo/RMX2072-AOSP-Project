"""Requalify an already locally retained GSI after a pause, without rebooting it.

Expected image inputs come from the previous verified flash. The boot-only
writer must still read and hash the physical boot, DTBO and super before writing.
This observer never changes the guard lease or requests recovery on failure.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from check_power_ready import check_power_ready
from gsi_adb_accept import collect, fetch_autonomous, inspect, shell
from gsi_adb_smoke import run as transfer_smoke


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--previous-record', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    work = args.workspace.resolve()
    prior = args.previous_record.resolve()
    output = args.output.resolve()
    if prior.parent != work / 'records' or output.parent != work / 'records' or prior == output:
        parser.error('Use separate record directories in this workspace')
    inputs_raw = (prior / 'inputs.json').read_bytes()
    inputs = json.loads(inputs_raw)
    previous = json.loads((prior / 'live/gsi-stable.json').read_text())
    if previous.get('guardian') != 'retained' or previous.get('seconds', 0) < 190:
        raise ValueError('Previous flash has no accepted stable GSI record')
    for key, filename in [('candidate', 'candidate/candidate.json'), ('scratch', 'volumes/scratch.json')]:
        if inputs[key] != json.loads((work / 'current' / filename).read_text()):
            raise ValueError('Container or test-volume seeds changed since the verified flash')
    live = output / 'live'
    live.mkdir(parents=True, exist_ok=False)
    boot = fetch_autonomous(live)
    proof = inspect(live, boot)
    if proof['identity'][6] != 'retained':
        raise ValueError('This observer requires an already retained boot')
    readiness = shell('getprop vendor.rmx.m1.accepted_by; getprop vendor.rmx.m1.usb_ready; service check android.security.maintenance').splitlines()
    if readiness != ['local-adbd', '1', 'Service android.security.maintenance: found']:
        raise ValueError('Local ADB and maintenance readiness not confirmed')
    power_text = shell('cat /data/local/tmp/rmx-m1-power.txt')
    power = check_power_ready(power_text, boot)
    (live / 'power-providers.txt').write_text(power_text)
    (live / 'power-driver-check.json').write_text(json.dumps(power, indent=2) + '\n')
    if inputs['boot'].get('source_device_trees'):
        from check_m2_boot import check_m2_boot
        text = shell('cat /data/local/tmp/rmx-m2-boot.txt')
        checked = check_m2_boot(text, boot, inputs['ramdisk']['first_stage_init_sha256'],
                                proof['identity'][1], (live / 'boot-events.txt').read_text(),
                                display=inputs['boot'].get('device_tree_build', {}).get('display', False))
        (live / 'm2-components.txt').write_text(text)
        (live / 'm2-components.json').write_text(json.dumps(checked, indent=2) + '\n')
    start = time.monotonic()
    samples = []
    print('Observing locally retained boot ' + boot, flush=True)
    while time.monotonic() - start < 190:
        proof = inspect(live, boot)
        if proof['identity'][6] != 'retained':
            raise ValueError('Local retention was lost')
        samples.append(dict(elapsed=round(time.monotonic() - start, 3), identity=proof['identity']))
        time.sleep(10)
    transfer_smoke(live, boot)
    proof = inspect(live, boot)
    if proof['identity'][6] != 'retained':
        raise ValueError('Local retention was lost during ADB transfer')
    proof.update(guardian='retained', seconds=round(time.monotonic() - start, 3),
                 soak=samples, guard_mode_during_soak='retained', observer_sent_keep=False)
    (live / 'gsi-stable.json').write_text(json.dumps(proof, indent=2) + '\n')
    collect(live)
    (output / 'inputs.json').write_bytes(inputs_raw)
    record = dict(result='PASS_RETAINED_GSI_REOBSERVATION', utc=datetime.now(timezone.utc).isoformat(),
                  boot_id=boot, previous_record=prior.name,
                  expected_inputs_sha256=hashlib.sha256(inputs_raw).hexdigest(),
                  physical_image_hashes='Still require EDL readback before any boot-only update',
                  cold_start='NOT CLAIMED: no timed operator power-cycle evidence',
                  reboot_requested=False, guard_lease_changed=False, soak_seconds=proof['seconds'])
    (output / 'reobservation.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
