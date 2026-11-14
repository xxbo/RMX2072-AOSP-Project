"""Wait for a new autonomous boot after a separately recorded operator power cycle.

This observer never requests Android handoff or sets the device clock. USB
absence alone does not establish cold power-off; preserve the operator steps.
"""
import argparse,json,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
from uuid import UUID
from gsi_adb_accept import SERIAL,shell,fetch_autonomous,accept,soak_and_retain

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--previous-boot',type=UUID,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--timeout',type=int,default=900)
    p.add_argument('--warm-record',type=Path,help='Require the same M2 source components as the accepted warm trial')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    warm=json.loads((a.warm_record/'inputs.json').read_text()) if a.warm_record else None
    start=time.monotonic();last=None
    (a.output/'observer.json').write_text(json.dumps(dict(previous_boot=str(a.previous_boot),utc=datetime.now(timezone.utc).isoformat(),starts_android=False,sets_clock=False),indent=2)+'\n')
    with (a.output/'transports.jsonl').open('w') as log:
        while time.monotonic()-start<a.timeout:
            row=dict(elapsed=round(time.monotonic()-start,3),utc=datetime.now(timezone.utc).isoformat())
            try:
                listing=subprocess.check_output(['adb','devices','-l'],text=True,timeout=3)
                row['transports']=[x for x in listing.splitlines() if x.strip() and not x.startswith('List of devices')]
                if any(x.startswith(SERIAL) and x.split()[1]=='device' for x in row['transports']):
                    boot=shell('cat /proc/sys/kernel/random/boot_id').strip();UUID(boot);row['boot_id']=boot
                    if boot!=str(a.previous_boot):
                        before=time.monotonic()
                        identity=shell('cat /proc/sys/kernel/random/boot_id; cat /proc/uptime; uname -r; getprop ro.build.version.sdk; getenforce; getprop vendor.rmx.m1.state; getprop vendor.rmx.m1.accepted_by; getprop vendor.rmx.m1.usb_ready; service check android.security.maintenance').splitlines()
                        arrival=dict(utc=datetime.now(timezone.utc).isoformat(),monotonic_start=before,monotonic_end=time.monotonic(),identity=identity)
                        if len(identity)!=9 or identity[0]!=boot or identity[5:8]!=['retained','local-adbd','1']:
                            raise ValueError('New boot has not yet passed local readiness')
                        (a.output/'arrival-identity.json').write_text(json.dumps(arrival,indent=2)+'\n')
                        assert fetch_autonomous(a.output)==boot
                        try:
                            if warm and warm['boot'].get('source_device_trees'):
                                from check_m2_boot import check_m2_boot
                                text=shell('cat /data/local/tmp/rmx-m2-boot.txt')
                                components=check_m2_boot(text,boot,warm['ramdisk']['first_stage_init_sha256'],identity[2])
                                (a.output/'m2-components.txt').write_text(text)
                                (a.output/'m2-components.json').write_text(json.dumps(components,indent=2)+'\n')
                            from check_power_ready import check_power_ready
                            power=shell('cat /data/local/tmp/rmx-m1-power.txt')
                            checked=check_power_ready(power,boot)
                            (a.output/'power-providers.txt').write_text(power)
                            (a.output/'power-driver-check.json').write_text(json.dumps(checked,indent=2)+'\n')
                        except (OSError,subprocess.SubprocessError,ValueError) as error:
                            try:
                                shell('/vendor/bin/hw/rmx-m1-control --rollback '+boot)
                            except (OSError,subprocess.SubprocessError):
                                pass
                            raise RuntimeError('Cold-start source/power evidence failed; guarded rollback requested') from error
                        accept(a.output,boot)
                        print('Accepted new autonomous GSI boot '+boot,flush=True)
                        log.write(json.dumps(row)+'\n');log.flush()
                        result=soak_and_retain(a.output)
                        (a.output/'result.json').write_text(json.dumps(dict(current_mode='Android 17 GSI',stable=result,previous_boot=str(a.previous_boot),cold_power_cycle='Requires separate operator/USB evidence'),indent=2)+'\n')
                        print('New autonomous boot retained',flush=True)
                        return
            except (OSError,subprocess.SubprocessError,ValueError) as error:
                row['error']=str(error)
            log.write(json.dumps(row)+'\n');log.flush()
            state=(row.get('transports'),row.get('boot_id'),row.get('error'))
            if state!=last:print(json.dumps(row),flush=True);last=state
            time.sleep(1)
    raise TimeoutError('No accepted new autonomous GSI boot; inspect USB and recover F20')

if __name__=='__main__':main()
