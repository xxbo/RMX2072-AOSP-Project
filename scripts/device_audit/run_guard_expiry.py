"""Inject loss of a retained guard's lease and observe autonomous EDL fallback.

No reboot command is sent. Recovery-console reads only capture old pstore.
Restore the verified original set after this check before further qualification.
"""
import argparse,hashlib,json,re,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
from uuid import UUID
from gsi_adb_accept import inspect,shell

def verify_fault_capture(output, boot, require_disarm):
    console=(output/'console-ramoops-0').read_text(errors='replace')
    journal=(output/'pmsg-ramoops-0').read_bytes()
    recovery=json.loads((output/'intermediate-boot.json').read_text())['boot_id']
    UUID(recovery)
    if recovery==boot or ('RMX-M1-AUTO boot='+boot+' state=expired').encode() not in journal:
        raise ValueError('No matching expired boot and distinct recovery boot')
    providers=(output/'recovery-providers.txt').read_text(errors='replace')
    marker='M1AUTO boot='+recovery+' previous=RMX-M1-AUTO boot='+boot+' state=expired'
    # Early boot IDs can rotate out of the old console ring. Correlate its
    # expiry/pretimeout interval with the recovery boot's parsed pmsg identity.
    expired=[float(x) for x in re.findall(r'\[\s*(\d+\.\d+)\].*RMX-M1-GUARD state=expired',console)]
    pretimeout=[float(x) for x in re.findall(r'\[\s*(\d+\.\d+)\].*watchdog0: pretimeout event',console)]
    if marker not in providers or not any(28<=b-a<=30.5 for a in expired for b in pretimeout):
        raise ValueError('No correlated recovery journal and kernel watchdog pretimeout')
    if require_disarm:
        disarm=(output/'recovery-watchdog.log').read_text()
        if ('M1RECOVERY boot='+recovery+' ' not in disarm or
            'AP watchdog disable ioctl rc=0 identity=qcom_wdt' not in disarm):
            raise ValueError('Recovery watchdog disable not confirmed for this boot')
    return recovery


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',type=Path,required=True)
    p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--trial',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--edl-hold-seconds',type=int,default=0)
    p.add_argument('--require-watchdog-disarm',action='store_true')
    p.add_argument('--capture-next-edl',action='store_true',help='After verified reset/disarm, arm the prepared restore runner before EDL appears; requires zero hold')
    p.add_argument('--recovery-gate',type=Path,help='Atomically release a preverified restore runner after EDL qualification')
    a=p.parse_args();sys.path.insert(0,str(a.workspace.resolve()/'serial-deps'))
    assert 0<=a.edl_hold_seconds<=120
    assert not a.recovery_gate or not a.recovery_gate.exists()
    assert not a.capture_next_edl or (a.recovery_gate and a.require_watchdog_disarm and a.edl_hold_seconds==0)
    from serial.tools.list_ports import comports
    from observe_ufs_first_stage import previous_boot
    from usb_edl_return import ACM,EDL,ports_with_id
    boot=shell('cat /proc/sys/kernel/random/boot_id').strip();UUID(boot)
    proof=inspect(a.evidence,boot)
    assert proof['identity'][6]=='retained'
    a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'before.json').write_text(json.dumps(proof,indent=2)+'\n')
    audit=Path(__file__).resolve().parent
    (a.output/'host-tools.json').write_text(json.dumps(dict(
        source_commit=subprocess.check_output(['git','-C',str(audit.parents[1]),'rev-parse','HEAD'],text=True).strip(),
        sha256={name:hashlib.sha256((audit/name).read_bytes()).hexdigest() for name in
                ('run_guard_expiry.py','observe_ufs_first_stage.py','run_ufs_trial.py','gsi_adb_accept.py')}
    ),indent=2)+'\n')
    start=time.monotonic()
    (a.output/'fault.json').write_text(json.dumps(dict(boot_id=boot,utc=datetime.now(timezone.utc).isoformat(),command='expire-lease',lease_seconds=45,hardware_seconds=30,host_reboot_commands=False),indent=2)+'\n')
    assert shell('/vendor/bin/hw/rmx-m1-control --expire-lease '+boot).strip()=='lease'
    def release_gate(**status):
        row=dict(trial=a.trial,allow_recovery=True,boot_id=boot,
                 host_reboot_commands=False,utc=datetime.now(timezone.utc).isoformat(),**status)
        pending=a.recovery_gate.with_suffix('.tmp')
        pending.write_text(json.dumps(row)+'\n');pending.replace(a.recovery_gate)
        (a.output/'recovery-gate.json').write_text(json.dumps(row,indent=2)+'\n')
    captured=False;last=None;edl_since=None
    with (a.output/'transport.jsonl').open('w') as log:
        while time.monotonic()-start<300+a.edl_hold_seconds:
            ports=comports()
            row=dict(elapsed=round(time.monotonic()-start,3),ports=[dict(device=x.device,vid=x.vid,pid=x.pid) for x in ports if (x.vid,x.pid) in (ACM,EDL)])
            if ports_with_id(ports,EDL):
                if edl_since is None:edl_since=time.monotonic()
                row['edl_continuous_seconds']=round(time.monotonic()-edl_since,3)
                row['automatic_edl']=True;log.write(json.dumps(row)+'\n');log.flush()
                if time.monotonic()-edl_since<a.edl_hold_seconds:
                    time.sleep(.5);continue
                recovery=verify_fault_capture(a.output,boot,a.require_watchdog_disarm)
                (a.output/'result.json').write_text(json.dumps(dict(boot_id=boot,recovery_boot_id=recovery,automatic_edl=True,elapsed=row['elapsed'],edl_continuous_seconds=row['edl_continuous_seconds'],capture_next_edl=a.capture_next_edl,journal_expired=True,kernel_pretimeout=True,recovery_watchdog_disarm_verified=a.require_watchdog_disarm,host_reboot_commands=False),indent=2)+'\n')
                if a.recovery_gate and not a.capture_next_edl:
                    release_gate(automatic_edl=True,edl_continuous_seconds=row['edl_continuous_seconds'])
                print('Lease expiry and autonomous EDL fallback verified',flush=True);return
            if edl_since is not None:
                (a.output/'edl-window-failure.json').write_text(json.dumps(dict(result='FAIL_EDL_HOLD',automatic_edl_observed=True,held_seconds=round(time.monotonic()-edl_since,3),required_seconds=a.edl_hold_seconds),indent=2)+'\n')
                raise RuntimeError('EDL disappeared before the required recovery window')
            if ports_with_id(ports,ACM) and not captured:
                previous_boot(a.trial,UUID(boot),a.output,time.monotonic()+60,return_on_accepted=False,request_edl=False)
                captured=True
                row['capture_completed_elapsed']=round(time.monotonic()-start,3)
                if a.capture_next_edl:
                    recovery=verify_fault_capture(a.output,boot,True)
                    release_gate(await_autonomous_edl=True,recovery_boot_id=recovery,
                                 reset_and_disarm_verified=True)
                    print('Reset and disarm verified; restore runner armed for next autonomous EDL',flush=True)
            try:row['adb']=shell('cat /proc/sys/kernel/random/boot_id; getprop vendor.rmx.m1.state',3).splitlines()
            except (OSError,subprocess.SubprocessError):pass
            log.write(json.dumps(row)+'\n');log.flush()
            if row.get('adb') and row['adb'][0] != boot:
                failure=dict(result='FAIL_AUTONOMOUS_EDL',old_boot=boot,
                             unexpected_new_gsi_boot=row['adb'][0],elapsed=row['elapsed'],
                             host_reboot_commands=False)
                (a.output/'failure.json').write_text(json.dumps(failure,indent=2)+'\n')
                raise RuntimeError('Watchdog restarted GSI instead of selecting recovery')
            state=(row['ports'],row.get('adb'))
            if state!=last:print(json.dumps(row),flush=True);last=state
            time.sleep(1)
    raise TimeoutError('Autonomous EDL fallback not confirmed; inspect USB and restore F20')

if __name__=='__main__':main()
