"""Publish an operator-controlled disconnected start with timed ADB evidence.

This does not infer power-off from USB absence alone. The operator's power-key
response, scheduled shutdown window, new boot uptime, local guard acceptance
and subsequent same-boot soak must all agree.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
from check_power_ready import check_power_ready


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record',type=Path,required=True)
    parser.add_argument('--warm-record',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args(); root=a.record; live=root/'reconnect'
    load=lambda p:json.loads(p.read_text(encoding='utf-8'))
    lines=lambda p:[json.loads(x) for x in p.read_text(encoding='utf-8').splitlines()]
    scheduled=load(root/'scheduled.json'); steps=lines(root/'operator.jsonl')
    unplug,power,reconnect=steps
    assert [s['event'] for s in steps]==['operator_unplug_confirmed',
        'operator_power_key_response_while_disconnected','operator_reconnect_confirmed']
    assert unplug['monotonic']<scheduled['planned_host_monotonic']
    assert power['monotonic']>scheduled['planned_host_monotonic']+25
    assert reconnect['monotonic']>power['monotonic']+90
    assert 'RMX2072-M1' not in unplug['adb'] and 'RMX2072-M1' not in power['adb']
    accepted=load(live/'gsi-accepted.json'); stable=load(live/'gsi-stable.json')
    arrival=load(live/'arrival-identity.json'); boot=arrival['identity'][0]
    assert boot!=scheduled['boot_id'] and boot==accepted['identity'][2]==stable['identity'][2]
    assert accepted['guard_mode_at_acceptance']==stable['guardian']=='retained'
    assert stable['seconds']>=190 and stable['identity'][3]=='Enforcing'
    assert arrival['identity'][2:8]==[stable['identity'][1],'37','Enforcing','retained','local-adbd','1']
    uptime=float(arrival['identity'][1].split()[0])
    bounds=[arrival[k]-uptime for k in ('monotonic_start','monotonic_end')]
    # Boot began after the shutdown window, no later than the operator reply.
    assert bounds[0]>scheduled['planned_host_monotonic']+25
    assert bounds[1]<power['monotonic']+5
    transports=lines(live/'transports.jsonl')
    at=next(i for i,r in enumerate(transports) if r.get('boot_id')==boot)
    absent=next(i for i,r in enumerate(transports) if not r.get('transports'))
    assert absent<at and all(not r.get('transports') for r in transports[absent:at])
    def mono(utc):
        return scheduled['monotonic']+(datetime.fromisoformat(utc)-datetime.fromisoformat(scheduled['utc'])).total_seconds()
    first=mono(transports[at]['utc'])
    assert mono(transports[absent]['utc'])<scheduled['planned_host_monotonic']
    before_usb=first-bounds[1]
    assert before_usb>=60
    power_check=check_power_ready((live/'power-providers.txt').read_text(),boot)
    assert power_check==load(live/'power-driver-check.json')
    smoke=load(live/'adb-smoke.json')
    assert smoke['device_sha256']==smoke['returned_sha256'] and smoke['bytes']==1048576
    result=dict(result='PASS_OPERATOR_CONTROLLED_DISCONNECTED_START',boot_id=boot,
        warm_inputs=load(a.warm_record/'inputs.json'),scheduled_shutdown=scheduled,
        operator_steps=steps,first_usb_absence=transports[absent],first_new_boot_adb=transports[at],
        arrival_identity=arrival,estimated_kernel_start_host_monotonic=bounds,
        kernel_running_before_first_adb_seconds=round(before_usb,3),
        power_drivers=power_check,identity=stable['identity'],pid1=stable['pid1'],
        ufs_evidence=stable['ufs_evidence'],soak_seconds=stable['seconds'],adb_smoke=smoke,
        autonomous_events=[s for s in (live/'boot-events.txt').read_text().splitlines()
            if s.startswith(('M1EVENT autonomous=','M1EVENT previous_guard=','M1EVENT boot_usb_state='))],
        previous_poweroff_console='Absent after this power cycle; notifier execution was not captured',
        watchdog_recovery_on_this_kernel='NOT RUN',current_mode='Android 17 GSI retained',
        raw_sha256={str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
            for d in (root,live) for p in d.iterdir() if p.is_file() and p.stat().st_size<10000000})
    if result['warm_inputs']['boot'].get('source_device_trees'):
        from check_m2_boot import check_m2_boot
        components=check_m2_boot((live/'m2-components.txt').read_text(),boot,
            result['warm_inputs']['ramdisk']['first_stage_init_sha256'],stable['identity'][1])
        assert components==load(live/'m2-components.json')
        assert power_check['binding']=='upstream-pon-parent-pwrkey-child'
        result['source_boot_components']=components
    a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(result['result'],boot,round(before_usb,3))


if __name__=='__main__':main()
